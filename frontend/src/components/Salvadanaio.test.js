import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import Salvadanaio from './Salvadanaio';

test('unavailable capability does not show a made-up zero balance', () => {
  const html = renderToStaticMarkup(<Salvadanaio />);
  expect(html).toContain('Salvadanaio');
  expect(html).toContain('non ancora attivo');
  expect(html).not.toContain('$0,00');
});

test('shows saved balance, daily net deposits and pending separately', () => {
  const html = renderToStaticMarkup(<Salvadanaio data={{available:true,ready:true,bot_online:true,balance:'100',pending:'20',deposited_today:'70',days:[{utc_day:'2026-10-27',amount:'70'}],day_count:1}} />);
  expect(html).toContain('$100,00');
  expect(html).toContain('$70,00');
  expect(html).toContain('2026-10-27');
  expect(html).toContain('Non incluso nel saldo');
  expect(html).toContain('PAPER');
});

test('warns about an offline bot and accounting still pending', () => {
  const html = renderToStaticMarkup(<Salvadanaio data={{available:true,ready:false,bot_online:false,balance:'0',pending:'0',deposited_today:'0',days:[]}} />);
  expect(html).toContain('ultimo saldo salvato');
  expect(html).toContain('in attesa di verifica');
});
