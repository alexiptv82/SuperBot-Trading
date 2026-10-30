# AI roles — SuperBot Brain unico e classici (decisione utente 30/10/2026)

## Brain nuovo (isolato, solo PAPER, NON in produzione)

- **DeepSeek** e' il provider primario H24. Nessuna finestra oraria 08–20: `brain_scalp/service.py` usa `make_primary()` e `PaperSupervisor.step()` opera indipendentemente dall'ora del giorno, se sono presenti candidati, dati freschi, budget e limiti di protezione soddisfatti.
- `deepseek-flash` e `reasoning_effort=high` (selezione in `transports.py`). Un'analisi non significa un ordine e non ci sono aperture forzate per riempire slot.
- **Claude** e' il revisore selettivo: chiamato solo per `timing_uncertain`, `timeframe_conflict` o disaccordo con il riferimento classico; non e' un secondo motore che decide ogni candela. Lo stesso context_id viene riutilizzato. Se la revisione e' obbligatoria e il revisore non e' disponibile, la proposta resta non ammissibile e non c'e' fallback meccanico.
- Fuori dal budget o a provider non disponibile il Brain non inventa nuove decisioni. Gli stop locali e la gestione delle posizioni PAPER proseguono sul thread proprietario indipendentemente dal provider. La prenotazione costo massima non e' la fattura API: prima del rilascio verificare prezzi token e gestione credito.
- **H24 e' disponibilita' delle valutazioni quando serve, non una chiamata ad ogni minuto o un obbligo di aprire.** Il loop protettivo previsto e' 5 s e l'intervallo tra richieste AI 5 minuti; allarmi e limiti possono impedire nuovi ingressi.
- La modalita' operativa richiede mandato finanziario completo e credenziali sicure. Nessun merge, deploy, server attivo o richiesta pagata da questo ramo.

## Classici Falco (Hawk) / Toro (Bull)

- Preferenza approvata: **regole meccaniche primarie**, con AI minima o completamente esclusa. Il ramo `work/classics-manual-teaching-20261030` supporta `DESK_CLASSICS_AI_MODE=rules_only`, che blocca le richieste Claude mantenendo regole di ingresso/uscita e protezioni; `scheduled` e' il comportamento precedente.
- Le tre verifiche storiche ancora fallite sulla vecchia impostazione Claude non richiedono di potenziare Claude nei classici. Sono aspettative di test legacy da riclassificare/adeguare alla configurazione meccanica, non un motivo per disabilitare i rischi o forzare i bot.
- Le chiusure manuali dei classici sono eventi che **possono** essere confermati come insegnamento, non si trasformano automaticamente in nuovi prompt o ordini.
- Nessun dato/lezione di un portafoglio viene fuso nel Brain unico senza una migrazione controllata e approvazione separata.

## Release gates non superati

Test end-to-end con dati pubblici reali, supervisione costi/credito, approvazione mandato, backup e restore, single reader Telegram, verifica PWA compatibile, autorizzazione separata a merge/deploy. Tutto resta PAPER.

AI: chatgpt
