# SuperBot F0 — 2026-11-03 — PR #30 merged, workflow ready for first manual execution

## Autorizzazione
Utente «ok procediamo» in risposta alla richiesta esplicita di merge della **sola PR #30** nel ramo `main`; la PR V3 #29 non è autorizzata a essere mergiata.

## Operazione GitHub eseguita
- `mcp__GitHub__merge_pull_request` con `merge_method=squash` e `expected_head_sha=6931d84bed3867a9f773d22744795c9f5dd5c950`.
- GitHub risponde `merged:true`; commit merge squash su main: `281dff50ead29b1ca2bfa79772cdf40033698289`.
- Verifica successiva: PR #30 `merged:true`, `closed`; PR #29 `draft:true`, `open`, `merged:false`.
- `.github/workflows/f0-restricted-status.yml` esiste ora su `main`. Contiene `workflow_dispatch` e schedule `35 3 * * *` (03:35 UTC), SSH `superbot-f0`, forced-command richiesto, pinned host key, no checkout e permessi `contents: read`.
- I 8 test del ramo PR #30 erano PASS. Non è stata eseguita una connessione remota con la nuova chiave; non esiste ancora un run della diagnostica `SuperBot F0 - restricted VPS status` osservato nel risultato di GitHub.

## Credenziali e safety
L'utente ha confermato di aver creato `SUPERBOT_F0_SSH_PRIVATE_KEY` direttamente in GitHub e di aver installato la relativa chiave pubblica sulla VPS. La connessione GitHub non consente al modello di leggere secret o verificarne direttamente il valore. Nessuna credenziale è stata condivisa nella chat.
Nessun comando SSH eseguito da ChatGPT né modifica ai wallet, bot, storico, database, WAL, VPS runtime, V3 o backup F0 offhost.

## Gate successivo
Serve `workflow_dispatch` del workflow via UI GitHub (gli attuali strumenti GitHub collegati consentono la lettura dei run ma non l'avvio ex novo dei workflow). Azione UI: GitHub repo → Actions → SuperBot F0 - restricted VPS status → Run workflow → branch main → Run workflow. Dopo conferma avvio da utente, ChatGPT legge risultati/log direttamente da GitHub. Se il job fallisce, indagare senza inviare chiavi private o usare vecchio SSH-root. Se PASS, attestare solo diagnostica metadati `OBSERVATION_ONLY`, non backup F0 certificato.

## Scheduling
Dopo merge è abilitata anche l'esecuzione automatica quotidiana prevista alle 03:35 UTC. Non dichiarare il job riuscito finché non esiste un run concluso con esito positivo.
