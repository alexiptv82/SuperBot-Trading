import React, { useCallback, useEffect, useState } from 'react';
import API from '../api';
import { BrainCloseControls } from '../components/OverviewCloseControls';
import ArenaCloseControls from '../components/ArenaCloseControls';
import { ARENA_PROFILES, money, portfolioFromExisting, sanitizedTrial, trialTotalPnl } from '../brainArenaModel';
import { arenaCloseUiEnabled } from '../arenaCloseModel';

const BLOCK = { background: '#172338', border: '1px solid #30465e', borderRadius: 16, padding: 16 };
const MUTED = { color: '#a4b6cd', fontSize: 12 };
const PANELS = ['Panoramica', 'Posizioni aperte', 'Storico', 'Performance', 'Memoria'];
const MODELS = Object.freeze({
  deepseek: { accent: '#4ade80', icon: '🧠' },
  qwen: { accent: '#60a5fa', icon: '🔷' },
  minimax: { accent: '#c084fc', icon: '💠' },
});
const label = side => side === 1 ? 'LONG' : side === -1 ? 'SHORT' : '—';
const shown = (value) => value === null || value === undefined || value === '' ? '—' : value;

function Metric({ title, value }) {
  return <div style={{ ...BLOCK, background: '#0e1a2d', padding: 12, minWidth: 0 }}>
    <div style={MUTED}>{title}</div>
    <div style={{ fontSize: 18, fontWeight: 800, marginTop: 4, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
  </div>;
}
function Trade({ t, open = false }) {
  const price = t.entry ?? t.entry_price ?? t.fill_price;
  const exit = t.exit ?? t.exit_price;
  const pnl = open ? (t.unrealized_pnl ?? null) : (t.realized_pnl ?? null);
  return <article style={{ ...BLOCK, marginBottom: 9 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
      <strong>{shown(t.symbol)} · {label(t.side)} · {shown(t.leverage)}×</strong>
      <strong style={{ color: pnl === null ? '#cbd5e1' : Number(pnl) < 0 ? '#fda4af' : '#4ade80' }}>{money(pnl)}</strong>
    </div>
    <div style={{ ...MUTED, marginTop: 7 }}>
      Entrata {shown(price)} · {open ? 'Stop ' + shown(t.stop ?? t.stop_price) : 'Uscita ' + shown(exit)}
      {' · '}Margine {money(t.margin ?? t.margin_used)}
    </div>
    {open && <div style={{ ...MUTED, marginTop: 5 }}>
      Prezzo disponibile: {t.price_source === 'ticker' ? shown(t.price) : '—'}
      {' · '}ROI: {t.price_source === 'ticker' && t.roi_pct != null ? shown(t.roi_pct) + '%' : '—'}
    </div>}
    {open && <div style={{ ...MUTED, marginTop: 5 }}>
      Take profit: {shown(t.take_profit ?? t.tp_price)} · Posizione PAPER
    </div>}
    {!open && <div style={{ ...MUTED, marginTop: 5 }}>Commissioni: {money(t.fees)} · Motivo: {shown(t.exit_reason ?? t.reason)}</div>}
  </article>;
}

export default function BrainArena() {
  const [chosen, select] = useState('deepseek');
  const [tab, setTab] = useState('Panoramica');
  const [rows, setRows] = useState({ deepseek: null, qwen: null, minimax: null });
  const [loading, setLoading] = useState(true);
  const [warning, setWarning] = useState(null);
  const [refresh, setRefresh] = useState(0);
  // Chiusure manuali dell'esperimento: solo con flag UI e rotte dedicate per AI attive sul server.
  const [closeInfo, setCloseInfo] = useState({});

  const fetchData = useCallback(async signal => {
    // Existing PAPER read APIs, unchanged. Missing data NEVER treated as zero.
    const [overview, status, trades] = await Promise.allSettled([
      API.get('/api/v3/overview', { signal }),
      API.get('/api/v3/brain/status', { signal }),
      API.get('/api/v3/brain/trades?limit=100', { signal }),
    ]);
    if (signal.aborted) return;
    const brain = overview.status === 'fulfilled'
      ? portfolioFromExisting(
          overview.value.data,
          status.status === 'fulfilled' ? status.value.data : null,
          trades.status === 'fulfilled' ? trades.value.data : null,
        ) : null;
    let shadow = { deepseek: null, qwen: null, minimax: null };
    // Disabled unless the independent read-only API has been audited and deployed.
    if (process.env.REACT_APP_BRAIN_ARENA_SHADOW_API === '1') {
      try {
        const response = await API.get('/api/v3/arena', { signal });
        if (signal.aborted) return;
        shadow = {
          deepseek: sanitizedTrial('deepseek', response?.data?.portfolios?.deepseek),
          qwen: sanitizedTrial('qwen', response?.data?.portfolios?.qwen),
          minimax: sanitizedTrial('minimax', response?.data?.portfolios?.minimax),
        };
      } catch (_) { /* Keep absent instead of showing stale/fake performance. */ }
    }
    const shownBrain = shadow.deepseek || brain;
    if (arenaCloseUiEnabled()) {
      const trial = ['deepseek', 'qwen', 'minimax'].filter(id => shadow[id]);
      const infos = await Promise.allSettled(trial.map(id => API.get(`/api/v3/arena/${id}/annotations`, { signal })));
      if (signal.aborted) return;
      const next = {};
      trial.forEach((id, i) => {
        const d = infos[i].status === 'fulfilled' ? infos[i].value.data : null;
        next[id] = d && d.ok === true && d.provider === id && Array.isArray(d.annotations)
          ? { ready: d.manual_close_ready === true, annotations: d.annotations } : null;
      });
      setCloseInfo(next);
    }
    setRows({ deepseek: shownBrain, qwen: shadow.qwen, minimax: shadow.minimax });
    setWarning(shownBrain ? null : 'Il Brain PAPER attuale non risponde. Non vengono mostrati numeri presunti.');
    setLoading(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal).catch(() => {
      if (!controller.signal.aborted) {
        setRows({ deepseek: null, qwen: null, minimax: null });
        setWarning('Dati PAPER non disponibili.');
        setLoading(false);
      }
    });
    const timer = setInterval(() => {
      if (!controller.signal.aborted) fetchData(controller.signal).catch(() => {});
    }, 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [fetchData, refresh]);

  const selected = ARENA_PROFILES.find(p => p.id === chosen);
  const data = rows[chosen];
  const totalRealized = trialTotalPnl(rows);
  // La prova e' "in corso" solo se i tre portafogli sono verificati con lo stesso T0 (stesso criterio del PnL comune).
  const trialLive = totalRealized !== null;
  return <main style={{ background: '#0b1323', color: '#eef5ff', minHeight: '100vh', padding: '16px 12px 100px', maxWidth: 1200, margin: '0 auto', fontFamily: 'system-ui, sans-serif' }}>
    <header style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'start', marginBottom: 16 }}>
      <div>
        <div style={{ ...MUTED, color: '#7dd3fc', fontWeight: 800, letterSpacing: 1.5 }}>SUPERBOT V3 · PAPER ONLY</div>
        <h1 style={{ margin: '5px 0', fontSize: 25 }}>🧠 AI Arena</h1>
        <div style={MUTED}>Confronto PAPER di 14 giorni · {trialLive
          ? 'prova in corso dal ' + new Date(rows.qwen.trial_start_ms).toLocaleDateString('it-IT')
          : 'in attesa di attivazione comune'}</div>
        <div style={{ ...MUTED, marginTop: 6 }}>
          Lettura automatica ogni 30 secondi · valori da dati verificati, non ordini
        </div>
      </div>
      <button onClick={() => setRefresh(v => v + 1)} style={{ padding: 9, borderRadius: 10, border: '1px solid #456079', color: '#e2e8f0', background: '#172338' }}>Aggiorna</button>
    </header>
    <section role="note" style={{ ...BLOCK, marginBottom: 14, borderColor: '#365375', color: '#b6cce2', fontSize: 13 }}>
      {trialLive ? <>
        <strong>Prova PAPER in corso.</strong> Tre portafogli indipendenti da 2.000 USDT, stesso universo,
        stesso mandato di rischio e stesso avvio. Nessun ordine reale; Falco e Toro non vengono toccati.
        Ogni AI ha comandi di chiusura separati, attivi solo se il suo servizio di uscita PAPER è sano.
      </> : <>
        <strong>Stato: sola lettura.</strong> DeepSeek può mostrare lo storico PAPER esistente,
        che non fa parte dei 14 giorni del nuovo esperimento.
        I tre risultati sono confrontabili soltanto dopo la verifica dei journal indipendenti
        e l'avvio contemporaneo dei tre portafogli.
        Finché Qwen e MiniMax non sono avviati, non esistono profitti o trade da mostrare.
        Questa pagina non apre posizioni e non modifica Falco o Toro.
        La chiusura manuale del Brain storico richiede un servizio PAPER sano e abilitazione esplicita;
        ogni AI dell'esperimento ha comandi di chiusura separati, attivi solo dopo abilitazione esplicita.
      </>}
    </section>
    {warning && <p role="alert" style={{ color: '#fda4af' }}>{warning}</p>}
    <section aria-label="Seleziona modello AI" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8, marginBottom: 15 }}>
      {ARENA_PROFILES.map(p => {
        const info = rows[p.id];
        const active = chosen === p.id;
        return <button key={p.id} onClick={() => { select(p.id); setTab('Panoramica'); }}
          aria-pressed={active} style={{ ...BLOCK, padding: '13px 8px', textAlign: 'center', cursor: 'pointer',
            borderColor: active ? MODELS[p.id].accent : '#30465e', boxShadow: active ? '0 0 0 1px ' + MODELS[p.id].accent : 'none',
            color: '#eef5ff', minWidth: 0 }}>
          <div style={{ fontSize: 22 }}>{MODELS[p.id].icon}</div>
          <strong style={{ fontSize: 14 }}>{p.title}</strong>
          <div style={{ ...MUTED, marginTop: 3, fontSize: 10 }}>
            {info ? (info.source === 'v3_existing_brain_paper' ? 'Storico precedente' : info.state) : 'Non avviato'}
          </div>
          <div style={{ fontSize: 18, fontWeight: 800, marginTop: 8 }}>2.000</div>
          <div style={{ ...MUTED, fontSize: 10 }}>USDT iniziali</div>
          <div style={{ color: info ? (Number(info.realized_pnl) < 0 ? '#fda4af' : '#4ade80') : '#94a3b8', fontSize: 12, marginTop: 8 }}>
            {info ? money(info.realized_pnl) : 'PnL —'}
          </div>
        </button>;
      })}
    </section>
    <div style={{ ...BLOCK, marginBottom: 14, display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 7, fontSize: 12 }}>
      <span>Capitale previsto per il test: <strong>6.000 USDT PAPER</strong></span>
      <span>PnL del test comune: <strong>{money(totalRealized)}</strong></span>
    </div>
    <nav aria-label="Dettagli del portafoglio" style={{ display: 'flex', gap: 7, overflowX: 'auto', paddingBottom: 12 }}>
      {PANELS.map(p => <button key={p} onClick={() => setTab(p)} aria-current={p === tab ? 'page' : undefined}
        style={{ padding: '9px 11px', border: '1px solid ' + (tab === p ? '#60a5fa' : '#30465e'),
          background: tab === p ? '#203552' : '#172338', color: '#eef5ff',
          borderRadius: 11, whiteSpace: 'nowrap', cursor: 'pointer' }}>{p}</button>)}
    </nav>
    <h2 style={{ fontSize: 19, marginTop: 4 }}>{selected.title} <span style={{ ...MUTED }}>· {selected.kind}</span></h2>
    {data?.source === 'v3_existing_brain_paper' && <div role="note" style={{ ...MUTED, marginBottom: 12 }}>
      Storico DeepSeek precedente al test: non incluso nel PnL comparativo dei tre portafogli.
    </div>}
    {!data ? <div role="status" style={BLOCK}>
      {loading ? 'Caricamento…' : 'Portafoglio non ancora disponibile. Nessuna operazione simulata da mostrare.'}
    </div> : <>
      {tab === 'Panoramica' && <>
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 9, marginBottom: 12 }}>
          <Metric title="Equity PAPER" value={data.equity_basis === 'open_unmarked' ? 'Non calcolabile' : money(data.equity)}/>
          <Metric title="Saldo contabile" value={money(data.settled_equity)}/>
          <Metric title="PnL realizzato" value={money(data.realized_pnl)}/>
          <Metric title="PnL aperto" value={money(data.unrealized_pnl)}/>
          <Metric title="Posizioni aperte" value={shown(data.open_count)}/>
          <Metric title="Trade chiusi" value={shown(data.total_closed)}/>
        </section>
        <div style={BLOCK}>
          <strong>Ultima decisione</strong>
          <div style={{ ...MUTED, marginTop: 7 }}>
            {data.last_decision ? [data.last_decision.symbol, data.last_decision.status,
              data.last_decision.strategy_id].filter(Boolean).join(' · ') : 'Non disponibile'}
          </div>
          <div style={{ ...MUTED, marginTop: 7 }}>
            Ultimo evento verificato: {Number.isSafeInteger(data.updated_ms) && data.updated_ms > 0
              ? new Date(data.updated_ms).toLocaleString('it-IT')
              : 'Non disponibile'}
          </div>
          <div style={{ ...MUTED, marginTop: 7 }}>Sorgente: {data.source}. Nessuna API di trading accessibile da questa pagina.</div>
        </div>
      </>}
      {tab === 'Posizioni aperte' && (data.open_positions == null
        ? <div role="status" style={BLOCK}>Dettagli delle posizioni non disponibili.</div>
        : data.open_positions.length === 0
          ? <div style={BLOCK}>Nessuna posizione aperta.</div>
          : chosen === 'deepseek' && data.source === 'v3_existing_brain_paper'
            ? <BrainCloseControls
                positions={data.open_positions}
                serverPending={data.close_pending === true}
                readOnly={process.env.REACT_APP_PREVIEW_READONLY === '1' ||
                          process.env.REACT_APP_ARENA_EXISTING_CLOSE !== '1' ||
                          data.manual_close_allowed !== true}
                allowCloseAll={false}
                onRefresh={() => setRefresh(v => v + 1)}
                renderPosition={t => <Trade t={t} open/>}
              />
            : data.source === 'arena_independent_journal_v1' && arenaCloseUiEnabled() && closeInfo[chosen]
              ? <ArenaCloseControls key={chosen} provider={chosen}
                  positions={data.open_positions}
                  ready={closeInfo[chosen].ready}
                  annotations={closeInfo[chosen].annotations}
                  onRefresh={() => setRefresh(v => v + 1)}
                  renderPosition={t => <Trade t={t} open/>}
                />
              : <section>
                {data.open_positions.map((t, i) => <Trade key={t.position_id || i} t={t} open/>)}
                <div role="status" style={{ ...MUTED, padding: 9 }}>
                  Chiusura manuale di {selected.title} non abilitata su questa dashboard:
                  richiede il servizio di uscita PAPER dedicato e l'attivazione esplicita.
                </div>
              </section>)}
      {tab === 'Storico' && (data.closed_trades == null
        ? <div role="status" style={BLOCK}>Storico non disponibile.</div>
        : data.closed_trades.length
          ? data.closed_trades.map((t, i) => <Trade key={t.position_id || i} t={t}/>)
          : <div style={BLOCK}>Nessun trade chiuso.</div>)}
      {tab === 'Performance' && <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 9 }}>
        <Metric title="P&L realizzato" value={money(data.realized_pnl)}/>
        <Metric title="PnL oggi (UTC)" value={money(data.day_pnl)}/>
        <Metric title="Win rate" value={data.win_rate == null ? '—' : shown(data.win_rate) + '%'}/>
        <Metric title="Margine in uso" value={money(data.margin_in_use)}/>
        <Metric title="Trade chiusi" value={shown(data.total_closed)}/>
        <Metric title="Capitale iniziale" value="2.000 USDT"/>
      </section>}
      {tab === 'Memoria' && <section>
        <div role="note" style={{ ...BLOCK, marginBottom: 12 }}>
          <strong>Registro delle esperienze · {selected.title}</strong>
          <p style={{ ...MUTED, marginTop: 8 }}>
            Il journal registra decisioni, NO_TRADE, esiti e chiusure manuali.
            Registrare un evento non significa che il modello abbia già imparato:
            la memoria condivisa sarà validata prima di essere utilizzata dal Brain principale.
          </p>
          <div style={{ ...MUTED, marginTop: 7 }}>
            Stato apprendimento: {data.learning_status === 'JOURNAL_EVIDENCE_ONLY_NOT_MODEL_TRAINING'
              ? 'Evidenze del journal verificate; apprendimento AI non ancora certificato'
              : 'Memoria operativa non ancora certificata'}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 9 }}>
          <Metric title="Decisioni registrate" value={shown(data.decision_count)}/>
          <Metric title="NO_TRADE registrati" value={shown(data.no_trade_count)}/>
          <Metric title="Trade con esito collegato" value={shown(data.verified_outcome_count)}/>
          <Metric title="Chiusure manuali registrate" value={shown(data.manual_close_count)}/>
          <Metric title="Motivazioni umane registrate"
            value={closeInfo[chosen] ? closeInfo[chosen].annotations.length : '—'}/>
        </div>
        <p style={{ ...MUTED, marginTop: 12 }}>
          Gli esempi manuali conservano l'origine umana; il motivo è solo quello indicato
          dall'operatore, mai dedotto dal risultato. Nessuna strategia viene modificata automaticamente.
        </p>
      </section>}
    </>}
  </main>;
}
