# Lettore di regime v2 — 30/10/2026 (Claude)

**Ramo laboratorio:** `work/regime-lab-claude-20261030` (mai unito a `rule-pool`; perimetro verificato dal workflow: nessun file fuori da `backend/regime_lab_claude/` e dal workflow).
**Nessun bot toccato. Nessun deploy. `DESK_MODE=paper`. Solo candele pubbliche.**

## Richiesta
Dal PDF «Lettore dinamico del regime per simbolo» (altra AI) costruire un lettore migliorato che serva ai **classici** (capire il cambio di tendenza, pareggiare i due lati) e al **Brain** (la parte short dei classici come base, il lettore come contesto).

## Cosa e' stato costruito
- `regime_v2.py`: direzione (contesto 4h, presente 15m+1h, variazione), qualita' del movimento (Kaufman ER su 24 barre 1h) e anomalia di volatilita' (ATR 15m / media delle 288 precedenti) come tre misure separate. Stati: SHOCK, DOWN_CLEAN, DOWN_CHOP, TURNING_UP, RANGE, TURNING_DOWN, UP_CHOP, UP_CLEAN, EMERGING_DOWN, EMERGING_UP, NA. Classe per lato (ALIGNED / NEUTRAL / OPPOSED) per specchio esatto. Isteresi senza memoria (stesso risultato batch e live). Livello di mercato: stessa macchina sulle mediane dei simboli cripto (oro/argento esclusi, minimo 5 simboli).
- Credito al PDF di partenza: le caratteristiche di candela (avanzamento, equilibrio dei corpi, rottura delle 6 barre precedenti, posizione della chiusura, struttura HH/HL) e la filosofia «non bloccante». Cambiato: qualita' del movimento e volatilita' separate dalla direzione, livello di mercato, simmetria esatta dimostrata da test, isteresi senza memoria, classe per lato invece di un'etichetta unica, laboratorio pre-registrato.
- 21 test: specchio, causalita', equivalenza batch/vivo, barra non chiusa, buchi nei dati, isteresi, NA non scavalcato, limite di memoria, mediana di mercato, inversione a V rilevata prima dell'incrocio delle EMA.

## Metodo del laboratorio (scritto prima di guardare i rendimenti)
Fase struttura (non legge mai i rendimenti) -> fase griglia (solo struttura) -> fase completa una volta sola. Metrica del valore: R medio dei trade tenuti meno R medio dei trade scartati (non «fare meno trade»), bootstrap a blocchi di 7 giorni, placebo con serie spostata di 5-60 giorni, scenari S1/S2, gate R1-R7. Gate strutturali: S0a (nessuno stato oltre il 60%), S0b (ALIGNED tra 8% e 60% dei trade), S0d (durata mediana almeno 8 barre), D1 (ritardo <= 50% delle EMA 20/50 su 1h), D2 (lift >= 1,15 e <= 2 cambi/giorno), D3 (rilevazione delle vere svolte oltre il p95 dei placebo).

## Risultati finora
- Iterazione 1 (v2.0, hash `1c7dee868ad5`), commit risultati `6edbfb3`: **non accettata** — S0a (RANGE 62%), S0d (6 barre), D1 (0,70), D2 (1,12) falliti; S0b e D3 passati (80% contro 60%).
- Errata E2: una sola correzione v2.1 ammessa. Errata E3 (commit `fbbbdb6`): griglia di 16 configurazioni (isteresi 2/4, peso 15m 0,60/0,30, soglia contesto 0,25/0,15, soglia presente 0,20/0,30) e regola di scelta fissate PRIMA dell'esecuzione. Se nessuna passa tutto: lettore **non idoneo**, stop.
- Limite dichiarato: la scelta e' in-sample sulle stesse 18 mesi (solo metriche strutturali), non e' una prova fuori campione.

## Per ChatGPT (Brain Scalp, regola 9)
Niente da fare finche' il laboratorio non chiude. Se il lettore passa: snapshot di regime come blocco del prompt, candidati short classici etichettati per classe, prima in modalita' ombra; dimensionamento per classe = decisione dell'utente. `scalp1m` non e' validato.

AI: claude
