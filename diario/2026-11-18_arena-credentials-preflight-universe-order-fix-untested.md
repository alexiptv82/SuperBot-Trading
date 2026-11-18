# Checkpoint 18/11/2026, 16:51 Europe/Rome — CREDENZIALI/PREFLIGHT OK; FIX ORDINE UNIVERSO NON TESTATO

**Tipo:** delta append-only rispetto al checkpoint delle 15:51. Solo documentazione; nessun merge, deploy, Action, modifica VPS, T0, ordine o API a pagamento in questa esecuzione.

## Novità verificate

1. **Budget OpenRouter verificato senza inferenze.** Nel commento PR #110 delle 16:00, screenshot Termius registra per Qwen e MiniMax `LIMITE_6_USD_VERIFICATO` e `CONTROLLO_COMPLETATO`. Il controllo ha usato introspezione `/key`, non completamenti a pagamento.
2. **Credenziale DeepSeek Arena predisposta separatamente.** Alle 16:15 è documentata una configurazione atomica con permessi 0600, senza alterare il file Brain storico e senza avviare runner. Non è prova di validità live della chiave né di hard cap provider; il conto potrebbe essere condiviso.
3. **Decisione utente sulla gara 72h.** DeepSeek/Qwen/MiniMax devono operare autonomamente su tre portafogli PAPER separati, incluse le uscite automatiche; durante la gara non sono previste chiusure manuali Samsung. Brain storico continua separato e fuori classifica; Falco/Toro restano spenti. Il bridge web/manual-close non è quindi blocker T0 per questa gara e non va ricreato in produzione solo a tale scopo. T0 non è comunque autorizzato implicitamente.
4. **Preflight Arena completato in pausa.** Alle 16:31 lo screenshot registra `STATO_GARA=PREPARED_PAUSED_NO_T0`, `BLOCCHI=[]`, tre provider con uscite abilitate, zero posizioni e pausa attiva; budget totale 18 USD e nessuna verifica costi pendente. Nessun runner decisionale o T0 avviato.
5. **Snapshot universo fresco ma confronto bloccante.** Alle 16:38 lo snapshot Bitget risultava fresco, schema valido, 27 mercati, target crypto valido e XAU/XAG presenti; i confronti esatti fallivano. Il diff read-only delle 16:40 ha provato che i tre provider hanno lo stesso insieme di 27 simboli, senza mancanti o extra, ma in ordine diverso. La causa è il confronto order-sensitive in `trial_setup.activate`.
6. **PR #110 aggiornato, correzione non ancora provata.** Nuovo HEAD verificato `9b417e7e24c3a59aa003937cc2bb47685ace3863` (commit codice `bf88da5`, commit test `9b417e7`). La modifica minima accetta stesso insieme con ordine diverso e continua a rifiutare duplicati, membership diversa, hash snapshot alterato, schema errato, target crypto insufficiente o snapshot oltre 6 ore. Aggiunti test mirati, ma **pytest non è stato eseguito**: revisione soltanto statica. Snapshot/config e hash evidenze T0 restano invariati.

## Stato consolidato per la ripresa

- **Obiettivo e portafogli:** gara comparativa PAPER 72h fra DeepSeek, Qwen e MiniMax, tre portafogli separati e uscite autonome. Brain storico continua separato; Falco/Toro ritirati/spenti. Storici, SHORT Falco ed EventJournal vanno preservati.
- **Desiderato vs implementato:** autonomia decisionale/uscite e budget 6 USD per concorrente sono desiderati; run sostituite, exit-worker sani e preflight in pausa sono verificati. T0, runner decisionali e inferenze non sono partiti. La correzione order-insensitive è solo nel PR e non testata/installata.
- **Rischio/costi:** massimo desiderato 18 USD totale. Qwen/MiniMax hanno controllo remoto non sensibile del limite 6 USD; DeepSeek resta privo di hard-cap provider verificato e non deve interferire col Brain storico.
- **Servizi/backup/chiavi:** nessun controllo live indipendente VPS in questo checkpoint. La copia cifrata age sul PC aveva prodotto `ESITO: VERIFICA OK` e chiave pubblica coincidente, ma ciò non certifica il backup VPS. `work/extbackup-bot-stopped-20261109` resta preparato e non installato. Non sono stati letti o pubblicati segreti.
- **Riferimenti:** PR #110 draft HEAD `9b417e7e24c3a59aa003937cc2bb47685ace3863`; RC84 PR #80 resta all'ultimo dato verificato `0e29a73a36f668643da4088178bacb8616a45ac0`.
- **Conversazioni:** accessibili soltanto gli estratti recenti e i riscontri allegati/commentati; nessuna trascrizione integrale di chat eliminate.

## Fatto / preparato / rilasciato

- **Fatto e verificato da screenshot/commenti:** limiti Qwen/MiniMax; predisposizione separata DeepSeek; decisione no manual-close durante la gara; preflight in pausa; diagnosi del mismatch solo d'ordine.
- **Preparato ma non rilasciato:** fix PR #110 e relativi test; backup esterno; candidato web/manual-close, ora differito per la gara.
- **Rilasciato/attivo:** nessun T0, runner decisionale Arena, inferenza pagata, merge, deploy, modifica produzione/VPS o ordine LIVE.
- **Non approvato:** installare il fix, avviare T0, ricreare il web produzione, modificare Brain storico/portafogli, usare API a pagamento o passare a LIVE.

## Problemi e prossimo passo

1. Eseguire in ambiente isolato il sottoinsieme pytest mirato alla normalizzazione dell'universo e ai casi di rifiuto; registrare comando, esito e SHA.
2. Solo con test PASS, valutare un update-stage controllato e ripetere il preflight read-only, senza assegnare T0.
3. Richiedere autorizzazione separata prima di qualunque installazione su VPS o avvio della gara PAPER.
4. Conservare backup, run precedenti, storici ed EventJournal; non ripetere replace/smoke già conclusi.

## Limiti

Questo checkpoint non certifica stato live VPS oltre le prove recenti, non installa accessi remoti e non interpreta `ok procedi` come autorizzazione a deploy/T0. La correzione resta non testata e non installata.
