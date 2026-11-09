# 09/11/2026 — ChatGPT RC84 review SHA 5e768630, proposta CI hardening e gate self-contradiction

## Identità verificata
- PR #80 Draft `cursor/rc84-running-stop-health-telegram-20261108`, HEAD `5e76863001ac2d540ca0ef8e81b849e0f449b9d7`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`; non mergeata.
- Commit test+documento `56877eecee148e7c35c5cc3fcf526bec2cd46770`; commit finale solo handoff.
- [Review indipendente pubblicata in PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6748220955).
- Nessuna modifica a `.github/workflows/`, nessuna CI GitHub avviata; nessun accesso VPS, merge, deploy, reset, restart, ordine.

## Pass code review sul hardening
- `backend/tests/test_superbot.py` wrapper HTTP per test integration: host/schema/porta URL effettivo devono coincidere con `REACT_APP_BACKEND_URL` e whitelist localhost, `allow_redirects=False`, `requests.Session.trust_env=False` (no proxy ambiente), default timeout 10 s. Regressioni redirect verso server sentinella, altra porta locale, proxy ed URL diversi con spia HTTPAdapter.send; nessuna connessione esterna nei test sintetici.
- YAML **solo nel Markdown** `docs/v3/RC84-CI-OFFLINE-PROPOSAL-20261109.md`, non attivo; preflight in backend e frontend con `sudo -n unshare -n`, verifica lo/rotte/ENETUNREACH/DNS, nessun fallback con rete; `PYTHONPATH` assoluto passato a sudo, import validati da cwd diversa.
- Pin SHA delle quattro `actions/*` verificati come commit esistenti con API GitHub: checkout `11d5960a326750d5838078e36cf38b85af677262`, setup-python `a26af69be951a213d495a4c3e4e4022e16d87065`, setup-node `49933ea5288caeca8642d1e84afbd3f7d6820020`, upload-artifact `ea165f8d65b6e75b540449e92b4886f43607fa02`. Verifica di origine/tag dichiarata da Claude via git ls-remote; non security audit del source delle azioni.
- Test **riferiti da Claude** localmente (NON rieseguiti da ChatGPT): backend Python 3.11 netns **6960 PASS / 0 FAIL / 9 deselected / 3 xfailed**, due ordini; Jest **124/124 PASS**, React build PASS; actionlint 1.7.12 PASS. Nessun workflow GitHub per HEAD.

## Due micro-gate PRIMA di attivare CI
**P1 autocontraddizione CI.** `backend/tests/test_v3_rc84_ci_proposal.py::test_proposal_is_not_an_active_workflow` afferma che `.github/workflows/rc84-offline-verify.yml` non deve esistere. Ma la CI proposta una volta attivata crea proprio questo file e lancia la suite `pytest backend/tests`, che raccoglie il test e quindi **fallirebbe al primo run**. Correzione *test-only*: consentire file mancante in stato Draft; se file esiste, esigere corrispondenza byte-a-byte o normalizzata al blocco YAML revisionato in docs e invarianti permessi/trigger/guard; test scratch per caso assente, identico, alterato. NESSUNA creazione del workflow ora.

**P2 timeout massimo non applicato.** `backend/tests/test_superbot.py::_Guarded._send` usa `kwargs.setdefault('timeout', 10)`: mantiene valori espliciti anche `timeout=999`, `timeout=None`. Il report afferma massimo 30 s, ma il wrapper non lo impone. Fail-closed: validazione valori timeout numerici/finitezza, positivi e ≤30s (o limitazione a 30, con decisione esplicita), test che impediscano richieste su valori invalidi. Non cambiare produzione.

## Stato e prossima fase
La struttura CI è valida come **proposta inattiva**, ma non pronta al primo run prima dei due gate sopra. Preflight Ubuntu 24.04 GitHub-hosted non è testato: deve fail-closed senza ripiego. Dopo mini-fix e review chiedere **OK esplicito user** prima del commit separato senza `[skip ci]` che aggiunge `.github/workflows/rc84-offline-verify.yml` e provoca potenziale avvio job. In seguito esaminare log CI sullo SHA e gate release: browser autenticato Android, staging bootstrap password statica pubblica da rimuovere/ruotare se attiva previo mandato, decisione stack PR #76/main, backup off-host+restore, preflight VPS autorizzato, Brain handover A→B e sistema systemd, stop classici OHLC periodici. Nuova run Falco/Toro 1000 + Brain 2000 solo PAPER con storico preservato e consenso espresso. **NO MERGE/DEPLOY/VPS/RESTART/RESET/ORDINI**.
