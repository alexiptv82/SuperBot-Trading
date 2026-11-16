# SuperBot AI Arena — primo confronto API 3 modelli su 25 mercati (16/11/2026)

## Evidenza confermata sulla VPS
Screenshot utente delle 20:46:
- `Ran 12 tests in 16.697s / OK`.
- `RESULT=THREE_MODEL_ALL25_COMMON_PACKET_VERIFIED_NO_DEPLOY`.
- 25 mercati: 23 crypto, XAUUSDT, XAGUSDT.
- Digest della cache di origine `fba771b33ad1935614df124d74c357b63d66694f47193abb65ed514c77ed4bdd`.
- `model_input_bytes=11415` e digest identico per tutte e tre le AI `3c834a5659f3d32b63c2bb969b59778d5bf58b30dc2f8afcfec333ac863cb58e`.
- `snapshot_age_seconds=3686` → input di ricerca STORICO, non un feed live; zero chiamate ai modelli e zero ordini.

## Nuovo ramo
`work/arena-three-ai-one-shot-research-20261116`, basato su `work/arena-three-ai-common-packet-20261116`.

`deploy/scripts/arena-three-ai-research-oneshot-20261116.py` offre:
- `--selftest`: nessuna rete, cache o chiave letta, test su input identico e controllo del limite di credito.
- `--preflight <sha>`: sola lettura del file ricerca persistito. Ricalcola il pacchetto comune e gli hash. Nessuna API key letta, nessuna GET/POST.
- `--run <sha> --confirm-three-paid=YES`: disponibile solo con root, consentito solo dopo conferma INTERATTIVA scrivendo SI. Al massimo **tre POST a pagamento** (una per modello, nessun retry). GET read-only dell'endpoint OpenRouter /key per verificare i limiti delle chiavi preesistenti (≤2 USD ciascuna; residuo ≥0.15 USD) prima di ogni POST. Non consuma API trading e non vede né modifica i journal. Restituisce esclusivamente decisione CANDIDATE o NO_TRADE, symbol, side, confidence, reason_code, uso token, modello richiesto e hash dell'input. Non stampa credenziali o risposta grezza.
- **Prova storica**: non tenta mai di tradare, salva ZERO file e non aggiorna alcun servizio. I risultati vanno archiviati dall'utente solo dopo averli visionati. Nessun bot viene riavviato.
- `backend/v3/arena/test_three_ai_research_oneshot.py`: 11 test offline scritti, **non ancora eseguiti sulla VPS**. Comportamento request/response e budget validato soltanto in mock; non è una certificazione live.

## Configurazione modelli reale della prova
- Qwen: `qwen/qwen3.7-plus`, usa la propria chiave OpenRouter Qwen (root-only).
- MiniMax: `minimax/minimax-m3.1-flash`, usa la propria chiave OpenRouter MiniMax (root-only).
- DeepSeek: `deepseek/deepseek-v4.1-flash-1017`, usa la chiave OpenRouter Qwen per questa SOLA prova di ricerca, non legge alcuna chiave DeepSeek di produzione. **AVVERTENZA**: questo modello DeepSeek di ricerca potrebbe essere DIVERSO dalla versione DeepSeek effettivamente utilizzata dal Brain attuale. Non confrontare quindi direttamente performance dei portafogli o attribuire eventuali prestazioni del modello OpenRouter al Brain già attivo. Una futura verifica read-only del model ID operativo sarà necessaria prima di un test rigoroso *stesso modello*.

I tre ricevono gli stessi byte input/sistema. I parametri di response format differiscono soltanto per compatibilità dei fornitori: Qwen json_schema strict con reasoning off; MiniMax e DeepSeek json_object con temperatura zero. L'output non è una raccomandazione di trade.

## Gate prima di spendere
1. Verificare su VPS offline i 12 test precedenti e gli 11 nuovi, il file Python, poi `--preflight` con SHA aggiornato.
2. Controllare che l'utente accetti che DeepSeek OpenRouter sia una diversa versione sperimentale rispetto al modello runtime (non verificato), se si procede con le chiamate pagate.
3. Solo dopo conferma, una singola sessione del comando `--run ... --confirm-three-paid=YES`, con esplicita SI e massimo tre chiamate pagate. Non attivare i 14 giorni, i servizi PAPER, la UI o altre funzionalità senza nuovo consenso.

Nessun merge/deploy. Falco SHORT conservato, Toro a riposo, Brain attuale non toccato. I tre portafogli PAPER da 2000 USDT non sono ancora partiti.
