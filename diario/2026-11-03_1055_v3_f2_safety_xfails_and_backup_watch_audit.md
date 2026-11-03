# SuperBot V3 — 2026-11-03 — coordinamento F2 sicurezza e audit backup F0 (nessun deploy)

## Brain F2: safety contract gates aggiunti realmente
- PR #33 continua **DRAFT** e si appoggia solo al branch F1 `work/v3-foundations-event-risk-20261102`. PR #29/#32 non integrate.
- Creato `backend/tests/test_brain_f2_safety_contract.py` sul branch `work/v3-brain-f2-grok` con tre test di sicurezza `@pytest.mark.xfail(strict=True)`:
  1. Non proporre OPEN/APPROVED in assenza di risk manager operativo/configurato (no risk quote).
  2. DeepSeek assente/402 solleva eccezione dal client simulato: fail closed con NO_TRADE, niente fallback.
  3. journal_append deve ricevere realmente un evento `Event` con portfolio_id brain e timestamp, non solo RAM.
- Aggiornato workflow isolato F1+F2 a includere `backend/tests/test_brain_f2*.py`, senza AI reali, secrets, deploy, né VPS.
- GitHub Actions run https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41606677413: successo sia Python 3.10 sia 3.11: `110 passed, 3 xfailed`. I tre casi **non sono risolti**; l'xfail strict renderà XPASS un errore visibile finché la revisione non lo converte a test normalmente passing.
- Il lavoro di Grok richiesto in seguito: sostituire mocks con contratti safe, adapter F1 `RiskPolicy, RiskRequest, RiskQuote`, isolamento run/portfolio, journal idempotente, no fallback su errori, recovery e test su CLOSE/MODIFY_STOP. Evitare qualsiasi auto-promozione delle strategie; consegnare sorgenti/tarball per revisione ChatGPT perché connettore Grok è attualmente read-only.
- Revisioni concrete documentate in `docs/v3/brain-f2-grok-review-20261103.md`.

## Audit delle infrastrutture backup già presenti: fatti osservati
- `.github/workflows/sg-extbackup-watch.yml` sul branch `main`: workflow preesistente che legge lo stato remoto `/opt/superbot-extbackup/status.json` via chiave SSH **legacy root** `SINGAPORE_SSH_PRIVATE_KEY`. Il parser `deploy/scripts/extbackup_watch.py` verifica solo esistenza di ultimo_successo, assenza ultimo_errore e freschezza sotto soglia (default 36 ore); **non verifica hash archivio, liste contenuti, presenza off-host, chiave age recuperabile o restore**. NON rilanciare questo workflow con privilegi root per F0.
- Ultima esecuzione visibile nei 100 workflow recenti al momento dell'audit: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41447751395, 2026-11-02 12:48 UTC, `conclusion: success`; log: `OK ultimo backup esterno riuscito 2026-11-02T03:28:45Z (9.3 ore fa): superbot-backup-20261102T032845Z.tar.gz.age`. Il formato `.age` suggerisce archivio cifrato ma il log non prova decifrabilità/completezza.
- Il workflow dichiara schedulazione giornaliera `40 4 * * *` (UTC). Nelle esecuzioni recenti che coprono 2026-11-01/03 non appare un controllo del 2026-11-03. **Verificare se la schedulazione sia attiva / ritardata / disabilitata**: l'assenza di un run non prova che il backup locale notturno non sia avvenuto.
- Il codice `external_backup.py` citato dalla sentinella si trova presumibilmente su VPS in `/opt/superbot-extbackup`, non è incluso nel repository `main`. Non è stato ispezionato in questo checkpoint; nessuna garanzia sul suo elenco inclusioni o destinazione.
- F1 PR #29 contiene già `backend/v3/backup_certification.py` con `observe_brain_source_readonly`, `capture_brain_copy`, `verify_brain_offhost` e `docs/v3/f0-backup-certification-runbook.md`: richiedono witness esterno indipendente SHA256 eventi, numero/seq, hash manifesto, snapshot WAL-aware, storage separato, restore e confronto.
- Dati storici attesi dai precedenti controlli: snapshot Brain locale WAL-aware con 8.447 eventi; Hawk 348 e Bull 186 chiusure; includere lessons, archive e learning. Quest'osservazione NON è certificazione di conservazione offhost.
- PR #32 `ops/f0/classic_metadata_acl.sh` ancora in bozza, verificata a livello statico: `--check` non modifica dati, `--apply` richiede root sul server e propone ACL solo --x su cartelle hawk/bull, con rollback; CI precedente PASS. Nessun permesso applicato, nessuna sicurezza filesystem affermata senza check locale.

## Prossimo gate operatore (nessuna autorizzazione ancora concessa)
1. Predisporre **audit sola lettura** del pipeline esterno già presente: tipologia destinazione indipendente, recenti run e archive manifest, retention, copertura delle tre famiglie di dati, status cron. Non esporre recipient privati, password o indirizzi sensibili.
2. Ottenere fonte indipendente dei witness PR29 e RESTORE verificato fuori VPS, non simulare.
3. Per ACL classici PR #32 effettuare `--check` locale solo dopo approvazione del comando amministrativo separato; l'applicazione `--apply` non è parte dell'audit e resta proibita senza esplicita autorizzazione.
4. Privilegiare GitHub restricted diagnostics F0 già convalidato; non usare vecchie credenziali root per operazioni arbitrarie.

**Nessun restart, merge, deploy, import, reset wallet, cambio ACL, cancellazione chiavi o accesso SSH root eseguito durante questo lavoro.**
