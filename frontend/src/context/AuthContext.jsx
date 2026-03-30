import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../services/api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);


  useEffect(() => {
    // Check for token in URL fragment (from OAuth redirect)
    const hash = window.location.hash;
    if (hash && hash.startsWith('#token=')) {
      const token = hash.split('=')[1];
      localStorage.setItem('token', token);
      // Clean up URL
      window.history.replaceState(null, null, window.location.pathname);
      fetchUser();
      return;
    }

    const token = localStorage.getItem('token');
    if (token) {
      fetchUser();
    } else {
      setLoading(false);
    }
  }, []);

  const fetchUser = async () => {
    try {
      const userData = await api.get(`/auth/me?t=${Date.now()}`);
      setUser(userData);
    } catch (err) {
      console.error("Auth verify failed", err);
      localStorage.removeItem('token');
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    try {
      const params = new URLSearchParams();
      params.append('username', email); // OAuth2PasswordRequestForm expects 'username'
      params.append('password', password);
      
      const data = await api.post('/auth/login', params);
      
      const { access_token } = data;
      localStorage.setItem('token', access_token);
      await fetchUser();
      return { success: true };
    } catch (err) {
      console.error("Login failed", err);
      throw err;
    }
  };

  const register = async (email, password, name) => {
    try {
      await api.post('/auth/register', { email, password, name });
      return { success: true };
    } catch (err) {
      console.error("Registration failed", err);
      // Extract the detail message for better UX
      const message = err.response?.data?.detail || err.message || "Registration failed";
      throw new Error(message);
    }
  };

  const logout = () => {
    localStorage.removeItem('token');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
