import React, { useState, useEffect } from 'react';

const iconProps = {
  width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
  strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true,
};

// Occhio aperto: la password e' nascosta, toccando la mostri.
const EyeIcon = () => (
  <svg {...iconProps}>
    <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

// Occhio barrato: la password e' visibile, toccando la nascondi.
const EyeOffIcon = () => (
  <svg {...iconProps}>
    <path d="M17.94 17.94A10.94 10.94 0 0 1 12 19c-7 0-11-7-11-7a19.8 19.8 0 0 1 5.06-5.94" />
    <path d="M9.9 4.24A10.9 10.9 0 0 1 12 5c7 0 11 7 11 7a19.9 19.9 0 0 1-3.17 4.19" />
    <path d="M14.12 14.12A3 3 0 1 1 9.88 9.88" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </svg>
);

/**
 * Campo password con occhio per mostrare/nascondere cio' che si scrive.
 * Di default la password e' nascosta; si ri-nasconde da sola quando l'app
 * va in background (cosi' non resta leggibile nell'anteprima delle app recenti).
 * `style` e' lo stile dell'input; il marginBottom passa al contenitore cosi'
 * l'occhio resta centrato sul campo.
 */
export default function PasswordInput({ style, ...inputProps }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const hideWhenBackgrounded = () => { if (document.hidden) setVisible(false); };
    document.addEventListener('visibilitychange', hideWhenBackgrounded);
    return () => document.removeEventListener('visibilitychange', hideWhenBackgrounded);
  }, []);

  const { marginBottom, ...fieldStyle } = style || {};

  return (
    <div style={{ position: 'relative', width: '100%', marginBottom }}>
      <input
        {...inputProps}
        type={visible ? 'text' : 'password'}
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        style={{ ...fieldStyle, marginBottom: 0, paddingRight: '48px' }}
      />
      <button
        type="button"
        onClick={() => setVisible(v => !v)}
        // evita che il tocco tolga il focus al campo (resta aperta la tastiera)
        onMouseDown={e => e.preventDefault()}
        aria-label={visible ? 'Nascondi password' : 'Mostra password'}
        aria-pressed={visible}
        title={visible ? 'Nascondi password' : 'Mostra password'}
        style={{
          position: 'absolute', top: 0, bottom: 0, right: 0, width: '46px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          color: visible ? '#38bdf8' : '#94a3b8',
        }}
      >
        {visible ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  );
}
