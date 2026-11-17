import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom';
import { botAPI } from './api';
import { AppProvider } from './AppContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Trades from './pages/Trades';
import Performance from './pages/Performance';
import Settings from './pages/Settings';
import NavBar from './components/NavBar';
import LiveDashboard from './pages/LiveDashboard';
import LiveTrades from './pages/LiveTrades';
import LivePerformance from './pages/LivePerformance';
import BrainDashboard from './pages/BrainDashboard';
import Overview from './pages/Overview';
import BrainArena from './pages/BrainArena';
import Supervisor from './pages/Supervisor';

// Error boundary globale: cattura qualsiasi crash di render nell'albero React
// e mostra un messaggio utile invece della schermata nera.
class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    try { document.title = '❌ ' + (error?.message || 'crash'); } catch (_) {}
    console.error('[AppErrorBoundary]', error, info?.componentStack);
  }
  handleReload() {
    try { sessionStorage.clear(); } catch (_) {}
    window.location.reload(true);
  }
  render() {
    if (!this.state.hasError) return this.props.children;
    const msg = this.state.error?.message || '';
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', padding: '24px',
        background: '#0f172a', color: '#f1f5f9', textAlign: 'center'
      }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>⚠️</div>
        <h2 style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '8px' }}>
          Qualcosa è andato storto
        </h2>
        {msg ? (
          <p style={{
            fontSize: '12px', color: '#64748b', fontFamily: 'monospace',
            background: '#1e293b', borderRadius: '8px', padding: '10px 14px',
            marginBottom: '20px', maxWidth: '340px', wordBreak: 'break-all'
          }}>{msg}</p>
        ) : null}
        <button
          onClick={this.handleReload.bind(this)}
          style={{
            padding: '12px 28px', borderRadius: '12px', border: 'none',
            background: '#0ea5e9', color: 'white', fontSize: '15px',
            fontWeight: 'bold', cursor: 'pointer'
          }}
        >
          🔄 Ricarica app
        </button>
      </div>
    );
  }
}

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

// A preview banner alone cannot make legacy control pages read-only.
// In a read-only build, never mount operational routes or the LIVE toggle.
export const isArenaReadOnlyPreview = (env = process.env) =>
  env.REACT_APP_PREVIEW_READONLY === '1';

export default function App() {
  const [auth, setAuth] = useState(!!sessionStorage.getItem('sb_token'));
  const previewOnly = isArenaReadOnlyPreview();
  const handleLogout = () => {
    sessionStorage.removeItem('sb_token');
    sessionStorage.removeItem('sb_mode');
    setAuth(false);
  };
  if (!auth) return (
    <AppErrorBoundary>
      <Login onLogin={() => setAuth(true)} />
    </AppErrorBoundary>
  );
  return (
    <AppErrorBoundary>
      <AppProvider>
        <BrowserRouter basename={process.env.REACT_APP_BASENAME || undefined}>
          {previewOnly && <div role="status" style={{ background:'#78350f', color:'#fff7ed', padding:'10px 14px', fontWeight:700, textAlign:'center', fontSize:13 }}>
            ANTEPRIMA AI ARENA IN SOLA LETTURA — nuovi portafogli non avviati; il Brain storico può essere operativo. Nessuna chiusura abilitata in questa anteprima.
          </div>}
          {!previewOnly && <PasswordBanner />}
          <div style={{ paddingBottom: '75px' }}>
            {previewOnly ? <Routes>
              <Route path="/arena" element={<BrainArena />} />
              <Route path="*" element={<Navigate to="/arena" replace />} />
            </Routes> : <Routes>
              {/* ── Sezione PAPER (soldi simulati) ── */}
              <Route path="/" element={<Navigate to={process.env.REACT_APP_BRAIN_ARENA_PREVIEW === '1' ? '/arena' : '/overview'} replace />} />
              <Route path="/arena" element={<BrainArena />} />
              <Route path="/classic" element={<Dashboard />} />
              <Route path="/trades" element={<Trades />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/settings" element={<Settings />} />
              {/* ── Sezione LIVE (BitGet reale) ── */}
              <Route path="/live" element={<LiveDashboard />} />
              <Route path="/live/trades" element={<LiveTrades />} />
              <Route path="/live/performance" element={<LivePerformance />} />
              <Route path="/brain" element={<Navigate to="/classic?portfolio=brain" replace />} />
              <Route path="/brain/archive" element={<BrainDashboard archiveInitially />} />
              <Route path="/overview" element={<Overview />} />
              <Route path="/supervisor" element={<Supervisor />} />
              <Route path="*" element={<Navigate to="/" />} />
            </Routes>}
          </div>
          {previewOnly
            ? <div style={{ padding: '12px', textAlign: 'center', background: '#0e1a2d' }}>
                <button onClick={handleLogout} style={{ border: '1px solid #456079', borderRadius: 10,
                  padding: '9px 16px', background: '#172338', color: '#eef5ff' }}>Esci dall'anteprima</button>
              </div>
            : <NavBar onLogout={handleLogout} />}
        </BrowserRouter>
      </AppProvider>
    </AppErrorBoundary>
  );
}
