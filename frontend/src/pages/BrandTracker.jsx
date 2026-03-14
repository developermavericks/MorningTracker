import { useState, useEffect, useMemo } from "react";
import { getHeaders } from "../utils/apiUtils";

export default function BrandTracker({ onNavigate }) {
    const [brands, setBrands] = useState([]);
    const [newBrand, setNewBrand] = useState("");
    const [newKeywords, setNewKeywords] = useState("");
    const [loading, setLoading] = useState(false);
    const [msg, setMsg] = useState(null);
    const [days, setDays] = useState(30);
    const [search, setSearch] = useState("");
    const [newRegion, setNewRegion] = useState("india");
    const [downloading, setDownloading] = useState(null);
    const [editingBrand, setEditingBrand] = useState(null);

    const regions = [
        { id: "global", label: "Global" },
        { id: "india", label: "India" },
        { id: "usa", label: "USA" },
        { id: "uk", label: "UK" },
        { id: "canada", label: "Canada" },
        { id: "japan", label: "Japan" },
        { id: "australia", label: "Australia" },
        { id: "europe", label: "Europe" }
    ];

    useEffect(() => {
        fetchBrands();
    }, []);

    const fetchBrands = async () => {
        try {
            const res = await fetch("/api/brands/", { headers: getHeaders() });
            const data = await res.json();
            setBrands(Array.isArray(data) ? data : []);
        } catch (err) {
            console.error("Failed to fetch brands", err);
        }
    };

    const addBrand = async () => {
        if (!newBrand.trim()) return;
        try {
            const res = await fetch("/api/brands/", {
                method: "POST",
                headers: getHeaders(),
                body: JSON.stringify({ 
                    name: newBrand.trim(),
                    keywords: newKeywords.trim() || null,
                    region: newRegion
                }),
            });
            if (res.ok) {
                setNewBrand("");
                setNewKeywords("");
                fetchBrands();
                setMsg({ type: "success", text: "Brand added to watchlist." });
            } else {
                const err = await res.json();
                setMsg({ type: "error", text: err.detail || "Failed to add brand" });
            }
        } catch (err) {
            setMsg({ type: "error", text: "Connection error" });
        }
    };

    const updateBrandNode = async (name, keywords, region) => {
        try {
            const res = await fetch(`/api/brands/${encodeURIComponent(name)}`, {
                method: "PUT",
                headers: getHeaders(),
                body: JSON.stringify({ name, keywords, region }),
            });
            if (res.ok) {
                setEditingBrand(null);
                fetchBrands();
                setMsg({ type: "success", text: "Brand configuration updated." });
            }
        } catch (err) {
            console.error(err);
        }
    };

    const handleDownload = (name) => {
        const from = prompt("Enter Start Date (YYYY-MM-DD) or leave empty for all time:", "");
        if (from === null) return;
        const to = prompt("Enter End Date (YYYY-MM-DD) or leave empty for all time:", "");
        if (to === null) return;

        let url = `/api/brands/download/${encodeURIComponent(name)}/excel?token=${localStorage.getItem('token')}`;
        if (from) url += `&date_from=${from}`;
        if (to) url += `&date_to=${to}`;
        
        window.open(url, '_blank');
    };

    const deleteBrand = async (name) => {
        if (!window.confirm(`Stop tracking ${name}?`)) return;
        try {
            await fetch(`/api/brands/${encodeURIComponent(name)}`, { 
                method: "DELETE",
                headers: getHeaders()
            });
            fetchBrands();
        } catch (err) {
            console.error(err);
        }
    };

    const startScrape = async () => {
        setLoading(true);
        setMsg(null);
        try {
            const res = await fetch(`/api/brands/scrape?days=${days}`, { 
                method: "POST",
                headers: getHeaders()
            });
            const data = await res.json();
            if (res.ok) {
                setMsg({ type: "success", text: `Scrape mission initiated for ${brands.length} brands.` });
            } else {
                setMsg({ type: "error", text: data.detail || "Failed to start scrape" });
            }
        } catch (err) {
            setMsg({ type: "error", text: "Connection error" });
        } finally {
            setLoading(false);
        }
    };

    const startIndividualScrape = async (name) => {
        setMsg(null);
        try {
            const res = await fetch(`/api/brands/scrape/${encodeURIComponent(name)}?days=${days}`, { 
                method: "POST",
                headers: getHeaders()
            });
            const data = await res.json();
            if (res.ok) {
                setMsg({ type: "success", text: `Scrape initiated for ${name}.` });
            } else {
                setMsg({ type: "error", text: data.detail || "Failed to start scrape" });
            }
        } catch (err) {
            setMsg({ type: "error", text: "Connection error" });
        }
    };

    const filteredBrands = useMemo(() => {
        return brands.filter(b => b.name.toLowerCase().includes(search.toLowerCase()));
    }, [brands, search]);

    return (
        <div className="page-container">
            <header className="page-header" style={{ marginBottom: '40px' }}>
                <div>
                    <h1 className="page-title">Portfolio Monitoring</h1>
                    <p className="page-subtitle">Strategic intelligence for specific brand nodes</p>
                </div>
            </header>

            {msg && (
                <div className={`alert ${msg.type === "error" ? "alert-error" : "alert-success"}`} style={{ marginBottom: '32px' }}>
                    {msg.text}
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 350px', gap: '32px', marginBottom: '32px', alignItems: 'start' }}>
                <div className="card" style={{ boxShadow: 'var(--glow)', border: 'none' }}>
                    <div className="card-title" style={{ marginBottom: '24px' }}>Watchlist Configuration</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                        <div style={{ display: "flex", gap: "16px" }}>
                            <input
                                type="text"
                                className="form-control"
                                placeholder="Brand Name"
                                value={newBrand}
                                onChange={(e) => setNewBrand(e.target.value)}
                                style={{ flex: 1.5, height: '48px' }}
                            />
                            <select 
                                className="form-control"
                                value={newRegion}
                                onChange={(e) => setNewRegion(e.target.value)}
                                style={{ flex: 1, height: '48px' }}
                            >
                                {regions.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                            </select>
                        </div>
                        <input
                            type="text"
                            className="form-control"
                            placeholder="Keywords (comma separated)"
                            value={newKeywords}
                            onChange={(e) => setNewKeywords(e.target.value)}
                            style={{ width: '100%', height: '48px' }}
                        />
                        <button className="btn btn-primary" onClick={addBrand} style={{ height: '48px', justifyContent: 'center' }}>
                            ⊕ Add Brand Node
                        </button>
                    </div>
                </div>

                <div className="card" style={{ border: 'none', background: 'var(--surface2)' }}>
                    <div className="card-title">Bulk Discovery</div>
                    <div className="form-group">
                        <label className="form-label">Lookback Window</label>
                        <select
                            className="form-control"
                            value={days}
                            onChange={(e) => setDays(e.target.value)}
                            disabled={loading}
                        >
                            <option value={1}>24 Hours</option>
                            <option value={7}>7 Days</option>
                            <option value={30}>30 Days</option>
                        </select>
                    </div>
                    <button
                        className="btn btn-primary"
                        onClick={startScrape}
                        disabled={loading || brands.length === 0}
                        style={{ width: '100%', marginTop: '16px', height: '42px', justifyContent: 'center' }}
                    >
                        {loading ? <div className="spinner" /> : "🚀 Scrape All Brands"}
                    </button>
                </div>
            </div>

            <div className="card" style={{ border: 'none' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                    <div className="card-title" style={{ margin: 0 }}>Active Monitoring ({brands.length})</div>
                    <input 
                        type="text" 
                        className="form-control" 
                        placeholder="Filter watchlist..." 
                        style={{ width: '250px', fontSize: '13px' }}
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>
                
                <div className="table-wrap">
                    <table className="table">
                        <thead>
                            <tr>
                                <th>Brand Node</th>
                                <th>Region</th>
                                <th>Keywords Filter</th>
                                <th>Intelligence</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredBrands.length === 0 ? (
                                <tr><td colSpan="5" className="empty-state">No matching nodes found.</td></tr>
                            ) : (
                                filteredBrands.map((b) => (
                                    <tr key={b.name}>
                                        <td style={{ fontWeight: 600, color: "var(--accent)", fontSize: '15px' }}>
                                            <span style={{ cursor: 'pointer' }} onClick={() => onNavigate('articles', { sector: b.name })}>
                                                {b.name}
                                            </span>
                                        </td>
                                        <td>
                                            {editingBrand === b.name ? (
                                                <select 
                                                    className="form-control"
                                                    style={{ height: '32px', fontSize: '12px' }}
                                                    defaultValue={b.region || "india"}
                                                    onChange={(e) => updateBrandNode(b.name, b.keywords, e.target.value)}
                                                >
                                                    {regions.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                                                </select>
                                            ) : (
                                                <div 
                                                    className="badge" 
                                                    style={{ cursor: 'pointer', background: 'var(--surface2)', color: 'var(--text)', fontSize: '11px', textTransform: 'capitalize' }}
                                                    onClick={() => setEditingBrand(b.name)}
                                                >
                                                    {b.region || "india"}
                                                </div>
                                            )}
                                        </td>
                                        <td>
                                            {editingBrand === b.name ? (
                                                <input 
                                                    autoFocus
                                                    className="form-control"
                                                    style={{ height: '32px', fontSize: '12px' }}
                                                    defaultValue={b.keywords || ""}
                                                    onBlur={(e) => updateBrandNode(b.name, e.target.value, b.region)}
                                                    onKeyDown={(e) => e.key === 'Enter' && updateBrandNode(b.name, e.target.value, b.region)}
                                                />
                                            ) : (
                                                <div 
                                                    style={{ cursor: 'pointer', fontStyle: b.keywords ? 'normal' : 'italic', color: b.keywords ? 'inherit' : 'var(--muted)', fontSize: '12px' }}
                                                    onClick={() => setEditingBrand(b.name)}
                                                >
                                                    {b.keywords || "Click to add keywords..."}
                                                </div>
                                            )}
                                        </td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                                <span className="badge" style={{ background: 'var(--surface2)', color: 'var(--accent)' }}>
                                                    {b.article_count || 0} Articles
                                                </span>
                                            </div>
                                        </td>
                                        <td>
                                            <div style={{ display: "flex", gap: "8px" }}>
                                                <button className="btn btn-primary" onClick={() => startIndividualScrape(b.name)} style={{ padding: '4px 12px', fontSize: '11px' }}>
                                                    🚀 Scrape
                                                </button>
                                                <button className="btn btn-secondary" 
                                                    onClick={() => handleDownload(b.name)}
                                                    style={{ padding: '4px 12px', fontSize: '11px' }}
                                                >
                                                    Excel
                                                </button>
                                                <button className="btn btn-danger" onClick={() => deleteBrand(b.name)} style={{ padding: "4px 12px", fontSize: "11px" }}>
                                                    Remove
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
