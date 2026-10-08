import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Trades from './pages/Trades';
import Performance from './pages/Performance';
import Settings from './pages/Settings';
import NavBar from './components/NavBar';
export default function App() {
  const [auth, setAuth] = useState(!!localStorage.getItem('sb_token'));
  if (!auth) return <Login onLogin={() => setAuth(true)} />;
  return (
    <BrowserRouter>
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
