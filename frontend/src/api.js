import axios from 'axios';

const API = axios.create({
  baseURL: process.env.REACT_APP_BACKEND_URL || process.env.REACT_APP_API_URL || 'http://51.91.109.45:8002',
  timeout: 10000
});

// Allega il token di sessione a ogni richiesta, se presente.
API.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('sb_token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

// Se il token non è più valido (scaduto/mancante), torna alla schermata di login.
API.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem('sb_token');
      if (window.location.pathname !== '/') window.location.href = '/';
    }
    return Promise.reject(err);
  }
);

export const botAPI = {
  getStatus: () => API.get('/api/bot/status'),
  getConfig: () => API.get('/api/bot/config'),
  start: () => API.post('/api/bot/start'),
  stop: () => API.post('/api/bot/stop'),
  getPrices: () => API.get('/api/market/prices'),
  getIndicators: (symbol) => API.get(`/api/market/indicators/${symbol}`),
  getTrades: (limit = 50, offset = 0) => API.get(`/api/trades?limit=${limit}&offset=${offset}`),
  getOpenTrades: () => API.get('/api/trades/open'),
  getPerformance: () => API.get('/api/performance'),
  getLogs: () => API.get('/api/logs?limit=50'),
  login: (password) => API.post('/api/auth/login', { password }),
  health: () => API.get('/api/health'),
  webauthnStatus: () => API.get('/api/auth/webauthn/status'),
  webauthnRegisterOptions: () => API.post('/api/auth/webauthn/register/options'),
  webauthnRegisterVerify: (state_id, credential, device_label) =>
    API.post('/api/auth/webauthn/register/verify', { state_id, credential, device_label }),
  webauthnLoginOptions: () => API.post('/api/auth/webauthn/login/options'),
  webauthnLoginVerify: (state_id, credential) =>
    API.post('/api/auth/webauthn/login/verify', { state_id, credential }),
};

export default API;
