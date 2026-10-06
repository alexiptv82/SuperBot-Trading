import axios from 'axios';
const API = axios.create({
  baseURL: process.env.REACT_APP_BACKEND_URL || process.env.REACT_APP_API_URL || 'http://51.91.109.45:8002',
  timeout: 10000
});
export const botAPI = {
  getStatus: () => API.get('/api/bot/status'),
  start: () => API.post('/api/bot/start'),
  stop: () => API.post('/api/bot/stop'),
  getPrices: () => API.get('/api/market/prices'),
  getIndicators: (symbol) => API.get(`/api/market/indicators/${symbol}`),
  getTrades: () => API.get('/api/trades?limit=50'),
  getOpenTrades: () => API.get('/api/trades/open'),
  getPerformance: () => API.get('/api/performance'),
  getLogs: () => API.get('/api/logs?limit=50'),
  login: (password) => API.post('/api/auth/login', { password }),
  health: () => API.get('/api/health'),
};
export default API;
