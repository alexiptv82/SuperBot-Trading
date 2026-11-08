# RC80 — Seconda revisione indipendente ChatGPT, 8 novembre 2026

**Esito:** SHA nuovo verificato `b64519346cbe0c928cd29d3e9d57c619b472ac78` nella [PR Draft #77](https://github.com/alexiptv82/SuperBot-Trading/pull/77), base invariata sulla PR #75 `b6eaa173c12c241647f89f730e1430a841cade3a`. Nessun merge/deploy/intervento VPS. Nessun workflow run GitHub associato all'HEAD.

**Rilievi pregressi:** P0-A lock `flock` correttamente implementato con test multiprocesso; P0-B identità posizione include `open_ms` e non accetta chiusure parziali come finali; P1-C barre 1m ammesse solo a età 60–120 secondi, modello close-only dichiarato e wick senza fill; P1-D failure di telemetria blocca chiusura, funzione d'allarme prevista, ma UI non ancora collegata. Le correzioni sono verificabili sul sorgente. Test locali dichiarati dall'autore, non ricertificati indipendentemente; nessuna CI remota.

**Due nuove condizioni bloccanti:** (1) `inspect_claims` testa indipendentemente esistenza del record terminale in history e learning, senza verificare identico `close_ms`/esito tra le due fonti: può archiviare claim falso in caso di registri discordanti. (2) `verify_snapshot` nel preflight di avvio richiede copia byte-identica a dati originali; dopo una chiusura i dati cambiano e restart con snapshot iniziale viene rifiutato prima di riconciliare il claim. Il test esistente copia a mano i nuovi file nello snapshot tramite `_refresh`, e quindi non copre la continuità in crash/restart. Serve protocollo di snapshot/restore verificabile che conservi RC69/RC77 e test con due posizioni (una chiusa e una da sorvegliare).

**Revisione dettagliata e richiesta patch mirata:** https://github.com/alexiptv82/SuperBot-Trading/pull/77#issuecomment-6720701115 .

**Gate residui rilascio:** monitor OFF di default; backend/dashboard devono esporre copertura effettiva, stale/blind/partial e il limite stop close-only. Backup esterno non certificato. Brain manual close PR #74 non deployato. Ultimo audit VPS disponibile RC77 Falco/Toro 0 PAPER aperte, Brain PAUSED. Nessuna nuova run 1000/1000/2000. Nessun test end-to-end VPS eseguito qui. Priorità P0-E/F prima di ulteriori feature.
