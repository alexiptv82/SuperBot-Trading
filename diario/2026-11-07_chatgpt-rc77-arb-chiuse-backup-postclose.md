# SuperBot V3 — RC77: ARB manuali chiuse, riconciliazione e backup locale post-close

**7 novembre 2026, circa 19:59 CET** · **Evidenze VPS Singapore**, PAPER esclusivamente.

## Audit post-click utente
L'utente ha confermato di aver premuto personalmente "Chiudi ora" su entrambi i trade ARB. [GitHub Actions RC77 audit READ ONLY SUCCESS](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42403639118) (18:55 UTC) ha confermato:
- **Falco: 0 aperte; Toro: 0 aperte**. Nessuna richiesta `close_position.flag` in attesa, unità manual-exit con heartbeat fresco, container legacy spenti, modalità web PAPER; Brain PAUSED.
- Falco ARB id 62, SHORT 25x, `closed_by=utente`, `manual_learning=loss_reduction_example`, `source=rules`, prezzo entrata `0.160507892`, uscita `0.16818363`, **gross -119,5539**, fee **3,0717**, **net -122,6256 USDT PAPER**, `open_ms=1793602540218`, `close_ms=1794077580552`.
- Toro ARB id 19, stessa entrata/uscita e leva, `closed_by=utente`, `manual_learning=loss_reduction_example`, **gross -221,1747**, fee **5,6827**, **net -226,8574 USDT PAPER**, `open_ms=1793602539893`, `close_ms=1794077589285`.
- **Totale ARB:** perdita netta **-349,4830 USDT PAPER**, fee **8,7544**; le 6 precedenti chiusure manuali positive del 7/11 erano +782,9613 net; somma delle 8 chiusure manuali **+433,4783 USDT PAPER** (Falco **+506,2913**, Toro **-72,8130**). NON è l'equity corrente o un profitto reale Bitget.
- Variazione di ARB dall'ingresso al prezzo di uscita: +4,78% contro due SHORT, gross loss circa 119,55% dei rispettivi margini per entrambi. L'uscita `0.16818363` è sopra lo stop `0.162574857` e sopra il livello teorico di liquidazione `0.166125668`. **Non dedurre automaticamente che uno stop sia stato attraversato in un istante preciso senza serie temporale affidabile**, ma confermare il gap operativo: il servizio exit-only della RC73 non monitora SL/TP e i vecchi worker sono OFF. Inoltre è un **gap di simulazione/floor/liquidazione PAPER** se il simulatore permette perdita superiore al margine senza gestione: P0 da investigare e correggere prima della nuova run. Le quote di rischio restano protette, non modificare né riavviare per prova.
- Le chiusure manuali sono esempi di riduzione di perdita, non segnali da usare per modificare automaticamente l'algoritmo.

## Backup dopo le 8 chiusure, eseguito con consenso utente
- Ramo di lavoro isolato [RC77](https://github.com/alexiptv82/SuperBot-Trading/tree/work/v3-rc77-post-arb-close-backup-20261107), senza merge/deploy: script `deploy/scripts/v3-rc77-local-snapshot-restore.py`, workflow `v3-rc77-local-snapshot-postclose.yml`. Derivato dai controlli fail-closed RC69 con attesi **0/0** e prova esplicita delle due chiusure ARB manuali da storico.
- **[Run backup #42403863492 SUCCESS](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42403863492)**. Nuova directory **`/opt/superbot-backups/rc77-paper-legacy-20261107T185803Z-331904`** con manifesto `rc77-paper-local-snapshot-v1` e hashes per **37 file Falco + 35 Toro**. Sono esclusi dal backup i file effimeri di heartbeat e lock del worker exit-only, non le transazioni/storici/lezioni. **0 posizioni** in entrambe le copie. Hash SHA-256 e copia coerente con origine, **restore isolato realmente eseguito e PASS**, originali invariati; nessun Docker restart.
- **[Audit indipendente #42403956859 SUCCESS](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42403956859)**: SHA di manifest e 37+35 file nel nuovo snapshot confrontati di nuovo con i sorgenti, `RC77_VERIFICATION=PASS`, 1 snapshot RC77 valido; verifica read-only.
- Snapshot **RC69 antecedente alle chiusure** mai sovrascritto. Nuovo backup **locale sullo stesso VPS**, NON off-host. Servizio backup esterno `superbot-extbackup.service` ancora errore `exit-code`; **non dichiarare certificato offsite**.
- Nessuna azione trading, reset, merge, deploy, riavvio, cambio soglie/strategia, API pagata, credenziali o live. Nessuna modifica ai dati originali VPS se non nuova directory di backup.

## Prossimi passi / gate non superati
1. Preparare in ramo isolato diagnosi post-trade read-only per **Falco/Toro/Brain**, leggendo `close_by`, `open_ms`, id posizione, MFE/MAE solo se misurabili, comparazione di entrate e protezione, distinguendo cause provate vs non dimostrate. Aggregare chiusure parziali per id run + posizione (Toro ARB storico aveva 4 fill profittabili di un solo trade).
2. **P0** prima della nuova run: sidecar SL/TP indipendente e testato per tutte le posizioni PAPER anche con scanner/AI in pausa, monitor pause/timeout, gestione coerente dello stop e liquidazione simulata; evitare worker duplice e scritture concurrenti. **NON riavviare i legacy**. La politica di sicurezza, size e stop richiede approvazione.
3. Brain manual-close PR #74 ancora offline e non deployata; collaudo isolamento sidecar/lease/run_id/IPC e backup/rollback, senza aprire trades artificiali.
4. Diagnosticare e riparare backup off-host, verificare restore esterno, prima di dichiarare pronta la ripartenza.
5. Solo dopo gate e OK esplicito separato: nuove run isolate PAPER Falco 1.000, Toro 1.000, Brain 2.000 USDT; preservare tutte le storie, Claude nei classici e loro SHORT originali, miglioramenti LONG/trend incrementali.

**Nota:** "chiuse entrambe" confermato dall'utente e da evidenza VPS, non dall'assistente mediante ordini. 
