# 2026-11-23 — Interruzione Claude 529 durante sviluppo Guardian e profili scalp

## Provenienza e attendibilità
- Il proprietario ha incollato un log narrativo di Claude Code terminato con `API Error: 529 Overloaded`. Non è un errore di test né prova di danneggiamento del codice.
- Da verifica GitHub al momento di questo checkpoint, il branch remoto `claude/falco-evoluto-20261123` è ancora a `a6661a0d6ab184af4f68722c7c19ba0ba3b290cf`; nessuna delle modifiche più recenti risulta pubblicata su quel ramo. Potrebbero essere modifiche locali non committate nella workspace Claude/VPS.

## Avanzamento DICHIARATO da Claude nel log (non verificato sui file locali)
- Non dispone di root: sudo richiede password e run Brain RC1 root-only 0700. Non ha attestato il file pausa, quindi stato pausa RC1 resta ignoto.
- Letto proposal Guardian, E0, thesis, rischio, DailyLossGuard, runner. RiskManager aggiunta gestione leva/margini minimi, posizioni massime e rischio guardian; policy hash nuovo solo dove necessario. Schema 2 runner_config in sviluppo con `analyst`, `exit_policy`, `guardian` (schema 1 invariato).
- Modulo Smart Guardian puro ricostruisce MTM, picco, floor e rischio aperto; LOCKED fino a reset dopo rottura floor o perdita sessione; sessione Europe/Rome. Claude dichiara 12 test Guardian PASS; 1.224 test regressione PASS (due file fuori gate non eseguiti per dipendenza cryptography mancante). Questi numeri sono riportati dal log, non certificati indipendentemente.
- Integrazione exit_worker per politica uscite per-run + `stop_kind` opzionale in evento chiusura era IN CORSO al momento del 529; non dichiarare conclusa.
- Mancano conferme di completamento analista Falco LONG/SHORT, AI occasionale, nuova run Brain Scalp, confronto dashboard, commit, pubblicazione branch.

## Ripresa richiesta a Claude
1. Nella stessa workspace: prima `git status`, `git diff --stat`, `git diff --check`, branch/HEAD e inventario file modificati; verificare che le modifiche locali esistano.
2. Fare checkpoint non distruttivo delle modifiche esistenti (branch isolato; preservare WIP; no reset/clean/pull distruttivo o sovrascritture). Ri-eseguire test realmente pertinenti e indicare gate parziali.
3. Completare wiring schema2, exit worker e journal stop_kind, test di backward compatibility schema1 e safety. Poi analista Falco Evoluto, AI occasionale, nuove configurazioni e UI confronto; no deployment.
4. L'utente vuole Claude operativo via VPS quando autorizzato, non uso ripetuto Termius; sudo root assente, raggruppare un solo controllo root eventuale alla fine. Pausa Brain RC1 non certificata.
5. Non riavviare Brain, Falco, Toro, Arena, non approvare mandati, non usare real, non fare merge/deploy senza approvazione.

## Decisioni progettuali già consolidate
- Falco Evoluto PAPER 1.000 USDT, Brain Scalp PAPER 2.000, leva min15 max45, margini Falco100-250 Brain250-450, 4 slot max, NO_TRADE consentito.
- Proposta rischio dinamico max 4% equity/trade e max 20% margine, max 10% equity rischio aggregato, stop nuove aperture -8% sessione (da testare), senza aggirare floor e limiti margin.
- Uscite previste 3R, break-even +1R, trailing da +1,5R distanza1R; Profit Guardian prioritario floor mobile/giveback con percentuali, reingresso e stati NORMAL/SELECTIVE/PROTECTED/LOCKED, reset ore08 Europe/Rome senza forzare chiusure.
- Prompt consolidato dell'utente resta valido, il 529 non modifica i requisiti.