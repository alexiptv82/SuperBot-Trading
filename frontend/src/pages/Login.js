import React, { useState } from 'react';
import { botAPI } from '../api';
export default function Login({ onLogin }) {
  const [pwd, setPwd] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const handleLogin = async () => {
    setLoading(true); setError('');
    try {
      await botAPI.login(pwd);
      onLogin();
    } catch {
      setError('Password errata');
    } finally {
      setLoading(false);
    }
  };
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '24px',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)'
    }}>
      <div style={{ fontSize: '60px', marginBottom: '16px' }}>🤖</div>
      <h1 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '8px', color: '#f1f5f9' }}>SuperBot</h1>
      <p style={{ color: '#94a3b8', marginBottom: '32px' }}>Trading Bot Dashboard</p>
      <div style={{ width: '100%', maxWidth: '360px' }}>
        <input
          type="password"
          placeholder="Password"
          value={pwd}
          onChange={e => setPwd(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleLogin()}
          style={{
            width: '100%', padding: '14px 16px', borderRadius: '12px',
            border: '1px solid #334155', background: '#1e293b',
            color: '#f1f5f9', fontSize: '16px', marginBottom: '12px', outline: 'none'
          }}
        />
        {error && <p style={{ color: '#f87171', marginBottom: '12px', textAlign: 'center' }}>{error}</p>}
        <button onClick={handleLogin} disabled={loading} style={{
          width: '100%', padding: '14px', borderRadius: '12px',
          background: loading ? '#334155' : '#0ea5e9',
          color: 'white', fontSize: '16px', fontWeight: 'bold',
          border: 'none', cursor: loading ? 'not-allowed' : 'pointer'
        }}>
          {loading ? 'Accesso...' : 'Accedi'}
        </button>
      </div>
    </div>
  );
}
