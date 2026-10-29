# Gate 2: riconciliazione delle prime 146 posizioni PAPER (29/10/2026)

Test automatizzati **40824613230 SUCCESS**: 3 regressioni superate, nessun deploy/SSH/ordine/live. Fonte unica esportazione read-only del 27 ottobre sul ramo diario: diario/analisi-run-2026-10-27/positions.csv; SHA256 0d1252e15d5d07c7dc7fa61789648e0a45d9383e7efc783852439ceaf95ff281. Modulo backend/rollback_lab/tape_audit.py; output JSON artifact Actions.

## Statistiche riconciliate

| Indicatore | Golden Hawk#2 + Bull#1 | Prima crisi Hawk#3 + Bull#2 |
|---|---:|---:|
| Posizioni | 93 | 53 |
| Netto USD | +1861.3621 | -429.5490 |
| Aperture registrate rules | 93 | 53 |
| TP / netto | 54 / +2742.5785 | 14 / +486.2971 |
| SL / netto | 34 / -911.3879 | 20 / -660.2772 |
| Model-or-rule labeled Claude / netto | 4 / -39.2171 | 16 / -225.4920 |
| Chiusure manuali | 1 | 3 |
| Versione uscita non registrata | 93 | 0 |
| Metadati entry mancanti | 4 | 0 |

**ATTENZIONE:** la classificazione «model_or_rule_close_labeled_claude» NON dimostra che Claude abbia preso la decisione di chiudere. Gli ingressi sono source=rules; la fonte delle uscite resta da identificare e la frequenza maggiore puo' dipendere anche dal mercato.

Versioni d'ingresso inferite nelle golden: a0afc63 (6 posizioni), 7ced3a6 (35), 9fa667f (51), sconosciuta (1). Prima crisi: 5818aee (2) e b4709d1 (51). La golden non e' una singola versione 12 ottobre. Inoltre i commit 9fa667f, 5818aee e altri possono essere trigger di deploy, non mutazioni di scoring.

## Procedura successiva, tutta offline

1. Identificare tutte le 20 chiusure ambigue del gruppo storico e le 4 manuali; associare a ciascuna evento, prompt/risposta AI e cambio di codice verificabile. Se non documentabile, autore UNKNOWN.
2. Replay di sole uscite **partendo dalle posizioni vere**: stesso simbolo, lato, ora, prezzo, margine, leva, stop, target; fare avanzare i motori di uscita sulle medesime candele storiche. Annotare ambiguita' dell'intrabar 15m e usare stop-prima in caso di conflitto.
3. Ricostruire gli ingressi con snapshot point-in-time, score, ranking, fallback AI e dimensionamento. Misurare trade matching con criterio simbolo+lato+finestra temporale e delta prezzo.
4. Congelare l'esperimento una volta riprodotte le golden e applicarlo senza tuning alle prime crisi e ai periodi successivi. Nessun rollback finche' la fedelta' non e' certificata.

Dati storici disponibili per fonte: state_v2.json, trade_history.jsonl, learning_log.jsonl in archivi auditati; non e' verificato che esistano tutte le risposte AI o tutti i prompt. Prima di un eventuale audit diretto del VPS occorre confermare accesso e autorizzazione specifica.

**Mai toccati** classici, Brain, VPS, posizioni, vault, journal o deployment. Questo e' lavoro su branch di laboratorio e non attiva ordini.

AI: chatgpt (chat normale)
