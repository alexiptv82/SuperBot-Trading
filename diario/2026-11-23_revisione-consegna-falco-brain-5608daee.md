# 2026-11-23 — Revisione ChatGPT consegna Claude Falco Evoluto / Brain Scalp 5608daee

## Verifiche effettuate
- Ramo remoto `claude/falco-evoluto-20261123` è al commit esatto `5608daeebf20c57ce1e1edffbdeb4a401042d89a`.
- Fonte controllata: `docs/falco-evoluto/PROPOSTA.md`, `backend/v3/guardian.py`, entrambe le configurazioni `runner_config_{falco_evoluto,brain_scalp}_paper.json`, configurazione loader, ciclo e runner, bridge close e compare.
- Il codice e le configurazioni del Guardian e confronto esistono; il report di Claude dichiara 5.485 V3, 158 builder, 169 Jest PASS, non rieffettuati autonomamente da ChatGPT.
- Nessuna prova di installazione run nuove o di pausa RC1: sudo root non disponibile all'operatore `superbot-agent`. Non dichiarare pausa completata.

## Criticità prima del GO
1. Manual close per due nuove run: `backend/v3/close_bridge_server.py` sceglie **una sola** run Brain con `V3_BRIDGE_BRAIN_RUN_DIR` e `V3_BRIDGE_BRAIN_RUN_ID`. La pagina compare è readonly; implementare bridge PAPER single-position multi-run validato da allowlist e verificare autenticazione, mutex/exit writer, idempotenza, identità run, segreti mai esposti, nessun close-all. Prova end-to-end su due journal isolati prima di attivazione.
2. Profilo Falco: config `max_total_margin_fraction=0.95`, `minimum_equity=450` su 1000; Brain `0.50`, floor `1600` su 2000. Questa asimmetria altera confronto e resilienza di Falco. **Proposta (non approvata dal proprietario):** Falco 0.50 come Brain, floor Falco 800 (80% equity iniziale, coerente con Brain), preservando limite storico >=450; se si vuole esposizione 95% va giustificata come differenza sperimentale deliberata.
3. Costo AI Brain stima ~0.77 USD/24h a cicli 30m vs cap 0.75; prevedere budget stopping e quote reali, senza chiamate extra forzate. Non aumentare cap senza OK.
4. In Guardian, trigger +8%: Brain da 2000 è +160, Falco da 1000 è +80. Floorkeep 75% e drawdown globale di HWM contabilizzato in funzione della MTM attuale; non garantisce conservazione dei profitti se posizioni aperte, gap e slippage.
5. Leva 15-45x / risk max20% margine può imporre NO_TRADE frequenti: Brain 450x45=20250 notional, 16bp cost buffer=32.40, max equity risk4% 80 -> distanza stop ammissibile circa 0.235%; non forzare chiusure/stop stretti.
6. Test E0 storico inconcludente (30 trade e 10 sessioni non raggiunti), Guardian valido come controllo di esposizione ma non dimostrato che migliori il rendimento atteso.

## Prossimo lavoro raccomandato
- Proseguire sullo stesso ramo, senza un'altra architettura: (a) single-position manual close sulle due nuove run; (b) revisione/proposta allineamento margine/floor per confronto; (c) dry-run deploy e test end-to-end, con mandati approved:false e servizi non partiti; (d) verifica pausa Brain RC1 con una sola esecuzione root autorizzata e log verificabile.
- Nessun GO/deploy/merge/riavvio senza approvazione esplicita utente. Solo PAPER.