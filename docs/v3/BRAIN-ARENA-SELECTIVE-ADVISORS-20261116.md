# SuperBot AI Arena — collaborazione selettiva tra tre cervelli (16 novembre 2026)

## Decisione dell'utente

Dopo aver preparato tre Brain indipendenti, l'utente propone di utilizzare eventualmente **la migliore AI come principale** e le altre due **come consulenti solo quando serve**. Obiettivo: sfruttare punti di forza complementari senza triplicare le chiamate API. La strategia SHORT di Falco va conservata e ripristinabile; Toro puo' restare accantonato.

Questa proposta e' tecnicamente **sensata come esperimento**, ma non e' dimostrato che due pareri AI migliorino le performance. Non usare voto di maggioranza, non presumere che tre AI siano indipendenti statisticamente, e non attivare una modalita' collaborativa prima di verificarla.

## Due esperimenti differenti, senza confusione

**A — Arena comparativa (14 giorni):** DeepSeek, Qwen e MiniMax prendono decisioni senza leggere i pareri reciproci, su snapshot di mercato identici, tre wallet PAPER da 2.000 USDT, journal, budget ed esecuzioni PAPER separati. Misura qualita' direzionale, orari, rischio, PnL netto, drawdown, LONG/SHORT/NO_TRADE, costi e latenza. I 14 giorni iniziano al T0 comune, NON ora. Baseline Brain storica archiviata.

**B — Arena consultiva (solo dopo A e in shadow):** una delle tre AI resta il lead. In caso di reale dubbio, si chiede un parere ad **una** delle altre; soltanto se e' in disaccordo e rimane budget puo' essere consultata la terza. Nessuna consulenza puo' bypassare equity floor 450 USDT, risk gate, mandate, freschezza candele, servizio uscite, slot o politica di esecuzione. In questo stadio consultivo non invia ordini ne' modifica la decisione del lead.

In seguito, soltanto se B mostra un miglioramento prospettico dopo costi e senza regressioni di rischio, valutare l'attivazione come supporto al Brain PAPER principale previa autorizzazione distinta. Anche li' il lead resta responsabile e il rischio deterministico decide l'eseguibilita'.

## Gate deterministici di richiesta consulenza

Codice puro: `backend/v3/arena/selective_advisors.py`. Di default `enabled=False` e ritorna `SHADOW_ONLY`, `can_change_trade=False`, senza rete, comandi o scrittura.

Si consulta per una proposta OPEN solo quando c'e' uno di questi segnali:
- Fiducia numerica del modello **inferiore a 0,65** (soglia *sperimentale*, da calibrare).
- LONG contro il trend 4H ribassista o SHORT contro il trend 4H rialzista.
- Contrasto evidente fra trend 1H e 4H.
- Regime SHOCK.

**EXPANSION da sola non e' un veto e non provoca consultazione automatica**, perche' durante i crolli alcuni SHORT in alta volatilita' sono stati i migliori. NO_TRADE, dati mancanti/vecchi e proposte non eleggibili al rischio non vengono trasformati in trade tramite consulenza.

Prima chiamata: massimo un consulente non coincidente con il lead, richiede numero chiamate e budget residui. Seconda chiamata: soltanto se il primo e' in disaccordo e c'e' ancora budget. Segnali/risposte sono artefatti di studio da registrare, **non una causa automatica di apertura o chiusura**. Per impedire sovraconsumi, ogni fornitore mantiene limite per chiave (2 USD), budget software separato, massimo giornaliero, max per chiamata e log dei token.

## Stima economica semplice (NON addebito effettivo)

Prezzi per 1 milione di token mostrati dal catalogo OpenRouter sul VPS il 16/11/2026:
- Qwen 3.7 Plus: input **0,32 USD**, output **1,28 USD**.
- MiniMax M3.1 Flash: input **0,15 USD**, output **0,60 USD**.

**Scenario illustrativo:** richiesta da 3.000 token input e 1.000 token output:
- Qwen: (3000 × 0,32 + 1000 × 1,28) / 1.000.000 = **0,00224 USD** per consultazione.
- MiniMax: (3000 × 0,15 + 1000 × 0,60) / 1.000.000 = **0,00105 USD**.

**Uso pieno H24 a 8 simboli ogni ora, 14 giorni:** 8 × 24 × 14 = 2.688 richieste **per modello**. A quei token: Qwen ~**6,02 USD**, MiniMax ~**2,82 USD**, cioe' piu' degli attuali **2 USD di limite per chiave**. Non promettere che il confronto indipendente H24 sia fattibile per 14 giorni senza calibrare la frequenza o aumentare il budget autorizzato. Token di ragionamento, tariffe e retry potrebbero cambiare il conto.

**Collaborazione selettiva:** ipotizzando soltanto 20 consultazioni Qwen e 5 MiniMax al giorno, per 14 giorni: (20 × 0,00224 + 5 × 0,00105) × 14 = **0,70 USD** circa complessivi per i due consulenti, **oltre** ai costi dell'AI principale e senza commissioni/tasse. Questo e' un esempio, non una promessa e non rappresenta le reali percentuali di trigger. Se entrambi fossero consultati 20 volte/giorno: ~0,92 USD in 14 giorni. Il budget del test va valutato sulla telemetria e sulla disponibilita' effettiva del saldo OpenRouter.

La spesa minima effettiva per testare il beneficio dei consulenti puo' essere limitata a **shadow on-demand su campione** anziche' doppiare tutti i cicli.

## Cosa registrare per ogni parere

- `decision_event_id` del lead, symbol, `timestamp_ms`, hash del contesto di candele chiuse, trigger causale; ID consulente, latenza e token/costo.
- Richiesta sintetica a un consulente, nessuna informazione futura e nessuna posizione di altri portafogli non necessaria; risposta strutturata `AGREE/CHALLENGE/UNSURE` piu' `NO_TRADE/LONG/SHORT`, codici rischio da un'allowlist; niente testo libero nelle ragioni del journal.
- Stato di rischio dopo il parere separato dalla sua qualita', risultato controfattuale delle decisioni con/senza consulenza, disaccordi, falsi allarmi, rinunce valide. Valutare il guadagno *marginale* dei pareri sulle medesime opportunita', non l'impressione di maggiore intelligenza.
- Nessuna decisione del consulente ha autorita' di trading. Un modello offline o il suo errore non deve bloccare il servizio uscite.

## Falco preservato

Archivio codice creato: `archive/falco-short-before-ai-arena-20261116` ancorato al commit storico `fed2e3fd32ff162d22b045b4a8e5f0524e88a9b7` del ramo `rule-pool`. Questa copia e' **solo codice GitHub**, non sostituisce il backup coerente e verificato del Falco V3 attivo in VPS. Vedi `docs/v3/FALCO-SHORT-PRESERVATION-BEFORE-AI-ARENA-20261116.md` per il protocollo di conservazione dati e uscite.

## Stato

- `selective_advisors.py` e relativi test offline creati su ramo isolato; **nessun test eseguito su GitHub Actions**, nessuna esecuzione su VPS.
- Nessun consulente attivato, nessun ordine PAPER effettuato con questo modulo.
- Tre runner PAPER separati e integrazione frontend live NON ancora completati; non annunciare T0 o avvio esperimento.
- Falco e Toro non sono stati fermati o modificati.
