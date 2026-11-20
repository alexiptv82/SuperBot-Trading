# Addendum al checkpoint verificabile — 20/11/2026 08:46 Europe/Rome

Questo addendum completa, senza modificare retroattivamente, il checkpoint `2026-11-20_0843_checkpoint-seconda-acquisizione-feed-brain-unico.md`. Durante la verifica finale di `STATO.md` è risultata accessibile la voce Claude (5), commit diario `28d22b008269e642fdc3ec6585549cdde0ec62ec`.

## Correzioni e integrazioni verificate

- La correzione del validatore al commit `733182f6e3e8760aaf900c24215f51e8ed380154` dispone di una suite completa dichiarata: **V3 5.311, builder 157, Jest 137, zero fallimenti**, pubblicata tramite gate. Sostituisce l'indicazione prudenziale del checkpoint 08:43 secondo cui la suite completa su questo SHA non era ancora documentata.
- Esiste un ramo isolato `claude/skills-brain-unico-20261120` @ `0ce8adf8`, derivato da `integration/brain-unico-20261119` @ `8fa61d18`, con 32 file aggiunti: cinque skill adattate, licenza/provenienza e documentazione.
- Le cinque selezionate sono: exit-strategies, risk-management, position-sizing, trade-journal e walk-forward-validation.
- Il confronto offline riferisce utilità per exit/risk/position/walk-forward, ma segnala formula Deflated Sharpe Ratio errata nella skill walk-forward e basso valore del formato trade-journal perché in conflitto con EventJournal. Nessuna skill ha corretto l'analisi di base.
- Il ramo delle skill **non è integrato** nel ramo laboratorio né in main; il riconoscimento resta non verificato (`Unknown skill`) e richiede una nuova sessione o reload esplicito del proprietario.
- Il ramo originario con dieci skill resta solo riferimento. Nessuno script/dipendenza eseguito o installato, nessun deploy/servizio/parametro/spesa/LIVE.

Tutto il resto del checkpoint 08:43 resta valido: archivio integro ma non attestato finché l'anchor non è registrato; fix feed offline da provare con probe autorizzato massimo 3 tentativi; RC PAPER e backup esterno soltanto preparati; copia age verificata localmente ma non prova VPS; trading esclusivamente PAPER.
