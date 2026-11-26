# Checkpoint verificabile SuperBot-Trading — 26/11/2026 15:50 Europe/Rome

## Esito, fonti e limiti

Checkpoint append-only di ripresa di `alexiptv82/SuperBot-Trading`, esclusivamente PAPER. Fonti consultate:

1. GitHub, ramo `diario`: `STATO.md`, checkpoint delle 13:43, ultimi commit visibili e RC84 PR #80;
2. `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, Library `libfile_754adf32b63881919d64ef3bc26b222a`, versione 155 prima di questa scrittura;
3. conversazione recente effettivamente accessibile sul Brain originale dopo le 13:43.

Questa esecuzione non ha interrogato la VPS né eseguito comandi, test, chiamate AI a pagamento o azioni operative. Le informazioni operative più recenti restano prove puntuali precedenti. Nessuna chat persa è stata ricostruita e nessun segreto o dettaglio di accesso è stato pubblicato.

## Novità verificata: pausa controllata raccomandata, non autorizzata

- L'utente ha chiesto se attendere o intervenire, evidenziando il rischio di consumare credito AI mentre il Brain continua a produrre chiamate senza aprire trade.
- La risposta ha raccomandato, dopo una verifica preventiva del limite giornaliero e degli scarti successivi alla proposta V3, una pausa controllata delle nuove aperture del Brain originale per evitare ulteriori costi inutili.
- La pausa proposta deve conservare uscite e chiusure delle eventuali posizioni; non prevede aumento del budget, abbassamento della confidenza, indebolimento dei filtri o forzatura di trade.
- Non risultano autorizzazione dell'utente, esecuzione del comando di pausa, stato del runner dopo la raccomandazione, approvazione della V3 `f9ae6e8bf8`, cambio budget o altra modifica attivata.
- Stato dimostrabile invariato: V2 era ancora attiva alle 13:00; V3 soltanto generata e in attesa di approvazione. Non assumere che il Brain sia stato fermato.

## Obiettivi, decisioni e roadmap

- Tre portafogli PAPER distinti e storici preservati: Falco, Toro e Brain. `NO_TRADE` e slot vuoti restano esiti validi.
- Sviluppo strategico trasferito su Evolution X PAPER; Brain originale invariato salvo manutenzione/sicurezza e possibile pausa controllata soltanto dopo consenso.
- Obiettivi Evolution X: ridurre i costi AI e aumentare opportunità valide con portafoglio vuoto, senza diventare più aggressivo; maggiore prudenza con 3–4 posizioni o dopo profitto.
- Smart AI Router, Opportunity Discovery, Adaptive Selectivity e AI Credit Guardian appartengono alla roadmap Evolution X isolata. I progressi offline di Evolution X non costituiscono modifiche al Brain originale.
- Nessuna nuova spesa API, reset, merge, deploy o modifica strategica del Brain senza consenso separato.

## Tre portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato | Implementato/verificato | Stato più recente dimostrabile |
|---|---|---|---|
| Falco | classico distinto, strategia e storico preservati | Falco classico preservato; Falco Evoluto archiviato/disabilitato con Brain V2 | nessun nuovo controllo live |
| Toro | classico distinto e storico preservato | storico preservato; `semantic_not_certified` | non è il bot corrente della dashboard Brain |
| Brain | PAPER 2.000 USDT, AI selettiva, memoria e rischio preservati | `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run 539 eventi e tre sessioni collegate | 13:00: V2 attiva, V3 proposta non approvata; pausa successiva soltanto raccomandata, non provata |

## Configurazione e rischio: desiderato contro implementato

- Profilo B precedente: tetto quattro posizioni e rischio aperto comprensivo dei costi; integrazione `c11e6d7d…`, piano `302e94d2…`.
- Issue #124: correzione `0f71d0be…`, integrazione `5f110379…`, chiusa il 22/11; il latch blocca nuove aperture senza impedire le uscite.
- Brain V2 documentato: ciclo 30 minuti; leva 15–50×; margine massimo 400 USDT/trade e totale 55%; rischio 4,3%/trade e 12% aperto; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek confidenza minima 0,56; veto Claude; fallback dimezzato spento; LONG solo trend 1h+4h; costi/slippage entro 30% di 1R.
- La raccomandazione di pausa non modifica questi parametri e non approva V3.

## Servizi, dashboard, contabilità e apprendimento

- Ultima prova servizi: 11:28, runner `running`, uscite `healthy`, 146 `NO_TRADE`, 16 `ai_unavailable`, zero aperture; budget applicativo DeepSeek 3,8811/4 USD. È un contatore applicativo, non saldo provider o fattura.
- Screenshot 13:00: V2 attiva, analisi 30 minuti, proposta V3 `f9ae6e8bf8` generata; non prova servizi, posizioni o budget successivi.
- Nessuna prova della pausa consigliata o di nuove chiamate dopo la raccomandazione.
- Dashboard 09:33: equity 2.209,73 USDT, totale contabile 2.393,80 USDT e netto sessione -3,54 USDT ancora da riconciliare.
- Web-only del 25/11 verificata senza riavvio del runner; `work/brain-v2-web-counts-20261125` @ `6e305ed027e6aca132b0b3c1f27f42933ef902cd`, con runner/memoria `paper_reduce` ancora non certificati.

## Backup e chiavi, senza dati sensibili

- `claude/extbackup-storici-20261121` @ `1588c95af8411b48616d73203d5d10211d38e246`.
- Backup cifrato definitivo del 22/11 documentato come inviato e verificato da clone nuovo; restore Windows incompleto; Android/Termux e copia aggiuntiva preparati ma non eseguiti.
- `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: backup esterno preparato, non installato né certificato.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK`; chiave pubblica derivata coincidente. Prova locale, non certificazione del backup sulla VPS.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `86389b92df6bfc91856653b515d555d48a1e824d`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- `integration/brain-unico-20261119`: `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`.
- `claude/tetto-posizioni-20261121`: `887fc9616b5eedc2b4441357618fd5469ab5977d`.
- `claude/extbackup-storici-20261121`: `1588c95af8411b48616d73203d5d10211d38e246`.
- `claude/live-evolution-20261124`: `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`.
- `work/brain-v2-web-counts-20261125`: `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- RC84 PR #80: open, draft, non merged; head `0e29a73a36f668643da4088178bacb8616a45ac0`; ultimo aggiornamento 09/11/2026.
- Issue #124 chiusa il 22/11. EX-08B `cb31997f` resta non riscontrato su SuperBot-Trading.

## Test e fonte

- Tetto quattro posizioni/rischio: ramo `887fc961…`; risultati ereditati, non rilanciati.
- Issue #124: quattro test dedicati, tre rossi prima del fix; suite V3 dichiarata 5.414.
- Brain V2 `6a96e599…`: V3 5.588, Builder 158, Jest 212, restart 13/13, simulatore 2/2.
- Integrazione `f50f7ae4…`: V3 5.500 con un skipped, Builder 158, Jest 210, Android 126/126.
- Correzione conteggi `6e305ed…`: regressione mirata documentata; nessuna full suite o Action rilanciata qui.
- Nuova fonte: conversazione accessibile con domanda sui costi e raccomandazione di pausa; nessun test o controllo VPS nuovo.

## Eseguito, preparato, non approvato

### Eseguito/verificato

- Brain V2 PAPER/web, backup cifrato, age locale, diagnostica 11:28 e generazione della proposta V3 da parte dell'utente.
- Decisione di concentrare lo sviluppo su Evolution X.
- In questo checkpoint: sole letture e doppia documentazione.

### Preparato/raccomandato ma non eseguito

- pausa controllata delle nuove aperture del Brain, preservando le uscite;
- proposta V3 `f9ae6e8bf8`;
- roadmap Evolution X e AI Credit Guardian offline;
- backup storico, restore e riconciliazioni pendenti.

### Non approvato/non provato

- pausa effettiva del Brain e approvazione/attivazione V3;
- modifiche a soglie, capitale, leva, stop, budget o servizi;
- restart, reset, deploy, merge, Actions, modifiche VPS, ordini o API a pagamento.

## Blocker, prossime attività e ripresa

1. Confrontare `STATO.md`, questo checkpoint e la prima sezione Library.
2. Non assumere che il Brain sia fermo: verificare soltanto dopo autorizzazione se la pausa è stata eseguita e se le uscite restano sane.
3. Prima di spendere altro credito, verificare in sola lettura limite giornaliero e motivi degli scarti; non aumentare budget o abbassare confidenza automaticamente.
4. Trattare V2 come attiva finché non esiste prova esplicita di approvazione V3.
5. Proseguire Evolution X isolato in PAPER; non confondere i suoi test offline con lo stato del Brain originale.
6. Preservare Falco/Toro/Brain, EventJournal, archivi, memoria e backup.
7. Se una scrittura fallisce, recuperare prima quella destinazione al checkpoint successivo.

## Azioni escluse

Nessuna modifica di codice operativo, merge, deploy, GitHub Actions, VPS, reboot/riavvio, reset, ordine o API a pagamento. Nessun segreto letto o esposto.

