# 29 ottobre 2026 ore 08:07 Italia — screenshot classici in pausa

Dati da screenshot utente; non lettura VPS. Entrambi PAPER, dashboard indica codice vdc16e01.

| Campo | Hawk run #7 | Bull run #6 |
|---|---:|---:|
| Equity | 698,86 USD | 673,48 USD |
| Variazione da 1.000 | -301,14 USD (-30,11%) | -326,52 USD (-32,65%) |
| P&L oggi | -145,89 USD | -205,67 USD |
| Cassa | 698,86 USD | 522,49 USD |
| Margine | 0 USD | 150 USD |
| P&L flottante | 0 USD | +0,99 USD |
| Aperte | 0/10 | 1/3 |
| Chiuse | 8 | 7 |
| Salvadanaio | 0 USD | 0 USD |
| Stato | in pausa | pausa in corso, termina 1 posizione |

La somma delle due equity visualizzate e' 1.372,34 USD, rispetto a base iniziale 2.000 e' -627,66 USD (-31,383%). Solo PAPER.

Utente ha premuto Pausa da app su entrambi, non ha chiuso trade ne' resettato. Bull conserva la posizione BTC SHORT 15x/margine 150 USD dei precedenti screenshot. Non forzare la chiusura.

Entrambi oggi hanno raggiunto stop 12%; l'engine legacy halted blocca NUOVE aperture ma non chiude posizioni gia' aperte. P&L oggi Bull -205,67 USD richiede audit cronologico del daily rollover (data/day_start_equity), entrate, chiusure, MFE/MAE, drawdown e versione, non prova automatica di bug.

Prossimo passo prima di ogni reset: backup indipendente consistente e test restore, verifica run archive, zero posizioni, capital journal/Salvadanaio e brain intatti. Reset porta ciascun conto a 1000 PAPER e lascia il bot in pausa. No deploy, no modifica bot/VPS/Brain effettuata da ChatGPT.

AI: chatgpt (chat normale)
