import { useState, useEffect, useRef } from "react";
import apiClient, { api } from "../services/api";

const BASE = "/heavy-automation";
const TIMEZONES = ["Asia/Kolkata", "UTC", "America/New_York", "America/Los_Angeles", "Europe/London"];
const WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
const MONTH_DAYS = Array.from({ length: 31 }, (_, i) => i + 1);

const DEFAULT_COMPANY = {
  name: "",
  sector_match: "",
  enabled: true,
  timezone: "Asia/Kolkata",
  fetch_time: "07:00",
  window_hours: 24,
  relevancy_method: "Hybrid",
  llm_judge_enabled: false,
  pooja_algo_enabled: false,
  pooja_folder_filtering_enabled: false,
  pooja_priority_conf: 5,
  pooja_non_priority_conf: 7,
  email_send_reports: true,
  email_send_html: false,
  search_mode: "title",
  relevance_context: "",
  relevance_threshold: 0.5,
  mail_send_mode: "Immediate",
  mail_send_time: "08:00",
  frequency: "Daily",
  days: [],
  recipients: [],
};

// API helpers
async function fetchCompanies() { return await api.get(`${BASE}/companies`); }
async function createCompany(body) { return await api.post(`${BASE}/companies`, body); }
async function updateCompany(id, body) { return await api.put(`${BASE}/companies/${id}`, body); }
async function deleteCompany(id) { return await api.delete(`${BASE}/companies/${id}`); }
async function triggerRun(id) { return await api.post(`${BASE}/companies/${id}/run`); }
async function fetchRuns(id) { return await api.get(`${BASE}/companies/${id}/runs`); }
async function fetchRunArticles(runId) { return await api.get(`${BASE}/runs/${runId}/articles`); }

function StatusPill({ status }) {
  const styles = {
    running: { bg: "rgba(74,158,255,.1)", color: "var(--accent)" },
    completed: { bg: "rgba(16,185,129,.1)", color: "#10b981" },
    failed: { bg: "rgba(239,68,68,.1)", color: "#ef4444" },
    pending: { bg: "rgba(245,158,11,.1)", color: "#f59e0b" },
    sent: { bg: "rgba(16,185,129,.1)", color: "#10b981" },
  };
  const s = styles[status] || styles.pending;
  return <span style={{ background: s.bg, color: s.color, fontSize: "11px", fontWeight: 700, textTransform: "uppercase", padding: "4px 8px", borderRadius: "4px" }}>{status}</span>;
}

function RecipientItem({ email, onRemove }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "rgba(30,58,95,.15)", borderRadius: "6px", border: "1px solid rgba(30,58,95,.3)", marginBottom: "6px" }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "13px", fontWeight: 600 }}>{email}</div>
        <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>Google Intelligence Report</div>
      </div>
      <button onClick={onRemove} style={{ background: "none", border: "none", color: "var(--danger)", cursor: "pointer", fontSize: "18px", padding: "0 8px" }}>×</button>
    </div>
  );
}

function AddRecipientForm({ onAdd }) {
  const [email, setEmail] = useState("");
  const add = () => {
    if (!email.trim()) return;
    onAdd(email);
    setEmail("");
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px", padding: "12px", border: "1px dashed var(--border)", borderRadius: "6px" }}>
      <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--muted)", textTransform: "uppercase" }}>Add New Recipient</div>
      <div style={{ display: "flex", gap: "8px" }}>
        <input type="email" placeholder="email@example.com" value={email} onChange={e => setEmail(e.target.value)} style={{ flex: 1, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", fontSize: "13px" }} />
        <button onClick={add} style={{ padding: "8px 16px", background: "var(--accent)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700, fontSize: "13px" }}>Add</button>
      </div>
    </div>
  );
}

function DaySelector({ frequency, days, onChange }) {
  if (frequency === "Daily") return null;
  const safeDays = days || [];
  const options = frequency === "Monthly" ? MONTH_DAYS.map(String) : WEEKDAYS;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
      {options.map(d => (
        <button key={d} onClick={() => onChange(safeDays.includes(String(d)) ? safeDays.filter(x => x !== String(d)) : [...safeDays, String(d)])} style={{
          padding: "6px 12px", borderRadius: "4px", fontSize: "12px", fontWeight: 600, border: "1px solid", cursor: "pointer",
          background: safeDays.includes(String(d)) ? "var(--accent)" : "transparent",
          color: safeDays.includes(String(d)) ? "white" : "var(--text)",
          borderColor: safeDays.includes(String(d)) ? "var(--accent)" : "var(--border)",
        }}>{d}</button>
      ))}
    </div>
  );
}

function parseHeavyProgressLog(progressMessage, startedAt, completedAt, status, llmEnabled = true) {
  if (!progressMessage) {
    return { progress: 0, steps: [], lines: "" };
  }
  
  const lines = progressMessage.split("\n").map(l => l.trim()).filter(Boolean);
  
  const steps = [
    { key: "fetch", label: "Fetching articles from database", status: "pending" },
    { key: "dedup", label: "Deduplication & Clustering", status: "pending" },
    { key: "relevancy", label: "Hybrid Relevancy check", status: "pending" },
  ];
  if (llmEnabled) {
    steps.push({ key: "llm", label: "LLM Review & Verification", status: "pending" });
  }
  steps.push(
    { key: "report", label: "Generating briefs & reports", status: "pending" },
    { key: "email", label: "Sending intelligence email", status: "pending" }
  );
  
  let activeIndex = -1;
  
  for (const line of lines) {
    if (line.includes("Fetching articles")) {
      activeIndex = 0;
    } else if (line.includes("Exact dedup") || line.includes("Near-dup clustering")) {
      activeIndex = 1;
    } else if (line.includes("Filtering articles")) {
      activeIndex = 2;
    } else if (line.includes("LLM judgment")) {
      if (llmEnabled) {
        activeIndex = 3;
      } else {
        activeIndex = 2;
      }
    } else if (line.includes("Generating combined Google Report") || line.includes("Report saved") || line.includes("Report DOCX saved") || line.includes("Report Excel saved")) {
      activeIndex = llmEnabled ? 4 : 3;
    } else if (line.includes("Sending intelligence brief email") || line.includes("Sending email") || line.includes("Email scheduled")) {
      activeIndex = llmEnabled ? 5 : 4;
    }
  }
  
  for (let i = 0; i < steps.length; i++) {
    if (status === "completed") {
      steps[i].status = "completed";
    } else if (status === "failed") {
      if (i < activeIndex) {
        steps[i].status = "completed";
      } else if (i === activeIndex) {
        steps[i].status = "failed";
      } else {
        steps[i].status = "pending";
      }
    } else {
      if (i < activeIndex) {
        steps[i].status = "completed";
      } else if (i === activeIndex) {
        steps[i].status = "running";
      } else {
        steps[i].status = "pending";
      }
    }
  }
  
  let pct = 0;
  if (status === "completed") {
    pct = 100;
  } else if (status === "failed") {
    pct = 100;
  } else if (activeIndex !== -1) {
    pct = Math.round(((activeIndex + 0.5) / steps.length) * 100);
  } else {
    pct = 5;
  }
  
  return {
    progress: pct,
    steps,
    lines: lines.join("\n"),
  };
}

function RunHistory({ company }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const expandedInitRef = useRef(false);

  const handleDownloadReport = async (filename) => {
    try {
      const name = filename.split(/[/\\]/).pop();
      const blob = await apiClient.get(`heavy-automation/reports/${name}`, {
        responseType: "blob"
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      console.error("Failed to download file", err);
      alert("Failed to download report. It may have been cleared or expired.");
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchRuns(company.id);
        const sorted = data || [];
        setRuns(sorted);
        // Auto-expand the latest run on first load
        if (!expandedInitRef.current && sorted.length > 0) {
          setExpanded(sorted[0].id);
          expandedInitRef.current = true;
        }
      } catch (e) {
        console.error("Failed to load runs:", e);
      } finally {
        setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 4000);
    return () => clearInterval(interval);
  }, [company.id]);

  if (loading) return <div style={{ color: "var(--muted)" }}>Loading run history...</div>;
  if (!runs.length) return <div style={{ color: "var(--muted)" }}>No runs yet. Click "Run Now" to start.</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {runs.map((run, idx) => (
        <div key={run.id} style={{ border: "1px solid var(--border)", borderRadius: "6px", overflow: "hidden" }}>
          <div onClick={() => setExpanded(expanded === run.id ? null : run.id)} style={{ padding: "12px", background: "rgba(30,58,95,.05)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", flex: 1 }}>
              <StatusPill status={run.status} />
              <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                  {run.fetched_count} fetched • {run.deduped_count} deduped • <strong>{run.relevant_count} relevant</strong>
                </div>
                <div style={{ fontSize: "10px", color: "var(--muted)", opacity: 0.6 }}>
                  {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                  {idx === 0 && <span style={{ marginLeft: "6px", color: "var(--accent)", fontWeight: 700 }}>● Latest</span>}
                </div>
              </div>
            </div>
            <span style={{ color: "var(--muted)" }}>{expanded === run.id ? "▲" : "▼"}</span>
          </div>
          {expanded === run.id && (
            <div style={{ padding: "12px", borderTop: "1px solid var(--border)", background: "rgba(30,58,95,.02)", fontSize: "12px", display: "flex", flexDirection: "column", gap: "10px" }}>
              <div><strong>Email Status:</strong> <StatusPill status={run.email_status || "pending"} /></div>
              
              {/* 0-article warning */}
              {run.fetched_count === 0 && (
                <div style={{ padding: "10px 12px", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.25)", borderRadius: "6px", color: "#f59e0b", fontSize: "12px" }}>
                  ⚠️ <strong>0 articles fetched</strong> — No articles with sector <code style={{ background: "rgba(0,0,0,0.2)", padding: "1px 5px", borderRadius: "3px" }}>{company.sector_match}</code> found in the local database within the time window. Articles are only present if a scrape job has been run for this sector.
                </div>
              )}

              <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", margin: "4px 0" }}>
                {run.master_doc_path && (
                  <button
                    onClick={() => handleDownloadReport(run.master_doc_path)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      background: "var(--nav-active)",
                      border: "1px solid var(--nav-active-border)",
                      padding: "6px 12px",
                      borderRadius: "6px",
                      color: "var(--accent)",
                      cursor: "pointer",
                      fontWeight: 600
                    }}
                  >
                    📄 Google Report
                  </button>
                )}
                {run.master_excel_path && (
                  <button
                    onClick={() => handleDownloadReport(run.master_excel_path)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      background: "var(--nav-active)",
                      border: "1px solid var(--nav-active-border)",
                      padding: "6px 12px",
                      borderRadius: "6px",
                      color: "var(--accent)",
                      cursor: "pointer",
                      fontWeight: 600
                    }}
                  >
                    📊 Google Report (Excel)
                  </button>
                )}
                {run.mailer_doc_path && (
                  <button
                    onClick={() => handleDownloadReport(run.mailer_doc_path)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      background: "rgba(66,133,244,0.12)",
                      border: "1px solid rgba(66,133,244,0.35)",
                      padding: "6px 12px",
                      borderRadius: "6px",
                      color: "#4285F4",
                      cursor: "pointer",
                      fontWeight: 600
                    }}
                  >
                    📧 Download Mailer Doc
                  </button>
                )}
                {run.google_doc_url && (
                  <a
                    href={run.google_doc_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      background: "rgba(52,168,83,0.12)",
                      border: "1px solid rgba(52,168,83,0.35)",
                      padding: "6px 12px",
                      borderRadius: "6px",
                      color: "#34A853",
                      cursor: "pointer",
                      fontWeight: 600,
                      textDecoration: "none",
                      fontSize: "13px"
                    }}
                  >
                    🔗 Open Mailer Google Doc
                  </a>
                )}
              </div>

              {/* Progress parser & dynamic loader */}
              {(() => {
                const pInfo = parseHeavyProgressLog(run.progress_message, run.started_at, run.finished_at, run.status, company.llm_judge_enabled);
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px", margin: "8px 0" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: "700", color: "var(--muted)" }}>
                      <span>Run Progress</span>
                      <span>{pInfo.progress}%</span>
                    </div>
                    <div style={{ width: "100%", height: "6px", background: "rgba(255,255,255,0.05)", border: "1px solid var(--border)", borderRadius: "100px", overflow: "hidden" }}>
                      <div style={{ width: `${pInfo.progress}%`, height: "100%", background: run.status === "completed" ? "linear-gradient(90deg, #22c55e 0%, #4ade80 100%)" : run.status === "failed" ? "linear-gradient(90deg, #ef4444 0%, #f87171 100%)" : "linear-gradient(90deg, var(--accent) 0%, #a855f7 100%)", transition: "width 0.4s ease-out" }} />
                    </div>

                    {/* Sequential step loaders */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "8px" }}>
                      {pInfo.steps.map(s => {
                        const isCompleted = s.status === "completed";
                        const isRunning = s.status === "running";
                        const isFailed = s.status === "failed";
                        
                        const icon = isCompleted ? "✓" : isRunning ? "⚡" : isFailed ? "✗" : "○";
                        const color = isCompleted ? "#22c55e" : isRunning ? "var(--accent)" : isFailed ? "#ef4444" : "var(--muted)";
                        
                        return (
                          <div key={s.key} style={{ display: "flex", alignItems: "center", gap: "8px", color }}>
                            <span style={{ fontWeight: "700" }}>{icon}</span>
                            <span style={{ fontSize: "12px", fontWeight: isRunning ? "700" : "500" }}>{s.label}</span>
                          </div>
                        );
                      })}
                    </div>

                    {/* Console trace window */}
                    {pInfo.lines && (
                      <div style={{ background: "#0b0c10", border: "1px solid var(--nav-active-border)", borderRadius: "8px", overflow: "hidden", marginTop: "12px" }}>
                        <div style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid rgba(255,255,255,0.05)", padding: "6px 12px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                          <div style={{ display: "flex", gap: "6px" }}>
                            <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#ef4444", display: "inline-block" }}></span>
                            <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#eab308", display: "inline-block" }}></span>
                            <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#22c55e", display: "inline-block" }}></span>
                          </div>
                          <span style={{ fontSize: "9px", fontFamily: "monospace", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", fontWeight: "700" }}>Trace Log</span>
                        </div>
                        <div style={{ margin: 0, padding: "10px", fontSize: "11px", color: "#34d399", fontFamily: "monospace", overflowX: "auto", maxHeight: "250px", overflowY: "auto", textAlign: "left", display: "flex", flexDirection: "column", gap: "6px" }}>
                          {pInfo.lines.split("\n").map((line, lIdx) => {
                            if (line.includes("Downloadable output:")) {
                              const parts = line.split("Downloadable output:");
                              const textPart = parts[0].trim();
                              const pathPart = parts[1].trim();
                              const filename = pathPart.split("/").pop();
                              return (
                                <div key={lIdx} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", borderBottom: "1px dashed rgba(52,211,153,0.15)", paddingBottom: "4px" }}>
                                  <span>{textPart}</span>
                                  <button
                                    onClick={() => handleDownloadReport(filename)}
                                    style={{
                                      background: "rgba(52,211,153,0.15)",
                                      border: "1px solid rgba(52,211,153,0.45)",
                                      color: "#34d399",
                                      padding: "2px 8px",
                                      borderRadius: "4px",
                                      fontSize: "10px",
                                      cursor: "pointer",
                                      fontWeight: "700"
                                    }}
                                  >
                                    📥 Download
                                  </button>
                                </div>
                              );
                            }
                            return <div key={lIdx} style={{ whiteSpace: "pre-wrap" }}>{line}</div>;
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
              
              {run.started_at && <div><strong>Started:</strong> {new Date(run.started_at).toLocaleString()}</div>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function CompanySettings({ company, availableSectors, onSave, onDelete, onRunNow }) {
  const [form, setForm] = useState(company);
  const [tab, setTab] = useState("schedule");
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    setForm(company);
  }, [company]);

  const set = (key, val) => setForm(p => ({ ...p, [key]: val }));

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { ...form, days: (form.days && form.days.length) ? form.days : null };
      await updateCompany(company.id, payload);
      onSave(payload);
    } catch (e) {
      alert("Save failed: " + (e?.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  const handleRunNow = async () => {
    setRunning(true);
    try {
      await triggerRun(company.id);
      onRunNow();
    } catch (e) {
      alert("Run failed: " + (e?.response?.data?.detail || e.message));
    } finally {
      setRunning(false);
    }
  };

  const handleSectorCheckboxChange = (sector, checked) => {
    const currentSectors = form.sector_match ? form.sector_match.split(',').map(s => s.trim()).filter(Boolean) : [];
    let newSectors;
    if (checked) {
      newSectors = [...currentSectors, sector];
    } else {
      newSectors = currentSectors.filter(s => s !== sector);
    }
    set("sector_match", newSectors.join(','));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: "16px" }}>
      {/* Tab bar */}
      <div style={{ display: "flex", gap: "12px", borderBottom: "1px solid var(--border)", paddingBottom: "12px" }}>
        {["schedule", "relevancy", "recipients", "history"].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "8px 16px", background: "none", border: "none", borderBottom: tab === t ? "2px solid var(--accent)" : "none", cursor: "pointer", fontWeight: 700, color: tab === t ? "var(--accent)" : "var(--muted)", fontSize: "13px", textTransform: "uppercase"
          }}>{t}</button>
        ))}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {tab === "schedule" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Automation Status</label>
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                background: form.enabled ? "rgba(16, 185, 129, 0.05)" : "rgba(239, 68, 68, 0.05)",
                border: form.enabled ? "1px solid rgba(16, 185, 129, 0.2)" : "1px solid rgba(239, 68, 68, 0.2)",
                borderRadius: "8px",
                padding: "12px",
                transition: "all 0.2s ease"
              }}>
                <input
                  type="checkbox"
                  id="enabled"
                  checked={form.enabled ?? true}
                  onChange={e => set("enabled", e.target.checked)}
                  style={{ width: "16px", height: "16px", cursor: "pointer" }}
                />
                <label htmlFor="enabled" style={{ fontSize: "13px", fontWeight: "700", cursor: "pointer", flex: 1, color: form.enabled ? "var(--success)" : "var(--danger)" }}>
                  {form.enabled ? "✓ Automation Active" : "✗ Automation Disabled (Paused)"}
                </label>
              </div>
            </div>

            <div style={{ display: "flex", gap: "16px" }}>
              <div>
                <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Fetch Time</label>
                <input type="time" value={form.fetch_time} onChange={e => set("fetch_time", e.target.value)} style={{ width: "160px", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} />
              </div>
              <div>
                <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Time Range (Hours)</label>
                <input type="number" min="1" max="720" value={form.window_hours} onChange={e => set("window_hours", parseInt(e.target.value) || 24)} style={{ width: "120px", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} />
              </div>
            </div>
            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Timezone</label>
              <select value={form.timezone} onChange={e => set("timezone", e.target.value)} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }}>
                {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Frequency</label>
              <select value={form.frequency} onChange={e => set("frequency", e.target.value)} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }}>
                {["Daily", "Weekly", "Monthly"].map(f => <option key={f}>{f}</option>)}
              </select>
            </div>
            {form.frequency !== "Daily" && (
              <div>
                <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>{form.frequency === "Monthly" ? "Days" : "Weekdays"}</label>
                <DaySelector frequency={form.frequency} days={form.days} onChange={v => set("days", v)} />
              </div>
            )}
            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Send Mode</label>
              <select value={form.mail_send_mode} onChange={e => set("mail_send_mode", e.target.value)} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }}>
                <option value="Immediate">Immediate</option>
                <option value="Scheduled">Scheduled</option>
              </select>
            </div>
            {form.mail_send_mode === "Scheduled" && (
              <div>
                <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Send At</label>
                <input type="time" value={form.mail_send_time || "08:00"} onChange={e => set("mail_send_time", e.target.value)} style={{ width: "160px", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} />
              </div>
            )}
          </div>
        )}

        {tab === "relevancy" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Sectors Selection</label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: "8px", maxHeight: "150px", overflowY: "auto", border: "1px solid var(--border)", borderRadius: "6px", padding: "10px", background: "rgba(0,0,0,0.1)" }}>
                {availableSectors.map(s => (
                  <label key={s} style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px" }}>
                    <input
                      type="checkbox"
                      checked={form.sector_match ? form.sector_match.split(',').map(x => x.trim()).includes(s) : false}
                      onChange={e => handleSectorCheckboxChange(s, e.target.checked)}
                    />
                    <span>{s}</span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Search Scope</label>
              <div style={{ display: "flex", gap: "16px", background: "rgba(30, 58, 95, 0.03)", border: "1px solid var(--border)", borderRadius: "6px", padding: "12px" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px", fontWeight: 600 }}>
                  <input
                    type="radio"
                    name="search_mode"
                    value="title"
                    checked={form.search_mode !== "full_body"}
                    onChange={() => set("search_mode", "title")}
                  />
                  <span>Only Title Search</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px", fontWeight: 600 }}>
                  <input
                    type="radio"
                    name="search_mode"
                    value="full_body"
                    checked={form.search_mode === "full_body"}
                    onChange={() => set("search_mode", "full_body")}
                  />
                  <span>Full Body Search</span>
                </label>
              </div>
            </div>

            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Pipeline Rules & Logic</label>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(147, 51, 234, 0.05)", border: "1px solid rgba(147, 51, 234, 0.2)", borderRadius: "8px", padding: "12px" }}>
                  <input
                    type="checkbox"
                    id="llm_judge_enabled"
                    checked={form.llm_judge_enabled ?? false}
                    onChange={e => set("llm_judge_enabled", e.target.checked)}
                    style={{ width: "16px", height: "16px" }}
                  />
                  <label htmlFor="llm_judge_enabled" style={{ fontSize: "13px", fontWeight: "700", cursor: "pointer", flex: 1 }}>
                    Enable LLM Judge (Pass ambiguous articles through AI verification)
                  </label>
                </div>
                
                <div style={{ display: "flex", alignItems: "center", gap: "8px", background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.2)", borderRadius: "8px", padding: "12px" }}>
                  <input
                    type="checkbox"
                    id="pooja_folder_filtering_enabled"
                    checked={form.pooja_folder_filtering_enabled ?? false}
                    onChange={e => set("pooja_folder_filtering_enabled", e.target.checked)}
                    style={{ width: "16px", height: "16px" }}
                  />
                  <label htmlFor="pooja_folder_filtering_enabled" style={{ fontSize: "13px", fontWeight: "700", cursor: "pointer", flex: 1 }}>
                    Enable Pooja Folder Filtering Logic (Priority media + keywords.xlsx from folder)
                  </label>
                </div>
                
                <div style={{ display: "flex", alignItems: "flex-start", gap: "8px", background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.2)", borderRadius: "8px", padding: "12px" }}>
                  <input
                    type="checkbox"
                    id="pooja_algo_enabled"
                    checked={form.pooja_algo_enabled ?? false}
                    onChange={e => set("pooja_algo_enabled", e.target.checked)}
                    style={{ width: "16px", height: "16px", marginTop: "3px" }}
                  />
                  <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
                    <label htmlFor="pooja_algo_enabled" style={{ fontSize: "13px", fontWeight: "700", cursor: "pointer" }}>
                      Enable Pooja Algo
                    </label>
                    <span style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px", lineHeight: "1.4" }}>
                      <strong>Info Tag:</strong> First filters all fetched articles to keep only priority publication matches (dropping non-priority sources). Then, runs the keyword matching/scoring logic on those priority survivors.
                    </span>
                    
                    {form.pooja_algo_enabled && (
                      <div style={{ display: "flex", gap: "16px", marginTop: "12px", background: "rgba(255,255,255,0.6)", padding: "10px", borderRadius: "6px", border: "1px dashed rgba(16, 185, 129, 0.3)" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <label htmlFor="pooja_priority_conf" style={{ fontSize: "11px", fontWeight: "600", color: "var(--muted)" }}>
                            Priority Media Threshold (0-10)
                          </label>
                          <input
                            type="number"
                            id="pooja_priority_conf"
                            min="0"
                            max="10"
                            value={form.pooja_priority_conf ?? 5}
                            onChange={e => set("pooja_priority_conf", parseInt(e.target.value) || 0)}
                            style={{ width: "80px", padding: "4px 8px", border: "1px solid var(--border)", borderRadius: "4px", fontSize: "12px" }}
                          />
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                          <label htmlFor="pooja_non_priority_conf" style={{ fontSize: "11px", fontWeight: "600", color: "var(--muted)" }}>
                            Non-Priority Threshold (0-10)
                          </label>
                          <input
                            type="number"
                            id="pooja_non_priority_conf"
                            min="0"
                            max="10"
                            value={form.pooja_non_priority_conf ?? 7}
                            onChange={e => set("pooja_non_priority_conf", parseInt(e.target.value) || 0)}
                            style={{ width: "80px", padding: "4px 8px", border: "1px solid var(--border)", borderRadius: "4px", fontSize: "12px" }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>AI Context (optional)</label>
              <textarea value={form.relevance_context} onChange={e => set("relevance_context", e.target.value)} placeholder="e.g. India-focused news" style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", minHeight: "80px", fontFamily: "inherit" }} />
            </div>
          </div>
        )}

        {tab === "recipients" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "8px", color: "var(--muted)" }}>Send Configurations</label>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", background: "rgba(30, 58, 95, 0.03)", border: "1px solid var(--border)", borderRadius: "8px", padding: "14px", marginBottom: "8px" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "13px", fontWeight: "600" }}>
                  <input
                    type="checkbox"
                    checked={form.email_send_reports ?? true}
                    onChange={e => set("email_send_reports", e.target.checked)}
                    style={{ width: "16px", height: "16px" }}
                  />
                  <span>Send Reports (Attach Word & Excel Briefings)</span>
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "13px", fontWeight: "600" }}>
                  <input
                    type="checkbox"
                    checked={form.email_send_html ?? false}
                    onChange={e => set("email_send_html", e.target.checked)}
                    style={{ width: "16px", height: "16px" }}
                  />
                  <span>Send HTML Mailer (Inline Email Briefing)</span>
                </label>
              </div>
            </div>

            <div>
              <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "12px", color: "var(--muted)" }}>Email Recipients</label>
              {(form.recipients || []).map((r, i) => (
                <RecipientItem key={i} email={r.email} onRemove={() => set("recipients", form.recipients.filter((_, j) => j !== i))} />
              ))}
              <AddRecipientForm onAdd={email => set("recipients", [...(form.recipients || []), { email, role: "master_doc" }])} />
            </div>
          </div>
        )}

        {tab === "history" && (
          <RunHistory company={company} />
        )}
      </div>

      {/* Action buttons */}
      <div style={{ display: "flex", gap: "8px", borderTop: "1px solid var(--border)", paddingTop: "16px" }}>
        <button onClick={handleSave} disabled={saving} style={{ flex: 1, padding: "10px 16px", background: "var(--accent)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700, opacity: saving ? 0.6 : 1 }}>{saving ? "Saving..." : "Save"}</button>
        <button onClick={handleRunNow} disabled={running} style={{ flex: 1, padding: "10px 16px", background: "var(--success)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700, opacity: running ? 0.6 : 1 }}>{running ? "Running..." : "Run Now"}</button>
        <button onClick={onDelete} style={{ padding: "10px 16px", background: "rgba(239,68,68,.1)", color: "var(--danger)", border: "1px solid rgba(239,68,68,.3)", borderRadius: "6px", cursor: "pointer", fontWeight: 700 }}>Delete</button>
      </div>
    </div>
  );
}

function BackupStatus() {
  const [backup, setBackup] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const check = async () => {
      if (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
        setLoading(false);
        return;
      }
      try {
        const baseUrl = import.meta.env.VITE_NEXUS_BASE_URL || "http://35.240.197.209";
        const response = await fetch(`${baseUrl}/api/backup-status`, { headers: { "X-Service-Key": "nexus_sk_fb74eaae34cd3e53f6ac2031479337cb" } });
        if (response.ok) {
          const data = await response.json();
          setBackup(data);
        }
      } catch (e) {
        console.error("Backup check failed:", e);
      } finally {
        setLoading(false);
      }
    };
    check();
    const interval = setInterval(check, 300000); // Check every 5 minutes
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div style={{ padding: "12px", background: "var(--surface2)", color: "var(--muted)", borderRadius: "6px", fontSize: "12px" }}>Backup status: checking...</div>;
  if (!backup) return null;

  const age = (Date.now() - new Date(backup.last_backup).getTime()) / (1000 * 3600 * 24);
  const isStale = age > 1;

  return (
    <div style={{ padding: "12px", background: isStale ? "rgba(239,68,68,.1)" : "rgba(16,185,129,.1)", color: isStale ? "var(--danger)" : "var(--success)", borderRadius: "6px", fontSize: "12px" }}>
      <strong>Database Backup:</strong> {backup.last_backup ? new Date(backup.last_backup).toLocaleDateString() : "Unknown"} ({isStale ? "⚠ Stale" : "✓ Current"})
    </div>
  );
}

function NexusStatsPanel() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get("/heavy-automation/nexus-stats");
      setStats(data);
    } catch (e) {
      console.error("Failed to load nexus stats:", e);
      setError(e.message || "Connection failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  if (loading) {
    return (
      <div style={{ padding: "40px", textAlign: "center", color: "var(--muted)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "12px" }}>
        <div style={{ width: "24px", height: "24px", border: "2px solid rgba(255,255,255,.1)", borderTopColor: "var(--accent)", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        <span>Loading production database intelligence...</span>
        <span style={{ fontSize: "11px", color: "var(--muted)", opacity: 0.6 }}>Querying Nexus feed across all sectors — may take 10–20s</span>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div style={{ padding: "40px", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: "16px" }}>
        <div style={{ fontSize: "28px" }}>⚠️</div>
        <div style={{ color: "var(--danger)", fontWeight: 700, fontSize: "14px" }}>Failed to load database statistics</div>
        <div style={{ color: "var(--muted)", fontSize: "12px", maxWidth: "280px" }}>{error || "Could not reach the Nexus production server. Check your connection."}</div>
        <button
          onClick={loadStats}
          style={{ padding: "8px 20px", background: "var(--accent)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700, fontSize: "13px" }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px", height: "100%", overflowY: "auto" }}>
      <div>
        <h2 style={{ fontSize: "18px", fontWeight: 700, margin: "0 0 4px 0", color: "var(--text)" }}>NEXUS Database Intelligence</h2>
        <p style={{ fontSize: "13px", color: "var(--muted)", margin: 0 }}>Real-time statistics of the polled intelligence database feed.</p>
      </div>

      {/* Main total metric */}
      <div style={{
        background: "linear-gradient(135deg, var(--nav-active) 0%, var(--surface2) 100%)",
        border: "1px solid var(--nav-active-border)",
        borderRadius: "12px",
        padding: "20px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between"
      }}>
        <div>
          <div style={{ fontSize: "11px", fontWeight: 700, textTransform: "uppercase", color: "var(--muted)", letterSpacing: "1px" }}>Total Articles Available</div>
          <div style={{ fontSize: "36px", fontWeight: 800, color: "var(--text)", marginTop: "4px" }}>
            {stats.total_articles ? stats.total_articles.toLocaleString() : 0}
          </div>
        </div>
        <div style={{ fontSize: "36px" }}>📊</div>
      </div>

      {/* Table grid */}
      <div>
        <h3 style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", color: "var(--muted)", letterSpacing: "0.5px", marginBottom: "12px" }}>Breakdown by Sector</h3>
        <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--surface)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", background: "rgba(0,0,0,0.02)" }}>
                <th style={{ textAlign: "left", padding: "12px 16px", color: "var(--muted)", fontWeight: 700 }}>Sector</th>
                <th style={{ textAlign: "right", padding: "12px 16px", color: "var(--muted)", fontWeight: 700 }}>Last 24 Hours</th>
                <th style={{ textAlign: "right", padding: "12px 16px", color: "var(--muted)", fontWeight: 700 }}>All-Time</th>
              </tr>
            </thead>
            <tbody>
              {stats.sector_stats && stats.sector_stats.map((row, idx) => (
                <tr key={row.sector} style={{ borderBottom: idx === stats.sector_stats.length - 1 ? "none" : "1px solid var(--border)", background: idx % 2 === 0 ? "transparent" : "rgba(0,0,0,0.01)" }}>
                  <td style={{ padding: "12px 16px", fontWeight: 600, textTransform: "capitalize", color: "var(--text)" }}>{row.sector}</td>
                  <td style={{ padding: "12px 16px", textAlign: "right", color: "var(--accent)", fontWeight: 700 }}>{row.count_24h ? row.count_24h.toLocaleString() : 0}</td>
                  <td style={{ padding: "12px 16px", textAlign: "right", color: "var(--muted)" }}>{row.count_all ? row.count_all.toLocaleString() : 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function HeavyAutomation() {
  const [companies, setCompanies] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [availableSectors, setAvailableSectors] = useState([]);

  const loadCompanies = async () => {
    setLoading(true);
    try {
      const data = await fetchCompanies();
      setCompanies(data || []);
    } catch (e) {
      console.error("Failed to load companies:", e);
    } finally {
      setLoading(false);
    }
  };

  const loadSectors = async () => {
    try {
      // Use Nexus sectors (includes google, ai, healthcare, etc.) for Heavy Automation
      const resp = await api.get("/heavy-automation/nexus-sectors");
      if (resp && resp.sectors) {
        setAvailableSectors(resp.sectors);
      }
    } catch (e) {
      console.error("Failed to load sectors:", e);
      // Fallback to hardcoded Nexus sectors
      setAvailableSectors(['ai', 'consultancies', 'foods and drinks', 'google', 'healthcare', 'lifestyle', 'policies', 'real estate', 'startups', 'stock market', 'tech', 'travel']);
    }
  };

  useEffect(() => { 
    loadCompanies();
    loadSectors();
  }, []);

  const handleCreate = async (form) => {
    try {
      const created = await createCompany(form);
      setCompanies([...companies, created]);
      setSelected(created);
      setShowForm(false);
    } catch (e) {
      alert("Create failed: " + (e?.response?.data?.detail || e.message));
    }
  };

  return (
    <div>
      <header className="page-header" style={{ marginBottom: "32px" }}>
        <h1 className="page-title">Heavy Automation</h1>
        <p className="page-subtitle">Intelligent News Intelligence Briefings</p>
        <div style={{ marginTop: "16px" }}>
          <BackupStatus />
        </div>
      </header>

      <div style={{ display: "flex", gap: "24px", height: "calc(100vh - 200px)" }}>
        {/* Companies list */}
        <div style={{ width: "280px", display: "flex", flexDirection: "column", gap: "12px" }}>
          <button onClick={() => setShowForm(!showForm)} style={{ padding: "10px 16px", background: "var(--accent)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700 }}>+ Add Company</button>
          <div style={{ flex: 1, overflowY: "auto", border: "1px solid var(--border)", borderRadius: "6px" }}>
            {loading ? (
              <div style={{ padding: "16px", color: "var(--muted)" }}>Loading...</div>
            ) : companies.length === 0 ? (
              <div style={{ padding: "16px", color: "var(--muted)" }}>No companies. Create one to start.</div>
            ) : (
              companies.map(c => (
                <div key={c.id} onClick={() => setSelected(c)} style={{
                  padding: "12px 16px", borderBottom: "1px solid var(--border)", cursor: "pointer",
                  background: selected?.id === c.id ? "var(--nav-active)" : "transparent",
                  borderLeft: selected?.id === c.id ? "3px solid var(--accent)" : "3px solid transparent",
                  opacity: c.enabled ? 1 : 0.75
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div style={{ fontWeight: 700, fontSize: "13px", color: c.enabled ? "var(--text)" : "var(--muted)" }}>{c.name}</div>
                    {!c.enabled && (
                      <span style={{ fontSize: "9px", fontWeight: 700, padding: "2px 6px", background: "rgba(239, 68, 68, 0.1)", color: "var(--danger)", borderRadius: "10px", textTransform: "uppercase" }}>Paused</span>
                    )}
                  </div>
                  <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>{c.sector_match}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Settings panel */}
        <div style={{ flex: 1, border: "1px solid var(--border)", borderRadius: "6px", padding: "20px", background: "var(--surface)" }}>
          {showForm ? (
            <NewCompanyForm availableSectors={availableSectors} onCreated={handleCreate} onCancel={() => setShowForm(false)} />
          ) : selected ? (
            <CompanySettings
              company={selected}
              availableSectors={availableSectors}
              onSave={updated => setSelected(updated)}
              onDelete={async () => { await deleteCompany(selected.id); setCompanies(companies.filter(c => c.id !== selected.id)); setSelected(null); }}
              onRunNow={() => loadCompanies()}
            />
          ) : (
            <NexusStatsPanel />
          )}
        </div>
      </div>
    </div>
  );
}

function NewCompanyForm({ availableSectors, onCreated, onCancel }) {
  const [form, setForm] = useState(DEFAULT_COMPANY);
  const [creating, setCreating] = useState(false);

  const set = (key, val) => setForm(p => ({ ...p, [key]: val }));

  const handleSubmit = async () => {
    if (!form.name.trim()) return alert("Company name required");
    if (!form.sector_match) return alert("Select at least one sector");
    setCreating(true);
    try {
      await onCreated(form);
    } finally {
      setCreating(false);
    }
  };

  const handleSectorCheckboxChange = (sector, checked) => {
    const currentSectors = form.sector_match ? form.sector_match.split(',').map(s => s.trim()).filter(Boolean) : [];
    let newSectors;
    if (checked) {
      newSectors = [...currentSectors, sector];
    } else {
      newSectors = currentSectors.filter(s => s !== sector);
    }
    set("sector_match", newSectors.join(','));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      <h3 style={{ fontSize: "16px", fontWeight: 700 }}>New Company</h3>
      <div>
        <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Company Name</label>
        <input value={form.name} onChange={e => set("name", e.target.value)} placeholder="e.g. Google India" style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", fontSize: "13px" }} />
      </div>
      <div>
        <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Time Range (Hours)</label>
        <input type="number" min="1" max="720" value={form.window_hours} onChange={e => set("window_hours", parseInt(e.target.value) || 24)} style={{ width: "100px", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} />
      </div>
      <div>
        <label style={{ fontSize: "12px", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px", color: "var(--muted)" }}>Sectors Selection</label>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: "8px", maxHeight: "150px", overflowY: "auto", border: "1px solid var(--border)", borderRadius: "6px", padding: "10px", background: "rgba(0,0,0,0.1)" }}>
          {availableSectors.map(s => (
            <label key={s} style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", fontSize: "13px" }}>
              <input
                type="checkbox"
                checked={form.sector_match ? form.sector_match.split(',').map(x => x.trim()).includes(s) : false}
                onChange={e => handleSectorCheckboxChange(s, e.target.checked)}
              />
              <span>{s}</span>
            </label>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", gap: "8px" }}>
        <button onClick={handleSubmit} disabled={creating} style={{ flex: 1, padding: "10px", background: "var(--accent)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700 }}>{creating ? "Creating..." : "Create"}</button>
        <button onClick={onCancel} style={{ flex: 1, padding: "10px", background: "transparent", color: "var(--muted)", border: "1px solid var(--border)", borderRadius: "6px", cursor: "pointer", fontWeight: 700 }}>Cancel</button>
      </div>
    </div>
  );
}
