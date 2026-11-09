# 09/11/2026 — SuperBot V3, audit della proposta CI offline e guard test integrazione (RC84 SHA 74fbde2)

## Riferimenti e stato
- [PR #80 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80) HEAD `74fbde2ae0327503241e1e7e1ca15513b818de28`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`, non mergeata. Commit codice/test/doc `bee85fda7b2c513fec19af86ae211213fade924d`, commit successivo aggiornamento handoff.
- [Review indipendente ChatGPT in PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6747209165).
- Nessun file `.github/workflows/` aggiunto/modificato da questa patch: proposta **inerte** `docs/v3/RC84-CI-OFFLINE-PROPOSAL-20261109.md` con blocco Markdown contenente YAML; **nessuna GitHub CI** associata allo SHA. Nessun merge/deploy/VPS/riavvio/reset/ordine da parte di ChatGPT.

## Parti corrette e verificabili nel codice
- `backend/tests/conftest.py` registra `integration` e salta automaticamente test server salvo `SUPERBOT_ALLOW_INTEGRATION=1` e URL backend con host esatto localhost/127.0.0.1/::1. `backend/tests/test_superbot.py` usa secondo guard del wrapper `http` per GET/POST; password bootstrap hardcoded rimossa da questo modulo (restano occorrenze nel repository).
- `backend/tests/test_ci_integration_guard.py`: con server finto loopback registra 0 chiamate e 0 POST senza opt-in o con marker escluso, prova positiva locale su GET health e POST start, invalid host/URL; `backend/tests/test_v3_rc84_ci_proposal.py` controlla testo bozza senza dipendenze addizionali. `actionlint` dichiarato passato.
- YAML proposto Python 3.11 / Node 22, permessi `contents: read`, test `-m 'not integration'`, env `REACT_APP_BACKEND_URL: ''` e `SUPERBOT_ALLOW_INTEGRATION: '0'`, namespace rete vuoto per pytest/Jest/build, no segreti/ssh/docker/systemctl/trigger main. Trigger potenziale: push sul branch RC84 che aggiunge `.github/workflows/rc84-offline-verify.yml`; qui NON effettuato.
- **Evidenza test locale riferita da Claude** (non eseguita da ChatGPT): backend Python 3.11 netns **6935 PASS / 0 FAIL / 3 xfail / 9 deselected**, Jest **124/124**, build React PASS. Un primo run senza loopback aveva 1 FAIL nel test positivo, poi risolto con ioctl sulla sandbox e riconfermato con loopback funzionante. Nessun run su GitHub ospitato.

## Gate piccoli ma importanti prima di pubblicare workflow

### P1: wrapper check URL reale e redirect
`_Guarded._check()` in `test_superbot.py` verifica l'ambiente ma **non** l'URL effettivo passato a `requests.request`. Python Requests abilita i redirect HTTP per default (documentazione). Con opt-in locale un server che risponde redirect verso host remoto potrebbe far partire una seconda richiesta fuori loopback quando i test sono eseguiti **fuori da un namespace isolato**: la whitelist di host iniziale non è un confine per tutti gli hop. Richiesta mini-fix: wrapper valida URL effettivo, `allow_redirects=False`, sessione `trust_env=False` (no proxy ereditati), timeout; test di redirect finto che documenta nessuna richiesta a host non-locali. `unshare -n` blocca il traffico esterno nel workflow proposto, ma non basta per usare in sicurezza opt-in locale in altri contesti.

### P1: portabilità / prerequisiti del runner GitHub reale
`sudo unshare -n` e `ip link set lo up` su `ubuntu-24.04` sono stati soltanto proposti, **mai verificati su GitHub-hosted runner**; esistono limitazioni AppArmor per namespace non privilegiati, ma non è provato che questo specifico comando sudo fallisca. Aggiungere un **preflight diagnostico** nell'esecuzione vera; comportamento deve restare fail-closed: se namespace non disponibile, job rosso, **mai fallback con rete aperta**. Specificare `PYTHONPATH=.:backend` nel workflow per evitare effetti di ordine dei test import backend/desk. Le azioni ufficiali `checkout/setup-python/setup-node/upload-artifact` sono ancora a tag @v4/@v5: pin a SHA verificati prima del commit che attiva la CI. Evitare di inserire app workflows operativi o segreti.
- Il rollout della CI richiede **approvazione esplicita dell'utente** prima del commit che aggiunge il YAML in `.github/workflows/`, poiché il push lo avvierà. Nessun workflow GitHub è stato lanciato in questa review.

## Gate del progetto ancora aperti
- D1 UI claim + D2 fencing Brain hanno superato code review, MA non collaudo operativo.
- CI su commit pinned che non contiene `[skip ci]`, browser autenticato e Android, decisione includere/escludere PR #76 e 2 commit main, password bootstrap staging statica da rimuovere/ruotare se attivo (controllo VPS solo con mandato), backup off-host+restore, preflight VPS read-only separatamente autorizzato, handover Brain verso sidecar senza processi legacy non aggiornati, rischio stop classici OHLC 15m periodico e NON continuo. Ripartenza **solo PAPER** portafogli Falco/Toro 1000 e Brain 2000 USDT, storico e learning preservati, solo dopo OK esplicito.

**Verdetto:** proposta CI accettabile come disegno, non ancora autorizzata per attivazione; micro-hardening redirect/target + portabilità runner prima del GO. Nessun merge/deploy/VPS/RESET/RESTART/ORDINI.
