import { brainExitReason } from './Overview';
import { closeResultMessages } from '../components/OverviewCloseControls';

jest.mock('../api', () => ({ get: jest.fn() }));

test('il motivo «tempo scaduto» non porta un numero di ore scritto nel codice (invecchierebbe col limite)', () => {
  expect(brainExitReason('timeout')).toBe('tempo scaduto');
  expect(brainExitReason('timeout')).not.toMatch(/\d/);
});

test('esiti di chiusura: il simbolo al posto dell’identificativo tecnico', () => {
  const names = { aaa111: 'BTCUSDT', bbb222: 'ETHUSDT' };
  const nameOf = id => names[id] || 'Posizione';
  const msg = closeResultMessages({ status: 'done', closed: ['aaa111'],
    failed: [['bbb222', 'price_unavailable'], ['ccc333', 'position_already_closed']] }, nameOf).join(' | ');
  expect(msg).toContain('BTCUSDT: posizione chiusa.');
  expect(msg).toContain('ETHUSDT: prezzo non disponibile, riprova.');
  expect(msg).toContain('Posizione: posizione già chiusa.');
  expect(msg).not.toContain('aaa111');
  expect(msg).not.toContain('bbb222');
  expect(msg).not.toContain('ccc333');
});

test('senza funzione di traduzione il comportamento resta quello consegnato', () => {
  expect(closeResultMessages({ status: 'done', closed: ['p-001'], failed: [] })).toEqual(['p-001: posizione chiusa.']);
});
