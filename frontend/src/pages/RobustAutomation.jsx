import { useState, useEffect, useRef } from "react";
import apiClient, { api } from "../services/api";

const BASE = "/robust-automation";
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
  
  // File uploads metadata
  keywords_file_name: "",
  priority_media_file_name: "",
  manual_keywords: "",

  // Output toggles
  send_email: true,
  send_html_mailer: true,
  send_mailer_doc: true,
  send_report_doc: true,
  send_report_excel: true,
  upload_to_google_drive: false,
  update_takeaways_sheet: false,

  // LLM Providers
  llm_verification_provider: "none",
  llm_summary_provider: "none",
  llm_executive_provider: "none",

  // Schedulers
  mail_send_mode: "Immediate",
  mail_send_time: "08:00",
  frequency: "Daily",
  days: [],
  
  // Takeaways
  takeaways_sheet_url: "",
  send_monthly_takeaways_enabled: false,
  monthly_takeaways_day: 1,
  monthly_takeaways_time: "09:00",
  search_mode: "title",
  pooja_algo_enabled: true,
  verification_doc_filename: "",
  verification_doc_text: "",
  verification_system_prompt: "",
  verification_user_prompt: "",
  summary_user_prompt: "",
  executive_user_prompt: "",

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
async function uploadSupportingDoc(id, file) {
  const data = new FormData();
  data.append("file", file);
  return await api.post(`${BASE}/companies/${id}/upload-doc`, data);
}
async function deleteSupportingDoc(id) { return await api.delete(`${BASE}/companies/${id}/doc`); }
async function fetchPromptHistory(id) { return await api.get(`${BASE}/companies/${id}/prompt-history`); }
async function restorePromptVersion(id, historyId) { return await api.post(`${BASE}/companies/${id}/restore-prompt`, { history_id: historyId }); }

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

function RecipientItem({ email, role, onRemove }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "rgba(30,58,95,.15)", borderRadius: "6px", border: "1px solid rgba(30,58,95,.3)", marginBottom: "6px" }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: "13px", fontWeight: 600 }}>{email}</div>
        <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>Role: <span style={{ fontWeight: 700, color: "var(--accent)", textTransform: "uppercase" }}>{role}</span></div>
      </div>
      <button onClick={onRemove} style={{ background: "none", border: "none", color: "var(--danger)", cursor: "pointer", fontSize: "18px", padding: "0 8px" }}>×</button>
    </div>
  );
}

function AddRecipientForm({ onAdd }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("brief");
  const add = () => {
    if (!email.trim()) return;
    onAdd(email, role);
    setEmail("");
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "12px", padding: "12px", border: "1px dashed var(--border)", borderRadius: "6px" }}>
      <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--muted)", textTransform: "uppercase" }}>Add New Recipient</div>
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        <input type="email" placeholder="email@example.com" value={email} onChange={e => setEmail(e.target.value)} style={{ flex: 1, minWidth: "150px", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", fontSize: "13px" }} />
        <select value={role} onChange={e => setRole(e.target.value)} style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", fontSize: "13px", background: "var(--surface)" }}>
          <option value="brief">Daily Brief</option>
          <option value="master_doc">Master Doc / Excel</option>
        </select>
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

function parseRobustProgressLog(progressMessage, startedAt, completedAt, status, verifyLlm, summaryLlm, execLlm) {
  if (!progressMessage) {
    return { progress: 0, steps: [], lines: "" };
  }
  
  const lines = progressMessage.split("\n").map(l => l.trim()).filter(Boolean);
  
  const steps = [
    { key: "fetch", label: "Polling articles from production feed", status: "pending" },
    { key: "dedup", label: "Exact & TF-IDF Deduplication", status: "pending" },
  ];
  if (verifyLlm !== "none") {
    steps.push({ key: "verify", label: "LLM Keyword Verification", status: "pending" });
  }
  if (summaryLlm !== "none") {
    steps.push({ key: "summary", label: "LLM Summary Generation", status: "pending" });
  }
  if (execLlm !== "none") {
    steps.push({ key: "exec", label: "LLM Executive Synthesis", status: "pending" });
  }
  steps.push(
    { key: "report", label: "Compiling doc & excel reports", status: "pending" },
    { key: "email", label: "Dispatching reports via email", status: "pending" }
  );
  
  let activeIndex = -1;
  
  for (const line of lines) {
    if (line.includes("Polling articles")) {
      activeIndex = 0;
    } else if (line.includes("Exact deduplication") || line.includes("Near-duplicate")) {
      activeIndex = 1;
    } else if (line.includes("Validating article relevance")) {
      activeIndex = verifyLlm !== "none" ? 2 : 1;
    } else if (line.includes("Generating article summaries")) {
      let offset = 2;
      if (verifyLlm !== "none") offset += 1;
      activeIndex = offset;
    } else if (line.includes("Generating Executive Summary")) {
      let offset = 2;
      if (verifyLlm !== "none") offset += 1;
      if (summaryLlm !== "none") offset += 1;
      activeIndex = offset;
    } else if (line.includes("Compiling reports")) {
      let offset = 2;
      if (verifyLlm !== "none") offset += 1;
      if (summaryLlm !== "none") offset += 1;
      if (execLlm !== "none") offset += 1;
      activeIndex = offset;
    } else if (line.includes("Sending daily news email") || line.includes("Email scheduled")) {
      let offset = 3;
      if (verifyLlm !== "none") offset += 1;
      if (summaryLlm !== "none") offset += 1;
      if (execLlm !== "none") offset += 1;
      activeIndex = offset;
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
  
  const completedCount = steps.filter(s => s.status === "completed").length;
  const progress = steps.length ? Math.round((completedCount / steps.length) * 100) : 0;
  
  return { progress, steps, lines: progressMessage };
}

export default function RobustAutomation() {
  const [companies, setCompanies] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [formData, setFormData] = useState(DEFAULT_COMPANY);
  const [activeTab, setActiveTab] = useState("general");
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [runArticles, setRunArticles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [expandedRunId, setExpandedRunId] = useState(null);
  const expandedInitRef = useRef(false);
  const [showArticlesModal, setShowArticlesModal] = useState(false);
  const [fileUploading, setFileUploading] = useState({ keywords: false, media: false });
  const [availableSectors, setAvailableSectors] = useState([]);
  
  // Prompt History & Supporting Doc states
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [historyItems, setHistoryItems] = useState([]);
  const [historyStageFilter, setHistoryStageFilter] = useState("all");
  const [docUploading, setDocUploading] = useState(false);
  const [showDocPreview, setShowDocPreview] = useState(false);
  const [showPdfModal, setShowPdfModal] = useState(false);

  const handleUploadDoc = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!selectedCompany?.id) {
      alert("Please save or select a company configuration first.");
      return;
    }
    setDocUploading(true);
    try {
      const updated = await uploadSupportingDoc(selectedCompany.id, file);
      setFormData(updated);
      setSelectedCompany(updated);
      setCompanies(companies.map(c => c.id === updated.id ? updated : c));
      alert(`Supporting document '${file.name}' attached and parsed successfully!`);
    } catch (err) {
      console.error(err);
      alert("Failed to upload document: " + (err.response?.data?.detail || err.message));
    } finally {
      setDocUploading(false);
    }
  };

  const handleDeleteDoc = async () => {
    if (!selectedCompany?.id) return;
    if (!confirm("Are you sure you want to remove the supporting document?")) return;
    try {
      const updated = await deleteSupportingDoc(selectedCompany.id);
      setFormData(updated);
      setSelectedCompany(updated);
      setCompanies(companies.map(c => c.id === updated.id ? updated : c));
    } catch (err) {
      console.error(err);
      alert("Failed to remove document: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleOpenPromptHistory = async () => {
    if (!selectedCompany?.id) {
      alert("Please save or select a company configuration first.");
      return;
    }
    try {
      const res = await fetchPromptHistory(selectedCompany.id);
      setHistoryItems(res || []);
      setShowHistoryModal(true);
    } catch (err) {
      console.error(err);
      alert("Failed to fetch prompt history: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleRestorePrompt = async (historyId) => {
    if (!selectedCompany?.id) return;
    if (!confirm("Restore this historical prompt version into your active configuration?")) return;
    try {
      const updated = await restorePromptVersion(selectedCompany.id, historyId);
      setFormData(updated);
      setSelectedCompany(updated);
      setCompanies(companies.map(c => c.id === updated.id ? updated : c));
      setShowHistoryModal(false);
      alert("Prompt version restored successfully!");
    } catch (err) {
      console.error(err);
      alert("Failed to restore prompt version: " + (err.response?.data?.detail || err.message));
    }
  };

  const runsTimerRef = useRef(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await fetchCompanies();
      setCompanies(res);
      if (res && res.length > 0 && !selectedCompany) {
        handleSelectCompany(res[0]);
      }
      const sectorsRes = await api.get(`${BASE}/nexus-sectors`);
      setAvailableSectors(sectorsRes.sectors || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadReport = async (filename) => {
    try {
      const name = filename.split(/[/\\]/).pop();
      const response = await apiClient.get(`robust-automation/reports/${name}`, {
        responseType: "blob"
      });
      const blob = response instanceof Blob ? response : new Blob([response]);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download file", err);
      alert("Failed to download report: " + err.message);
    }
  };

  useEffect(() => {
    loadData();
    return () => clearInterval(runsTimerRef.current);
  }, []);

  const handleSelectCompany = async (company) => {
    setSelectedCompany(company);
    setFormData({
      ...DEFAULT_COMPANY,
      ...company,
    });
    setRuns([]);
    setSelectedRun(null);
    expandedInitRef.current = false;
    setExpandedRunId(null);
    clearInterval(runsTimerRef.current);
    
    // Fetch runs for the selected company
    try {
      const runRes = await fetchRuns(company.id);
      setRuns(runRes);
      if (runRes && runRes.length > 0) {
        setExpandedRunId(runRes[0].id);
        expandedInitRef.current = true;
      }
      
      // Auto-poll runs status if any is running
      const isAnyRunning = runRes.some(r => r.status === "running");
      if (isAnyRunning) {
        startPollingRuns(company.id);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const startPollingRuns = (companyId) => {
    setPolling(true);
    clearInterval(runsTimerRef.current);
    runsTimerRef.current = setInterval(async () => {
      try {
        const runRes = await fetchRuns(companyId);
        setRuns(runRes);
        const stillRunning = runRes.some(r => r.status === "running");
        if (!stillRunning) {
          clearInterval(runsTimerRef.current);
          setPolling(false);
        }
      } catch (e) {
        console.error(e);
        clearInterval(runsTimerRef.current);
        setPolling(false);
      }
    }, 6000);
  };

  const handleSave = async () => {
    try {
      if (formData.id) {
        const res = await updateCompany(formData.id, formData);
        setCompanies(companies.map(c => c.id === res.id ? res : c));
        setSelectedCompany(res);
        alert("Configuration updated successfully!");
      } else {
        const res = await createCompany(formData);
        setCompanies([...companies, res]);
        handleSelectCompany(res);
        alert("Company profile created successfully!");
      }
    } catch (e) {
      alert("Error: " + (e.response?.data?.detail || e.message));
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("Are you sure you want to delete this company profile? This will clear all runs history and configurations.")) return;
    try {
      await deleteCompany(selectedCompany.id);
      const updated = companies.filter(c => c.id !== selectedCompany.id);
      setCompanies(updated);
      if (updated.length > 0) {
        handleSelectCompany(updated[0]);
      } else {
        setSelectedCompany(null);
        setFormData(DEFAULT_COMPANY);
      }
      alert("Company profile deleted successfully.");
    } catch (e) {
      alert("Error deleting company: " + e.message);
    }
  };

  const handleRunNow = async () => {
    if (!selectedCompany) return;
    try {
      await triggerRun(selectedCompany.id);
      alert("Pipeline task launched successfully!");
      // Immediately fetch runs and start polling
      const runRes = await fetchRuns(selectedCompany.id);
      setRuns(runRes);
      if (runRes && runRes.length > 0) {
        setExpandedRunId(runRes[0].id);
        expandedInitRef.current = true;
      }
      startPollingRuns(selectedCompany.id);
    } catch (e) {
      alert("Failed to trigger run: " + e.message);
    }
  };

  const handleViewArticles = async (run) => {
    setSelectedRun(run);
    try {
      const res = await fetchRunArticles(run.id);
      setRunArticles(res);
      setShowArticlesModal(true);
    } catch (e) {
      alert("Error loading audit logs: " + e.message);
    }
  };

  const handleUploadFile = async (e, type) => {
    const file = e.target.files[0];
    if (!file) return;
    setFileUploading(prev => ({ ...prev, [type]: true }));
    const formDataObj = new FormData();
    formDataObj.append("file", file);
    
    try {
      const endpoint = `${BASE}/companies/${selectedCompany.id}/upload-${type === "keywords" ? "keywords" : "priority-media"}`;
      await api.post(endpoint, formDataObj, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      alert(`${type === "keywords" ? "Keywords" : "Priority Media"} file uploaded successfully!`);
      // Reload current company profile
      const res = await fetchCompanies();
      setCompanies(res);
      const reloaded = res.find(c => c.id === selectedCompany.id);
      if (reloaded) handleSelectCompany(reloaded);
    } catch (err) {
      alert("Upload failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setFileUploading(prev => ({ ...prev, [type]: false }));
    }
  };

  return (
    <div style={{ display: "flex", height: "calc(100vh - 40px)", overflow: "hidden" }}>
      {/* Left panel: Company List */}
      <div style={{ width: "280px", borderRight: "1px solid var(--border)", background: "var(--bg)", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 800 }}>Profiles</h3>
          <button onClick={() => { setSelectedCompany(null); setFormData(DEFAULT_COMPANY); setRuns([]); }} style={{ background: "none", border: "1px solid var(--accent)", color: "var(--accent)", padding: "4px 8px", borderRadius: "4px", cursor: "pointer", fontSize: "11px", fontWeight: 700 }}>+ NEW</button>
        </div>
        <div style={{ flex: 1, overflowY: "auto", padding: "8px" }}>
          {companies.map(c => (
            <div key={c.id} onClick={() => handleSelectCompany(c)} style={{
              padding: "12px", borderRadius: "6px", cursor: "pointer", marginBottom: "4px",
              background: selectedCompany?.id === c.id ? "rgba(74,158,255,.08)" : "transparent",
              border: selectedCompany?.id === c.id ? "1px solid var(--accent)" : "1px solid transparent",
            }}>
              <div style={{ fontSize: "14px", fontWeight: 700, color: selectedCompany?.id === c.id ? "var(--accent)" : "var(--text)" }}>{c.name}</div>
              <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "4px" }}>Sectors: {c.sector_match}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel: Editor & Tabs */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "var(--surface)", overflow: "hidden" }}>
        {/* Top title bar */}
        <div style={{ padding: "16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 800 }}>{formData.id ? formData.name : "Create New Pipeline Profile"}</h2>
            {formData.id && <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>Active ID: {formData.id}</div>}
          </div>
          <div style={{ display: "flex", gap: "10px" }}>
            {formData.id && (
              <>
                <button onClick={handleRunNow} style={{ padding: "8px 16px", background: "var(--success)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700, fontSize: "13px" }}>▶ RUN PIPELINE</button>
                <button onClick={handleDelete} style={{ padding: "8px 16px", background: "rgba(239,68,68,.1)", color: "var(--danger)", border: "1px solid var(--danger)", borderRadius: "6px", cursor: "pointer", fontWeight: 700, fontSize: "13px" }}>✕ Delete Profile</button>
              </>
            )}
            <button onClick={handleSave} style={{ padding: "8px 16px", background: "var(--accent)", color: "white", border: "none", borderRadius: "6px", cursor: "pointer", fontWeight: 700, fontSize: "13px" }}>Save Config</button>
          </div>
        </div>

        {/* Tab Headers */}
        <div style={{ display: "flex", background: "var(--bg)", borderBottom: "1px solid var(--border)" }}>
          {[
            { id: "general", label: "Settings & Schedule" },
            { id: "files", label: "Custom Configuration Files" },
            { id: "relevance", label: "Outputs & Deliverables" },
            { id: "llm", label: "LLM Configuration" },
            { id: "recipients", label: "Recipients" },
            { id: "history", label: "Run History & Logs" }
          ].map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
              padding: "12px 18px", background: "none", border: "none", borderBottom: activeTab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
              color: activeTab === t.id ? "var(--accent)" : "var(--muted)", cursor: "pointer", fontWeight: 700, fontSize: "13px"
            }}>{t.label}</button>
          ))}
        </div>

        {/* Tab Contents */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>
          
          {/* Tab: General Settings & Schedule */}
          {activeTab === "general" && (
            <div style={{ maxWidth: "700px", display: "flex", flexDirection: "column", gap: "16px" }}>
              <div style={{ display: "flex", gap: "16px" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Company/Client Name</label>
                  <input type="text" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} placeholder="e.g. Google India" />
                </div>
                <div style={{ width: "120px" }}>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Timezone</label>
                  <select value={formData.timezone} onChange={e => setFormData({ ...formData, timezone: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--surface)" }}>
                    {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "10px" }}>Selected Sectors</label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "10px", padding: "12px", background: "rgba(255,255,255,.02)", border: "1px solid var(--border)", borderRadius: "8px" }}>
                  {availableSectors.map(sec => {
                    const currentSectors = formData.sector_match
                      ? formData.sector_match.split(",").map(s => s.trim().toLowerCase()).filter(Boolean)
                      : [];
                    const isChecked = currentSectors.includes(sec.toLowerCase());
                    
                    const handleCheckboxChange = (e) => {
                      let updatedSectors = [...currentSectors];
                      if (e.target.checked) {
                        if (!updatedSectors.includes(sec.toLowerCase())) {
                          updatedSectors.push(sec.toLowerCase());
                        }
                      } else {
                        updatedSectors = updatedSectors.filter(s => s !== sec.toLowerCase());
                      }
                      setFormData({ ...formData, sector_match: updatedSectors.join(", ") });
                    };

                    return (
                      <div key={sec} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <input type="checkbox" id={`sector-${sec}`} checked={isChecked} onChange={handleCheckboxChange} style={{ width: "16px", height: "16px", cursor: "pointer" }} />
                        <label htmlFor={`sector-${sec}`} style={{ fontSize: "13px", cursor: "pointer", textTransform: "capitalize" }}>{sec}</label>
                      </div>
                    );
                  })}
                </div>
                {availableSectors.length === 0 && (
                  <div style={{ fontSize: "12px", color: "var(--muted)", marginTop: "4px" }}>Loading sectors list...</div>
                )}
              </div>

              <div style={{ display: "flex", gap: "16px" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Time window (Hours to look back)</label>
                  <input type="number" value={formData.window_hours} onChange={e => setFormData({ ...formData, window_hours: parseInt(e.target.value) || 24 })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Daily Fetch Time</label>
                  <input type="text" value={formData.fetch_time} onChange={e => setFormData({ ...formData, fetch_time: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} placeholder="07:00" />
                </div>
              </div>

              <div style={{ display: "flex", gap: "16px" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Frequency</label>
                  <select value={formData.frequency} onChange={e => setFormData({ ...formData, frequency: e.target.value, days: [] })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--surface)" }}>
                    <option value="Daily">Daily</option>
                    <option value="Weekly">Weekly</option>
                    <option value="Monthly">Monthly</option>
                    <option value="Custom">Custom</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Mail Send Mode</label>
                  <select value={formData.mail_send_mode} onChange={e => setFormData({ ...formData, mail_send_mode: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--surface)" }}>
                    <option value="Immediate">Immediate Send</option>
                    <option value="Scheduled">Scheduled Delay</option>
                  </select>
                </div>
                {formData.mail_send_mode === "Scheduled" && (
                  <div style={{ width: "120px" }}>
                    <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Mail Time</label>
                    <input type="text" value={formData.mail_send_time} onChange={e => setFormData({ ...formData, mail_send_time: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} placeholder="08:00" />
                  </div>
                )}
              </div>

              {formData.frequency !== "Daily" && (
                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Trigger Days</label>
                  <DaySelector frequency={formData.frequency} days={formData.days} onChange={days => setFormData({ ...formData, days })} />
                </div>
              )}

              <div style={{ display: "flex", gap: "16px", borderTop: "1px solid var(--border)", paddingTop: "16px" }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>Search Mode</label>
                  <select value={formData.search_mode || "title"} onChange={e => setFormData({ ...formData, search_mode: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--surface)" }}>
                    <option value="title">Search in Title Only</option>
                    <option value="body">Search in Title & Full Body</option>
                  </select>
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: "8px", marginTop: "18px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <input type="checkbox" id="pooja_algo_enabled" checked={formData.pooja_algo_enabled ?? true} onChange={e => setFormData({ ...formData, pooja_algo_enabled: e.target.checked })} style={{ width: "16px", height: "16px", cursor: "pointer" }} />
                    <label htmlFor="pooja_algo_enabled" style={{ fontSize: "13px", fontWeight: 700, cursor: "pointer" }}>Enable Pooja Filtering Logic</label>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <input type="checkbox" id="group_by_source_sector" checked={formData.group_by_source_sector ?? false} onChange={e => setFormData({ ...formData, group_by_source_sector: e.target.checked })} style={{ width: "16px", height: "16px", cursor: "pointer" }} />
                    <label htmlFor="group_by_source_sector" style={{ fontSize: "13px", fontWeight: 700, cursor: "pointer" }}>Categorize by Polled Sector</label>
                  </div>
                </div>
              </div>

              <div style={{ borderTop: "1px solid var(--border)", marginTop: "12px", paddingTop: "12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <input type="checkbox" id="enabled" checked={formData.enabled} onChange={e => setFormData({ ...formData, enabled: e.target.checked })} style={{ width: "16px", height: "16px" }} />
                  <label htmlFor="enabled" style={{ fontSize: "13px", fontWeight: 700, cursor: "pointer" }}>Enable Automated Scheduler</label>
                </div>
              </div>
            </div>
          )}

          {/* Tab: Custom Configuration Files */}
          {activeTab === "files" && (
            <div style={{ maxWidth: "700px", display: "flex", flexDirection: "column", gap: "24px" }}>
              <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg)" }}>
                <h4 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 800 }}>Keywords Excel List</h4>
                <p style={{ fontSize: "12px", color: "var(--muted)", margin: "0 0 16px 0" }}>Upload a <code>keywords.xlsx</code> file containing custom categories and queries. The system parses it in-memory dynamically during pipeline runs.</p>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <input type="file" accept=".xlsx" onChange={e => handleUploadFile(e, "keywords")} style={{ display: "none" }} id="keywords-upload-input" disabled={!selectedCompany?.id} />
                  <label htmlFor="keywords-upload-input" style={{
                    padding: "8px 16px", border: "1px solid var(--border)", borderRadius: "6px", cursor: selectedCompany?.id ? "pointer" : "not-allowed",
                    fontSize: "13px", fontWeight: 700, background: "var(--surface)", opacity: selectedCompany?.id ? 1 : 0.5
                  }}>
                    {fileUploading.keywords ? "Uploading..." : "✕ Choose Excel File"}
                  </label>
                  {formData.keywords_file_name ? (
                    <span style={{ fontSize: "13px", color: "var(--success)", fontWeight: 600 }}>✓ Loaded: {formData.keywords_file_name}</span>
                  ) : (
                    <span style={{ fontSize: "13px", color: "var(--muted)" }}>No file uploaded. Relevancy keyword checks will be bypassed.</span>
                  )}
                </div>
              </div>

              <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg)" }}>
                <h4 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 800 }}>Or: Manually Enter Keywords (Comma Separated)</h4>
                <p style={{ fontSize: "12px", color: "var(--muted)", margin: "0 0 12px 0" }}>Enter keywords separated by commas. Multi-term queries (e.g. <code>Boston Scientific + investment</code>) require all terms to match inside the article title.</p>
                <textarea
                  value={formData.manual_keywords || ""}
                  onChange={e => setFormData({ ...formData, manual_keywords: e.target.value })}
                  style={{ width: "100%", height: "120px", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--surface)", color: "var(--text)", fontFamily: "monospace", fontSize: "13px", resize: "vertical" }}
                  placeholder="e.g. watchman, PulseSelect, Boston Scientific + investment, Terumo"
                />
              </div>

              <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg)" }}>
                <h4 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 800 }}>Priority Media Publications List</h4>
                <p style={{ fontSize: "12px", color: "var(--muted)", margin: "0 0 16px 0" }}>Upload a priority media outlets sheet. Articles fetched from these media sources will pass through the priority-tier threshold.</p>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <input type="file" accept=".xlsx" onChange={e => handleUploadFile(e, "media")} style={{ display: "none" }} id="media-upload-input" disabled={!selectedCompany?.id} />
                  <label htmlFor="media-upload-input" style={{
                    padding: "8px 16px", border: "1px solid var(--border)", borderRadius: "6px", cursor: selectedCompany?.id ? "pointer" : "not-allowed",
                    fontSize: "13px", fontWeight: 700, background: "var(--surface)", opacity: selectedCompany?.id ? 1 : 0.5
                  }}>
                    {fileUploading.media ? "Uploading..." : "✕ Choose Excel File"}
                  </label>
                  {formData.priority_media_file_name ? (
                    <span style={{ fontSize: "13px", color: "var(--success)", fontWeight: 600 }}>✓ Loaded: {formData.priority_media_file_name}</span>
                  ) : (
                    <span style={{ fontSize: "13px", color: "var(--muted)" }}>No file uploaded. All publications will bypass media checks.</span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Tab: Outputs & Deliverables */}
          {activeTab === "relevance" && (
            <div style={{ maxWidth: "700px", display: "flex", flexDirection: "column", gap: "20px" }}>
              <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg)" }}>
                <h4 style={{ margin: "0 0 16px 0", fontSize: "14px", fontWeight: 800, textTransform: "uppercase", color: "var(--accent)" }}>Select deliverables to generate & distribute</h4>
                
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <input type="checkbox" id="send_email" checked={formData.send_email} onChange={e => setFormData({ ...formData, send_email: e.target.checked })} style={{ width: "16px", height: "16px" }} />
                    <label htmlFor="send_email" style={{ fontSize: "13px", fontWeight: 700, cursor: "pointer" }}>Send email briefs to recipients list</label>
                  </div>
                  
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", paddingLeft: "24px" }}>
                    <input type="checkbox" id="send_html_mailer" checked={formData.send_html_mailer} onChange={e => setFormData({ ...formData, send_html_mailer: e.target.checked })} disabled={!formData.send_email} style={{ width: "16px", height: "16px" }} />
                    <label htmlFor="send_html_mailer" style={{ fontSize: "13px", fontWeight: 600, cursor: "pointer" }}>Include rich HTML design mailer inline inside email body</label>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "10px", paddingLeft: "24px" }}>
                    <input type="checkbox" id="send_mailer_doc" checked={formData.send_mailer_doc} onChange={e => setFormData({ ...formData, send_mailer_doc: e.target.checked })} disabled={!formData.send_email} style={{ width: "16px", height: "16px" }} />
                    <label htmlFor="send_mailer_doc" style={{ fontSize: "13px", fontWeight: 600, cursor: "pointer" }}>Attach Brief Mailer Word DOCX file</label>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "10px", paddingLeft: "24px" }}>
                    <input type="checkbox" id="send_report_doc" checked={formData.send_report_doc} onChange={e => setFormData({ ...formData, send_report_doc: e.target.checked })} disabled={!formData.send_email} style={{ width: "16px", height: "16px" }} />
                    <label htmlFor="send_report_doc" style={{ fontSize: "13px", fontWeight: 600, cursor: "pointer" }}>Attach Master Corporate Report Word DOCX file</label>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "10px", paddingLeft: "24px" }}>
                    <input type="checkbox" id="send_report_excel" checked={formData.send_report_excel} onChange={e => setFormData({ ...formData, send_report_excel: e.target.checked })} disabled={!formData.send_email} style={{ width: "16px", height: "16px" }} />
                    <label htmlFor="send_report_excel" style={{ fontSize: "13px", fontWeight: 600, cursor: "pointer" }}>Attach Master Corporate Report Excel sheet</label>
                  </div>
                </div>
              </div>

              <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg)" }}>
                <h4 style={{ margin: "0 0 16px 0", fontSize: "14px", fontWeight: 800, textTransform: "uppercase", color: "var(--accent)" }}>Cloud Integrations</h4>
                
                <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <input type="checkbox" id="upload_to_google_drive" checked={formData.upload_to_google_drive} onChange={e => setFormData({ ...formData, upload_to_google_drive: e.target.checked })} style={{ width: "16px", height: "16px" }} />
                      <label htmlFor="upload_to_google_drive" style={{ fontSize: "13px", fontWeight: 700, cursor: "pointer" }}>Upload briefings to Google Drive & generate sharing links</label>
                    </div>
                  </div>

                  <div style={{ borderTop: "1px solid rgba(255,255,255,.05)", paddingTop: "12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <input type="checkbox" id="update_takeaways_sheet" checked={formData.update_takeaways_sheet} onChange={e => setFormData({ ...formData, update_takeaways_sheet: e.target.checked })} style={{ width: "16px", height: "16px" }} />
                      <label htmlFor="update_takeaways_sheet" style={{ fontSize: "13px", fontWeight: 700, cursor: "pointer" }}>Append daily takeaways to Cumulative Google Sheet</label>
                    </div>
                    {formData.update_takeaways_sheet && (
                      <div style={{ marginTop: "10px" }}>
                        <label style={{ display: "block", fontSize: "11px", fontWeight: 700, color: "var(--muted)", marginBottom: "4px" }}>Takeaways Sheet URL</label>
                        <input type="text" value={formData.takeaways_sheet_url || ""} onChange={e => setFormData({ ...formData, takeaways_sheet_url: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px" }} placeholder="https://docs.google.com/spreadsheets/d/..." />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tab: LLM Configuration */}
          {activeTab === "llm" && (
            <div style={{ maxWidth: "800px", display: "flex", flexDirection: "column", gap: "20px" }}>
              <div style={{ padding: "20px", border: "1px solid var(--border)", borderRadius: "10px", background: "var(--bg)", boxShadow: "0 4px 12px rgba(0,0,0,0.05)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: "15px", fontWeight: 800 }}>LLM Provider Switchboard & Custom Prompt Studio</h4>
                    <p style={{ fontSize: "12px", color: "var(--muted)", margin: "4px 0 0 0" }}>Configure LLMs, attach brand guidelines/documents, customize prompts, and inspect historical prompt changes.</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleOpenPromptHistory}
                    style={{
                      padding: "8px 14px",
                      background: "var(--surface)",
                      border: "1px solid var(--accent)",
                      color: "var(--accent)",
                      borderRadius: "6px",
                      fontSize: "12px",
                      fontWeight: 700,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px"
                    }}
                  >
                    📜 Prompt History
                  </button>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                  {/* Stage 1: Keyword Verification & Supporting Doc */}
                  <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--surface)" }}>
                    <div style={{ fontSize: "13px", fontWeight: 800, color: "var(--accent)", marginBottom: "8px" }}>Stage 1: Keyword Relevance Verification & Supporting Context</div>
                    <p style={{ fontSize: "11px", color: "var(--muted)", margin: "0 0 12px 0" }}>Attach topic PDFs (e.g. <code>Brand Details.pdf</code>) and refine prompts to reject random keyword hits.</p>

                    <label style={{ display: "block", fontSize: "11px", fontWeight: 700, marginBottom: "4px" }}>Verification Provider</label>
                    <select value={formData.llm_verification_provider} onChange={e => setFormData({ ...formData, llm_verification_provider: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--bg)", marginBottom: "16px" }}>
                      <option value="none">None (Keep all keyword matches without verifying)</option>
                      <option value="claude">Claude (Recommended for precision & brand audit)</option>
                      <option value="groq">Groq (Recommended for speed)</option>
                    </select>

                    {/* Supporting Document Upload Card */}
                    <div style={{ background: "rgba(255,255,255,0.02)", border: "1px dashed var(--border)", borderRadius: "6px", padding: "12px", marginBottom: "16px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div>
                          <div style={{ fontSize: "12px", fontWeight: 700 }}>📄 Attached Supporting Document</div>
                          <div style={{ fontSize: "11px", color: "var(--muted)" }}>Inject PDF/Text brand rules directly into LLM relevance checks.</div>
                        </div>
                        <div>
                          {formData.verification_doc_filename ? (
                            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                              <span style={{ fontSize: "11px", background: "rgba(34,197,94,0.15)", color: "var(--success)", border: "1px solid var(--success)", padding: "3px 8px", borderRadius: "4px", fontWeight: 700 }}>
                                ✓ {formData.verification_doc_filename}
                              </span>
                              <button type="button" onClick={() => setShowDocPreview(!showDocPreview)} style={{ padding: "4px 8px", fontSize: "10px", borderRadius: "4px", border: "1px solid var(--border)", background: "var(--bg)", cursor: "pointer", fontWeight: "700" }}>
                                {showDocPreview ? "Hide Text" : "👁 View Formatted Text"}
                              </button>
                              <button type="button" onClick={() => setShowPdfModal(true)} style={{ padding: "4px 8px", fontSize: "10px", borderRadius: "4px", border: "1px solid var(--accent)", color: "var(--accent)", background: "rgba(74,158,255,0.1)", cursor: "pointer", fontWeight: "700" }}>
                                📑 Preview Original PDF
                              </button>
                              <button type="button" onClick={handleDeleteDoc} style={{ padding: "4px 8px", fontSize: "10px", borderRadius: "4px", border: "1px solid var(--danger)", color: "var(--danger)", background: "none", cursor: "pointer" }}>
                                🗑 Remove
                              </button>
                            </div>
                          ) : (
                            <label style={{ padding: "6px 12px", background: "var(--accent)", color: "#fff", borderRadius: "6px", fontSize: "11px", fontWeight: 700, cursor: docUploading ? "wait" : "pointer" }}>
                              {docUploading ? "Uploading..." : "➕ Attach Document (PDF)"}
                              <input type="file" accept=".pdf,.txt" onChange={handleUploadDoc} style={{ display: "none" }} disabled={docUploading} />
                            </label>
                          )}
                        </div>
                      </div>

                      {showDocPreview && formData.verification_doc_text && (
                        <div style={{
                          marginTop: "12px", padding: "12px", background: "#0b0c10", border: "1px solid var(--border)",
                          borderRadius: "6px", maxHeight: "350px", overflowY: "auto", overflowX: "auto",
                          fontSize: "11px", color: "#34d399", fontFamily: "Consolas, Monaco, monospace",
                          whiteSpace: "pre-wrap", lineHeight: "1.4", tabSize: 4
                        }}>
                          {formData.verification_doc_text}
                        </div>
                      )}
                    </div>

                    {/* Stage 1 System Prompt */}
                    <div style={{ marginBottom: "12px" }}>
                      <label style={{ display: "block", fontSize: "11px", fontWeight: 700, marginBottom: "4px" }}>System Prompt (Role & Guidelines)</label>
                      <textarea
                        rows={2}
                        value={formData.verification_system_prompt || ""}
                        onChange={e => setFormData({ ...formData, verification_system_prompt: e.target.value })}
                        placeholder="Default: You are a precise news relevance auditor. Decide if the news article is genuinely relevant to the matched keyword and client topic."
                        style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--bg)", fontSize: "12px", fontFamily: "monospace" }}
                      />
                    </div>

                    {/* Stage 1 User Prompt */}
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                        <label style={{ fontSize: "11px", fontWeight: 700 }}>User Verification Prompt</label>
                        <span style={{ fontSize: "10px", color: "var(--accent)" }}>Vars: <code>{`{title}`}</code>, <code>{`{keyword}`}</code>, <code>{`{brand_context}`}</code>, <code>{`{company_name}`}</code>, <code>{`{snippet}`}</code></span>
                      </div>
                      <textarea
                        rows={4}
                        value={formData.verification_user_prompt || ""}
                        onChange={e => setFormData({ ...formData, verification_user_prompt: e.target.value })}
                        placeholder="Default: Article Title: {title}&#10;Matched Keyword: {keyword}&#10;&#10;Supporting Brand/Topic Context:&#10;{brand_context}&#10;&#10;Decide if this article is genuinely relevant to {company_name}. Respond ONLY with 'yes' or 'no'."
                        style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--bg)", fontSize: "12px", fontFamily: "monospace" }}
                      />
                    </div>
                  </div>

                  {/* Stage 2: Per-Article Summaries */}
                  <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--surface)" }}>
                    <div style={{ fontSize: "13px", fontWeight: 800, color: "var(--accent)", marginBottom: "8px" }}>Stage 2: Per-Article Summaries</div>
                    
                    <label style={{ display: "block", fontSize: "11px", fontWeight: 700, marginBottom: "4px" }}>Summary Provider</label>
                    <select value={formData.llm_summary_provider} onChange={e => setFormData({ ...formData, llm_summary_provider: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--bg)", marginBottom: "12px" }}>
                      <option value="none">None (Use original snippet)</option>
                      <option value="claude">Claude</option>
                      <option value="groq">Groq</option>
                    </select>

                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <label style={{ fontSize: "11px", fontWeight: 700 }}>Custom Summary Prompt</label>
                      <span style={{ fontSize: "10px", color: "var(--accent)" }}>Vars: <code>{`{title}`}</code>, <code>{`{body}`}</code>, <code>{`{company_name}`}</code></span>
                    </div>
                    <textarea
                      rows={3}
                      value={formData.summary_user_prompt || ""}
                      onChange={e => setFormData({ ...formData, summary_user_prompt: e.target.value })}
                      placeholder="Default: Summarize this news article in 30-40 words.&#10;&#10;Title: {title}&#10;Body:&#10;{body}&#10;&#10;Respond with ONLY the summary."
                      style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--bg)", fontSize: "12px", fontFamily: "monospace" }}
                    />
                  </div>

                  {/* Stage 3: Executive Brief Synthesis */}
                  <div style={{ padding: "16px", border: "1px solid var(--border)", borderRadius: "8px", background: "var(--surface)" }}>
                    <div style={{ fontSize: "13px", fontWeight: 800, color: "var(--accent)", marginBottom: "8px" }}>Stage 3: Executive Brief Synthesis</div>
                    
                    <label style={{ display: "block", fontSize: "11px", fontWeight: 700, marginBottom: "4px" }}>Executive Synthesis Provider</label>
                    <select value={formData.llm_executive_provider} onChange={e => setFormData({ ...formData, llm_executive_provider: e.target.value })} style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--bg)", marginBottom: "12px" }}>
                      <option value="none">None (Omit executive synthesis)</option>
                      <option value="claude">Claude</option>
                      <option value="groq">Groq</option>
                    </select>

                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                      <label style={{ fontSize: "11px", fontWeight: 700 }}>Custom Executive Prompt</label>
                      <span style={{ fontSize: "10px", color: "var(--accent)" }}>Vars: <code>{`{company_name}`}</code></span>
                    </div>
                    <textarea
                      rows={3}
                      value={formData.executive_user_prompt || ""}
                      onChange={e => setFormData({ ...formData, executive_user_prompt: e.target.value })}
                      placeholder="Default: Synthesize key takeaways and executive bullet points for {company_name}."
                      style={{ width: "100%", padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "6px", background: "var(--bg)", fontSize: "12px", fontFamily: "monospace" }}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tab: Recipients */}
          {activeTab === "recipients" && (
            <div style={{ maxWidth: "600px" }}>
              <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: "12px" }}>Configured Recipients</div>
              <div>
                {formData.recipients.length === 0 ? (
                  <div style={{ padding: "16px", border: "1px dashed var(--border)", borderRadius: "6px", color: "var(--muted)", textAlign: "center" }}>No recipients mapped to this client configuration.</div>
                ) : (
                  formData.recipients.map((r, idx) => (
                    <RecipientItem key={idx} email={r.email} role={r.role} onRemove={() => setFormData({
                      ...formData,
                      recipients: formData.recipients.filter((_, i) => i !== idx),
                    })} />
                  ))
                )}
              </div>
              <AddRecipientForm onAdd={(email, role) => setFormData({
                ...formData,
                recipients: [...formData.recipients, { email, role }],
              })} />
            </div>
          )}

          {/* Tab: Run History & Logs */}
          {activeTab === "history" && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                <h4 style={{ margin: 0, fontSize: "14px", fontWeight: 800 }}>Pipeline Task Logs</h4>
                {polling && <div style={{ fontSize: "12px", color: "var(--accent)" }}>● Polling active run logs...</div>}
              </div>

              {runs.length === 0 ? (
                <div style={{ padding: "30px", textAlign: "center", color: "var(--muted)", border: "1px dashed var(--border)", borderRadius: "8px" }}>No runs recorded yet. Press "Run Now" to trigger the pipeline manually.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {runs.map(run => {
                    const logObj = parseRobustProgressLog(
                      run.progress_message,
                      run.started_at,
                      run.finished_at,
                      run.status,
                      formData.llm_verification_provider,
                      formData.llm_summary_provider,
                      formData.llm_executive_provider
                    );
                    
                    return (
                      <div key={run.id} style={{ border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg)", overflow: "hidden" }}>
                        <div onClick={() => setExpandedRunId(expandedRunId === run.id ? null : run.id)} style={{ padding: "16px", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "16px", borderBottom: expandedRunId === run.id ? "1px solid var(--border)" : "none", cursor: "pointer", alignItems: "center" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "16px", flex: 1 }}>
                            <StatusPill status={run.status} />
                            <div>
                              <div style={{ fontSize: "12px", color: "var(--muted)" }}>
                                {run.fetched_count} fetched • {run.deduped_count} deduped • <strong>{run.relevant_count} relevant</strong>
                              </div>
                              <div style={{ fontSize: "10px", color: "var(--muted)", opacity: 0.6 }}>
                                {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
                              </div>
                            </div>
                          </div>
                          
                          <div style={{ display: "flex", gap: "10px", alignItems: "center" }} onClick={e => e.stopPropagation()}>
                            {run.status === "completed" && (
                              <button onClick={() => handleViewArticles(run)} style={{ padding: "6px 12px", background: "rgba(74,158,255,.1)", color: "var(--accent)", border: "none", borderRadius: "4px", fontSize: "12px", fontWeight: 700, cursor: "pointer" }}>Audit Articles ({run.relevant_count})</button>
                            )}
                          </div>
                          <span style={{ color: "var(--muted)" }}>{expandedRunId === run.id ? "▲" : "▼"}</span>
                        </div>

                        {/* Progress Log steps */}
                        {expandedRunId === run.id && (
                          <div style={{ padding: "16px", background: "var(--surface)", borderTop: "1px solid var(--border)" }}>
                          {run.status === "completed" && (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginBottom: "16px" }}>
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
                                    fontWeight: 600,
                                    fontSize: "12px"
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
                                    fontWeight: 600,
                                    fontSize: "12px"
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
                                    fontWeight: 600,
                                    fontSize: "12px"
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
                                    fontSize: "12px"
                                  }}
                                >
                                  🔗 Open Mailer Google Doc
                                </a>
                              )}
                              {formData.takeaways_sheet_url && (
                                <a
                                  href={formData.takeaways_sheet_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "6px",
                                    background: "rgba(244,180,0,0.12)",
                                    border: "1px solid rgba(244,180,0,0.35)",
                                    padding: "6px 12px",
                                    borderRadius: "6px",
                                    color: "#F4B400",
                                    cursor: "pointer",
                                    fontWeight: 600,
                                    textDecoration: "none",
                                    fontSize: "12px"
                                  }}
                                >
                                  📈 Cumulative Spreadsheet
                                </a>
                              )}
                            </div>
                          )}

                          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "8px", fontWeight: 700 }}>
                            <span style={{ color: "var(--muted)" }}>Progress Status</span>
                            <span>{logObj.progress}%</span>
                          </div>
                          <div style={{ height: "4px", background: "var(--border)", borderRadius: "2px", overflow: "hidden", marginBottom: "16px" }}>
                            <div style={{ width: `${logObj.progress}%`, height: "100%", background: "var(--accent)" }} />
                          </div>

                          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                            {logObj.steps.map((st, i) => (
                              <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                                <span style={{ color: st.status === "completed" ? "var(--text)" : "var(--muted)" }}>{st.label}</span>
                                <span style={{
                                  fontWeight: 700,
                                  color: st.status === "completed" ? "var(--success)" : st.status === "failed" ? "var(--danger)" : st.status === "running" ? "var(--accent)" : "var(--muted)"
                                }}>
                                  {st.status === "completed" ? "✓ Done" : st.status === "failed" ? "✗ Failed" : st.status === "running" ? "● Running" : "Pending"}
                                </span>
                              </div>
                            ))}
                          </div>
                          
                          {/* Green-on-black Console log trace window with per-stage downloads */}
                          {logObj.lines && (
                            <div style={{ background: "#0b0c10", border: "1px solid var(--nav-active-border)", borderRadius: "8px", overflow: "hidden", marginTop: "16px" }}>
                              <div style={{ background: "rgba(255,255,255,0.02)", borderBottom: "1px solid rgba(255,255,255,0.05)", padding: "6px 12px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <div style={{ display: "flex", gap: "6px" }}>
                                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#ef4444", display: "inline-block" }}></span>
                                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#eab308", display: "inline-block" }}></span>
                                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#22c55e", display: "inline-block" }}></span>
                                </div>
                                <span style={{ fontSize: "9px", fontFamily: "monospace", color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", fontWeight: "700" }}>Trace Log</span>
                              </div>
                              <div style={{ margin: 0, padding: "10px", fontSize: "11px", color: "#34d399", fontFamily: "monospace", overflowX: "auto", maxHeight: "250px", overflowY: "auto", textAlign: "left", display: "flex", flexDirection: "column", gap: "6px" }}>
                                {logObj.lines.split("\n").map((line, lIdx) => {
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
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

        </div>
      </div>

      {/* Audit Articles Modal */}
      {showArticlesModal && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,.7)",
          display: "flex", justifyContent: "center", alignItems: "center", zIndex: 99999, padding: "20px"
        }}>
          <div style={{
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px",
            width: "100%", maxWidth: "900px", maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden"
          }}>
            <div style={{ padding: "16px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 800 }}>Audit Trail: Run #{selectedRun?.id} ({runArticles.length} Articles)</h3>
              <button onClick={() => setShowArticlesModal(false)} style={{ background: "none", border: "none", color: "var(--text)", cursor: "pointer", fontSize: "20px", fontWeight: 700 }}>✕</button>
            </div>
            
            <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
              {runArticles.length === 0 ? (
                <div style={{ textAlign: "center", padding: "20px", color: "var(--muted)" }}>No articles recorded in the audit trail.</div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                  <thead>
                    <tr style={{ textAlign: "left", borderBottom: "2px solid var(--border)" }}>
                      <th style={{ padding: "8px" }}>Title & URL</th>
                      <th style={{ padding: "8px" }}>Pillar / Sub</th>
                      <th style={{ padding: "8px" }}>Keywords Matched</th>
                      <th style={{ padding: "8px" }}>Summary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runArticles.map(art => (
                      <tr key={art.id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "12px 8px", maxWidth: "250px" }}>
                          <a href={art.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 600 }}>{art.title}</a>
                        </td>
                        <td style={{ padding: "12px 8px" }}>
                          <div>{art.pillar}</div>
                          <div style={{ fontSize: "11px", color: "var(--muted)", marginTop: "2px" }}>{art.sub_category}</div>
                        </td>
                        <td style={{ padding: "12px 8px", maxWidth: "150px" }}>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                            {art.matched_keywords?.map((k, i) => (
                              <span key={i} style={{ background: "rgba(251,188,4,.1)", color: "#fbbc04", padding: "2px 6px", borderRadius: "4px", fontSize: "10px", fontWeight: 600 }}>{k}</span>
                            ))}
                          </div>
                        </td>
                        <td style={{ padding: "12px 8px", color: "var(--muted)", maxWidth: "300px" }}>{art.llm_summary}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Prompt History Modal */}
      {showHistoryModal && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,.75)",
          display: "flex", justifyContent: "center", alignItems: "center", zIndex: 99999, padding: "20px"
        }}>
          <div style={{
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px",
            width: "100%", maxWidth: "850px", maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden",
            boxShadow: "0 10px 30px rgba(0,0,0,0.5)"
          }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--bg)" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 800 }}>📜 Prompt History & Audit Log</h3>
                <div style={{ fontSize: "12px", color: "var(--muted)" }}>Client: <strong>{selectedCompany?.name}</strong></div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <select value={historyStageFilter} onChange={e => setHistoryStageFilter(e.target.value)} style={{ padding: "6px 10px", borderRadius: "6px", border: "1px solid var(--border)", background: "var(--surface)", fontSize: "12px" }}>
                  <option value="all">All Pipeline Stages</option>
                  <option value="verification">Verification Stage</option>
                  <option value="summary">Summary Stage</option>
                  <option value="executive">Executive Synthesis Stage</option>
                </select>
                <button onClick={() => setShowHistoryModal(false)} style={{ background: "none", border: "none", color: "var(--text)", cursor: "pointer", fontSize: "20px", fontWeight: 700 }}>✕</button>
              </div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "20px", display: "flex", flexDirection: "column", gap: "16px" }}>
              {historyItems.filter(h => historyStageFilter === "all" || h.stage === historyStageFilter).length === 0 ? (
                <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--muted)" }}>No prompt history recorded for this client yet. Whenever you modify and save a custom prompt, a version history entry is automatically captured here.</div>
              ) : (
                historyItems
                  .filter(h => historyStageFilter === "all" || h.stage === historyStageFilter)
                  .map((item) => (
                    <div key={item.id} style={{ border: "1px solid var(--border)", borderRadius: "8px", background: "var(--bg)", padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span style={{
                            padding: "2px 8px", borderRadius: "4px", fontSize: "10px", fontWeight: 800, textTransform: "uppercase",
                            background: item.stage === "verification" ? "rgba(74,158,255,0.15)" : item.stage === "summary" ? "rgba(234,179,8,0.15)" : "rgba(168,85,247,0.15)",
                            color: item.stage === "verification" ? "var(--accent)" : item.stage === "summary" ? "#eab308" : "#a855f7"
                          }}>
                            {item.stage}
                          </span>
                          <span style={{ fontSize: "12px", fontWeight: 700 }}>Version #{item.id}</span>
                          <span style={{ fontSize: "11px", color: "var(--muted)" }}>• {item.version_note || "Saved update"}</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                          <span style={{ fontSize: "11px", color: "var(--muted)" }}>{item.created_at ? new Date(item.created_at).toLocaleString() : ""} ({item.created_by})</span>
                          <button
                            type="button"
                            onClick={() => handleRestorePrompt(item.id)}
                            style={{
                              padding: "4px 10px", background: "rgba(34,197,94,0.15)", border: "1px solid var(--success)",
                              color: "var(--success)", borderRadius: "4px", fontSize: "11px", fontWeight: 700, cursor: "pointer"
                            }}
                          >
                            🔄 Restore Version
                          </button>
                        </div>
                      </div>

                      {item.system_prompt && (
                        <div>
                          <div style={{ fontSize: "10px", fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: "2px" }}>System Prompt:</div>
                          <div style={{ padding: "8px", background: "#0b0c10", borderRadius: "4px", fontSize: "11px", color: "#a7f3d0", fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
                            {item.system_prompt}
                          </div>
                        </div>
                      )}

                      <div>
                        <div style={{ fontSize: "10px", fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: "2px" }}>User Prompt:</div>
                        <div style={{ padding: "8px", background: "#0b0c10", borderRadius: "4px", fontSize: "11px", color: "#67e8f9", fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
                          {item.user_prompt}
                        </div>
                      </div>
                    </div>
                  ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Original PDF Preview Modal */}
      {showPdfModal && (
        <div style={{
          position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,.8)",
          display: "flex", justifyContent: "center", alignItems: "center", zIndex: 99999, padding: "20px"
        }}>
          <div style={{
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px",
            width: "100%", maxWidth: "1000px", height: "88vh", display: "flex", flexDirection: "column", overflow: "hidden",
            boxShadow: "0 10px 30px rgba(0,0,0,0.6)"
          }}>
            <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "center", background: "var(--bg)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "16px" }}>📑</span>
                <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 800 }}>Document Viewer: {formData.verification_doc_filename}</h3>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <a
                  href={`/api/robust-automation/companies/${selectedCompany?.id}/doc/file?token=${localStorage.getItem("token") || ""}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    padding: "4px 10px", background: "var(--surface)", border: "1px solid var(--accent)",
                    color: "var(--accent)", borderRadius: "4px", fontSize: "11px", fontWeight: 700, textDecoration: "none",
                    display: "flex", alignItems: "center", gap: "4px"
                  }}
                >
                  🔗 Open in New Tab
                </a>
                <button onClick={() => setShowPdfModal(false)} style={{ background: "none", border: "none", color: "var(--text)", cursor: "pointer", fontSize: "20px", fontWeight: 700 }}>✕</button>
              </div>
            </div>

            <div style={{ flex: 1, background: "#1e1e1e", display: "flex", overflow: "hidden" }}>
              <iframe
                title="PDF Document Viewer"
                src={`/api/robust-automation/companies/${selectedCompany?.id}/doc/file?token=${localStorage.getItem("token") || ""}`}
                style={{ width: "100%", height: "100%", border: "none" }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
