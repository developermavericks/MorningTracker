import { useState, useEffect } from "react";
import { api } from "../services/api";

export default function AdminUserDetail({ email, onNavigate }) {
    const [userData, setUserData] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchUserDetail = async () => {
        setLoading(true);
        try {
            const data = await api.get(`admin/users/${email}/jobs?t=${Date.now()}`);
            setUserData(data);
        } catch (err) {
            console.error("Failed to fetch user detail", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (email) fetchUserDetail();
    }, [email]);

    if (loading) return <div className="spinner-container"><div className="spinner" /></div>;
    if (!userData) return <div className="error-state">User not found or error loading data.</div>;

    return (
        <div className="page-container">
            <header className="page-header" style={{ marginBottom: '40px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <button className="btn btn-secondary" onClick={() => onNavigate('admin')} style={{ marginBottom: '16px' }}>← Back to Dashboard</button>
                    <h1 className="page-title">{userData.user.name}</h1>
                    <p className="page-subtitle">{userData.user.email}</p>
                </div>
                <div style={{ display: 'flex', gap: '24px' }}>
                    <div className="stat-node">
                        <div className="stat-label">TOTAL JOBS</div>
                        <div className="stat-value">{userData.stats.total_jobs}</div>
                    </div>
                    <div className="stat-node">
                        <div className="stat-label">TOTAL ARTICLES</div>
                        <div className="stat-value">{userData.stats.total_articles}</div>
                    </div>
                    <div className="stat-node">
                        <div className="stat-label">TOP BRAND</div>
                        <div className="stat-value" style={{ textTransform: 'capitalize' }}>{userData.stats.most_searched_brand || 'None'}</div>
                    </div>
                </div>
            </header>

            <div className="card" style={{ border: 'none' }}>
                <div className="card-title">Activity Timeline</div>
                <div className="table-wrap">
                    <table className="table">
                        <thead>
                            <tr>
                                <th>Started At</th>
                                <th>Brand</th>
                                <th>Region</th>
                                <th>Lookback</th>
                                <th>Scraped</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {userData.jobs.map(j => (
                                <tr key={j.id}>
                                    <td style={{ fontSize: '12px' }}>{new Date(j.started_at).toLocaleString()}</td>
                                    <td style={{ textTransform: 'capitalize' }}>{j.sector}</td>
                                    <td style={{ textTransform: 'capitalize' }}>{j.region}</td>
                                    <td>{(new Date(j.date_to) - new Date(j.date_from)) / (1000 * 60 * 60 * 24)}d</td>
                                    <td>{j.total_scraped}</td>
                                    <td>
                                        <div className="badge" style={{ 
                                            background: j.status === 'completed' ? 'var(--success-bg)' : j.status === 'failed' ? 'var(--danger-bg)' : 'var(--surface2)',
                                            color: j.status === 'completed' ? 'var(--success)' : j.status === 'failed' ? 'var(--danger)' : 'var(--text)'
                                        }}>
                                            {j.status}
                                        </div>
                                    </td>
                                    <td>
                                        <button className="btn btn-secondary" style={{ padding: '4px 12px', fontSize: '11px' }}
                                                onClick={() => onNavigate('admin-job', { id: j.id })}>
                                            View
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
