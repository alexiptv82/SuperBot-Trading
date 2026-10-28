# Brain Scalp doppio wallet — sviluppo isolato 28 ottobre (chat normale)

## Mandato e confini
Utente: «procedi!» a seguito della scelta B e del piano che esplicitava sviluppo isolato, niente interruzione degli attuali bot, test e rilascio successivo con nuova autorizzazione. Non si è eseguito alcun deploy, riavvio, ordine, reset, archiviazione o chiusura delle posizioni su VPS. I classici Hawk/Bull e il Brain originale non sono stati modificati.

## Codice operativo di laboratorio pubblicato
Branch work/brain-scalp-dual-20261028, base Brain Free V2 e0021488b47e8b245954a708b139bc4785a4b644. Nuovo package backend/director/brain_scalp, senza modificare backend/desk o backend/director/brain_free.
- Brain Hawk/Bull: account-id distinti, 1.000 USD PAPER nuovi ciascuno; slot 10/3; margini 100–250 e 150–350; rischio di test 50 USD/trade, 150 USD/portafoglio, max margin 950, daily stop 20% e kill equity 450. Questi parametri nuovi non sono autorizzati al deploy.
- WalletStore SQLite separati, writer lock, fail-closed su root e conto non corretto, backup/restore confrontabile; no reset implicito.
- Scanner causal 1m/5m breakout long/short, shortlist di massimo 5, reason code di ogni mercato; schema piano AI condizionale con expiry/trigger, stop/target e livelli validati; quote con max 30s.
- Esecutore locale riusa brain_free.execution.apply/protect/close con fee, tick e buffer liquidazione, stop/protezione preingressi, risk budget e piani pending che impegnano slot/margine, uscite su profitto netto osservato/time/giveback.
- BrainPair: un'unica shortlist condivisa, due ledger e due esecutori indipendenti, rifiuta decisioni di direzione contraddittoria rispetto alla shortlist.
- Dati heartbeat e last_prices salvati per una dashboard read-only. Nessuna chiamata a DeepSeek o Bitget è effettuata da questo package.
- CI offline Python 3.10/3.11 e protezioni su file classici e Brain Free originale: Actions 40709722381 e 40710090248 SUCCESS. Ultimo commit di test heartbeat d96d171 è stato inviato con nuova CI richiesta, risultato da verificare prima di certificare l'ultima punta.
- Documentazione tecnica e checklist review per Claude in docs/brain-scalp-dual-review.md, separazione stretta dai classici.

## PWA separata e verificata
Branch work/brain-scalp-dual-app-20261028, base main 2283bfb1c63959015658904a75d68d6587cca314.
- Endpoint autenticato GET /api/brain/scalp e reader SQLite in sola lettura su due root distinti: non crea conti, mostra stato not_started quando non sono disponibili, non inventa equity se prezzi stantii, controlla l'identità del conto.
- Schermata /brain/scalp: Brain Hawk e Brain Bull, slot, equity, margine, leva, posizioni, pending, motivo aperture/uscite e rifiuti, link dal vecchio Brain.
- CI 40710835022 SUCCESS: backend reader/auth GET-only e build frontend Yarn. Guardie confermano invariate directory dei bot classici e file originali Brain Free.
- NESSUN deploy dell'app e nessun mount del nuovo volume eseguito.

## BLOCCANTI, niente deploy
1. Feed H24 Bitget con WS/REST, dati 1m/5m, universo liquidità/top30, tempo quote, reconnect, zero duplicazione writer.
2. Modello AI H24 con prompt di shortlist breve, risposta strutturata, budgeting AI crash-safe reserve/settle e costi token per wallet, test sotto disconnessione.
3. Replay anti-lookahead e robustezza, scalping retest/rimbalzi oltre breakout, simulazione reale della frequenza, bidirezionalità, P&L netto e drawdown.
4. Stesura ed esecuzione futura con separata autorizzazione del retirement Brain originale: posizioni prima contabilizzate o gestite fino a flat, SQLite/outbox/log/requests/spese e storici in backup verificato/restaurabile, stato ritirato, mai doppia istanza; risorse e API misurate.
5. PWA in runtime richiede mount rigorosamente RO dei nuovi wallet, test e autorizzazione dedicata. I due rami hanno basi diverse: niente merge indiscriminato.

## Passaggio Claude
Leggere docs/brain-scalp-dual-review.md, diff del ramo Brain e CI. Chiedo audit indipendente su long/short, stop/risk/buffer, funding e fee, daily rollover, idempotenza crash, stale, costo provider e test su dati storici. Usare branch/file disgiunti e registrare la review sul diario; non toccare né distribuire classici o Brain originale. La chat Claude NON ha ricevuto un messaggio diretto da questo tool; la consegna è pubblicata sul ramo diario.

AI: chatgpt (chat normale)
