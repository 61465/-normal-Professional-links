"""
MobeFace Backend — Live Tech Deals Aggregator
يجمع باستمرار من Craigslist (متعدد المدن) + eBay RSS ويخزّن في SQLite،
ثم يخدم الفلاتر من الـ DB (سريع جداً، بدون اعتماد على المصادر الخارجية وقت الطلب).
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from storage import (
    init_db, upsert_many, query_listings, cleanup_old, stats, count_listings,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("mobeface")

ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL_SECONDS", "600"))  # 10 min
SCRAPE_ON_STARTUP = os.getenv("SCRAPE_ON_STARTUP", "1") == "1"

app = FastAPI(title="MobeFace API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Headers تحاكي متصفح حقيقي ─────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
FEED_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
}
TIMEOUT = 20.0

# ── مدن Craigslist (الأقرب لـ Springfield 01119) ──────────────────────────
CRAIGSLIST_CITIES = ["springfield", "westernmass", "hartford", "boston", "providence"]

# ── استعلامات شاملة ──────────────────────────────────────────────────────
EBAY_QUERIES = [
    "iphone used unlocked", "iphone for parts", "iphone 13", "iphone 14", "iphone 15",
    "samsung galaxy used", "samsung galaxy broken", "samsung s23", "samsung s24",
    "google pixel used", "pixel 7", "pixel 8",
    "oneplus phone used", "motorola unlocked", "xiaomi phone",
    "ps5 console", "ps5 slim", "ps4 pro",
    "xbox series x", "xbox series s", "xbox one",
    "nintendo switch oled", "nintendo switch lite", "switch console",
    "steam deck", "rog ally",
    "ipad air used", "ipad pro used", "samsung tab",
    "macbook air used", "macbook pro used", "dell xps", "thinkpad",
    "airpods pro", "apple watch used", "galaxy watch",
]

CRAIGSLIST_QUERIES = [
    ("moa", "iphone"), ("moa", "samsung"), ("moa", "pixel"), ("moa", "oneplus"),
    ("moa", "ipad"), ("moa", "android"), ("moa", "phone"),
    ("vgm", "ps5"), ("vgm", "ps4"), ("vgm", "xbox"), ("vgm", "switch"),
    ("vgm", "steam deck"), ("vgm", "console"),
    ("sys", "macbook"), ("sys", "laptop"), ("sys", "thinkpad"),
    ("ela", "airpods"), ("ela", "apple watch"), ("ela", "earbuds"),
]

CATEGORY_RULES = {
    "phone":      ["iphone", "samsung", "galaxy", "pixel", "motorola", "oneplus", "xiaomi", "phone", "android"],
    "gaming":     ["ps5", "ps4", "xbox", "nintendo", "switch", "playstation", "quest", "gaming", "console", "steam deck", "rog ally"],
    "tablet":     ["ipad", "tab ", "tablet"],
    "laptop":     ["macbook", "laptop", "dell", "hp ", "lenovo", "thinkpad", "xps"],
    "accessories":["airpods", "watch", "earbud", "headphone", "galaxy watch"],
}

PARTS_KEYWORDS = [
    "broken", "cracked", "parts", "for parts", "bad esn", "icloud",
    "locked", "bent", "water damage", "won't turn", "does not turn",
    "smashed", "damaged", "repair", "spares", "not working", "dead",
]

FAULT_PATTERNS = {
    "Cracked Screen":     ["cracked screen", "broken screen", "smashed screen"],
    "Cracked Back Glass": ["cracked back", "broken back glass"],
    "iCloud Locked":      ["icloud", "activation locked"],
    "Carrier Locked":     ["carrier locked", "network locked"],
    "Won't Turn On":      ["won't turn on", "does not turn on", "dead", "no power"],
    "Water Damage":       ["water damage", "liquid damage"],
    "Battery Issue":      ["battery", "swollen battery"],
    "Face ID Broken":     ["face id", "no face id"],
    "Bent Frame":         ["bent frame", "bent body"],
}

CATEGORY_IMAGES = {
    "phone":       "https://images.unsplash.com/photo-1598300042247-d088f8ab3a91?w=400&q=70",
    "gaming":      "https://images.unsplash.com/photo-1606813907291-d86efa9b94db?w=400&q=70",
    "tablet":      "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&q=70",
    "laptop":      "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=400&q=70",
    "accessories": "https://images.unsplash.com/photo-1600294037681-c80b4cb5b434?w=400&q=70",
    "other":       "https://images.unsplash.com/photo-1518770660439-4636190af475?w=400&q=70",
}


# ── مساعدات ────────────────────────────────────────────────────────────────
def detect_category(text: str) -> str:
    t = text.lower()
    for cat, kws in CATEGORY_RULES.items():
        if any(k in t for k in kws):
            return cat
    return "other"


def detect_condition(text: str) -> str:
    t = text.lower()
    return "parts" if any(k in t for k in PARTS_KEYWORDS) else "working"


def detect_fault(text: str) -> str | None:
    t = text.lower()
    for fault, patterns in FAULT_PATTERNS.items():
        if any(p in t for p in patterns):
            return fault
    return None


def extract_price(text: str) -> int | None:
    match = re.search(r'\$\s*([\d,]+(?:\.\d{2})?)', text or "")
    if match:
        try:
            return int(float(match.group(1).replace(",", "")))
        except ValueError:
            pass
    return None


def make_id(prefix: str, url: str) -> str:
    return f"{prefix}-{hashlib.md5(url.encode()).hexdigest()[:10]}"


# ── eBay RSS Scraper ────────────────────────────────────────────────────────
async def fetch_ebay_rss(client: httpx.AsyncClient, query: str) -> list[dict]:
    url = (
        f"https://www.ebay.com/sch/i.html"
        f"?_nkw={query.replace(' ', '+')}"
        f"&_stpos=01119&_sadis=25&LH_BIN=1&_rss=1&_sacat=0"
    )
    results = []
    try:
        r = await client.get(url, headers=FEED_HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return []
        feed = feedparser.parse(r.text)
        for entry in feed.entries[:30]:
            title   = (entry.get("title") or "").strip()
            link    = entry.get("link", "")
            summary = entry.get("summary") or entry.get("description") or ""

            price = extract_price(title) or extract_price(summary)
            if not title or not link:
                continue
            if price and (price < 5 or price > 4000):
                continue

            cat   = detect_category(title)
            cond  = detect_condition(title + " " + summary)
            fault = detect_fault(title + " " + summary)

            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
            image = img_match.group(1) if img_match else CATEGORY_IMAGES.get(cat, CATEGORY_IMAGES["other"])

            results.append({
                "id":          make_id("eb", link),
                "title":       title,
                "price":       price,
                "condition":   cond,
                "category":    cat,
                "source":      "ebay",
                "sourceLabel": "eBay",
                "sourceColor": "#e53238",
                "image":       image,
                "url":         link,
                "fault":       fault,
                "city":        "Ships to 01119",
                "hot":         bool(price and price < 300 and cond == "working"),
            })
    except Exception as e:
        log.warning("eBay RSS '%s' failed: %s", query, e)
    return results


# ── Craigslist HTML Scraper (متعدد المدن) ─────────────────────────────────
async def fetch_craigslist(client: httpx.AsyncClient, city: str, cat: str, query: str) -> list[dict]:
    url = (
        f"https://{city}.craigslist.org/search/{cat}"
        f"?query={query.replace(' ', '+')}&postal=01119&search_distance=50"
    )
    results = []
    try:
        r = await client.get(url, headers=BROWSER_HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "lxml")
        items = (
            soup.select("li.cl-search-result")
            or soup.select("li.result-row")
            or soup.select("li.cl-static-search-result")
        )

        schema_items = []
        schema_tag = soup.select_one("script#ld_searchpage_results")
        if schema_tag and schema_tag.string:
            try:
                schema_items = json.loads(schema_tag.string).get("itemListElement", [])
            except Exception:
                schema_items = []

        for idx, item in enumerate(items[:50]):
            schema_item = schema_items[idx].get("item", {}) if idx < len(schema_items) else {}

            title_el = (
                item.select_one("a.cl-app-anchor span[data-testid='listing-title']")
                or item.select_one("a.result-title")
                or item.select_one(".title")
            )
            title = title_el.get_text(strip=True) if title_el else schema_item.get("name", "")

            link_el = item.select_one("a.cl-app-anchor") or item.select_one("a.result-title") or item.select_one("a[href]")
            link = link_el.get("href", "") if link_el else ""
            if link:
                link = urljoin(str(r.url), link)

            price_el = item.select_one("span.priceinfo") or item.select_one("span.result-price") or item.select_one(".price")
            price_text = price_el.get_text(strip=True) if price_el else ""
            schema_price = schema_item.get("offers", {}).get("price")
            # السعر الصريح فقط — لا fallback من العنوان
            price = extract_price(price_text)
            if not price and schema_price:
                try:
                    price = int(float(schema_price))
                except (TypeError, ValueError):
                    price = None

            img_el = item.select_one("img")
            image = img_el.get("src") or img_el.get("data-src") if img_el else None
            schema_images = schema_item.get("image") or []
            if isinstance(schema_images, str):
                schema_images = [schema_images]
            if (not image or "placeholder" in (image or "")) and schema_images:
                image = schema_images[0]
            if not image or "placeholder" in (image or ""):
                image = CATEGORY_IMAGES.get(detect_category(title), CATEGORY_IMAGES["other"])

            if not title or not link:
                continue
            if price and (price < 5 or price > 4000):
                continue

            cat_ = detect_category(title)
            cond = detect_condition(title)
            fault = detect_fault(title)
            address = schema_item.get("offers", {}).get("availableAtOrFrom", {}).get("address", {})
            city_name = address.get("addressLocality") or city.title()

            results.append({
                "id":          make_id("cl", link),
                "title":       title,
                "price":       price,
                "condition":   cond,
                "category":    cat_,
                "source":      "craigslist",
                "sourceLabel": "Craigslist",
                "sourceColor": "#c41230",
                "image":       image,
                "url":         link,
                "fault":       fault,
                "city":        f"{city_name}, {('MA' if city in ('springfield','westernmass','boston') else 'CT' if city=='hartford' else 'RI')}",
                "hot":         bool(price and price < 250 and cond == "working"),
            })
    except Exception as e:
        log.warning("Craigslist '%s/%s/%s' failed: %s", city, cat, query, e)
    return results


# ── Master Scraper ──────────────────────────────────────────────────────────
async def run_full_scrape() -> dict:
    """يجلب كل شيء من جميع المصادر، يخزّن في DB، يرجع stats."""
    started = asyncio.get_event_loop().time()
    log.info("Starting full scrape …")

    all_items: list[dict] = []
    sem = asyncio.Semaphore(6)  # cap concurrency to be polite

    async def bounded(coro):
        async with sem:
            return await coro

    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT, connect=5.0)) as client:
        tasks = []
        # eBay
        for q in EBAY_QUERIES:
            tasks.append(bounded(fetch_ebay_rss(client, q)))
        # Craigslist × كل مدينة
        for city in CRAIGSLIST_CITIES:
            for cat, query in CRAIGSLIST_QUERIES:
                tasks.append(bounded(fetch_craigslist(client, city, cat, query)))

        batches = await asyncio.gather(*tasks, return_exceptions=True)
        for batch in batches:
            if isinstance(batch, Exception):
                continue
            all_items.extend(batch)

    # dedup by id (نفس الرابط من نفس المصدر)
    seen = {}
    for it in all_items:
        seen[it["id"]] = it
    unique = list(seen.values())

    added, updated = upsert_many(unique)
    deleted = cleanup_old(max_age_days=7, max_total=1000)
    elapsed = asyncio.get_event_loop().time() - started
    total = count_listings()
    log.info(
        "Scrape done in %.1fs: fetched=%d unique=%d added=%d updated=%d deleted=%d total=%d",
        elapsed, len(all_items), len(unique), added, updated, deleted, total,
    )
    return {
        "fetched":  len(all_items),
        "unique":   len(unique),
        "added":    added,
        "updated":  updated,
        "deleted":  deleted,
        "total":    total,
        "elapsed":  round(elapsed, 2),
    }


# ── Background Loop ─────────────────────────────────────────────────────────
_scrape_task: asyncio.Task | None = None
_last_scrape_result: dict | None = None
_scrape_lock = asyncio.Lock()


async def scrape_loop():
    global _last_scrape_result
    if SCRAPE_ON_STARTUP:
        try:
            async with _scrape_lock:
                _last_scrape_result = await run_full_scrape()
        except Exception as e:
            log.exception("Initial scrape failed: %s", e)

    while True:
        await asyncio.sleep(SCRAPE_INTERVAL)
        try:
            async with _scrape_lock:
                _last_scrape_result = await run_full_scrape()
        except Exception as e:
            log.exception("Scheduled scrape failed: %s", e)


@app.on_event("startup")
async def _startup():
    init_db()
    global _scrape_task
    _scrape_task = asyncio.create_task(scrape_loop())
    log.info("MobeFace startup complete — scrape every %ds, %d listings in DB",
             SCRAPE_INTERVAL, count_listings())


@app.on_event("shutdown")
async def _shutdown():
    if _scrape_task:
        _scrape_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _scrape_task


# ── API Endpoints ───────────────────────────────────────────────────────────
@app.get("/api/listings")
async def get_listings(
    q:         str = Query(default=""),
    category:  str = Query(default="all"),
    condition: str = Query(default="all"),
    source:    str = Query(default="all"),
    limit:     int = Query(default=500, ge=1, le=2000),
):
    listings = query_listings(
        q=q.strip(), category=category, condition=condition, source=source, limit=limit,
    )
    s = stats()
    return {
        "total":       len(listings),
        "listings":    listings,
        "sources":     ["ebay", "craigslist"],
        "fetched_at":  datetime.now(timezone.utc).isoformat(),
        "db_total":    s["total"],
        "last_scrape": (
            datetime.fromtimestamp(s["last_scrape"], tz=timezone.utc).isoformat()
            if s["last_scrape"] else None
        ),
    }


@app.get("/api/stats")
async def get_stats():
    s = stats()
    return {
        **s,
        "last_scrape_iso": (
            datetime.fromtimestamp(s["last_scrape"], tz=timezone.utc).isoformat()
            if s["last_scrape"] else None
        ),
        "last_run": _last_scrape_result,
        "scrape_interval_sec": SCRAPE_INTERVAL,
    }


@app.post("/api/refresh")
async def trigger_refresh():
    """يطلق scrape فوري (يستخدمه زر Refresh في الواجهة)."""
    if _scrape_lock.locked():
        return {"status": "already_running"}
    async with _scrape_lock:
        result = await run_full_scrape()
    return {"status": "ok", **result}


@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "MobeFace API running", "db_total": count_listings()}


@app.get("/")
async def root():
    return {"name": "MobeFace API", "version": "2.0.0", "docs": "/docs"}
