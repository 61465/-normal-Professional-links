import { useMemo } from 'react';
import { analyzeDeal } from '../services/aiAnalyzer';

// ── Color helpers ─────────────────────────────────────────────────────────
function scoreColor(score) {
  if (score >= 75) return '#22c55e';
  if (score >= 55) return '#facc15';
  if (score >= 35) return '#fb923c';
  return '#ef4444';
}

export default function DealCard({ listing, onAIAnalyze, onOpenUrl }) {
  // Quick AI score (lightweight — just for badge on card)
  const quickScore = useMemo(() => analyzeDeal(listing).score, [listing]);
  const scoreClr   = scoreColor(quickScore);

  return (
    <article
      id={`deal-${listing.id}`}
      className={`deal-card ${listing.hot ? 'hot-deal' : ''}`}
      aria-label={listing.title}
    >
      {/* Hot / New badges */}
      {listing.isNew && <div className="new-badge">✨ جديد</div>}
      {listing.hot && !listing.isNew && <div className="hot-badge">🔥 Hot</div>}

      {/* AI Score badge */}
      <div
        className="ai-score-badge"
        style={{ background: `${scoreClr}22`, color: scoreClr, borderColor: `${scoreClr}44` }}
        title={`درجة الصفقة: ${quickScore}/100`}
      >
        {quickScore}
      </div>

      {/* Image */}
      <div className="image-wrapper">
        <img
          className="card-image"
          src={listing.image}
          alt={listing.title}
          loading="lazy"
          onError={e => { e.target.src = 'https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?w=400&q=60'; }}
        />
        {/* Source badge */}
        <span
          className="source-badge"
          style={{ background: listing.sourceColor + 'cc' }}
        >
          {listing.sourceLabel}
        </span>
      </div>

      {/* Body */}
      <div className="card-body">
        {/* Meta row */}
        <div className="card-meta">
          <span className={`condition-badge ${listing.condition}`}>
            {listing.condition === 'working' ? '✅ سليم' : '🔧 للقطع'}
          </span>
          <span className="posted-time">🕒 {listing.postedAgo}</span>
        </div>

        {/* Title */}
        <h3 className="card-title">{listing.title}</h3>

        {/* Fault */}
        {listing.fault && (
          <div className="fault-tag">
            ⚠️ {listing.fault}
          </div>
        )}

        {/* Location */}
        <div className="card-location">
          📍 {listing.city}
        </div>
      </div>

      {/* Footer */}
      <div className="card-footer">
        <div className="card-price">
          {listing.price ? <><small>$</small>{listing.price}</> : <span className="price-unknown">غير محدد</span>}
        </div>
        <div className="card-actions">
          {/* AI Analysis */}
          <button
            id={`ai-btn-${listing.id}`}
            className="btn btn-ghost btn-icon"
            onClick={onAIAnalyze}
            title="تحليل ذكي للصفقة"
            aria-label="تحليل AI"
          >
            🤖
          </button>

          {/* Open listing */}
          <button
            id={`open-btn-${listing.id}`}
            className="btn btn-primary"
            onClick={onOpenUrl}
            aria-label="فتح الإعلان"
          >
            فتح ↗
          </button>
        </div>
      </div>
    </article>
  );
}

