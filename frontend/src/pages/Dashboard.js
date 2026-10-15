import React, { useState, useCallback, useEffect } from 'react';
import { deskAPI, bullAPI, errMsg } from '../api';
import { fmtClock, fmtDuration, signed, pnlColor, botState } from '../deskUi';
import ChartModal from '../components/ChartModal';
import { CloseControl } from '../components/LiveParts';

// Helper: API giusta per portfolio
const apiFor = (portfolio) => portfolio === 'bull' ? bullAPI : deskAPI;

// Stessi 27 simboli del bot V2 (backend/desk/cli.py SYMBOLS) e di /api/desk/prices.
const V2_SYMBOLS = [
  'BTCUSDT','ETHUSDT','BNBUSDT','XRPUSDT','SOLUSDT','ADAUSDT','DOGEUSDT','AVAXUSDT',
  'DOTUSDT','LINKUSDT','MATICUSDT','UNIUSDT','ATOMUSDT','LTCUSDT','BCHUSDT',
  'APTUSDT','ARBUSDT','OPUSDT','NEARUSDT','FILUSDT','INJUSDT','SUIUSDT','TIAUSDT',
  'RUNEUSDT','STXUSDT','XAUUSDT','XAGUSDT',
];

// Mappa simbolo → ID icona (lowercase). XAU/XAG usano l'emoji (nessun logo crypto).
const ICON_ID = {
  BTC:'btc', ETH:'eth', BNB:'bnb', XRP:'xrp', SOL:'sol', ADA:'ada', DOGE:'doge', AVAX:'avax',
  DOT:'dot', LINK:'link', MATIC:'matic', UNI:'uni', ATOM:'atom', LTC:'ltc', BCH:'bch',
  APT:'apt', ARB:'arb', OP:'op', NEAR:'near', FIL:'fil', INJ:'inj', SUI:'sui', TIA:'tia',
  RUNE:'rune', STX:'stx',
  XAU:'xau', XAG:'xag',
};

// Fallback emoji per metalli (non sempre in CDN)
const FALLBACK_EMOJI = { XAU:'🥇', XAG:'🥈' };

const fmt = (v, d = 2) => (v == null || isNaN(v)) ? '--' : Number(v).toFixed(d);

// Logo crypto: prova più sorgenti in ordine; se falliscono tutte mostra un badge
// con la sigla, che non dipende da nessun servizio esterno (quindi i simboli si vedono sempre).
function CryptoIcon({ base, size = 28 }) {
  const [idx, setIdx] = useState(0);
  const id = ICON_ID[base];

  if (FALLBACK_EMOJI[base]) {
    return <span style={{ fontSize: size * 0.8 }}>{FALLBACK_EMOJI[base]}</span>;
  }

  const sources = id ? [
    `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/${id}.png`,
    `https://assets.coincap.io/assets/icons/${id}@2x.png`,
    `https://coinicons-api.vercel.app/api/icon/${id}`,
  ] : [];

  if (idx >= sources.length) {
    return (
      <span style={{
        width: size, height: size, borderRadius: '50%', background: '#334155',
        color: '#e2e8f0', display: 'inline-flex', alignItems: 'center',
        justifyContent: 'center', fontSize: Math.max(8, size * 0.32), fontWeight: 'bold',
      }}>{base.slice(0, 4)}</span>
    );
  }
  return (
    <img
      key={sources[idx]}
      src={sources[idx]}
      alt={base}
      width={size}
      height={size}
      onError={() => setIdx(i => i + 1)}
      style={{ borderRadius: '50%', display: 'block' }}
    />
  );
}

class DeskErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(e) { return { err: e }; }
  render() {
    if (this.state.err) return (
      <div style={{ color: '#f87171', fontSize: '12px', padding: '8px' }}>
        Errore nel rendering V2: {this.state.err.message}
      </div>
    );
    return this.props.children;
  }
}

const Card = ({ children, style, onClick }) => (
  <div onClick={onClick} style={{
    background: '#1e293b', borderRadius: '16px', padding: '16px',
    border: '1px solid #334155', ...style
  }}>{children}</div>
);

const StatusChip = ({ label, ok, okText, badText }) => (
  <span style={{
    padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 'bold',
    background: ok ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
    color: ok ? '#4ade80' : '#f87171',
    border: `1px solid ${ok ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)'}`,
  }}>
    {label}: {ok ? okText : badText}
  </span>
);

function MarketCarousel({ symbols, prices, onSymbolClick }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{
        display: 'flex', overflowX: 'auto', gap: '8px', paddingBottom: '8px',
        scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch',
      }}>
        {symbols.map(sym => {
          const base = sym.replace('USDT', '').replace('PERP', '');
          const data = prices[sym] || prices[base] || {};
          const isActive = data.price > 0;
          const up = (data.change_24h || 0) >= 0;
          return (
            <div
              key={sym}
              onClick={() => onSymbolClick(sym)}
              style={{
                background: '#1e293b', borderRadius: '12px', padding: '10px 8px',
                border: '1px solid #334155', cursor: 'pointer', flexShrink: 0,
                minWidth: '100px', textAlign: 'center', opacity: isActive ? 1 : 0.55,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '4px' }}>
                <CryptoIcon base={base} size={28} />
              </div>
              <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '4px', fontWeight: 'bold' }}>{base}</div>
              <div style={{ fontSize: '13px', fontWeight: 'bold' }}>
                {isActive ? (data.price >= 1 ? '$' + data.price.toLocaleString('it-IT', { maximumFractionDigits: 2 }) : '$' + fmt(data.price, 4)) : '--'}
              </div>
              <div style={{ fontSize: '11px', color: up ? '#4ade80' : '#f87171', marginTop: '2px' }}>
                {isActive ? ((up ? '▲ +' : '▼ ') + Math.abs(data.change_24h || 0).toFixed(2) + '%') : ''}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: '10px', color: '#475569', textAlign: 'center', marginTop: '-4px' }}>
        ← scorri per vedere tutti i {symbols.length} simboli →
      </div>
    </div>
  );
}

function StateBanner({ status, isBull }) {
  const st = botState(status);
  const cyc = status.cycle || {};
  const nOpen = status.open_positions ?? 0;
  const box = (color, title, lines) => (
    <Card style={{ marginBottom: '12px', borderColor: color, background: color + '14', fontSize: '13px' }}>
      <div style={{ color, fontWeight: 'bold', marginBottom: lines.length ? '4px' : 0 }}>{title}</div>
      {lines.map((l, i) => <div key={i} style={{ color: '#94a3b8', fontSize: '12px', marginTop: i ? '2px' : 0 }}>{l}</div>)}
    </Card>
  );

  if (st.key === 'offline') {
    const age = status.heartbeat_age_s != null ? ` (ultimo segnale ${fmtDuration(status.heartbeat_age_s * 1000)} fa)` : '';
    return box('#f87171', `🔴 Il bot non risponde${age}`,
      ['I comandi che premi restano in coda e partono appena il bot torna online.']);
  }
  if (st.key === 'draining') {
    return box('#fbbf24', `⏳ Pausa in corso — finisco ${nOpen} ${nOpen === 1 ? 'posizione' : 'posizioni'}`,
      ['Non apro nuovi trade. Le posizioni aperte si chiudono da sole (stop loss, take profit o uscita del bot).',
       'Quando sono tutte chiuse il bot passa in pausa e puoi azzerare il portafoglio da Impostazioni.']);
  }
  if (st.key === 'paused') {
    return box('#94a3b8', '⏸ Bot in pausa',
      ['Nessuna posizione aperta. Premi Avvia per far ripartire il bot, oppure azzera il portafoglio da Impostazioni.']);
  }
  const lines = [];
  if (cyc.running) lines.push('Analisi del mercato in corso…');
  else if (cyc.next_cycle_ms) lines.push(`Prossimo controllo del mercato alle ${fmtClock(cyc.next_cycle_ms)}` +
    (cyc.last_end_ms ? ` · ultimo alle ${fmtClock(cyc.last_end_ms)}` : ''));
  if (cyc.last_ok === false) lines.push(`⚠️ L'ultimo ciclo è fallito (${cyc.last_error || 'errore'}): riprovo tra pochi minuti.`);
  return box('#4ade80', `🟢 ${isBull ? 'Bull' : 'Hawk'} in funzione`, lines);
}

// Sezione KPI per un portafoglio
function PortfolioSection({ status, portfolio, busy, actionMsg, onCloseAll, onChartOpen, onPause, onResume, onClosePosition }) {
  const isBull = portfolio === 'bull';

  if (!status) return (
    <Card style={{ marginBottom: '16px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
      ⏳ Connessione al portafoglio {isBull ? '🐂 Bull' : '🦅 Hawk'}...
    </Card>
  );

  if (status.available !== true) return (
    <Card style={{ marginBottom: '16px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
      🔴 {isBull ? '🐂 Bull' : '🦅 Hawk'} — {status.message || 'nessun dato disponibile, riprovo tra pochi secondi'}
    </Card>
  );

  const st = botState(status);
  const positions = Array.isArray(status.positions) ? status.positions : [];
  const nOpen = positions.length;
  const mode = status.bot_mode;                       // running | draining | paused
  const canPause = mode === 'running' && !busy;
  const canStart = (mode === 'draining' || mode === 'paused') && !busy;
  // Tasto "Chiudi ora" su ogni posizione: solo se il bot di adesso lo sa fare (il battito lo dichiara) ed e' acceso.
  // Con il bot in paper la posizione e' finta: si chiude solo nel simulatore, nessun ordine su BitGet.
  const closer = status.can_close_position && status.bot_online !== false && onClosePosition
    ? { pending: status.close_position_pending || [], onClose: onClosePosition, simulated: status.exec_mode !== 'live' } : null;

  const budgetSpent = status.budget_spent_usd ?? 0;
  const budgetCap = status.budget_daily_cap_usd ?? 0.70;
  const budgetExhausted = budgetSpent >= budgetCap * 0.95;
  const equityLow = (status.equity ?? 1000) < 450;
  const pnlTotal = status.pnl_total ?? ((status.equity ?? 0) - (status.start_equity ?? 1000));
  const equityColor = pnlTotal > 0 ? '#4ade80' : pnlTotal < 0 ? (status.equity >= 800 ? '#fbbf24' : '#f87171') : '#e2e8f0';

  const btn = (enabled, color, label, onClick) => (
    <button disabled={!enabled} onClick={onClick} style={{
      flex: 1, padding: '12px', borderRadius: '10px', fontWeight: 'bold', fontSize: '14px',
      border: `1px solid ${enabled ? color : '#334155'}`,
      background: enabled ? color + '22' : 'rgba(51,65,85,0.2)',
      color: enabled ? color : '#475569', cursor: enabled ? 'pointer' : 'not-allowed',
    }}>{label}</button>
  );

  return (
    <>
      {/* Equity hero */}
      <Card style={{ marginBottom: '12px', textAlign: 'center', borderColor: equityColor + '55' }}>
        <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
          Equity — {isBull ? '🐂 Bull' : '🦅 Hawk'} · run #{status.run_no ?? 1}
        </div>
        <div style={{ fontSize: '36px', fontWeight: 'bold', color: equityColor }}>${fmt(status.equity)}</div>
        <div style={{ fontSize: '13px', fontWeight: 'bold', color: pnlColor(pnlTotal), marginTop: '2px' }}>
          {signed(pnlTotal)}$ ({signed(status.pnl_total_pct)}%) da ${fmt(status.start_equity, 0)}
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: '14px', marginTop: '8px', fontSize: '12px', flexWrap: 'wrap' }}>
          <span style={{ color: '#64748b' }}>Cassa <strong style={{ color: '#cbd5e1' }}>${fmt(status.cash)}</strong></span>
          <span style={{ color: '#64748b' }}>Margine <strong style={{ color: '#cbd5e1' }}>${fmt(status.margin_used, 0)}</strong></span>
          <span style={{ color: '#64748b' }}>Aperto <strong style={{ color: pnlColor(status.unrealized_pnl) }}>{signed(status.unrealized_pnl)}$</strong></span>
          <span style={{ color: '#64748b' }}>Oggi <strong style={{ color: pnlColor(status.day_pnl) }}>{signed(status.day_pnl)}$</strong></span>
        </div>
      </Card>

      {/* KPI secondari */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <Card style={{ flex: 1, textAlign: 'center', padding: '12px 8px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>Aperte</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', color: nOpen > 0 ? '#38bdf8' : '#94a3b8' }}>
            {nOpen}<span style={{ fontSize: '12px', color: '#475569' }}>/{status.max_open ?? '-'}</span>
          </div>
        </Card>
        <Card style={{ flex: 1, textAlign: 'center', padding: '12px 8px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>Chiuse</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{status.total_closed ?? '--'}</div>
        </Card>
        <Card style={{ flex: 1, textAlign: 'center', padding: '12px 8px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>Budget AI</div>
          <div style={{ fontSize: '18px', fontWeight: 'bold', color: budgetSpent > budgetCap * 0.85 ? '#fbbf24' : '#4ade80' }}>
            ${fmt(budgetSpent, 3)}
          </div>
          <div style={{ fontSize: '9px', color: '#475569' }}>/ ${fmt(budgetCap)} oggi</div>
        </Card>
      </div>

      {/* Stato del bot e comandi */}
      <StateBanner status={status} isBull={isBull} />

      <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
        {btn(canStart, '#4ade80', busy === 'resume' ? '⏳ Avvio…' : (mode === 'draining' ? '▶ Riprendi' : '▶ Avvia'), onResume)}
        {btn(canPause, '#fbbf24', busy === 'pause' ? '⏳ Pausa…' : '⏸ Pausa', onPause)}
      </div>
      {actionMsg && (
        <div style={{ marginBottom: '10px', fontSize: '12px', textAlign: 'center', color: actionMsg.ok ? '#4ade80' : '#fca5a5' }}>
          {actionMsg.text}
        </div>
      )}
      {mode === 'running' && (
        <div style={{ marginBottom: '12px', fontSize: '11px', color: '#475569', textAlign: 'center' }}>
          Pausa = il bot non apre nuovi trade e lascia finire quelli aperti (niente chiusure forzate).
        </div>
      )}

      {/* Avvisi */}
      {status.halt && (
        <Card style={{ marginBottom: '12px', borderColor: '#dc2626', background: 'rgba(220,38,38,0.08)', color: '#fca5a5', fontSize: '13px' }}>
          <div style={{ fontWeight: 'bold', marginBottom: '2px' }}>🛑 Nuovi trade bloccati: {status.halt}</div>
          <div style={{ color: '#94a3b8', fontSize: '12px' }}>
            Le posizioni aperte continuano a essere gestite. Il blocco si toglie da solo (nuovo giorno) o azzerando il portafoglio da Impostazioni.
          </div>
        </Card>
      )}
      {!status.halt && st.key === 'running' && budgetExhausted && (
        <Card style={{ marginBottom: '12px', borderColor: '#f59e0b', background: 'rgba(245,158,11,0.08)', fontSize: '13px' }}>
          <div style={{ color: '#fbbf24', fontWeight: 'bold', marginBottom: '2px' }}>
            ⚠️ Budget AI esaurito ({(budgetSpent / budgetCap * 100).toFixed(0)}% usato)
          </div>
          <div style={{ color: '#94a3b8', fontSize: '12px' }}>
            Oggi Claude non viene più interpellato: il bot continua con le sue regole. Da Impostazioni puoi azzerare il budget.
          </div>
        </Card>
      )}
      {!status.halt && equityLow && (
        <Card style={{ marginBottom: '12px', borderColor: '#dc2626', background: 'rgba(220,38,38,0.08)', fontSize: '13px' }}>
          <div style={{ color: '#f87171', fontWeight: 'bold', marginBottom: '2px' }}>
            🛑 Capitale sotto la soglia critica (${fmt(status.equity, 0)})
          </div>
          <div style={{ color: '#94a3b8', fontSize: '12px' }}>
            Metti in pausa e, a posizioni chiuse, azzera il portafoglio da Impostazioni per ripartire da 1000$.
          </div>
        </Card>
      )}
      {status.last_action && Date.now() - (status.last_action.ts || 0) < 15 * 60 * 1000 && (
        <Card style={{ marginBottom: '12px', fontSize: '12px', color: status.last_action.ok ? '#94a3b8' : '#fca5a5' }}>
          {status.last_action.ok ? '✓' : '✕'} {fmtClock(status.last_action.ts)} — {status.last_action.detail}
        </Card>
      )}

      {/* Chiudi tutto */}
      {nOpen > 0 && (
        <button
          disabled={busy === 'close'}
          onClick={onCloseAll}
          style={{
            width: '100%', padding: '10px', borderRadius: '10px', marginBottom: '12px',
            border: '1px solid #dc2626', background: 'rgba(220,38,38,0.1)',
            color: '#fca5a5', fontWeight: 'bold', fontSize: '13px',
            cursor: busy === 'close' ? 'not-allowed' : 'pointer', opacity: busy === 'close' ? 0.6 : 1,
          }}
        >
          {busy === 'close' ? '⏳ Chiusura…' : `🔒 Chiudi subito tutte le posizioni (${nOpen}) a prezzo di mercato`}
        </button>
      )}

      {/* Posizioni aperte */}
      {nOpen > 0 && (
        <>
          <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
            ⚡ Posizioni Aperte
          </h2>
          {positions.map((p) => {
            const sym = p.symbol || '?';
            const base = sym.replace('USDT', '').replace('PERP', '');
            const isLong = p.side === 1;
            return (
              <Card
                key={sym}
                onClick={() => onChartOpen(sym.endsWith('USDT') ? sym : sym + 'USDT', p)}
                style={{ marginBottom: '8px', cursor: 'pointer', borderColor: isLong ? '#164e63' : '#4c0519' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                    <CryptoIcon base={base} size={24} />
                    <span style={{
                      padding: '2px 7px', borderRadius: '5px', fontSize: '10px', fontWeight: 'bold',
                      background: isLong ? '#166534' : '#7f1d1d', color: 'white'
                    }}>{isLong ? 'LONG' : 'SHORT'}</span>
                    <span style={{ fontWeight: 'bold', fontSize: '14px' }}>{base}</span>
                    <span style={{ color: '#94a3b8', fontSize: '12px' }}>x{p.leverage ?? '--'}</span>
                    <span style={{ fontSize: '10px', color: '#475569', background: '#0f172a', padding: '1px 5px', borderRadius: '4px' }}>
                      {p.trade_type || 'medio'}
                    </span>
                    {(p.dca_count ?? 0) > 0 && <span style={{ color: '#fbbf24', fontSize: '10px' }}>DCA×{p.dca_count}</span>}
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ color: pnlColor(p.pnl), fontWeight: 'bold', fontSize: '16px' }}>{signed(p.pnl)}$</div>
                    <div style={{ color: pnlColor(p.pnl), fontSize: '11px' }}>{signed(p.pnl_pct)}% sul margine</div>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', fontSize: '11px', color: '#94a3b8' }}>
                  <span>Entrata <strong style={{ color: '#e2e8f0' }}>${fmt(p.entry, p.entry < 1 ? 5 : 2)}</strong></span>
                  <span>
                    Ora <strong style={{ color: '#e2e8f0' }}>${fmt(p.price, p.price < 1 ? 5 : 2)}</strong>
                    <span style={{ color: p.price_source === 'live' ? '#4ade80' : '#fbbf24', marginLeft: '4px' }}>
                      {p.price_source === 'live' ? '●' : p.price_source === 'bot' ? '◐' : '○'}
                    </span>
                  </span>
                  <span>Margine <strong style={{ color: '#e2e8f0' }}>${fmt(p.margin, 0)}</strong></span>
                </div>
                <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '10px', flexWrap: 'wrap' }}>
                  {p.sl && <span style={{ color: '#f87171' }}>SL ${fmt(p.sl, p.sl < 1 ? 5 : 2)}</span>}
                  {p.tp && <span style={{ color: '#4ade80' }}>TP ${fmt(p.tp, p.tp < 1 ? 5 : 2)}</span>}
                  {p.liq && <span style={{ color: '#64748b' }}>Liq ${fmt(p.liq, p.liq < 1 ? 5 : 2)}</span>}
                  {p.open_ms && <span style={{ color: '#64748b' }}>aperta da {fmtDuration(Date.now() - p.open_ms)}</span>}
                </div>
                {p.price_source !== 'live' && (
                  <div style={{ fontSize: '10px', color: '#a16207', marginTop: '4px' }}>
                    {p.price_source === 'bot' ? 'Prezzo dell’ultimo ciclo del bot (quello live non è raggiungibile)' : 'Prezzo non disponibile: P&L non calcolabile'}
                  </div>
                )}
                {closer && (
                  <div onClick={(e) => e.stopPropagation()}>
                    <CloseControl p={{ ...p, symbol: base }} closer={closer} />
                  </div>
                )}
                <div style={{ fontSize: '10px', color: '#334155', marginTop: '4px', textAlign: 'right' }}>📈 tocca per il grafico</div>
              </Card>
            );
          })}
        </>
      )}

      {nOpen === 0 && (
        <Card style={{ marginBottom: '12px', textAlign: 'center', color: '#475569', fontSize: '13px' }}>
          Nessuna posizione aperta al momento
        </Card>
      )}
    </>
  );
}

export default function Dashboard() {
  const [prices, setPrices] = useState({});
  const [statuses, setStatuses] = useState({ hawk: null, bull: null });
  const [portfolio, setPortfolio] = useState('hawk'); // 'hawk' | 'bull'
  const [now, setNow] = useState(new Date());
  const [chartState, setChartState] = useState(null);
  const [busy, setBusy] = useState({ hawk: null, bull: null });        // 'pause' | 'resume' | 'close' | null
  const [actionMsg, setActionMsg] = useState({ hawk: null, bull: null });

  const fetchOne = useCallback(async (pf) => {
    try {
      const r = await apiFor(pf).getStatus();
      setStatuses(s => ({ ...s, [pf]: r.data }));
    } catch (e) {
      // se il server non risponde non cancello l'ultimo stato buono: segno solo che e' vecchio
      setStatuses(s => (s[pf] ? s : { ...s, [pf]: { available: false, message: 'Server non raggiungibile: riprovo tra pochi secondi' } }));
    }
  }, []);
  const fetchStatus = useCallback(() => Promise.all([fetchOne('hawk'), fetchOne('bull')]), [fetchOne]);

  const fetchPrices = useCallback(async () => {
    try { const p = await deskAPI.getPrices(); setPrices(p.data); } catch {}
  }, []);

  useEffect(() => { fetchStatus(); const t = setInterval(fetchStatus, 6000); return () => clearInterval(t); }, [fetchStatus]);
  useEffect(() => { fetchPrices(); const t = setInterval(fetchPrices, 60000); return () => clearInterval(t); }, [fetchPrices]);
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 15000); return () => clearInterval(t); }, []);

  const marketLive = Object.keys(prices).length > 0;
  const dateLabel = now.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' });
  const timeLabel = now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  const activeStatus = statuses[portfolio];

  const openChart = (symbol, tradeInfo = null) => setChartState({ symbol, tradeInfo });
  const closeChart = () => setChartState(null);

  const say = (pf, ok, text) => {
    setActionMsg(m => ({ ...m, [pf]: { ok, text } }));
    setTimeout(() => setActionMsg(m => ({ ...m, [pf]: null })), 12000);
  };

  // Esegue un comando, mostra l'esito e rilegge lo stato subito (il server lo calcola dal flag, quindi e' immediato).
  const run = async (pf, kind, call, okFallback) => {
    setBusy(b => ({ ...b, [pf]: kind }));
    try {
      const { data } = await call();
      if (data && data.bot_mode) {
        setStatuses(s => s[pf] ? ({ ...s, [pf]: { ...s[pf], paused: data.paused, bot_mode: data.bot_mode, draining: data.bot_mode === 'draining' } }) : s);
      }
      say(pf, true, data?.message || okFallback);
    } catch (e) {
      say(pf, false, `Errore: ${errMsg(e)}`);
    } finally {
      setBusy(b => ({ ...b, [pf]: null }));
      fetchOne(pf);
      setTimeout(() => fetchOne(pf), 2500);
      setTimeout(() => fetchOne(pf), 8000);
    }
  };

  const handlePause = () => run(portfolio, 'pause', () => apiFor(portfolio).pause(), 'Pausa attivata.');
  const handleResume = () => run(portfolio, 'resume', () => apiFor(portfolio).resume(), 'Bot avviato.');
  // Chiude UNA posizione a mano (stesso comando della pagina Live). Ritorna {ok, message} per il tasto.
  const handleClosePosition = (pf) => async (symbol) => {
    try {
      const { data } = await apiFor(pf).closePosition(symbol);
      return { ok: true, message: data?.message || 'Chiusura inviata.' };
    } catch (e) {
      return { ok: false, message: errMsg(e) };
    } finally {
      fetchOne(pf);
      setTimeout(() => fetchOne(pf), 2500);
      setTimeout(() => fetchOne(pf), 8000);
    }
  };
  const handleCloseAll = () => {
    const n = activeStatus?.open_positions ?? 0;
    if (!window.confirm(`Chiudere subito tutte le ${n} posizioni a prezzo di mercato?\n\nIl bot non si ferma: se non lo metti in pausa potrà riaprirne di nuove.`)) return;
    return run(portfolio, 'close', () => apiFor(portfolio).closeAll(), 'Chiusura inviata.');
  };

  const chip = (pf, label, color) => {
    const st = botState(statuses[pf]);
    return (
      <div style={{
        flex: 1, padding: '6px 10px', borderRadius: '10px', fontSize: '12px', textAlign: 'center',
        background: st.color + '14', border: `1px solid ${st.color}55`, color: st.key === 'running' ? color : st.color,
      }}>
        {label} {st.key === 'running' ? '● ' : st.key === 'offline' ? '○ ' : st.key === 'draining' ? '◐ ' : '⏸ '}{st.text}
      </div>
    );
  };

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div>
          <h1 style={{
            fontSize: '22px', fontWeight: 'bold',
            background: 'linear-gradient(90deg, #f1f5f9, #38bdf8)',
            WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
            margin: 0,
          }}>💹 Trade non reale</h1>
          <div style={{ fontSize: '10px', color: '#475569', fontWeight: 700, letterSpacing: '0.08em', marginTop: '3px' }}>
            ○ PAPER MODE · soldi simulati
          </div>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          <StatusChip label="Mercato" ok={marketLive} okText="Live" badText="Offline" />
        </div>
      </div>

      <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '16px' }}>
        {dateLabel} · <strong style={{ color: '#94a3b8' }}>{timeLabel}</strong>
        {activeStatus?.day && <span> · Giorno {activeStatus.day}</span>}
        {activeStatus?.cycle?.count != null && <span> · Ciclo #{activeStatus.cycle.count}</span>}
        {activeStatus?.version && <span> · v{activeStatus.version}</span>}
      </div>

      {/* Stato dei due bot */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '14px' }}>
        {chip('hawk', '🦅 Hawk', '#38bdf8')}
        {chip('bull', '🐂 Bull', '#a78bfa')}
      </div>

      {/* Selettore portafoglio */}
      <div style={{
        display: 'flex', gap: '6px', marginBottom: '14px',
        background: '#1e293b', borderRadius: '12px', padding: '4px', border: '1px solid #334155'
      }}>
        {[['hawk', '🦅 Hawk', '#38bdf8'], ['bull', '🐂 Bull', '#7c3aed']].map(([id, label, color]) => (
          <button key={id} onClick={() => setPortfolio(id)}
            style={{
              flex: 1, padding: '10px', border: 'none', borderRadius: '10px',
              background: portfolio === id ? color : 'transparent',
              color: portfolio === id ? '#fff' : '#64748b',
              fontWeight: 'bold', cursor: 'pointer', fontSize: '13px', transition: 'all 0.15s',
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* KPI portafoglio selezionato */}
      <DeskErrorBoundary>
        <PortfolioSection
          status={activeStatus}
          portfolio={portfolio}
          busy={busy[portfolio]}
          actionMsg={actionMsg[portfolio]}
          onCloseAll={handleCloseAll}
          onChartOpen={openChart}
          onPause={handlePause}
          onResume={handleResume}
          onClosePosition={handleClosePosition(portfolio)}
        />
      </DeskErrorBoundary>

      {/* ── Mercato Live ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '4px', marginTop: '8px', color: '#cbd5e1' }}>
        📊 Mercato Live
      </h2>
      <p style={{ fontSize: '11px', color: '#475569', marginBottom: '8px' }}>
        {V2_SYMBOLS.length} simboli monitorati dal Bot V2 — tocca per aprire il grafico
      </p>
      <MarketCarousel
        symbols={V2_SYMBOLS}
        prices={prices}
        onSymbolClick={(sym) => openChart(sym)}
      />

      {/* Modal grafico */}
      <ChartModal
        symbol={chartState?.symbol || null}
        tradeInfo={chartState?.tradeInfo || null}
        onClose={closeChart}
      />
    </div>
  );
}

// Esportato solo per la prova di rendering (non cambia nulla per l app)
export { PortfolioSection };
