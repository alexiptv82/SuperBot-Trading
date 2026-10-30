# Lettore strutturale e metodologia classica — 30 ottobre 2026
AI: chatgpt Work. Implementazione OFFLINE, non deployata.

## Mandato
Indicatore consultivo per Brain e Falco/Toro. Nessun obbligo LONG/SHORT, veto, variazione score, ordine o modifica dei limiti. Brain conserva DeepSeek primario H24 e Claude revisore selettivo. PAPER; nessun portafoglio o storico modificato.

## Ipotesi strutturale v1 congelata prima della valutazione
Quindici minuti per osservazione rapida, non micro-transizioni 1m: due chiusure consecutive oltre massimo/minimo delle otto barre precedenti, buffer 0,25 ATR14 calcolato prima delle due chiusure. Lettura simmetrica UP_REASSESSMENT / DOWN_REASSESSMENT / NO_BREAK.
Contesti EMA12/24 su 1h e 4h, banda descrittiva relativa 0,1%; almeno48 barre complete per ciascun contesto. Il contesto lento NON è un requisito dell'avviso veloce. In sua assenza UNKNOWN, non inferenza del trend.
Non è un rilevatore certificato di minimi/massimi né una prova di anticipo. Confermare due15m comporta ritardo; si misura il compromesso, non lo si nasconde.
La v1.1 rimane immutata per confronti; non sono state ottimizzate sue soglie. Questo nuovo algoritmo è un candidato di ricerca, non una soluzione predittiva dimostrata.

## Dati e isolamento
Worker separato unico, massimo3 simboli/minuto a rotazione su50, richieste pubbliche Bitget15m fino1000 righe, trasporto esistente timeout8s. Nessuna rete sul thread proprietario del wallet per questo modulo. Opt-in BRAIN_STRUCTURE_ADVISORY=on o DESK_STRUCTURE_ADVISORY=on, default off; nessuna configurazione runtime cambiata.
Solo candele chiuse, timestamp allineati; ordinamento e duplicati identici accettati, revisioni conflittuali/gap/stale rifiutati senza opinione. Dati più vecchi30min esclusi; errori di refresh rimuovono il vecchio parere. Quote operative e guardie esistenti sono indipendenti. Nessun backfill inventato.
Con1000 barre15m disponibili (~10,4giorni) il4h ha circa62 barre e può essere pronto; la rotazione NON garantisce copertura simultanea di tutti i simboli, soprattutto con timeout. Metalli/simboli non restituiti dall'exchange rimangono senza opinione.
Classici: sola chiave diagnostica structure_advisory e log; notifica in console su cambiofase con cooldown4h per simbolo/direzione. Nessun nuovo Telegram. Nessun consumatore trading legge questa chiave.

## SHORT: cosa era trasferito e cosa cambia
Audit sorgente rule-pool fed2e3fd32ff162d22b045b4a8e5f0524e88a9b7 e candidato classici559b458: signals.py blob57b524e75593b0fe6f3a0712af1a0b2f14bd4a75, seasonal.py blob0f2821fbc6c6737ba82d72605eb5232c11953fdf identici ai sorgenti9fa667ff1103f037bec06f9131996366d27370c4. Questo è confronto repository, NON verifica versioneVPS corrente.
Prima: legacy_reference e contesto preparati ma BrainService.tick non passava references; scannerBrain rimane breakout1m/5m, diverso dai classici. Non era trasferita l'intera metodologia operativa.
Ora: copia byte-identica di quei due sorgenti congelati e verifica SHA256 runtime; esecuzione del vero read_symbol su15m causali, non un riassunto inventato. Il loader lega soltanto la dipendenza seasonal alla copia verificata; non cambia funzioni/pesi.
DeepSeek vede entrambi i punteggi, trend4h/1h, prezzoEMA, momentum24h, RSI, volume, motivi disponibili e cautele, nel campo classical_methodology. Non sono probabilità. Reasons originali solo per lato preferito.
SHA256 signals3c398e4be0335896b30f09426e5d8567cefd064907290b71b13860b8d54ec5bf; seasonal47c12da1abbe51be0c826fc03b7609af40407e2e101911ded3444def5d6912c7.
Non trasferiti: selezioneclassici, sizing, DCA, gestione uscite o soglie operative nel motoreBrain. ScannerBrain invariato: vede consigli solo per candidati già selezionati. Questo limita le opportunitàSHORT visibili; non dichiarare clone dei classici o miglioramento economico.
Scorer originale richiede60 barre4h e usa EMA200 con warmup corto; cautele su uguaglianzeSHORT e stagionalità statica preservate/visibili. Storia insufficiente = unavailable, non punteggi finti. Nessuna correzione LONG o P1 inserita in questa fase.

## Libertà AI verificata
Il nuovo campo consultivo è distinto dal vecchio classical_reference che può chiedere revisione su disaccordo. Il nuovo parere non attiva obbligatoriamente Claude e non aggiunge gate. Test end-to-end sintetico: scorer originaleSHORT -> candidatoLONG -> risposta AI LONG -> piano ammesso dalle guardie esistenti, senza revisione forzata. HOLD resta valido.
Errori/assenza/stale del sensore o metodologia non eliminano candidati, non autorizzano nuovi simboli e non mutano wallet.
Aumenta il contesto AI: consumo token massimo resta limitato dalla policy esistente, non nuove chiamate nel modulo.

## Validazione
Locale Python3.12: 84 test +21 subtestPASS su osservatori/integrazione/contesto AI; inoltre157 test regressione motorePASS (suite in parte sovrapposte, non sommare come test unici). Nuovi test18, inclusi3 classici eseguendo la vera funzione diagnostica estrattaAST senza caricare il bot.
Primo tentativo nuova integrazione ha evidenziato numpy scalars non accettati dalla whitelist: normalizzati a scalari Python senza cambiare valori/scorer; suite finale verde.
CI remota da verificare dopo pubblicazione. Nessun test API/provider a pagamento, nessun servizio avviato. Nessun vantaggio predittivo o economico misurato.
Backup codice: basi immutabili6b198e060dcbb478b5fd69c6d4fcd928d5821888 e559b458102a72cccbddb8a71eb102f28e5631b45, più rami nuovi isolati; rollback con revert, non reset dati.


## Esito finale verificato — 30/10, Work
Brain codice26b7098786080b8982a05a4b2c3f5da3cba3ff24: Actions41059587780 SUCCESS suPython3.10/3.11; per interprete9test osservatore+24integrazione+157regressioni motorePASS.
Classici codice72041ebe77c882f7b5c1b02e6f56152d91381bf4: Actions41059759276 SUCCESS suPython3.10/3.11;9osservatore+3diagnosticaPASS e A/B95test con92PASS/3FAILlegacyClaude identici subase/candidato. Nessuna nuova regressione; non dichiarare95/95verde.
Primo workflowclassici41059589228 fallito perché il nuovo harnessunittest non raccoglieva funzioni pytest; corretto usando pytest/JUnit con guardia anti0test e confronto degli IDfalliti, senza cambiare i test o il runtime.
Verifica ASTlocale: CLIclassico identico alla base eccetto nuova funzione diagnostica e chiamata. GuardieGitremote: scorer/engineclassici, scanner/engineBrain, modulioperativi, frontend e deploy non modificati nei rispettivi perimetri.
Fase implementazione/testCONCLUSA offline; nessun deploy/merge o prova predittiva nuova. Il limite scannerBrain resta documentato: metodologia consultiva non trasforma il Brain in cloneclassici.
Checkpoint GitHub+Library aggiornati; prossimo passo separato: validazione quantitativa nuova e completamento apertiBrain/classici già elencati.
AI: chatgpt Work
