# Handoff tecnico — Capital Management V1 per Hawk e Bull
Data decisioni: 2026-10-23 · fase: **design approvato nei parametri, implementazione NON autorizzata, nessun deploy**.
Sorgente operativa verificata prima di questa nota: codice bot SHA `f87f2d63c5849b177dbd33ee43c5be05ca58c8ed`, `code_version=f87f2d6` su Hawk e Bull PAPER. NON assumere che il HEAD di `rule-pool` sia il codice effettivamente deployato. Futuro ramo di lavoro proposto `work/capital-management-v1` da SHA `f87f2d63...`; ramo NON ancora creato.

## Decisioni utente (definitive)
1. Stop giornaliero: **20%** sul budget operativo di inizio giornata, non su totale storico né salvadanaio. Oggi è **12% runtime** e deve restare tale fino ad autorizzazione successiva.
2. Vault per bot: ogni 00:00 **UTC** eccedenza sopra $1000 spostata al salvadanaio virtuale, max $1000 per nuove attività il giorno successivo. Se patrimonio operativo < $1000, nessun rientro automatico del vault; usare ciò che resta.
3. Posizioni aperte a mezzanotte restano aperte. Spostare solo liquidità effettivamente trasferibile/profitto realizzato; eccedenza non trasferibile in **accantonamento in attesa**, completare automaticamente alla chiusura se il capitale copre ancora il trasferimento. Non accreditare profitti non realizzati nel saldo protetto.
4. Trasferimento vault -> conto operativo **solo su comando manuale autenticato** dell'utente; idempotenza/doppio click, storico e conferma effettiva; in PAPER contatore, in eventuale live futuro nessun prelievo automatico su Bitget. Evitare che il trasferimento azzeri stop giornaliero.
5. Margin cap percentuale del budget operativo a inizio giornata: **Hawk 10%**, **Bull 25%**, slot invariati **Hawk 10 / Bull 6**. Protezione assoluta `kill_equity=$450` invariata. I tetti non obbligano ad aprire e si rivalutano ogni 00:00 UTC.
6. PAPER SEMPRE; nessun deploy senza nuovo OK esplicito; nessuna modifica al codice già distribuito finché l'utente non autorizza l'implementazione; lavoro su branch separato da rule-pool; preservare DB/brain e rollback.

## Quattro componenti
- `Capital Manager` (`backend/desk/capital_manager.py`): daily budget, daily reference equity, stop di rischio e accounting neutrale rispetto ai trasferimenti.
- `Vault Manager` (`backend/desk/vault_manager.py`): saldo vault, pending, rollover UTC unico per giorno, trasferimenti atomici e idempotenti, journal recuperabile dopo crash; non toccare posizioni aperte. Non superare saldo realizzato e liquidità trasferibile.
- `Position Sizer` (`backend/desk/position_sizer.py`): max_margin per posizione (10%/25%), validazione cassa/margini/slot, DCA e seconda gamba, fee e guardrail coerenti; NON aumentare leva.
- `Dashboard Capitali` (app su `main`: `backend/desk_view.py`, `backend/desk_api.py`, frontend Dashboard/Settings/api): saldi operativo/vault/pending/total, stop e %; trasferimento manuale con ID univoco e stato richiesto/eseguito/rifiutato.

## Punti scoperti dall'audit codice, da non saltare
- `engine.PaperAccount.equity = cash + margin_in_use + unrealized` e `roll_day` ridefinisce reference dal patrimonio corrente; riallineare con transfers neutrali e rollover idempotente.
- `cli.make_account` sovrascrive oggi i limits persistiti con `PORTFOLIO.limits`: nuovo day_budget/position_cap persistito deve essere applicato in modo coerente a runtime e dopo riavvio.
- Il ciclo di mercato può essere ogni 30 minuti; rollover logico a 00:00 UTC anche con bot in pausa e riavvii, con prezzi affidabili e congelamento ingressi durante riconciliazione.
- `engine.open` limita margin con `min(max_margin_trade,max_margin_total-margin_in_use,cash*0.95)`; `engine.add_dca` e `_fill_split` hanno guardie distinte. La percentuale complessiva per posizione deve essere testata su ingresso + split + DCA (comportamento dei DCA può cambiare rispetto a base).
- Bull attualmente impone minimo 150$ e forced 200$ con cap massimo 350$; Hawk minimo 50$, forced 60$ e cap 100$. Non forzare $150 quando nuovo cap 25% di $500=$125; saltare il trade.
- `SYSTEM_HAWK`, `SYSTEM_BULL` e generatore deterministico contengono cifre fisse; rendere coerenti i prompt con nuove percentuali senza altri cambi di strategia non autorizzati.
- `reset_portfolio` oggi ricrea conto da $1000 e usa `state.clear()`: nessuna futura funzione può cancellare il vault o il journal. Brain/history/lessons/learning_log intoccabili.
- App e bot sono su storie distinte (app=main, bot=rule-pool runtime SHA f87f2d6): preparare codici/revisioni in rami separati senza merge cross-history.

## Formula e sicurezza da implementare con test
- day_budget = riferimento operativo per il nuovo giorno, massimo $1000, dopo vault; margini max day_budget*0.10 Hawk o *0.25 Bull.
- Perdita giornaliera autorizzata = 0.20*day_budget, con P&L depurato dai movimenti contabili. Il lock di stop dura fino al nuovo giorno UTC; un prelievo manuale non lo resetta. `kill_equity=450` invariato.
- Invariante: operativa + vault = totale costante nei trasferimenti; pending non è denaro protetto.
- No profitto fittizio: attendere realizzazione e cassa disponibile; pending può ridursi/cancellarsi se il mercato gira contro. No forced close a mezzanotte, no ingresso oltre il budget.
- Journal immutabile con idempotency_key, committed snapshot e replay/rollback. Test crash durante operazione, ricostruzione, doppio trigger, vecchi stati, riconciliazione.
- Distinguere 3 nozioni: patrimonio operativo effettivo (posizioni aperte comprese), budget assegnato a nuovi ingressi (cap 1000), capitale reale trasferibile (cassa realizzata). Al rollover, quando pending >0, non dedurre dal patrimonio contabile denaro non trasferito e non aumentare il vault.
- Non trasformare deposito/prelievo in P&L o eliminazione stop, non confondere budget AI (Claude/DeepSeek) con gestione capitale.

## Decisioni progettuali aggiuntive consigliate, DA CONFERMARE nel pre-implementazione
A. Margine max 10%/25% come **tetto complessivo per posizione** includendo DCA e split, non solo ingresso iniziale (cambia il comportamento dei DCA).
B. Prelievo manuale durante il giorno aumenta cassa ma non il riferimento di margin sizing/stop fino a giorno UTC successivo; non sblocca stop.
C. Se posizioni aperte generano patrimonio temporaneamente >1000: nuovi ingressi comunque limitati al budget 1000 e alla cassa disponibile; profitto pending non è vault.

## Sequenza futura
1. Nuova sessione Work legge `SINCRONIZZAZIONE-WORK-CHAT.md`, questo file, STATO/diario. Verifica ramo/code_version corrente.
2. Dopo approvazione separata a **implementare**, creare `work/capital-management-v1` dalla baseline; progettare ledger e test offline, NON deploy.
3. Test su $1120 flat -> 120 vault; $900 -> 0; $1150 con non realizzato -> pending; closing +120 -> vault max120; closing loss -> pending 0; midnight duplicate; server restart; budget 900 => Hawk90/Bull225; DCA/split; guardrail; transfer manuale idempotente; lock stop e $450; shutdown & rollback; archivio run e AI memory.
4. PR/review tra Work, chat normale e Claude; confronto strategia base vs proposta, codice e test; nessun merge/deploy prima di OK specifico.
5. Solo dopo esplicito OK per deploy, backup verificato, un'unica istanza PAPER, rollout sorvegliato, nuova code_version runtime confermata per entrambi.

## Stato aggiornato
**Nessun ramo/commit di codice creato; nessun deploy autorizzato.** L'utente ora chiede coordinamento fra Work e chat normale. Questo handoff esiste soltanto sul ramo `diario`.


## Specifica dettagliata successiva — ChatGPT Work, 23/10
L'utente riconferma le cinque decisioni e autorizza la progettazione tecnica definitiva. Piano consegnato in [CAPITAL-MANAGEMENT-V1-SPECIFICA.md](CAPITAL-MANAGEMENT-V1-SPECIFICA.md): contabilità, rollover, pending, writer unico, persistenza/recovery, sizer, API/UI, migrazione, rollback e test previsti. A/B/C sono raccomandazioni da approvare esplicitamente; nessuna implementazione, nuovo ramo di codice o deploy in questo checkpoint.
