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
      
      if (err.response) {
        setError(err.response.data?.detail || 'Registration failed. Please try again.');
      } else {
        setError('Connection error. Please check if the backend is running.');
      }
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
      background: 'var(--bg)'
    }}>
      <div className="card" style={{ maxWidth: '400px', width: '100%', boxShadow: 'var(--glow)' }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div className="brand-icon" style={{ fontSize: '48px', marginBottom: '12px' }}>✦</div>
          <h1 className="page-title" style={{ fontSize: '24px' }}>NEXUS</h1>
          <p className="page-subtitle">Request Intelligence Access</p>
        </div>

        {error && (
          <div className={`alert alert-error ${isShaking ? 'shake' : ''}`}>
            <span style={{ fontSize: '18px' }}>⚠</span>
            {error}
          </div>
        )}

        {success && (
          <div className="alert alert-success">
            <span style={{ fontSize: '18px' }}>✓</span>
            Account requested successfully! Redirecting to login...
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="form-group">
            <label className="form-label">Full Name</label>
            <input 
              type="text" 
              className="form-control" 
              placeholder="John Doe"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (error) setError('');
              }}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input 
              type="email" 
              className="form-control" 
              placeholder="name@company.com"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (error) setError('');
              }}
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input 
              type="password" 
              className="form-control" 
              placeholder="••••••••"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (error) setError('');
              }}
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }} disabled={loading || success}>
            {loading ? 'Processing...' : 'Request Access'}
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
