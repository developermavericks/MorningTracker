import { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ThemeProvider, useTheme } from "./context/ThemeContext";
import Dashboard from "./pages/Dashboard";
import ArticlesBrowser from "./pages/ArticlesBrowser";
import useStore from "./store/useStore";
import BrandTracker from "./pages/BrandTracker";
import Jobs from "./pages/Jobs";
import Diagnostics from "./pages/Diagnostics";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import ErrorBoundary from "./components/ErrorBoundary";
import "./index.css";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: "◈" },
  { id: "articles", label: "Articles", icon: "≡" },
  { id: "brands", label: "Brand Tracker", icon: "🏢" },
  { id: "jobs", label: "Jobs", icon: "◎" },
  { id: "diagnostics", label: "", icon: "" },
];

function ThemeToggle() {
  const { primaryColor, setPrimaryColor } = useTheme();
  
  return (
    <div 
      className="nav-item"
      style={{ 
        position: 'fixed',
        top: '12px',
        left: '12px',
        zIndex: 9999,
        width: 'auto',
        background: 'var(--surface)', 
        border: '1px solid var(--border)',
        boxShadow: 'var(--glow)',
        padding: '6px 12px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        borderRadius: '20px'
      }}
    >
      <span style={{ fontSize: '11px', fontWeight: '800', color: 'var(--accent)' }}>🎨 COLOUR</span>
      <input 
        type="color" 
        value={primaryColor}
        onChange={(e) => setPrimaryColor(e.target.value)}
        style={{ 
          border: 'none',
          width: '24px',
          height: '24px',
          padding: '0',
          background: 'none',
          cursor: 'pointer',
          borderRadius: '4px'
        }}
      />
    </div>
  );
}

function ProtectedApp() {
  const { user, loading, logout } = useAuth();
  const [page, setPage] = useState("dashboard");
  const { stats, jobs, fetchStats, fetchJobs } = useStore();
  const [apiStatus, setApiStatus] = useState("checking");

  useEffect(() => {
    if (!user) return;
    fetchStats();
    fetchJobs();
    
    let ws;
    const connect = () => {
      const token = localStorage.getItem('token');
      if (!token) return;
      
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      // WebSocket MUST connect directly to Railway (Vercel proxy doesn't support WS)
      const target = 'morningtracker-production.up.railway.app';
      ws = new WebSocket(`${protocol}//${target}/api/articles/ws/stats?token=${token}`);
      ws.onopen = () => {
        setApiStatus("online");
        console.log("WebSocket connected to Railway node.");
      };
      ws.onmessage = (msg) => {
        setApiStatus("online");
        const data = JSON.parse(msg.data);
        useStore.setState({ stats: data });
      };
      ws.onerror = () => setApiStatus("offline");
      ws.onclose = () => setTimeout(connect, 10000);
    };
    connect();
    return () => ws && ws.close();
  }, [user]);

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--bg)' }}>
      <div className="spinner" style={{ width: '40px', height: '40px' }} />
    </div>
  );

  if (!user) return <Navigate to="/login" />;

  // Defensive array check for production robustness
  const safeJobs = Array.isArray(jobs) ? jobs : [];
  const activeCount = safeJobs.filter((j) => j.status === "running" || j.status === "pending").length;
  const totalArticles = safeJobs.reduce((sum, j) => sum + (j.total_scraped || 0), 0);
  const statusColor = apiStatus === "online" ? "var(--success)" : "var(--danger)";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand" style={{ marginTop: '40px' }}>
          <div className="brand-icon" style={{ color: 'var(--accent)' }}>✦</div>
          <div>
            <div className="brand-name">NEXUS</div>
            <div className="brand-sub">Intelligence Tracker</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV.map((n) => (
            <button
              key={n.id}
              className={`nav-item ${page === n.id ? "active" : ""}`}
              onClick={() => setPage(n.id)}
            >
              <span className="nav-icon">{n.icon}</span>
              <span>{n.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer" style={{ flexDirection: 'column', gap: '12px', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div className="status-dot" style={{ background: statusColor }} />
                <span style={{ fontSize: '10px' }}>{apiStatus === "online" ? "Connected" : "Offline"}</span>
            </div>
            <button onClick={logout} className="nav-item" style={{ padding: '4px 0', fontSize: '11px', color: 'var(--danger)' }}>
                ✕ Sign Out
            </button>
        </div>
      </aside>

      <main className="main-content">
        {page === "dashboard" && <Dashboard onNavigate={setPage} />}
        {page === "articles" && <ArticlesBrowser />}
        {page === "brands" && <BrandTracker />}
        {page === "jobs" && <Jobs />}
        {page === "diagnostics" && <Diagnostics />}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <Router>
        <ThemeProvider>
          <ThemeToggle />
          <AuthProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              <Route path="/*" element={<ProtectedApp />} />
            </Routes>
          </AuthProvider>
        </ThemeProvider>
      </Router>
    </ErrorBoundary>
  );
}
