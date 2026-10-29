# Brain Scalp — Gruppo 6 e sizing, 29 ottobre 2026

Stato: implementazione PAPER offline. Nessun merge/deploy, provider attivo o modifica al VPS.
Autorizzazione: briefing utente «scegli tu tra opzione A/B/C e implementa», successivo alla sospensione iniziale del Gruppo 6.

## Scelta I8: C

Si mantengono le configurazioni: 1.000 USDT PAPER per wallet; margine totale massimo 950; Hawk 100–250 per piano e massimo 10 slot; Bull 150–350 e massimo 3 slot; rischio stimato 50 per trade e 150 aggregato, daily stop20%, kill equity450.
Gli slot sono un limite superiore, non un obiettivo. Hawk può prenotare nove margini minimi da100: il residuo50 non finanzia un decimo ingresso valido. Bull può prenotare350+350+250. Nessun abbassamento dei minimi per riempire lo schermo, nessun capitale nuovo e nessun aumento del budget a980.

L'opzione C risolve l'incoerenza dichiarando la capacità finanziabile. Le modifiche al sizing sono il secondo punto separatamente autorizzato dal briefing, non un cambiamento dei mandati finanziari dell'opzione C.

## Problema trovato nel codice e correzione

Il precedente _resize_for_budget scorreva le leve in ordine decrescente e accettava il primo margine finanziabile: conservava la leva sacrificando prima il margine.
Adesso sceglie il massimo margine finanziabile senza superare quello proposto dall'AI; a parità di margine conserva la maggiore leva ammissibile, sempre entro la richiesta e i vincoli già presenti.
Se neppure la leva1 consente il margine intero, riduce il margine al massimo finanziabile; se scende sotto il minimo, rifiuta. Non aumenta mai automaticamente una proposta AI per occupare capitale.

Esempio sintetico, non trade osservato: quotazione100, richiesta LONG250 a45x, stop98, fee0,0006 e slippage0,0002 per lato. Il nuovo solver propone250 a9x, rischio stimato circa49,04; quello precedente sacrificava il margine per una leva maggiore. SHORT simmetrico con stop102 è coperto dai test.
Questa scelta non aumenta necessariamente il nozionale o il profitto: margine e leva non sono sinonimi di esposizione. Non dimostra la causa delle piccole taglie del Brain attivo e non corregge la selezione dei segnali.

## Prenotazione ed esecuzione

- submit resta una prenotazione PAPER: può adattare la richiesta al capitale residuo, con evento plan_reservation_resized che conserva valori originali/allocati; nessun ordine.
- La cassa prenotata dagli altri piani comprende margine più fee d'ingresso sulla loro leva; non può essere impegnata due volte. Le prenotazioni non sono una garanzia del futuro fill.
- Il rischio viene rivalutato al trigger dopo le protezioni e le uscite, come nel codice precedente. La fase di ammissione non promette rischio già riservato per ogni piano.
- La normalizzazione contrattuale resta nel motore condiviso Brain Free, che non è stato modificato. Il wrapper scalp verifica il margine realmente ottenuto: tolleranza massima di un centesimo per polvere di quantità; un lotto grossolano che crea una posizione molto sotto minimo viene rifiutato senza addebito o evento open persistito.
- Il rischio aggregato usa la posizione realmente normalizzata. entry_fill include margine, leva e rischio stimato effettivi; BrainPair restituisce margine e leva prenotati ai chiamanti.
- Nessuna modifica a database/schema/hash finanziario o migrazione automatica. Wallet legacy non compatibili col Gruppo3 restano soggetti ai suoi gate di migrazione esplicita.

## API e architettura proposta

Verifica29/10/2026 nelle fonti ufficiali:
- https://api-docs.deepseek.com/quick_start/pricing — usare deepseek-flash (attualmente instradato a DeepSeek-V4.1-Flash-1017); alternativa deepseek-v4-pro.
- https://api-docs.deepseek.com/guides/thinking_mode/ — Chat Completions: thinking.type=enabled e reasoning_effort=high. Con SDK OpenAI, thinking passa in extra_body. Non confondere il formato Responses: reasoning.effort.
- https://api-docs.deepseek.com/news/news260424/ — deepseek-chat e deepseek-reasoner ritirati dal24/07/2026.
- https://developers.openai.com/api/docs/models/gpt-6.1-sol — ID API gpt-6.1-sol; tool calling tramite Responses.

Brain Scalp non contiene ancora chiamate ai modelli o un provider da migrare. Il suo BrainConfig locale specifica deepseek-flash/high e il secondo livello gpt-6.1-sol è identificato in configurazione, senza invocazioni. Brain Free condiviso rimane invariato.
Lo scanner di mercato esistente è deterministico; DeepSeek dovrà valutare una shortlist con contesto compatto. Copertura H24 di tutti i simboli non significa una chiamata AI completa su tutto l'universo a ogni tick.
Routing dei casi contraddittori, prompt, budget/metrica API, gestione errori/timeout, supervisore H24 e convalida paper comparativa restano lavoro successivo. Nessuna architettura a due livelli già operativa dichiarata.

## Verifiche

Nuova suite test_brain_scalp_group6:12 test. Mandati C invariati; conservazione margine250 per LONG/SHORT; esecuzione e rischio; nessun aumento richieste; fallback1x; nove prenotazioni Hawk;350+350+250 Bull e restart; fee su cassa prenotata; lotto sotto minimo rifiutato atomicamente; output BrainPair/wallet isolati; rischio/capitale aggregati; nomi modelli e isolamento Brain Free.
Suite completa motore:114 test locali Python3.12 PASS. CI dedicata esegue anche Gruppo6 su Python3.10/3.11. Esiti CI finali e commit nel diario.

## Ripristino e seguito

Base codice f097801b1836a3864807811c5f9c9e731a4cc789, ramo work/brain-scalp-dual-20261028. PWA resta sul commit9251e6ddf2d68b607fffd73b8383da8f00c687fa.
Ripristino codice con nuovo commit di revert, mai force push; nessun dato operativo modificato da ripristinare.
Classici accantonati come direzione progettuale su decisione dell'utente; nessuna azione operativa su container/classici/memoria/Brain Free eseguita.
AI: chatgpt
