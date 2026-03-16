import { useState, useEffect, useCallback } from "react";
import useStore from "../store/useStore";
import { api } from "../services/api";

function ArticleModal({ article, onClose, onDelete }) {
  if (!article) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ boxShadow: 'var(--glow)' }}>
        <div className="modal-title" style={{ color: 'var(--accent)', fontSize: '24px' }}>{article.title || "Untitled"}</div>
        <div className="modal-meta" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="meta-item">Agency: <span>{article.agency || "N/A"}</span></div>
          <div className="meta-item">Published: <span>{article.published_at ? new Date(article.published_at).toLocaleDateString() : "—"}</span></div>
          <div className="meta-item">
            <span className="badge badge-sector">{article.sector}</span>
          </div>
        </div>
        
        <div style={{ marginTop: '24px' }}>
          <a href={article.url} target="_blank" rel="noopener noreferrer" className="btn btn-secondary" style={{ textDecoration: 'none', fontSize: '12px' }}>
            ↗ View Original Source
          </a>
        </div>

        <div className="article-body" style={{ marginTop: '32px', background: 'var(--surface2)', padding: '24px', borderRadius: 'var(--radius)' }}>
          {article.summary ? (
             <div style={{ marginBottom: '24px', borderLeft: '4px solid var(--accent)', paddingLeft: '16px' }}>
                <strong style={{ display: 'block', marginBottom: '8px', fontSize: '11px', textTransform: 'uppercase', color: 'var(--accent)' }}>AI Summary</strong>
                <p style={{ fontSize: '15px', color: 'var(--text)' }}>{article.summary}</p>
             </div>
          ) : null}
          {article.full_body ? (
               <>
                <strong style={{ display: 'block', marginBottom: '8px', fontSize: '11px', textTransform: 'uppercase', color: 'var(--muted)' }}>Content</strong>
                <div style={{ fontStyle: 'normal' }}>{article.full_body}</div>
               </>
          ) : (
            <div style={{ color: "var(--muted)", fontStyle: "italic" }}>Full content processing failed or unavailable.</div>
          )}
        </div>

        <div style={{ marginTop: 32, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <button 
            className="btn btn-secondary" 
            style={{ color: '#ff4444', borderColor: '#ff4444' }}
            onClick={() => onDelete(article.id)}
          >
            Delete Article
          </button>
          <button className="btn btn-primary" onClick={onClose}>Done Reading</button>
        </div>
      </div>
    </div>
  );
}

export default function ArticlesBrowser() {
  const { articles, totalArticles, loading, fetchArticles, deleteArticle, deleteBulkArticles } = useStore();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({
    sector: "",
    region: "",
    search: "",
  });

  const load = useCallback((pg = 1) => {
    fetchArticles({ page: pg, ...filters });
    setPage(pg);
  }, [filters, fetchArticles]);

  useEffect(() => { load(1); }, [load]);

  const openArticle = async (id) => {
    try {
      const full = await api.get(`/articles/${id}`);
      setSelected(full);
    } catch { }
  };

  const handleDelete = async (id, e) => {
    if (e) e.stopPropagation();
    if (window.confirm("Are you sure you want to permanently delete this article?")) {
      const success = await deleteArticle(id);
      if (success && selected?.id === id) {
        setSelected(null);
      }
    }
  };

  const handleBulkDelete = async () => {
    if (window.confirm("Are you sure you want to permanently delete ALL articles matching this search criteria?")) {
      const success = await deleteBulkArticles(filters);
      if (success) {
        setSelected(null);
        load(1);
      }
    }
  };

  const totalPages = Math.ceil(totalArticles / 25) || 1;

  return (
    <div>
      {selected && <ArticleModal article={selected} onClose={() => setSelected(null)} onDelete={handleDelete} />}

      <header className="page-header" style={{ marginBottom: '40px' }}>
        <h1 className="page-title">Intelligence Hub</h1>
        <p className="page-subtitle">Exploration & Discovery // {totalArticles.toLocaleString()} Articles Tracked</p>
      </header>

      <div className="card" style={{ marginBottom: '32px', border: 'none', background: 'var(--surface2)' }}>
        <div className="filter-bar" style={{ gap: '16px' }}>
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label">Search Query</label>
            <input
              type="text"
              className="form-control"
              placeholder="Keywords, companies, or topics..."
              value={filters.search}
              onChange={(e) => setFilters(f => ({ ...f, search: e.target.value }))}
              onKeyDown={(e) => e.key === "Enter" && load(1)}
            />
          </div>
          <button className="btn btn-primary" onClick={() => load(1)} style={{ padding: '10px 32px' }}>
            Filter Results
          </button>
          <button 
            className="btn btn-secondary" 
            onClick={handleBulkDelete} 
            style={{ padding: '10px 32px', color: '#ff4444', borderColor: '#ff4444', background: 'transparent' }}
          >
            Delete All Filtered
          </button>
        </div>
      </div>

      <div className="table-wrap" style={{ boxShadow: 'var(--glow)', border: 'none' }}>
        <table>
          <thead>
            <tr>
              <th>Intelligence Report</th>
              <th>Publisher</th>
              <th>Timeline</th>
              <th>Classification</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} style={{ textAlign: "center", padding: 60 }}>
                <div className="spinner" style={{ width: '32px', height: '32px' }} />
              </td></tr>
            ) : articles.length === 0 ? (
              <tr><td colSpan={5}>
                <div className="empty-state">
                  <div className="empty-state-icon">✦</div>
                  <h3>No findings match your criteria</h3>
                  <p>Try refining your search or launching a new tracking mission.</p>
                </div>
              </td></tr>
            ) : articles.map((a) => (
              <tr key={a.id} style={{ cursor: "pointer" }} onClick={() => openArticle(a.id)}>
                <td style={{ maxWidth: 400 }}>
                  <div style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text)', marginBottom: '4px' }}>{a.title}</div>
                  <div style={{ fontSize: '12px', color: 'var(--muted)' }}>{a.author || "Global Desk"}</div>
                </td>
                <td style={{ fontSize: '13px' }}>{a.agency || "Unknown Source"}</td>
                <td style={{ fontSize: '13px' }}>
                  {a.published_at ? new Date(a.published_at).toLocaleDateString() : "—"}
                </td>
                <td><span className="badge badge-sector">{a.sector}</span></td>
                <td style={{ textAlign: 'right' }}>
                   <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', alignItems: 'center' }}>
                     <button 
                        className="btn btn-secondary" 
                        style={{ padding: '6px 16px', fontSize: '11px', color: '#ff4444', borderColor: '#ff4444', background: 'transparent' }}
                        onClick={(e) => handleDelete(a.id, e)}
                     >
                       Delete
                     </button>
                     <div className="btn btn-secondary" style={{ padding: '6px 16px', fontSize: '11px' }}>Deep Dive</div>
                   </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button className="btn btn-secondary" disabled={page <= 1} onClick={() => load(page - 1)}>
            Previous
          </button>
          <span style={{ fontSize: 13, color: "var(--muted)", fontWeight: '500' }}>
            {page} / {totalPages}
          </span>
          <button className="btn btn-secondary" disabled={page >= totalPages} onClick={() => load(page + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
