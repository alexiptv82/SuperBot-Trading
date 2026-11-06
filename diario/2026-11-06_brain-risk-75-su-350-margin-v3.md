# SuperBot V3 — Brain: rischio PAPER 75 USDT su 350 di margine, adattivo 20–50x

Checkpoint 2026-11-06 — richieste esplicite utente; GPT-6. **Solo codice su PR #62 in BOZZA; nessun merge, deploy, riavvio, VPS o modifica alla run preparata.**

## La richiesta
- Brain capitale iniziale 2.000 USDT PAPER, margine operativo fino a 350–400 USDT, leva obbligatoria 20x–50x.
- Limite nuova perdita allo stop **75 USDT stimati su 350 USDT di margine**, scala proporzionalmente su importi superiori: 400 USDT -> 85,7142857 USDT. È il **21,4285714285714285% del margine**; 75 è il 3,75% di equity iniziale e 85,71 è il 4,285714% del capitale iniziale.
- Tutte le restanti protezioni confermate: rischio aperto 5% equity (100 USDT all'avvio), floor 450, daily warn/halt 35%/50%, TAKE/STOP esistenti, margine totale 40%=800 USDT come precedentemente proposto.

## Modifica incrementale applicata SOLO nel branch RC
- PR #62, commit **047d2b23a33cbfa145d46e884b2c2927521110fe** sul branch `work/v3-release-candidate-gpt6-20261106`.
- `backend/v3/risk.py`: `RiskPolicy` opzionale con `max_loss_margin_fraction`, `min_leverage`, `max_leverage`. `quote_paper_risk` impone simultaneamente rischio equity 4,285714%, rischio/margine 21,42857% sul **margine effettivamente calcolato**, range leva20–50, buffer liquidazione e tutte le soglie preesistenti. Una perdita allo stop è solo teorica, gap/liq/commissioni superiori possono eccederla.
- `backend/v3/brain_f2/engine.py`: su profilo opzionale, prova leve inferiori dentro20–50 prima di respingere trade incompatibile. Esempio 50x con stop0,5% -> 32x; se nemmeno20x è compatibile, `NO_TRADE`; nuova provenienza allowlisted `risk:leverage_adjusted`.
- `backend/v3/runner/config.py`: legge le tre nuove chiavi SOLO se tutte presenti, preserva formato legacy e `RiskPolicy` default. Il policy hash originale resta IDENTICO sui classici/default; la nuova policy usa un hash differente.
- `backend/v3/runner/runner_config_brain2000_paper.json`: `initial_equity=2000`, `max_loss_fraction=0.042857142857142857`, `max_open_risk_fraction=0.05`, `max_position_margin_fraction=0.20`, `max_total_margin_fraction=0.40`, `max_loss_margin_fraction=0.214285714285714285`, `min_leverage=20`, `max_leverage=50`. Altre chiavi INVARIATE.
- `backend/tests/test_v3_brain_risk_75_profile.py`: 11 test nuovi con perdita stimata ≤75 su350 e ≤85,714... su400, range leva, rifiuto stop incompatibile, budget5% condiviso, mantenimento hash legacy, parser rigido, adeguamento leva AI.

## Verifiche
- **419/419 test mirati PASS**, nessun guasto in risk, runner config, Brain F2, runner cycle/e2e e 11 test del nuovo profilo. Modulo di rischio puro, dati sintetici. Non dimostra performance di trading, gap o profitti.
- Prova numerica: con stop compatibile e leva20, margine **350**, perdita stimata **74,99999965**; margine **400**, perdita stimata **85,71428531** USDT. Includono buffer costi stimati16 bp, non garantiscono esecuzione reale.
- CI PR #62 (`v3-dashboard-ci`) avviata a seguito del commit; prima di dichiarare la RC verde consultare il risultato finale GitHub.

## Vincoli ancora aperti / NO-GO deploy
- Il 5% complessivo del portafoglio resta invariato: dopo posizione rischio75, solo25 USDT rischio residuo. Due posizioni a rischio massimo non possono coesistere; NON ho aumentato questo limite in assenza di richiesta.
- A20x questo budget permette circa **0,91%** di movimento prezzo avverso prima dei costi stimati; a50x solo circa **0,27%**. Il Risk Manager sceglie leva minore quando possibile; se stop più distante resta matematicamente incompatibile, rifiuta e non forza chiusure.
- **La run Brain2k già preparata in pausa sulla VPS era associata al profilo precedente**. Non modificare `runner_config.json`, mandato o journal **in-place**: serve predisporre una nuova run PAUSED/UNAPPROVED con fingerprint e policy hash nuovi dopo gli ulteriori gate, con storico vecchio preservato.
- NO merge, NO deploy, NO riavvio Falco/Toro/Brain, NO modifica posizioni vecchie. Falco/Toro non toccati.

## Archivio
- `/SuperBot-Trading/SuperBot-V3-Brain-Risk-75-Su350-Optin-PAPER-2026-11-06.zip` SHA-256 `79b6f912468b29222ad50d2be12ec36b84a08b3b06e585ca03834c52e915a0ef`, Library `libfile_8b1218f892ec8191aae9d5d6485fcdb3`.
- `/SuperBot-Trading/RAPPORTO_BRAIN_V3_RISK_75_SU_350_2026-11-06.md` SHA-256 `6a99e69c4e9d0d06cca2de24a9632eac2bef514a030cb88a72031fcb04abc04a`, Library `libfile_877e4b9ff5a4819185dcaae4f748b124`.