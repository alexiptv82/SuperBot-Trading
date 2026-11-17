# AI Arena — React compilato e anteprima privata SSH (17 novembre 2026, 14:10 Europe/Rome)

## Screenshot di collaudo confermato
L'utente ha eseguito il branch `work/arena-ui-smoke-build-20261117` nel checkout temporaneo della VPS `/tmp/arena-ui-smoke.rCgqLY/repo`.
Risultato visibile su Termius:
- React build completata `Done in 21.70s`, 14 file di build.
- Digest del bundle: `e222e6ca6bf61406d38d08cda9e4dcd22ca4c3990f167b56106bca486064fd3e`.
- `RESULT=TESTS_AND_REACT_BUILD_VERIFIED_NO_DEPLOY`, `published=NO`, `services_changed=0`.
- Colllaudo 31/31 Jest superato nel run precedente, React compilato in questo.
- Nessun file copiato nell'app operativa; portafogli Qwen/MiniMax non avviati; storico DeepSeek visibile in sola lettura con API già esistenti.

## Perché anteprima distinta
Il sistema operativo e Nginx di produzione restano intatti. L'app usa un frontend CRA con stesso dominio per `/api` e login; servire solo file statici con `python -m http.server` darebbe errore 404 sugli endpoint. Non creare una porta HTTP pubblica per aggirare le API.

## Preparata anteprima soltanto via SSH locale
Nuovo file `deploy/scripts/arena-ui-ssh-readonly-preview-20261117.py` (non eseguito sulla VPS):
- modalità `--preflight`: solo lettura. Verifica repository temporaneo, nessun diff del frontend rispetto al sorgente compilato, checksum bundle esatto, assenza di modifiche tracciate, porta 18088 libera e `GET http://127.0.0.1:8002/api/health` con HTTP 200.
- modalità `--serve-ssh-only`: dopo preflight avvia un server Python esclusivamente in ascolto su `127.0.0.1:18088`, non modifica Nginx né avvia/ferma bot. Da Samsung si accede soltanto tramite **Termius → Port Forwarding → Local**, con host VPS Singapore già configurato, porta locale **18088**, destinazione **127.0.0.1:18088**, indirizzo bind locale **127.0.0.1** (NON 0.0.0.0); infine Chrome Android su `http://127.0.0.1:18088/arena`. Nessun nuovo DNS, firewall, dominio o porta pubblica.
- server statico SPA con proxy blindato. Soli GET consentiti: `/api/v3/overview`, `/api/v3/brain/status`, `/api/v3/brain/trades?limit=100`, `/api/auth/password-status`, `/api/auth/webauthn/status`. Unico POST consentito: `/api/auth/login` (normale login password, richiesta cifrata nell'SSH tunnel; nessuna credenziale salvata dal server). Ogni API operativa o mutazione, incluse PUT/PATCH/DELETE/POST chiusure, bloccata con HTTP 403. Il login biometrico o il cambio password non funzionano in questa anteprima isolata, da effettuare nell'app vera se necessari.
- HTML e asset serviti soltanto da `frontend/build` con path traversal bloccato. No log token/password, no caching. Il server non ha né legge segreti di trading.
- Controindicazione nota: l'anteprima non può mostrare Qwen/MiniMax in attività senza journal PAPER indipendenti. Non avvia i tre wallet né il test di 14 giorni. L'app operativa resta invariata.
- Se l'API `127.0.0.1:8002` non risulta 200, fermarsi per diagnosi read-only: non cambiare proxy di produzione.

## Prossimi comandi proposti
Con checkout ancora disponibile e `git status --porcelain` pulito:
```bash
cd /tmp/arena-ui-smoke.rCgqLY/repo &&
git pull --ff-only --quiet &&
python3 -m py_compile deploy/scripts/arena-ui-ssh-readonly-preview-20261117.py &&
python3 deploy/scripts/arena-ui-ssh-readonly-preview-20261117.py --preflight
```
Soltanto se preflight confermato, avvio manuale `--serve-ssh-only` mediante Termius; non far partire il server come daemon di sistema né pubblicarlo su Internet. Nessun GitHub Actions.

## Piani successivi
1. Anteprima browser Samsung con dati autentici del Brain (solo storico, non trial).
2. Completa equivalenza 25 contratti verificati e regole di rischio; tre wallet PAPER da 2.000 USDT e servizi uscite distinti, un T0 uguale per 14 giorni.
3. Con nuovo consenso esplicito, deploy controllato della dashboard e successiva attivazione trial. NO merge/deploy senza consenso; Falco SHORT invariato, Toro a riposo.
