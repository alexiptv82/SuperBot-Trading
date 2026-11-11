# 11/11/2026 — Verifica effettiva: Falco, Toro e Brain tutti PAPER RUNNING

L'utente ha riferito che la dashboard mostra tutti e tre i portafogli in funzione, senza trade aperti. **Verifica indipendente recuperata dai log GitHub Actions**: [run #43055462087](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43055462087) SUCCESS, controllo VPS alle 16:09 UTC (~17:09 Europe/Rome).

```text
PAPER_START_ACTIVATION_MODE=paper_running
PAPER_START_COOLDOWN_ELAPSED_MINUTES=30
PAPER_START_BRAIN_MANDATE_APPROVED=True
PAPER_START_FALCO_SERVICE_ACTIVE=True
PAPER_START_FALCO_PAUSE_FLAG_PRESENT=False
PAPER_START_FALCO_HEARTBEAT_MODE=running
PAPER_START_FALCO_HEARTBEAT_FRESH=True
PAPER_START_TORO_SERVICE_ACTIVE=True
PAPER_START_TORO_PAUSE_FLAG_PRESENT=False
PAPER_START_TORO_HEARTBEAT_MODE=running
PAPER_START_TORO_HEARTBEAT_FRESH=True
PAPER_START_BRAIN_SERVICE_ACTIVE=True
PAPER_START_BRAIN_PAUSE_FLAG_PRESENT=False
PAPER_START_BRAIN_HEARTBEAT_MODE=running
PAPER_START_BRAIN_HEARTBEAT_FRESH=True
PAPER_START_BRAIN_EXIT_HEALTHY=True
PAPER_START_WEB_STILL_READONLY_WITH_SINGLE_CLOSE_ONLY=PASS
PAPER_START_FABLE_NOT_DEPLOYED=PASS
RC84_THREE_PAPER_BOTS_RUNNING_AFTER_20M_COOLDOWN=PASS
```

**Stato operativo confermato**: Falco/Toro 1.000 USDT PAPER ciascuno, Brain 2.000 PAPER. I tre servizi girano, tutte le pause rimosse dopo cooldown, mandato Brain PAPER approvato, owner uscite Brain sano, web continua a proteggere start/reset/bulk e consente solo singole chiusure PAPER. Fable NON è installato nel runner attivo. Zero trade aperti secondo osservazione diretta dell'utente: **non confermato indipendentemente dal workflow**, che controlla lo stato dei motori e dei heartbeat, non il conteggio delle posizioni. Non trasformare assenza di trade in bug senza analizzare decisioni/cicli: Brain usa 60 minuti, NO_TRADE valido, i classici hanno propri filtri.

La vecchia automazione ChatGPT `6af48c99fcec819190cd468c506523e7` aveva indicato verifica non conclusiva per mancata restituzione iniziale del workflow dal connettore; successivamente è stata recuperata la run GHA e letto il log SUCCESS. Non ripetere Actions inutilmente, quota limitata.

**Prossimo controllo**: al primo ciclo completo, inspect read-only del numero decisioni Brain, esito DeepSeek, errori provider, filtraggio segnali Falco/Toro, nessuna apertura forzata; successivamente prima chiusura manuale PAPER effettiva verificata su PnL e learning. Nessuna modifica ai parametri, motori o ordini in questo checkpoint.
