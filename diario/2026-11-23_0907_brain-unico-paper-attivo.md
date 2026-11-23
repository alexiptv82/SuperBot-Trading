# 2026-11-23 09:07 CET — Brain Unico RC1 ATTIVATO in PAPER (evidenza Termius)

## Evidenza screenshot proprietario
- Il proprietario ha eseguito in Termius sulla VPS Singapore `sudo sh /root/brain-unico-avvio/80-paper.sh attiva "Operatore"`.
- Output terminale visibile: `PASS PAPER isolato: DESK_MODE=paper nelle unita', run con marcatore paper_only`.
- `PASS limiti di rischio = profilo B` con fingerprint config `e415ca96e7475b820712294fd97a81dfe6ef03e21df00342a0eab68203edc` (come stampato nell'immagine).
- `PASS servizio delle uscite sano (lease, battito, monitor con prezzi di mercato recenti)`.
- `PASS chiave DeepSeek presente (valore non letto)` — PRESENZA soltanto, non prova endpoint/API DeepSeek effettivamente riuscita; lo screenshot non mostra esito `ESITO VERIFICA: GO` dello script diagnostico separato.
- `mandato: VALIDO`.
- Riga confermativa: `PAPER ATTIVO: mandato approvato da Operatore, pausa tolta. Il Brain decide al prossimo giro (ciclo 60 min).`.
- Subito prima, `BRAIN_UI_RESULT=SUCCESS_UI_BRAIN_UNICO` dalla pubblicazione UI stile Classici. Dashboard aveva ricevuto approvazione grafica dal proprietario.

## Configurazione e limiti documentati
- Brain Unico PAPER 2.000 USDT virtuali; DeepSeek Flash principale; profilo B; 8 simboli; ciclo 60 min; rischio stimato a stop 1% trade, 4% rischio aperto, 4 posizioni, -4% stop a nuovi ingressi giornalieri, leva 1–30x, budget AI $0.75/giorno. Non sono garanzie di perdita massima effettiva.
- Memoria che influenza il prompt: gli esiti chiusi e collegati alimentano scoreboard per strategia/lato/regime al ciclo successivo; classificazione significativa richiede 15 esiti e 4 giorni per cella. Auto-training del modello assente, non confondere con apprendimento contestuale.
- Claude non è un revisore automatico nel runner: resta supporto esterno per diagnosi e miglioramenti.

## Prossime osservazioni
- Verificare entro i primi cicli che dashboard passi a running, che crescano timestamp/ciclo decisionale, appaia decisione o NO_TRADE, che DeepSeek risponda davvero senza `ai_unavailable`/`invalid_model_output`, e che contabilità/budget/uscite restino coerenti.
- Se errore AI persistente, risolvere solo il problema emerso, senza cambiare strategia. Se NO_TRADE, non forzare aperture.
- Test iniziale ~72 ore a partire dal 2026-11-23 09:07 CET, riferimento 2026-11-26 09:07 CET, salvo pause o condizioni che invalidano ore di test.
- **Le 72 ore NON si fermano automaticamente**. Il proprietario deve eseguire una pausa o revoca esplicita. `sudo sh /root/brain-unico-avvio/80-paper.sh pausa` blocca nuovi ingressi ma lascia operare le uscite; `revoca` anche mandato approved:false. Nessuna chiusura forzata delle posizioni attive a fine test.
- I servizi non si riavviano automaticamente con reboot VPS; se riavviata serve operatore per ripristinare uscite; annotare eventuale intervallo di monitor non attivo.

Questa voce registra soltanto il successo dell'attivazione visibile nello screenshot del proprietario, NON certifica che l'AI abbia già effettuato chiamate o operazioni e NON dimostra profitto.