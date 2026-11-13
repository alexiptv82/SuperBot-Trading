# Checkpoint verificabile — Step0′ autorizzato/preregistrato; audit fonti pubblico PASS

**Data:** 13/11/2026 19:46 Europe/Rome  
**Ambito:** sola documentazione; esclusivamente PAPER; storici ed EventJournal da preservare.

## Decisione utente verificata

L'utente ha autorizzato il **Passo 0′** della nuova ipotesi Toro LONG funding-negativo + recupero prezzo, imponendo che la preregistrazione sia fissata prima di qualsiasi risultato e con queste precisazioni:

1. nessun gate R:R aggiuntivo non dichiarato; soltanto distanza stop 0,8–2,5 ATR;
2. cinque hold-out scelti meccanicamente e nominati: **ADA, AVAX, BCH, DOGE, DOT**, senza sostituzioni a posteriori;
3. orizzonte **24h primario**, 8h secondario;
4. tre controlli espliciti da 1.000 semi: long casuale stesso asset/mese; long casuale con funding negativo senza trigger; stesso trigger senza condizione funding (ablation chiave).

Devono inoltre essere salvati ogni trade, timestamp funding, MAE/MFE, costi, risultati mensili, frequenza segnali e SHA dei dati. L'autorizzazione copre il percorso di test preregistrato, non modifica automaticamente rischi operativi né autorizza deploy/riattivazione.

## PR #97 — preregistrazione completata, test strategico non avviato

- [PR Draft #97](https://github.com/alexiptv82/SuperBot-Trading/pull/97), ramo `work/toro-funding-prereg-20261113`.
- Base `0e29a73a36f668643da4088178bacb8616a45ac0`; HEAD immutabile `429bdd7382ef03a4f1617ee6174ed35d7e44f7a2`.
- Un commit/un file: `docs/v3/TORO-FUNDING-LONG-PREREG-20261113.md`.
- Diario metodologico già registrato al commit `a7622d85f090c8a1cdee77bc8e2353db9b060422`.
- Addendum successivo di correzione SOL nel diario: `55cfebf1cb34b1daf048bef93a8458e45e3d98cd`.
- Sei soglie GO Claude conservate senza ritocchi; universo top15 mensile richiede volume dei 30 giorni precedenti e listing age >=365 giorni ricostruiti storicamente.
- Rischio 12 USDT/trade e 24 aggregato è **solo proposta per una futura fase PAPER**, non configurazione applicata.
- Nessun backtest funding P avviato.

## SOL 4h V1 — segno definitivamente risolto

Fonte primaria mostrata dall'utente:
- 67 operazioni;
- `avg_net=-0.0002571351706489649` = **−0,025714%**;
- `avg_gross=+0,074286%`;
- costo test 0,10%.

Anche la riga del log è stata riletta con segno negativo. La precedente lettura positiva era un errore visivo della chat, non un difetto dimostrato nei dati o nello script. La media V1 aggregata 4h resta **−0,1305%** e il NO-GO BB100 V1 è confermato.

## PR #98 — audit fonti pubblico completato

- [PR Draft #98](https://github.com/alexiptv82/SuperBot-Trading/pull/98), ramo `work/toro-funding-data-audit-20261113`.
- Base esatta prereg #97 `429bdd7382ef03a4f1617ee6174ed35d7e44f7a2`.
- HEAD `bdf48f79425fa968e64d3a4be61a23568728d80b`; un commit/un file: `deploy/scripts/toro_funding_source_audit_20261113.py`.
- Blob Git dello script `4c48f2e14ff044bd74cbb6c0b32ffdf915c569a4`.
- Prima prova API pubblica: Bitget e Binance recenti 20 record BTC sullo stesso intervallo; Binance gennaio 2022, 21 record; nessun errore.
- Audit completo successivo: `PUBLIC_DATA_AVAILABLE verified_symbols=6/6 errors=0 PROXY_GATE=NOT_EVALUATED LIVE_TRADES=0 NO_BOT_CHANGES=1`; manifest e 12 file JSON settled-rate con SHA.

| Asset | Bitget | Binance | timestamp settlement esatti comuni | concordanza del solo segno |
|---|---:|---:|---:|---:|
| BTCUSDT | 270 | 270 | 132 | 91,667% |
| ADAUSDT | 270 | 270 | 132 | 80,303% |
| AVAXUSDT | 270 | 270 | 132 | 81,061% |
| BCHUSDT | 270 | 270 | 132 | 81,061% |
| DOGEUSDT | 270 | 270 | 132 | 85,606% |
| DOTUSDT | 270 | 270 | 132 | 71,970% |

### Limite metodologico essenziale

`132/270` non è la coverage oraria preregistrata e la concordanza del segno non è coincidenza degli episodi estremi-negativi. L'audit dimostra accessibilità e raccolta dei dati pubblici, **non** supera o fallisce il proxy gate e non prova edge, PnL o GO strategico.

## Eseguito / preparato / non eseguito

- **Eseguito:** autorizzazione utente; prereg #97; verifica SOL primaria; preflight API; audit fonti PR #98 sui sei simboli.
- **Preparato:** dati diagnostici con hash e piano di confronto cross-venue.
- **Non eseguito:** proxy gate 70/60/10/90 sugli episodi estremi; ricostruzione top15 storica; Step0′ strategico; bootstrap/benchmark; backtest; shadow Bitget; test PAPER.
- **Rilasciato:** nulla. Nessun rischio o servizio modificato.

## Tre portafogli PAPER

- **Brain:** unpause guarded già verificato; ultimo stato disponibile runner attivo/exit healthy. Nessuna nuova prova del primo ciclo completo sugli otto simboli, aperture/chiusure o PnL.
- **Falco:** SHORT originale congelato e non riattivato; richiede gate SHORT_ONLY separato.
- **Toro:** BB100 V1 resta NO-GO e sospeso. Funding P è autorizzato come percorso di ricerca preregistrato, ma il backtest non è iniziato e nessuna logica è collegata al runner.

## Backup, chiavi e riferimenti

- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup/restore VPS.
- `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- RC84 PR #80 resta riferimento storico.
- Solo PAPER; storici ed EventJournal devono essere preservati.
- Nessun segreto, token, passphrase, chiave privata o dettaglio utile all'accesso VPS registrato.

## Prossimi passi / ripresa

1. Eseguire soltanto diagnostica offline sui dati già acquisiti: normalizzare settlement e misurare episodi estremi con soglie preregistrate 70% pooled, 60% per simbolo, almeno 10 episodi/simbolo e 90% ore comparabili.
2. Non presentare percentile retrospettivo 90gg come segnale causale.
3. Risolvere il gate dell'universo top15 storico senza survivorship prima del backtest strategico.
4. Solo se i data gate passano, implementare Step0′ esattamente come preregistrato, senza retuning.
5. Nessun merge/deploy/riattivazione o modifica rischi senza mandato separato.
