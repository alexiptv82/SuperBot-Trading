# Brain AI Libero — revisione read-only 2026-10-27

Branch verificato: `work/brain-ai-libero` (`b197cdc79c9fa1932dcf190b822769eca8330d75`). Confronto contro `rule-pool` (`183fdb7b1bf25140d2d236c98e50262b5cd3411b`): rami divergenti, +6/-38 commit rispetto alla base comune; NON eseguire merge automatico dell'intera storia. Nuovo namespace `backend/director/brain_free`, workflow e Docker dedicati.

## Controlli confermati per ispezione del codice
- PAPER enforced da `Runtime` e dal preflight di rilascio; conto nuovo da 2000 USD, massimo 10 slot, 1600 USD di margine aggregato.
- `deploy/brain-free.trigger` disarmato (`action=none`, `approved=no`). Il workflow richiede autorizzazione esplicita e SHA immutabili.
- Ricostruzione conto da SQLite, writer esclusivo e vincolo sul digest/config; nessun reset implicito.
- Logica di stop su barre/quote separata dalle richieste AI; nessun fallback delle aperture a regole classiche.
- Rollout previsto con snapshot SQLite, check integrità, arresto dei tre container Brain precedenti e rollback dei soli Brain in caso di errore.

## Punti da verificare prima di autorizzare un deploy
1. **Nessun daily stop al 20%**: il nuovo Brain è deliberatamente privo di questo limite, come indicato nella specifica più recente e nei test. In tal senso NON promettere protezione del capitale residuo o tetto massimo alla perdita. Verificare che l'operatore approvi espressamente questo profilo di rischio.
2. **Versioni runtime**: il rollout contiene riferimenti rigidi per tre Brain precedenti e i classici. Confrontarli read-only con gli effettivi ID/SHA/container; non assumere che il solo codice nel repo rappresenti il VPS attivo.
3. **Dipendenza dalla dashboard**: il rollout richiede che la app abbia già montato il nuovo account in sola lettura. Serve revisione separata del branch dashboard e dei relativi test/backup.
4. **CI non certificata in questa revisione**: i test offline riportati dal documento candidato sono precedenti; non è stato eseguito alcun runner in questa sessione. Richiedere CI verde su SHA esatto, test di regressione e verifica del piano rollback prima del deploy.
5. **Limiti PAPER**: prezzi, funding e liquidazione sono simulazioni/approssimazioni. Validare schema feed Bitget su campioni pubblici; non rappresentare esiti paper come risultati live.
6. **Sicurezza del cutover**: confermare root vuota, backup restaurabile, vecchi account leggibili, nessun servizio classico toccato e nessuna doppia istanza.

## Esito
**REVIEW IN CORSO — DEPLOY NON AUTORIZZATO**. Nessun merge, nessun trigger, nessun accesso o intervento VPS eseguito in questa revisione. Un precedente confronto a livello file mostra 30 percorsi modificati/aggiunti nel branch del candidato; fare review della patch effettiva dopo una strategia esplicita di integrazione, senza portare accidentalmente commit estranei.

## CI della revisione
Questo aggiornamento documentale innesca una nuova esecuzione del workflow offline sul commit di revisione. Non autorizza rollout o deploy.
