import axios from 'axios';

const getApiBase = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  if (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
    return "http://localhost:8000/api/";
  }
  return "/api/";
};

const API_BASE = getApiBase();

const apiClient = axios.create({
  baseURL: API_BASE,
});

// Auth Interceptor
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Error handling Interceptor
apiClient.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const originalRequest = error.config;
    
    // 1. Handle Token Expiry / Unauthorized
    if (error.response?.status === 401 && !originalRequest._retry) {
      console.warn("Unauthorized! Clearing local session...");
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      // Force reload to trigger AuthContext logout/redirect
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }

    // 2. Handle Transient Network Errors / 503s with Retries
    if ((error.code === 'ECONNABORTED' || error.response?.status >= 500) && !originalRequest._retry) {
      originalRequest._retry = true;
      console.log("Transient error. Retrying request...");
      await new Promise(res => setTimeout(res, 1000));
      return apiClient(originalRequest);
    }

    const message = error.response?.data?.detail || error.message || 'Unknown Error';
    return Promise.reject(new Error(message));
  }
);

export const api = {
  get: (url, params) => apiClient.get(url, { params }),
  post: (url, data, config) => apiClient.post(url, data, config),
  put: (url, data, config) => apiClient.put(url, data, config),
  delete: (url) => apiClient.delete(url),
  
  // Helper for direct URLs
  getExportUrl: (job_id) => {
    const token = localStorage.getItem('token');
    return `${API_BASE}articles/export/csv?job_id=${job_id}${token ? `&query_token=${token}` : ''}`;
  },
  getExcelUrl: (job_id) => {
    const token = localStorage.getItem('token');
    return `${API_BASE}articles/export/xlsx?job_id=${job_id}${token ? `&query_token=${token}` : ''}`;
  }
};

export default apiClient;
