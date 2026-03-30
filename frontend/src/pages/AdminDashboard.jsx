import { useState, useEffect } from "react";
import { api } from "../services/api";

export default function AdminDashboard({ onNavigate }) {
    const [jobs, setJobs] = useState([]);
    const [summary, setSummary] = useState({ total_jobs: 0, total_articles: 0, active_users: 0 });
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [total, setTotal] = useState(0);
    const [filters, setFilters] = useState({
        user_name: "",
        user_email: "",
        brand: "",
        status: ""
    });

    const fetchAdminData = async () => {
        setLoading(true);
        try {
            const data = await api.get("admin/jobs", { ...filters, page, limit: 10, t: Date.now() });
            setJobs(data.jobs);
            setTotal(data.total);
            setSummary(data.summary);
        } catch (err) {
            console.error("ADMIN_ERROR: Failed to fetch data", err);
            alert(`Admin Data Load Failed: ${err.message}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAdminData();
    }, [page, filters]);

    const handleFilterChange = (e) => {
        setFilters({ ...filters, [e.target.name]: e.target.value });
        setPage(1);
    };

    return (
        <div className="page-container">
            <header className="page-header" style={{ marginBottom: '40px' }}>
                <div>
                    <h1 className="page-title">Admin Command Center</h1>
                    <p className="page-subtitle">Global oversight of all intelligence operations</p>
                </div>
            </header>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '24px', marginBottom: '40px' }}>
                <div className="card" style={{ background: 'var(--surface2)', border: 'none' }}>
                    <div style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '8px' }}>TOTAL JOBS</div>
                    <div style={{ fontSize: '32px', fontWeight: '800', color: 'var(--accent)' }}>{summary.total_jobs}</div>
                </div>
                <div className="card" style={{ background: 'var(--surface2)', border: 'none' }}>
                    <div style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '8px' }}>ARTICLES SCRAPED</div>
                    <div style={{ fontSize: '32px', fontWeight: '800', color: 'var(--success)' }}>{summary.total_articles}</div>
                </div>
                <div className="card" style={{ background: 'var(--surface2)', border: 'none' }}>
                    <div style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '8px' }}>ACTIVE USERS</div>
                    <div style={{ fontSize: '32px', fontWeight: '800', color: 'var(--warning)' }}>{summary.active_users}</div>
                </div>
            </div>

            <div className="card" style={{ marginBottom: '32px', border: 'none' }}>
                <div className="card-title">Filter System</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '16px' }}>
                    <input name="user_name" placeholder="User Name" className="form-control" onChange={handleFilterChange} />
                    <input name="user_email" placeholder="User Email" className="form-control" onChange={handleFilterChange} />
                    <input name="brand" placeholder="Brand/Sector" className="form-control" onChange={handleFilterChange} />
                    <select name="status" className="form-control" onChange={handleFilterChange}>
                        <option value="">All Statuses</option>
                        <option value="pending">Pending</option>
                        <option value="running">Running</option>
                        <option value="completed">Completed</option>
                        <option value="failed">Failed</option>
                    </select>
                </div>
            </div>

            <div className="card" style={{ border: 'none' }}>
                <div className="card-title">Global Job Stream</div>
                <div className="table-wrap">
                    <table className="table">
                        <thead>
                            <tr>
                                <th>Timestamp</th>
                                <th>User</th>
                                <th>Brand</th>
                                <th>Region</th>
                                <th>Articles</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr><td colSpan="7" style={{ textAlign: 'center', padding: '40px' }}><div className="spinner" /></td></tr>
                            ) : jobs.length === 0 ? (
                                <tr><td colSpan="7" className="empty-state">No jobs matching criteria.</td></tr>
                            ) : (
                                jobs.map(j => (
                                    <tr key={j.id}>
                                        <td style={{ fontSize: '12px', color: 'var(--muted)' }}>
                                            {new Date(j.started_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                                        </td>
                                        <td>
                                            <div style={{ fontWeight: 600 }}>{j.user_name}</div>
                                            <div style={{ fontSize: '11px', color: 'var(--muted)', cursor: 'pointer' }} 
                                                 onClick={() => onNavigate('admin-user', { email: j.user_email })}>
                                                {j.user_email}
                                            </div>
                                        </td>
                                        <td style={{ textTransform: 'capitalize' }}>{j.sector}</td>
                                        <td style={{ textTransform: 'capitalize' }}>{j.region}</td>
                                        <td>
                                            <span style={{ fontWeight: 700 }}>{j.total_scraped}</span>
                                        </td>
                                        <td>
                                            <div className="badge" style={{ 
                                                background: j.status === 'completed' ? 'var(--success-bg)' : j.status === 'failed' ? 'var(--danger-bg)' : 'var(--surface2)',
                                                color: j.status === 'completed' ? 'var(--success)' : j.status === 'failed' ? 'var(--danger)' : 'var(--text)'
                                            }}>
                                                {j.status}
                                            </div>
                                        </td>
                                        <td>
                                            <button className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '11px' }}
                                                    onClick={() => onNavigate('admin-job', { id: j.id })}>
                                                Inspect
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '24px' }}>
                    <button className="btn btn-secondary" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
                    <span style={{ display: 'flex', alignItems: 'center' }}>Page {page} of {Math.ceil(total / 10)}</span>
                    <button className="btn btn-secondary" disabled={page >= Math.ceil(total / 10)} onClick={() => setPage(p => p + 1)}>Next →</button>
                </div>
            </div>
        </div>
    );
}
