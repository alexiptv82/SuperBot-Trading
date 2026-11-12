# Checkpoint 12/11/2026, 20:44 Europe/Rome — RC84 fase 2 hardening finale, candidato congelato dc98413 per revisione Grok

## Novità verificata

Il ramo isolato `work/rc84-signals-mtf-closed-20261112` è avanzato dal candidato 2C `45b9f334...` al commit finale di hardening:

[`dc98413ee555c7f0aefeeca8a5367b41ba370c92`](https://github.com/alexiptv82/SuperBot-Trading/commit/dc98413ee555c7f0aefeeca8a5367b41ba370c92) — `fix(signals): hardening finale fase 2 ... [skip ci]`.

Il candidato è congelato per revisione indipendente Grok. Non è una release: nessun tag, PR associata, GitHub Action, merge, deploy, installazione VPS o modifica a pause, wallet, posizioni, rischi o strategie. La sorgente installata resta `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`.

## Hardening eseguito

### Conflitti dati fail-closed end-to-end

`backend/desk/cli.py::merge_bars` non sovrascrive più in silenzio due candele con lo stesso timestamp e valori diversi:

- duplicati identici vengono uniti;
- conflitti nella stessa risposta 4H, tra pagine 1Dutc o tra cache e download restano entrambi visibili a `signals.series_check`;
- la serie viene rifiutata, trend `UNKNOWN`, cache del simbolo/timeframe svuotata, attesa 30 minuti e ricostruzione;
- heartbeat `conflitto_dati`;
- conflitto 4H: nessuna nuova apertura sul simbolo; conflitto 1Dutc: contesto `UNKNOWN`, zero punti e nessun nuovo gate.

### Copertura recuperata

Le prove preesistenti sono state adattate ai contratti RC84 senza cambiare il comportamento operativo:

- Falco usa aperture `scalp`; Toro/S25 usa opt-in esplicito;
- DCA, stop/TP, svuotamento in pausa, ripresa, entrata diversificata e registro chiusure tornano coperti;
- claim irrisolto blocca davvero le aperture e la riconciliazione le sblocca;
- nessuna nuova esposizione nello stesso ciclo con claim pendente;
- S25 senza autorizzazione non apre ma continua a chiudere a tempo;
- heartbeat Brain include `last_cycle`; `GET /api/v3/brain/config` resta read-only;
- barriera comune azzera cache HTF tra test e impedisce rete Bitget involontaria.

File modificati verificati: `backend/desk/cli.py`; `backend/tests/conftest.py`, `rc84_test_support.py`, `test_desk.py`, `test_desk_rc84_hardening.py`, `test_desk_rc84_phase2b.py`, test RC82/RC84 claim/exposure/visibility/runner; documento `docs/v3/RC84-FASE2-MOTORE-SEGNALI.md`.

## Validazione e fonte

Fonte primaria: commit `dc98413...` e sezione 8D del documento versionato nel commit. Fonte complementare: messaggio recente recuperabile della conversazione del progetto.

| Esecuzione | Esito verificato/riportato |
|---|---:|
| Suite `backend/tests`, Python 3.13, esclusi due moduli che non si importano | **7.039 pass / 1 fail** |
| Fallimento residuo Python 3.13 | solo `test_v3_rc84_import_paths`, SQLAlchemy 2.0.28 incompatibile |
| Moduli SQLAlchemy, Python 3.11 + requirements | **49/49 PASS** sia su `ab7e0b7` sia sul candidato |
| Hardening nuovo | 11 prove end-to-end |
| Replay | 42 percorsi, identico bit per bit alla fase 2/2B |

Convalide aggiuntive documentate:

- EMA50/EMA200 4H e 1D identiche al calcolo indipendente `pandas ewm(adjust=False)`;
- candele 4H/15m in formazione con movimenti estremi non alterano la lettura;
- serie mancanti, interrotte o conflittuali → `UNKNOWN`;
- chiusure PAPER, stop, TP, DCA, storico e riconciliazione verdi nelle suite RC82/RC84;
- stesso segnale su due cicli apre una sola posizione; lo stesso segnale regole non apre anche su Toro.

Il singolo fail Python 3.13 è classificato come problema d'ambiente, non corretto nel prodotto: gli stessi moduli passano 49/49 con Python 3.11. Nessun test è stato rimosso per ottenere il risultato.

## Desiderato vs implementato

| Area | Stato |
|---|---|
| Barre chiuse, EMA200 vera, storico 1D paginato, continuità crypto | implementati nel candidato congelato; non rilasciati |
| Duplicati conflittuali | fail-closed end-to-end nel candidato |
| Protezioni DCA/claim/chiusure/riconciliazione | copertura recuperata |
| Calendario XAU/XAG e `4H&limit=1000` | restano da verificare read-only |
| Falco SHORT-only / Toro LONG+SHORT | roadmap separata, non implementata |
| Policy rischio P-1…P-5 | non applicate |
| Redditività reale | non provata; replay sintetico |

PR #90 resta Draft all'HEAD `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`; PR #91 resta Draft all'HEAD `500563a96db0e771f74a580b7278765eae0eaa92`. Nessuna delle due incorpora automaticamente il candidato congelato.

## Stato PAPER, backup e chiavi

Ultimo stato operativo documentato invariato: Falco/Toro sotto pausa RC84 in `draining`; Brain `paused`, exit `healthy`; tre pause e resume non autorizzato. Nessun controllo live VPS nuovo e conteggi correnti non noti.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore VPS. RC84 PR #80 resta riferimento storico. Nessun segreto letto o pubblicato.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito:** hardening candidato, recupero copertura e test locali; congelamento SHA per audit Grok; doppio checkpoint documentale.
- **Preparato:** candidato tecnico `dc98413...`.
- **Rilasciato:** nulla.
- **Non approvato/non eseguito:** tag, PR, merge, deploy, Actions, installazione o modifica VPS, restart/resume, reset, wallet, ordini, LIVE o API a pagamento.

## Blocker e ripresa

Attendere la revisione indipendente Grok. Prima di qualunque proposta di rilascio: verificare read-only calendario XAU/XAG e granularità/limiti `4H&limit=1000`; rieseguire i gate concordati sulla revisione esatta; mantenere separati candidato fase 2, audit PR #91 e roadmap Falco/Toro. Non creare tag, perché potrebbe avviare workflow. Preservare PAPER, pause, EventJournal, learning e storici. Non assumere chat eliminate o stato VPS successivo.
