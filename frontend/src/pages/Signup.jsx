import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';

const Signup = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [isShaking, setIsShaking] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess(false);
    setIsShaking(false);
    setLoading(true);

    try {
      await register(email, password, name);
      setSuccess(true);
      setTimeout(() => navigate('/login'), 3000);
    } catch (err) {
      setIsShaking(true);
      setTimeout(() => setIsShaking(false), 500);
      
      // Improve error message extraction
      const message = err.response?.data?.detail || err.message || "Registration failed. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
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
          <p className="page-subtitle" style={{ fontSize: '11px', fontWeight: '600' }}>CREATE YOUR ACCOUNT</p>
        </div>

        {error && (
          <div className={`alert alert-error ${isShaking ? 'shake' : ''}`}>
            <span style={{ fontSize: '18px' }}>⚠</span>
            {error}
          </div>
        )}

        {success && (
          <div className="alert alert-success" style={{ marginBottom: '24px', borderRadius: '12px', fontSize: '13px' }}>
            <span style={{ fontSize: '18px' }}>✓</span>
            Account created successfully! Redirecting to login...
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="form-group">
            <label className="form-label" style={{ fontSize: '10px', letterSpacing: '0.15em' }}>FULL NAME</label>
            <input 
              type="text" 
              className="form-control" 
              placeholder="John Doe"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (error) setError('');
              }}
              style={{ borderRadius: '12px', padding: '14px 18px' }}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label" style={{ fontSize: '10px', letterSpacing: '0.15em' }}>EMAIL ADDRESS</label>
            <input 
              type="email" 
              className="form-control" 
              placeholder="name@company.com"
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
            <label className="form-label" style={{ fontSize: '10px', letterSpacing: '0.15em' }}>PASSWORD</label>
            <input 
              type="password" 
              className="form-control" 
              placeholder="••••••••"
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
          }} disabled={loading || success}>
            {loading ? <div className="spinner" style={{ borderTopColor: '#000' }} /> : 'CREATE ACCOUNT'}
          </button>
        </form>

        <p style={{ marginTop: '24px', textAlign: 'center', fontSize: '13px', color: 'var(--muted)' }}>
          Already have an account? <Link to="/login" style={{ fontWeight: '600' }}>Sign In</Link>
        </p>
      </div>
    </div>
  );
};

export default Signup;
