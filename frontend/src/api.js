import axios from 'axios';

// REACT_APP_BACKEND_URL impostata ma VUOTA (e' il caso del deploy su main) =
// richieste relative, cioe' stesso dominio tramite il proxy /api di nginx.
// Non usare `||`: la stringa vuota e' falsa e cadeva sul fallback con l'IP in
// http://, che il browser blocca (mixed content) quando la pagina e' in HTTPS,
// e il login non arrivava mai al server.
const configuredBackend = process.env.REACT_APP_BACKEND_URL;
const baseURL = configuredBackend !== undefined
  ? configuredBackend
  : (process.env.REACT_APP_API_URL || 'http://51.91.109.45:8002');

const API = axios.create({
  baseURL,
  timeout: 10000
});

// Allega il token di sessione a ogni richiesta, se presente.
API.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('sb_token');
  // Non sovrascrive un token passato esplicitamente (es. quello limitato del cambio password).
  if (token && !cfg.headers.Authorization) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

// Se il token non è più valido (scaduto/mancante), torna alla schermata di login.
API.interceptors.response.use(
  (res) => res,
  (err) => {
    // Un 401 da login/cambio password significa "password errata", non "sessione scaduta".
    const url = err?.config?.url || '';
    const isAuthForm = url.includes('/api/auth/login') || url.includes('/api/auth/change-password')
      || url.includes('/api/auth/forgot');
    if (err?.response?.status === 401 && !isAuthForm) {
      localStorage.removeItem('sb_token');
      if (window.location.pathname !== '/') window.location.href = '/';
    }
    return Promise.reject(err);
  }
);

export const botAPI = {
  getStatus: () => API.get('/api/bot/status'),
  getConfig: () => API.get('/api/bot/config'),
  updateRiskConfig: (payload) => API.put('/api/bot/config/risk', payload),
  start: () => API.post('/api/bot/start'),
  stop: () => API.post('/api/bot/stop'),
  getPrices: () => API.get('/api/market/prices'),
  getIndicators: (symbol) => API.get(`/api/market/indicators/${symbol}`),
  getTrades: (limit = 50, offset = 0) => API.get(`/api/trades?limit=${limit}&offset=${offset}`),
  getOpenTrades: () => API.get('/api/trades/open'),
  getPerformance: () => API.get('/api/performance'),
  getLogs: () => API.get('/api/logs?limit=50'),
  login: (password) => API.post('/api/auth/login', { password }),
  changePassword: (old_password, new_password, token) =>
    API.post('/api/auth/change-password', { old_password, new_password },
      token ? { headers: { Authorization: `Bearer ${token}` } } : undefined),
  forgotPassword: () => API.post('/api/auth/forgot'),
  forgotPasswordConfirm: (code, new_password) =>
    API.post('/api/auth/forgot/confirm', { code, new_password }),
  passwordStatus: () => API.get('/api/auth/password-status'),
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
