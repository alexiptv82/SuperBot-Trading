# STATO di SuperBot Trading

**Aggiornato:** lunedì 19 ottobre 2026, ~11:40 (ora di Roma) — da Claude.
**In corso:** nessuno. (Chi comincia a lavorare su un componente scrive qui sotto: "In corso: <chi> su <componente> dalle <ora>", e lo toglie a fine lavoro.)

## In una frase
Il bot di trading su futures Bitget (due portafogli, Hawk e Bull, più un pool di regole) e la sua app girano **tutti su un unico server a Singapore, in modalità paper** (soldi finti). La migrazione da Strasburgo è finita il 19 ottobre. Il live con soldi veri non è attivo e non è in programma finché l'utente non lo decide.

## Che cosa gira e dove (verificato il 19/10 mattina)

| Componente | Stato | Note |
|-----------|-------|------|
| Server Singapore (`51.79.205.82`) | attivo | Ospita tutto. Si è riavviato due volte il 19/10 all'alba (rescue di OVH, non per colpa nostra); i container sono ripartiti da soli |
| App (container `superbot`) | online | `https://superbot-trading.duckdns.org`, HTTPS valido, login con password e impronta digitale. L'utente l'ha provata da telefono: tutto funziona |
| Bot Hawk e Bull | online, **paper** | Cicli ogni 30 minuti; il 19/10 mattina nessun segnale sopra soglia, quindi nessuna posizione aperta: non è un guasto |
| Pool di regole (`superbot-pool`) | online | Runner paper |
| Strasburgo (`51.91.109.45`) | SuperBot fermo | Resta acceso HI-TV (non toccare) e `superbot-staging` (da decidere) |

## Decisioni dell'utente ancora valide (le più recenti)
- Tutto in **paper**; il live si valuta solo dopo il test, con una sua decisione esplicita.
- La **strategia dei bot non cambia** se non la cambia lui. Il cervello (storico, appunti, registro di apprendimento) non si tocca mai.
- 19/10: tutto SuperBot deve essere separato da Strasburgo e stare su Singapore (fatto).
- 19/10: **le chiavi API di Bitget restano in stand-by** finché non si va in live. Sono limitate all'IP di Strasburgo: da Singapore Bitget le rifiuta (errore "Invalid IP"). Quando si andrà in live, l'utente deve aggiungere l'IP `51.79.205.82` alla lista di ciascuna chiave (le due di sola lettura e le due di trading). Fino ad allora la pagina Live dell'app mostra zeri per progetto (in paper non legge il saldo) e va bene così.
- 19/10: l'utente ha lasciato decidere a Claude sui tre workflow di migrazione dei dati → **rimossi** (vedi `diario/2026-10-19_claude.md`).
- 19/10: l'utente vuole che **ChatGPT e Claude possano sostituirsi a vicenda** (scrivere, commit, push, rami, deploy come l'altra AI) e che esista questo diario → creato.

## Cose aperte (in ordine di importanza)
1. **Verificare per intero i nuovi deploy rinforzati** (app: backup verificato, controllo finale di salute, ritorno indietro; bot: backup del cervello). Finora sono stati provati solo i singoli passi. Il deploy dell'app dura pochi secondi di indisponibilità. Il deploy dei bot richiede l'OK esplicito dell'utente.
2. **Ponte temporaneo del 18/10** (`superbot-desk-api` + una chiave SSH limitata per il tunnel): non serve più perché app e bot stanno sullo stesso server. Da ritirare, ma solo con OK dell'utente. Non influisce sulla capacità delle AI di lavorare (che passa dal repository).
3. **Staging a Strasburgo** (`superbot-staging`): decidere se spegnerlo.
4. **Credenziali usate durante la migrazione**: ruotare la chiave SSH di Singapore, il token GitHub e il token DuckDNS (comparsi in chat o in screenshot). Da fare con l'utente.
5. **Repository pubblico**: l'utente deve decidere se renderlo privato. Prima i server hanno bisogno di una chiave di sola lettura per scaricare il codice, altrimenti i deploy si fermano.
6. **Backup fuori dal server**: oggi le copie stanno sullo stesso server. Manca una copia esterna aggiornata di database app, pool e cervello.
7. **Riallineare `main` e `rule-pool`** (hanno storie diverse: 46 commit solo su main, 100 solo su rule-pool) e correggere in `rule-pool` il bug del `Request` mancante in `backend/server.py` (per questo l'app si distribuisce sempre da `main`).
8. **Dati di mercato mancanti**: due endpoint Bitget (open interest, rapporto long/short) rispondono 404, quindi quelle feature sono a zero. Correggerli cambia ciò che vede Claude, quindi serve l'OK dell'utente.
9. **Una ventina di workflow di sola diagnosi** usano ancora ssh senza verifica rigorosa della chiave del server (non mandano segreti di trading).
10. **Prossima fase (P2)**: nuove strategie e scalping con ingressi e riingressi rapidi, H24. Prima va chiarito con l'utente cosa intende con "20/30%". Si parte solo in modalità ombra/paper e dopo una sua decisione.

## Prossimo passo suggerito
Chiedere all'utente cosa vuole sul punto 1 (primo deploy completo rinforzato dell'app) oppure sul punto 10 (chiarire il "20/30%"). Non fare altro che lettura finché non risponde.

## Dove trovare i dettagli
- Come si lavora: `MANUALE-OPERATIVO.md`.
- Cosa è successo e quando: cartella `diario/` e `STORIA-FINO-AL-19-OTTOBRE.md`.
- Esiti dei controlli sul server: file `deploy/*-output.txt` sul ramo `rule-pool` (i più utili: `superbot-sg-check`, `sg-bots-check`, `sg-hardening-check`).
- Documentazione estesa (rapporti, valutazioni, specifiche): sta nel Project "superbot trading" di Claude. Se serve un documento che non c'è qui, l'utente può passarlo.
