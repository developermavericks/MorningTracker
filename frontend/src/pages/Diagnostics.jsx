import { useState, useEffect } from "react";
import { api } from "../services/api";

export default function Diagnostics() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchDiagnostics = async () => {
        try {
            const json = await api.get("/diagnostics/health");
            setData(json);
        } catch (e) {
            console.error(e);
            setData({
                overall: "offline",
                components: {
                    database: { status: "offline", message: "API Unreachable" },
                    groq_api: { status: "offline", message: "API Unreachable" },
                    playwright: { status: "offline", message: "API Unreachable" },
                    jobs: { status: "offline", message: "API Unreachable" }
                },
                recent_log_errors: ["Critical: Connection to Intelligence API lost."]
            });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchDiagnostics();
        const interval = setInterval(fetchDiagnostics, 15000);
        return () => clearInterval(interval);
    }, []);

    const getStatusColor = (status) => {
        switch (status) {
            case "online": return "var(--success)";
            case "rate_limited": return "var(--warning)";
            case "degraded": return "var(--warning)";
            case "error": return "var(--danger)";
            case "offline": return "var(--danger)";
            default: return "var(--muted)";
        }
    };

    if (loading && !data) {
        return (
            <div style={{ textAlign: "center", padding: 100 }}>
                <div className="spinner" style={{ margin: "0 auto", width: 40, height: 40 }} />
                <p style={{ marginTop: 24, color: "var(--muted)", letterSpacing: '0.1em', fontSize: '11px', textTransform: 'uppercase' }}>Scanning System Integrity...</p>
            </div>
        );
    }

    const c = data?.components || {};

    const handleEmergencyStop = async () => {
        const warning = "⚠️ DANGER: This is a destructive action.\n\n" +
                      "This will PURGE all pending tasks and AGGRESSIVELY halt all active scrapes.\n" +
                      "It can crash current operations and cause data inconsistency.\n\n" +
                      "Are you ABSOLUTELY sure you want to proceed?";
        
        if (!window.confirm(warning)) return;

        const phrase = window.prompt("To authorize this action, please enter the authorization phrase:");
        if (!phrase) return;

        try {
            setLoading(true);
            const res = await api.post("/diagnostics/emergency-stop", { phrase });
            alert("Emergency Stop Triggered: " + (res.results?.actions?.join(", ") || "Success"));
            await fetchDiagnostics();
        } catch (e) {
            console.error(e);
            if (e.response?.status === 403) {
                alert("ACCESS DENIED: The authorization phrase was incorrect.");
            } else {
                alert("Failed to trigger emergency stop.");
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="page-container">
            <header className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: '1px solid var(--border)', paddingBottom: '32px', marginBottom: '40px' }}>
                <div>
                    {/* <h1 className="page-title">System Telemetry</h1>
                    <p className="page-subtitle">Real-time health monitoring & component verification</p> */}
                </div>
                <div style={{ display: "flex", gap: "12px" }}>
                    {/* <button className="btn btn-secondary" onClick={fetchDiagnostics} disabled={loading} style={{ background: 'var(--surface)' }}>
                        {loading ? "Refreshing..." : "↻ Forced Sync"}
                    </button> */}
                    <button className="btn btn-danger" onClick={handleEmergencyStop} disabled={loading} style={{ 
                        background: 'var(--danger)', 
                        color: 'white',
                        border: 'none',
                        boxShadow: '0 0 15px rgba(239, 68, 68, 0.4)'
                    }}>
                        {loading ? "Processing..." : "🛑 Emergency Stop"}
                    </button>
                </div>
            </header>

            {/* <div style={{
                padding: "24px",
                marginBottom: 40,
                borderRadius: 'var(--radius)',
                background: 'var(--surface2)',
                borderLeft: `6px solid ${getStatusColor(data?.overall)}`,
                display: "flex",
                alignItems: "center",
                gap: 20,
                boxShadow: 'var(--glow)'
            }}>
                <div className="status-dot" style={{ background: getStatusColor(data?.overall), width: 14, height: 14 }} />
                <div style={{ fontSize: '20px', fontWeight: 600 }}>
                   NEXUS Status: <span style={{ color: getStatusColor(data?.overall), textTransform: "uppercase" }}>{data?.overall || "UNKNOWN"}</span>
                </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 24, marginBottom: 40 }}>
                <div className="card">
                    <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        Core Database
                        <span className="badge" style={{ background: getStatusColor(c.database?.status) }}>{c.database?.status}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: "var(--muted)", marginTop: '12px' }}>
                        Primary storage cluster status and connection health.
                    </div>
                </div>

                <div className="card">
                    <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        NLP Intelligence
                        <span className="badge" style={{ background: getStatusColor(c.groq_api?.status) }}>{c.groq_api?.status}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: "var(--muted)", marginTop: '12px', marginBottom: '20px' }}>
                        Groq API rate limits and token availability.
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, background: "var(--bg)", padding: 16, borderRadius: '8px' }}>
                        <div>
                            <div style={{ fontSize: 9, textTransform: "uppercase", opacity: 0.6 }}>Remaining</div>
                            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>{c.groq_api?.remaining_reqs ?? "—"} reqs</div>
                        </div>
                        <div>
                            <div style={{ fontSize: 9, textTransform: "uppercase", opacity: 0.6 }}>Tokens</div>
                            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>{c.groq_api?.remaining_tokens ?? "—"}</div>
                        </div>
                    </div>
                </div>

                <div className="card">
                    <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        Extraction Grid
                        <span className="badge" style={{ background: getStatusColor(c.jobs?.status) }}>{c.jobs?.status}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: "var(--muted)", marginTop: '12px' }}>
                        Active scraping workers and queuing latency.
                    </div>
                    <div style={{ marginTop: '16px', display: 'flex', gap: '20px' }}>
                        <div style={{ fontSize: '12px' }}>Active: <strong style={{ color: 'var(--accent)' }}>{c.jobs?.running_count || 0}</strong></div>
                        <div style={{ fontSize: '12px' }}>Yield: <strong style={{ color: 'var(--success)' }}>{data?.total_articles_collected || 0}</strong></div>
                    </div>
                </div>

                <div className="card">
                    <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        Browsing Engine
                        <span className="badge" style={{ background: getStatusColor(c.playwright?.status) }}>{c.playwright?.status}</span>
                    </div>
                    <div style={{ fontSize: '13px', color: "var(--muted)", marginTop: '12px' }}>
                        Playwright headless services for high-fidelity extraction.
                    </div>
                </div>
            </div>

            <div className="card" style={{ background: '#1c1917', border: 'none' }}>
                <div className="card-title" style={{ color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '8px' }}>●</span> Intelligence Stream Logs
                </div>
                <div style={{
                    marginTop: '20px',
                    padding: '20px',
                    background: '#0c0a09',
                    borderRadius: '8px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '12px',
                    color: 'var(--muted)',
                    maxHeight: '300px',
                    overflowY: 'auto'
                }}>
                    {data?.recent_log_errors?.length > 0 ? (
                        data.recent_log_errors.map((err, i) => (
                            <div key={i} style={{ paddingBottom: '12px', marginBottom: '12px', borderBottom: '1px solid #292524', color: '#f87171' }}>
                                [{new Date().toLocaleTimeString()}] {err}
                            </div>
                        ))
                    ) : (
                        <div style={{ color: 'var(--success)', opacity: 0.8 }}>✓ All intelligence streams performing within parameters.</div>
                    )}
                </div>
            </div> */}
        </div>
    );

}
