# 11/11/2026 — Brain Fable 5.2 secondo cervello: PR Draft #82, budget 5 USD/mese, NO DEPLOY

**Decisione dell'utente:** accettata proposta «DeepSeek principale + Fable 5.2 come consulente occasionale, massimo 5 USD/mese». Dopo «sì, sono d'accordo procedi!» è stata implementata una **prima fase SHADOW**, senza promuovere Fable ad autorità di trading.

## Evidenza tecnica verificata

- Anthropic ufficiale: `claude-fable-5-2`, prezzi 8 USD / milione input, 40 USD / milione output; `output_config.effort=low` supportato. Fonti: https://platform.claude.com/docs/en/models/fable-5-2/overview e https://platform.claude.com/docs/en/build-with-claude/effort.
- **PR Draft #82**: https://github.com/alexiptv82/SuperBot-Trading/pull/82, branch `work/brain-fable-shadow-budget-20261111`, base `work/rc84-provider-credit-and-manual-close-20261111`, HEAD al momento creazione `3f30912dc67f51020bc3f18c04f5ed7d5c363472`.
- Nuovo `backend/v3/runner/fable_shadow.py`: ledger SQLite persistente (eventi append-only per osservazioni, prenotazioni e risultati Fable), budget Fable dedicato e **condiviso tra tutte le run Brain** su `/opt/superbot-v3-fable-ledger/fable_budget.db` (non si azzera alla ripartenza). Prima di ogni richiesta riserva un costo massimo prudente e atomico; totale mensile UTC massimo 5.000.000 microUSD, nessun rimborso su fallimento. Max 2 richieste/giorno, 6h cooldown per asset, dedup. Rileva cambio regime, OPEN VOLATILE, leva >=40x o confidenza <=0,62; nessuna consultazione per eventi ordinari. `max_tokens=1536`, effort low.
- `backend/v3/runner/wiring.py`: DeepSeek resta analista principale; wrapper SHADOW chiama Fable, salva solo classificazione + sintesi limitata, restituisce **identico oggetto di decisione DeepSeek** (non può aprire/chiudere trade, cambiare leva/stop/size né sostituire il motore). Con errore provider/ledger ignora il consulente, senza bloccare la strategia DeepSeek.
- **Default completamente OFF**: due flag separati `BRAIN_FABLE_SHADOW=1` e `BRAIN_FABLE_BUDGET_APPROVED=1` necessari, oltre a PAPER+sidecar e chiave Anthropic sicura sul processo Brain. Il programma già sulla VPS **NON** ha questi flag né il nuovo codice; nessun deploy, merge, service restart, lettura di chiave o modello chiamato. NON è stata collegata la chiave Claude di Falco/Toro a Brain.
- Runbook `docs/v3/BRAIN-FABLE-SHADOW-5USD-20261111.md` sul ramo.
- **Test offline** [Actions #43025542149](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43025542149) **SUCCESS: 9 pytest PASS in 0,14s**, sintassi AST valida; nessun accesso VPS, nessuna chiamata Claude, nessun nuovo costo AI.

## Limiti e prossima fase

- I 5 USD sono un **tetto applicativo del nuovo modulo Fable**, con prenotazioni conservative in mese UTC. **Non** includono i consumi Claude dei classici Falco/Toro né DeepSeek. La fatturazione Claude Console resta condivisa e indipendente.
- La consulenza Fable è **solo SHADOW**: per ora le sue opinioni non intervengono direttamente nelle decisioni, permettendo un confronto prima di introdurre qualsiasi effetto sulla strategia. Non dichiarare benefici finanziari senza prova.
- Non ancora presente un riepilogo costi Fable nella UI né un'analisi automatica retrospettiva su perdite pesanti: si potrà derivare dal ledger e dal journal quando ci saranno dati PAPER realmente nuovi.
- Prima del futuro rilascio: revisionare criticità, proteggere nuova directory DB condivisa mode 0700, montarla in RW soltanto nel Brain runner (systemd ProtectSystem), usare la chiave Anthropic solo in memoria Brain tramite EnvironmentFile protetto, mantenere limiti rischio/mandato invariati, preparare rollback, **richiedere autorizzazione distinta per deploy e attivazione delle richieste AI**. Il mandato Brain resta `approved=false` e i bot PAPER in pausa.
- Utente nel frattempo ha mostrato evidenza Termius che la **nuova chiave Claude per Falco/Toro** è stata accettata (`RC84_CLAUDE_REKEY_COMPLETED=PASS`), senza condividere il segreto. DeepSeek saldo disponibile dall'ultimo controllo. Restano da completare i «Chiudi ora» singoli e l'autorizzazione all'avvio PAPER dei tre motori; Fable NON deve bloccarli.

**Nessuna modifica operativa sulla VPS in questo incarico.** Il lavoro finisce come proposta GitHub pronta per revisione, non come motore già in esercizio.
