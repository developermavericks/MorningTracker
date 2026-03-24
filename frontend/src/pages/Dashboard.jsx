import { useEffect, useState } from "react";
import useStore from "../store/useStore";
import { api } from "../services/api";

export default function Dashboard({ onNavigate }) {
  const { stats, fetchStats, jobs, fetchJobs } = useStore();
  // const [enriching, setEnriching] = useState(false);
  // const [enrichMsg, setEnrichMsg] = useState(null);

  useEffect(() => {
    fetchStats();
    fetchJobs();
    const interval = setInterval(() => {
      fetchStats();
      fetchJobs();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const activeJobs = Array.isArray(jobs) ? jobs.filter(j => j.status === 'running' || j.status === 'pending') : [];
  const maxSector = stats?.by_sector?.[0]?.count || 1;
  const maxRegion = stats?.by_region?.[0]?.count || 1;

  /*
  const handleEnrich = async () => {
    setEnriching(true);
    setEnrichMsg(null);
    try {
      const data = await api.post("/scrape/enrich");
      setEnrichMsg(`✓ ${data.status}: ${data.count} articles enqueued.`);
      fetchStats();
    } catch (e) {
      setEnrichMsg(`⚠ Connection failed: ${e.message}`);
    } finally {
      setEnriching(false);
    }
  };
  */

  const loading = !stats;

  return (
    <div>
      <header className="page-header" style={{ marginBottom: '40px' }}>
        <h1 className="page-title">Intelligence Overview</h1>
        <p className="page-subtitle">NEXUS GLOBAL — Strategic Command Center</p>
      </header>

      <div className="stats-grid" style={{ marginBottom: 32 }}>
        <div className="stat-card" style={{ boxShadow: 'var(--glow)' }}>
          <div className="stat-label">Total Insights</div>
          <div className="stat-value">{loading ? "—" : (stats?.total_articles ?? 0).toLocaleString()}</div>
          <div className="stat-sub">Validated articles</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Data Integrity</div>
          <div className="stat-value" style={{ color: 'var(--accent)' }}>
            {loading ? "—" : `${stats?.body_coverage_pct ?? 0}%`}
          </div>
          <div className="stat-sub">Content coverage</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Asset Classes</div>
          <div className="stat-value">{loading ? "—" : stats?.by_sector?.length ?? 0}</div>
          <div className="stat-sub">Sectors monitored</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">System Health</div>
          <div className="stat-value" style={{ fontSize: 18, paddingTop: 8, color: 'var(--success)' }}>
            OPERATIONAL
          </div>
          <div className="stat-sub">All nodes active</div>
        </div>
      </div>

      {activeJobs.length > 0 && (
        <div className="card" style={{ marginBottom: 32, borderLeft: '4px solid var(--accent)', background: 'rgba(30, 58, 95, 0.2)' }}>
          <div className="card-title" style={{ fontSize: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
            <div className="spinner" style={{ width: 14, height: 14 }} /> 
            LIVE OPERATIONS — {activeJobs.length} Mission(s) In-Progress
          </div>
          <div style={{ marginTop: 20 }}>
            {activeJobs.map(job => {
              const pct = job.total_found > 0 ? Math.round((job.total_scraped / job.total_found) * 100) : 0;
              return (
                <div key={job.id} style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontSize: 12 }}>
                    <span>{job.id.slice(0,8)} // <strong>{job.sector.toUpperCase()}</strong> ({job.region})</span>
                    <span>{job.current_phase} — {pct}%</span>
                  </div>
                  <div className="progress-bar-track" style={{ height: 6 }}>
                    <div className="progress-bar-fill progress-pulse" style={{ width: `${Math.max(pct, 5)}%`, background: 'var(--accent)' }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, marginBottom: 32 }}>
        <div className="card">
          <div className="card-title" style={{ marginBottom: '24px' }}>Distribution by Sector</div>
          {loading ? <div className="spinner" /> : (
            <div className="bar-chart">
              {stats?.by_sector?.slice(0, 8).map((s) => (
                <div className="bar-row" key={s.sector}>
                  <div className="bar-label" style={{ width: '120px' }}>{s.sector}</div>
                  <div className="bar-outer" style={{ background: 'var(--bg)' }}>
                    <div className="bar-inner" style={{ width: `${(s.count / maxSector) * 100}%`, background: 'var(--accent)' }} />
                  </div>
                  <div className="bar-count" style={{ width: '60px' }}>{s.count.toLocaleString()}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title" style={{ marginBottom: '24px' }}>Task Distribution</div>
          {loading ? <div className="spinner" /> : (
            <div className="bar-chart">
              {stats?.jobs_by_status?.map((j) => (
                <div className="bar-row" key={j.status}>
                  <div className="bar-label" style={{ width: '120px' }}>{j.status.toUpperCase()}</div>
                  <div className="bar-outer" style={{ background: 'var(--bg)' }}>
                    <div className="bar-inner" style={{ 
                      width: `${(j.count / (stats?.jobs_by_status?.[0]?.count || 1)) * 100}%`, 
                      background: j.status === 'completed' ? 'var(--success)' : 'var(--accent)' 
                    }} />
                  </div>
                  <div className="bar-count" style={{ width: '60px' }}>{j.count}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 
      {enrichMsg && (
        <div className={`alert ${enrichMsg.startsWith("✓") ? "alert-success" : "alert-error"}`} style={{ marginBottom: '24px' }}>
          {enrichMsg}
        </div>
      )}
      */}

      <div className="card" style={{ background: 'var(--surface2)', border: 'none' }}>
        <div className="card-title">Strategic Actions</div>
        <div style={{ display: "flex", gap: 16, marginTop: '20px' }}>
          <button className="btn btn-primary" onClick={() => onNavigate("scrape")} style={{ padding: '12px 24px' }}>
            ⊕ New Intelligence Mission
          </button>
          <button className="btn btn-secondary" onClick={() => onNavigate("articles")}>
             Global Archive
          </button>
          {/* 
          <button className="btn btn-secondary" onClick={handleEnrich} disabled={enriching}>
            {enriching ? <><div className="spinner" /> Processing...</> : "↻ Deep Refresh Bodies"}
          </button>
          */}
        </div>
      </div>
    </div>
  );
}
