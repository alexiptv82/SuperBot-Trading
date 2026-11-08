# 2026-11-08 — ChatGPT verifica indipendente del rapporto RC83 (Brain V3)

## Riferimenti controllati
- Report Claude: https://github.com/alexiptv82/SuperBot-Trading/blob/ccr-999de027-0stnyt/claude/rc83-brain-audit-20261108.md (commit `22590d3020db9e67d3f6143f24424bdd3918486f`). 
- Diario Claude: `diario/2026-11-08_claude-rc83-brain-audit.md` e checkpoint STATO.md sul ramo `diario` a commit `6ab9ae9f1f4f96929f0c67b22dc436bd9cb92066`. Entrambe le voci sono state lette.
- Base di audit Claude `29eb75750625a8819cd2db71dc2459d164c3199c` (RC81/PR #78), **non** un test sul merge completo RC82 né una verifica VPS. Report verificato in GitHub, nessuna PR di fix per Brain.
- Nel report: **4.849/4.849 test V3 PASS dichiarati da Claude** sulla sua VM, nessun P0/P1 trovati; suite citate 34 manual-close, 4 cutover, 46 exit-service, 24 exit-worker, 5 Brain 2000. Questa review ChatGPT **non ha rieseguito indipendentemente i 4.849 test** e il report non porta allegati dei log/identità del runner. Non dichiarare certificazione CI o e2e.
- RC82 classici PR #79 è indipendente e oggi in evoluzione; al momento di questa verifica il suo HEAD è passato a `1e64684b9d813aad1ca1c7d344872333e451fd05` dopo `bccfddf`. Questo **NON** è stato ancora revisionato da ChatGPT; non introdurre lo SHA nel rilascio senza handoff e nuova review.

## Che cosa ha verificato la lettura dei sorgenti
- `backend/v3/runner/open_serial.py`: il gate PAPER OPEN richiama realmente `exit_service_healthy` prima di `execute_paper`, in fail-closed.
- `backend/v3/runner/exit_service.py`: lease POSIX + heartbeat aggiornato, controllo run_id, stato `healthy`; modulo definito *prototype (NOT wired into live runner)*; richiede handover di un solo owner.
- `backend/v3/runner/exit_worker.py`: esiste CLI `--validate-only` e avvio esplicito `--start-paper`; `--legacy-exits-disabled` è dichiarato in argparse **operator assertion only: legacy worker ownership removed (NOT a technical proof)**. Dunque la flag **NON spegne il vecchio writer**. L'audit Claude non dimostra il vero single-owner sulla VPS.
- `backend/v3_api.py` per chiusura Brain opt-in controlla sidecar e run_id; il comando API può dare `pending` e non è automaticamente prova della chiusura. Manca ancora prova di funzionamento con il browser/app autenticata sul deployment finale.
- La UI Brain è già stata sviluppata e testata in RC72/RC74; RC80/RC81 telemetry maintenance **non** deve essere applicata al Brain.
- Non verificato oggi lo stato attuale della VPS, dei mount/data-dir, i servizi systemd, la versione effettivamente distribuita né la configurazione journal della nuova run.

## Decisione di revisione: CODE AUDIT RC83 ACCETTATO COME EVIDENZA OFFLINE, RELEASE NO-GO
Il rapporto non prova bug P0/P1 nel perimetro di test; supporta una buona copertura offline. **Non significa che il sistema Brain sia pronto a negoziare trade PAPER sulla VPS**.

Il gap di deployment sidecar è un **operational release blocker**, anche se classificato P2 nel rapporto Claude. Il codice documenta esplicitamente che la flag di handover NON costituisce prova automatica del precedente owner disattivato.

## Gate indispensabili prima di autorizzare nuova run Brain 2.000 PAPER
1. Congelare versione finale delle PR e loro compatibilità (RC74 Brain, RC80, RC81, RC82 Grok). Non mergeare automaticamente.
2. Predisporre e verificare backup separati e prova restore, incluso off-host, senza alterare storico.
3. **Preflight read-only** autorizzato della VPS: inventario runner Brain/legacy-exits/exit-worker, service unit, mount, nome `run_id`, `journal.db`, config, env PAPER e lock; provare che non esistano due exit owner. Nessuna azione mutating inclusa nel preflight.
4. Testare `--validate-only` su clone/sandbox isolato o autorizzazione separata per la run vera, verificarne il comportamento senza scrivere.
5. Handover single-owner studiato e reversibile; NON eseguire semplicemente `--start-paper --legacy-exits-disabled` finché il vecchio proprietario non è realmente disattivato/isolato. Monitor e manual close devono produrre heartbeat `healthy` e scritture esclusive di journal; OPEN rimane bloccato fino ad allora.
6. Test E2E PAPER isolato su dati sintetici (sidecar crash/restart, price stale, stop/TP/liq, dup close/manual close, UI 3 wallet in browser autenticato), poi test di avvio controllato su nuova run con OK utente specifico.
7. Capitale desiderato per nuova run: Brain 2.000 USDT PAPER, Falco 1.000, Toro 1.000, storici preservati; nulla è stato azzerato/riavviato.

## Ruoli
- Grok owner RC82 classici finché non consegna SHAs/tests.
- Claude audit RC83 concluso; non occorre avviare un altro sviluppo Brain in questa fase, ma può fare revisione indipendente del piano di handover **senza intervento VPS**.
- ChatGPT coordina e certifica soltanto quanto effettivamente verificato.
- Diario canonico va aggiornato da un solo autore per volta per evitare sovrascritture. Claude ha aggiornato correttamente il diario questa volta, ma dal prossimo incarico la modifica di `diario/STATO.md` è riservata al coordinatore.

**NO MERGE/DEPLOY/VPS RESTART/RESET/TRADING LIVE, nessun intervento sulla VPS fatto da ChatGPT in questo audit.**
