import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isShaking, setIsShaking] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login, user } = useAuth();
  const navigate = useNavigate();

  // Redirect if already logged in
  useEffect(() => {
    if (user) navigate('/');
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsShaking(false);
    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err) {
      setIsShaking(true);
      setTimeout(() => setIsShaking(false), 500);

      if (err.response) {
        setError(err.response.data?.detail || 'Invalid credentials. Please try again.');
      } else {
        setError('Connection error. Is the server running?');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    window.location.href = "/api/auth/google";
  };

  return (
    <div style={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center', 
      minHeight: '100vh',
      background: 'radial-gradient(circle at top right, hsla(var(--accent-h), 80%, 80%, 0.1), transparent), radial-gradient(circle at bottom left, hsla(var(--accent-h), 80%, 40%, 0.05), transparent), var(--bg)',
      padding: '24px'
    }}>
      <div className="card" style={{ 
        maxWidth: '440px', 
        width: '100%', 
        padding: '40px',
        boxShadow: 'var(--glow), 0 0 0 1px var(--border)',
        backdropFilter: 'blur(10px)',
        background: 'rgba(255, 255, 255, 0.8)',
        borderRadius: '24px',
        position: 'relative',
        overflow: 'hidden'
      }}>
        {/* Subtle decorative glow */}
        <div style={{ 
          position: 'absolute', 
          top: '-50px', 
          right: '-50px', 
          width: '150px', 
          height: '150px', 
          background: 'var(--accent)', 
          filter: 'blur(100px)', 
          opacity: 0.1 
        }} />

        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <div className="brand-icon" style={{ 
            fontSize: '56px', 
            marginBottom: '16px',
            background: 'linear-gradient(135deg, var(--accent), var(--accent2))',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            display: 'inline-block'
          }}>✦</div>
          <h1 className="page-title" style={{ fontSize: '32px', marginBottom: '4px', letterSpacing: '0.1em' }}>NEXUS</h1>
          <p className="page-subtitle" style={{ fontSize: '11px', fontWeight: '600' }}>INTELLIGENCE OPERATING SYSTEM</p>
        </div>

        {error && (
          <div className={`alert alert-error ${isShaking ? 'shake' : ''}`} style={{ marginBottom: '24px', borderRadius: '12px', fontSize: '13px' }}>
            <span style={{ fontSize: '18px' }}>⚠️</span>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="form-group">
            <label className="form-label" style={{ fontSize: '10px', letterSpacing: '0.15em' }}>ACCESS IDENTIFIER</label>
            <input 
              type="email" 
              className="form-control" 
              placeholder="operator@nexus.io"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (error) setError('');
              }}
              style={{ borderRadius: '12px', padding: '14px 18px' }}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label" style={{ fontSize: '10px', letterSpacing: '0.15em' }}>SECURITY CLEARANCE</label>
            <input 
              type="password" 
              className="form-control" 
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (error) setError('');
              }}
              style={{ borderRadius: '12px', padding: '14px 18px' }}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" style={{ 
            width: '100%', 
            justifyContent: 'center', 
            height: '52px', 
            borderRadius: '12px',
            fontSize: '14px',
            boxShadow: '0 4px 15px hsla(var(--accent-h), var(--accent-s), var(--accent-l), 0.3)'
          }} disabled={loading}>
            {loading ? <div className="spinner" style={{ borderTopColor: '#000' }} /> : 'ESTABLISH CONNECTION'}
          </button>
        </form>

        <div style={{ margin: '32px 0', textAlign: 'center', position: 'relative' }}>
          <hr style={{ border: 'none', borderTop: '1px solid var(--border)' }} />
          <span style={{ 
            position: 'absolute', 
            top: '50%', 
            left: '50%', 
            transform: 'translate(-50%, -50%)',
            background: '#fff',
            padding: '0 16px',
            fontSize: '10px',
            fontWeight: '700',
            color: 'var(--muted)',
            letterSpacing: '0.1em'
          }}>FEDERATED AUTH</span>
        </div>

        <button 
          onClick={handleGoogleLogin} 
          className="btn btn-secondary" 
          style={{ 
            width: '100%', 
            justifyContent: 'center', 
            gap: '12px', 
            height: '52px', 
            borderRadius: '12px',
            fontSize: '13px',
            background: '#fff',
            border: '1px solid var(--border)'
          }}
        >
          <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/nui/google.svg" width="20" alt="Google" />
          Authorize via Google
        </button>

        <p style={{ marginTop: '32px', textAlign: 'center', fontSize: '13px', color: 'var(--muted)' }}>
          Unauthorized access is prohibited. <br/>
          <Link to="/signup" style={{ fontWeight: '700', color: 'var(--accent)', marginTop: '8px', display: 'inline-block' }}>REQUEST OPERATOR CLEARANCE</Link>
        </p>
      </div>
    </div>
  );
};

export default Login;
