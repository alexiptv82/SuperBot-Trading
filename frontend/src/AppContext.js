import React, { createContext, useContext, useState, useCallback } from 'react';

// Contesto globale per la modalità: 'paper' | 'live'
const AppCtx = createContext(null);

export function AppProvider({ children }) {
  const [mode, setModeState] = useState(() => {
    try { return sessionStorage.getItem('sb_mode') || 'paper'; } catch { return 'paper'; }
  });

  const setMode = useCallback((m) => {
    setModeState(m);
    try { sessionStorage.setItem('sb_mode', m); } catch {}
  }, []);

  const toggleMode = useCallback(() => {
    setModeState(prev => {
      const next = prev === 'paper' ? 'live' : 'paper';
      try { sessionStorage.setItem('sb_mode', next); } catch {}
      return next;
    });
  }, []);

  return (
    <AppCtx.Provider value={{ mode, setMode, toggleMode }}>
      {children}
    </AppCtx.Provider>
  );
}

export const useAppMode = () => useContext(AppCtx);
