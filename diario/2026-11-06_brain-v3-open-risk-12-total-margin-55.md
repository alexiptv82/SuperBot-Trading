# SuperBot-Trading V3 — Brain PAPER: rischio aperto complessivo 12%, margine complessivo 55%

**Checkpoint:** 6 novembre 2026. **Ambito:** solo profilo Brain 2.000 USDT PAPER, nessuna modifica a Falco/Toro, nessun deploy/merge/start/restart VPS. **PR #62** branch `work/v3-release-candidate-gpt6-20261106` resta draft.

## Decisione dell'utente e stima
- L'utente ha approvato rischio stimato `75 USDT su 350 USDT` per singola posizione (21,4285714% del margine), massimo margine singolo `400 USDT`, leva `20x–50x`; ha chiesto di adeguare il rischio complessivo da 5% ad almeno 10%, delegando un livello superiore.
- Scelto **12% di rischio aperto totale** sull'equity corrente, cioè **240 USDT iniziali** con 2.000 USDT PAPER.
- Per non rendere il 12% cosmetico, scelto **55% massimo margine totale** sull'equity corrente, cioè **1.100 USDT iniziali** (dal precedente 40% =800).
- Restano invariati `max_loss_fraction 0.042857142857142857` per singolo trade (fino a ~85,71 USDT iniziali), `max_loss_margin_fraction 0.214285714285714285`, `max_position_margin_fraction 0.20` (400 USDT iniziali), min/max leverage 20/50, floor equity 450, daily warning/halt 35%/50%, ciclo AI e budget.

## Coerenza quantitativa
- Un trade margine350 → rischio stimato max75 USDT; due → 150; tre → 225, margine totale1.050 <1.100 e rischio225 <240.
- Due trade margine400 → 171,43; due400 + uno300 → teorico235,71 con margine complessivo1.100.
- Tre trade da400 non sono tutti ammissibili a dimensione piena: 1.200 USDT di margine e257,14 USDT di rischio superano entrambi i tetti.
- Poiché la perdita stimata è limitata al 21,42857% del margine effettivo, 1.100 USDT di margine totale comportano un massimo **~235,71 USDT / 11,79% equity iniziale** nel modello; la policy 12% resta un limite ulteriore. Nessuna soglia garantisce le perdite effettive in caso di gap, slippage o liquidazione.
- Profili ereditati/classici: nessun cambio; configurazione standard Brain1000 mantiene i limiti originali.

## Sorgenti e verifica
- PR #62 commit `ff98f7ee23681420f77bb50ff0f84efc61469204`: SOLO `backend/v3/runner/runner_config_brain2000_paper.json` (due valori da `0.05` a `0.12`, `0.40` a `0.55`) + due moduli test nuovo/aggiornato + aggiornamento test RC2000.
- Follow-up test-only commit `b9a611f5fcc7360e7b2085d22e3482575cb7f383`: corregge ultimo confronto del dataclass `max_open_risk_fraction` rimasto a 5%; nessun comportamento runtime cambiato.
- Locali mirati: **461 PASS in 4.16s** su rischio, profilo, runner config, cycle, e2e, daily loss, contratti, inclusi test tre posizioni da350. Full local test V3 interrotto a ~21% per timeout, non dichiarato superato.
- GitHub CI SHA `ff98f7ee`: backend/frontend verdi e 4068 PASS V3, **1 FAIL** dovuto esclusivamente a test RC2000 che si attendeva 5%. Corretto nello SHA `b9a611f5`; controllare risultato CI su quest'ultimo commit prima di dichiarare il ramo verde. Test classici indipendenti.

## Archivio persistente
- Library `/SuperBot-Trading/SuperBot-V3-Brain-Rischio-Aperto-12pct-PAPER-2026-11-06.zip`, SHA256 `3bf05addd74be62bebd3f4e22e30101f90c86d145f60ec926715e226769fec55`, libfile `libfile_efb971a279c88191abd00a23c46f7877`.
- Library `/SuperBot-Trading/RAPPORTO_SUPERBOT_V3_BRAIN_RISCHIO_TOTALE_12_2026-11-06.md`, SHA256 `6213c77e02828476b6c82c567de5534f5797f1dded71f17a904fd3386d9cc7ad`, libfile `libfile_4b8d0fc2a49c8191a5fe2e3d2eaa2e30`.

## NO-GO al deploy
Nuovo profilo modifica il fingerprint SHA della configurazione e il `policy_hash` del mandato Brain. La directory Brain2k già predisposta sulla VPS resta associata al profilo precedente e deve rimanere in pausa. **Non sostituire file o mandate in-place**. Solo dopo i restanti gate RC/VPS e l'approvazione specifica del rilascio si potrà creare un'altra run PAPER isolata, inizialmente PAUSED e con mandato non approvato, conservando storico e backup. Nessun merge, deploy, restart o disattivazione pause in questo step.