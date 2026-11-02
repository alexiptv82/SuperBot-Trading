# 2026-11-02 13:49 Europe/Rome — Pool backup preflight, solo lettura

## Screenshot Termius
Il titolare ha eseguito verifiche preliminari sulla VPS Singapore e mostrato:
- Mount di `superbot-pool`: `/opt/superbot/data -> /app/botdata` e `/opt/superbot-pool-data -> /app/data/pool`.
- `du -sh /opt/superbot-pool-data`: `17M`.
- `df -h /opt/superbot-pool-data`: `/dev/sda1`, size 38G, used 5.9G, avail 32G, use 16%.
- Policy riavvio container: `unless-stopped`.
- `PREFLIGHT_COMPLETATO`.

## Diagnosi confermata
Il Pool rimane `running/unhealthy` e i log recenti reiterano `ImmutableTradeError` su `CTL_S2_top10` XRP (`exit_t`) dopo che il diario ha contato 291/291 closed PAPER compatibili nel replay. Un OPEN PAPER virtuale SHORT su ADA/USDT (2026-11-02 07:00 UTC) è documentato. La PR #28 corregge il next-open Donchian oltre il limite 48h, con 69 test CI PASS ma non è ancora unita né distribuita.

## Prossima procedura proposta (NON ancora eseguita)
Richiedere autorizzazione esplicita a fermare **soltanto** `superbot-pool` per creare backup consistente dell'intera `/opt/superbot-pool-data`, con verifica archivio, hash, test estrazione e `PRAGMA integrity_check` sulla COPIA, senza alterare `pool.db`, cache, contatori o posizioni. Fino al rilascio concordato, valutare mantenere il solo Pool fermo anziché rieseguire un ciclo fallente. Un docker stop esplicito con restart `unless-stopped` non impone il riavvio immediato, ma la policy/riavvii VPS va verificata al momento della procedura. Non eseguire merge/deploy PR #28 senza ulteriore consenso.
Non toccare `/opt/superbot/data`, Falco, Toro, Brain, AI Shadow, altre pause, portafogli, protezione 450 USDT.

**Stato**: soltanto preflight read-only completato; nessun backup, stop, restart, merge, deploy effettuato in questa chat.
AI: ChatGPT — ripresa progetto.
