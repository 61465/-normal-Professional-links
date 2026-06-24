// ── خدمة جلب البيانات الحقيقية من الـ Backend ───────────────────────────────
// In development Vite proxies /api to the backend. In production, set
// VITE_API_BASE if the API is hosted on another origin.
const API_BASE = import.meta.env.VITE_API_BASE || "";

/** يجلب الإعلانات من الـ DB المحلية في الـ backend (سريع، مفلتر، حتى 500) */
export async function fetchListings({ q = "", category = "all", condition = "all", source = "all", limit = 500 } = {}) {
  const params = new URLSearchParams({ q, category, condition, source, limit });
  const res = await fetch(`${API_BASE}/api/listings?${params}`, {
    signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return {
    listings:    data.listings || [],
    dbTotal:     data.db_total || 0,
    lastScrape:  data.last_scrape,
    fetchedAt:   data.fetched_at,
  };
}

/** يُجبر الـ backend على scrape فوري ويرجع الإحصائيات */
export async function triggerRefresh() {
  const res = await fetch(`${API_BASE}/api/refresh`, {
    method: 'POST',
    signal: AbortSignal.timeout(120000), // scrape كامل قد يأخذ دقيقة
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** فحص إذا كان الـ backend يعمل */
export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`, {
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}
