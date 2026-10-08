import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
const tabs = [
  { path: '/', icon: '📊', label: 'Dashboard' },
  { path: '/trades', icon: '💹', label: 'Trade' },
  { path: '/performance', icon: '🏆', label: 'Performance' },
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
            flex: 1, padding: '6px 0 8px', margin: '0 4px', borderRadius: '12px',
            background: active ? 'rgba(56,189,248,0.14)' : 'none', border: 'none',
            color: active ? '#38bdf8' : '#94a3b8',
            fontSize: '11px', fontWeight: active ? 'bold' : 'normal', cursor: 'pointer', display: 'flex',
            flexDirection: 'column', alignItems: 'center', gap: '2px',
            transition: 'background 0.15s, color 0.15s'
          }}>
            <span style={{ fontSize: '20px' }}>{t.icon}</span>
            <span>{t.label}</span>
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
