# Checkpoint verificabile — PR #98 proxy gate FAIL; Step0′ strategico non avviato

**Data:** 13/11/2026 20:54 Europe/Rome  
**Perimetro:** sola documentazione e ricerca offline; trading esclusivamente PAPER; nessun merge, deploy, GitHub Actions, VPS, riavvio, reset, ordine o API a pagamento.

## Novità verificata

La [PR Draft #98](https://github.com/alexiptv82/SuperBot-Trading/pull/98), ramo `work/toro-funding-data-audit-20261113`, è avanzata sul prereg immutabile della PR #97:

- base: `429bdd7382ef03a4f1617ee6174ed35d7e44f7a2`;
- HEAD: `659ff470402a802d885c86a80f61fcea90cd9d34`;
- due commit, due file;
- nuovo diagnostico research-only `deploy/scripts/toro_funding_proxy_diagnostic_20261113.py`, blob `0c0ae324657fe0118a74fd2e283315e86e8ca1d8`;
- nessuna rete: riusa soltanto i 12 JSON già salvati, ne verifica gli hash, esegue prima un self-test sintetico e applica le soglie preregistrate 70/60/10/90.

Esecuzione completata alle 19:56 Europe/Rome:

- `TORO_PROXY_DIAG SYNTHETIC_TEST=PASS NO_NETWORK=1`;
- `PANEL_RESULT=DIAGNOSTIC_THRESHOLDS_NOT_MET`;
- `pooled_extreme_events=155`;
- `pooled_precision=0.2968`;
- `STRATEGY_BACKTEST=0`;
- `FULL_UNIVERSE_GO=0`.

## Risultati del gate proxy

| Simbolo | episodi estremi Binance | coincidenze Bitget | precisione |
|---|---:|---:|---:|
| BTCUSDT | 20 | 1 | 5,00% |
| ADAUSDT | 27 | 10 | 37,04% |
| AVAXUSDT | 27 | 10 | 37,04% |
| BCHUSDT | 27 | 10 | 37,04% |
| DOGEUSDT | 27 | 8 | 29,63% |
| DOTUSDT | 27 | 7 | 25,93% |
| **Totale** | **155** | **46** | **29,68%** |

- Coverage ore comparabili: `0.9717`, superiore a 0,90 — **PASS**.
- Campione minimo: almeno 10 episodi per simbolo — **PASS**.
- Coincidenza pooled: 29,68% contro soglia 70% — **FAIL**.
- Coincidenza per simbolo: tutti sotto la soglia 60% — **FAIL**.

Decisione bloccata dal prereg: il funding Binance **non può essere trattato come surrogato valido** del funding Bitget. Non avviare Step0′ 2020–2026 con questo proxy e non abbassare le soglie a posteriori.

## Limite dell'evidenza

È una diagnostica retrospettiva p10 su 90 giorni e sei simboli (BTC più i cinque hold-out), non il top15 storico completo e non un test causale/predittivo. Il FAIL della **fonte proxy** non dimostra che la strategia LONG funding-negativo sia inefficace. Il backtest strategico non è stato eseguito; nessun PnL, trade o edge è stato prodotto.

Le sole strade residue documentate sono: dati storici Bitget reali con provenienza verificabile oppure raccolta prospettica shadow Bitget nel tempo. Nessuna delle due è stata avviata da questo checkpoint.

## Fatto / preparato / rilasciato

- **Fatto:** audit pubblico PR #98, self-test sintetico PASS, diagnostica offline sui 12 input con hash, valutazione gate preregistrato, esito proxy FAIL.
- **Preparato:** script diagnostico research-only e dataset verificato; non è un componente del bot.
- **Rilasciato:** nulla.
- **Non eseguito/non approvato:** Step0′ strategico, top15 storico, backtest 2020–2026, bootstrap/benchmark, raccolta shadow, integrazione runner, modifica rischi, riattivazione Toro/Falco.

## Tre portafogli PAPER

- **Brain:** ultimo riscontro disponibile: unpause guarded eseguito, runner attivo ed exit healthy. Mancano ancora prove nuove del primo ciclo completo sugli otto simboli, aperture/chiusure o PnL.
- **Falco:** strategia SHORT congelata, non riattivata.
- **Toro:** BB100 V1 resta NO-GO e sospeso. Il nuovo esito blocca solo il proxy Binance; Step0′ non è partito e Toro non è stato integrato o riattivato.

## Backup, chiavi e conservazione

- Copia cifrata age sul PC: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica la presenza, integrità o ripristinabilità del backup sulla VPS.
- Ramo `work/extbackup-bot-stopped-20261109`: backup esterno preparato, non installato.
- RC84 [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta riferimento storico.
- Storici ed EventJournal devono restare integri. Nessun segreto, token, passphrase, chiave privata o dettaglio d'accesso VPS è registrato qui.

## Problemi e prossimo passo

1. Fonte proxy Binance respinta dalle soglie preregistrate; vietato retuning post hoc.
2. Procurare dati storici Bitget reali con provenienza e copertura verificabili **oppure** definire una raccolta shadow prospettica; richiedono decisione separata.
3. Solo dopo un nuovo data gate valido, eseguire l'esperimento preregistrato senza modificare criteri e hold-out.
4. Per Brain, documentare un ciclo reale completo sugli otto simboli senza forzare ordini.
5. Nessun merge/deploy/VPS/riattivazione/modifica rischio senza mandato separato.

## Limiti di accesso

Questo checkpoint usa le evidenze GitHub e i contenuti Library effettivamente accessibili e le decisioni presenti nella conversazione corrente. Non dispone di trascrizioni integrali di chat eliminate e non certifica uno stato live VPS.
