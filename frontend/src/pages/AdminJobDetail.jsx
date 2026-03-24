import { useState, useEffect } from "react";
import { api } from "../services/api";

export default function AdminJobDetail({ id, onNavigate }) {
    const [job, setJob] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchJobDetail = async () => {
        setLoading(true);
        try {
            const data = await api.get(`admin/jobs/${id}`);
            setJob(data);
        } catch (err) {
            console.error("Failed to fetch job detail", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (id) fetchJobDetail();
    }, [id]);

    if (loading) return <div className="spinner-container"><div className="spinner" /></div>;
    if (!job) return <div className="error-state">Job not found.</div>;

    const phaseStats = (() => {
        try {
            return job.phase_stats ? (typeof job.phase_stats === 'string' ? JSON.parse(job.phase_stats) : job.phase_stats) : null;
        } catch (e) {
            console.error("Failed to parse phase_stats", e);
            return null;
        }
    })();

    const displayId = typeof job.id === 'string' ? job.id.split('-')[0] : 'UNKNOWN';

    return (
        <div className="page-container" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <header className="page-header" style={{ marginBottom: '40px' }}>
                <button className="btn btn-secondary" onClick={() => onNavigate('admin')} style={{ marginBottom: '16px' }}>← Back to Jobs</button>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 className="page-title">Mission Blueprint: {displayId}</h1>
                        <p className="page-subtitle">Detailed execution log for {job.user_name || 'System'} ({job.sector || 'N/A'})</p>
                    </div>
                    <div className="badge" style={{ 
                        padding: '8px 16px', fontSize: '14px',
                        background: job.status === 'completed' ? 'var(--success-bg)' : 'var(--surface2)',
                        color: job.status === 'completed' ? 'var(--success)' : 'var(--text)'
                    }}>
                        {(job.status || 'unknown').toUpperCase()}
                    </div>
                </div>
            </header>

            <div className="card" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginBottom: '24px', border: 'none' }}>
                <div>
                    <h3 style={{ fontSize: '14px', color: 'var(--muted)', marginBottom: '16px' }}>CONFIGURATION</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>User</span>
                            <span style={{ fontWeight: 600 }}>{job.user_name}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>Sector</span>
                            <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{job.sector}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>Region</span>
                            <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{job.region}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>Mode</span>
                            <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{job.search_mode}</span>
                        </div>
                    </div>
                </div>
                <div>
                    <h3 style={{ fontSize: '14px', color: 'var(--muted)', marginBottom: '16px' }}>EXECUTION</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>Started</span>
                            <span style={{ fontWeight: 600 }}>{new Date(job.started_at).toLocaleString()}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>Completed</span>
                            <span style={{ fontWeight: 600 }}>{job.completed_at ? new Date(job.completed_at).toLocaleString() : 'In Progress'}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>Date Range</span>
                            <span style={{ fontWeight: 600 }}>{job.date_from} to {job.date_to}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: 'var(--muted)' }}>Total Scraped</span>
                            <span style={{ fontWeight: 800, color: 'var(--accent)' }}>{job.total_scraped || 0} Articles</span>
                        </div>
                    </div>
                </div>
            </div>

            {job.error && (
                <div className="alert alert-error" style={{ marginBottom: '24px' }}>
                    <div style={{ fontWeight: 700, marginBottom: '4px' }}>ERROR DETECTED</div>
                    <div style={{ fontSize: '12px' }}>{job.error}</div>
                </div>
            )}

            {phaseStats && (
                <div className="card" style={{ border: 'none' }}>
                    <h3 style={{ fontSize: '14px', color: 'var(--muted)', marginBottom: '16px' }}>PHASE BREAKDOWN</h3>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {Object.entries(phaseStats).map(([phase, count]) => (
                            <div key={phase} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <div style={{ width: '80px', fontSize: '12px', color: 'var(--muted)' }}>PHASE {phase}</div>
                                <div style={{ flex: 1, height: '8px', background: 'var(--surface2)', borderRadius: '4px', overflow: 'hidden' }}>
                                    <div style={{ width: `${Math.min(100, (count / (job.total_scraped || 1)) * 100)}%`, height: '100%', background: 'var(--accent)' }} />
                                </div>
                                <div style={{ width: '40px', fontSize: '12px', textAlign: 'right' }}>{count}</div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
