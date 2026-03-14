import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("React Error Boundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg)',
          color: 'var(--text)',
          padding: '20px',
          textAlign: 'center'
        }}>
          <h1 style={{ color: 'var(--danger)', marginBottom: '16px' }}>✦ SYSTEM RECOVERY</h1>
          <p style={{ maxWidth: '500px', lineHeight: '1.6', opacity: 0.8 }}>
            The NEXUS interface encountered an unexpected state. Our automated recovery systems are recalibrating.
          </p>
          <button 
            onClick={() => window.location.reload()}
            style={{
              marginTop: '24px',
              padding: '12px 24px',
              background: 'var(--accent)',
              border: 'none',
              borderRadius: '8px',
              color: 'white',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            ↻ REFRESH INTERFACE
          </button>
          {process.env.NODE_ENV === 'development' && (
            <pre style={{ 
              marginTop: '40px', 
              padding: '20px', 
              background: 'var(--surface)', 
              borderRadius: '8px', 
              fontSize: '12px',
              textAlign: 'left',
              maxWidth: '90vw',
              overflow: 'auto'
            }}>
              {this.state.error?.toString()}
            </pre>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
