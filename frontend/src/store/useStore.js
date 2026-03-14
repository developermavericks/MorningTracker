import { create } from 'zustand';
import { api } from '../services/api';

const useStore = create((set, get) => ({
  // State
  user: null,
  jobs: [],
  stats: null,
  articles: [],
  totalArticles: 0,
  loading: false,
  error: null,

  // Actions
  setUser: (user) => set({ user }),
  
  fetchStats: async () => {
    try {
      const stats = await api.get('/articles/stats/summary');
      set({ stats });
    } catch (err) {
      console.error('Stats fetch failed:', err);
    }
  },

  fetchJobs: async () => {
    try {
      const jobs = await api.get('/scrape/jobs');
      set({ jobs });
    } catch (err) {
      console.error('Jobs fetch failed:', err);
    }
  },

  fetchArticles: async (params = {}) => {
    set({ loading: true });
    try {
      const data = await api.get('/articles/', params);
      set({ 
        articles: data.articles, 
        totalArticles: data.total,
        loading: false 
      });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  logout: () => {
    localStorage.removeItem('token');
    set({ user: null, jobs: [], stats: null, articles: [] });
  }
}));

export default useStore;
