# SuperBot V3 — ripresa chat e riparazione puntatore Libreria
Data: 2026-11-07 (Europe/Rome) · DOCUMENTAZIONE SOLTANTO · PAPER

## Intervento effettuato dopo la chat interrotta
- Recuperati e verificati il checkpoint master `diario/2026-11-07_chatgpt-rc69-rc74-checkpoint-completo.md`, `STATO.md` del ramo `diario`, [PR #73](https://github.com/alexiptv82/SuperBot-Trading/pull/73) e [PR #74](https://github.com/alexiptv82/SuperBot-Trading/pull/74).
- La Library aveva **una copia recente** `/SuperBot-Ripresa/CHECKPOINT-SUPERBOT-V3-2026-11-07-RC69-RC74.md` (pubblicata il 7/11), ma il puntatore principale `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md` era fermo al 6/11 e mancava del checkpoint RC69–RC74.
- Riparato e verificato il file **esistente** `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md` in Library, mantenendo lo stesso ID stabile `libfile_754adf32b63881919d64ef3bc26b222a` e avanzando da versione **40 a 41**. In testa inserito indice 7/11 + link alla fonte master; archivio preesistente conservato integralmente. Esito upload: `succeeded / File overwritten`, verificato rileggendo le prime righe e la versione 41 dal catalogo Library.
- Non sono state copiate chiavi, JWT, password o API token nei documenti.

## Stato dei componenti (da PR/diario, non da nuovo audit VPS)
- App web V3 e `Chiudi ora` individuale Falco/Toro: distribuiti in RC73; l'utente ha dichiarato che il test da Android ha funzionato. I due servizi PAPER exit-only erano attivi all'ultimo audit, vecchi motori di trading fermi. **Non supporre ancora 6 Falco + 2 Toro**, perché il test dell'utente ha modificato almeno una posizione: occorre audit *read-only* post-clic.
- Chiusura manuale Brain: [PR #74](https://github.com/alexiptv82/SuperBot-Trading/pull/74), `work/v3-rc74-brain-single-manual-close-20261107`, testata offline (181 backend e 87 frontend PASS, build PASS, regressione V3 4.173 PASS/1 SKIP + 114 executor PASS), ma **non deployata**, Brain 2.000 PAPER PAUSED senza trade del nuovo ciclo. Non azionare sidecar senza owner/lock/lease/run_id e percorsi IPC rigorosamente allineati. Niente trade finti.
- Le PR #73/#74 restano DRAFT/non unite; il deploy precedente proviene da branch pin. Backup **locale** RC69 verificato ma precedente il clic utente; backup **esterno off-host non certificato**.
- Nuova run PAPER *prevista e non inizializzata*: Falco 1000 USDT, Toro 1000, Brain 2000, storici conservati. Classic Falco/Toro devono mantenere SHORT e consultazione Claude originali; LONG/trend incrementali. Brain osserva in lettura i classici.

## Prossimo lavoro
1. Audit VPS **esclusivamente read-only**: verificare posizioni ancora aperte e chiuse dopo il clic Android, P&L/commissioni e journal, modalità PAPER, stato web/worker e backup; mai chiudere posizioni da assistant.
2. Se consistenti, produrre **nuovo snapshot post-clic** e restore isolato con autorizzazione, senza sostituire RC69.
3. Per Brain progettare/collaudare in ambiente sintetico la corretta attivazione `exit_worker` con owner unico e IPC `close_request.json` / `close_result.json` nel run corretto: attivazione su VPS **solo con specifico OK**.
4. Qualsiasi reset, avvio trading, modifica VPS, merge o nuova apertura richiede autorizzazione separata. Non dichiarare completato un collaudo live non effettuato.

## Ripresa rapida da qualunque chat o altra AI
Leggere per primo `diario/2026-11-07_chatgpt-rc69-rc74-checkpoint-completo.md`, quindi `STATO.md`, PR #73/#74 e Library `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md` v41. Procedere solo con inventario read-only post-test, preservando memoria, backup, cronologia e PAPER.
