import { useState, useEffect } from "react";
import useStore from "../store/useStore";
import { api } from "../services/api";

function JobRow({ job, onDelete, onRefresh }) {
  const isDiscovery = job.current_phase === 'Discovery' || job.current_phase === 'BrandDiscovery';

  const pct = job.total_found > 0
    ? Math.round((job.total_scraped / job.total_found) * 100)
    : 0;

  // FIX #2: useState is already at the top of the component — confirmed correct position
  const [docError, setDocError] = useState(null);

  const handleDocClick = async (e) => {
    e.preventDefault();
    setDocError(null);

    // FIX #4: window.open BEFORE any await, so it stays within the synchronous
    // user gesture and is not blocked by the browser as a popup
    const newTab = window.open("https://format-template-ggnn.vercel.app/", "_blank");

    try {
      const excelUrl = api.getExcelUrl(job.id);
      const response = await fetch(excelUrl);
      if (!response.ok) throw new Error(`Failed to fetch report: ${response.statusText}`);

      const blob = await response.blob();
      
      // Trigger download so user can manually upload to the Streamlit app
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `Nexus_Report_${job.sector}_${job.id.slice(0, 8)}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      console.log(`[Doc Button] Processing complete for job ${job.id}`);
    } catch (err) {
      console.error("[Doc Button Error]", err);
      // FIX #4 continued: close the tab we already opened if the fetch failed
      if (newTab) newTab.close();
      setDocError("Failed to prepare document. Try manual report download.");
      setTimeout(() => setDocError(null), 5000);
    }
  };

  return (
    <tr>
      <td style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
        {job.id.slice(0, 8)}
      </td>
      <td>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span className="badge badge-sector">{job.sector}</span>
          {job.current_phase && (
            <span style={{ fontSize: '9px', fontWeight: 'bold', color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              {job.current_phase}
            </span>
          )}
        </div>
      </td>
      <td style={{ fontSize: '13px' }}>
        <span className={`badge badge-${job.status}`}>{job.status}</span>
      </td>
      <td>
        <div style={{ fontSize: '12px', fontWeight: '600' }}>{job.user_name}</div>
        <div style={{ fontSize: '10px', color: 'var(--muted)' }}>{job.user_email}</div>
      </td>
      <td>
        <div style={{ minWidth: 180 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: "var(--muted)", marginBottom: 6 }}>
            <span>
              {isDiscovery || job.status === 'pending'
                ? `Found: ${job.cumulative_found || 0}`
                : `Extracted: ${job.total_scraped}/${job.total_found}`}
            </span>
            <span>{job.status === 'running' && pct > 0 ? `${pct}%` : ''}</span>
          </div>
          <div className="progress-bar-track" style={{ height: '4px', overflow: 'hidden' }}>
            <div
              className={`progress-bar-fill ${isDiscovery ? 'progress-pulse' : ''}`}
              style={{
                width: isDiscovery ? '100%' : `${pct}%`,
                background: job.status === 'failed' ? 'var(--danger)' : isDiscovery ? 'var(--info)' : 'var(--accent)',
                transition: 'width 0.5s ease',
                opacity: isDiscovery ? 0.6 : 1
              }}
            />
          </div>
        </div>
      </td>
      <td style={{ fontSize: 11, color: "var(--muted)" }}>
        {job.started_at ? new Date(job.started_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : "—"}
      </td>
      <td style={{ textAlign: 'right' }}>
        <div style={{ display: "flex", gap: 8, justifyContent: 'flex-end', alignItems: 'center' }}>
          {job.status === 'completed' && (
            // FIX #1 & #3: Replaced position:absolute on error span (which breaks inside <tr>/<td>)
            // with a column flex wrapper so error renders inline below the buttons — no absolute
            // positioning needed, works correctly inside table cells
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <a 
                  href={api.getExcelUrl(job.id)} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="btn btn-secondary" 
                  style={{ padding: '4px 12px', fontSize: '11px', textDecoration: 'none', borderColor: 'var(--accent)', color: 'var(--accent)' }}
                >
                  Report
                </a>
                <button 
                  className="btn btn-secondary" 
                  style={{ padding: '4px 12px', fontSize: '11px', borderColor: 'var(--accent)', color: 'var(--accent)' }}
                  onClick={handleDocClick}
                  title="Download report and open documentation generator in a new tab"
                >
                  Doc
                </button>
              </div>
              {docError && (
                <span style={{ 
                  color: 'var(--danger)', 
                  fontSize: '10px', 
                  whiteSpace: 'nowrap',
                  background: 'var(--surface)',
                  padding: '2px 8px',
                  borderRadius: '4px',
                  border: '1px solid var(--danger)',
                  boxShadow: 'var(--glow)'
                }}>
                  {docError}
                </span>
              )}
            </div>
          )}
          <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => onRefresh(job.id)}>
            ↻
          </button>
          <button className="btn btn-danger" style={{ padding: "4px 10px", fontSize: 11, background: 'none', border: 'none' }} onClick={() => onDelete(job.id)}>
            ✕
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function Jobs() {
  const { jobs, totalJobs, stats, fetchJobs, fetchStats } = useStore();
  const [loading, setLoading] = useState(!jobs.length);
  const [page, setPage] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    // Fetch aggregate stats independently for accuracy
    fetchStats();
    
    // Initial fetch for the CURRENT page (if we just loaded, it's 1)
    if (page === 1) {
      fetchJobs(1, false).finally(() => setLoading(false));
    }
    
    // Poll only for the first page to maintain performance and keep list fresh.
    // If the user has loaded page 2+, we stop auto-refreshing to prevent the list from resetting.
    let interval = null;
    if (page === 1) {
      interval = setInterval(() => {
        fetchJobs(1, false);
        fetchStats();
      }, 10000);
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [page]); // Restart/Stop interval based on current page

  const handleLoadMore = async () => {
    setLoadingMore(true);
    const nextPage = page + 1;
    await fetchJobs(nextPage, true);
    setPage(nextPage);
    setLoadingMore(false);
  };

  const refreshJob = async (id) => {
    try {
      const updated = await api.get(`/scrape/job/${id}?t=${Date.now()}`);
      useStore.setState({
        jobs: useStore.getState().jobs.map(j => j.id === id ? updated : j)
      });
    } catch { }
  };

  const deleteJob = async (id) => {
    if (!confirm("Remove this intelligence mission from history?")) return;
    try {
      await api.delete(`/scrape/job/${id}`);
      useStore.setState({
        jobs: useStore.getState().jobs.filter(j => j.id !== id)
      });
    } catch { }
  };

  const safeJobs = Array.isArray(jobs) ? jobs : [];
  const activeCount = safeJobs.filter((j) => j.status === "running" || j.status === "pending").length;
  const totalArticles = safeJobs.reduce((sum, j) => sum + (j.total_scraped || 0), 0);

  return (
    <div>
      <header className="page-header" style={{ marginBottom: '40px' }}>
        <h1 className="page-title">Mission Control (v2.0 - With Initiator Info)</h1>
        <p className="page-subtitle">Monitoring background operations and data streams</p>
      </header>

      <div className="stats-grid" style={{ marginBottom: 32 }}>
        <div className="stat-card" style={{ boxShadow: 'var(--glow)' }}>
          <div className="stat-label">System Active</div>
          <div className="stat-value">{stats?.active_jobs || 0}</div>
          <div className="stat-sub">Concurrent Missions</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Yield</div>
          <div className="stat-value">{(stats?.total_articles || 0).toLocaleString()}</div>
          <div className="stat-sub">Total Insights Gathered</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Success Rate</div>
          <div className="stat-value">
            {stats?.success_rate || 0}%
          </div>
          <div className="stat-sub">Reliability Metric</div>
        </div>
      </div>

      <div className="card" style={{ border: 'none', boxShadow: 'var(--glow)' }}>
        <div className="card-title">Intelligence Archive</div>
        <div className="table-wrap" style={{ border: 'none', marginTop: '16px' }}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Target</th>
                <th>Status</th>
                <th>Initiator</th>
                <th>Extraction Progress</th>
                <th>Initiated (IST)</th>
                <th style={{ textAlign: 'right' }}>Management</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} style={{ textAlign: "center", padding: 60 }}>
                  <div className="spinner" />
                </td></tr>
              ) : safeJobs.length === 0 ? (
                <tr><td colSpan={7} style={{ textAlign: "center", padding: 60, color: "var(--muted)" }}>
                  No jobs found. Start a scrape to see them here!
                </td></tr>
              ) : jobs.map((job) => (
                <JobRow key={job.id} job={job} onDelete={deleteJob} onRefresh={refreshJob} />
              ))}
            </tbody>
          </table>
          
          {jobs.length < totalJobs && (
            <div style={{ textAlign: "center", padding: "24px 0" }}>
              <button 
                className="btn btn-secondary" 
                onClick={handleLoadMore} 
                disabled={loadingMore}
                style={{ padding: "8px 24px", minWidth: "160px" }}
              >
                {loadingMore ? "Loading..." : "Load More Archive Data"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}