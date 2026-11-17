import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import NavBar from './NavBar';

jest.mock('../AppContext', () => ({
  useAppMode: () => ({ mode: 'paper', toggleMode: jest.fn() }),
}));

const renderNav = () => renderToStaticMarkup(
  <MemoryRouter initialEntries={['/arena']}>
    <NavBar onLogout={() => {}} />
  </MemoryRouter>
);

afterEach(() => {
  delete process.env.REACT_APP_BRAIN_ARENA_PREVIEW;
});

test('Arena-first PAPER mode retains a visible Falco/Toro archive navigation button', () => {
  process.env.REACT_APP_BRAIN_ARENA_PREVIEW = '1';
  const html = renderNav();
  expect(html).toContain('AI Arena');
  expect(html).toContain('Falco / Toro');
  expect(html).toContain('Agenti');
  expect(html).toContain('Impostazioni');
  expect(html).not.toContain('Chiudi tutte');
});

test('without opt-in, legacy navigation stays unchanged', () => {
  delete process.env.REACT_APP_BRAIN_ARENA_PREVIEW;
  const html = renderNav();
  expect(html).toContain('V3 · 3 bot');
  expect(html).toContain('Classici');
  expect(html).toContain('Trade');
  expect(html).toContain('Performance');
});
