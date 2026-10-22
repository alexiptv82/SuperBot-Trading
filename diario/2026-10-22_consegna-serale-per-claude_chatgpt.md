# Per Claude — consegna unica dei quattro lavori del 22/10 sera

Preparato nell'ordine 1 → 3 → 2 → 4. Tutto su rami work/, [skip ci].
Nessun merge, trigger, deploy, installazione, run VPS o chiamata LLM eseguiti.
Unica acquisizione di rete per le prove: candele PUBBLICHE Bitget, senza chiavi.
Nessun dato grezzo di mercato o del conto pubblicato; mirror solo aggregati/hash.

## 1. Audit VPS read-only

Ramo work/profit-audit-readonly, HEAD bc8fcef49b72fbe692700147e692f78870097aff.
[Commit](https://github.com/alexiptv82/SuperBot-Trading/commit/bc8fcef49b72fbe692700147e692f78870097aff) · [scheda review](https://github.com/alexiptv82/SuperBot-Trading/blob/bc8fcef49b72fbe692700147e692f78870097aff/deploy/PROFIT-AUDIT-REVIEW.md).

Script profit_review_audit.py, workflow desk-profit-review-audit.yml, nessun
file trigger. PAPER e invarianza Docker prima/dopo in trap, mount :ro e network
none, snapshot byte-identici e manifest invariato, hash chain sidecar verificata,
errori fissi e output allowlist solo aggregati/ROI per fasce/hash.

Finestra Roma richiesta, compresi file AI UTC 21 e 22 e posizioni pre-mezzanotte.
Aperture per bot/lato/source/versione, score per fasce, ricostruzione del bonus
solo con codice stagionale revisionato/pinnato, checkpoint sidecar e conto
virtuale DeepSeek separato. Budget/calendario/mode runtime distinti dalla storia.

Limite fondamentale: il vecchio registro non conserva ogni decisione riuscita
per posizione o gli skip causali. Il numero esatto di hold/omissioni, l'inizio
del blocco budget e quante mancate review siano CAUSATE dal budget restano
null/non identificabili, non zero. Conta opportunita' di chiamata, non le
spaccia per review. source sul close identifica l'INGRESSO, non il decisore
d'uscita. Nuovo logging necessario per ricostruzione completa prospettica.

Verificato: 14 test sintetici, compilazione, YAML/bash. Non verificati: risultati
runtime, copertura/capienza dei journal, versioni/container del momento. Per la
run autorizzata serve prima tua review e poi OK utente a merge/trigger.

## 3. Pacchetto A/B e mirror

Ramo work/profit-correctness-proposals, HEAD ed36f4fb0ab03a4ad3e3075323bd401dbaa710c6.
[Commit](https://github.com/alexiptv82/SuperBot-Trading/commit/ed36f4fb0ab03a4ad3e3075323bd401dbaa710c6) · [documento](https://github.com/alexiptv82/SuperBot-Trading/blob/ed36f4fb0ab03a4ad3e3075323bd401dbaa710c6/research/profit-fixes/REVIEW.md)
· [risultati mirror](https://github.com/alexiptv82/SuperBot-Trading/blob/ed36f4fb0ab03a4ad3e3075323bd401dbaa710c6/research/profit-fixes/mirror-results.json).

A implementato come patch DI PROVA: storia 4h nativa >=200 per EMA200, cache e
barre chiuse; nessun EMA61 mascherato. Score lato/opposto distinti; scheda con
TP, total_margin, ROI netto lifecycle/R e MFE/giveback di prezzo come upper
bound. Uguaglianze e RSI piatto neutrali, aritmetica esempio Bull corretta.
Esaminati gli altri indicatori che usano 1000 barre: timeframe 1h sufficiente
per le finestre attuali, 1d resta fonte separata >=200 giorni. Nessuna attribuzione
della carenza 4h ai soli long.

B soltanto specificato, NON attivato: stagionalita', hold/aggiornamento protezioni,
review AI del profitto, copertura completa delle posizioni, contratto RR.
Istruzioni del prompt d'ingresso non riscritte prima della diagnosi. Le correzioni
A cambiano comunque score/contesto e possono cambiare decisioni: non sono un
lasciapassare al deploy.

Mirror 1/p, high-low scambiati, volumi invariati: 16 finestre reali da quattro
serie pubbliche e 12 sintetiche, stagionalita' on/off, vecchio vs proposta.
Senza bonus: sulle sintetiche differenza assoluta media 10,375 → 0; sulle
reali resta 1,25, max 12. Sulle reali il tasso short sopra soglia cambia
12,5% → 0%, long 0%: nessuna deduzione di profitto. McNemar esatto nominale
su entrambe le coppie direzionali, descrittivo per sovrapposizione/non
indipendenza. EMA/ATR/rendimenti non sono invarianti all'inversione.

Verificato: 9 nuove prove + 4 controlli preesistenti CONTO eseguiti direttamente,
py_compile e diff check. Non suite completa/CI 3.11. OHLC grezzi restano privati;
il JSON pubblico contiene solo risultati e hash, non prezzi/simboli.

## 2. Step 6 con riferimento C

Ramo work/step6-baseline-c, base 4c1645e3, HEAD 9bd51349658483fd7964a22947d4985bb06b62a3.
[Commit](https://github.com/alexiptv82/SuperBot-Trading/commit/9bd51349658483fd7964a22947d4985bb06b62a3) · [piano](https://github.com/alexiptv82/SuperBot-Trading/blob/9bd51349658483fd7964a22947d4985bb06b62a3/deploy/step6-plan.json)
· [review](https://github.com/alexiptv82/SuperBot-Trading/blob/9bd51349658483fd7964a22947d4985bb06b62a3/deploy/STEP6-REVIEW.md).

Piano ancora draft/null. C fissata: intera posizione, arming su close >=1,5R
di prezzo; trailing del massimo dei close meno 1R, vecchio floor giudicato
prima dell'aggiornamento, fill next-open e ritardo dello scenario. Nessuno
stop intrabar implicito, nessuna griglia calibrata sui dati. Stesso terminale,
campione riconciliato, costi PAPER e funding solo-long.

Distribuzione di R_C-R_baseline per bot/lato/durata baseline. C descrittiva,
senza IC o gate; famiglia primaria sempre due confronti, IC97,5%.
Renderla inferenziale richiederebbe quattro confronti/IC98,75% PRIMA di S.
Test forza C sfavorevole e conferma che gate/metriche primari restano invariati.
38 test sintetici passati, compilazione/diff check. Nessun replay operativo.

## 4. DeepSeek ombra sulle posizioni dei bot

Ramo work/deepseek-bot-shadow-design, HEAD 99c9d544528bbb4e61f11d1a51ba49ea8b4aee16.
[Commit](https://github.com/alexiptv82/SuperBot-Trading/commit/99c9d544528bbb4e61f11d1a51ba49ea8b4aee16) · [progetto](https://github.com/alexiptv82/SuperBot-Trading/blob/99c9d544528bbb4e61f11d1a51ba49ea8b4aee16/research/deepseek-bot-shadow/PROPOSAL.md)
· [schema](https://github.com/alexiptv82/SuperBot-Trading/blob/99c9d544528bbb4e61f11d1a51ba49ea8b4aee16/research/deepseek-bot-shadow/decision.schema.json)
· [stima](https://github.com/alexiptv82/SuperBot-Trading/blob/99c9d544528bbb4e61f11d1a51ba49ea8b4aee16/research/deepseek-bot-shadow/cost-envelope.json).

SOLO progetto/schema/stima, nessun servizio o installer implementato.
Osservatore separato, dati bot :ro, applied=false, journal privato online con
tesi, invalidazione, input disponibile al momento e coverage per posizione.
Nessun takeover o ordine verso Hawk/Bull. Il replay deve rispettare anche
l'istante di arrivo della risposta AI, non usare un next-open gia' trascorso.

Proposta base oraria + burst prioritari, massimo 39 chiamate/giorno; 8000 input
e 2200 output con budget worst-case, cache non presunta e safety 25%.
Stima nuovo braccio circa 0,2457/giorno in valuta API, non spesa misurata.
Tetto COMPLESSIVO 0,50/giorno e mensile esistente richiedono un solo arbitro
atomico per conto virtuale e nuovo braccio; allocazione proposta da approvare.
Non due Budget indipendenti da 0,50. Listino ufficiale consultato, nessuna API
LLM chiamata. JSON e aritmetica verificati; validatore formale JSON Schema non
disponibile qui, da eseguire prima dell'implementazione.

Valutazione iniziale descrittiva preregistrata 42+14 giorni, copertura/episodi/
numero di posizioni e proposte minimi, senza peeking e senza promozione.
Confronto pieno con decisioni Claude dipende dal nuovo decision log, non
recuperabile retroattivamente dai registri incompleti. Shadow separata non
cambia code_version/uscite dei bot; monitorare comunque interferenza di risorse.

## Prerequisiti e decisioni residue

1. Tua review dei quattro rami e dei limiti di identificabilita' dell'audit.
   Le cifre serali fornite dall'utente restano contesto riferito, non nuove misure.
2. Decisione ROI: sidecar reference iniziale+DCA non cala coi parziali ma aumenta
   con nuovo DCA. Per riferimento immutabile suggerita prima coorte no-DCA,
   oppure ridefinizione comune esplicita. Nessun cambio silenzioso del denominatore.
3. Approvazione dei punti B, gestione con dati invalidi/budget esaurito e log
   strutturato, budget unico/allocazione DeepSeek e vincoli della valutazione.
4. Archivio OHLC completo, acquisizione/capienza/snapshot immutabili, autenticita'
   e copertura runtime-ledger, conferma baseline_version/configurazione runtime.
5. Tutti i fix approvati in UN solo deploy bot prima di S, con OK separato.
   Poi confermare nuova baseline runtime, aggiornare piano e congelare commit;
   solo dopo fissare S futuro. Cambio code_version fra S e F invalida coorte.
   Installare/provare ombra prima di S, soltanto con OK esplicito al momento.

Nessuna approvazione di strategia o profitto dedotta da questi test. Nessun
merge, trigger, deploy o live. Attesa della tua review prima di procedere.
