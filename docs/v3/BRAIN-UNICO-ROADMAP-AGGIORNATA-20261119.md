# Brain Unico — roadmap aggiornata (19/11/2026, dopo la decisione "Brain Unico prioritario")

Decisione (Issue #113, 10:20): la gara Arena **non blocca** il Brain Unico. Si lavora in parallelo; l'Arena può essere conclusa prima delle 72 ore con una procedura ordinata che conserva tutto. Questa nota riassume i binari, le dipendenze e i consensi che servono. Nessuna delle attività descritte sotto è stata eseguita su dati o servizi reali.

## Binari paralleli

| Binario | Stato | Dove (branch) | Cosa serve per procedere |
|---|---|---|---|
| **A. Conservazione degli storici (opzione B)** | preparato e collaudato in laboratorio | `claude/brain-unico-fase0-sealed-20261119` (bundle sigillato), `…-conclusion-…` (audit rischio, status, stop-openings) | revisione di ChatGPT del bundle; consenso dell'operatore per eseguire come root |
| **B. Finalizzazione anticipata dell'Arena** | procedura e comandi pronti, **non eseguiti** | `claude/brain-unico-fase0-conclusion-20261119` | consenso esplicito per `stop-openings`; attesa ≤ 24 h per la chiusura naturale delle posizioni |
| **C. Training Dataset Builder** | implementato offline, 54 test sintetici | `claude/brain-unico-training-dataset-20261119` | copie verificate (da A) per la prima esecuzione reale; cache di candele |
| **D. Verifica dei limiti di rischio MiniMax** | strumento pronto (`risk_audit`) | `claude/brain-unico-fase0-conclusion-20261119` | `status` e `full --groups arena_minimax` (sola lettura / copia di un journal) |
| **E. Brain Unico (decisore, risk manager, UI)** | in attesa | — | storico preservato + dataset + audit di apprendimento |

## Ordine consigliato, senza attese inutili

1. **Subito, in parallelo**: revisione dei branch A/B/C da parte di ChatGPT (nessun costo operativo).
2. **Primo consenso operativo (basso rischio)**: `status` e `full --groups arena_minimax` → risponde alla domanda sui limiti di rischio e produce la prima copia verificata di un journal.
3. **Decisione sull'Arena**: se non serve più, `stop-openings` (solo runner; uscite attive) → attesa della chiusura naturale → `full` definitivo con `ended_early_reason`.
4. **Prima esecuzione reale del dataset builder** sulle copie (schema reale del Brain storico da verificare), poi `sufficiency`.
5. **Solo con campione sufficiente**: baseline e modello shadow offline; nessuna promozione senza approvazione.
6. **Brain Unico**: un solo portafoglio, DeepSeek decisore, risk manager deterministico, Falco SHORT solo advisory, con il log in avanti di schema v2 (vedi builder, §8) per non dover più ricostruire.

## Principi che restano

Nessun reset o cancellazione; nessun merge o deploy senza autorizzazione; il Brain storico resta spento; Falco e Toro restano spenti come runner; nessuna chiamata Claude dal Brain finché non è approvata; i dati reali non entrano mai nel repository (solo numeri e hash); `certifies_backup` resta falso finché non esiste una copia **fuori host** cifrata con prova di ripristino indipendente.

## Rischi da non perdere di vista

- Il regime di rischio dell'Arena è **permissivo per scelta** (blocco giornaliero al 50 %, capitale minimo 450): una perdita di −40 % è compatibile con i limiti. Il Brain Unico non deve ereditarlo senza decisione esplicita.
- Il codice dello stage Arena è al commit `3dd6aa5`, **senza** il fix dell'universo (fino a `6a88857`): non confondere i risultati con quelli di un universo "top 25 per rank assoluto".
- `superbot-extbackup` è `inactive/dead`: nessun backup esterno attestato.
