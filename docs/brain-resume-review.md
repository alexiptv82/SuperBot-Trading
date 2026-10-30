# Brain: ripresa offline del 30 ottobre 2026

Base di ripristino: 3e73bbff44946df7dba027e27086009229ebb351.
Autorizzazione utente: integrare cio' che e' utile dei report e riprendere lo
sviluppo sospeso. Nessun merge/deploy, VPS, reset, chiamata AI a pagamento.

## Evidenza che cambia il piano
Il ramo Claude work/regime-lab-claude-20261030, commit
3fc4fa9c790c5266fa70aa546e8216ad981b7bd4, dichiara nessuna configurazione idonea
fra 16. La fase economica NON e' stata eseguita. Il diario del 30 ottobre
conferma lo stop del laboratorio. Non importiamo il lettore nel prompt, negli
ordini o nello scoring. Il presunto vantaggio permanente SHORT non e' dimostrato.
Nessun bonus +15, penalita' -45%, filtro CVD inventato o veto LONG introdotto.

## Implementato
- BrainAccount: un unico SQLite PAPER con identita' propria, usando PaperWallet,
  BrainPair e protezioni esistenti. WalletSpec completo obbligatorio; nessun
  default finanziario unico e nessuna fusione automatica dei due conti.
  La fixture di test ha 2000 USDT/1600 margine, ma NON e' un mandato di esercizio.
- Validazione preventiva di mandato; restart richiede stesso fingerprint;
  doppio writer e re-inizializzazione respinti. Backup SQLite gia' esistente riusato.
- PaperSupervisor.step: tick protettivo prima di ogni controllo AI; analisi su
  worker separato senza SQLite. DeepSeek/Claude restano callback esplicite, nessun
  nuovo trasporto. Il chiamante deve invocare step con dati aggiornati a cadenza
  regolare H24: qui non si installa/avvia alcun daemon o secondo Brain.
- Una analisi in volo; deadline verificata anche prima del revisore; una risposta
  scaduta non apre. Il trasporto deve avere timeout finiti: un thread Python non
  puo' interrompere forzatamente una chiamata bloccata. Nessun retry parallelo.
- Prenotazione budget intera analisi in micro-USD, salvata PRIMA di chiamare;
  persistente dopo crash, nessun rimborso di spese ignote. La somma e' un limite
  prudenziale, NON spesa API misurata. Il tetto prenotato deve coprire entrambi i
  provider a prezzi/token verificati prima del collegamento reale.
- Diagnostica LONG/SHORT dello scanner attuale, senza cambiarne i risultati:
  dati mancanti, setup assente, esclusione top-K, selezione. Registro al massimo
  una volta al minuto, 200 righe massime per evento. Le fasi AI/rischio continuano
  nei journal ai_context_processed/ai_plan_rejected gia' presenti.
- Snapshot unico schema v2 con capitale iniziale del mandato reale, scrittura
  atomica riusata. NON compatibile con la PWA dual v1: quel lettore lo rifiuta
  esplicitamente, evitando due falsi portafogli. Adattamento PWA prima del rilascio.
- Esperimento separato research/long_reclaim: recupero di supporto/resistenza con
  volume e conferma, speculare LONG/SHORT. Solo osservazioni, non collegato a bot
  o prompt. Preregistrazione e test causali; nessun risultato storico economico.

## Verifica e limiti
Suite precedente e nuovi test sintetici: conto/restart/backup, mandato, blocco
secondo writer, stop durante AI lenta, scadenza, budget dopo restart/errori,
prenotazione e ingresso con callback finta, diagnostica invariata/causale,
replica speculare del reclaim. Nessuna prova di redditivita' o apprendimento.

Restano requisiti di rilascio concreti: mandato unico definitivo (nessun aumento
rischio implicito), adattamento PWA v2, collegamento feed/trasporti con prezzi,
timeout e token massimi verificati, migrazione con backup e riconciliazione dei
dati attivi se richiesta, ed esplicito OK di deploy. Il Brain attivo resta quello
precedente. Non presentare questa consegna come sistema H24 gia' distribuito.
Ripristino: usare la base o nuovo commit revert; mai force/reset dei dati.
