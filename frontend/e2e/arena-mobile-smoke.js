// Prova mobile locale: build reale + API PAPER simulate (nessun server, nessun ordine).
const { chromium, devices } = require('playwright');
const fs = require('fs'), path = require('path');
// Build con: CI=true REACT_APP_BACKEND_URL= REACT_APP_BRAIN_ARENA_SHADOW_API=1 REACT_APP_ARENA_MANUAL_CLOSE=1
// REACT_APP_BRAIN_ARENA_PREVIEW=1 BUILD_PATH=<dir> npx react-scripts build; poi ARENA_BUILD=<dir> [DEV='Galaxy S24'] node arena-mobile-smoke.js
const BUILD = path.resolve(process.env.ARENA_BUILD || path.join(__dirname, '../build'));
const OUT = process.env.ARENA_SHOTS || __dirname;
const now = Date.now(), T0 = now - 3 * 86400000;
const pos = (id, sym, side, entry, stop, pnl) => ({ position_id: id, symbol: sym, side, leverage: 20, entry, stop,
  margin: '200', take_profit: null, price: entry, price_source: 'ticker', unrealized_pnl: pnl, roi_pct: '1.2' });
const wallet = (id, pnl, open, closed) => ({ portfolio_id: id, mode: 'paper', state: 'running', initial_capital: 2000,
  source: 'arena_independent_journal_v1', run_id: `brain-${id}-paper20261118`, equity: null, settled_equity: String(2000 + pnl),
  equity_basis: 'open_unmarked', realized_pnl: String(pnl), unrealized_pnl: null, day_pnl: '0', margin_in_use: '200',
  total_closed: closed, win_rate: '50', open_count: open.length, open_positions: open, closed_trades: [],
  updated_ms: now, trial_start_ms: T0, trial_comparable: true, decision_count: 120, no_trade_count: 97,
  manual_close_count: 0, verified_outcome_count: closed, learning_status: 'JOURNAL_EVIDENCE_ONLY_NOT_MODEL_TRAINING' });
const ARENA = { portfolios: {
  deepseek: wallet('deepseek', 14.2, [pos('ds-1', 'XAUUSDT', 1, '4012.5', '3980.4', '6.10')], 4),
  qwen: wallet('qwen', -8.4, [pos('qw-1', 'ETHUSDT', -1, '1778.9', '1793.1', '-2.30'), pos('qw-2', 'SOLUSDT', 1, '72.34', '71.76', '1.05')], 3),
  minimax: wallet('minimax', 3.1, [], 2) } };
const posted = [];
let closeState = 'pending';
async function routes(page) {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url()), p = url.pathname, m = route.request().method();
    const json = (b, s = 200) => route.fulfill({ status: s, contentType: 'application/json', body: JSON.stringify(b) });
    if (p.startsWith('/api/')) {
      if (m === 'POST') posted.push({ p, body: route.request().postDataJSON() });
      if (p === '/api/v3/overview') return json({ generated_at_ms: now, portfolios: [{ id: 'brain', state: 'running', realized_pnl: '0' }] });
      if (p === '/api/v3/brain/status') return json({ state: 'running' });
      if (p.startsWith('/api/v3/brain/trades')) return json({ open_positions: [], closed_trades: [] });
      if (p === '/api/v3/arena') return json(ARENA);
      const ann = p.match(/^\/api\/v3\/arena\/(deepseek|qwen|minimax)\/annotations$/);
      if (ann) return json({ ok: true, provider: ann[1], manual_close_ready: true, annotations: [] });
      if (/^\/api\/v3\/arena\/qwen\/close$/.test(p) && m === 'POST') return json({ ok: true, status: 'pending', terminal: false });
      if (/^\/api\/v3\/arena\/qwen\/close\/[A-Za-z0-9-]+$/.test(p)) {
        return json(closeState === 'pending' ? { ok: true, status: 'pending', terminal: false }
          : { ok: true, status: 'closed', terminal: true, close_event_id: 'e1', exit_reason: 'manual' });
      }
      if (/\/annotation$/.test(p)) return json({ ok: true, annotation: { reason: 'trend_change', note: null } });
      return json({ ok: false }, 404);
    }
    let file = path.join(BUILD, p);
    if (!file.startsWith(BUILD) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(BUILD, 'index.html');
    const type = file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.html') ? 'text/html' : undefined;
    return route.fulfill({ status: 200, body: fs.readFileSync(file), contentType: type });
  });
}
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices[process.env.DEV || 'Galaxy S9+'] });
  await ctx.addInitScript(() => sessionStorage.setItem('sb_token', 'test-session'));
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await routes(page);
  await page.goto('http://superbot.test/arena');
  await page.getByText('AI Arena').first().waitFor();
  const shot = n => page.screenshot({ path: path.join(OUT, n), fullPage: true });
  const vw = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  await shot('01-panoramica.png');
  await page.getByRole('button', { name: /Qwen/ }).click();
  await page.getByRole('button', { name: 'Posizioni aperte' }).click();
  await shot('02-qwen-posizioni.png');
  await page.getByRole('button', { name: 'Chiudi ETHUSDT' }).click();
  await shot('03-conferma.png');
  await page.getByRole('button', { name: 'Conferma chiusura' }).click();
  await page.getByText('in attesa della conferma').waitFor();
  closeState = 'closed';
  await page.getByText('Chiusura PAPER confermata dal journal').waitFor({ timeout: 10000 });
  await page.getByLabel('Cambio di tendenza').check();
  await shot('04-motivo.png');
  await page.getByRole('button', { name: 'Registra motivazione' }).click();
  await page.getByText('Motivazione registrata').waitFor();
  await page.getByRole('button', { name: 'Memoria' }).click();
  await shot('05-memoria.png');
  const vw2 = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  console.log(JSON.stringify({ device: process.env.DEV || 'Galaxy S9+', viewport: page.viewportSize(), widths: [vw, vw2], errors,
    posted: posted.map(x => ({ path: x.p.replace(/arena-[0-9a-f]+/, 'arena-<id>'), body_keys: Object.keys(x.body || {}) })) }, null, 1));
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
