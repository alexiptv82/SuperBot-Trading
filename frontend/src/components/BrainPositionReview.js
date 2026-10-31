import React from 'react';

const labels={HOLD:'Mantieni',SUGGEST_CLOSE:'Proposta di chiusura',
  SUGGEST_TIGHTEN:'Proposta di stop più stretto',closed:'Chiusura PAPER eseguita',
  stop_tightened:'Stop aggiornato'};

export default function BrainPositionReview({review,stale}) {
  const known=review&&['off','paper','unknown'].includes(review.mode);
  const last=review?.status==='recorded'?review.last:null;
  return <section aria-label="Revisione AI posizioni" style={{border:'1px solid #334155',borderRadius:14,padding:14,marginBottom:12}}>
    <strong>Gestione AI delle posizioni</strong>
    <p>{stale?'Stato storico · aggiornamento necessario':!known||review.mode==='unknown'
      ?'Stato automatico non disponibile':review.mode==='paper'
      ?'Gestione automatica PAPER abilitata':'Gestione automatica spenta'}</p>
    {!last?<p>Nessuna revisione leggibile disponibile.</p>:<>
      <p>Ultima revisione: {new Date(last.ts_ms).toLocaleString('it-IT')}</p>
      <p>{last.reviewer_checked?'Secondo parere Claude ricevuto':'Secondo parere Claude non registrato'}</p>
      {(last.proposals||[]).map((r,i)=><div key={'p'+i}>{r.symbol}: {labels[r.action]||'Proposta non disponibile'}{r.reason&&<p>{r.reason}</p>}</div>)}
      {(last.executed||[]).length===0?<p>Nessuna azione eseguita in questa revisione.</p>:
        last.executed.map((r,i)=><p key={'e'+i}>{r.symbol}: {labels[r.action]||'Esito non disponibile'}</p>)}
    </>}
  </section>;
}
