import { ago, botStatus, equityView, guardianView, lastRoundMs, staleLimitMs } from './paperBotsModel';
import { isActive } from './components/NavBar';

const NOW = 1_800_000_000_000;
const MIN = 60_000;
const run = (over = {}) => ({
  name: 'falco_evoluto', label: 'Falco Evoluto', available: true, state: 'running', paused: false,
  initial_equity: '1000', settled_equity: '1010', config: { cycle_minutes: 15 },
  guardian: { state: 'NORMAL', reasons: [], equity: '1042.5', session_start_equity: '1000', as_of_ms: NOW - 3 * MIN,
    unrealized: '32.5', peak_equity: '1050', giveback: '7.5', floor: null, budget: '80', risk_cap: null },
  decisions: [{ ts_ms: NOW - 3 * MIN, symbol: 'ETHUSDT', kind: 'NO_TRADE' }], ...over });

test('ago: minutes, hours, now, and no invented time', () => {
  expect(ago(NOW - 10_000, NOW)).toBe('ora');
  expect(ago(NOW + 5 * MIN, NOW)).toBe('ora');                       // orologi sfasati: mai "-5 min fa"
  expect(ago(NOW - 3 * MIN, NOW)).toBe('3 min fa');
  expect(ago(NOW - 65 * MIN, NOW)).toBe('1 h 05 min fa');
  for (const bad of [null, undefined, 0, -1, 'x', 1.5, NaN]) expect(ago(bad, NOW)).toBeNull();
});

test('the last round is the newest of guardian evaluation and decisions', () => {
  expect(lastRoundMs(run())).toBe(NOW - 3 * MIN);
  expect(lastRoundMs(run({ guardian: null, decisions: [{ ts_ms: NOW - 40 * MIN }, { ts_ms: NOW - 50 * MIN }] }))).toBe(NOW - 40 * MIN);
  expect(lastRoundMs(run({ guardian: null, decisions: [] }))).toBeNull();
  expect(lastRoundMs(run({ guardian: { as_of_ms: 'x' }, decisions: [{ ts_ms: null }] }))).toBeNull();
});

test('stale limit is two cycles plus five minutes, with a safe default', () => {
  expect(staleLimitMs(run())).toBe(35 * MIN);
  expect(staleLimitMs(run({ config: { cycle_minutes: 30 } }))).toBe(65 * MIN);
  expect(staleLimitMs(run({ config: {} }))).toBe(65 * MIN);
});

test('RUNNING only when the runner runs AND a round was recorded recently', () => {
  const ok = botStatus(run(), NOW);
  expect(ok).toMatchObject({ key: 'running', label: 'RUNNING', color: '#4ade80' });
  expect(ok.detail).toContain('3 min fa');
  const stale = botStatus(run({ guardian: { as_of_ms: NOW - 3 * 60 * MIN }, decisions: [{ ts_ms: NOW - 3 * 60 * MIN }] }), NOW);
  expect(stale.key).toBe('stale');
  expect(stale.color).toBe('#fbbf24');                                // ambra: non un RUNNING rassicurante
  expect(stale.detail).toContain('Nessun giro recente');
  expect(botStatus(run({ guardian: null, decisions: [] }), NOW).key).toBe('running_wait');
});

test('PAUSA wins over a heartbeat that still says running; halted and unknown are never RUNNING', () => {
  expect(botStatus(run({ paused: true }), NOW)).toMatchObject({ key: 'paused', label: 'PAUSA', color: '#fbbf24' });
  expect(botStatus(run({ state: 'halted' }), NOW)).toMatchObject({ key: 'halted', label: 'FERMO', color: '#f87171' });
  expect(botStatus(run({ state: null }), NOW).label).toBe('STATO N/D');
  expect(botStatus(run({ state: 'surprise' }), NOW).label).toBe('STATO N/D');
  expect(botStatus({ available: false, reason: 'not_started' }, NOW).label).toBe('NON AVVIATO');
  expect(botStatus({ available: false, reason: 'not_prepared' }, NOW).label).toBe('NON PREPARATO');
  expect(botStatus(null, NOW).label).toBe('NON PREPARATO');
});

test('equity: market value from the guardian when present, otherwise settled, never invented', () => {
  const e = equityView(run());
  expect(e).toMatchObject({ value: 1042.5, basis: 'market', total: 42.5, unrealized: 32.5, session: 42.5, settled: 1010 });
  expect(e.totalPct).toBeCloseTo(4.25, 5);
  const s = equityView(run({ guardian: null }));
  expect(s).toMatchObject({ value: 1010, basis: 'settled', total: 10, unrealized: null, session: null });
  const none = equityView({ available: true });
  expect(none).toMatchObject({ value: null, basis: null, total: null, totalPct: null });
});

test('guardian view: known states only, reasons translated, unknown codes dropped, normal has no cap', () => {
  const g = guardianView(run({ guardian: { state: 'LOCKED', reasons: ['below_floor', '<b>x</b>', 'session_loss'], risk_cap: '0',
    budget: '-5', floor: '1060', peak_equity: '1100', giveback: '40', as_of_ms: NOW } }));
  expect(g).toMatchObject({ label: 'Bloccato', color: '#f87171', floor: 1060, riskCap: 0 });
  expect(g.reasons).toEqual(['equity sotto il floor', 'perdita di sessione']);
  expect(guardianView(run()).riskCap).toBeNull();
  expect(guardianView(run({ guardian: { state: 'HACKED' } }))).toBeNull();
  expect(guardianView(run({ guardian: { state: '__proto__' } }))).toBeNull();
  expect(guardianView(run({ guardian: null }))).toBeNull();
});

test('the Storico tab stays lit on the pages reached from it, the Brain tab only on the main screen', () => {
  expect(isActive('/brain-unico', '/brain-unico')).toBe(true);
  expect(isActive('/brain-unico', '/brain-unico/rc1')).toBe(false);
  for (const p of ['/overview', '/brain-unico/rc1', '/compare']) expect(isActive('/overview', p)).toBe(true);
  expect(isActive('/overview', '/brain-unico')).toBe(false);
  expect(isActive('/classic', '/classic')).toBe(true);
});
