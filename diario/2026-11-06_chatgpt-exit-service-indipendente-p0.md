# SuperBot V3 — EXIT SERVICE PAPER indipendente dall'AI, gate P0
Checkpoint: 6 novembre 2026 | Autore: ChatGPT GPT-6 | Stato: PROTOTIPO LOCALE, NESSUN MERGE / DEPLOY / VPS / AVVIO.

## Sorgenti e perimetro
PR #57 runner e25c8dd8db88fd6994e3b7a75ecfdec5ff258421 e PR #61 dashboard a9044b6759da327b44da04f9e7f51e211d44e03f ancora draft e separate. Lavoro su ZIP e25: 385/385 file preesistenti byte-identici dopo rollback delle patch. Solo file nuovi e patch proposta, non push codice.

## Realizzato
Nuovo backend/v3/runner/exit_service.py: exit-sidecar per PAPER con esclusività POSIX flock per tutta la sessione, token di lease rigenerato a ogni restart, tick serializzati, heartbeat dedicato con stato healthy/degraded, monitor ogni minuto, manual-close a ogni tick di prova (~5s). Usa run_manual_close/run_exit_monitor/close_paper originali, journal SQLite con UNIQUE paper_close.<position_id>. Nessun ordine live, nessuna chiamata AI, nessun auto-start o CLI.
exit_service_healthy() è un gate read-only fail-closed: richiede lock realmente detenuto, token uguale al heartbeat, stessi data-dir/run-id, heartbeat/monitor/comandi recenti e sani. Dopo stop/crash o restart non riutilizza un battito vecchio.
Patch NON APPLICATA SuperBot-V3-EXIT-SIDECAR-RUNNER-OPT-IN-NON-APPLICARE.patch: Runner.external_exit_guard=None, run_brain_cycle.pre_open_guard=None (entrambi default OFF). In modalità futura split il runner cede il monitor e manual-close al sidecar, non chiama AI se uscite non sane; dopo DeepSeek e prima di execute_paper fa check aggiornato per non aprire se il sidecar è caduto. Testata solo in sandbox; su runner originale patch dry-run e git apply --check PASS.

## Prove
1.188 PASS in 12.11 s su copia e25 con patch opt-in temporanea; zero fallimenti. 1.176 PASS in 12.38 s sulla stessa baseline ripristinata (senza patch, solo modulo/test nuovi). Due processi reali: lock esclusivo, chiusura per stop e manuale mentre un thread AI simula blocco; un solo paper_close per posizione.
Smoke temporizzato reale con model mock in attesa per 30 sec: close manual in 5.022 sec in quel trial, confermato UNA chiusura, AI ancora in attesa. NON è SLA della VPS. La suite completa backend/tests/test_v3_*.py è stata tentata ma è scaduta dopo 200 s intorno al 21%: NON considerarla PASS, nessun test fallito osservato nel log parziale.

## P0 ancora aperti
Prototipo NON montato in wiring e senza entrypoint o watchdog/restart del processo. Se il sidecar muore, le nuove aperture si possono bloccare con guard ma le posizioni PAPER già aperte perderebbero monitor finché non torna: NON è un rilascio pronto.
Serve handover con un solo proprietario dei file close_request/.work. Prima di ogni OPEN dopo l'attesa AI serve rivalutare anche mandato, pausa, budget, daily-loss latched e rischio corrente, oltre a salute sidecar. Patch di exit su cycle.py va integrata manualmente con la patch S1b di Claude. Runner.run fallback tick_failed -> running rimane P1 aperto. Dashboard PR61 + S0/S1/S2 non integrati.
Non eseguiti su VPS/Bitget/DeepSeek; nessun Jest/CRA o CI Py3.10/3.11, nessuna prova restart Docker/systemd.

## File salvati nella Libreria /SuperBot-Trading
SuperBot-V3-Exit-Service-Indipendente-Gate-P0-2026-11-06.zip SHA256 8a18248c7f6a9b0b67874a778c280ff7df5405ec8ff654c22923fcff02726da0 (libfile_46763d916ef48191b24747b5af0a6b4f)
RAPPORTO_SUPERBOT_V3_EXIT_SERVICE_P0_2026-11-06.md SHA256 8e299f670350627dadcc7ca6adfaaa0ebdbac2362924385a51a41ba2955188e9 (libfile_e97dee70e3108191b1a5c6dfce3a7c8a)
SUPERBOT_EXIT_SERVICE_HANDOFF_CLAUDE_2026-11-06.md SHA256 1b2a393c01af5b355aaf81cbe4eff05eea33fd42373992961b7c177abcad98ac (libfile_afc27c110d3081918da10e76f323a11c).

Next: review Claude per wiring/entrypoint separate process, monitor restart e cutover, risk post-AI, union with S1b + PR57/61, full CI, prova su VPS PAPER solo con consenso utente. Parametri invariati: 2% per trade, 5% open-risk, warn 35%, halt 50%, equity floor 450 USDT. Nessun reset storico; niente sizing 43%.