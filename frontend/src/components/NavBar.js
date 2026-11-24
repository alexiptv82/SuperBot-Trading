import React, { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAppMode } from '../AppContext';

// Barra principale: SOLO Brain, Trade, Performance, Archivio (i due bot PAPER attuali). Tutto il resto (portafogli
// storici, Arena, RC1, classici) vive nell'Archivio; Impostazioni, strumenti tecnici, modalita' LIVE ed Esci stanno
// nel menu separato in alto (TopBar). Nessuna pagina o dato storico e' stato eliminato: cambia solo come ci si arriva.
export const PAPER_TABS = [
  { path: '/brain-unico', icon: '🧠', label: 'Brain' },
  { path: '/trades', icon: '💹', label: 'Trade' },
  { path: '/performance', icon: '📈', label: 'Performance' },
  { path: '/archivio', icon: '🗄️', label: 'Archivio' },
];

const LIVE_TABS = [
  { path: '/live', icon: '📊', label: 'Dashboard' },
  { path: '/live/trades', icon: '💹', label: 'Trade' },
  { path: '/live/performance', icon: '🏆', label: 'Performance' },
];

// Pagine storiche: tengono acceso il tab Archivio
const ARCHIVE_PREFIXES = ['/archivio', '/overview', '/classic', '/brain-unico/rc1', '/compare', '/arena', '/brain/archive'];

export const isActive = (tabPath, pathname) => {
  if (tabPath === '/archivio') return ARCHIVE_PREFIXES.some(p => pathname === p || pathname.startsWith(`${p}/`));
  if (tabPath === '/brain-unico') return pathname === '/brain-unico';
  return pathname === tabPath;
};

export default function NavBar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { mode } = useAppMode();
  const isLive = mode === 'live';
  const tabs = isLive ? LIVE_TABS : PAPER_TABS;
  const hi = isLive ? '#f87171' : '#a78bfa';
  return <nav aria-label="Navigazione principale" style={{
    position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 100, display: 'flex', gap: 4,
    background: 'rgba(11,16,24,0.97)', backdropFilter: 'blur(10px)', borderTop: '1px solid #263244',
    padding: '6px 8px calc(6px + env(safe-area-inset-bottom))' }}>
    {tabs.map(t => {
      const active = isActive(t.path, loc.pathname);
      return <button key={t.path} type="button" onClick={() => nav(t.path)} aria-current={active ? 'page' : undefined}
        style={{ flex: 1, minWidth: 0, minHeight: 52, padding: '6px 0', borderRadius: 14, border: 'none', cursor: 'pointer',
          background: active ? `${hi}24` : 'none', color: active ? hi : '#9aa8bc', fontSize: 12, fontWeight: active ? 800 : 600,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, WebkitTapHighlightColor: 'transparent' }}>
        <span aria-hidden="true" style={{ fontSize: 20, lineHeight: 1 }}>{t.icon}</span>
        <span>{t.label}</span>
      </button>;
    })}
  </nav>;
}

// Barra superiore: marchio, modalita' e menu separato (Impostazioni, Agenti, LIVE, Esci).
export function TopBar({ onLogout }) {
  const nav = useNavigate();
  const loc = useLocation();
  const { mode, toggleMode } = useAppMode();
  const [open, setOpen] = useState(false);
  const isLive = mode === 'live';
  useEffect(() => { setOpen(false); }, [loc.pathname]);
  useEffect(() => {
    if (!open) return undefined;
    const esc = e => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [open]);
  const go = path => { setOpen(false); nav(path); };
  const switchMode = () => { setOpen(false); toggleMode(); nav(isLive ? '/brain-unico' : '/live'); };
  const item = { display: 'flex', alignItems: 'center', gap: 12, width: '100%', minHeight: 52, padding: '12px 16px',
    background: 'none', border: 'none', borderBottom: '1px solid #263244', color: '#f1f5f9', fontSize: 16, cursor: 'pointer',
    textAlign: 'left', font: 'inherit' };
  return <>
    <div style={{ position: 'sticky', top: 0, zIndex: 90, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 8, padding: '10px 16px', background: 'rgba(11,16,24,0.92)', backdropFilter: 'blur(10px)', borderBottom: '1px solid #1c2533' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
        <strong style={{ fontSize: 16, color: '#f1f5f9', letterSpacing: '0.01em' }}>SuperBot</strong>
        <span style={{ fontSize: 12, fontWeight: 800, padding: '2px 9px', borderRadius: 999,
          color: isLive ? '#fecaca' : '#ddd6fe', background: isLive ? '#7f1d1d' : '#4c1d95aa' }}>
          {isLive ? 'LIVE · sola consultazione' : 'PAPER · soldi simulati'}</span>
      </div>
      <button type="button" aria-label="Menu" aria-expanded={open} aria-controls="app-menu" onClick={() => setOpen(o => !o)}
        style={{ minWidth: 48, minHeight: 44, borderRadius: 12, border: '1px solid #263244', background: '#141b26',
          color: '#f1f5f9', fontSize: 20, cursor: 'pointer' }}>☰</button>
    </div>
    {open && <div role="presentation" onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 200,
      background: 'rgba(0,0,0,0.55)' }}>
      <div id="app-menu" role="dialog" aria-modal="true" aria-label="Menu" onClick={e => e.stopPropagation()}
        style={{ position: 'absolute', top: 0, right: 0, width: 'min(320px, 86vw)', height: '100%', background: '#0f1520',
          borderLeft: '1px solid #263244', overflowY: 'auto' }}>
        <div style={{ padding: '16px', fontSize: 13, color: '#9aa8bc', borderBottom: '1px solid #263244' }}>
          Impostazioni e strumenti tecnici</div>
        <button type="button" style={item} onClick={() => go('/settings')}><span aria-hidden="true">⚙️</span>Impostazioni</button>
        <button type="button" style={item} onClick={() => go('/supervisor')}><span aria-hidden="true">🛰️</span>Agenti e supervisione</button>
        <button type="button" style={item} onClick={switchMode}><span aria-hidden="true">{isLive ? '⚪' : '🔴'}</span>
          {isLive ? 'Torna alla modalità PAPER' : 'Modalità LIVE (sola consultazione)'}</button>
        <button type="button" style={item} onClick={() => { setOpen(false); onLogout(); }}><span aria-hidden="true">🚪</span>Esci</button>
        <button type="button" style={{ ...item, color: '#9aa8bc', fontSize: 14, borderBottom: 'none' }} onClick={() => setOpen(false)}>Chiudi il menu</button>
      </div>
    </div>}
  </>;
}
