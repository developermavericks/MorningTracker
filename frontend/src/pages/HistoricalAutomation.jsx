import React, { useState, useEffect } from "react";
import { api } from "../services/api";

export default function HistoricalAutomation() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [expandedJobs, setExpandedJobs] = useState({});

  // Filters & Sorting
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("date_desc");

  // Form State
  const [name, setName] = useState("Eruditus / Emeritus Backfill");
  const [keywords, setKeywords] = useState(
    "Emeritus, Eruditus, Ashwin Damera, Chaitanya Kalipatnapu, Bhushan Heda, Avnish Singhal, Jawahir Morarji"
  );
  const [dateFrom, setDateFrom] = useState("2024-10-01");
  const [dateTo, setDateTo] = useState(new Date().toISOString().split("T")[0]);
  const [windowDays, setWindowDays] = useState(15);
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

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
    const interval = setInterval(fetchJobs, 5000); // Live poll every 5s
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
        window_days: parseInt(windowDays, 10)
      };

      const res = await api.post("/historical-automation/start", payload);
      setSuccessMsg(`Launched historical backfill! Created ${res.total_sub_jobs} sub-windows.`);
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
    if (!window.confirm("Delete this historical job completely?")) return;
    try {
      await api.delete(`/historical-automation/jobs/${jobId}`);
      fetchJobs();
    } catch (err) {
      alert("Failed to delete job: " + (err.message || err));
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

  const loadPresetEmeritus = () => {
    setName("Eruditus / Emeritus Backfill");
    setKeywords(
      "Emeritus, Eruditus, Ashwin Damera, Chaitanya Kalipatnapu, Bhushan Heda, Avnish Singhal, Jawahir Morarji"
    );
    setDateFrom("2024-10-01");
    setDateTo(new Date().toISOString().split("T")[0]);
    setWindowDays(15);
  };

  const formatSeconds = (sec) => {
    if (!sec || sec <= 0) return "0s";
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  // Aggregated Stats
  const activeJobsCount = jobs.filter((j) => j.status === "running").length;
  const grandTotalArticles = jobs.reduce((sum, j) => sum + (j.total_articles || 0), 0);

  // Filter & Sort Logic
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
    <div>
      {/* ─── Page Header ─────────────────────────────────────────────────── */}
      <div className="page-header">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <h1 className="page-title">Historical Automation</h1>
            <p className="page-subtitle">FAST METADATA-ONLY HISTORICAL SCRAPING ENGINE (TITLE, PUBLICATION, LINK, DATE & KEYWORDS)</p>
          </div>
          <button type="button" onClick={loadPresetEmeritus} className="btn btn-secondary" style={{ fontSize: "11px" }}>
            ⚡ Preset: Eruditus / Emeritus
          </button>
        </div>
      </div>

      {/* ─── Stats Grid ──────────────────────────────────────────────────── */}
      <div className="stats-grid">
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
          <div className="stat-sub">10x–50x Fast Discovery</div>
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
      <div className="card" style={{ marginBottom: "32px" }}>
        <div className="card-title">Launch New Historical Backfill</div>

        {errorMsg && (
          <div style={{ padding: "12px 16px", background: "rgba(239, 68, 68, 0.15)", color: "var(--danger)", borderRadius: "var(--radius)", marginBottom: "20px", fontSize: "13px", border: "1px solid rgba(239, 68, 68, 0.3)" }}>
            ⚠️ {errorMsg}
          </div>
        )}
        {successMsg && (
          <div style={{ padding: "12px 16px", background: "rgba(34, 197, 94, 0.15)", color: "var(--success)", borderRadius: "var(--radius)", marginBottom: "20px", fontSize: "13px", border: "1px solid rgba(34, 197, 94, 0.3)" }}>
            ✅ {successMsg}
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
                placeholder="e.g. Eruditus / Emeritus Backfill"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Slicing Window Size</label>
              <select
                className="form-control"
                value={windowDays}
                onChange={(e) => setWindowDays(e.target.value)}
              >
                <option value={7}>7 Days Window (High Density Scraping)</option>
                <option value={15}>15 Days Window (Recommended)</option>
                <option value={30}>30 Days Window (Large Historical Spans)</option>
              </select>
            </div>
          </div>

          <div className="form-group" style={{ marginBottom: "20px" }}>
            <label className="form-label">Target Keywords (Comma-Separated)</label>
            <textarea
              className="form-control"
              rows={3}
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="e.g. Emeritus, Eruditus, Ashwin Damera"
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
                required
              />
            </div>

            <button type="submit" className="btn btn-primary" disabled={creating} style={{ height: "42px" }}>
              {creating ? "Launching..." : "🚀 Launch Backfill"}
            </button>
          </div>
        </form>
      </div>

      {/* ─── Search, Filter & Sorting Bar ───────────────────────────────── */}
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
        <div style={{ flex: 1, maxWidth: "400px" }}>
          <input
            type="text"
            className="form-control"
            placeholder="🔍 Search historical jobs or keywords..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className="form-label" style={{ margin: 0 }}>Filter:</span>
            <select
              className="form-control"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{ width: "auto" }}
            >
              <option value="all">All Statuses</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="paused">Paused</option>
            </select>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className="form-label" style={{ margin: 0 }}>Sort:</span>
            <select
              className="form-control"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              style={{ width: "auto" }}
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
        <div className="card" style={{ textAlign: "center", padding: "40px", color: "var(--muted)" }}>
          No historical jobs found. Launch one above!
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {filteredJobs.map((job) => {
            const isExpanded = expandedJobs[job.id] !== false; // Default expanded
            const isFinished = job.status === "completed";
            const isRunning = job.status === "running";
            const isPaused = job.status === "paused";

            return (
              <div key={job.id} className="card" style={{ padding: 0, overflow: "hidden" }}>
                {/* ─── Parent Job Header ───────────────────────────────────── */}
                <div
                  style={{
                    padding: "20px 24px",
                    background: "var(--surface)",
                    borderBottom: "1px solid var(--border)",
                    display: "flex",
                    justify: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "16px"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <button
                      type="button"
                      onClick={() => toggleExpand(job.id)}
                      style={{
                        background: "var(--surface2)",
                        border: "1px solid var(--border)",
                        color: "var(--text)",
                        borderRadius: "var(--radius)",
                        width: "30px",
                        height: "30px",
                        display: "flex",
                        alignItems: "center",
                        justify: "center",
                        cursor: "pointer",
                        fontSize: "12px"
                      }}
                    >
                      {isExpanded ? "▼" : "▶"}
                    </button>

                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                        <h4 style={{ margin: 0, fontSize: "16px", fontWeight: "700", color: "var(--text)" }}>
                          {job.name}
                        </h4>
                        <span className={`badge badge-${job.status}`}>
                          {job.status.toUpperCase()}
                        </span>
                      </div>

                      <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>
                        📅 <strong>{job.date_from}</strong> to <strong>{job.date_to}</strong> ({job.total_sub_jobs} sub-windows of {job.window_days} days)
                      </div>
                    </div>
                  </div>

                  {/* Timing Badges & Action Buttons */}
                  <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
                    {isRunning && (
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <span className="badge badge-pending">
                          ⏱️ Elapsed: {formatSeconds(job.elapsed_seconds)}
                        </span>
                        <span className="badge badge-running">
                          ⏳ ETA: ~{formatSeconds(job.eta_seconds)}
                        </span>
                      </div>
                    )}

                    {job.has_master_excel && (
                      <button
                        type="button"
                        onClick={() => handleDownloadMaster(job.id)}
                        className="btn btn-primary"
                        style={{ fontSize: "11px", padding: "8px 14px" }}
                      >
                        📊 Download Master Excel
                      </button>
                    )}

                    {isRunning && (
                      <button
                        type="button"
                        onClick={() => handleStopJob(job.id)}
                        className="btn btn-secondary"
                        style={{ fontSize: "11px", padding: "8px 14px", color: "var(--warning)" }}
                      >
                        ⏸️ Pause All
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => handlePurgeData(job.id)}
                      className="btn btn-secondary"
                      style={{ fontSize: "11px", padding: "8px 14px", color: "var(--danger)" }}
                      title="Purge scraped data while keeping job container"
                    >
                      🧹 Purge Data
                    </button>

                    <button
                      type="button"
                      onClick={() => handleDeleteJob(job.id)}
                      className="btn btn-danger"
                      style={{ fontSize: "11px", padding: "8px 12px" }}
                      title="Delete entire job"
                    >
                      🗑️
                    </button>
                  </div>
                </div>

                {/* ─── Progress Bar & Month Completion Tracker ─────────────── */}
                <div style={{ padding: "16px 24px", background: "var(--surface2)", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "var(--muted)", marginBottom: "8px" }}>
                    <span>Progress: <strong>{job.completed_sub_jobs}</strong> / <strong>{job.total_sub_jobs}</strong> Sub-Windows Completed</span>
                    <span>Articles Discovered: <strong style={{ color: "var(--accent)", fontSize: "14px" }}>{job.total_articles.toLocaleString()}</strong></span>
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

                  {/* Month Completion Tracker Grid */}
                  <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "4px" }}>
                    {job.monthly_tracker.map((m, idx) => (
                      <span
                        key={idx}
                        className={`badge badge-${m.status}`}
                        style={{ whiteSpace: "nowrap" }}
                      >
                        {m.month} {m.status === "completed" ? "✅" : m.status === "running" ? "⏳" : m.status === "paused" ? "⏸️" : "🕒"}
                      </span>
                    ))}
                  </div>
                </div>

                {/* ─── Sub-Processes Tree View Table ───────────────────────── */}
                {isExpanded && (
                  <div className="table-wrap" style={{ border: "none", borderRadius: 0 }}>
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
                        {job.sub_jobs.map((sj) => (
                          <tr key={sj.id}>
                            <td style={{ fontWeight: "600", fontFamily: "var(--font-mono)" }}>
                              Window #{sj.window_index}
                            </td>
                            <td style={{ color: "var(--muted)" }}>
                              📅 {sj.date_from} → {sj.date_to}
                            </td>
                            <td>
                              <span className={`badge badge-${sj.status}`}>
                                {sj.status.toUpperCase()}
                              </span>
                            </td>
                            <td style={{ fontWeight: "700" }}>
                              {sj.articles_found}
                            </td>
                            <td style={{ textAlign: "right" }}>
                              <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                                {sj.has_excel && (
                                  <button
                                    type="button"
                                    onClick={() => handleDownloadSubExcel(sj.id)}
                                    className="btn btn-secondary"
                                    style={{ fontSize: "11px", padding: "4px 10px" }}
                                  >
                                    📄 Download Excel
                                  </button>
                                )}
                                {sj.status === "running" && (
                                  <button
                                    type="button"
                                    onClick={() => handleStopSubJob(sj.id)}
                                    className="btn btn-secondary"
                                    style={{ fontSize: "11px", padding: "4px 8px", color: "var(--warning)" }}
                                  >
                                    ⏸️ Stop
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
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
