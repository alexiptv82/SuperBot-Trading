# 09/11/2026 — SuperBot V3 RC84: QA Python 3.11 green offline; pericolo test integrazione e CI ancora aperta

## GitHub / code review
- PR #80 **DRAFT**: HEAD esatto `10ac0cce626716ee97983319f23cfb538b377ce1`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`, non mergeata, non distribuita.
- Commit codice+test `480cd53002d363432cac9790349e575bcd04d39a`, commit successivo soltanto aggiornamento dell'handoff.
- [Code review e avviso sicurezza GitHub](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6746349575).
- ChatGPT ha verificato il diff GitHub dei file `backend/{desk_view.py,live_view.py,v3_api.py}`, `backend/tests/{test_auth_flow.py,test_profiles_engine.py,test_brain_f3_boundaries.py,test_desk_view.py,test_long_s25.py,test_superbot.py,test_v3_rc84_claim_visibility.py}`, il test_integration e le dipendenze. Non ha rieseguito pytest/Jest, nessun run GitHub CI registrato sullo SHA. Nessun contatto VPS o trading.

## QA Python 3.11 da relazione Claude
**Backend completo in sandbox su Python 3.11:** **6.910 PASS / 0 FAIL / 9 SKIPPED / 3 xfail**. Confluenza auth/profiles inclusa. **Frontend Jest 124/124 PASS**, React `CI=true` build PASS. Lock/ownership 136 test PASS. Questi risultati sono **test locali riferiti da Claude**, non GitHub CI né attestazione da ChatGPT. 9 test `test_superbot.py` SKIPPED, **NON PASS**; 3 xfail preesistenti.

Interventi confermati da codice:
1. Fixture RiskPolicy F3 aggiunge valori default `max_loss_margin_fraction=None`, `min_leverage=1`, `max_leverage=125`, senza alterare rischio di produzione; test firma mutato intenzionalmente in scratch: 4 fallimenti, poi ripristinato.
2. Test auth/profiles smettono di lasciare il CWD globale alterato dopo import, ristabilendo i test subprocess RC80; attenzione che i test modificano ancora env all'import, ma non emerge nuova regressione nel report.
3. `live_view` inoltra `now` al reader, `desk_view` distingue in 409 'bot vecchio' e 'non risponde'; retry manual test allineato a contratto RC73 di comando in pending = rifiuto 409.
4. Pin `brain.py` del test S25 aggiornato dopo verifica modifica intenzionale RC82; `engine.py` (formule) invariato.
5. `v3_api` ora usa `heartbeat.paper_close_claims.pending >0` fresco per **non** presentare `ok` se lo state non riporta claim; segnala `unknown`.
6. `test_superbot.py` marcato `integration` e skip se manca `REACT_APP_BACKEND_URL`.

## SICUREZZA: requisito prima della CI
`backend/tests/test_superbot.py` contiene ancora test che, **se `REACT_APP_BACKEND_URL` è impostata**, eseguono HTTP contro l'URL e un **POST operativo `/api/bot/start`** oltre a login con password bootstrap statica nel repository. `skipif(not BASE_URL)` non è una barriera sufficiente: in CI può esserci una variabile `REACT_APP_BACKEND_URL` ereditata dal frontend o ambiente. **Non riportare valore password in report.** Prima di qualsiasi CI, escludere sempre i test `integration` con selezione esplicita *e* variabile URL disabilitata/validata oppure esclusione fisica del file. Test di integrazione solo in laboratorio isolato ed effimero, senza VPS, credenziali statiche o operazioni operative. Prova negativa: con URL fittizio presente nessuna richiesta esterna, nessun POST. Se `pytest.mark.integration` non è registrato in configurazione, registrarlo prima di `--strict-markers`.

## Pianificazione CI (NON eseguita)
- Dopo audit trigger GitHub: proporre su branch Draft un workflow esclusivamente offline `rc84-tests.yml`, Python 3.11 e Node22, `permissions: contents: read`, no `secrets`, no SSH / deploy / docker operational / systemctl / URL backend, nessun trigger `main` e nessuna esecuzione di workflow operativi.
- Allineare run su commit SHA pinned **senza `[skip ci]`** e verificare log e test, senza chiamare 'CI verde' prima dell'esecuzione. Attivazioni automatiche dopo commit devono essere previste e autorizzate, anche se di sola QA.
- Prima della release: decidere PR #76 (RC79 diagnostica post-trade, non antenata) e 2 commit `main` divergenti; creare RC unica; rimuovere password bootstrap pubblica da workflow staging e ruotare se staging attivo (solo con mandato), backup off-host+restore, UI web autenticata Android, Brain legacy→sidecar fencing e systemd con preflight VPS autorizzato, accettazione stop classici OHLC 15m periodici (non continuo), nuova run **solo PAPER** Falco/Toro 1000, Brain 2000 con storico e learning preservati e OK esplicito.

**Nessun merge/deploy/accesso VPS/restart/reset/ordine da ChatGPT; PR #80 Draft; release NO-GO.**
