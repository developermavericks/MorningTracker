import { useState, useEffect } from "react";
import apiClient, { api } from "../services/api";

function parseProgressLog(progressMessage, startedAt, completedAt, status, clientSections = []) {
  if (!progressMessage) {
    return { filteredLog: "", progress: 0, sections: [], estimatedSeconds: 0 };
  }

  const lines = progressMessage.split("\n");
  const filteredLines = [];
  
  // Initialize section progress dictionary
  const sectionsProgress = {};
  
  // Normalize the clientSections list
  const sectionNames = clientSections.map(s => typeof s === "string" ? s : s.name);
  for (const name of sectionNames) {
    sectionsProgress[name] = {
      name,
      status: "pending", // pending, discovering, processing, completed
      discovered: 0,
      processed: 0,
      relevant: 0,
      progress: 0
    };
  }

  // Regex patterns
  const discoveringRegex = /Discovering articles for section '(.+?)'/;
  const processingRegex = /Processing and filtering (\d+) discovered articles in '(.+?)'/;
  const progressRegex = /Processed article (\d+)\/(\d+) in '(.+?)'/;
  const completedRegex = /Section '(.+?)' completed\. Discovered: (\d+), Relevant: (\d+)/;

  for (const line of lines) {
    const discoveringMatch = line.match(discoveringRegex);
    const processingMatch = line.match(processingRegex);
    const progressMatch = line.match(progressRegex);
    const completedMatch = line.match(completedRegex);

    if (completedMatch) {
      const name = completedMatch[1];
      const discovered = parseInt(completedMatch[2], 10);
      const relevant = parseInt(completedMatch[3], 10);
      if (!sectionsProgress[name]) {
        sectionsProgress[name] = { name, status: "completed", discovered, processed: discovered, relevant, progress: 100 };
      } else {
        sectionsProgress[name].status = "completed";
        sectionsProgress[name].discovered = discovered;
        sectionsProgress[name].processed = discovered;
        sectionsProgress[name].relevant = relevant;
        sectionsProgress[name].progress = 100;
      }
      filteredLines.push(line);
    } else if (progressMatch) {
      const current = parseInt(progressMatch[1], 10);
      const total = parseInt(progressMatch[2], 10);
      const name = progressMatch[3];
      if (!sectionsProgress[name]) {
        sectionsProgress[name] = { name, status: "processing", discovered: total, processed: current, relevant: 0, progress: 0 };
      } else if (sectionsProgress[name].status !== "completed") {
        sectionsProgress[name].status = "processing";
        sectionsProgress[name].discovered = total;
        sectionsProgress[name].processed = current;
      }
      // Do not push progress dots to console to keep it clean
    } else if (processingMatch) {
      const total = parseInt(processingMatch[1], 10);
      const name = processingMatch[2];
      if (!sectionsProgress[name]) {
        sectionsProgress[name] = { name, status: "processing", discovered: total, processed: 0, relevant: 0, progress: 0 };
      } else if (sectionsProgress[name].status !== "completed") {
        sectionsProgress[name].status = "processing";
        sectionsProgress[name].discovered = total;
      }
      filteredLines.push(line);
    } else if (discoveringMatch) {
      const name = discoveringMatch[1];
      if (!sectionsProgress[name]) {
        sectionsProgress[name] = { name, status: "discovering", discovered: 0, processed: 0, relevant: 0, progress: 0 };
      } else if (sectionsProgress[name].status !== "completed" && sectionsProgress[name].status !== "processing") {
        sectionsProgress[name].status = "discovering";
      }
      filteredLines.push(line);
    } else {
      filteredLines.push(line);
    }
  }

  // Calculate progress for each section
  const sectionList = Object.values(sectionsProgress);
  for (const sec of sectionList) {
    if (sec.status === "completed") {
      sec.progress = 100;
    } else if (sec.status === "processing") {
      if (sec.discovered > 0) {
        sec.progress = Math.min(Math.round((sec.processed / sec.discovered) * 100), 99);
      } else {
        sec.progress = 15;
      }
    } else if (sec.status === "discovering") {
      sec.progress = 5;
    } else {
      sec.progress = 0;
    }
  }

  // Force completed status for sections if overall log says finished
  if (status === "completed") {
    for (const sec of sectionList) {
      sec.status = "completed";
      sec.progress = 100;
      if (sec.discovered > 0) {
        sec.processed = sec.discovered;
      }
    }
  }

  // Calculate overall progress percent
  let overallProgress = 0;
  if (status === "completed") {
    overallProgress = 100;
  } else if (status === "failed") {
    overallProgress = 100;
  } else if (sectionList.length > 0) {
    const totalSecProgress = sectionList.reduce((sum, s) => sum + s.progress, 0);
    const avgSecProgress = totalSecProgress / sectionList.length;
    overallProgress = Math.min(Math.round(10 + (avgSecProgress / 100) * 80), 90);
    
    const lastLine = lines.length > 0 ? lines[lines.length - 1] : "";
    if (lastLine.includes("Compiling Word briefing")) {
      overallProgress = 92;
    } else if (lastLine.includes("Uploading report") || lastLine.includes("Uploading Filtered") || lastLine.includes("Uploading Master")) {
      overallProgress = 95;
    } else if (lastLine.includes("Sending daily briefing") || lastLine.includes("Sending report email")) {
      overallProgress = 98;
    }
  } else {
    if (progressMessage.includes("Compiling Word briefing")) {
      overallProgress = 92;
    } else if (progressMessage.includes("Uploading report")) {
      overallProgress = 95;
    } else if (progressMessage.includes("Sending daily briefing")) {
      overallProgress = 98;
    } else if (progressMessage.includes("Discovering articles")) {
      overallProgress = 10;
    } else {
      overallProgress = 5;
    }
  }

  // Estimate remaining seconds (based on total progress across all sections)
  let estimatedSecondsRemaining = 0;
  if (status === "running") {
    const totalProcessed = sectionList.reduce((sum, s) => sum + s.processed, 0);
    const totalDiscovered = sectionList.reduce((sum, s) => sum + s.discovered, 0);
    if (totalProcessed > 0 && totalDiscovered > totalProcessed) {
      const elapsedMs = Math.max(1000, new Date().getTime() - new Date(startedAt).getTime());
      const msPerArticle = elapsedMs / totalProcessed;
      const remaining = totalDiscovered - totalProcessed;
      estimatedSecondsRemaining = Math.max(1, Math.round((remaining * msPerArticle) / 1000));
    }
  }

  const filteredLog = filteredLines.join("\n");
  return {
    filteredLog,
    progress: overallProgress,
    sections: sectionList,
    estimatedSeconds: estimatedSecondsRemaining
  };
}

export default function ClientReports() {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedClient, setSelectedClient] = useState(null);
  const [logsClient, setLogsClient] = useState(null);
  const [logs, setLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(false);

  // Form states
  const [clientName, setClientName] = useState("");
  const [scheduledTime, setScheduledTime] = useState("07:00");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [isActive, setIsActive] = useState(true);
  const [recipients, setRecipients] = useState("");
  const [sections, setSections] = useState([{ name: "Brand Mentions", keywords: "" }]);
  const [context, setContext] = useState("");
  
  // File Upload states
  const [uploadingTemplateId, setUploadingTemplateId] = useState(null);

  useEffect(() => {
    fetchClients();
  }, []);

  useEffect(() => {
    if (!logsClient) return;

    const fetchLogs = async () => {
      try {
        const data = await api.get(`clients/${logsClient.id}/logs`);
        setLogs(data);
      } catch (err) {
        console.error("Failed to poll logs", err);
      }
    };

    fetchLogs();
    const interval = setInterval(fetchLogs, 3000);
    return () => clearInterval(interval);
  }, [logsClient]);

  const fetchClients = async () => {
    setLoading(true);
    try {
      const data = await api.get("clients/");
      setClients(data);
    } catch (err) {
      console.error("Failed to fetch clients", err);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = (client = null) => {
    if (client) {
      setSelectedClient(client);
      setClientName(client.name);
      setScheduledTime(client.scheduled_time);
      setTimezone(client.timezone);
      setIsActive(client.is_active);
      setRecipients(client.recipients.join(", "));
      setSections(client.sections.map(s => ({ name: s.name, keywords: s.keywords.join(", ") })));
      setContext(client.context || "");
    } else {
      setSelectedClient(null);
      setClientName("");
      setScheduledTime("07:00");
      setTimezone("Asia/Kolkata");
      setIsActive(true);
      setRecipients("");
      setSections([{ name: "Brand Mentions", keywords: "" }]);
      setContext("");
    }
    setIsModalOpen(true);
  };

  const handleAddSection = () => {
    setSections([...sections, { name: "", keywords: "" }]);
  };

  const handleRemoveSection = (index) => {
    setSections(sections.filter((_, i) => i !== index));
  };

  const handleSectionChange = (index, field, value) => {
    const updated = [...sections];
    updated[index][field] = value;
    setSections(updated);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const token = localStorage.getItem("token");
    
    // Parse recipients
    const recipientsList = recipients
      .split(",")
      .map(r => r.trim())
      .filter(r => r.length > 0);
      
    // Parse sections
    const sectionsList = sections
      .filter(s => s.name.trim().length > 0)
      .map(s => ({
        name: s.name.trim(),
        keywords: s.keywords.split(",").map(k => k.trim()).filter(k => k.length > 0)
      }));

    const payload = {
      name: clientName.trim(),
      scheduled_time: scheduledTime,
      timezone: timezone,
      is_active: isActive,
      recipients: recipientsList,
      sections: sectionsList,
      context: context.trim()
    };

    try {
      const url = selectedClient ? `clients/${selectedClient.id}` : "clients/";
      if (selectedClient) {
        await api.put(url, payload);
      } else {
        await api.post(url, payload);
      }
      setIsModalOpen(false);
      fetchClients();
    } catch (err) {
      console.error("Failed to save client", err);
      alert(err.message || "Something went wrong");
    }
  };

  const handleDeleteClient = async (id) => {
    if (!confirm("Are you sure you want to delete this client? This will delete all its sections, keywords, templates, and history logs.")) return;
    try {
      await api.delete(`clients/${id}`);
      fetchClients();
    } catch (err) {
      console.error("Failed to delete client", err);
    }
  };

  const handleRunNow = async (client) => {
    try {
      await api.post(`clients/${client.id}/run`);
      // Automatically show run logs side overlay in real-time
      handleViewLogs(client);
    } catch (err) {
      console.error("Failed to trigger client run", err);
      alert("Failed to trigger report task.");
    }
  };

  const handleViewLogs = async (client) => {
    setLogsClient(client);
    setLogsLoading(true);
    try {
      const data = await api.get(`clients/${client.id}/logs`);
      setLogs(data);
    } catch (err) {
      console.error("Failed to fetch logs", err);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleUploadTemplate = async (clientId, file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".docx")) {
      alert("Only Microsoft Word (.docx) templates are supported.");
      return;
    }

    setUploadingTemplateId(clientId);
    const formData = new FormData();
    formData.append("file", file);

    try {
      await api.post(`clients/${clientId}/template`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });
      alert("Template document uploaded successfully!");
      fetchClients();
    } catch (err) {
      console.error("Failed to upload template", err);
      alert("Failed to upload template.");
    } finally {
      setUploadingTemplateId(null);
    }
  };

  const handleDownloadTemplate = (clientId) => {
    const token = localStorage.getItem("token");
    const baseUrl = apiClient.defaults.baseURL || "/api/";
    const url = `${baseUrl}${baseUrl.endsWith("/") ? "" : "/"}clients/${clientId}/template?query_token=${token}`;
    window.open(url, "_blank");
  };

  const handleDeleteTemplate = async (clientId) => {
    if (!window.confirm("Are you sure you want to delete this custom template and revert to the Default System Theme?")) {
      return;
    }
    try {
      await api.delete(`clients/${clientId}/template`);
      alert("Custom template deleted successfully!");
      fetchClients();
    } catch (err) {
      console.error("Failed to delete template", err);
      alert("Failed to delete template.");
    }
  };

  const handleDownloadReport = async (filePath) => {
    // Google Drive URL — export directly as DOCX without going through the backend
    if (filePath && filePath.startsWith("https://")) {
      const match = filePath.match(/\/document\/d\/([a-zA-Z0-9_-]+)/);
      if (match) {
        const exportUrl = `https://docs.google.com/document/d/${match[1]}/export?format=docx`;
        window.open(exportUrl, "_blank");
      } else {
        window.open(filePath, "_blank");
      }
      return;
    }
    // Legacy: local filename served from backend /reports/{filename}
    try {
      const blob = await apiClient.get(`clients/reports/${filePath}`, {
        responseType: "blob"
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filePath;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      console.error("Failed to download file", err);
      alert("Failed to download file. It may have been cleared or expired.");
    }
  };

  return (
    <div style={{ padding: "24px", minHeight: "100%", color: "var(--text)" }}>
      {/* Header section */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "24px" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "28px", fontWeight: "800", background: "linear-gradient(90deg, var(--accent) 0%, #a855f7 100%)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
            Client Automation Center
          </h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "14px", color: "var(--text-muted)" }}>
            Configure client scheduled reports, customize word document templates, and trigger manual briefing emails.
          </p>
        </div>
        <button
          onClick={() => handleOpenModal()}
          className="btn btn-primary"
          style={{
            background: "linear-gradient(135deg, var(--accent) 0%, #9333ea 100%)",
            color: "#fff",
            border: "none",
            padding: "10px 20px",
            borderRadius: "12px",
            fontWeight: "700",
            cursor: "pointer",
            boxShadow: "0 4px 12px rgba(147, 51, 234, 0.3)",
            transition: "transform 0.2s, box-shadow 0.2s"
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-2px)";
            e.currentTarget.style.boxShadow = "0 6px 16px rgba(147, 51, 234, 0.4)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "0 4px 12px rgba(147, 51, 234, 0.3)";
          }}
        >
          + Add Client Profile
        </button>
      </div>

      {/* Stats Cards grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "16px", padding: "16px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: "12px", fontWeight: "700", color: "var(--text-muted)", textTransform: "uppercase" }}>Active Clients</div>
          <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--accent)", marginTop: "8px" }}>
            {clients.filter(c => c.is_active).length}
          </div>
        </div>
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "16px", padding: "16px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: "12px", fontWeight: "700", color: "var(--text-muted)", textTransform: "uppercase" }}>Configured Sections</div>
          <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--accent)", marginTop: "8px" }}>
            {clients.reduce((sum, c) => sum + c.sections.length, 0)}
          </div>
        </div>
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "16px", padding: "16px", boxShadow: "var(--shadow)" }}>
          <div style={{ fontSize: "12px", fontWeight: "700", color: "var(--text-muted)", textTransform: "uppercase" }}>Total Recipients</div>
          <div style={{ fontSize: "28px", fontWeight: "800", color: "var(--accent)", marginTop: "8px" }}>
            {clients.reduce((sum, c) => sum + c.recipients.length, 0)}
          </div>
        </div>
      </div>

      {/* Main clients dashboard layout */}
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "48px" }}>
          <div className="spinner" style={{ width: "32px", height: "32px" }} />
        </div>
      ) : clients.length === 0 ? (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "16px", padding: "48px", textAlign: "center" }}>
          <div style={{ fontSize: "48px", marginBottom: "16px" }}>📡</div>
          <h3 style={{ margin: 0 }}>No automated clients configured yet</h3>
          <p style={{ color: "var(--text-muted)", maxWidth: "400px", margin: "8px auto 16px auto" }}>
            Get started by adding a client, setting up keywords, and specifying scheduled daily briefing times.
          </p>
          <button className="btn btn-primary" onClick={() => handleOpenModal()}>
            Create First Client
          </button>
        </div>
      ) : (
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "16px", overflow: "hidden", boxShadow: "var(--shadow)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
            <thead>
              <tr style={{ background: "rgba(255, 255, 255, 0.02)", borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: "16px", fontSize: "12px", fontWeight: "800", color: "var(--text-muted)", textTransform: "uppercase" }}>Client Name</th>
                <th style={{ padding: "16px", fontSize: "12px", fontWeight: "800", color: "var(--text-muted)", textTransform: "uppercase" }}>Schedule</th>
                <th style={{ padding: "16px", fontSize: "12px", fontWeight: "800", color: "var(--text-muted)", textTransform: "uppercase" }}>Sections & Keywords</th>
                <th style={{ padding: "16px", fontSize: "12px", fontWeight: "800", color: "var(--text-muted)", textTransform: "uppercase" }}>Template</th>
                <th style={{ padding: "16px", fontSize: "12px", fontWeight: "800", color: "var(--text-muted)", textTransform: "uppercase" }}>Last Execution</th>
                <th style={{ padding: "16px", fontSize: "12px", fontWeight: "800", color: "var(--text-muted)", textTransform: "uppercase", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {clients.map(client => (
                <tr key={client.id} style={{ borderBottom: "1px solid var(--border)", transition: "background 0.2s" }}>
                  {/* Client Info */}
                  <td style={{ padding: "16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                      <div style={{
                        width: "10px",
                        height: "10px",
                        borderRadius: "50%",
                        background: client.is_active ? "var(--success)" : "var(--text-muted)"
                      }} />
                      <div>
                        <div style={{ fontWeight: "700", fontSize: "16px" }}>{client.name}</div>
                        <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
                          {client.recipients.length} Recipient(s)
                        </div>
                      </div>
                    </div>
                  </td>
                  {/* Schedule */}
                  <td style={{ padding: "16px" }}>
                    <div style={{ fontWeight: "600" }}>⏰ {client.scheduled_time}</div>
                    <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>{client.timezone}</div>
                  </td>
                  {/* Sections and Keywords */}
                  <td style={{ padding: "16px", maxWidth: "300px" }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                      {client.sections.map(sec => (
                        <div
                          key={sec.id}
                          style={{
                            background: "rgba(255,255,255,0.04)",
                            border: "1px solid var(--border)",
                            borderRadius: "8px",
                            padding: "4px 8px",
                            fontSize: "11px"
                          }}
                          title={sec.keywords.join(", ")}
                        >
                          <span style={{ fontWeight: "700", color: "var(--accent)" }}>{sec.name}:</span>{" "}
                          <span style={{ color: "var(--text-muted)" }}>{sec.keywords.length} keywords</span>
                        </div>
                      ))}
                    </div>
                  </td>
                  {/* DOCX Template status */}
                  <td style={{ padding: "16px" }}>
                    {client.template_path ? (
                      <div style={{ fontSize: "13px", display: "flex", flexDirection: "column", gap: "4px" }}>
                        <span style={{ color: "var(--success)" }}>✓ Customized Template</span>
                        <div style={{ display: "flex", gap: "8px" }}>
                          <span
                            onClick={() => handleDownloadTemplate(client.id)}
                            style={{ fontSize: "10px", color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }}
                          >
                            Download
                          </span>
                          <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>|</span>
                          <label style={{ fontSize: "10px", color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }}>
                            {uploadingTemplateId === client.id ? "Replacing..." : "Replace"}
                            <input
                              type="file"
                              accept=".docx"
                              style={{ display: "none" }}
                              disabled={uploadingTemplateId === client.id}
                              onChange={(e) => handleUploadTemplate(client.id, e.target.files[0])}
                            />
                          </label>
                          <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>|</span>
                          <span
                            onClick={() => handleDeleteTemplate(client.id)}
                            style={{ fontSize: "10px", color: "var(--danger)", cursor: "pointer", textDecoration: "underline" }}
                          >
                            Delete
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div style={{ fontSize: "13px", display: "flex", flexDirection: "column", gap: "4px" }}>
                        <span style={{ color: "var(--text-muted)" }}>Default System Theme</span>
                        <label style={{ fontSize: "10px", color: "var(--accent)", cursor: "pointer", textDecoration: "underline" }}>
                          {uploadingTemplateId === client.id ? "Uploading..." : "Upload .docx Theme"}
                          <input
                            type="file"
                            accept=".docx"
                            style={{ display: "none" }}
                            disabled={uploadingTemplateId === client.id}
                            onChange={(e) => handleUploadTemplate(client.id, e.target.files[0])}
                          />
                        </label>
                      </div>
                    )}
                  </td>
                  {/* Last Run Time */}
                  <td style={{ padding: "16px", fontSize: "13px" }}>
                    {client.last_run_at ? (
                      new Date(client.last_run_at).toLocaleString("en-IN", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit"
                      })
                    ) : (
                      <span style={{ color: "var(--text-muted)" }}>Never run yet</span>
                    )}
                  </td>
                  {/* Actions Column */}
                  <td style={{ padding: "16px", textAlign: "right" }}>
                    <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                      <button
                        onClick={() => handleRunNow(client)}
                        className="btn btn-secondary"
                        style={{ padding: "6px 12px", fontSize: "12px", background: "rgba(168, 85, 247, 0.1)", border: "1px solid rgba(168, 85, 247, 0.3)" }}
                        title="Run automated briefing now"
                      >
                        ⚡ Run Now
                      </button>
                      <button
                        onClick={() => handleViewLogs(client)}
                        className="btn btn-secondary"
                        style={{ padding: "6px 12px", fontSize: "12px" }}
                      >
                        📋 Logs
                      </button>
                      <button
                        onClick={() => handleOpenModal(client)}
                        className="btn btn-secondary"
                        style={{ padding: "6px 12px", fontSize: "12px" }}
                      >
                        ✎ Edit
                      </button>
                      <button
                        onClick={() => handleDeleteClient(client.id)}
                        className="btn btn-danger"
                        style={{ padding: "6px 12px", fontSize: "12px" }}
                      >
                        ✕ Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Log view side overlay */}
      {logsClient && (
        <div style={{
          position: "fixed",
          top: 0,
          right: 0,
          width: "480px",
          height: "100vh",
          background: "var(--bg)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "-10px 0 30px rgba(0,0,0,0.3)",
          zIndex: 1000,
          padding: "24px",
          display: "flex",
          flexDirection: "column"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
            <h3 style={{ margin: 0 }}>Run History: {logsClient.name}</h3>
            <button
              onClick={() => setLogsClient(null)}
              style={{ background: "none", border: "none", fontSize: "20px", color: "var(--text-muted)", cursor: "pointer" }}
            >
              ✕
            </button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "12px" }}>
            {logsLoading ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "24px" }}>
                <div className="spinner" style={{ width: "24px", height: "24px" }} />
              </div>
            ) : logs.length === 0 ? (
              <div style={{ color: "var(--text-muted)", textAlign: "center", padding: "24px" }}>
                No execution logs found for this client.
              </div>
            ) : (
              logs.map(log => (
                <div
                  key={log.id}
                  style={{
                    background: "rgba(255,255,255,0.02)",
                    border: "1px solid var(--border)",
                    borderRadius: "12px",
                    padding: "12px"
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <span style={{
                      padding: "3px 8px",
                      borderRadius: "6px",
                      fontSize: "10px",
                      fontWeight: "800",
                      textTransform: "uppercase",
                      background: log.status === "completed" ? "rgba(34, 197, 94, 0.15)" : log.status === "running" ? "rgba(59, 130, 246, 0.15)" : "rgba(239, 68, 68, 0.15)",
                      color: log.status === "completed" ? "var(--success)" : log.status === "running" ? "#3b82f6" : "var(--danger)"
                    }}>
                      {log.status}
                    </span>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                      {new Date(log.started_at).toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                      {log.completed_at && (
                        <> | Duration: <strong>{((new Date(log.completed_at).getTime() - new Date(log.started_at).getTime()) / 60000).toFixed(1)} min</strong></>
                      )}
                    </span>
                  </div>

                  {(() => {
                    const progressInfo = parseProgressLog(log.progress_message, log.started_at, log.completed_at, log.status, logsClient?.sections || []);
                    return (
                      <>
                        {/* Beautiful horizontal progress loader */}
                        {log.progress_message && (
                          <div style={{ marginBottom: "14px", marginTop: "4px" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px", marginBottom: "4px" }}>
                              <span style={{ fontWeight: "700", color: "var(--text)", display: "flex", alignItems: "center", gap: "6px" }}>
                                {log.status === "running" ? (
                                  <>
                                    <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "var(--accent)", display: "inline-block", animation: "pulse 1.5s infinite" }}></span>
                                    <span>Processing Client Report Run...</span>
                                  </>
                                ) : log.status === "completed" ? (
                                  <span>✅ Report Generated Successfully</span>
                                ) : (
                                  <span>⚠️ Job Failed / Interrupted</span>
                                )}
                              </span>
                              <span style={{ fontFamily: "monospace", fontWeight: "700", color: log.status === "completed" ? "var(--success)" : log.status === "failed" ? "var(--danger)" : "var(--accent)" }}>
                                {progressInfo.progress}%
                              </span>
                            </div>
                            
                            {/* Bar Track */}
                            <div style={{
                              width: "100%",
                              height: "6px",
                              background: "rgba(255, 255, 255, 0.05)",
                              border: "1px solid var(--border)",
                              borderRadius: "100px",
                              overflow: "hidden",
                              position: "relative"
                            }}>
                              <div style={{
                                width: `${progressInfo.progress}%`,
                                height: "100%",
                                background: log.status === "completed" 
                                  ? "linear-gradient(90deg, #22c55e 0%, #4ade80 100%)" 
                                  : log.status === "failed" 
                                    ? "linear-gradient(90deg, #ef4444 0%, #f87171 100%)" 
                                    : "linear-gradient(90deg, var(--accent) 0%, #a855f7 100%)",
                                borderRadius: "100px",
                                transition: "width 0.4s ease-out",
                                boxShadow: log.status === "running" ? "0 0 6px rgba(168, 85, 247, 0.4)" : "none"
                              }} className={log.status === "running" ? "progress-bar-animated" : ""} />
                            </div>

                            {/* Detailed stats & estimates */}
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "var(--text-muted)", marginTop: "6px" }}>
                              <span>
                                {progressInfo.total > 0 ? (
                                  <>Discovered articles: <strong>{progressInfo.total}</strong></>
                                ) : (
                                  <span>Initializing database/discovery...</span>
                                )}
                              </span>
                              {log.status === "running" && progressInfo.total > 0 && (
                                <span>
                                  Scraped: <strong>{progressInfo.current} / {progressInfo.total}</strong>
                                  {progressInfo.estimatedSeconds > 0 && (
                                    <> | Est. remaining: <strong>~{(progressInfo.estimatedSeconds / 60).toFixed(1)} min</strong></>
                                  )}
                                </span>
                              )}
                            </div>

                            {/* Sections Progress Panel */}
                            {progressInfo.sections && progressInfo.sections.length > 0 && (
                              <div style={{
                                display: "flex",
                                flexDirection: "column",
                                gap: "8px",
                                marginTop: "12px",
                                borderTop: "1px dashed rgba(255,255,255,0.08)",
                                paddingTop: "12px"
                              }}>
                                <div style={{ fontSize: "10px", fontWeight: "800", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "2px" }}>
                                  Sections Progress
                                </div>
                                {progressInfo.sections.map((sec, sIdx) => {
                                  const isCompleted = sec.status === "completed";
                                  const isProcessing = sec.status === "processing";
                                  const isDiscovering = sec.status === "discovering";
                                  const isPending = sec.status === "pending";

                                  const badgeBg = isCompleted 
                                    ? "rgba(34, 197, 94, 0.12)" 
                                    : (isProcessing || isDiscovering) 
                                      ? "rgba(168, 85, 247, 0.12)" 
                                      : "rgba(255, 255, 255, 0.04)";
                                  const badgeColor = isCompleted 
                                    ? "var(--success)" 
                                    : (isProcessing || isDiscovering) 
                                      ? "var(--accent)" 
                                      : "var(--text-muted)";

                                  return (
                                    <div
                                      key={sIdx}
                                      style={{
                                        background: "rgba(255,255,255,0.01)",
                                        border: "1px solid rgba(255,255,255,0.03)",
                                        borderRadius: "8px",
                                        padding: "8px 10px"
                                      }}
                                    >
                                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                                        <span style={{ fontSize: "11px", fontWeight: "600", color: isPending ? "var(--text-muted)" : "var(--text)" }}>
                                          {sec.name}
                                        </span>
                                        <span style={{
                                          padding: "2px 6px",
                                          borderRadius: "4px",
                                          fontSize: "9px",
                                          fontWeight: "700",
                                          textTransform: "uppercase",
                                          background: badgeBg,
                                          color: badgeColor
                                        }}>
                                          {sec.status}
                                        </span>
                                      </div>

                                      {/* Small compact progress bar */}
                                      <div style={{
                                        width: "100%",
                                        height: "4px",
                                        background: "rgba(255, 255, 255, 0.03)",
                                        borderRadius: "4px",
                                        overflow: "hidden",
                                        position: "relative",
                                        marginBottom: "6px"
                                      }}>
                                        <div style={{
                                          width: `${sec.progress}%`,
                                          height: "100%",
                                          background: isCompleted 
                                            ? "linear-gradient(90deg, #22c55e 0%, #4ade80 100%)" 
                                            : isPending 
                                              ? "rgba(255, 255, 255, 0.05)" 
                                              : "linear-gradient(90deg, var(--accent) 0%, #a855f7 100%)",
                                          borderRadius: "4px",
                                          transition: "width 0.4s ease-out"
                                        }} />
                                      </div>

                                      {/* Counts and Relevance stats */}
                                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "var(--text-muted)" }}>
                                        <span>
                                          Discovered: <strong>{sec.discovered}</strong>
                                        </span>
                                        {isCompleted ? (
                                          <span style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                                            Relevant (Added to brief): <strong style={{ color: "var(--success)" }}>{sec.relevant}</strong>
                                          </span>
                                        ) : isProcessing ? (
                                          <span>
                                            Scraped: <strong>{sec.processed} / {sec.discovered}</strong>
                                          </span>
                                        ) : null}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}

                        {progressInfo.filteredLog && (
                          <div style={{
                            background: "#0b0c10",
                            border: "1px solid rgba(147, 51, 234, 0.2)",
                            borderRadius: "8px",
                            overflow: "hidden",
                            marginBottom: "8px",
                            boxShadow: "inset 0 0 12px rgba(0,0,0,0.85)"
                          }}>
                            {/* Terminal window title bar */}
                            <div style={{
                              background: "rgba(255,255,255,0.02)",
                              borderBottom: "1px solid rgba(255,255,255,0.05)",
                              padding: "6px 12px",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between"
                            }}>
                              <div style={{ display: "flex", gap: "6px" }}>
                                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#ef4444", display: "inline-block" }}></span>
                                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#eab308", display: "inline-block" }}></span>
                                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#22c55e", display: "inline-block" }}></span>
                              </div>
                              <span style={{ fontSize: "9px", fontFamily: "monospace", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "1px", fontWeight: "700" }}>
                                Console Trace
                              </span>
                            </div>
                            
                            {/* Terminal Content */}
                            <div style={{ 
                              fontSize: "11px", 
                              color: "#34d399", 
                              padding: "12px", 
                              fontFamily: "Fira Code, Consolas, Monaco, Courier New, monospace",
                              whiteSpace: "pre-wrap",
                              maxHeight: "185px",
                              overflowY: "auto",
                              lineHeight: "1.6",
                              textAlign: "left"
                            }}>
                              {progressInfo.filteredLog}
                            </div>
                          </div>
                        )}
                      </>
                    );
                  })()}

                  {log.error_message && (
                    <div style={{
                      fontSize: "11px", 
                      color: "#f87171", 
                      background: "rgba(239, 68, 68, 0.05)", 
                      border: "1px solid rgba(239, 68, 68, 0.2)",
                      padding: "10px", 
                      borderRadius: "8px", 
                      fontFamily: "Fira Code, Consolas, Monaco, Courier New, monospace", 
                      overflowX: "auto", 
                      marginBottom: "8px",
                      textAlign: "left"
                    }}>
                      <span style={{ fontWeight: "700" }}>⚠️ Error:</span> {log.error_message}
                    </div>
                  )}

                  {log.generated_file_path && (
                    <button
                      onClick={() => handleDownloadReport(log.generated_file_path)}
                      className="btn btn-secondary"
                      style={{ 
                        width: "100%", 
                        padding: "8px", 
                        fontSize: "12px", 
                        textAlign: "center",
                        background: "rgba(147, 51, 234, 0.15)",
                        border: "1px solid rgba(147, 51, 234, 0.35)",
                        color: "#fff",
                        fontWeight: "600",
                        borderRadius: "8px",
                        cursor: "pointer",
                        transition: "all 0.25s",
                        marginTop: "4px"
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = "rgba(147, 51, 234, 0.25)";
                        e.currentTarget.style.borderColor = "var(--accent)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = "rgba(147, 51, 234, 0.15)";
                        e.currentTarget.style.borderColor = "rgba(147, 51, 234, 0.35)";
                      }}
                    >
                      💾 Download DOCX Briefing
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Edit/Create Client dialog modal */}
      {isModalOpen && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          width: "100vw",
          height: "100vh",
          background: "rgba(0,0,0,0.6)",
          backdropFilter: "blur(4px)",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          zIndex: 1000
        }}>
          <div style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: "16px",
            width: "560px",
            maxHeight: "90vh",
            overflowY: "auto",
            padding: "24px",
            boxShadow: "0 20px 40px rgba(0,0,0,0.5)"
          }}>
            <h3 style={{ margin: "0 0 16px 0" }}>
              {selectedClient ? "Edit Client Profile" : "Create New Client Profile"}
            </h3>

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              {/* Client Name */}
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label className="form-label">Client Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Scapia"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  className="form-control"
                />
              </div>

              {/* Schedule Configuration */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <label className="form-label">Scheduled Run Time (Daily)</label>
                  <input
                    type="time"
                    required
                    value={scheduledTime}
                    onChange={(e) => setScheduledTime(e.target.value)}
                    className="form-control"
                  />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <label className="form-label">Target Timezone</label>
                  <select
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="form-control"
                    style={{ height: "38px" }}
                  >
                    <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                    <option value="Europe/London">Europe/London (GMT)</option>
                    <option value="US/Eastern">US/Eastern (EST)</option>
                    <option value="Asia/Dubai">Asia/Dubai (GST)</option>
                  </select>
                </div>
              </div>

              {/* Recipients List */}
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label className="form-label">Email Recipients</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. hello@mavericks.com, tech@mavericks.com"
                  value={recipients}
                  onChange={(e) => setRecipients(e.target.value)}
                  className="form-control"
                />
                <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>Separate multiple email addresses with commas.</span>
              </div>

              {/* AI Relevance Context */}
              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <label className="form-label">AI Relevance Context / Brand Guidelines</label>
                <textarea
                  rows="4"
                  placeholder="e.g. Scapia is a travel fintech credit card company. Focus on travel cards, forex fees, RBI credit guidelines, and competitor products like Niyo or OneCard. Filter out generic lifestyle travel news."
                  value={context}
                  onChange={(e) => setContext(e.target.value)}
                  className="form-control"
                  style={{ resize: "vertical", fontFamily: "inherit", padding: "8px" }}
                />
                <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>This detailed context is used by the AI to filter out noise and only keep relevant articles.</span>
              </div>

              {/* Active Toggle */}
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <input
                  type="checkbox"
                  id="active_checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  style={{ width: "16px", height: "16px" }}
                />
                <label htmlFor="active_checkbox" style={{ fontSize: "13px", fontWeight: "700", cursor: "pointer" }}>
                  Enable automatic daily briefing schedule
                </label>
              </div>

              {/* Sections & Keywords Configuration */}
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: "16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                  <label className="form-label" style={{ fontSize: "13px" }}>Briefing Sections</label>
                  <button
                    type="button"
                    onClick={handleAddSection}
                    className="btn btn-secondary"
                    style={{ padding: "4px 10px", fontSize: "11px" }}
                  >
                    + Add Section
                  </button>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "12px", maxHeight: "240px", overflowY: "auto", paddingRight: "4px" }}>
                  {sections.map((section, index) => (
                    <div
                      key={index}
                      style={{
                        background: "rgba(255,255,255,0.01)",
                        border: "1px solid var(--border)",
                        borderRadius: "12px",
                        padding: "12px",
                        position: "relative"
                      }}
                    >
                      {sections.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveSection(index)}
                          style={{
                            position: "absolute",
                            top: "8px",
                            right: "8px",
                            background: "none",
                            border: "none",
                            color: "var(--danger)",
                            cursor: "pointer",
                            fontSize: "14px"
                          }}
                        >
                          ✕
                        </button>
                      )}

                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                          <label className="form-label">Section Heading</label>
                          <input
                            type="text"
                            required
                            placeholder="e.g. Scapia in News"
                            value={section.name}
                            onChange={(e) => handleSectionChange(index, "name", e.target.value)}
                            className="form-control"
                          />
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                          <label className="form-label">Search Keywords (comma-separated)</label>
                          <input
                            type="text"
                            required
                            placeholder="e.g. Scapia, Scapia Card, Federal Bank Scapia"
                            value={section.keywords}
                            onChange={(e) => handleSectionChange(index, "keywords", e.target.value)}
                            className="form-control"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Submit & Cancel Actions */}
              <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end", borderTop: "1px solid var(--border)", paddingTop: "16px", marginTop: "8px" }}>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="btn btn-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  style={{ background: "linear-gradient(135deg, var(--accent) 0%, #9333ea 100%)", color: "#fff" }}
                >
                  Save Profile
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
