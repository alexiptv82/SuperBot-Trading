# Checkpoint verificabile — PR #99 Supertrend preregistrata; replay detached avviato, risultati assenti

**Data:** 13/11/2026 21:52 Europe/Rome  
**Perimetro:** sola documentazione del progresso già osservato; trading esclusivamente PAPER; nessun merge, deploy operativo, GitHub Actions, reboot, reset, ordine o API a pagamento eseguito da questo checkpoint.

## Decisione utente e nuovo percorso Toro

Dopo la bocciatura del proxy funding in PR #98, l'utente ha chiesto un **ultimo tentativo LONG** sulla base di una ricerca esterna dichiarata non verificata. È stato scelto un solo candidato, Supertrend 15m/1h, evitando la selezione opportunistica fra più strategie.

Questo percorso è indipendente da PR #97–#98 e non modifica retroattivamente il protocollo funding. Riconosce inoltre i precedenti fallimenti delle strategie LONG in PR #93, #94 e #96.

## PR #99 — stato verificato

- [PR Draft #99](https://github.com/alexiptv82/SuperBot-Trading/pull/99), aperta, non mergiata, mergeable.
- Ramo: `work/toro-supertrend-last-study-20261113`.
- Base: `work/toro-supertrend-last-base-20261113` a `0e29a73a36f668643da4088178bacb8616a45ac0`.
- HEAD: `4b06716546f91b1bb9f34bfc9256d57f321f1d84`.
- Cinque commit, tre file.
- Preregistrazione anteriore ai test: `0c8471a8d189e09fbd7d3f39825a997f2c1cff65`, file `docs/v3/TORO-LAST-LONG-SUPERTREND-PREREG-20261113.md`.
- Runner isolato: commit `8dfacbdb8da76e53bc0148ed928b2ef330ad2c10`, blob `652421126fa4dea1f03c962f6e1a23a4c16162ec`.
- Launcher detached: commit/HEAD `4b06716546f91b1bb9f34bfc9256d57f321f1d84`, blob `5e5a6572a392a53062cadf09a1664798c995c93d`.

## Protocollo preregistrato

Unica ipotesi: Supertrend 1h UP + flip Supertrend 15m UP, close sopra EMA200, RSI14 45–75, volume almeno 1,2× la media delle 20 barre precedenti, ATR10 moltiplicatore 3. Ingresso alla successiva apertura 15m; stop linea Supertrend −0,25 ATR14; target 2R con chiusura completa; durata massima 12h.

- Costi base: 16 bp taker+slippage e 1 bp funding ogni 8h.
- Stress: 30 bp.
- Asset: BTC, ETH, SOL, BNB, XRP.
- Finestra chiusa: 365 giorni fino al 13/11/2026 16:00 UTC.
- Classificazione obbligatoria: replay storico **solo eliminatorio**, non OOS incontaminato, perché storia precedente già osservata.
- Rischio 12 USDT/trade e 24 USDT aggregato: sola ipotesi futura PAPER, non configurazione applicata.
- Shadow prospettico 30 giorni soltanto dopo un eventuale PASS storico; nessun retuning dopo FAIL.
- Audit drawdown mark-to-market e verifica incrementale anti-lookahead restano fail-closed: nessun GO automatico.

## Avvio verificato, non completamento

Nel [commento PR #99 delle 21:39 CET](https://github.com/alexiptv82/SuperBot-Trading/pull/99#issuecomment-6864415166) è registrato l'output Termius:

- `TORO_ST_FINAL synthetic_tests=PASS no_network=1`;
- `TORO_ST_BOOT SOURCE_SHA=PASS SYNTHETIC=PASS`;
- avvio unit isolata `toro-supertrend-last-20261113.service`;
- `TORO_ST_BOOT RESULT=LAUNCHED_DETACHED paper_orders=0 production_units_unchanged=1`.

Questa evidenza dimostra pin sorgenti, sintassi/self-test e **solo l'avvio** del replay research-only. Non prova che il servizio abbia terminato, che il dataset sia completo o che il report finale esista. Non sono disponibili statistiche economiche, trade, expectancy, profit factor, drawdown, benchmark o esito GO/NO-GO.

Evitare una seconda istanza mentre la prima può essere ancora in esecuzione. Attendere un report finale e verificarne integrità, hash dati, log e stato della unit.

## Fatto / preparato / rilasciato

- **Fatto:** scelta dell'unico ultimo candidato; preregistrazione; implementazione research-only; pin e self-test PASS; avvio detached documentato.
- **Preparato:** replay storico eliminatorio, report JSON/CSV e gate fail-closed.
- **Rilasciato:** nulla.
- **Non verificato/non completato:** acquisizione completa dei dati, fine replay, risultati, audit indipendente anti-lookahead/MTM, shadow 30 giorni.
- **Non approvato:** integrazione Toro, modifica rischi, riattivazione Falco/Toro, merge/deploy operativo.

## Tre portafogli PAPER

- **Brain:** ultimo stato consolidato invariato: unpause guarded eseguito, runner attivo ed exit healthy nell'ultima evidenza disponibile. Nessuna nuova prova del primo ciclo completo sugli otto simboli, aperture/chiusure o PnL. La richiesta recente di un report dettagliato sul funzionamento di Brain risulta preparata ma non ancora prodotta in forma verificabile.
- **Falco:** strategia SHORT congelata e non riattivata.
- **Toro:** BB100 V1 resta NO-GO e sospeso. PR #99 è soltanto laboratorio isolato; zero ordini PAPER e nessuna configurazione Toro applicata.

## Backup, chiavi e riferimenti

- Copia cifrata age sul PC: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica il backup o restore sulla VPS.
- `work/extbackup-bot-stopped-20261109`: backup esterno preparato, non installato.
- RC84 [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta riferimento storico.
- Storici ed EventJournal devono restare integri. Nessun segreto, token, passphrase, chiave privata o dettaglio d'accesso VPS è registrato.

## Problemi e prossimo passo

1. Attendere senza rilanciare; verificare stato finale della unit, log e presenza del report.
2. Se il replay termina, registrare coverage, SHA dati, conteggio segnali/trade, costi, benchmark casuale, risultati per periodo/asset e tutti i gate preregistrati.
3. Mantenere fail-closed l'audit MTM e anti-lookahead: anche statistiche positive non autorizzano automaticamente shadow, integrazione o rischio.
4. Produrre separatamente il report tecnico dettagliato di Brain richiesto dall'utente; non confonderlo con questo test Toro.
5. Nessun merge/deploy/riattivazione o modifica rischio senza mandato separato.

## Limiti di accesso

Sono state consultate le evidenze GitHub, la copia Library e i progressi recenti effettivamente recuperabili. Non sono disponibili trascrizioni integrali di chat eliminate né un controllo indipendente dello stato live VPS; lo stato della unit deriva dall'output Termius registrato nel commento PR.
