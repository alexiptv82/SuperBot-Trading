import React from 'react';

const labels={HOLD:'Mantieni',SUGGEST_CLOSE:'Proposta di chiusura',
  SUGGEST_REDUCE:'Proposta di riduzione',reduced:'Riduzione PAPER eseguita',
  SUGGEST_TIGHTEN:'Proposta di stop più stretto',closed:'Chiusura PAPER eseguita',
  stop_tightened:'Stop aggiornato'};

const failures={balance:'Credito esaurito',auth:'Accesso API non autorizzato',
  rate:'Limite richieste raggiunto',network:'Rete o risposta non disponibile',
  http:'Errore del provider',truncated:'Risposta incompleta',
  prompt_limit:'Contesto oltre il limite',invalid_response:'Risposta non valida',
  unavailable:'Provider non disponibile'};

export default function BrainPositionReview({review,attempt,stale}) {
  const known=review&&['off','paper','unknown'].includes(review.mode);
  const last=review?.status==='recorded'?review.last:null;
  return <section aria-label="Revisione AI posizioni" style={{border:'1px solid #334155',borderRadius:14,padding:14,marginBottom:12}}>
    <strong>Gestione AI delle posizioni</strong>
    {attempt?.failure_code&&<p role="status">
      {stale?'Ultimo errore registrato':'Errore nell’ultima analisi'}: {attempt.provider==='deepseek'?'DeepSeek':attempt.provider==='claude'?'Claude':'AI'}
      {' · '}{failures[attempt.failure_code]||'Analisi non disponibile'}
      {' · '}{new Date(attempt.ts_ms).toLocaleString('it-IT')}. Nessuna azione da questa risposta.
    </p>}
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
