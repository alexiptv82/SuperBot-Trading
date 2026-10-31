import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import BrainPositionReview from './BrainPositionReview';

const review={mode:'paper',status:'recorded',last:{ts_ms:1800000000000,
  reviewer_checked:true,proposals:[{symbol:'BTC',action:'SUGGEST_CLOSE',reason:'<script>test</script>'}],executed:[]}};
test('proposal and second opinion never imply execution',()=>{
  const html=renderToStaticMarkup(<BrainPositionReview review={review}/>);
  expect(html).toContain('Proposta di chiusura');
  expect(html).toContain('Nessuna azione eseguita');
  expect(html).toContain('&lt;script&gt;');
  expect(html).not.toContain('Chiusura PAPER eseguita');
});
test('stale snapshot cannot claim currently enabled automation',()=>{
  const html=renderToStaticMarkup(<BrainPositionReview review={review} stale/>);
  expect(html).toContain('Stato storico');
  expect(html).not.toContain('PAPER abilitata');
});
test('missing telemetry is unknown, not disabled or enabled',()=>{
  const html=renderToStaticMarkup(<BrainPositionReview/>);
  expect(html).toContain('Stato automatico non disponibile');
});
