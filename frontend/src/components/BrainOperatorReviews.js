import React,{useCallback,useEffect,useRef,useState} from 'react';

export default function BrainOperatorReviews({basePath='/api/brain/operator',owner='Brain',accountScoped=false}){
  const [groups,setGroups]=useState([]);
  const [tickets,setTickets]=useState({});
  const [message,setMessage]=useState('');
  const ticketsRef=useRef({});
  const accountRef=useRef(null);
  const active=useRef(false);
  const controllers=useRef(new Set());
  const request=useCallback(async(url,options={})=>{
    const controller=new AbortController();
    controllers.current.add(controller);
    const timer=setTimeout(()=>controller.abort(),10000);
    try{
      const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options,signal:controller.signal});
      if(!response.ok)throw new Error('request_failed');
      return await response.json();
    }finally{
      clearTimeout(timer);
      controllers.current.delete(controller);
    }
  },[]);
  useEffect(()=>{
    let live=true,timer;
    active.current=true;
    const poll=async()=>{
      try{
        const data=await request(basePath+'/reviews');
        accountRef.current=data.status==='available'?data.account_id:null;
        if(live)setGroups(data.status==='available'&&Array.isArray(data.groups)?data.groups:[]);
        for(const [group,ticket] of Object.entries(ticketsRef.current)){
          if(!live)break;
          if(ticket.terminal)continue;
          const {status}=await request(basePath+'/result/'+ticket.id);
          if(['confirmed','expired','needs_reconciliation','rejected_account'].includes(status))
            ticketsRef.current[group]={...ticket,terminal:true};
          if(live&&status==='confirmed')setMessage('Conferma registrata '+(owner==='Brain'?'dal Brain':'da '+owner)+'. Esempio osservativo, non una regola.');
          else if(live&&['expired','needs_reconciliation','processing','rejected_account'].includes(status))
            setMessage('Esito '+status+': non ripetere la richiesta; verifica necessaria.');
        }
      }catch(e){if(live)setMessage('Conferme temporaneamente non disponibili. Le richieste inviate non vengono ripetute.');}
      finally{if(live)timer=setTimeout(poll,5000);}
    };
    poll();
    return()=>{
      live=false;active.current=false;clearTimeout(timer);
      controllers.current.forEach(controller=>controller.abort());
    };
    // This poll reads current tickets through the ref, without restarting requests.
  },[request,basePath,owner]);
  const send=async(group,choice)=>{
    if(ticketsRef.current[group])return;
    if(accountScoped&&!accountRef.current)return;
    const id=crypto.randomUUID().replace(/-/g,'');
    ticketsRef.current[group]={id,choice};
    setTickets({...ticketsRef.current});
    setMessage('Richiesta in invio: non ancora confermata da '+owner+'.');
    try{
      await request(basePath+'/confirm',{method:'POST',
        headers:{'Content-Type':'application/json','X-Brain-Operator':'1'},
        body:JSON.stringify({request_id:id,group_id:group,choice,...(accountScoped?{account_id:accountRef.current}:{})})});
      if(active.current)setMessage('Richiesta accodata. Attendo la conferma di '+owner+'.');
    }catch(e){if(active.current)setMessage('Esito invio incerto: attendo la verifica, non ripetere la richiesta.');}
  };
  return <section aria-label="Insegnamenti manuali" style={{marginBottom:14,padding:14,border:'1px solid #334155',borderRadius:12}}>
    <h3>Le tue chiusure manuali · {owner}</h3>
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
