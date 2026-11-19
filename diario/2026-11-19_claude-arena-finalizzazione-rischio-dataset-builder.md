# Checkpoint Claude Code — 19/11/2026: finalizzazione anticipata Arena, rischio MiniMax, Training Dataset Builder

Autore: Claude Code (laboratorio, utente non-root). Riferimento: Issue #113 (decisione del 19/11/2026 10:20: Brain Unico prioritario, Arena non bloccante). **Nessun dato reale letto, nessun servizio toccato, nessun merge/deploy, nessuna esecuzione privilegiata.** Tutti i test sono sintetici e non sono stati replicati da ChatGPT.

## Branch pubblicati (tutti `claude/*`, base indicata, nessun file in `.github/`)

| Branch | SHA | Base | Contenuto |
|---|---|---|---|
| `claude/brain-unico-fase0-conclusion-20261119` | `ad6d2f1888cc976fb50c84d215868f5a071d6f9e` | `claude/brain-unico-fase0-sealed-20261119` (`9bf08ac…`, PR #116) | audit dei limiti di rischio (`risk_audit.py`), comandi `status` e `stop-openings`, `full --groups`, procedura di finalizzazione anticipata dell'Arena |
| `claude/brain-unico-training-dataset-20261119` | `ab1a38ac7c49239fcce8b446f0e408c1e08d2482` | `main` | Training Dataset Builder offline (schema v1), roadmap aggiornata |

SHA256 del nuovo bundle sigillato (`ops/brain-unico/sealed/phase0_sealed.py` al commit `ad6d2f1`): `358f47932e6a2b61d5131d541c09a25ac4021b94bc7a66b8025d8bf3794824b5`. **Il bundle precedente (`afcab6f7…`, PR #116) è sostituito da questo; nessuno dei due è stato eseguito.**

## Che cosa c'è di nuovo

- **Finalizzazione anticipata dell'Arena** (`docs/v3/BRAIN-UNICO-ARENA-FINALIZZAZIONE-ANTICIPATA-20261119.md`): si fermano **solo** i tre runner (SIGTERM ordinato), le uscite restano attive e chiudono le posizioni con le regole normali (stop, take-profit a 2R, durata massima 24 h): nessuna chiusura manuale, quindi esiti non contaminati. `stop-openings` ha whitelist esatta, è idempotente, non ferma nulla se un'uscita non è attiva o systemd non risponde, e `[]` non significa "tutti". Riporta `ended_early_reason` e la durata effettiva (`arena_window`): non confrontare come gara da 72 h.
- **Rischio MiniMax**: la perdita riferita dall'utente non è certificata (journal di root, non leggibili dall'agente). Con la politica configurata (tetto 4,29 % del capitale per posizione, blocco giornaliero al 50 %, capitale minimo 450) una perdita del 40 % è **compatibile con i limiti**: non prova un guasto dei gate. `risk_audit` lo verifica dal journal (copia) e riporta solo numeri; il blocco giornaliero è un limite inferiore (solo realizzato). Verifica proposta: `status`, poi `full --groups arena_minimax`; blocco delle sole nuove aperture di MiniMax **solo se** compaiono `hard_flags`.
- **Training Dataset Builder** (`docs/v3/BRAIN-UNICO-TRAINING-DATASET-BUILDER-20261119.md`): una riga per decisione (eseguita, rifiutata, NO_TRADE) con feature, esito, etichette forward e provenienza; perdite, NO_TRADE, rifiuti, chiusure manuali e posizioni aperte restano; duplicati marcati e non cancellati; nessun testo libero; feature solo da candele chiuse; nessuna interpolazione; split cronologici con embargo/purging; soglie di sufficienza dell'utente (≥300/20 gg shadow offline, ≥1000/45 gg per considerare la promozione).
- **Difetto strutturale emerso**: il journal V3 (Brain e Arena) **non salva le feature al momento della decisione né MFE/MAE né funding**, e un rifiuto non registra lato né prezzo. Per V3 vanno ricostruiti da candele (marcato `reconstructed_from_candles`). Requisito per il Brain Unico: log in avanti (schema v2), descritto nel documento del builder.

## Verifica (sintetica, non replicata da ChatGPT)

61 test del bundle, 90 di Fase 0, 17 dell'audit di rischio, 29 di inventory (branch `conclusion`); 54 del dataset builder. Per mutazione: 18 su 18 (bundle e audit) e 30 su 30 (builder) difetti reintrodotti sono rilevati. Bug trovati dai test e corretti: lista vuota di provider/gruppi trattata come "tutti".

## Non fatto / richiede consenso separato

Esecuzione del bundle come root (passi `status`, `full`, `stop-openings`); qualunque stop di runner; snapshot reale; lettura di journal/DB; prima esecuzione reale del builder (serve una copia verificata; schema del Brain storico da verificare); cache di candele da fonte pubblica; lettore delle annotazioni manuali dell'Arena; copia esterna cifrata (progetto soltanto). `superbot-extbackup` resta `inactive/dead`: non attivato.

## Dove leggere

Branch `claude/brain-unico-fase0-conclusion-20261119` (`docs/v3/BRAIN-UNICO-ARENA-FINALIZZAZIONE-ANTICIPATA-20261119.md`, `docs/v3/BRAIN-UNICO-FASE0-PROCEDURA-OPERATORE-20261119.md`) e `claude/brain-unico-training-dataset-20261119` (`docs/v3/BRAIN-UNICO-TRAINING-DATASET-BUILDER-20261119.md`, `docs/v3/BRAIN-UNICO-ROADMAP-AGGIORNATA-20261119.md`). La PR draft di ciascun branch non è stata aperta da Claude (il connettore non ha permessi di scrittura sulle PR): se ne occupa ChatGPT.
