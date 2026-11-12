# Checkpoint 12/11/2026, 18:46 Europe/Rome — RC84 fase 2: recuperati risultati replay sintetico; correzione lacuna documentale

## Motivo del checkpoint

Il checkpoint delle 17:46 riportava che il risultato quantitativo del replay non era disponibile. Il riscontro diretto del commit candidato [`1f04f2ca3198f00b8ade03a597a8f8b69616c862`](https://github.com/alexiptv82/SuperBot-Trading/commit/1f04f2ca3198f00b8ade03a597a8f8b69616c862) mostra invece che `docs/v3/RC84-FASE2-MOTORE-SEGNALI.md` contiene già risultati deterministici e la loro metodologia. Questa è una **correzione della documentazione**, non una nuova esecuzione, approvazione o release.

## Metodo verificato nel commit

- ramo isolato: `work/rc84-signals-mtf-closed-20261112`, da baseline installata `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`;
- replay: 7 regimi sintetici × 6 semi = 42 percorsi, 240 giorni per percorso e 30 giorni valutati;
- stesso motore PAPER, commissioni, slippage, funding, cooldown, stop giornaliero e percorso regole Falco;
- candela in formazione emulata dalle 5m già chiuse; confronto appaiato sullo stesso mercato/seme;
- nessun dato di mercato reale, nessun Claude, nessuna Bitget live e nessuna GitHub Action;
- il documento del commit dichiara riesecuzione identica bit per bit con semi fissi.

## Risultati recuperati

| Versione | Trade | LONG netto | SHORT netto | Totale netto | Drawdown |
|---|---:|---:|---:|---:|---:|
| RC84 `ab7e0b7` | 1.629 | −1.615,54 USD | −3.130,07 USD | −4.745,61 USD | 4.826,21 USD |
| Candidato `1f04f2c` | 1.517 | −1.245,16 USD | −2.513,47 USD | −3.758,63 USD | 3.818,98 USD |
| Candidato con trend 1d a 15 punti | 2.309 | −3.194,97 USD | −4.136,96 USD | −7.331,93 USD | 7.375,19 USD |

Confronto appaiato candidato − RC84:

- LONG: +8,82 USD per percorso, 26/42 migliorati, `t=+1,00`;
- SHORT: +14,68 USD per percorso, 27/42 migliorati, `t=+1,54`;
- totale: +23,50 USD per percorso, 27/42 migliorati, `t=+1,99`;
- candidato con 1d a 15 punti: −61,58 USD per percorso, 14/42 migliorati, `t=−3,25`.

Regressi del candidato oltre la soglia del banco `max(20 USD, 5%)`: rialzista LONG −91,79 USD; laterale SHORT −47,14 USD; rialzo con correzioni LONG −31,03 USD. Il documento li considera entro il rumore del campione.

## Interpretazione corretta e limiti

I mercati usati sono passeggiate casuali con deriva e non incorporano un vantaggio tecnico reale. I netti negativi misurano soprattutto costi e frequenza; **non sono una previsione di redditività né una validazione sui wallet RC84 reali**.

Il candidato apre circa il 7% di trade in meno e mostra drawdown sintetico inferiore. Il miglioramento LONG non è statisticamente convincente (`t=1,00`); quello SHORT non prova un vantaggio (`t=1,54`). Il totale è al limite convenzionale (`t=1,99`) ma resta su dati sintetici. Dare 15 punti al trend 1d aumenta i trade e peggiora significativamente: `DAILY_TREND_POINTS=0` resta quindi la scelta preparata nel candidato.

## Stato desiderato vs implementato

| Area | Stato |
|---|---|
| Barre chiuse e vere EMA50/EMA200 4h/1d | preparate/testate in `1f04f2c`, non rilasciate |
| Gate 4h `UNKNOWN` | preparato; resta da verificare che non sia eccessivamente bloccante e che Bitget accetti `4H`/`1Dutc` |
| Trend 1d nel punteggio | sconsigliato dal replay; candidato mantiene 0 punti |
| Falco SHORT-only / Toro LONG+SHORT | roadmap separata, non implementata |
| Politiche rischio P-1…P-5 | non applicate; richiedono decisione separata |
| PR #91 audit wallet V3 | Draft, HEAD `500563a96db0e771f74a580b7278765eae0eaa92`; test V3/esecuzione reale non provati |

## Stato PAPER, backup e chiavi

Stato consolidato invariato: Falco/Toro sotto pausa RC84 in `draining`, Brain `paused` con exit `healthy`; tre pause e resume non autorizzato. Nessuna verifica live VPS nuova in questa esecuzione; i conteggi correnti non sono noti.

Backup esterno sul ramo `work/extbackup-bot-stopped-20261109`: preparato, non installato. La copia cifrata age sul PC ha mostrato PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore sulla VPS. RC84 PR #80 resta riferimento storico. Nessun segreto è stato letto o pubblicato.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito:** sola verifica documentale del contenuto del commit e correzione del checkpoint.
- **Preparato:** candidato e replay sintetico già contenuti in `1f04f2c`.
- **Rilasciato:** nulla.
- **Non eseguito/non approvato:** test Bitget read-only, replay su dati reali, PR/merge/deploy/Actions, modifica VPS, restart/resume, reset, wallet, ordini, LIVE o API a pagamento.

## Prossimo passo e ripresa

Prima di qualunque rilascio: verificare in sola lettura la granularità Bitget `4H`/`1Dutc`; sostituire il generatore sintetico con candele storiche reali su copia; riesaminare gate 4h e regressi; mantenere separati audit PR #91, candidato fase 2 e roadmap Falco/Toro. Conservare PAPER, EventJournal, learning e storici. Non assumere trascrizioni integrali di chat eliminate né stato VPS successivo all'ultima prova documentata.
