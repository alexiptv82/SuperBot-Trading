# AI Arena — conferma Bitget 3/3 e preview TOP 23 crypto (16/11/2026)

## Evidenza VPS 15:21
Lo screenshot del test pubblico Bitget mostra BTCUSDT, XAUUSDT (oro) e XAGUSDT (argento) tutti idonei: contratti USDT perpetui attivi, leva 20x supportata, ticker freschi/liquidi, 63 candele 15m chiuse ciascuno. Totale ready=3/3. Nessuna API AI pagata, nessun ordine e nessuna modifica servizi.

## Nuovo script diagnostico senza ordini
Branch work/arena-marketcap-23-preview-20261116. File deploy/scripts/arena-public-marketcap-preview-20261116.py.
Primo GET CoinGecko sui primi 250 asset per capitalizzazione; due GET Bitget sui cataloghi contratti USDT futures e ticker. Nessuna chiave, nessuna scrittura, nessuna operazione, nessun retry. Da questi dati costruisce una preview di fino a 23 crypto per rango compatibili con contratti Bitget, più XAU e XAG in due slot riservati.
Le esclusioni di stablecoin/wrapped/token sintetizzati oggi sono solo euristiche di alcuni identificativi o nomi evidenti: NON sono una classificazione esaustiva. La lista generata è etichettata PROVISIONAL_REQUIRES_CATEGORY_AND_CANDLE_AUDIT, tradable_or_approved=false, e NON viene passata ai runner. CoinGecko può imporre un limite 401/429 o una chiave Demo gratuita: lo script non procede con dati falsi se la fonte non risponde.
Lo script ha selftest sintetici offline, ma al momento della stesura non era ancora stato eseguito su VPS. Non dichiarare che il nuovo script è stato collaudato.

## Prossimi vincoli
Verificare categorie native/stablecoin/wrapped/tokenized con fonte affidabile; validare candele chiuse 1m/15m/1h/4h, cataloghi/volumi/spread reali; generare snapshot e shortlist uguali per DeepSeek/Qwen/MiniMax. Non aprire posizioni solo perché il coin è in classifica. Nessun trade forzato.
Proteggere le uscite per le posizioni aperte uscite dalla classifica e la strategia Falco SHORT (backup runtime VPS ancora da completare prima di pausa). Toro intatto; Brain DeepSeek operativo non cambiato.
Qwen/MiniMax chiavi ancora limitate a 2 USD ciascuna; utente ha ricaricato 10 USD di conto, nessun addebito da questo codice. Tre portafogli PAPER e test 14 giorni NON ancora avviati.

## Fonti
CoinGecko API leaderboard: https://www.coingecko.com/learn/coingecko-api-troubleshooting-guide-and-solutions
CoinGecko native vs non-native: https://support.coingecko.com/articles/7346603845-why-do-we-list-native-vs-non-native-cryptocurrencies-separately-on-coingecko
CoinGecko Demo API: https://support.coingecko.com/articles/9471335603-user-guide-how-to-sign-up-for-coingecko-demo-api-and-generate-an-api-key
Bitget public market: https://www.bitget.com/docs/classic/uta-api-upgrade-guide