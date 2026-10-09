import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import { botAPI } from './api';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Trades from './pages/Trades';
import Performance from './pages/Performance';
import Settings from './pages/Settings';
import NavBar from './components/NavBar';
// Avviso quando la password sta per scadere (ultimi 7 giorni su 60).
function PasswordBanner() {
  const [days, setDays] = useState(null);
  useEffect(() => {
    botAPI.passwordStatus()
      .then(({ data }) => { if (data.warn) setDays(data.days_left); })
      .catch(() => {});
  }, []);
  if (days === null) return null;
  return (
    <Link to="/settings" style={{
      display: 'block', padding: '10px 16px', background: '#78350f', color: '#fde68a',
      fontSize: '13px', textAlign: 'center', textDecoration: 'none',
    }}>
      🔑 La password scade {days <= 0 ? 'oggi' : days === 1 ? 'domani' : `tra ${days} giorni`}: tocca per cambiarla
    </Link>
  );
}

export default function App() {
  const [auth, setAuth] = useState(!!localStorage.getItem('sb_token'));
  if (!auth) return <Login onLogin={() => setAuth(true)} />;
  return (
    <BrowserRouter>
      <PasswordBanner />
      <div style={{ paddingBottom: '70px' }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </div>
      <NavBar onLogout={() => { localStorage.removeItem('sb_token'); setAuth(false); }} />
    </BrowserRouter>
  );
}
