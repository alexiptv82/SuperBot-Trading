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
      background: '#1e293b', borderTop: '1px solid #334155',
      display: 'flex', zIndex: 100, paddingBottom: 'env(safe-area-inset-bottom)'
    }}>
      {tabs.map(t => (
        <button key={t.path} onClick={() => nav(t.path)} style={{
          flex: 1, padding: '10px 0', background: 'none', border: 'none',
          color: loc.pathname === t.path ? '#38bdf8' : '#94a3b8',
          fontSize: '11px', cursor: 'pointer', display: 'flex',
          flexDirection: 'column', alignItems: 'center', gap: '2px'
        }}>
          <span style={{ fontSize: '20px' }}>{t.icon}</span>
          <span>{t.label}</span>
        </button>
      ))}
      <button onClick={onLogout} style={{
        flex: 1, padding: '10px 0', background: 'none', border: 'none',
        color: '#94a3b8', fontSize: '11px', cursor: 'pointer',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px'
      }}>
        <span style={{ fontSize: '20px' }}>🚪</span>
        <span>Esci</span>
      </button>
    </div>
  );
}
