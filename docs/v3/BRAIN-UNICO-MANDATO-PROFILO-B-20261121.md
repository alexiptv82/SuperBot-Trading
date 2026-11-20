# Brain Unico: configurazione e mandato del profilo B (DA ESAMINARE, non attivi)

**Stato:** preparati per la revisione del proprietario. **Non applicati:** nessuna run creata, nessun deploy, nessun servizio toccato. Decisione di riferimento: profilo **B Bilanciato** (21/11/2026), vedi `BRAIN-UNICO-PROFILO-RISCHIO-PROPOSTA-20261121.md`.

## File
| File | SHA-256 | Contenuto |
|---|---|---|
| `backend/v3/runner/runner_config_brain_unico_paper_b.json` | `e415ca968e7475be820712294fd97a81dfe6ef03e21df00342a0eab68203eedc` | configurazione della nuova run |
| `backend/v3/runner/mandate_brain_unico_paper_b.TEMPLATE.json` | `0bb3234252eaa51a13721adb4574c5635fbfdd6d61fa02f4102028e370cea825` | modello di mandato, **`approved: false`** |

Le configurazioni esistenti (`runner_config.json`, `runner_config_brain2000_paper.json`) **non** sono modificate.

## Differenze rispetto alla configurazione PAPER 2.000 attuale (solo queste)
| Campo | Attuale (storico) | Profilo B |
|---|---|---|
| `max_loss_fraction` (rischio per operazione, stimato allo stop) | 0,042857 (85,71 USDT) | **0,01 (20 USDT)** |
| `max_open_risk_fraction` | 0,12 | **0,04** |
| `max_total_margin_fraction` | 0,55 | **0,50** |
| `minimum_equity` (pavimento: niente nuove aperture) | 450 | **1.600** |
| `min_leverage` / `max_leverage` | 20 / 50 | **1 / 30** |
| `max_loss_margin_fraction` | 0,214 | **1** (vincolo disattivato; resta quello di liquidazione, più stretto) |
| `daily_loss_warn_fraction` / `daily_loss_halt_fraction` | 0,35 / 0,50 | **0,03 / 0,04** |

**Invariati:**
- simboli (8);
- capitale iniziale 2.000;
- margine per posizione 20 %;
- costi stimati 16 bp;
- buffer di liquidazione 0,5;
- slippage 2 bp e commissione 6 bp;
- modello `deepseek-flash` e ragionamento;
- ciclo di 60 minuti;
- tetto di spesa AI 0,75 USD al giorno.

## Mandato (modello)
```
version v1 · approved false · approved_by "" · portfolio_id brain · run_id brain-unico-paper-rc1 · policy_hash ba5c074ec2ecfe34
```
Il campo `avvertenze` riporta le tue precisazioni. Non ha effetto sui controlli: il motore lo ignora.
1. **Rischio per operazione:** l'1 % è la perdita **stimata** allo stop, costi stimati inclusi. **Non** è una perdita massima garantita: gap, slippage o funding oltre le ipotesi possono superarla.
2. **Pavimento:** 1.600 USDT blocca le **nuove** aperture. **Non** garantisce che l'equity non scenda oltre: le posizioni aperte proseguono fino al loro stop, e gap o slippage possono superarlo.
3. **Limite giornaliero:** il 4 % ferma le nuove aperture, **non** chiude le posizioni. La perdita della giornata può superare il 4 %.
4. **Solo PAPER.** Leva proposta dal modello entro 1–30×, abbassata dal motore se è troppo vicina alla liquidazione, mai alzata.

## Natura del mandato: garanzie effettive
- **Il mandato operativo NON è firmato.** `mandate.json` è un file che il runner rilegge a ogni giro. Il runner (`wiring.MandateFile`) e il motore (`engine._mandate_ok`) controllano soltanto: `approved` vero, `approved_by` non vuoto, `version`, `portfolio_id` = `brain`, `run_id` e `policy_hash`.
- **Garanzia effettiva:** chi può scrivere nella cartella dati della run, cioè root sulla VPS, può approvare. Il mandato dimostra la **coerenza** tra approvazione, limiti e run, **non l'identità** di chi ha approvato.
- **Sistema separato, non collegato al runner:** `backend/v3/brain_f3/authorization.py` verifica ricevute firmate Ed25519 con chiave pubblica fissata e validità massima di 24 ore. Nessun componente operativo lo usa oggi. Per il primo PAPER, come da tua decisione, nessuna nuova infrastruttura crittografica.

## Che cosa lega il mandato (e che cosa no)
- **Legati:** `policy_hash` lega i 7 limiti di rischio e il profilo di leva (`max_loss_margin_fraction`, `min_leverage`, `max_leverage`), oltre a `run_id` e portafoglio. Cambiarne uno invalida il mandato, e il runner resta fermo con `mandate_mismatch`.
- **Non legati:** limite giornaliero, simboli, modello, ciclo e budget AI. Per questi fa fede lo **SHA-256 della configurazione** indicato sopra, da ricontrollare all'attivazione.
- **Verifica:** `backend/tests/test_v3_brain_unico_paper_b_config.py` controlla i valori, l'hash, il rifiuto con limiti diversi o con un'altra run, l'accettazione di una copia approvata e la perdita stimata di 20 USDT con stop all'1 %.

## Attivazione (SOLO con la tua autorizzazione, insieme al deploy della RC)
1. Creare la cartella della nuova run `brain-unico-paper-rc1`, con journal nuovo e senza riusare né cancellare run storiche. Copiare la configurazione come `runner_config.json`.
2. **Verifica obbligatoria dell'impronta della configurazione COMPLETA.** Il runtime non la verifica da solo, e l'impronta del mandato non copre limite giornaliero, simboli, modello, ciclo e budget. Il passo si ferma se non coincide:
   ```
   printf '%s\n' 'e415ca968e7475be820712294fd97a81dfe6ef03e21df00342a0eab68203eedc  <cartella-run>/runner_config.json' | sha256sum --strict -c - && echo "CONFIGURAZIONE VERIFICATA"
   ```
3. Impostare `V3_RUN_ID` e `V3_RUNNER_CONFIG_PATH` per runner e API.
4. **Tu** copi il modello come `mandate.json` nella cartella dati della run, impostando `"approved": true` e `"approved_by"`. Finché manca o non coincide, il runner resta `halted` e non spende nulla. Il file viene riletto a ogni giro, senza riavvio.

Nessun passo è stato eseguito.
