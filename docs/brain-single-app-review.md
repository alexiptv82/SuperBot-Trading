# PWA conto Brain unico — 30 ottobre 2026

Base applicazione preservata: 9251e6ddf2d68b607fffd73b8383da8f00c687fa.
Contratto produttore verificato: a472c5327e8f9334c5677f5243c28095282faed2.
Ramo separato: work/brain-single-app-20261030. Nessun merge o deploy.

La GET autenticata /api/brain/scalp legge ora snapshot PAPER v1 dual oppure
v2 con identita' brain-scalp-single-paper. Proietta un solo profilo brain per
v2, senza sommare Hawk e Bull. Capitale iniziale e slot provengono dal mandato
pubblicato, non da costanti della pagina. PnL ricalcolato come equity meno
capitale iniziale; equity ignota resta ignota.

BRAIN_SCALP_LAYOUT=single va impostato al futuro rilascio insieme a
BRAIN_SCALP_SNAPSHOT_PATH sul file pubblicato dal supervisore. In questa modalita'
lo snapshot assente mostra conto non avviato e NON legge i database dual.
Il default auto conserva compatibilita' col lettore dual precedente. Snapshot
esistente corrotto, identita' estranea, misto v1/v2 o schema inatteso falliscono
chiusi senza ripiego su SQLite. Nessun endpoint di comando aggiunto.

PWA: una scheda per il conto unico, capitale/slot del conto; conserva comportamento
storico/offline e recupero rete. Con dati storici non scrive "chiudendo ora".
Nessun saldo iniziale inventato quando il conto manca. Vecchie viste dual restano
compatibili; nessuna modifica al Brain precedente o ai classici.

Verifica: suite backend preesistente, nuovi casi v2/corruzione/staleness/fallback,
round-trip del vero produttore (checkout pin in CI), suite React con conto unico,
offline/recupero e nessun saldo inventato, build produzione. Nessun provider reale,
rete mercato o dato operativo usato. Il test usa un conto effimero PAPER.

Restano per rilascio complessivo: mandato finanziario unico definitivo, feed e
trasporti con timeout/tetti token/budget verificati, eventuale migrazione esplicita
con backup e riconciliazione, integrazione dei due rami e autorizzazione deploy.
Non affermare che il servizio H24 sia attivo o che un nuovo edge LONG sia provato.
Rollback codice con nuova revert, mai riscrittura storia o reset portafogli.
