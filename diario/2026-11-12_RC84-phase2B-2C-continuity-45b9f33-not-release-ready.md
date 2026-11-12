# Checkpoint 12/11/2026, 19:49 Europe/Rome — RC84 fasi 2B/2C: storico paginato e continuità esatta; candidato 45b9f33 non release-ready

## Novità verificata

Il ramo isolato `work/rc84-signals-mtf-closed-20261112`, sempre separato dalla sorgente RC84 installata `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, è avanzato oltre la fase 2:

1. [Fase 2B `c8c209cd069b0c5fb3b9d8a3d618d18b36e3af2a`](https://github.com/alexiptv82/SuperBot-Trading/commit/c8c209cd069b0c5fb3b9d8a3d618d18b36e3af2a): storico giornaliero Bitget paginato, cache e budget.
2. [Fase 2C `45b9f334c9c62243962fcd32413c554e1b8dbea5`](https://github.com/alexiptv82/SuperBot-Trading/commit/45b9f334c9c62243962fcd32413c554e1b8dbea5): continuità esatta crypto e calendario separato per XAU/XAG.

Entrambi i commit sono `[skip ci]`. Il ramo non ha PR associata e non è stato mergiato, rilasciato o installato. Nessuna modifica a VPS, pause, wallet, posizioni, rischi o strategie.

## Fase 2B — fatto/preparato

- `fetch_daily_history`: pagine `history-candles 1Dutc` da 89 giorni, fino a 260 barre chiuse o quattro pagine; aggiornamento incrementale giornaliero.
- `merge_bars`: ordine crescente, deduplica per timestamp, esclusione delle candele in formazione e righe invalide; conflitti conteggiati.
- Cache 4H/1D, attesa di 30 minuti dopo errore, tetto di 12 pagine storiche per ciclo; stato HTF nel heartbeat.
- Risposte 4H/1Dutc con granularità incoerente rifiutate; storia corta/vecchia → `UNKNOWN`; trend 1d resta consultivo a zero punti.
- Documento del commit: verifica VPS riportata per BTC/ETH 1Dutc, tre richieste × 89 giorni = 267 barre chiuse consecutive senza gap (18/02–11/11/2026). La sezione residui riporta anche ETH 4H con 539 barre; il percorso esatto `4H&limit=1000` resta da ricontrollare prima di un rilascio.

## Fase 2C — fatto/preparato

- Rimossa la tolleranza generica di tre giorni, che poteva far calcolare EMA50/EMA200 su serie crypto incomplete.
- Crypto 24/7: intervalli esattamente di 4h/1d; dopo un buco si usa solo la coda continua più recente; se inferiore a 200 barre → `UNKNOWN` con motivo e data.
- XAU/XAG: ammesse solo barre mancanti che aprono di sabato/domenica UTC; buchi feriali → interruzione. Orari e festività Bitget dei metalli non sono ancora certificati.
- Duplicati identici uniti; duplicati conflittuali nella serie → rifiuto; aperture fuori griglia → rifiuto; righe sparse ordinate; barre future/in formazione escluse. Nessuna interpolazione.
- Fatti aggiunti: `market_calendar`, `trend4h_gaps`, `trend1d_gaps`, `last_gap`.
- Paginazione/cache/budget 2B, gate solo 4h, `DAILY_TREND_POINTS=0`, motore PAPER, rischio e strategie restano invariati.

## Test e fonte

Fonte GitHub: commit e documento `docs/v3/RC84-FASE2-MOTORE-SEGNALI.md`. Fonte esecuzioni: messaggio recente recuperabile della conversazione del progetto.

| Prova | Esito riportato |
|---|---:|
| Fase 2 originale | 23 PASS |
| Fase 2B | 13 PASS |
| Fase 2C | 13 PASS |
| Totale mirato 2/2B/2C | **49/49 PASS** |
| Suite completa candidato | **7.001 pass / 26 fail / 9 skip / 3 xfail** |
| Replay sintetico | identico alla fase 2/2B |

Il totale 7.001 equivale ai 6.952 pass della baseline più i 49 test mirati. I 26 fallimenti sono dichiarati identici e preesistenti; non sono stati risolti né rimossi.

## Perché non è release-ready

1. `merge_bars` conserva l'ultima riga scaricata quando due pagine forniscono lo stesso timestamp con valori diversi e conta il conflitto; di conseguenza il successivo `series_check` può non vedere più entrambe le righe. Occorre rendere il conflitto fail-closed lungo tutta la catena o dimostrarne la gestione.
2. Venti dei 26 fallimenti non dimostrano più le protezioni previste perché usano aperture `medio` su Falco, ora rifiutate prima di raggiungere DCA, pause/svuotamento, ripresa, entrata diversificata, riconciliazione e claim. Non è un difetto operativo provato, ma è **copertura persa**.
3. La protezione claim in alcuni casi passa per il motivo sbagliato; va riscritta con aperture `scalp` su Falco o `medio` da Claude su Toro, senza cambiare lo scopo.
4. Calendario Bitget XAU/XAG e granularità/limiti 4H devono essere verificati in sola lettura. Replay ancora sintetico e senza Claude/dati reali.

PR #91 resta Draft, HEAD `500563a96db0e771f74a580b7278765eae0eaa92`; non sostituisce queste verifiche. Roadmap Falco SHORT-only/Toro LONG+SHORT resta separata e non applicata.

## Stato consolidato PAPER, backup e chiavi

Ultimo stato operativo documentato invariato: Falco/Toro sotto pausa RC84 in `draining`; Brain `paused`, exit `healthy`; tre pause e resume non autorizzato. Nessun nuovo controllo live VPS in questa esecuzione e conteggi correnti non noti.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore VPS. RC84 PR #80 resta riferimento storico. Nessun segreto letto o pubblicato.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito:** sviluppo 2B/2C sul ramo isolato, test locali riportati e documentazione.
- **Preparato:** paginazione 1Dutc, continuità fail-safe e calendari di mercato.
- **Rilasciato:** nulla.
- **Non approvato/non eseguito:** hardening conflitti `merge_bars`, recupero copertura dei 20 test, PR, merge, deploy, Actions, installazione/modifica VPS, restart/resume, reset, wallet, ordini, LIVE o API a pagamento.

## Prossimo passo e istruzioni di ripresa

Partire da `45b9f334...`, senza trattarlo come release. Correggere prima la propagazione fail-closed dei duplicati conflittuali; recuperare le prove DCA/claim/chiusure/riconciliazione con aperture compatibili RC84; verificare in sola lettura XAU/XAG e `4H&limit=1000`; poi rieseguire 49 mirati, suite completa e replay. Mantenere PAPER, pause, EventJournal, learning e storici; non assumere trascrizioni integrali di chat eliminate né stato VPS successivo.
