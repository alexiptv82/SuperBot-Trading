# 29 ottobre — Classici: gate riconciliazione delle 146 posizioni

Utente chiede «Okay, quindi come procediamo?» a seguito di backtest completo 26 simboli che NON replica le golden. Con autorizzazione precedente allo sviluppo offline, ChatGPT ha creato il modulo di audit read-only delle posizioni originarie, sul ramo **work/classics-12oct-selective-lab-20261029**:
- backend/rollback_lab/tape_audit.py
- backend/tests/test_classics_tape_audit.py
- .github/workflows/classics-12oct-tape-ci.yml
- backend/rollback_lab/GOLDEN-TAPE-GATE-2026-10-29.md

**CI Actions 40824613230 SUCCESS (3/3 test)**, nessun accesso VPS, nessuna mutazione a bot, portafogli, Brain, deploy, journal o vault. Input: archivio read-only 27/10, 357 posizioni totali; 146 nelle golden Hawk#2/Bull#1 e prime crisi Hawk#3/Bull#2. SHA256 input: 0d1252e15d5d07c7dc7fa61789648e0a45d9383e7efc783852439ceaf95ff281.

| Metrica | Prime golden (93) | Prima crisi (53) |
|---|---:|---:|
| Netto USD | +1861.3621 | -429.5490 |
| Aperture source=rules | 93 | 53 |
| TP | 54 / +2742.5785 USD | 14 / +486.2971 USD |
| SL | 34 / -911.3879 USD | 20 / -660.2772 USD |
| Close label modello-o-regole | 4 / -39.2171 USD | 16 / -225.4920 USD |
| Manual | 1 | 3 |
| Exit version missing | 93 | 0 |
| Entrate senza metadati | 4 | 0 |

**NON attribuire a Claude** le 16 chiusure della crisi: la stringa «model_or_rule_close_labeled_claude» non e' prova della fonte! Serve identificazione tramite risposte AI e log originali per simbolo/timestamp. Anche la quota maggiore puo' dipendere dal regime di mercato; non prova causalita'.

Le golden sono state aperte con versioni inferite: a0afc63 6 posizioni, 7ced3a6 35, 9fa667f 51, unknown 1; non esiste una singola golden SHA 12/10. Una SHA di commit deploy trigger non implica una modifica di trading.

**Fase successiva da sviluppare su branch isolato**:
1. Per le 20 chiusure ambigue delle golden+prima crisi e le 4 manuali, cercare attributo fonte decisione/azione/log di allora; usare UNKNOWN se assente.
2. Replay di sole uscite sulle aperture REALI di positions.csv, alimentate da stesse candele registrate e stop-prima nelle ambiguita' OHLC; misurare fedelta' PnL e trade durations.
3. Replay degli ingressi solo quando disponibili veri snapshot di mercato e decisioni storiche, confronto trade-by-trade. Congelare golden, verificare crisi come out-of-sample.
4. Valutare patch classici soltanto dopo certificazione della fedelta' e nuova autorizzazione al deploy, previo backup/restore e piano posizioni aperte. Nel frattempo **nessuna modifica classici**.

Link CI: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40824613230
Link documentazione ramo lab: https://github.com/alexiptv82/SuperBot-Trading/blob/work/classics-12oct-selective-lab-20261029/backend/rollback_lab/GOLDEN-TAPE-GATE-2026-10-29.md

AI: chatgpt (chat normale)
