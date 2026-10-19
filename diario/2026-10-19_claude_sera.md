# 19 ottobre 2026, sera — Claude (seguito di 2026-10-19_claude.md)

## Decisioni dell'utente (17:23–17:42 ora di Roma)
- Percorso "ombra" su Hawk E Bull, con nuove run PAPER da $1.000 su entrambi. Nessun passaggio ad "attivo" senza un nuovo OK.
- Filosofia: +25/30% non è un'uscita obbligatoria ma il punto in cui si valuta il mercato (tieni / chiudi / parziale). Tendenza conservativa. Problema osservato: posizioni a +25/30% che dopo ore tornano in perdita.
- Parziali su Hawk (oggi `partial_fraction = 0` nella policy di ricerca): NON deciso. Solo variante di confronto nel replay.
- 17:42: l'utente conferma l'architettura dell'ombra come **processo separato** (vedi sotto). Nessun deploy autorizzato finora.

## Architettura confermata: ombra come processo separato
- Nuovo contenitore che legge in sola lettura `state_v2.json` e `heartbeat.json` dopo la fine di ogni ciclo e scrive il registro in una cartella propria. I bot non cambiano: niente redeploy dei bot, e "ombra on/off" non può alterare conto o decisioni.
- `save_state` scrive in modo atomico (`.tmp` + `os.replace`): lettura sicura. Da verificare: mount in sola lettura della cartella dati.
- L'installazione del contenitore richiede OK esplicito dell'utente, backup fresco verificato, SHA fissato.

## Nuove run: nessun redeploy
- Una nuova run nasce con `reset_portfolio.flag`: bot in pausa e senza posizioni aperte; archivia la run, riparte a $1.000, resta in pausa finché l'utente preme Avvia; il cervello si conserva.
- ATTENZIONE: il reset sposta in archivio e rimuove `trade_history.jsonl`. L'estrazione dei dati di Hawk run 3 / Bull run 2 va fatta PRIMA del reset (dal backup verificato) o dall'archivio.
- Le nuove run partono solo quando l'ombra è pronta, così osserva la run intera.

## Revisione del contratto snapshot di ChatGPT (letto contro `engine.py` di rule-pool 0b9a2ad)
- Gamba aggregata (entry medio, qty residua, `fee_open` residua) esatta per il lordo.
- Margine di riferimento = `pos.margin + Σ dca_levels.margin` (non `total_margin`, che scende con i parziali).
- `realized_net` = Σ `net` dei record `closed` con stesso `id` e `partial: true`; chiave (`id`, `close_ms`).
- Funding del motore: solo long, 1 bp/8h su qty×entry, calcolato alla chiusura dalle ore dall'apertura (DCA/seconda gamba sovrastimati, short a zero). Lo snapshot lo replica e lo dichiara "modello del motore", non funding reale. Non corretto: decide l'utente.
- Costi dai limiti del conto (fee 6 bp, slippage 2 bp, spread 0); il vecchio `profit_manager_shadow.py` usa 3 bp di slippage, incoerente.
- Picco anche da `px_hi`/`px_lo` (limite superiore non eseguibile); ordine ambiguo DCA+parziale nello stesso ciclo: `ambiguous_order`, PM congelato.
- Moduli `profit_manager_*` già presenti su rule-pool (mai deployati): da sostituire, ritirare o tenere come riferimento PM-A; decide ChatGPT e dichiara.

## Revisione estrattore 67735f3 (ChatGPT, work/profit-manager)
Sicuro come copiatore (i 9 test non sono stati eseguiti da Claude). Richieste: leggere il `MANIFEST.json` del backup (confine di ciclo verificato) invece di un manifesto fatto a mano; passo "schema" con sole chiavi e conteggi; incrocio `run_no` con `run_started_ms`; posizioni aperte o senza 2h di copertura = censurate. ChatGPT ha accolto i quattro punti.

## Stato dei bot (fotografia delle 11:02 locali, NON aggiornata)
Online, paper, cicli ogni 30 min, soglia di confidenza non superata (`CONF_LOW`); nessun blocco. Hawk 738,89 $, Bull 861,64 $. Nuovo controllo (`sg-bots-check`) non eseguito: l'integrazione GitHub di Claude dà 403 in scrittura su rule-pool; va lanciato da ChatGPT.

## Aperto
Sostituzione/ritiro dei moduli `profit_manager_*`; mount in sola lettura; replay storico parziale (workflow server + candele pubbliche Bitget); parziali su Hawk; nuovo `sg-bots-check`; A–D non corretti.
