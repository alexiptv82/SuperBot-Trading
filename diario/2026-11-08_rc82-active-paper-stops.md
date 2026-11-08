# 2026-11-08 — RC82 stop PAPER attivo

Diario sul branch RC82, non sul branch canonico `diario`.

Base verificata sul remoto: `29eb75750625a8819cd2db71dc2459d164c3199c`, branch `cursor/rc81-stop-telemetry-ui-chatgpt-20261108`, PR #78. Nessun commit su quella PR.

Audit del ciclo attivo Falco/Toro (`backend/desk/cli.py`, `backend/desk/engine.py`) con dati sintetici. Confermati, poi corretti in modo minimo:

- barra futura e minimo zero non possono più liquidare;
- il feed assente, vecchio o ultimo prezzo inutilizzabile mette `stop_feed.alarm` e `stop_certified=false` nel heartbeat;
- lo stop di una candela già chiusa è valutato prima del DCA che potrebbe allargarlo; un secondo passaggio applica uno stop stretto nello stesso ciclo;
- il riavvio dopo un salvataggio fallito non duplica la riga di storico.

Non sono stati cambiati formula, leva, size, capitale, prompt o il prezzo che `on_bar` assegna a stop, target e liquidazione. Claude resta consultato secondo chiave e calendario: lo stub non esce in rete.

Test locali: 11 casi RC82 dentro la suite da 95 con `test_desk.py` (95 passed) e 67 passed fra exit-only, RC78 e RC80. Workflow di push e pull_request non includono `cursor/**`: il push di questo branch non è un deploy. `[skip ci]` è solo un segno in più.

Prossimo passo: revisione indipendente. Non è una certificazione di stop né un via libera al riavvio. PR #77 e #78 non vanno toccate.
