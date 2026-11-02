# 2026-11-02 — Autorizzazione esplicita utente: fermare solo il Pool per backup, lasciare fermo

L'utente, rispondendo alla domanda specifica, ha scritto: «sei sei autorizzato.»

**Mandato autorizzato**: arrestare temporaneamente **soltanto** il container `superbot-pool`, effettuare un backup consistente e verificabile di `/opt/superbot-pool-data` (SQLite e candele) e **lasciare il Pool fermo** in attesa di una successiva decisione di rilascio/riavvio. La policy del container rilevata è `unless-stopped`. Spazio disponibile 32 GB; dati 17 MB; volume dati `/opt/superbot-pool-data -> /app/data/pool`. Volume separato `/opt/superbot/data -> /app/botdata` non va modificato.

**Non autorizzati**: fermare Falco/Toro, modificare l'operatività Brain o le sue pause, cancellare o riscrivere dati, forzare chiusura OPEN ADA paper, cambiare il journal o disattivare immutabilità, fare merge/deploy della PR #28, effettuare ordini o usare chiavi. Backup deve includere eventuali sidecar SQLite e tutte le candele, hash archivio, prova di estrazione in cartella diversa, confronti file e PRAGMA integrity_check su copia.

**Stato**: ChatGPT non dispone di collegamento SSH diretto alla VPS in questa conversazione; non ha quindi ancora eseguito stop o backup. Fornire un comando unico da incollare in Termius e attendere il risultato dal titolare prima di attestare l'esecuzione.

Contesto: Pool `running/unhealthy`, errore ripetuto `ImmutableTradeError` su XRP `CTL_S2_top10`; 291/291 closed PAPER in audit compatibili, 1 OPEN ADA SHORT paper; PR #28 DRAFT, test 69/69 PASS, non deployata.
AI: ChatGPT.
