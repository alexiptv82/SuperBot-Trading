import React from 'react';

// Colore per profilo di rischio: stesso schema in tutta l'app.
export const PROFILE_COLORS = {
  conservative: '#38bdf8',
  aggressive: '#fb923c',
  legacy: '#94a3b8',
};

export const profileColor = (name) => PROFILE_COLORS[name] || '#94a3b8';

// Etichetta piccola col nome del profilo (Conservativo / Aggressivo / Precedente).
export default function ProfileBadge({ profile, label }) {
  const text = label || (profile ? profile : null);
  if (!text) return null;
  const color = profileColor(profile);
  return (
    <span style={{
      padding: '2px 8px', borderRadius: '6px', fontSize: '10px', fontWeight: 'bold',
      border: `1px solid ${color}`, color, background: 'rgba(15,23,42,0.6)',
      whiteSpace: 'nowrap'
    }}>{text}</span>
  );
}
