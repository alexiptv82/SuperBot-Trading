import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
const tabs = [
  { path: '/', icon: '📊', label: 'Dashboard' },
  { path: '/trades', icon: '💹', label: 'Non reale', sublabel: 'PAPER' },
  { path: '/performance', icon: '🏆', label: 'Performance' },
  { path: '/live', icon: '🔴', label: 'Trade Live', sublabel: 'LIVE' },
  { path: '/settings', icon: '⚙️', label: 'Impostazioni' },
];
export default function NavBar({ onLogout }) {
  const nav = useNavigate();
  const loc = useLocation();
  return (
    <div style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      background: 'rgba(30,41,59,0.92)', backdropFilter: 'blur(8px)',
      borderTop: '1px solid #334155',
      display: 'flex', zIndex: 100, paddingBottom: 'env(safe-area-inset-bottom)',
      paddingTop: '6px'
    }}>
      {tabs.map(t => {
        const active = loc.pathname === t.path;
        return (
          <button key={t.path} onClick={() => nav(t.path)} style={{
            flex: 1, padding: '6px 0 8px', margin: '0 2px', borderRadius: '12px',
            background: active
              ? (t.path === '/live' ? 'rgba(239,68,68,0.14)' : 'rgba(56,189,248,0.14)')
              : 'none',
            border: active && t.path === '/live' ? '1px solid rgba(239,68,68,0.25)' : 'none',
            color: active
              ? (t.path === '/live' ? '#f87171' : '#38bdf8')
              : '#94a3b8',
            fontSize: '10px', fontWeight: active ? 'bold' : 'normal', cursor: 'pointer', display: 'flex',
            flexDirection: 'column', alignItems: 'center', gap: '1px',
            transition: 'background 0.15s, color 0.15s'
          }}>
            <span style={{ fontSize: '19px' }}>{t.icon}</span>
            <span style={{ lineHeight: 1.2, textAlign: 'center' }}>{t.label}</span>
            {t.sublabel && (
              <span style={{
                fontSize: '8px', fontWeight: 700, letterSpacing: '0.08em',
                color: t.path === '/live'
                  ? (active ? '#f87171' : '#6b2323')
                  : (active ? '#38bdf8' : '#334155'),
                lineHeight: 1,
              }}>{t.sublabel}</span>
            )}
          </button>
        );
      })}
      <button onClick={onLogout} style={{
        flex: 1, padding: '6px 0 8px', margin: '0 4px', borderRadius: '12px',
        background: 'none', border: 'none',
        color: '#94a3b8', fontSize: '11px', cursor: 'pointer',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px'
      }}>
        <span style={{ fontSize: '20px' }}>🚪</span>
        <span>Esci</span>
      </button>
    </div>
  );
}
