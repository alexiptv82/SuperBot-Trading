# Trend Engine v1.1 — Integrazione Falco/Toro in sola osservazione
30 ottobre 2026 · [skip ci]

## Scopo vincolante
Indicatore precoce e simmetrico di possibili cambi trend, in particolare ribasso→ripresa LONG. Non blocca trade SHORT, non promuove LONG forzati, non cambia pesi, budget, stop, TP o logica di scelta meccanica. AI classici opzionale; rules_only resta indipendente.

## Implementazione isolata
- Ramo `work/classics-trend-v11-shadow-20261030`, basato su `work/classics-trend-awareness-20261030`.
- Stessa implementazione pura in `backend/director/trend_engine_v11.py` e lo stesso `TrendShadow` asincrono. Nessun `adjust_scores`, nessuna chiave API, nessuna logica di ordini.
- I classici originali leggono candele 15m per il loro scorer. Le candele 15m NON vengono adattate o spacciate per 1m. Il reader aggiuntivo puo' avviare fetch pubblici Bitget V2 `1m` (fino a 300 barre) **soltanto** nel worker shadow, senza bloccare il loop di protezione o i segnali esistenti.
- Il loop di controllo `_poll_v11_shadow` gira ogni 5s solo con `DESK_TREND_V11_SHADOW=on`, altrimenti non effettua nessun lavoro. Prende al massimo 12 simboli per ciclo di rotazione, privilegiando le posizioni aperte. Aggiorna lo stato osservativo `trend_v11_observations` e logga gli stati TRANSITION_UP/DOWN nuovi senza mutare i `readings_list`, punteggi LONG/SHORT, candidati o ordini.
- Intervallo delle letture 60s, risultato freschissimo massimo 180s. Se la rete non risponde o il prezzo non e' affidabile, l'indicatore scompare; **nessun fallback di ordini**. Le richieste gia' previste dal trading restano intatte.
- Questa e' una lettura di supporto separata: non necessariamente tutti i 30 simboli hanno ogni minuto un indicatore 1m pronto, perche' la sorgente pubblica e' rate-limited. Non dichiarare copertura H24 completa senza prove.

## Test
Run `41047006505`: SUCCESS Python3.10/3.11, 26 nuovi test per versione, inclusi parity sintetica rispetto al v1.1, stato operator invariato se indicatore BEARISH, quote incompiute/gap, worker non bloccante e test old LONG/SHORT.
Confronto A/B suite legacy 95 test: originali 19 fallimenti, candidati 3 fallimenti *gia' presenti* relativi alla vecchia configurazione Claude; **zero nuove regressioni**. Nessun test mascherato. I tre fallimenti legacy non equivalgono a nuove regressioni del reader.

## Rilascio
Nessun deployment/merge e nessuna modifica dei classici attivi. Per abilitare in futuro serve valutazione SHADOW, backup/restore, verifica runtime dei fetch pubblici e approvazione separata a deploy; non impostare la variabile sul VPS senza OK. Non cancellare storici/brain.
AI: chatgpt
