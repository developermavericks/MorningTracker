import { useState, useEffect, useMemo } from "react";
import { api } from "../services/api";

export default function NewScrape({ onNavigate }) {
  const [options, setOptions] = useState({ sectors: [], regions: [] });
  const [form, setForm] = useState({
    sector: "",
    region: "",
    date_from: "",
    date_to: new Date().toISOString().slice(0, 10),
    search_mode: "broad",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.get(`/scrape/options?t=${Date.now()}`)
      .then(setOptions)
      .catch(() => { });
  }, []);

  const dateWarning = useMemo(() => {
    if (!form.date_from || !form.date_to) return null;
    const days = Math.round((new Date(form.date_to) - new Date(form.date_from)) / 86400000);
    if (days < 0) return "⚠ Start date must be before end date";
    if (days > 30) return `⚠ Range limited to 30 days per job (Current: ${days} days)`;
    return null;
  }, [form.date_from, form.date_to]);

  const handleSubmit = async () => {
    if (!form.sector || !form.region || !form.date_from || !form.date_to) {
      setError("Please define all intelligence parameters.");
      return;
    }
    if (dateWarning) {
      setError(dateWarning);
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.post("/scrape/start", form);
      setResult(data);
    } catch (e) {
      setError("Network or connection variance detected.");
    } finally {
      setLoading(false);
    }
  };

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div>
      <header className="page-header" style={{ marginBottom: '40px' }}>
        <h1 className="page-title">Intelligence Mission</h1>
        <p className="page-subtitle">Configure search parameters and initiate data extraction</p>
      </header>

      {error && <div className="alert alert-error" style={{ marginBottom: '24px' }}>{error}</div>}
      {result && (
        <div className="alert alert-success" style={{ marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div>Mission initiated // <strong>{result.job_id.slice(0, 8)}</strong></div>
          <button className="btn btn-secondary" onClick={() => onNavigate("jobs")} style={{ padding: "4px 12px", fontSize: '11px' }}>
            Track Progress
          </button>
        </div>
      )}

      <div className="card" style={{ marginBottom: 32, boxShadow: 'var(--glow)', border: 'none' }}>
        <div className="card-title" style={{ marginBottom: '24px' }}>Target Parameters</div>

        <div className="form-grid" style={{ marginBottom: '32px' }}>
          <div className="form-group">
            <label className="form-label">Asset Sector</label>
            <select className="form-control" value={form.sector} onChange={(e) => set("sector", e.target.value)}>
              <option value="">— Choose Sector —</option>
              {options.sectors.map((s) => (
                <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Geo Region</label>
            <select className="form-control" value={form.region} onChange={(e) => set("region", e.target.value)}>
              <option value="">— Choose Region —</option>
              {options.regions.map((r) => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Timeline Start</label>
            <input
              type="date"
              className="form-control"
              value={form.date_from}
              max={form.date_to}
              onChange={(e) => set("date_from", e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Timeline End</label>
            <input
              type="date"
              className="form-control"
              value={form.date_to}
              min={form.date_from}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => set("date_to", e.target.value)}
            />
          </div>
        </div>

        <div style={{ background: 'var(--surface2)', padding: '24px', borderRadius: 'var(--radius)', marginBottom: '32px' }}>
          <label className="form-label" style={{ marginBottom: '16px', display: 'block' }}>Search Intensity</label>
          <div style={{ display: "flex", gap: "16px" }}>
            <button
              className="btn btn-secondary"
              style={{ flex: 1, padding: "16px", background: form.search_mode === "broad" ? 'var(--accent)' : 'var(--bg)', color: form.search_mode === "broad" ? 'white' : 'var(--text)', border: 'none' }}
              onClick={() => set("search_mode", "broad")}
            >
              <div style={{ fontWeight: 600 }}>Standard Search</div>
              <div style={{ fontSize: 11, opacity: 0.8 }}>Comprehensive global discovery</div>
            </button>
            <button
              className="btn btn-secondary"
              style={{ flex: 1, padding: "16px", background: form.search_mode === "smart" ? 'var(--accent)' : 'var(--bg)', color: form.search_mode === "smart" ? 'white' : 'var(--text)', border: 'none' }}
              onClick={() => set("search_mode", "smart")}
            >
              <div style={{ fontWeight: 600 }}>✨ AI Precision</div>
              <div style={{ fontSize: 11, opacity: 0.8 }}>Intelligent relevance filtering</div>
            </button>
          </div>
        </div>

        <button className="btn btn-primary" onClick={handleSubmit} disabled={loading || !!dateWarning} style={{ height: '48px', fontSize: '15px', justifyContent: 'center' }}>
          {loading ? <><div className="spinner" /> Initializing...</> : "Launch Extraction Mission"}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px' }}>
         <div className="card" style={{ border: 'none', background: 'var(--surface2)' }}>
            <div style={{ color: 'var(--accent)', fontSize: '20px', marginBottom: '12px' }}>01. Discovery</div>
            <p style={{ fontSize: '13px', color: 'var(--muted)', lineHeight: '1.6' }}>
               Synchronizing with global data streams (Google & Bing News) to identify intelligence nodes.
            </p>
         </div>
         <div className="card" style={{ border: 'none', background: 'var(--surface2)' }}>
            <div style={{ color: 'var(--accent)', fontSize: '20px', marginBottom: '12px' }}>02. Extraction</div>
            <p style={{ fontSize: '13px', color: 'var(--muted)', lineHeight: '1.6' }}>
               Autonomous browsing agents render and extract core insights while bypassing defensive paywalls.
            </p>
         </div>
         <div className="card" style={{ border: 'none', background: 'var(--surface2)' }}>
            <div style={{ color: 'var(--accent)', fontSize: '20px', marginBottom: '12px' }}>03. Analysis</div>
            <p style={{ fontSize: '13px', color: 'var(--muted)', lineHeight: '1.6' }}>
               AI processing layer performs deduplication, classification, and executive summarization.
            </p>
         </div>
      </div>
    </div>
  );
}
