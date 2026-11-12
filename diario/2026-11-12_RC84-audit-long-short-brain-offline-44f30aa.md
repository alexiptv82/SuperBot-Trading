# Checkpoint 12/11/2026, 14:45 Europe/Rome — Audit RC84 LONG/SHORT/Brain offline; analizzatore da correggere

## Fonte nuova verificata

Sul ramo di sessione `ccr-999de027-0stnyt` è stato pubblicato il commit firmato [`44f30aa74a279ecd2a59237bf89c7d4eaaabd365`](https://github.com/alexiptv82/SuperBot-Trading/commit/44f30aa74a279ecd2a59237bf89c7d4eaaabd365), messaggio `docs(audit): RC84 audit SHORT vs LONG e Brain, con analizzatore offline dei registri PAPER [skip ci]`. Il commit aggiunge:

- `docs/v3/RC84-AUDIT-LONG-SHORT-BRAIN-20261112.md`;
- `deploy/scripts/audit_long_short.py`.

Base esaminata: sorgente RC84 distribuita `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`. L'audit dichiara sola lettura del codice e prove sintetiche offline sul codice reale di `signals.py`: nessun accesso VPS, nessun registro PAPER reale, nessun ordine e nessuna modifica operativa.

## Risultati dimostrati offline

1. **EMA200 4h accorciata:** con 1.000 candele 15m restano circa 62 barre 4h e il codice usa di fatto EMA61. In 40 scenari sintetici ribassisti con rimbalzo, 23 hanno armato LONG ≥60 mentre la vera EMA200 4h restava ribassista.
2. **Trend giornaliero assente:** la storia standard copre circa 10 giorni, sotto le 30 barre richieste; il filtro 1d non si attiva. Esiste inoltre un bug latente per 30–49 barre che può etichettare bear anche un rialzo forte.
3. **Conferma inversione non vincolante:** il modulo è advisory e il bias 4h resta UNKNOWN con la storia standard.
4. **Candele non chiuse nei punteggi:** prova sintetica da 52 a 64 punti, da medio a scalp, per uno spike su candela aperta; la freschezza del prezzo esecutivo è un controllo diverso.
5. **S25:** in `ab7e0b7` i nuovi ingressi sono spenti di default e richiedono doppio opt-in Toro; eventuali operazioni precedenti restano da separare dai registri.
6. **Divario prompt/motore:** soglia R:R motore 1,5 e saltabile senza TP, soglie Toro inferiori a quelle dichiarate, TP minimo 5% non imposto, guardrail che può alzare margine/leva di una proposta prudente, fallback a 1,8×SL.
7. **Funding PAPER asimmetrico:** addebitato solo ai LONG, quindi ogni confronto LONG/SHORT va letto anche al lordo del campo funding.

Le sei chiusure del 12/11 (+234,64 USDT, tutte TP) non hanno la direzione nel riepilogo accessibile: **non sono prova che gli SHORT abbiano prodotto il risultato**. L'ordine causale delle perdite LONG resta ipotesi da verificare sui registri reali.

## Brain RC84

Il rapporto verifica nel codice distribuito la presenza delle quattro correzioni già documentate: paginazione/storia 3.000+, sola candela chiusa, parser leva fail-closed fino a 200 senza aumentare il tetto di rischio, esito ultimo ciclo persistito nell'heartbeat. Non è stato osservato un ciclo analitico completo dopo il rilascio: Brain resta in pausa. Alla futura attivazione, autorizzata separatamente, la prova deve controllare dati/contratti, chiamata analista, spesa registrata e decisione nel journal; NO_TRADE con dati validi è esito corretto.

## Limite successivo sullo strumento quantitativo

Una revisione recente accessibile ha segnalato che `audit_long_short.py` va corretto prima dell'uso autorevole sui registri reali. L'ispezione diretta del commit conferma almeno:

- cutoff predefinito `2026-11-12T12:37:00Z`, mentre il cutover documentato alle 12:37 Europe/Rome corrisponde a 11:37Z;
- separazione prima/dopo basata su `close_ms`, non sull'istante di apertura `open_ms`.

Restano inoltre da riesaminare aggregazione dei parziali/identificativi e collegamento con `learning_log`. Lo script è quindi **preparato e provato solo su dati sintetici**, non approvato né eseguito sui dati VPS e non va usato per conclusioni reali finché corretto e ritestato su copie.

## Stato consolidato PAPER e infrastruttura

| Portafoglio | Ultimo stato verificato | Configurazione/rischio |
|---|---|---|
| **Falco** | RC84 avviato in pausa; heartbeat `draining`; conteggio corrente non noto | PAPER; token Telegram nativi assenti; relay separato post-cutover da riverificare |
| **Toro** | RC84 avviato in pausa; heartbeat `draining`; conteggio corrente non noto | PAPER; token Telegram nativi assenti; relay separato post-cutover da riverificare |
| **Brain** | Runner `paused`, exit `healthy`; nessun ciclo completo post-RC84 provato | PAPER; mandato/rischio invariati; notifiche e ciclo reale non verificati |

Restano verificati: cutover PR #90 applicato su `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`, blob `dcabc6683e517f09ead3e0bca1a91a719eaf26d0`; sorgente PR #85 `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`; PR #85–#90 Draft/non mergiate; tre pause conservate e resume non autorizzato. I valori Falco 7/Toro 3 appartengono allo snapshot precedente, non sono conteggi correnti.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; prova locale, non certifica il backup sulla VPS né un restore off-host. PR #80 RC84 resta riferimento storico Draft. Nessun dato sensibile è stato letto o salvato.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito e verificato:** audit statico/offline e prove sintetiche; pubblicazione del solo commit documentale/analizzatore sul ramo di sessione; verifica del commit GitHub firmato.
- **Preparato:** analizzatore read-only, ma con correzioni necessarie prima dell'uso reale; proposte continuazione/inversione e allineamento prompt/motore, non implementate.
- **Rilasciato operativo:** nulla da questo audit. Lo stato installato resta il cutover RC84 già documentato, sotto pausa.
- **Non approvato/non eseguito:** nessuna modifica E1–E7, nessuna esecuzione sui registri VPS, nessun resume, merge, deploy, Action, restart, reset, ordine, LIVE o API a pagamento.

## Blocker, prossimo passo e istruzioni di ripresa

1. Correggere lo strumento in un ramo di lavoro: cutoff Europe/Rome→UTC corretto, attribuzione per `open_ms`, parziali/ID e collegamento learning; aggiungere test sintetici mirati.
2. Solo dopo revisione, eseguirlo su **copie** di `trade_history.jsonl`/stato e non sui file vivi; separare LONG/SHORT, origine, orizzonte, S25 e funding.
3. Non toccare strategie o rischio finché i risultati reali non sono misurati e approvati.
4. Prima di qualunque resume: controlli read-only del relay Telegram, heartbeat/exit Brain, tre pause, EventJournal e integrità storici; resume resta non autorizzato.
5. Preservare PAPER, wallet, EventJournal, learning, snapshot e rollback. Backup off-host e restore restano non certificati.

**Limiti di accesso:** consultati GitHub, Library e le sole conversazioni recenti effettivamente restituite. Nessuna trascrizione integrale di chat eliminate e nessuna verifica live della VPS successiva ai riscontri già documentati.
