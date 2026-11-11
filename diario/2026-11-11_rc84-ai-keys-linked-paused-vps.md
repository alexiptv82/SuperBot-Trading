# 11 novembre 2026 — Claude (Falco/Toro) e DeepSeek (Brain) collegati ai NUOVI motori PAPER

**ESECUZIONE REALMENTE COMPLETATA:** [GitHub Actions 42993907491](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42993907491), stato completed / conclusion success, job 130433114497 SUCCESS, ~09:17 UTC / ~10:17 Europe/Rome, 11/11/2026.

L'utente ha autorizzato «perfetto puoi andare avanti» dopo la conferma di risoluzione del 403 web. L'ambito operativo qui è **solo collegamento delle API key AI esistenti ai nuovi servizi PAPER IN PAUSA**, senza trading, modello a pagamento, deploy web o modifica dati legacy.

## Esecuzione e riscontri diretti

- Preparato script a esecuzione singola `deploy/scripts/v3-rc84-connect-existing-ai-paused-only.py` su ramo `work/paper-restart-prep-20261110`, commit `dbdc0811eea4460eeb959129a734804e6669292a`; workflow specifico `.github/workflows/v3-rc84-connect-paused-ai-once.yml`, PIN esatto, trigger `deploy/v3-rc84-connect-paused-ai.trigger` commit `58ab4c955d2d9fe43ee43842003a967d9b9c9115`.
- Guard preflight in sola lettura sulla VPS: `RC84_AI_THREE_WALLETS_PAUSED_AND_EXIT_HEALTHY=PASS`, presenza Claude in vecchi container fermi Falco/Toro e DeepSeek nel vecchio Brain, `RC84_AI_THREE_NEW_TARGETS_AVAILABLE=True`, `RC84_AI_PRECHECK_PASS_NO_FILES_WRITTEN=True`.
- Operazione di provisioning: credenziali lette **solo in memoria all'interno della stessa VPS** dall'environment Docker dei vecchi container PAPER **fermi**, senza scrivere valori nei log, chat o GitHub. Solo tre chiavi modello, **nessuna chiave exchange**, in directory `/etc/superbot-v3-paper` privata root e file `0600`:
  - `falco-ai.env`: `ANTHROPIC_API_KEY`.
  - `toro-ai.env`: `ANTHROPIC_API_KEY`.
  - `brain-ai.env`: `DEEPSEEK_API_KEY`.
- Restart **solo di tre servizi nuovi** per leggere EnvironmentFile: `superbot-v3-paper-falco.service`, `superbot-v3-paper-toro.service`, `superbot-v3-paper-brain-runner.service`. Non riavviati `superbot-v3-paper-brain-exit`, i due exit-worker classici legacy o i vecchi container, e non toccata la web.
- Runtime verificato **senza emettere valori** confrontando le variabili con `/proc/PID/environ` internamente: `RC84_AI_CLAUDE_FALCO_LOADED_AND_PAUSED=True`, `RC84_AI_CLAUDE_TORO_LOADED_AND_PAUSED=True`, `RC84_AI_DEEPSEEK_BRAIN_LOADED_AND_PAUSED=True`. `RC84_AI_ALL_THREE_HEARTBEATS_PAUSED=PASS`. `RC84_AI_BRAIN_EXIT_AND_LEGACY_UNCHANGED=True`.
- `RC84_AI_KEYS_NOT_PRINTED_OR_UPLOADED=True`, `RC84_AI_ZERO_PROVIDER_REQUESTS_AND_ZERO_TRADES=True`.
- **Nessuna nuova posizione/trade** e nessuna chiamata pagata a Claude o DeepSeek in questa operazione. **I modelli NON sono stati testati con richieste vere:** la presenza in memoria del processo non dimostra chiave ancora valida o disponibilità credito.

## Stato esatto di SuperBot

| Componente | Stato |
|---|---|
| Falco | Nuovo portafoglio 1.000 USDT PAPER, servizio attivo IN PAUSA, Claude key caricata |
| Toro | Nuovo portafoglio 1.000 USDT PAPER, servizio attivo IN PAUSA, Claude key caricata |
| Brain V3 | Nuovo portafoglio 2.000 USDT PAPER, motore attivo IN PAUSA, DeepSeek key caricata; mandato approved=false |
| Brain exit sidecar | Ancora attivo/sano, stesso owner |
| Web pubblica | Dashboard RC84 con Brain in Performance e Impostazioni; 403 permessi risolto e confermato funzionante dall'utente |
| Vecchio storico / RC84 e RC73 di rollback | Non modificati |

## Gate finale prima delle aperture PAPER (NON eseguito)

1. **Confermare disponibilità/credito dei provider AI con approccio economico e autorizzato**, soprattutto DeepSeek: l'utente aveva precedentemente avuto credito esaurito. Evitare test AI inutili; eventuale singola richiesta minima deve rispettare daily cap e non innescare fallback meccanico indesiderato.
2. **Ripristinare pulsanti manuali Chiudi ora** per le nuove run, mantenendo percorso singola chiusura e registrazione learning. Attualmente web opera `V3_CUTOVER_READONLY=1` e single-close disabilitati: non riavviare trading senza protezioni di uscita e possibilità di stop.
3. Prima di rimuovere pause e approvare mandato Brain: consenso utente distinto. Garantire SOLO PAPER, profilo Brain 20–50x, size max 400, equity floor 450, cooldown 15–30 min, non forzare slot, NO_TRADE accettabile, nessuna chiusura forzata mezzanotte. Nessun ordine reale.
4. Monitorare risultati PAPER e reali decisioni AI, senza promettere profitti. Evitare nuove suite/Actions pesanti prima del 1 dicembre.

**Resta vietato condividere segreti in chat, diary o GitHub.** Le chiavi sono state collegate sul server, non sono state ricreate o ruotate. Il riconoscimento del successo si basa sul job SUCCESS e su righe del log effettivamente lette.
