# Laboratorio "modifica long" (P1) — esito — 29/10/2026 (Claude)

## Richiesta dell'utente (13:22)
Lavorare sulla modifica long (Fix P1 "sbias LONG", commit `635b964`, in stand-by): dire se si puo' migliorare, cercare informazioni, elaborare una versione piu' affidabile che non faccia regredire il bot.

## Cosa e' stato fatto (solo laboratorio offline, nessun bot/deploy/file di produzione toccato)
- Ramo isolato `work/long-lab-claude-20261029` (da `rule-pool` `fed2e3f`), solo `backend/long_lab_claude/**` e un workflow dedicato; **mai unito a `rule-pool`**.
- Codice vero del 13/10 (`read_symbol`, `rules_decisions`, `PaperAccount`, `desk.regime`) su ~18 mesi di candele 15m pubbliche Bitget (26 simboli), costi del motore, soglie di produzione. Punteggio del laboratorio identico a `read_symbol` (test barra per barra, anche con P1).
- Criteri G1–G9 e varianti scritti PRIMA dei risultati (`PREREGISTRAZIONE.md`; errata dichiarate: placebo della famiglia sbagliata, corretto; criteri invariati).
- Rapporto: `backend/long_lab_claude/RAPPORTO.md` (commit `1231c98`), tabelle in `results/report.md`; copia nel Project: `claude/laboratorio-modifica-long-2026-10-29.md`.

## Esito
1. Il bonus "rimbalzo" di P1 non cambia nulla: scatta 4240 volte, 22–26 decisioni cambiate, 0 nuovi long aperti (il punteggio long in quei momenti e' ~0, lo short ~57).
2. Il peso 4h 20→14 non corregge i long: dimezza le aperture (5084→2529 trade simulati); il netto "migliora" solo perche' ogni trade medio perde. Stesso effetto con soglie +6 e con un P1 a bonus casuale (placebo): G5 e G7 falliti.
3. Il segnale di rimbalzo di P1 non ha vantaggio proprio (long dopo RSI<35 e momentum positivo: −0,196 R contro −0,179 R a caso; su BTC/ETH/oro/argento −0,43 R, peggio in modo significativo). Coerente con Zaremba et al. 2021 (momentum nelle crypto grandi, inversione solo nelle illiquide).
4. Versioni nuove (`g_long`, `t_bonus`, `t_bonus_g`, `r_reb`, `ref_gate`): **nessuna** passa i criteri. Regola pre-registrata: nessuna modifica long da rilasciare, **il 13/10 resta com'e'**.
5. Il punteggio di base non ha potere predittivo misurabile: senza costi R −0,004, con costi −0,160; l'unico filone con un piccolo segnale lordo e' `t_bonus` (inversione di mercato confermata), instabile col costo e con la stagionalita'.

## Limiti da sapere
- La replica non riproduce l'entita' dei giorni d'oro (12–16/10: R +0,06, 43% vittorie; bot veri 12–15/10: R +0,54, 61%), pur riproducendo struttura e lato dei trade. Quindi i valori assoluti della replica sono probabilmente pessimisti; i confronti tra varianti restano validi. Causa non misurata.
- Un solo periodo di 18 mesi; i long reali del 12–26/10 sono 13 su 247.
- Importi del laboratorio sono simulati; nessun saldo reale riportato.

## Conferma dello screenshot dell'utente (13:45)
Il numero cerchiato `9fa667f` e' il commit di "deploy desk (calendario di Claude)" del 13/10, cioe' lo stesso codice riportato oggi (ora `0ad6893`, merge commit: 9 moduli su 10 identici byte per byte, `engine.py` +10 righe di adattatore di sola lettura, Dockerfile aggiunge solo tzdata).

## Prossimi passi proposti (servono decisioni dell'utente)
1. P1 resta in stand-by: considerarla chiusa.
2. Test di fedelta' con candele da 1 minuto (solo laboratorio) per spiegare il divario replica-reale e verificare se il paper e' ottimista.
3. Laboratorio "dove guadagna il bot" (condizioni di mercato, costi/ordini limit, soglie) pre-registrato e con validazione fuori campione.
4. Ancora aperti da prima: aggiornare la guardia di baseline di `desk-deploy.yml` (`dc16e01` → `0ad6893`) prima di qualunque deploy bot (con OK utente); pagine Brain da rinominare (ChatGPT); l'utente avvia i bot a mano (finestre Claude: 29/10 14:30–18:30, 30/10 00:00–04:00, 31/10 08:00–12:00, ora svizzera).

AI: claude
