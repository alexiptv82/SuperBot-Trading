# SuperBot V3 — 2026-11-03 — F0 backup recency preflight PR #34 DRAFT, 7/7 CI PASS Python 3.10/3.11

## Perché
La sentinella `.github/workflows/sg-extbackup-watch.yml` ha registrato nel suo ultimo job osservato [41447751395](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41447751395), del 2026-11-02, un archivio `superbot-backup-20261102T032845Z.tar.gz.age` con timestamp 2026-11-02T03:28:45Z. Una copia locale consistente Brain F0 è stata creata in data 2026-11-03 intorno alle 03:55Z; dichiarati 8.447 eventi. L'archivio del giorno precedente non dimostra di contenere la copia successiva; l'ultimo watcher disponibile non dimostra neppure assenza di backup più recenti.

## Sviluppo effettuato in questa sessione
- Branch `work/f0-external-backup-preflight-20261103` creato da `main` (SHA iniziale `fb38267433235780e5f22a335837139cf5ec4211`).
- [PR #34](https://github.com/alexiptv82/SuperBot-Trading/pull/34), **DRAFT**, HEAD `cdaa645688256b7ce65d772ba901d84628d85d9a`, base main, **nessun merge**.
- `ops/f0/offhost_preflight.py`: comando locale read-only non distribuito, eseguibile solamente da un operatore root su VPS previa distinta autorizzazione. Legge due JSON a percorsi FISSI: `/opt/superbot-extbackup/status.json` e `/opt/superbot-v3-backups/f0-brain-20261103T035500Z/manifest.json`. Output redatto con soli campi allowlist, senza errori raw, segreti, percorsi esterni o chiavi. Fa controlli di dimensione max 64 KiB, symlink final O_NOFOLLOW, schema snapshot, osservazioni e timestamp; **non apre DB, non apre age, non usa subprocess/network e non esegue backup**. Esito esplicito `externally_certified:false`, `archive_coverage_verified:false`, `restore_verified:false`, `external_storage_verified:false` sempre, anche se l'archivio risulta successivo allo snapshot.
- `ops/f0/test_offhost_preflight.py`: 7 fixture di test sintetiche positive/negative, inclusi segreto da non stampare, archivio predatato, archivio più recente che resta non certificato, JSON malformato, symlink, manifest mismatched, data errata, file oversized.
- `.github/workflows/f0-external-preflight-tests.yml` e `docs/v3/f0-external-backup-preflight-20261103.md` aggiunti. Nessuna modifica al vecchio workflow root-SSH.
- Il codice è stato eseguito e verificato localmente: 7/7 unittest PASS. Hash Git blob dei due sorgenti corrispondono esattamente ai sorgenti testati: script `e8db9f8a28b9b68b35bc70666ce2db93c8f72f30`, test `5f0cd37272bbf3a90eea1eb6d5d71db116be8c32`.
- GitHub Actions [run 41612288658](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41612288658): **SUCCESS** con Python 3.10 **7/7 PASS**, Python 3.11 **7/7 PASS**. CI non accede ad alcuna VPS o secret.

## Stato altre PR e prossimo gate
PR #29 V3 F1, PR #32 ACL Hawk/Bull, PR #33 Grok Brain F2, PR #34 preflight backup **tutte DRAFT e NON mergiate**. PR #33 HEAD `f8070966a8f0c79aa339a0582b0650d8cb1b85cc` include ticket tecnico per R1; i tre test `xfail` documentano rischi non corretti.

F0 backup storico offhost continua **NO-GO**: servono fonti dati reali, conferma destinazione esterna e contenuti archivio, chiave recuperabile, ripristino reale su altro host e verifica contro testimoni source-side. Lo script PR #34 è solo una verifica cronologica di metadati e NON un certificato.

**Nessun intervento server, ACL apply, riavvio, reset wallet, import storico, merge o deploy effettuato.** I bot restano fermi (stato non rieffettuato live in questa sessione). Evitare chiave SSH root legacy per operazioni nuove; preferire autorizzazioni distinte least-privilege.
