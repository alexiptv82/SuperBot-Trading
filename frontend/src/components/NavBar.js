import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppMode } from '../AppContext';

// Tab per modalità PAPER
const PAPER_TABS = [
  { path: '/',            icon: '📊', label: 'Dashboard' },
  { path: '/trades',      icon: '💹', label: 'Trade' },
  { path: '/performance', icon: '🏆', label: 'Performance' },
];

// Tab per modalità LIVE
const LIVE_TABS = [
  { path: '/live',             icon: '📊', label: 'Dashboard' },
  { path: '/live/trades',      icon: '💹', label: 'Trade' },
  { path: '/live/performance', icon: '🏆', label: 'Performance' },
];

export default function NavBar({ onLogout }) {
  const nav = useNavigate();
  const loc = useLocation();
  const { mode, toggleMode } = useAppMode();

  const isLive = mode === 'live';
  const tabs = isLive ? LIVE_TABS : PAPER_TABS;

  // Quando si switcha modalità, naviga alla home della modalità target
  const handleToggle = () => {
    toggleMode();
    if (isLive) {
      nav('/');          // passa a paper → Dashboard paper
    } else {
      nav('/live');      // passa a live → Dashboard live
    }
  };

  return (
    <div style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      background: isLive ? 'rgba(15,20,39,0.96)' : 'rgba(30,41,59,0.96)',
      backdropFilter: 'blur(10px)',
      borderTop: `1px solid ${isLive ? '#1e3a4a' : '#334155'}`,
      display: 'flex', zIndex: 100,
      paddingBottom: 'env(safe-area-inset-bottom)',
      paddingTop: '4px',
      transition: 'background 0.3s, border-color 0.3s',
    }}>
      {/* Tab sinistra + destra con toggle al centro */}
      {/* Tab 1 e 2 */}
      {tabs.slice(0, 2).map(t => {
        const active = loc.pathname === t.path;
        return (
          <button key={t.path} onClick={() => nav(t.path)} style={{
            flex: 1, padding: '5px 0 7px', margin: '0 2px', borderRadius: '10px',
            background: active
              ? (isLive ? 'rgba(239,68,68,0.14)' : 'rgba(56,189,248,0.14)')
              : 'none',
            border: 'none',
            color: active
              ? (isLive ? '#f87171' : '#38bdf8')
              : '#64748b',
            fontSize: '10px', fontWeight: active ? 700 : 400,
            cursor: 'pointer', display: 'flex',
            flexDirection: 'column', alignItems: 'center', gap: '2px',
            transition: 'all 0.15s',
          }}>
            <span style={{ fontSize: '18px' }}>{t.icon}</span>
            <span>{t.label}</span>
          </button>
        );
      })}

      {/* Toggle centrale PAPER ↔ LIVE */}
      <button
        onClick={handleToggle}
        style={{
          flex: '0 0 68px',
          margin: '0 4px',
          padding: '4px 0 6px',
          borderRadius: '14px',
          border: `1.5px solid ${isLive ? 'rgba(239,68,68,0.5)' : 'rgba(100,116,139,0.35)'}`,
          background: isLive
            ? 'linear-gradient(180deg, rgba(239,68,68,0.18) 0%, rgba(127,29,29,0.22) 100%)'
            : 'rgba(30,41,59,0.6)',
          cursor: 'pointer',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1px',
          transition: 'all 0.25s',
          boxShadow: isLive ? '0 0 10px rgba(239,68,68,0.2)' : 'none',
        }}>
        <span style={{ fontSize: '20px', lineHeight: 1.2 }}>
          {isLive ? '🔴' : '⚪'}
        </span>
        <span style={{
          fontSize: '9px', fontWeight: 800, letterSpacing: '0.08em',
          color: isLive ? '#f87171' : '#475569',
          textTransform: 'uppercase', lineHeight: 1.2,
        }}>
          {isLive ? 'LIVE' : 'PAPER'}
        </span>
        <span style={{
          fontSize: '8px', color: isLive ? '#7f1d1d' : '#334155',
          lineHeight: 1, marginTop: '1px',
        }}>
          {isLive ? '→ non reale' : '→ live'}
        </span>
      </button>

      {/* Tab 3 */}
      {tabs.slice(2).map(t => {
        const active = loc.pathname === t.path;
        return (
          <button key={t.path} onClick={() => nav(t.path)} style={{
            flex: 1, padding: '5px 0 7px', margin: '0 2px', borderRadius: '10px',
            background: active
              ? (isLive ? 'rgba(239,68,68,0.14)' : 'rgba(56,189,248,0.14)')
              : 'none',
            border: 'none',
            color: active
              ? (isLive ? '#f87171' : '#38bdf8')
              : '#64748b',
            fontSize: '10px', fontWeight: active ? 700 : 400,
            cursor: 'pointer', display: 'flex',
            flexDirection: 'column', alignItems: 'center', gap: '2px',
            transition: 'all 0.15s',
          }}>
            <span style={{ fontSize: '18px' }}>{t.icon}</span>
            <span>{t.label}</span>
          </button>
        );
      })}

      {/* Impostazioni + Esci */}
      <button onClick={() => nav('/settings')} style={{
        flex: 1, padding: '5px 0 7px', margin: '0 2px', borderRadius: '10px',
        background: loc.pathname === '/settings'
          ? (isLive ? 'rgba(239,68,68,0.14)' : 'rgba(56,189,248,0.14)')
          : 'none',
        border: 'none',
        color: loc.pathname === '/settings'
          ? (isLive ? '#f87171' : '#38bdf8')
          : '#64748b',
        fontSize: '10px', cursor: 'pointer',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px',
        transition: 'all 0.15s',
      }}>
        <span style={{ fontSize: '18px' }}>⚙️</span>
        <span>Impostazioni</span>
      </button>

      <button onClick={onLogout} style={{
        flex: 1, padding: '5px 0 7px', margin: '0 2px', borderRadius: '10px',
        background: 'none', border: 'none',
        color: '#64748b', fontSize: '10px', cursor: 'pointer',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px',
      }}>
        <span style={{ fontSize: '18px' }}>🚪</span>
        <span>Esci</span>
      </button>
    </div>
  );
}
