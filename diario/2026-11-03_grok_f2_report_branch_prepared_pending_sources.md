# SuperBot V3 — 2026-11-03 — Consegna Grok F2 e ramo di integrazione pronto

L'utente ha riportato un resoconto attribuito a Grok sul Brain V3 F2, con tarball nominato `v3-brain-f2-isolated.tar.gz` **non allegato in questa conversazione** e non trovato tra i file disponibili. Le affermazioni sui file effettivi e sui test `5/5 PASS` sono **dichiarazioni del collaboratore, non ancora riprodotte da ChatGPT**.

Contenuto dichiarato: `backend/v3/brain_f2/contracts.py` (NO_TRADE, OPEN, CLOSE, MODIFY_STOP, HOLD e provenance), `analyst.py` (MockDeepSeek), `reviewer.py` (MockClaude), `engine.py` (orchestratore con risk quote e memoria in-memory), README, `backend/tests/test_brain_f2.py`. Mancano adapter API reali DeepSeek/Claude, persistenza EventJournal, ciclo H24, regimi, policy di promozione strategie, integrazione posizioni e dashboard. Nessun deploy/merge richiesto e nessun sistema live toccato.

Grok ha segnalato un `403 Resource not accessible by integration` tentando la creazione del ramo. ChatGPT ha verificato il codice di `backend/v3/risk.py` e `events.py` e che PR #29 resta DRAFT su `work/v3-foundations-event-risk-20261102`, HEAD `91e6040ca7d81874fda9afd8c1a3cb10c6efe55e`, poi **creato con successo tramite il proprio connettore GitHub** il ramo `work/v3-brain-f2-grok` a partire da tale F1. La capacità di scrittura del connettore ChatGPT è verificata; non serve cambiare i permessi GitHub di Grok per procedere con la consegna.

**Il nuovo ramo è solo una copia di F1 e non contiene ancora F2.** Non creare PR DRAFT sostenendo che il codice è stato caricato finché non si dispone dei sorgenti reali. Attendere il tarball originale allegato dall'utente, quindi verificare il contenuto, difendersi da percorsi tar sospetti, controllare i contratti reali e riprodurre i test, infine creare PR DRAFT con base `work/v3-foundations-event-risk-20261102` per diff isolato F2.

Gate di valutazione: fail-closed se API indisponibile, quote di rischio per OPEN non applicato indiscriminatamente a CLOSE/HOLD/MODIFY_STOP, modifiche stop non permissive, idempotenza e per-position IDs, NO_TRADE senza ordini, doppio trigger/restart, segregazione portfolio, tempi/dati di mercato stale, provenance senza secrets o prompt injection, memoria e reviewer mock non spacciati per live. Nessuna chiave AI in commit.

Nessun avvio bot, merge PR #29/#32, reset, import, deploy o modifica VPS.