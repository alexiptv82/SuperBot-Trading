import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import BrainMemorySection from './BrainMemorySection';

const ok = {
  state: 'ok', run_id: 'r1',
  memory: { decisions: 3, valid_links: 2, coverage_pct: '66.7', chain_ok: true, missing: 1, invalid: 0,
    untraced_opens: 1, no_trade: 1 },
  theses: { mode: 'observe', enforce_active: false, opens_with_thesis: 3, distinct_theses: 1, reentries: 2,
    would_block: 1, rules: { reentry_limit: 1 } },
  learning: { valid_examples_collected: 2, distinct_days: 1, shadow_threshold: { examples: 300, days: 20 },
    promotion_review_threshold: { examples: 1000, days: 45 }, training_authorized: false, model_active: false },
  recent: [
    { ts_ms: 1700000000000, symbol: 'BTCUSDT', kind: 'OPEN', status: 'APPROVED', link: 'valid', reentry_index: 3, would_block: true },
    { ts_ms: 1700000000000, symbol: 'ETHUSDT', kind: 'NO_TRADE', status: 'REJECTED', link: 'missing' },
    { ts_ms: 1700000000000, symbol: 'SOLUSDT', kind: 'toString', status: '__proto__', link: '__proto__' },
  ],
};

test('memory, theses and learning are shown as observation, never as training', () => {
  const html = renderToStaticMarkup(<BrainMemorySection memory={ok} />);
  expect(html).toContain('Memoria decisionale');
  expect(html).toContain('66.7%');
  expect(html).toContain('snapshot mancante');
  expect(html).toContain('Solo osservazione');
  expect(html).toContain('oltre il 2° reingresso');
  expect(html).toContain('in osservazione: verrebbe bloccato');
  expect(html).toContain('Addestramento autorizzato');
  expect(html).not.toContain('Blocco attivo');
  expect(html).toMatch(/Addestramento autorizzato<\/span><span>No/);
  expect(html).toContain('non valida');                       // codice sconosciuto: mai mostrato com'è
  expect(html).not.toContain('__proto__');
  expect(html).not.toContain('<button');                      // sola lettura
  expect(html).not.toContain('function');
});

test('a broken chain is an alert', () => {
  const html = renderToStaticMarkup(<BrainMemorySection memory={{ ...ok, memory: { ...ok.memory, chain_ok: false } }} />);
  expect(html).toContain('role="alert"');
  expect(html).toContain('Catena del registro non integra');
});

test('not started and unavailable states', () => {
  expect(renderToStaticMarkup(<BrainMemorySection memory={{ state: 'not_started' }} />)).toContain('non ancora avviato');
  expect(renderToStaticMarkup(<BrainMemorySection memory={null} />)).toContain('Memoria non disponibile');
  expect(renderToStaticMarkup(<BrainMemorySection memory={{ state: 'unavailable' }} />)).toContain('Memoria non disponibile');
});

test('unknown rule codes are never shown as such', () => {
  const html = renderToStaticMarkup(<BrainMemorySection memory={{ ...ok, theses: { ...ok.theses, rules: { constructor: 2 } } }} />);
  expect(html).toContain('altra regola');
  expect(html).not.toContain('constructor');
});

test('progress never exceeds 100%', () => {
  const big = { ...ok, learning: { ...ok.learning, valid_examples_collected: 5000 } };
  expect(renderToStaticMarkup(<BrainMemorySection memory={big} />)).toContain('aria-valuenow="100"');
});

test('duplicate decisions per slot: counted, highlighted, and never a false zero', () => {
  const dup = renderToStaticMarkup(<BrainMemorySection memory={{ ...ok, memory: { ...ok.memory, duplicate_slot_decisions: 2 } }} />);
  expect(dup).toContain('Decisioni duplicate nello stesso slot');
  expect(dup).toMatch(/#fbbf24[^>]*>2</);
  const unknown = renderToStaticMarkup(<BrainMemorySection memory={ok} />);
  expect(unknown).toMatch(/Decisioni duplicate nello stesso slot.*non verificabile/);
});
