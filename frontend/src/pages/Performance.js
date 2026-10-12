import React, { useState, useEffect, useCallback } from 'react';
import { deskAPI, bullAPI } from '../api';
import { fmtDateTime, PARAM_ROWS } from '../deskUi';

const GOOD   = '#4ade80';
const BAD    = '#f87171';
const MUTED  = '#94a3b8';
const BORDER = '#334155';
const SURF   = '#1e293b';
const ACCENT = '#38bdf8';

const Card = ({ children, style }) => (
  <div style={{ background: SURF, borderRadius: '14px', padding: '14px', border: `1px solid ${BORDER}`, ...style }}>
    {children}
  </div>
);

const sign = (v) => (v > 0 ? '+' : '');
const fmt  = (v) => `${sign(v)}${Number(v).toFixed(2)}$`;
const pct  = (w, t) => (t > 0 ? Math.round(w / t * 100) : 0);

const fmtTime = (ms) => {
  if (!ms) return '--';
  const d = new Date(ms);
  return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
};

const fmtDay = (iso) => {
  try {
    const d = new Date(iso + 'T00:00:00Z');
    return d.toLocaleDateString('it-IT', { weekday: 'short', day: '2-digit', month: 'short', timeZone: 'UTC' });
  } catch { return iso; }
};

const WinBadge = ({ wins, total }) => {
  const w = pct(wins, total);
  return (
    <span style={{
      fontSize: '11px', fontWeight: 'bold', padding: '2px 7px', borderRadius: '20px',
      background: w >= 50 ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
      color: w >= 50 ? GOOD : BAD,
    }}>
      {w}% WR
    </span>
  );
};

const PnlBadge = ({ value }) => (
  <span style={{ fontWeight: 'bold', color: value >= 0 ? GOOD : BAD, fontSize: '14px' }}>
    {fmt(value)}
  </span>
);

// Riepilogo totale in cima
const TotalsBar = ({ perf }) => {
  if (!perf) return null;
  const { total_trades, winning_trades, losing_trades, total_pnl, win_rate, avg_pnl_per_trade, profit_factor } = perf;
  const items = [
    ['Trade', total_trades, '#f1f5f9'],
    ['Profit', winning_trades, GOOD],
    ['Loss', losing_trades, BAD],
    ['Win%', `${win_rate}%`, win_rate >= 50 ? GOOD : BAD],
    ['P&L', fmt(total_pnl), total_pnl >= 0 ? GOOD : BAD],
    ['Media', fmt(avg_pnl_per_trade), avg_pnl_per_trade >= 0 ? GOOD : BAD],
  ];
  if (profit_factor != null) items.push(['P.Factor', profit_factor, profit_factor >= 1 ? GOOD : BAD]);

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '16px',
    }}>
      {items.map(([label, value, color]) => (
        <div key={label} style={{
          background: SURF, border: `1px solid ${BORDER}`, borderRadius: '10px',
          padding: '8px 12px', textAlign: 'center', flex: '1 1 calc(33% - 6px)',
        }}>
          <div style={{ fontSize: '10px', color: MUTED, marginBottom: '3px' }}>{label}</div>
          <div style={{ fontSize: '15px', fontWeight: 'bold', color }}>{value}</div>
        </div>
      ))}
    </div>
  );
};

// Blocco per-simbolo dentro un giorno
const SymbolRow = ({ sym, s }) => (
  <div style={{
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '6px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px',
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{ fontWeight: 'bold', color: '#f1f5f9', minWidth: '52px' }}>{sym.replace('USDT', '')}</span>
      <WinBadge wins={s.wins} total={s.trades} />
      <span style={{ color: MUTED, fontSize: '11px' }}>
        {s.wins}✅ {s.losses}❌ / {s.trades}
      </span>
    </div>
    <PnlBadge value={s.total_pnl} />
  </div>
);

// Riga singolo trade
const TradeRow = ({ t }) => {
  const sideLabel = t.side === 1 ? '▲ L' : '▼ S';
  const sideColor = t.side === 1 ? '#38bdf8' : '#c084fc';
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '6px',
      padding: '5px 0', borderBottom: `1px solid rgba(51,65,85,0.5)`,
      fontSize: '12px',
    }}>
      <span style={{ color: MUTED, minWidth: '36px' }}>{fmtTime(t.close_ms)}</span>
      <span style={{ color: sideColor, fontWeight: 'bold', minWidth: '20px' }}>{sideLabel}</span>
      <span style={{ color: '#cbd5e1', minWidth: '44px', fontWeight: 'bold' }}>{(t.symbol || '').replace('USDT', '')}</span>
      <span style={{ color: MUTED, fontSize: '10px', minWidth: '36px' }}>{t.trade_type}</span>
      {t.partial && <span style={{ fontSize: '9px', color: ACCENT, border: `1px solid ${ACCENT}`, borderRadius: '4px', padding: '0 3px' }}>PART</span>}
      <span style={{ marginLeft: 'auto', fontWeight: 'bold', color: t.net >= 0 ? GOOD : BAD }}>
        {fmt(t.net)}
      </span>
    </div>
  );
};

// Card di un giorno
const DayCard = ({ day, data, defaultOpen }) => {
  const [open, setOpen] = useState(defaultOpen);
  const [showTrades, setShowTrades] = useState(false);

  const isPositive = data.total_pnl >= 0;
  const emoji = isPositive ? '📈' : '📉';

  return (
    <Card style={{ marginBottom: '10px' }}>
      {/* Header giorno — cliccabile */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '15px' }}>{emoji}</span>
          <span style={{ fontWeight: 'bold', color: '#f1f5f9', fontSize: '14px' }}>{fmtDay(day)}</span>
          <WinBadge wins={data.wins} total={data.total_trades} />
          <span style={{ fontSize: '11px', color: MUTED }}>{data.wins}✅ {data.losses}❌</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <PnlBadge value={data.total_pnl} />
          <span style={{ color: MUTED, fontSize: '14px' }}>{open ? '▲' : '▼'}</span>
        </div>
      </div>

      {open && (
        <div style={{ marginTop: '12px' }}>
          {/* per simbolo */}
          <div style={{ fontSize: '12px', color: MUTED, marginBottom: '6px', fontWeight: 'bold', letterSpacing: '0.05em' }}>
            ASSET
          </div>
          {Object.entries(data.by_symbol)
            .sort((a, b) => b[1].total_pnl - a[1].total_pnl)
            .map(([sym, s]) => <SymbolRow key={sym} sym={sym} s={s} />)}

          {/* espandi/comprimi lista trade */}
          <div
            onClick={() => setShowTrades(t => !t)}
            style={{
              marginTop: '10px', cursor: 'pointer', fontSize: '12px', color: ACCENT,
              display: 'flex', alignItems: 'center', gap: '4px',
            }}
          >
            {showTrades ? '▲ Nascondi' : `▼ Vedi ${data.total_trades} trade`}
          </div>
          {showTrades && (
            <div style={{ marginTop: '8px' }}>
              {data.trades.map((t, i) => <TradeRow key={i} t={t} />)}
            </div>
          )}
        </div>
      )}
    </Card>
  );
};


// Riga etichetta / valore
const Row = ({ label, value, color }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px' }}>
    <span style={{ color: MUTED }}>{label}</span>
    <span style={{ fontWeight: 'bold', color: color || '#f1f5f9' }}>{value}</span>
  </div>
);

const REASON_LABEL = {
  'stop loss': 'Stop loss', 'take profit': 'Take profit', 'liquidazione': 'Liquidazione',
  'chiusura Claude': 'Uscita decisa dal bot', 'chiusura manuale': 'Chiusura manuale',
};

// Metriche estese (tab Statistiche)
const ExtraStats = ({ perf }) => (
  <Card style={{ marginBottom: '12px' }}>
    <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '6px', color: '#f1f5f9' }}>📐 Qualità dei trade</div>
    <Row label="Vincita media" value={fmt(perf.avg_win ?? 0)} color={GOOD} />
    <Row label="Perdita media" value={fmt(perf.avg_loss ?? 0)} color={BAD} />
    <Row label="Miglior trade" value={fmt(perf.best_trade ?? 0)} color={GOOD} />
    <Row label="Peggior trade" value={fmt(perf.worst_trade ?? 0)} color={BAD} />
    <Row label="Calo massimo (drawdown)" value={`-${Number(perf.max_drawdown ?? 0).toFixed(2)}$`} color={BAD} />
    <Row label="Durata media" value={perf.avg_hold_hours != null ? `${perf.avg_hold_hours} h` : '--'} />
    <Row label="Commissioni pagate" value={`-${Number(perf.total_fees ?? 0).toFixed(2)}$`} />
    {perf.partial_closes > 0 && <Row label="Chiusure parziali incluse" value={perf.partial_closes} />}
  </Card>
);

const BucketCard = ({ title, data, labelMap = {} }) => (
  Object.keys(data || {}).length > 0 ? (
    <Card style={{ marginBottom: '12px' }}>
      <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '10px', color: '#f1f5f9' }}>{title}</div>
      {Object.entries(data).map(([k, s]) => (
        <div key={k} style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '7px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontWeight: 'bold', color: '#f1f5f9', textTransform: 'capitalize' }}>{labelMap[k] || k}</span>
            <WinBadge wins={s.wins} total={s.trades} />
            <span style={{ color: MUTED, fontSize: '11px' }}>{s.trades} trade</span>
          </div>
          <PnlBadge value={s.net_pnl} />
        </div>
      ))}
    </Card>
  ) : null
);


function RunCard({ run, current, isCurrent }) {
  const pnl = run.pnl ?? run.net_total ?? 0;
  const changed = !isCurrent && current ? PARAM_ROWS.filter(([, get]) => {
    const a = get(run.params), b = get(current.params);
    return a != null && b != null && String(a) !== String(b);
  }) : [];
  const [open, setOpen] = useState(isCurrent);
  return (
    <Card style={{ marginBottom: '10px', borderColor: isCurrent ? ACCENT : BORDER }}>
      <div onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ fontWeight: 'bold', color: '#f1f5f9', fontSize: '14px' }}>
            Run #{run.run_no ?? '?'} {isCurrent && <span style={{ color: ACCENT, fontSize: '11px' }}>● in corso</span>}
          </div>
          <div style={{ fontSize: '11px', color: MUTED }}>
            {fmtDateTime(run.started_ms)} → {isCurrent ? 'adesso' : fmtDateTime(run.ended_ms)}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <PnlBadge value={pnl} />
          <div style={{ fontSize: '11px', color: MUTED }}>{run.trades} trade · {run.win_rate ?? 0}% WR</div>
        </div>
      </div>
      {changed.length > 0 && (
        <div style={{ marginTop: '8px', fontSize: '11px', color: '#fbbf24' }}>
          ≠ Parametri diversi dalla run attuale: {changed.map(([l]) => l).join(', ')}
        </div>
      )}
      {open && (
        <div style={{ marginTop: '10px' }}>
          <Row label="Equity finale" value={run.end_equity != null ? `$${Number(run.end_equity).toFixed(2)}` : '--'} />
          <Row label="Vincenti / perdenti" value={`${run.wins ?? 0} / ${run.losses ?? 0}`} />
          <Row label="Netto dei trade" value={fmt(run.net_total ?? 0)} color={(run.net_total ?? 0) >= 0 ? GOOD : BAD} />
          <Row label="Miglior / peggior trade" value={`${fmt(run.best ?? 0)} / ${fmt(run.worst ?? 0)}`} />
          {run.profit_factor != null && <Row label="Profit factor" value={run.profit_factor} />}
          {run.max_drawdown != null && <Row label="Calo massimo" value={`-${Number(run.max_drawdown).toFixed(2)}$`} color={BAD} />}
          <div style={{ fontSize: '12px', color: MUTED, margin: '10px 0 4px', fontWeight: 'bold' }}>PARAMETRI USATI</div>
          {PARAM_ROWS.map(([label, get, show]) => {
            const v = get(run.params);
            if (v == null) return null;
            const cur = current ? get(current.params) : null;
            const diff = !isCurrent && cur != null && String(cur) !== String(v);
            return <Row key={label} label={label} value={show(v) + (diff ? `  (ora ${show(cur)})` : '')} color={diff ? '#fbbf24' : undefined} />;
          })}
        </div>
      )}
    </Card>
  );
}

function RunsTab({ runs }) {
  if (!runs) return <div style={{ textAlign: 'center', color: MUTED, padding: '30px' }}>Caricamento…</div>;
  return (
    <>
      <div style={{ fontSize: '12px', color: MUTED, marginBottom: '10px' }}>
        Ogni volta che azzeri il portafoglio da Impostazioni, la run finisce qui con i suoi risultati e i parametri usati:
        così confronti prima e dopo un cambio di parametri.
      </div>
      <RunCard run={runs.current} current={runs.current} isCurrent />
      {runs.archived.length === 0 ? (
        <Card><div style={{ textAlign: 'center', color: MUTED, padding: '16px', fontSize: '13px' }}>
          Nessuna run archiviata ancora. Compaiono dopo il primo azzeramento del portafoglio.
        </div></Card>
      ) : runs.archived.map(r => <RunCard key={r.archive} run={r} current={runs.current} isCurrent={false} />)}
    </>
  );
}

export default function Performance() {
  // portfolio selector: 'hawk' | 'bull'
  const [portfolio, setPortfolio] = useState('hawk');

  const [diary,   setDiary]   = useState(null);
  const [perf,    setPerf]    = useState(null);
  const [runs,    setRuns]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab,     setTab]     = useState('diary'); // 'diary' | 'stats'

  const load = useCallback((pf = portfolio) => {
    setLoading(true);
    const api = pf === 'bull' ? bullAPI : deskAPI;
    Promise.all([
      api.getDiary().catch(() => null),
      api.getPerformance().catch(() => null),
      api.getRuns().catch(() => null),
    ]).then(([d, p, r]) => {
      if (d?.data) setDiary(d.data);
      if (p?.data) setPerf(p.data);
      if (r?.data) setRuns(r.data);
      setLoading(false);
    });
  }, [portfolio]);

  useEffect(() => {
    setDiary(null);
    setPerf(null);
    setRuns(null);
    load(portfolio);
    const id = setInterval(() => load(portfolio), 120_000);
    return () => clearInterval(id);
  }, [portfolio, load]);

  const TabBtn = ({ id, label }) => (
    <button
      onClick={() => setTab(id)}
      style={{
        flex: 1, padding: '10px 4px', border: 'none', borderRadius: '10px',
        background: tab === id ? ACCENT : 'transparent',
        color: tab === id ? '#0f172a' : MUTED,
        fontWeight: 'bold', cursor: 'pointer', fontSize: '12px',
      }}
    >
      {label}
    </button>
  );

  const hasDiary = diary?.days?.length > 0;
  const hasPerf  = perf?.total_trades > 0;

  const portfolioColor = portfolio === 'bull' ? '#a78bfa' : '#38bdf8';

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <h1 style={{ fontSize: '22px', fontWeight: 'bold', margin: 0 }}>🏆 Performance</h1>
        <button
          onClick={() => load(portfolio)}
          disabled={loading}
          style={{
            padding: '6px 12px', borderRadius: '8px', border: `1px solid ${BORDER}`,
            background: 'none', color: loading ? MUTED : ACCENT,
            fontSize: '12px', cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? '...' : '↻ Aggiorna'}
        </button>
      </div>

      {/* Selettore portfolio */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '14px', background: SURF, borderRadius: '12px', padding: '4px', border: `1px solid ${BORDER}` }}>
        {[['hawk', '🦅 Hawk'], ['bull', '🐂 Bull']].map(([id, label]) => (
          <button key={id} onClick={() => setPortfolio(id)}
            style={{
              flex: 1, padding: '10px', border: 'none', borderRadius: '10px',
              background: portfolio === id ? (id === 'bull' ? '#7c3aed' : ACCENT) : 'transparent',
              color: portfolio === id ? '#fff' : MUTED,
              fontWeight: 'bold', cursor: 'pointer', fontSize: '13px',
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* Tab selector */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px', background: SURF, borderRadius: '12px', padding: '4px', border: `1px solid ${BORDER}` }}>
        <TabBtn id="diary" label="📖 Diario" />
        <TabBtn id="stats" label="📊 Statistiche" />
        <TabBtn id="runs" label="🧪 Run" />
      </div>

      {loading && !hasDiary && tab !== 'runs' && (
        <div style={{ textAlign: 'center', color: MUTED, padding: '40px', fontSize: '14px' }}>
          Caricamento...
        </div>
      )}

      {!loading && !hasDiary && !hasPerf && tab !== 'runs' && (
        <Card>
          <div style={{ textAlign: 'center', color: MUTED, padding: '30px' }}>
            <div style={{ fontSize: '32px', marginBottom: '10px' }}>📭</div>
            <div>Nessun trade chiuso ancora.</div>
            <div style={{ fontSize: '12px', marginTop: '6px' }}>
              Il diario si aggiorna in automatico ogni volta che il bot chiude un trade.
            </div>
          </div>
        </Card>
      )}

      {/* ── TAB DIARIO ── */}
      {tab === 'diary' && hasDiary && (
        <>
          <TotalsBar perf={perf} />
          {diary.days.map((d, i) => (
            <DayCard key={d.day} day={d.day} data={d} defaultOpen={i === 0} />
          ))}
        </>
      )}

      {/* ── TAB STATISTICHE ── */}
      {tab === 'stats' && hasPerf && (
        <>
          <TotalsBar perf={perf} />

          {/* Per simbolo — tutti i giorni aggregati */}
          <Card style={{ marginBottom: '12px' }}>
            <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '10px', color: '#f1f5f9' }}>
              💱 Totale per Asset {portfolio === 'bull' ? '🐂' : '🦅'}
            </div>
            {Object.entries(perf.by_symbol || {})
              .sort((a, b) => b[1].net_pnl - a[1].net_pnl)
              .map(([sym, s]) => (
                <div key={sym} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '7px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 'bold', color: '#f1f5f9', minWidth: '52px' }}>{sym.replace('USDT', '')}</span>
                    <WinBadge wins={s.wins} total={s.trades} />
                    <span style={{ color: MUTED, fontSize: '11px' }}>{s.trades} trade</span>
                  </div>
                  <PnlBadge value={s.net_pnl} />
                </div>
              ))}
          </Card>

          <BucketCard title="⚡ Per tipo di trade" data={perf.by_type} />
          <BucketCard title="🎯 Come si sono chiusi" data={perf.by_reason} labelMap={REASON_LABEL} />
          <BucketCard title="↕️ Long / Short" data={perf.by_side} labelMap={{ long: 'Long', short: 'Short' }} />
          <ExtraStats perf={perf} />

          <div style={{ fontSize: '11px', color: '#475569', textAlign: 'center', marginTop: '8px' }}>
            P&L al netto di commissioni e slippage (paper mode)
          </div>
        </>
      )}

      {/* ── TAB RUN ── */}
      {tab === 'runs' && <RunsTab runs={runs} />}
    </div>
  );
}
