import axios from 'axios';

const API_BASE = "https://morningtracker-production.up.railway.app/api/";

const apiClient = axios.create({
  baseURL: API_BASE,
  // Enforce absolute baseURL by making sure relative URLs are always appended to it
  // This is the default behavior of axios when baseURL is set, but good to be explicit
  // and ensure no leading slashes in requests bypass it.
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
  post: (url, data) => apiClient.post(url, data),
  put: (url, data) => apiClient.put(url, data),
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
