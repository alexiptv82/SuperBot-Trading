import React,{useEffect,useState} from 'react';

export default function BrainOperatorReviews(){
  const [groups,setGroups]=useState([]);
  const [tickets,setTickets]=useState({});
  const [message,setMessage]=useState('');
  useEffect(()=>{
    let live=true;
    const poll=async()=>{
      try{
        const r=await fetch('/api/brain/operator/reviews',{credentials:'same-origin',cache:'no-store'});
        if(!r.ok)throw new Error();
        const data=await r.json();
        if(live)setGroups(data.status==='available'&&Array.isArray(data.groups)?data.groups:[]);
        for(const [group,ticket] of Object.entries(tickets)){
          const answer=await fetch('/api/brain/operator/result/'+ticket.id,{credentials:'same-origin',cache:'no-store'});
          if(!answer.ok)continue;
          const status=(await answer.json()).status;
          if(live&&status==='confirmed')setMessage('Conferma registrata dal Brain. Esempio osservativo, non una regola.');
          else if(live&&['expired','needs_reconciliation','processing'].includes(status))
            setMessage('Esito '+status+': non ripetere la richiesta; verifica necessaria.');
        }
      }catch(e){if(live)setMessage('Conferme temporaneamente non disponibili.');}
    };
    poll();const timer=setInterval(poll,5000);
    return()=>{live=false;clearInterval(timer);};
  },[tickets]);
  const send=async(group,choice)=>{
    const id=crypto.randomUUID().replace(/-/g,'');
    setTickets(old=>({...old,[group]:{id,choice}}));
    setMessage('Richiesta in invio: non ancora confermata dal Brain.');
    try{
      const r=await fetch('/api/brain/operator/confirm',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-Brain-Operator':'1'},
        body:JSON.stringify({request_id:id,group_id:group,choice})});
      if(!r.ok)throw new Error();
      setMessage('Richiesta accodata. Attendo la conferma del Brain.');
    }catch(e){setMessage('Esito invio incerto: attendo la verifica, non ripetere la richiesta.');}
  };
  return <section aria-label="Insegnamenti manuali" style={{marginBottom:14,padding:14,border:'1px solid #334155',borderRadius:12}}>
    <h3>Le tue chiusure manuali</h3>
    <p>Vuoi conservare queste chiusure come esempi delle tue preferenze? Non diventano regole automatiche.</p>
    {message&&<p role="status">{message}</p>}
    {groups.map(g=><div key={g.group_id} style={{marginBottom:10}}>
      <strong>{Array.isArray(g.symbols)?g.symbols.join(', '):''}</strong>
      <p>{g.count} chiusure · netto PAPER {typeof g.net_usd==='number'?g.net_usd.toFixed(2):'—'} USDT</p>
      <button disabled={!!tickets[g.group_id]} onClick={()=>send(g.group_id,'yes')}>Conserva come esempio</button>{' '}
      <button disabled={!!tickets[g.group_id]} onClick={()=>send(g.group_id,'no')}>Non usare come esempio</button>
    </div>)}
    {!groups.length&&<p>Nessuna conferma disponibile.</p>}
  </section>;
}
