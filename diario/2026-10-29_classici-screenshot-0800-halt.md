# 29 ottobre 2026 — Screenshot classici ore 08:01–08:02 italiane, stop giornaliero

Rilevazione dell'utente tramite **screenshot della dashboard**, non lettura diretta dello stato server.

**Hawk:** dashboard in funzione, 0/10 posizioni aperte, 8 trade chiusi nella run, alert rosso "Nuovi trade bloccati: stop giornaliero raggiunto", ultimo controllo alle 08:00 e prossimo alle 08:15; budget Claude visualizzato 0.000/0.70 USD; Salvadanaio **$0,00** visibile. L'equity NON è nell'inquadratura. Il bottone Pausa è disponibile, Avvia non disponibile. Nessuna prova di soglia assoluta 450 USD.

**Bull:** dashboard in funzione, 1/3 posizioni aperte e 7 trade chiusi, alert rosso "Nuovi trade bloccati: stop giornaliero raggiunto". Posizione PAPER BTC SHORT 15x, margine $150, entry 79943.31, prezzo screenshot 79935.80, SL 80563.81, TP 78871.05, liquidazione 84873.15, P&L temporaneo +$0.21; durata all'08:01 4h42m (apertura stimata alle **03:19 italiane del 29 ottobre**, non il giorno precedente). Salvadanaio ed equity NON visibili nella porzione di screenshot Bull.

**Confronto con screenshot 28/10 ore21:56:** Hawk run #7 aveva 6 chiusi; Bull run #6 aveva 4 chiusi. Ora 8 e 7 rispettivamente: sono aumentati i conteggi (+2, +3) da ieri sera. La nuova posizione BTC Bull aperta dopo le 01:00 italiane (00:00 UTC) è evidenza che si sono potute generare aperture nella nuova giornata: l'alert a ore08 potrebbe essere un **secondo daily stop dopo rollover**, non necessariamente errore. Per provare causa precisa, acquisire orari delle ultime chiusure, equity, day_start_equity, campo day e heartbeat. NON inferire l'equity precisa o l'uso di DeepSeek dallo screenshot.

**Codice attuale rule-pool verificato:** in engine.py `PaperAccount.roll_day(day, prices)` aggiorna day_start_equity quando cambia il giorno; `halted` blocca ingressi se equity <=450 o <=0.88*day_start_equity. Stop quotidiano **non chiude forzatamente le posizioni**. In cli.py `_check_portfolio_reset_flag` esige `pause.flag`, **zero posizioni** e, se Salvadanaio v1 presente, richiesta esplicita `reset_vault:true` più stato READY; reset archivia `state_v2`, `trade_history`, lessons/errors e crea nuovo conto PAPER da1000, incrementa run e resta in pausa. Non confondere reset con cancellazione del cervello, ma effettuare comunque backup indipendente verificato prima.

**Proposta di sicurezza prima di altri test:** mettere manualmente Hawk e Bull in **Pausa** dall'app per congelare nuove aperture senza Chiudi tutto; lasciare che il BTC Bull sia gestito da SL/TP fino a chiusura naturale (la pausa non è garanzia che continuino tutti i gestori AI). Fare acquisizione read-only del diario/trade e verificare equity e vault entrambi prima di scegliere un reset. Un reset frequente può nascondere un vantaggio statistico negativo: etichettare ogni nuova run come esperimento indipendente, mantenere le run perdenti e non riaprire i bot alla cieca senza nuova diagnosi.

**Nessun comando di pausa, reset, chiusura o deploy eseguito da questa chat.** Nessuna modifica a Hawk/Bull, Brain o VPS.

AI: chatgpt (chat normale)
