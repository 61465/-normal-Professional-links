export default function FilterBar({
  categories, conditions, sources,
  category, condition, source, sortBy,
  onCategory, onCondition, onSource, onSort,
}) {
  return (
    <nav className="filter-bar" aria-label="فلاتر البحث">
      <div className="filter-bar-inner">

        {/* Category */}
        <div className="filter-section">
          <div className="filter-chips">
            {categories.map(c => (
              <button
                key={c.id}
                id={`cat-${c.id}`}
                className={`chip ${category === c.id ? 'active' : ''}`}
                onClick={() => onCategory(c.id)}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="divider-v" />

        {/* Condition */}
        <div className="filter-section">
          <span className="filter-label">الحالة:</span>
          <div className="filter-chips">
            {conditions.map(c => (
              <button
                key={c.id}
                id={`cond-${c.id}`}
                className={`chip ${condition === c.id ? 'active' : ''}`}
                onClick={() => onCondition(c.id)}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>

        <div className="divider-v" />

        {/* Source */}
        <div className="filter-section">
          <span className="filter-label">المصدر:</span>
          <div className="filter-chips">
            {sources.map(s => (
              <button
                key={s.id}
                id={`src-${s.id}`}
                className={`chip ${source === s.id ? 'active' : ''}`}
                onClick={() => onSource(s.id)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        <div className="divider-v" />

        {/* Sort */}
        <div className="filter-section">
          <span className="filter-label">ترتيب:</span>
          <select
            id="sort-select"
            className={`sort-select ${sortBy !== 'hot' ? 'active' : ''}`}
            value={sortBy}
            onChange={e => onSort(e.target.value)}
          >
            <option value="hot">🔥 الأكثر رواجاً</option>
            <option value="newest">🕒 الأحدث</option>
            <option value="price_asc">💰 الأرخص أولاً</option>
            <option value="price_desc">💎 الأغلى أولاً</option>
          </select>
        </div>

      </div>
    </nav>
  );
}
