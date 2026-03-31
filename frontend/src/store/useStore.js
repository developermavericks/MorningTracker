import { create } from 'zustand';
import { api } from '../services/api';

const useStore = create((set, get) => ({
  // State
  user: null,
  jobs: [],
  stats: null,
  articles: [],
  totalArticles: 0,
  totalJobs: 0,
  loading: false,
  error: null,

  // Actions
  setUser: (user) => set({ user }),
  
  fetchStats: async () => {
    try {
      const stats = await api.get(`/articles/stats/summary?t=${Date.now()}`);
      set({ stats });
    } catch (err) {
      console.error('Stats fetch failed:', err);
    }
  },

  fetchJobs: async (page = 1, append = false) => {
    try {
      const data = await api.get(`/scrape/jobs?page=${page}&t=${Date.now()}`);
      
      const newJobs = data.jobs || (Array.isArray(data) ? data : []);
      const total = data.total || 0;

      set((state) => ({
        jobs: append ? [...state.jobs, ...newJobs] : newJobs,
        totalJobs: total || (append ? state.totalJobs : newJobs.length)
      }));
    } catch (err) {
      console.error('Jobs fetch failed:', err);
      if (!append) set({ jobs: [] });
    }
  },

  fetchArticles: async (params = {}) => {
    set({ loading: true });
    try {
      const data = await api.get('/articles/', { ...params, t: Date.now() });
      // Defensive checks for production stability
      const safeArticles = Array.isArray(data.articles) ? data.articles : [];
      const safeTotal = typeof data.total === 'number' ? data.total : 0;
      set({ 
        articles: safeArticles, 
        totalArticles: safeTotal,
        loading: false 
      });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  deleteArticle: async (id) => {
    try {
      await api.delete(`/articles/${id}`);
      set((state) => ({
        articles: state.articles.filter((a) => a.id !== id),
        totalArticles: Math.max(0, state.totalArticles - 1)
      }));
      return true;
    } catch (err) {
      console.error('Failed to delete article:', err);
      return false;
    }
  },

  deleteBulkArticles: async (params = {}) => {
    try {
      // Build query string for filters
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, val]) => {
         if (val) query.append(key, val);
      });
      await api.delete(`/articles/bulk?${query.toString()}`);
      set({ articles: [], totalArticles: 0 });
      return true;
    } catch (err) {
      console.error('Failed to bulk delete articles:', err);
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, jobs: [], stats: null, articles: [] });
  }
}));

export default useStore;
