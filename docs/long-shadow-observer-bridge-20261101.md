# LONG Shadow — observer read-only collegato (solo sviluppo, 1 novembre 2026)

## Obiettivo

Unire il registratore Bitget pubblico, il motore LONG V6.1.1 **identico** alla versione congelata e tre wallet letti in sola lettura (Falco/Toro/Brain) per produrre consigli. Nessuna esecuzione di ordini, nessun cambio SHORT/Brain/AI/portafoglio, nessun deploy sulla VPS. La PR #26 rimane Draft.

## File e contratti

- `backend/long_shadow_stream.py` legge gli envelope JSONL e mantiene solo snapshot WebSocket **effettivamente ricevuti**; gli update delle candele in formazione rimangono provvisori. Riavvio/sessione nuova invalida il warmup, nessuna candela finale inventata.
- `backend/long_shadow_stream_runner.py` legge e verifica la raccolta append-only/rotazione dal collector esterno, senza collegarsi a Bitget né usarne credenziali.
- `backend/long_shadow_readonly.py` legge lo stato dei tre account; Brain Free/Pilot vanno selezionati esplicitamente, wallet invalido/stale → unavailable, mai conto vuoto. La dashboard accetta un consiglio esterno solo se **timestamp esatto dello snapshot wallet** coincide con quello usato dall'observer, e solo se il consiglio è stato creato negli ultimi **60 secondi**. Eventuali vecchi JSON senza binding vengono nascosti.
- `backend/long_shadow_observer.py` abbina la BBO fresca (≤2s), dati MTF ricevuti e wallet fresco (≤30s nel contratto di ricerca). Utilizza `long_shadow_offline_probe.frozen_engine`, che rifiuta qualsiasi motore con SHA256 diverso da `36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72`. Due setup (CONTINUATION/REVERSAL) per simbolo BTC/ETH e destinatario. Output `CANDIDATE` o `NO_TRADE`, entrambi **advisory-only**, mai autorità di aprire, bloccare, modificare scoring o chiudere posizioni. Mancanza mercato/wallet → NO_TRADE.
- `backend/long_shadow_observer_runner.py` è un comando **esplicitamente invocato** per ricerca che legge il collector pubblico, esegue l'advisor solo se `--enable-advice`, scrive `observer_state.json` con tutti i record e file `hawk.json`, `bull.json`, `brain.json` limitati alla vista esistente. Isolamento output da input e wallet, scrittura atomica, durata di default 60 secondi. NON è un servizio systemd/Docker o attivazione H24.

## Esecuzione soltanto in staging con collector pubblico separato

Preparare il motore congelato `engine.py` **fuori dal repository** e directory di ricerca dei wallet PAPER, senza segreti, senza dati finanziari committati. Comando di esempio **illustrativo**, NON eseguito automaticamente:

```bash
PYTHONPATH=backend python backend/long_shadow_observer_runner.py \
  --input-dir /research/bitget-capture \
  --output-dir /research/long-shadow-output \
  --hawk-wallet /research/wallets/hawk \
  --bull-wallet /research/wallets/bull \
  --brain-wallet /research/wallets/brain \
  --brain-source free \
  --frozen-engine /research/frozen-v611/superbot_long_lab/engine.py \
  --enable-advice --seconds 60
```

Se la fonte Brain non è `free` il parametro deve essere verificato, non indovinato. Se nessun collector gira, i dati sono vecchi oppure mancano candele verificate 1m/15m/1H/4H, il risultato sarà NO_TRADE o errore diagnostico; **non forzare un CANDIDATE**.

## Limite reale che rimane

Il capture di 15 minuti mostra che alcuni TF hanno snapshot iniziali chiusi, ma non osserva la finalizzazione di tutte le candele 1H/4H successive. Poiché le update `kline` del WebSocket non sono promosse a chiusure, dopo qualche minuto di sola raccolta i frame 1m diventano stantii e il frozen engine restituisce NO_TRADE. La continuità H24 **non è ancora dimostrata**: prima di un avvio serve una sorgente continua verificata di candele chiuse (es. snapshot REST pubblico dopo la chiusura, con timestamp di ricezione e test causali), più la conferma del Brain attivo e il test end-to-end su staging. Non aggirare la freschezza del motore.

## Test/decisioni

- Nuove suite `test_long_shadow_observer.py` (12 casi) e `test_long_shadow_observer_runner.py` (9 casi); più test `_shadow_record` per coerenza wallet/advice e scadenza del segnale. Risultati CI vanno controllati, non si presume SUCCESS prima del workflow GitHub.
- PR #27 resta separata: chiusura manuale **del singolo trade per ID** con altri trade invariati; nessun endpoint/consumer operativo attivo.
- LONG V6.1.1 e baseline SHORT invariati; Brain libero bocciato per prossimo rilascio, redesign con regole in fase successiva. `PAPER_ELIGIBLE=NO`, `ORDERS_CREATED=0`, nessun deploy, merge o reset.