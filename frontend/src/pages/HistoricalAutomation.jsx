import React, { useState, useEffect } from "react";
import { api } from "../services/api";

export default function HistoricalAutomation() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  
  // Default collapsed: expandedJobs[jobId] === true means expanded
  const [expandedJobs, setExpandedJobs] = useState({});

  // Filters & Sorting for main jobs list
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("date_desc");

  // Sub-process filters & sorting per parent job: { [jobId]: { month: "all", status: "all", sort: "index_asc" } }
  const [subJobControls, setSubJobControls] = useState({});

  // Form State (Default empty inputs with placeholders)
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [windowDays, setWindowDays] = useState(15);
  const [resolveUrls, setResolveUrls] = useState(false);
  
  // Feedback & Info Modal State
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [showInfoModal, setShowInfoModal] = useState(false);

  const fetchJobs = async () => {
    try {
      const data = await api.get("/historical-automation/jobs");
      setJobs(data.jobs || []);
    } catch (err) {
      console.error("Failed to fetch historical jobs", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleStartJob = async (e) => {
    e.preventDefault();
    setErrorMsg("");
    setSuccessMsg("");

    if (!name.trim() || !keywords.trim() || !dateFrom || !dateTo) {
      setErrorMsg("Please fill in all required fields.");
      return;
    }

    setCreating(true);
    try {
      const payload = {
        name: name.trim(),
        keywords: keywords.trim(),
        date_from: dateFrom,
        date_to: dateTo,
        window_days: parseInt(windowDays, 10),
        resolve_urls: resolveUrls
      };

      const res = await api.post("/historical-automation/start", payload);
      setSuccessMsg(`Launched historical backfill! Created ${res.total_sub_jobs} sub-windows.`);
      
      // Reset inputs to clean empty state with placeholders
      setName("");
      setKeywords("");
      setDateFrom("");
      setDateTo("");
      fetchJobs();
    } catch (err) {
      setErrorMsg(err.message || "Failed to start historical job.");
    } finally {
      setCreating(false);
    }
  };

  const handleStopJob = async (jobId) => {
    if (!window.confirm("Pause all processing for this job? Scraped data will be safely preserved.")) return;
    try {
      await api.post(`/historical-automation/jobs/${jobId}/stop`);
      fetchJobs();
    } catch (err) {
      alert("Failed to stop job: " + (err.message || err));
    }
  };

  const handleStopSubJob = async (subJobId) => {
    try {
      await api.post(`/historical-automation/sub-jobs/${subJobId}/stop`);
      fetchJobs();
    } catch (err) {
      alert("Failed to stop sub-job: " + (err.message || err));
    }
  };

  const handlePurgeData = async (jobId) => {
    if (!window.confirm("Are you sure you want to delete all scraped articles for this job?")) return;
    try {
      await api.delete(`/historical-automation/jobs/${jobId}/data`);
      fetchJobs();
    } catch (err) {
      alert("Failed to purge data: " + (err.message || err));
    }
  };

  const handleDeleteJob = async (jobId) => {
    if (!window.confirm("Delete this historical job AND all its scraped articles completely?")) return;
    try {
      await api.delete(`/historical-automation/jobs/${jobId}`);
      fetchJobs();
    } catch (err) {
      alert("Failed to delete job: " + (err.message || err));
    }
  };

  const handleDeleteJobOnly = async (jobId) => {
    if (!window.confirm("Delete this job container while preserving all scraped articles in the database?")) return;
    try {
      await api.delete(`/historical-automation/jobs/${jobId}?keep_data=true`);
      fetchJobs();
    } catch (err) {
      alert("Failed to delete job container: " + (err.message || err));
    }
  };

  const getApiBaseUrl = () => {
    if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
    return "/api/";
  };

  const handleDownloadMaster = (jobId) => {
    const token = localStorage.getItem("token");
    const base = getApiBaseUrl().replace(/\/$/, "");
    window.open(`${base}/historical-automation/jobs/${jobId}/download?token=${token}`, "_blank");
  };

  const handleDownloadSubExcel = (subJobId) => {
    const token = localStorage.getItem("token");
    const base = getApiBaseUrl().replace(/\/$/, "");
    window.open(`${base}/historical-automation/sub-jobs/${subJobId}/download?token=${token}`, "_blank");
  };

  const toggleExpand = (jobId) => {
    setExpandedJobs((prev) => ({ ...prev, [jobId]: !prev[jobId] }));
  };

  const expandAll = () => {
    const nextState = {};
    jobs.forEach((j) => {
      nextState[j.id] = true;
    });
    setExpandedJobs(nextState);
  };

  const collapseAll = () => {
    setExpandedJobs({});
  };

  const formatSeconds = (sec) => {
    if (!sec || sec <= 0) return "0s";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  const getSubJobControl = (jobId) => {
    return subJobControls[jobId] || { month: "all", status: "all", sort: "index_asc" };
  };

  const updateSubJobControl = (jobId, key, value) => {
    setSubJobControls((prev) => ({
      ...prev,
      [jobId]: {
        ...getSubJobControl(jobId),
        [key]: value
      }
    }));
  };

  // Aggregated Stats
  const activeJobsCount = jobs.filter((j) => j.status === "running").length;
  const grandTotalArticles = jobs.reduce((sum, j) => sum + (j.total_articles || 0), 0);

  // Main Jobs Filtering & Sorting
  const filteredJobs = jobs.filter((j) => {
    const matchesSearch =
      j.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      j.keywords.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === "all" || j.status === statusFilter;
    return matchesSearch && matchesStatus;
  }).sort((a, b) => {
    if (sortBy === "date_desc") return new Date(b.date_from) - new Date(a.date_from);
    if (sortBy === "date_asc") return new Date(a.date_from) - new Date(b.date_from);
    if (sortBy === "articles_desc") return (b.total_articles || 0) - (a.total_articles || 0);
    return new Date(b.started_at) - new Date(a.started_at);
  });

  return (
    <div style={{ maxWidth: "100%", overflowX: "hidden", boxSizing: "border-box" }}>
      {/* ─── Page Header ─────────────────────────────────────────────────── */}
      <div className="page-header" style={{ marginBottom: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <h1 className="page-title">Historical Automation</h1>
            <p className="page-subtitle">FAST METADATA-ONLY HISTORICAL SCRAPING ENGINE (TITLE, PUBLICATION, LINK, DATE & KEYWORDS)</p>
          </div>
        </div>
      </div>

      {/* ─── Stats Grid ──────────────────────────────────────────────────── */}
      <div className="stats-grid" style={{ marginBottom: "28px" }}>
        <div className="stat-card">
          <div className="stat-label">Active Jobs</div>
          <div className="stat-value">{activeJobsCount}</div>
          <div className="stat-sub">Running backfill processes</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Total Articles Found</div>
          <div className="stat-value">{grandTotalArticles.toLocaleString()}</div>
          <div className="stat-sub">Across all date ranges</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Engine Mode</div>
          <div className="stat-value" style={{ fontSize: "20px", color: "var(--accent)", marginTop: "8px" }}>
            Metadata Only
          </div>
          <div className="stat-sub">10x-50x Fast Discovery</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Sub-Window Slicing</div>
          <div className="stat-value" style={{ fontSize: "20px", color: "var(--success)", marginTop: "8px" }}>
            15 Days Auto
          </div>
          <div className="stat-sub">Progressive & Cumulative</div>
        </div>
      </div>

      {/* ─── Create Form Card ────────────────────────────────────────────── */}
      <div className="card" style={{ marginBottom: "32px", borderRadius: "14px" }}>
        <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>Launch New Historical Backfill</span>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowInfoModal(!showInfoModal)}
            style={{ fontSize: "11px", padding: "4px 10px", textTransform: "none" }}
          >
            {showInfoModal ? "Hide Keyword Info" : "Keyword Syntax Info"}
          </button>
        </div>

        {showInfoModal && (
          <div style={{ padding: "16px", background: "var(--surface2)", borderRadius: "var(--radius)", marginBottom: "20px", border: "1px solid var(--border)", fontSize: "13px", lineHeight: "1.6" }}>
            <div style={{ fontWeight: "700", marginBottom: "8px", color: "var(--accent)" }}>
              Keyword Input Syntax & Treatment Guide:
            </div>
            <ul style={{ paddingLeft: "20px", margin: 0 }}>
              <li><strong>Comma-Separated Queries:</strong> Separate multiple search queries with commas (e.g. <code>Emeritus, Google, Protectt.ai</code>).</li>
              <li><strong>Exact Phrase Matching (Quotes):</strong> Wrap keywords in quotes (e.g. <code>"protectt.ai"</code> or <code>"protection bill"</code>) to match exact phrase string without variations.</li>
              <li><strong>Mandatory Terms (+):</strong> Use <code>+</code> to require both terms in the article (e.g. <code>eruditus + india</code> matches articles with both Eruditus AND India).</li>
              <li><strong>Exclusion Terms (-):</strong> Use <code>-</code> to exclude unwanted terms (e.g. <code>noise - pollution</code> matches articles about noise while filtering out pollution).</li>
            </ul>
          </div>
        )}

        {errorMsg && (
          <div style={{ padding: "12px 16px", background: "rgba(239, 68, 68, 0.15)", color: "var(--danger)", borderRadius: "var(--radius)", marginBottom: "20px", fontSize: "13px", border: "1px solid rgba(239, 68, 68, 0.3)" }}>
            Error: {errorMsg}
          </div>
        )}
        {successMsg && (
          <div style={{ padding: "12px 16px", background: "rgba(34, 197, 94, 0.15)", color: "var(--success)", borderRadius: "var(--radius)", marginBottom: "20px", fontSize: "13px", border: "1px solid rgba(34, 197, 94, 0.3)" }}>
            Success: {successMsg}
          </div>
        )}

        <form onSubmit={handleStartJob}>
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">Client / Batch Name</label>
              <input
                type="text"
                className="form-control"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Eruditus / Emeritus Backfill or Google Historical Scraping"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Slicing Window Size</label>
              <select
                className="form-control"
                value={windowDays}
                onChange={(e) => setWindowDays(e.target.value)}
                style={{ paddingRight: "32px" }}
              >
                <option value={7}>7 Days Window (High Density Scraping)</option>
                <option value={15}>15 Days Window (Recommended)</option>
                <option value={30}>30 Days Window (Large Historical Spans)</option>
              </select>
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
              <label className="form-label" style={{ margin: 0 }}>Target Keywords (Comma-Separated)</label>
              <button
                type="button"
                onClick={() => setShowInfoModal(!showInfoModal)}
                style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", fontSize: "11px", textDecoration: "underline" }}
              >
                How will keywords be treated?
              </button>
            </div>
            <textarea
              className="form-control"
              rows={3}
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder='e.g. "Protectt.ai", eruditus + india, noise - pollution, "protection bill", Ashwin Damera'
              required
            />
          </div>

          <div className="form-grid" style={{ gridTemplateColumns: "1fr 1fr auto", alignItems: "end" }}>
            <div className="form-group">
              <label className="form-label">Start Date</label>
              <input
                type="date"
                className="form-control"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                placeholder="YYYY-MM-DD"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">End Date</label>
              <input
                type="date"
                className="form-control"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                placeholder="YYYY-MM-DD"
                required
              />
            </div>

            <button type="submit" className="btn btn-primary" disabled={creating} style={{ height: "42px", padding: "0 24px", textTransform: "none" }}>
              {creating ? "Launching..." : "Launch Backfill"}
            </button>
          </div>

          <div style={{ marginTop: "12px" }}>
            <label style={{ display: "inline-flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "12px", color: "var(--muted)", userSelect: "none" }}>
              <input
                type="checkbox"
                checked={resolveUrls}
                onChange={(e) => setResolveUrls(e.target.checked)}
                style={{ cursor: "pointer", accentColor: "var(--accent)", width: "14px", height: "14px" }}
              />
              <span>Resolve URLs to original publisher links</span>
            </label>
          </div>
        </form>
      </div>

      {/* ─── Search, Filter & Global Expand/Collapse Bar ───────────────── */}
      <div
        style={{
          display: "flex",
          justify: "space-between",
          alignItems: "center",
          marginBottom: "24px",
          gap: "16px",
          flexWrap: "wrap"
        }}
      >
        <div style={{ flex: 1, minWidth: "260px", maxWidth: "420px" }}>
          <input
            type="text"
            className="form-control"
            placeholder="Search historical jobs or keywords..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
          <button type="button" onClick={expandAll} className="btn btn-secondary" style={{ fontSize: "12px", padding: "6px 14px", textTransform: "none" }}>
            Expand All
          </button>
          <button type="button" onClick={collapseAll} className="btn btn-secondary" style={{ fontSize: "12px", padding: "6px 14px", textTransform: "none" }}>
            Collapse All
          </button>

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span className="form-label" style={{ margin: 0, fontSize: "12px" }}>Filter:</span>
            <select
              className="form-control"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ width: "auto", minWidth: "120px", fontSize: "12px", padding: "6px 32px 6px 12px" }}
            >
              <option value="all">All Statuses</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="paused">Paused</option>
            </select>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span className="form-label" style={{ margin: 0, fontSize: "12px" }}>Sort:</span>
            <select
              className="form-control"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              style={{ width: "auto", minWidth: "150px", fontSize: "12px", padding: "6px 32px 6px 12px" }}
            >
              <option value="date_desc">Latest Date First</option>
              <option value="date_asc">Oldest Date First</option>
              <option value="articles_desc">Most Articles Found</option>
            </select>
          </div>
        </div>
      </div>

      {/* ─── Jobs List Tree View ────────────────────────────────────────── */}
      {loading ? (
        <div style={{ textAlign: "center", padding: "60px", color: "var(--muted)" }}>
          <div className="spinner" style={{ margin: "0 auto 16px auto", width: "36px", height: "36px" }} />
          Loading historical jobs...
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "40px", color: "var(--muted)", borderRadius: "14px" }}>
          No historical jobs found. Launch one above using the form.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {filteredJobs.map((job) => {
            // Default is collapsed (expandedJobs[job.id] === true is expanded)
            const isExpanded = expandedJobs[job.id] === true;
            const isFinished = job.status === "completed";
            const isRunning = job.status === "running";

            // Sub-job filters for this parent job
            const subCtrl = getSubJobControl(job.id);
            const allSubMonths = Array.from(new Set((job.monthly_tracker || []).map((m) => m.month)));

            let displaySubJobs = (job.sub_jobs || []).filter((sj) => {
              const sjMonth = new Date(sj.date_from).toLocaleDateString("en-US", { month: "short", year: "numeric" });
              const matchesMonth = subCtrl.month === "all" || sjMonth === subCtrl.month;
              const matchesStatus = subCtrl.status === "all" || sj.status === subCtrl.status;
              return matchesMonth && matchesStatus;
            }).sort((a, b) => {
              if (subCtrl.sort === "index_desc") return b.window_index - a.window_index;
              if (subCtrl.sort === "articles_desc") return b.articles_found - a.articles_found;
              if (subCtrl.sort === "date_asc") return new Date(a.date_from) - new Date(b.date_from);
              if (subCtrl.sort === "date_desc") return new Date(b.date_from) - new Date(a.date_from);
              return a.window_index - b.window_index; // default index_asc
            });

            return (
              <div key={job.id} className="card" style={{ padding: 0, overflow: "hidden", borderRadius: "14px", border: "1px solid var(--border)" }}>
                {/* ─── Parent Job Header (Structured 2-Row Card Header) ──── */}
                <div
                  style={{
                    padding: "18px 22px",
                    background: "var(--surface)",
                    cursor: "pointer"
                  }}
                  onClick={() => toggleExpand(job.id)}
                >
                  {/* Row 1: Job Identity & Main Status/Metrics */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px", marginBottom: "12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleExpand(job.id);
                        }}
                        className="btn btn-secondary"
                        style={{
                          padding: "4px 12px",
                          fontSize: "12px",
                          fontWeight: "600",
                          borderRadius: "6px",
                          textTransform: "none"
                        }}
                      >
                        {isExpanded ? "Collapse ▲" : "Expand ▼"}
                      </button>

                      <h4 style={{ margin: 0, fontSize: "16px", fontWeight: "700", color: "var(--text)" }}>
                        {job.name}
                      </h4>

                      <span className={`badge badge-${job.status}`}>
                        {job.status.toUpperCase()}
                      </span>
                    </div>

                    {/* Metrics Badges on Right */}
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      <span style={{
                        fontSize: "12px",
                        fontWeight: "600",
                        padding: "4px 12px",
                        borderRadius: "16px",
                        background: "var(--nav-active)",
                        color: "var(--accent)",
                        border: "1px solid var(--nav-active-border)"
                      }}>
                        Articles Scraped: {job.total_articles.toLocaleString()}
                      </span>

                      {isRunning && (
                        <>
                          <span className="badge badge-pending" style={{ textTransform: "none" }}>
                            Elapsed: {formatSeconds(job.elapsed_seconds)}
                          </span>
                          <span className="badge badge-running" style={{ textTransform: "none" }}>
                            ETA: ~{formatSeconds(job.eta_seconds)}
                          </span>
                        </>
                      )}

                      {isFinished && job.total_duration_seconds > 0 && (
                        <span className="badge badge-completed" style={{ textTransform: "none" }}>
                          Duration: {formatSeconds(job.total_duration_seconds)}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Row 2: Date Range Sub-Text & Actions Toolbar */}
                  <div
                    style={{
                      display: "flex",
                      justify: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "12px",
                      paddingTop: "10px",
                      borderTop: "1px solid rgba(128, 128, 128, 0.15)"
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                      Date Span: <strong>{job.date_from}</strong> to <strong>{job.date_to}</strong> &bull; {job.total_sub_jobs} sub-windows ({job.window_days} days/window)
                    </div>

                    {/* Actions Toolbar */}
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      {job.has_master_excel && (
                        <button
                          type="button"
                          onClick={() => handleDownloadMaster(job.id)}
                          className="btn btn-primary"
                          style={{ fontSize: "12px", padding: "5px 14px", textTransform: "none" }}
                        >
                          Download Master Excel
                        </button>
                      )}

                      {isRunning && (
                        <button
                          type="button"
                          onClick={() => handleStopJob(job.id)}
                          className="btn btn-secondary"
                          style={{ fontSize: "12px", padding: "5px 14px", color: "var(--warning)", textTransform: "none" }}
                        >
                          Pause All
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => handlePurgeData(job.id)}
                        className="btn btn-secondary"
                        style={{ fontSize: "12px", padding: "5px 14px", color: "var(--danger)", textTransform: "none" }}
                        title="Purge scraped data while keeping job container"
                      >
                        Purge Data
                      </button>

                      <button
                        type="button"
                        onClick={() => handleDeleteJobOnly(job.id)}
                        className="btn btn-secondary"
                        style={{ fontSize: "12px", padding: "5px 14px", textTransform: "none" }}
                        title="Delete job container while preserving all scraped articles in the database"
                      >
                        Delete (Keep Scraped Data)
                      </button>

                      <button
                        type="button"
                        onClick={() => handleDeleteJob(job.id)}
                        className="btn btn-danger"
                        style={{ fontSize: "12px", padding: "5px 14px", textTransform: "none" }}
                        title="Delete entire job and remove all its scraped articles"
                      >
                        Delete Job & Data
                      </button>
                    </div>
                  </div>
                </div>

                {/* ─── Expanded Job Section ─────────────────────────────── */}
                {isExpanded && (
                  <div style={{ borderTop: "1px solid var(--border)" }}>
                    {/* Progress Bar & Month Completion Tracker */}
                    <div style={{ padding: "16px 20px", background: "var(--surface2)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "var(--muted)", marginBottom: "8px" }}>
                        <span>Progress: <strong>{job.completed_sub_jobs}</strong> / <strong>{job.total_sub_jobs}</strong> Sub-Windows Completed</span>
                        <span>Total Articles Discovered: <strong style={{ color: "var(--accent)", fontSize: "14px" }}>{job.total_articles.toLocaleString()}</strong></span>
                      </div>

                      {/* Progress Bar Track */}
                      <div className="progress-bar-track" style={{ height: "6px", overflow: "hidden", marginBottom: "14px" }}>
                        <div
                          className="progress-bar-fill"
                          style={{
                            width: `${(job.completed_sub_jobs / job.total_sub_jobs) * 100}%`,
                            background: isFinished ? "var(--success)" : "var(--accent)",
                            transition: "width 0.5s ease"
                          }}
                        />
                      </div>

                      {/* Month Completion Tracker Pills (Flex Wrap to fit View Window) */}
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                        {job.monthly_tracker.map((m, idx) => (
                          <span
                            key={idx}
                            className={`badge badge-${m.status}`}
                            style={{ whiteSpace: "nowrap", cursor: "pointer", textTransform: "none" }}
                            onClick={() => updateSubJobControl(job.id, "month", subCtrl.month === m.month ? "all" : m.month)}
                            title="Click to filter subprocesses by this month"
                          >
                            {m.month} ({m.status.toUpperCase()})
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Sub-Processes Filter & Sorting Controls */}
                    <div style={{
                      padding: "12px 20px",
                      background: "var(--surface)",
                      borderTop: "1px solid var(--border)",
                      borderBottom: "1px solid var(--border)",
                      display: "flex",
                      justify: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "12px"
                    }}>
                      <div style={{ fontSize: "13px", fontWeight: "700", color: "var(--text)" }}>
                        Sub-Processes & Slicing Windows ({displaySubJobs.length})
                      </div>

                      <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontSize: "11px", color: "var(--muted)" }}>Month:</span>
                          <select
                            className="form-control"
                            value={subCtrl.month}
                            onChange={(e) => updateSubJobControl(job.id, "month", e.target.value)}
                            style={{ width: "auto", minWidth: "120px", fontSize: "12px", padding: "5px 32px 5px 10px" }}
                          >
                            <option value="all">All Months</option>
                            {allSubMonths.map((m) => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontSize: "11px", color: "var(--muted)" }}>Status:</span>
                          <select
                            className="form-control"
                            value={subCtrl.status}
                            onChange={(e) => updateSubJobControl(job.id, "status", e.target.value)}
                            style={{ width: "auto", minWidth: "120px", fontSize: "12px", padding: "5px 32px 5px 10px" }}
                          >
                            <option value="all">All Statuses</option>
                            <option value="completed">Completed</option>
                            <option value="running">Running</option>
                            <option value="pending">Pending</option>
                            <option value="paused">Paused</option>
                          </select>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontSize: "11px", color: "var(--muted)" }}>Sort:</span>
                          <select
                            className="form-control"
                            value={subCtrl.sort}
                            onChange={(e) => updateSubJobControl(job.id, "sort", e.target.value)}
                            style={{ width: "auto", minWidth: "150px", fontSize: "12px", padding: "5px 32px 5px 10px" }}
                          >
                            <option value="index_asc">Window # (1 to N)</option>
                            <option value="index_desc">Window # (N to 1)</option>
                            <option value="articles_desc">Most Articles</option>
                            <option value="date_asc">Oldest Date</option>
                            <option value="date_desc">Latest Date</option>
                          </select>
                        </div>
                      </div>
                    </div>

                    {/* Sub-Processes Tree View Table */}
                    <div className="table-wrap" style={{ border: "none", borderRadius: 0, maxWidth: "100%", overflowX: "auto" }}>
                      <table>
                        <thead>
                          <tr>
                            <th>Sub-Window</th>
                            <th>Date Span</th>
                            <th>Status</th>
                            <th>Articles Discovered</th>
                            <th style={{ textAlign: "right" }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {displaySubJobs.length === 0 ? (
                            <tr>
                              <td colSpan={5} style={{ textAlign: "center", padding: "20px", color: "var(--muted)" }}>
                                No sub-processes match the selected filters.
                              </td>
                            </tr>
                          ) : (
                            displaySubJobs.map((sj) => (
                              <tr key={sj.id}>
                                <td style={{ fontWeight: "600", fontFamily: "var(--font-mono)" }}>
                                  Window #{sj.window_index}
                                </td>
                                <td style={{ color: "var(--muted)" }}>
                                  {sj.date_from} to {sj.date_to}
                                </td>
                                <td>
                                  <span className={`badge badge-${sj.status}`}>
                                    {sj.status.toUpperCase()}
                                  </span>
                                </td>
                                <td style={{ fontWeight: "700" }}>
                                  {sj.articles_found} Articles
                                </td>
                                <td style={{ textAlign: "right" }}>
                                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                                    {sj.has_excel && (
                                      <button
                                        type="button"
                                        onClick={() => handleDownloadSubExcel(sj.id)}
                                        className="btn btn-secondary"
                                        style={{ fontSize: "11px", padding: "4px 10px", textTransform: "none" }}
                                      >
                                        Download Excel
                                      </button>
                                    )}
                                    {sj.status === "running" && (
                                      <button
                                        type="button"
                                        onClick={() => handleStopSubJob(sj.id)}
                                        className="btn btn-secondary"
                                        style={{ fontSize: "11px", padding: "4px 8px", color: "var(--warning)", textTransform: "none" }}
                                      >
                                        Stop
                                      </button>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
