# Checkpoint verificabile SuperBot-Trading — 20/11/2026 08:43 Europe/Rome

## Ambito e limiti della verifica

Checkpoint esclusivamente documentale. Fonti effettivamente consultate: repository GitHub `alexiptv82/SuperBot-Trading` (ramo `diario`, `STATO.md`, ultimi checkpoint/commit/PR/issue) e file Library stabile `ULTIMO-STATO-SUPERBOT.md`. Le conversazioni recenti sono state considerate solo tramite contesto effettivamente accessibile; non si presume di ricostruire chat eliminate. Nessun controllo live della VPS, nessun deploy/merge/reboot/reset, nessuna Action avviata, nessun ordine o API a pagamento.

## Stato consolidato utilizzabile per la ripresa

### Obiettivo e vincoli permanenti

- SuperBot resta un sistema di trading **esclusivamente PAPER** con tre portafogli distinti: **Falco**, **Toro** e **Brain**.
- Conservare storici, audit trail ed EventJournal; nessuna operazione distruttiva o reset dei dati.
- Falco e Toro restano strategie deterministiche separate; Brain è il percorso adattivo/ML ma deve operare entro guardrail, tracciabilità, validazione walk-forward e possibilità di rollback.
- Stato desiderato: rischi e capitale isolati per portafoglio, sizing e limiti espliciti, stop/circuit breaker, confronto equo su dati coerenti, apprendimento solo da eventi verificabili.
- Stato implementato verificato: l'infrastruttura PAPER e i tre portafogli risultano documentati; non è provata in questa esecuzione la configurazione runtime effettiva né lo stato live dei servizi. Qualsiasi valore di rischio desiderato ma non dimostrato da file/test resta **da verificare**, non va presentato come attivo.

### Novità verificate dopo il checkpoint 07:45

1. **Seconda acquisizione storica riuscita, ma non ancora attestata dal proprietario**
   - Manifest: `candles-20261120T064955Z-95a00e9b`.
   - SHA-256 manifest: `4c982882e53324ce944279b3e016cc8b71f4b96e64e76e7a03afa0021aecf407`.
   - 8 simboli × timeframe 15m/1h/4h = 24 file; 47.352 righe su 47.376 attese; periodo documentato 04/10/2026–20/11/2026 00:00 UTC; 8,47 MB.
   - Budget: 264 tentativi acquisizione + 2 probe = 266/350; il probe BTCUSDT 15m ha usato 2 tentativi su massimo 3.
   - Integrità riportata `intact`; provenienza `manifest_unanchored`. Il confronto in memoria con l'anchor corretto restituisce `attested`, ma **l'anchor non risulta registrato dal proprietario**. L'archivio quindi non autorizza ancora training o decisioni operative.

2. **Difetto temporale del feed Bitget identificato**
   - `history-candles` seleziona rispetto al tempo di chiusura: tutti i 24 file acquisiti omettono esattamente l'ultima candela chiusa.
   - Impatto documentato: decisioni Brain arretrate di una candela (fino a 15 minuti sul 15m e 4 ore sul 4h); lo stesso schema interessa il monitor stop 1m.
   - Fix offline al commit `315edf155655b963952ff1ebf4fbcfbd5e90e2ec`: finestre `(end-200*step, end]` ed esclusione della candela in formazione.
   - Il fix **non è ancora confermato contro l'API reale**: serve un probe autorizzato con massimo 3 tentativi.

3. **Brain Unico e chiusure manuali**
   - Commit `095a0432d8ccbea82fd72abdd4872323246f8107`: schermata principale/redirect `/brain-unico`; manifest PWA invariato, quindi nessuna reinstallazione prevista dopo un eventuale futuro deploy.
   - La schermata riunisce profitti/perdite, statistiche, posizioni aperte con singola conferma, trade chiusi, stato sistema, memoria/tesi/apprendimento e storico Falco/Toro/Brain. **Arena non è ancora integrata**.
   - Le chiusure manuali sono conservate come eventi operatore (`reason=manual`, `is_manual`, `closed_by=operator`), hanno expectancy separata e sono escluse dallo scoreboard strategico e dall'imitazione/apprendimento.
   - Evidenza test del commit: 4 pytest E2E, 8 nuovi Jest; Jest 137/137 e build OK.

4. **Piano RC PAPER preparato, non approvato né distribuito**
   - Commit `8fa61d18e615533cb428911b751811f2fd846595`: bozza `docs/v3/BRAIN-UNICO-RC-PAPER-PIANO-20261120.md`.
   - Copre GO/NO-GO, backup/restore attestato, mandato, validazione di 14 giorni e rollback.
   - Ultima suite completa documentata su questo SHA: V3 5.310, builder 157, Jest 137, zero fallimenti. Non è dichiarata una nuova suite completa sul successivo HEAD.

5. **Validatore archivio corretto su dati reali**
   - HEAD verificato del ramo di lavoro documentato: `733182f6e3e8760aaf900c24215f51e8ed380154`.
   - Il validatore rifiutava feature reali come `t15m_ret_2880` perché la regex ammetteva solo tre cifre. Il commit HEAD estende il limite a cinque cifre.
   - Riscontro dichiarato: 24/24 campioni reali verificati e 24/24 manomissioni rilevate; test di regressione dimostra il fallimento della regola precedente.
   - Manca evidenza di una nuova esecuzione dell'intera suite sullo SHA `733182f6`.

6. **Valutazione competenze esterne: preparata, non adottata**
   - Sorgente isolata verificata al commit `981e1d7`, licenza MIT, 10 skill / 54 file / circa 860 KB.
   - Nessuno script o dipendenza eseguiti/installati; nessuna integrazione nel bot; PR non creata (permesso GitHub 403).
   - Solo cinque moduli sono candidati come supporto metodologico: exit strategies, risk management, position sizing, trade journal, walk-forward validation. Parti AMM/Solana o non pertinenti sono escluse.
   - Attivazione nella sessione non verificata (`Unknown skill`); nessuna approvazione all'adozione.

### Branch, PR, issue e backup verificati

- Ramo di lavoro documentato: HEAD `733182f6e3e8760aaf900c24215f51e8ed380154`.
- PR #80 RC84: aperta/draft, head `0e29a73a36f668643da4088178bacb8616a45ac0`; nessun merge/deploy provato.
- PR #120 `f4f745788e4514d01dc11e11402eb689a2ec7c74`, #121 `5b7403aa333b43d801ca7e28825ea4707f6847b4`, #122 `513448e57747f381e11ce23ab09788d6a41e6cb0`, #123 `c51c7520b35640518baea217404da9657702d4f5`: aperte/draft e non unite.
- Issue #124: aperta.
- Backup esterno sul ramo `work/extbackup-bot-stopped-20261109`, SHA `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: **preparato, non installato e non certificato**.
- Copia cifrata della chiave age sul PC: verifica PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente. Questo prova la leggibilità/coerenza della copia locale cifrata; **non certifica il backup né il ripristino sulla VPS**.
- Stato servizi, chiavi e backup VPS: non verificato live in questa esecuzione; nessun segreto letto o pubblicato.

### Eseguito / preparato / non approvato

- **Eseguito e verificato documentalmente:** acquisizione dei 24 file; rilevazione del difetto di ultima candela; fix offline; Brain Unico; semantica delle chiusure manuali; correzione regex del validatore; test specifici indicati sopra.
- **Preparato:** piano RC PAPER; backup esterno; valutazione metodologica delle skill; anchor corretto noto ma non registrato.
- **Non approvato/non eseguito:** registrazione anchor, training Brain sull'archivio, probe reale del fix feed, merge/deploy, installazione backup, restore test VPS, integrazione Arena, adozione skill esterne, trading reale.

### Blocker e prossime attività ordinate

1. Far registrare al proprietario l'anchor manifest e verificare lo stato `attested` da fonte persistente.
2. Con autorizzazione esplicita, eseguire il solo probe reale del fix feed con tetto di 3 tentativi; nessuna acquisizione massiva.
3. Eseguire la suite completa sullo SHA `733182f6` e registrarvi fonte/esito.
4. Integrare Arena nella vista storica e completare i controlli/latch delle perdite, solo tramite normale revisione PR.
5. Prima di qualsiasi RC: certificare backup/restore, mandato PAPER, GO/NO-GO, finestra di 14 giorni e rollback. Nessun deploy implicito.
6. Conservare EventJournal e storici; non trasformare chiusure manuali in segnali imitabili.

## Istruzioni di ripresa per un'altra AI

1. Leggere prima `STATO.md`, questo checkpoint e il file Library stabile; confrontare SHA/PR con GitHub prima di affermare novità.
2. Trattare `733182f6` come ultimo HEAD documentato, non come deploy VPS.
3. Trattare l'archivio come integro ma **non attestato** finché l'anchor non è persistito e verificato.
4. Non considerare risolto il difetto feed fino al probe reale autorizzato; il fix è soltanto offline.
5. Mantenere separati desiderato, implementato, testato e distribuito; indicare sempre la fonte dei test.
6. Non leggere/esporre segreti né inferire stato live VPS. Tutto resta PAPER.
