# V3 RC67 — Contabilità Brain e osservazioni dei classici (7 novembre 2026)

**STATO: DRAFT / PAPER / NESSUN DEPLOY.** Questa PR non avvia motori, non autorizza chiusure, non modifica strategie e non abilita operazioni LIVE.

## Regola di verità dei numeri

- **Fonte capitale Brain:** file di configurazione originale e specifico della run. Per la ripartenza proposta è `backend/v3/runner/runner_config_brain2000_paper.json` (capitale iniziale 2.000 USDT). La dashboard legge il path **esplicito** `V3_RUNNER_CONFIG_PATH` installato dal gestore del deployment. Mai scegliere automaticamente `runner_config.json`: il nome o valore possono appartenere a un'altra prova.
- **Fonte profitti:** eventi `paper_close` del solo `V3_RUN_ID` su SQLite Journal, validati mediante `extract_outcomes` (contabilità netto-commissioni). Se una chiusura è incoerente o non validabile, nessuna metrica derivata viene dichiarata attendibile.
- **Saldo PAPER contabile** = capitale iniziale della run + P&L netto dei trade chiusi.
- **Equity totale**: disponibile come saldo contabile soltanto se non esistono posizioni aperte; con posizioni aperte serve un mark aggiornato e attestato con data/fonte. Senza tale prova, viene mostrato `—` e non si sostituisce il mark con prezzo di ingresso o prezzo vecchio.
- **Profitto di oggi** = P&L *realizzato* dei soli trade chiusi tra `00:00:00 UTC` del giorno corrente e `now`. Non comprende P&L latente, altri portafogli o run precedenti.
- **Run non pronta:** senza journal, config, run_id valido, evento reale della run, oppure con validazioni fallite, mostrare `—` (nessuna congettura su saldi iniziali effettivamente depositati).

## Osservazione Falco/Toro

La dashboard inserisce sotto le tre card una sezione `Brain · osservazioni Falco e Toro` che mostra **solo** stato, aperte, profitto giornaliero e ultimo evento dei classici. È uno specchio read-only con campo `peer_observations_mode=display_only_not_ai_input`.

Questa PR **NON** inietta i dati nell'analista, nel reviewer o in `BrainEngine.step`: non si può chiamare apprendimento automatico. La prossima integrazione richiede:
1. Snapshot tipizzato read-only dello stesso timestamp per entrambi i classici, con validazione freshness e `run_id`.
2. Collegamento all'analista con citazione della fonte e registrazione nel journal del contesto realmente consumato, incluso il caso `NO_DATA` e `NO_TRADE`.
3. Divieto assoluto di trasferire margini, capitali, posizioni o ordini tra Brain/Falco/Toro; nessun override dei risk gate o delle decisioni manuali.
4. Test offline con peer assente, stale, malformato, segnali contraddittori e ritardi; preferire `NO_DATA` a indicazioni fabricate.

## Gate per l'app mobile e la ripartenza PAPER

Controllare ambiente `V3_RUNNER_CONFIG_PATH`, `V3_JOURNAL_PATH`, `V3_RUN_ID` e i mount delle tre viste **senza** modificare lo storico. Eseguire snapshot locale verificato + restore isolato, sessioni, permessi e smoke test su telefono; PR #65/66 e release #62 sono ancora in bozza. Backup cifrato esterno differibile soltanto per l'esperimento PAPER con rischio residuo documentato.

**Nessun merge/deploy/avvio/reset/chiusura trade è compreso in questo documento.**
