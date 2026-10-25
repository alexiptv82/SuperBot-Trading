# Claude chat ↔ Singapore VPS — MCP diagnostico (PREPARAZIONE, NON INSTALLATO)

**Stato: branch isolato di preparazione. Nessun servizio installato, porta aperta o bot modificato.**
Tutto su questo branch è **proposta da revisionare**; `rule-pool` e runtime `297b126` non vengono toccati.

## Architettura e limiti
1. MCP HTTP in container indipendente `superbot-claude-mcp-ro` non privilegiato.
2. Mount read-only di **sole** directory PAPER Hawk/Bull e shadow DeepSeek. Mai socket Docker, SSH agent, cartelle con chiavi, backup, app mobile o directory HiTV.
3. Strumenti esposti: `bot_status`, `bot_positions`, `bot_recent_events`, `bot_lessons_check`, `deepseek_shadow_status`, `deepseek_recent_decisions`.
4. Nessuna shell generica, riavvio, deploy, operazione trade, editor, comando Docker o risposta AI grezza esportata.
5. Listener solo `127.0.0.1:8765` sul VPS. Per la chat Claude serve un endpoint **HTTPS pubblico** via tunnel/reverse-proxy autenticato, per esempio Cloudflare Tunnel su un dominio dell'utente.
6. Il server usa `Authorization: Bearer <token_segreto_casuale>` con confronto a tempo costante. Nessun token nei file GitHub o nei messaggi della chat.
7. Docker image in modo read-only, non-root, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, `--pids-limit`, `--memory`, `--cpus`, `--mount type=bind,readonly` solo dati PAPER.
8. Esporre HTTPS soltanto **dopo** aver configurato autenticazione e verificato che richiesta senza bearer riceva 401. In Claude, il percorso è `Customize → Connectors → Add → Custom → Web`; URL remoto HTTPS .../mcp. Nel dialogo usare **No sign in → Request headers** se la funzione è presente. Se non appare, serve OAuth: **non** rendere pubblico un endpoint anonimo.
9. Gli strumenti leggono file fino al ciclo/snapshot disponibile. **Non** fanno polling exchange e **non** interpretano i prezzi persistiti come quotazioni live.

## Fasi successive — richiedono nuovo OK esplicito
- Fare code/security review della preparazione (import SDK, auth, limiti, permessi mount).
- Risolvere il requisito hostname HTTPS (dominio Cloudflare o altra soluzione TLS gestita) e scegliere autenticazione supportata dall'account Claude.
- Salvare una chiave accesso lunga e casuale fuori dal repo, predisporre meccanismo di revoca.
- Prima di ogni modifica VPS: backup verificato, controllo porte/firewall, deployment indipendente, rollback senza fermare Hawk/Bull/DeepSeek/HI-TV. Nessun deploy su `rule-pool`.
- Test locali Python MCP, poi HTTPS con autentico client MCP e un test Claude da browser, mostrando all'utente quali strumenti vengono esposti.

## Nota importante
La semplice connessione GitHub di Claude **non** gli permette di leggere via SSH né di collegarsi al socket Docker sul VPS. Questo connettore sarà un servizio nuovo isolato, abilitato solo dopo la tua autorizzazione al rilascio.
