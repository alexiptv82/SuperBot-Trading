# Checkpoint verificabile — Brain preflight VPS parziale; DeepSeek non chiamato

**Data:** 13/11/2026 12:47 Europe/Rome  
**Ambito:** sola documentazione; trading esclusivamente PAPER; nessuna modifica operativa eseguita da questo checkpoint.

## Sintesi per la ripresa

La priorità utente resta **Brain PAPER**. Falco SHORT originale resta congelato e Toro LONG/Twin resta sospeso. Il preflight preparato per Issue #95 è stato eseguito sulla VPS secondo il riscontro testuale pubblicato nel commento dell'Issue, ma l'esito è soltanto parziale: Brain è rimasto in pausa, il ciclo isolato si è fermato su dati non disponibili prima dell'inferenza, DeepSeek **non è stato chiamato**, non sono state prodotte decisioni e non è stata provata alcuna apertura PAPER.

**Decisione attuale: NO-GO per unpause o apertura Brain.**

## Fatto e verificato

Fonte primaria: [Issue #95, commento con riscontro del preflight](https://github.com/alexiptv82/SuperBot-Trading/issues/95#issuecomment-6851543620), basato sull'output VPS mostrato dall'utente alle 12:26 locali; questa esecuzione non ha effettuato accesso SSH diretto.

- Mandato Brain: `approved=True`; `approved_by` presente; `run_id_ok=1`; `policy_hash_ok=1`.
- Runner Brain: heartbeat `paused`, ciclo 0.
- Exit Brain: heartbeat `healthy`; `exit_service_healthy=True`.
- Journal: `integrity=ok`, chain `ok`.
- Budget DeepSeek: 0 chiamate/spesa registrata nella run; cap 0,75 USD; chiave caricata indicata solo come booleano, nessun segreto letto o esposto.
- Regole contratti: 6/8; mancanti BTCUSDT ed ETHUSDT.
- Primo simbolo disponibile SOLUSDT; ciclo isolato fermato con `data_unavailable`, zero decisioni e zero aperture.
- Campo `deepseek {}`: significa che la chiamata non è avvenuta, non che il modello abbia risposto con un oggetto vuoto.
- Journal e budget della run risultavano invariati; `pause.flag` ancora presente.
- Lo `stage_sha` non è visibile nel riscontro: resta non verificato. La mancanza BTC/ETH è compatibile con il parser precedente che rifiuta `maxLever>125`, ma non dimostra quale sorgente sia installata.

## Preparato, non eseguito/rilasciato

1. Preflight Issue #95:
   - script `deploy/scripts/v3-brain-paper-preflight-readonly.sh`;
   - commit [`5c71be8fe7fb2a74652833297a45de0a508639fc`](https://github.com/alexiptv82/SuperBot-Trading/commit/5c71be8fe7fb2a74652833297a45de0a508639fc);
   - blob Git segnalato nell'audit: `5224b914cc1238bab74af7494a48bdba8a1ae1c2`.
   - Limite: non è strettamente “sola lettura”; crea dati temporanei, esegue codice come root e può effettuare una chiamata DeepSeek fuori dal budget della run. L'esecuzione osservata non è arrivata alla chiamata.

2. Smoke DeepSeek isolato senza ordini:
   - script `deploy/scripts/v3-brain-deepseek-smoke-noorder-20261113.sh`;
   - branch `work/brain-deepseek-smoke-readonly-20261113`;
   - commit [`46cd607dbd6d1331361b7d03ff57cd2dc90f8bb9`](https://github.com/alexiptv82/SuperBot-Trading/commit/46cd607dbd6d1331361b7d03ff57cd2dc90f8bb9);
   - stampa SHA stage e regola parser, verifica pausa/servizi e può fare una singola richiesta JSON NO_TRADE a DeepSeek senza ordine, senza stampare chiave o testo completo.
   - **Non risulta eseguito sulla VPS** al momento di questo checkpoint. Anche un PASS proverebbe soltanto protocollo/provider, non feed Bitget→Brain→rischio→apertura PAPER.

## Stato portafogli e configurazioni

- **Falco PAPER:** strategia SHORT originale congelata; nessuna modifica, resume o ordine autorizzato.
- **Toro PAPER:** LONG/Twin sospeso; PR #93 resta FAIL e PR #94 resta PASS tecnico ma NO-GO strategico; nessuna configurazione finale approvata.
- **Brain PAPER:** obiettivo desiderato 2.000 USDT, floor 450, leva 20–50, 8 simboli, DeepSeek `deepseek-flash`; il preflight conferma alcuni gate e l'infrastruttura exit, ma non certifica feed, inferenza, decisione, rischio e apertura E2E. Restare paused.
- `NO_TRADE` resta un esito valido; non forzare un trade per “provare” il sistema.

## Rilasciato

Niente. Nessun merge, deploy, GitHub Actions, modifica VPS/systemd, reboot, reset, unpause, ordine o API a pagamento eseguito da questo checkpoint.

## PR, backup e chiavi

- RC84 / PR #80 resta riferimento storico; nessuna nuova assunzione di rilascio in questo checkpoint.
- Backup esterno sul branch `work/extbackup-bot-stopped-20261109`: preparato, **non installato**.
- Copia cifrata della chiave age sul PC: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente. Ciò verifica la copia PC, **non certifica** backup o restore sulla VPS.
- Nessuna chiave privata, passphrase, token o dettaglio d'accesso è registrato qui.

## Problemi / blocker

1. `stage_sha` VPS non acquisito nel riscontro.
2. Regole contratto solo 6/8; BTCUSDT e ETHUSDT mancanti.
3. Feed/candele SOLUSDT non disponibili nel ciclo isolato.
4. DeepSeek non chiamato; nessuna risposta o decisione verificata.
5. Nessuna proposta passata attraverso approval/risk; nessuna apertura PAPER/uscita E2E provata.
6. Un eventuale aggiornamento del parser o stage richiede diff, backup/rollback e consenso separato; non va inferito dal presente checkpoint.

## Prossimo passo minimo e sicuro

1. Conservare Brain in pausa.
2. Ottenere e registrare lo `stage_sha` installato e la regola parser, senza modifiche.
3. Solo con decisione esplicita dell'utente, eseguire lo smoke no-order preparato: una chiamata DeepSeek fuori dal budget della run e quindi non automatica.
4. Se il provider passa, risolvere feed/contratti in una proposta separata; nessun deploy senza diff, rollback e consenso.
5. Solo dopo provider + feed + E2E isolato verificati, preparare un rapporto go/no-go. L'unpause Brain resta un'autorizzazione distinta.
6. Preservare integralmente storici ed EventJournal.

## Limiti delle fonti

Le conversazioni complete o eliminate non sono accessibili come archivio integrale. Sono stati usati soltanto il contenuto corrente accessibile, GitHub e il file consolidato. Lo stato live VPS non è assunto oltre l'output riportato nell'Issue; non è stato effettuato un controllo SSH indipendente in questa esecuzione.
