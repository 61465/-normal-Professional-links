import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { fetchListings, checkHealth, triggerRefresh } from './services/api';
import { analyzeDeal } from './services/aiAnalyzer';
import { SEARCH_PORTALS } from './data/portals';
import DealCard from './components/DealCard';
import PortalCard from './components/PortalCard';
import Header from './components/Header';
import FilterBar from './components/FilterBar';
import AIModal from './components/AIModal';
import ViewerModal from './components/ViewerModal';
import './index.css';

const CATEGORIES = [
  { id: 'all', label: '🔍 الكل' },
  { id: 'phone', label: '📱 هواتف' },
  { id: 'gaming', label: '🎮 ألعاب' },
  { id: 'tablet', label: '📟 لوحية' },
  { id: 'laptop', label: '💻 لابتوب' },
  { id: 'accessories', label: '🎧 إكسسوار' },
];

const CONDITIONS = [
  { id: 'all', label: 'الكل' },
  { id: 'working', label: '✅ سليم' },
  { id: 'parts', label: '🔧 للقطع' },
];

const SOURCES = [
  { id: 'all', label: 'الكل' },
  { id: 'craigslist', label: 'Craigslist' },
  { id: 'ebay', label: 'eBay' },
  { id: 'facebook', label: 'Facebook' },
  { id: 'offerup', label: 'OfferUp' },
];

const PROTECTED_SOURCES = ['facebook', 'offerup'];

export default function App() {
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [category, setCategory] = useState('all');
  const [condition, setCondition] = useState('all');
  const [source, setSource] = useState('all');
  const [sortBy, setSortBy] = useState('hot');

  const [aiTarget, setAiTarget] = useState(null);
  const [viewUrl, setViewUrl] = useState(null);
  const [dbTotal, setDbTotal] = useState(0);
  const [lastScrape, setLastScrape] = useState(null);
  const [newCount, setNewCount] = useState(0);
  const [scraping, setScraping] = useState(false);
  const knownIdsRef = useRef(new Set());

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 500);
    return () => window.clearTimeout(timer);
  }, [search]);

  const loadListings = useCallback(async ({ silent = false } = {}) => {
    if (PROTECTED_SOURCES.includes(source)) {
      setListings([]);
      setError(null);
      setLoading(false);
      return;
    }

    if (!silent) setLoading(true);
    setError(null);
    try {
      const healthy = await checkHealth();
      if (!healthy) {
        if (!silent) setListings([]);
        setError('backend_down');
        return;
      }

      const data = await fetchListings({
        q: debouncedSearch,
        category,
        condition,
        source,
      });

      // كشف الجديد منذ آخر تحميل
      if (knownIdsRef.current.size > 0) {
        const newcomers = data.listings.filter(l => !knownIdsRef.current.has(l.id));
        if (newcomers.length > 0 && silent) {
          setNewCount(prev => prev + newcomers.length);
        }
      }
      knownIdsRef.current = new Set(data.listings.map(l => l.id));

      setListings(data.listings);
      setDbTotal(data.dbTotal);
      setLastScrape(data.lastScrape);
    } catch (e) {
      setError('fetch_error');
      if (!silent) setListings([]);
      console.error(e);
    } finally {
      if (!silent) setLoading(false);
    }
  }, [debouncedSearch, category, condition, source, refreshKey]);

  useEffect(() => { loadListings(); }, [loadListings]);

  // 🔄 Auto-refresh كل 60 ثانية (silent — لا يكسر الـ UI)
  useEffect(() => {
    const id = window.setInterval(() => loadListings({ silent: true }), 60000);
    return () => window.clearInterval(id);
  }, [loadListings]);

  // 🚀 Force backend scrape
  const handleForceRefresh = useCallback(async () => {
    setScraping(true);
    try {
      await triggerRefresh();
      setNewCount(0);
      await loadListings();
    } catch (e) {
      console.error('refresh failed', e);
    } finally {
      setScraping(false);
    }
  }, [loadListings]);

  // عرض الإعلانات الجديدة (يصفّر العداد)
  const handleShowNew = useCallback(() => {
    setNewCount(0);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const sortedListings = useMemo(() => {
    const list = [...listings];
    switch (sortBy) {
      case 'hot':
        list.sort((a, b) => {
          // hot أولاً، ثم الأرخص داخل كل مجموعة
          const h = Number(b.hot) - Number(a.hot);
          if (h !== 0) return h;
          return (a.price ?? Infinity) - (b.price ?? Infinity);
        });
        break;
      case 'price_asc':
        // الأرخص أولاً، عناصر بدون سعر في النهاية
        list.sort((a, b) => {
          const ap = a.price ?? Infinity;
          const bp = b.price ?? Infinity;
          return ap - bp;
        });
        break;
      case 'price_desc':
        // الأغلى أولاً، عناصر بدون سعر في النهاية
        list.sort((a, b) => {
          const ap = a.price ?? -Infinity;
          const bp = b.price ?? -Infinity;
          if (a.price == null && b.price != null) return 1;
          if (b.price == null && a.price != null) return -1;
          return bp - ap;
        });
        break;
      case 'newest':
        // إعلانات Craigslist بدون timestamp دقيق؛ نضع الـ id كـ proxy عشوائي
        list.sort((a, b) => (b.id || '').localeCompare(a.id || ''));
        break;
      default:
        break;
    }
    return list;
  }, [listings, sortBy]);

  const filteredPortals = useMemo(() => {
    if (source !== 'all' && source !== 'facebook' && source !== 'offerup') return [];
    if (category === 'all') return SEARCH_PORTALS;
    return SEARCH_PORTALS.filter(p => p.category === category);
  }, [source, category]);

  const stats = useMemo(() => {
    const priced = listings.filter(l => l.price);
    return {
      total: listings.length,
      hot: listings.filter(l => l.hot).length,
      parts: listings.filter(l => l.condition === 'parts').length,
      avgPrice: priced.length ? Math.round(priced.reduce((s, l) => s + l.price, 0) / priced.length) : 0,
    };
  }, [listings]);

  const handleAI = (listing) => setAiTarget({ listing, analysis: analyzeDeal(listing) });
  const handleUrl = (url, label) => setViewUrl({ url, label });
  const refreshListings = () => setRefreshKey(k => k + 1);

  const lastScrapeText = useMemo(() => {
    if (!lastScrape) return null;
    const delta = Math.floor((Date.now() - new Date(lastScrape).getTime()) / 1000);
    if (delta < 60) return 'الآن';
    if (delta < 3600) return `قبل ${Math.floor(delta / 60)} د`;
    return `قبل ${Math.floor(delta / 3600)} س`;
  }, [lastScrape]);

  if (loading) return (
    <>
      <Header search={search} onSearch={setSearch} {...stats} />
      <FilterBar categories={CATEGORIES} conditions={CONDITIONS} sources={SOURCES}
        category={category} condition={condition} source={source} sortBy={sortBy}
        onCategory={setCategory} onCondition={setCondition} onSource={setSource} onSort={setSortBy} />
      <main className="feed">
        <div className="loading-banner">
          <div className="loading-spinner" />
          <span>جاري جلب الإعلانات الحقيقية من Craigslist وeBay...</span>
        </div>
        <div className="feed-grid">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="skeleton-card">
              <div className="skeleton skeleton-img" />
              <div className="skeleton-body">
                <div className="skeleton skeleton-line w-80" />
                <div className="skeleton skeleton-line w-60" />
                <div className="skeleton skeleton-line w-40" />
              </div>
            </div>
          ))}
        </div>
      </main>
    </>
  );

  if ((error === 'backend_down' || error === 'fetch_error') && listings.length === 0) return (
    <>
      <Header search={search} onSearch={setSearch} {...stats} />
      <main className="feed">
        <div className="error-banner">
          <div className="error-icon">⚠️</div>
          <div>
            <h3>الـ Backend غير مشغّل</h3>
            <p>شغّل الخادم بالأمر التالي في مجلد <code>backend/</code> ثم أعد تحميل الصفحة:</p>
            <pre className="error-cmd">uvicorn main:app --reload --port 8001</pre>
          </div>
          <button className="btn btn-primary" onClick={refreshListings} style={{ marginTop: 8 }}>
            🔄 إعادة المحاولة
          </button>
        </div>
      </main>
    </>
  );

  return (
    <>
      <Header search={search} onSearch={setSearch}
        hotCount={stats.hot} partsCount={stats.parts}
        avgPrice={stats.avgPrice} totalCount={stats.total} />

      <FilterBar categories={CATEGORIES} conditions={CONDITIONS} sources={SOURCES}
        category={category} condition={condition} source={source} sortBy={sortBy}
        onCategory={setCategory} onCondition={setCondition} onSource={setSource} onSort={setSortBy} />

      <main className="feed">
        {(source === 'all' || source === 'craigslist' || source === 'ebay') && (
          <section>
            <div className="feed-header">
              <h2 className="section-title">📡 إعلانات مباشرة</h2>
              <div className="feed-meta">
                <span className="feed-count">
                  <strong>{sortedListings.length}</strong> من <strong>{dbTotal}</strong>
                </span>
                {lastScrapeText && (
                  <span className="last-scrape">🕒 آخر جمع: {lastScrapeText}</span>
                )}
                <button
                  className="btn-refresh"
                  onClick={handleForceRefresh}
                  disabled={scraping}
                  title={scraping ? 'جاري الجمع…' : 'جلب جديد الآن'}
                >
                  {scraping ? '⏳' : '🔄'}
                </button>
              </div>
            </div>

            {newCount > 0 && (
              <button className="new-deals-banner" onClick={handleShowNew}>
                ✨ {newCount} عرض جديد — اضغط للعرض
              </button>
            )}

            {sortedListings.length === 0 ? (
              <div className="empty-state">
                <div className="icon">🔍</div>
                <h3>لا توجد نتائج حقيقية حالياً</h3>
                <p>جرب كلمة بحث مختلفة أو غيّر المصدر/التصنيف</p>
              </div>
            ) : (
              <div className="feed-grid">
                {sortedListings.map(listing => (
                  <DealCard
                    key={listing.id}
                    listing={listing}
                    onAIAnalyze={() => handleAI(listing)}
                    onOpenUrl={() => handleUrl(listing.url, listing.title)}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {filteredPortals.length > 0 && (source === 'all' || source === 'facebook' || source === 'offerup') && (
          <section style={{ marginTop: 32 }}>
            <div className="feed-header">
              <h2 className="section-title">🔒 منصات محمية — روابط بحث مباشرة</h2>
              <span className="feed-badge-note">هذه المنصات لا تسمح بسحب البيانات، لذلك لا نعرض منها إعلانات وهمية</span>
            </div>
            <div className="portal-grid">
              {filteredPortals.map(p => <PortalCard key={p.id} portal={p} />)}
            </div>
          </section>
        )}
      </main>

      {aiTarget && (
        <AIModal
          listing={aiTarget.listing}
          analysis={aiTarget.analysis}
          onClose={() => setAiTarget(null)}
          onOpenUrl={() => handleUrl(aiTarget.listing.url, aiTarget.listing.title)}
        />
      )}
      {viewUrl && (
        <ViewerModal
          url={viewUrl.url}
          label={viewUrl.label}
          onClose={() => setViewUrl(null)}
        />
      )}
    </>
  );
}
