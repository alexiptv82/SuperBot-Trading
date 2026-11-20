# Checkpoint verificabile SuperBot-Trading — 20/11/2026 17:46 Europe/Rome

## Esito sintetico

Il proprietario ha chiuso la linea d'indagine sui dati classici: **Falco e Toro devono essere conservati integralmente, senza modifiche, ma classificati come archivi storici semanticamente non certificati**. Non devono entrare automaticamente nel training e non devono essere sottoposti ad altre indagini o prove Termius senza una nuova richiesta. La decisione è implementata nel ramo `integration/brain-unico-20261119` a `f9009aee2432a31e6304032ffb000fe5eba88243`: le righe restano nel dataset con stato `excluded` e motivo `semantic_not_certified`, senza concorrere a split, sufficienza o training.

## Obiettivi e vincoli invariati

- Trading esclusivamente **PAPER**; portafogli distinti **Falco**, **Toro** e **Brain**.
- Priorità operativa e progettuale: Brain Unico verificabile, memoria preservata, rischio esplicito e training solo su dati attestati.
- `EventJournal` e storici append-only; dati originali dei classici intoccabili.
- `NO_TRADE` valido; nessun riempimento forzato degli slot.
- Nessun merge, deploy, riavvio, reset, ordine, training, API a pagamento o modifica operativa da questo checkpoint.

## Decisione utente e configurazione implementata

| Area | Decisione/desiderato | Implementato | Ancora aperto |
|---|---|---|---|
| Falco/Toro | conservarli integralmente, senza riconciliare o riscrivere i dati | archivi marcati semanticamente non certificati | nessuna nuova indagine senza nuova richiesta |
| Dataset | conservare tutte le righe per memoria/audit | righe Falco/Toro presenti con stato `excluded` | nessuna cancellazione |
| Training | usare solo fonti attestate | gate `semantic_not_certified`; esclusione da split, sufficienza e training | revocabile soltanto con nuova decisione e modifica esplicita del codice |
| Brain/Arena | componenti indispensabili per Brain Unico | journal V3 verificati nella prova reale precedente | backup esterno permanente e restore PC ancora da autorizzare/certificare |
| Rischio | limiti, stop, mandato e circuit breaker approvati | anti-reingresso `observe`; perdita giornaliera read-only | `enforce`, profilo rischio v2 e mandato nuova run non approvati; Issue #124 aperta |

## Evidenze e anomalie preservate

- Falco: differenza PAPER di +21,13 USDT tra cassa+salvadanaio e capitale+risultati.
- Toro: differenza PAPER di +39,08 USDT e 25 trade nello stato contro 55 nello storico, quindi 30 righe soltanto nello storico.
- Questi dati non vengono corretti, cancellati o promossi al training. Sono conservati come evidenza storica non certificata.
- Non viene assunta una causa definitiva delle anomalie; l'indagine è sospesa per decisione del proprietario.

## Backup e restore: stato consolidato

- Prova reale precedente: archivio cifrato di 117.472.954 byte; journal validi Brain 1.058, DeepSeek 1.260, Qwen 1.281 e MiniMax 1.306.
- Esiti formalizzati dal candidato extbackup: 0 = certificato; 1 = difetto tecnico/NO-GO; 3 = integro ma semanticamente non certificato. L'esito 3 non è un successo completo.
- Falco/Toro restano nell'archivio con esito semantico non certificato; Brain/Arena mantengono l'integrità tecnica verificata.
- Il file di circa 117 MB supera il limite GitHub di 100 MB per singolo file: preparare archivi separati per componente resta una attività futura, non eseguita.
- Installazione dell'extbackup aggiornato e prova di ripristino sul PC richiedono consenso separato.

## Branch, PR, issue e SHA verificati

- `diario` prima di questo checkpoint: `d12f3ce89d5fc3cf4c2be03796f5065d35537ce2`.
- `integration/brain-unico-20261119`: `f9009aee2432a31e6304032ffb000fe5eba88243`.
- `claude/extbackup-storici-20261121`: invariato a `f60b90d64521cd8834f6f99d85d7fe04f8187d99`.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): **open**, P0.
- Ramo storico `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`, preparato e non installato/certificato secondo lo stato consolidato.
- `main` è stato verificato a `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`; i relativi commit PAPER sono storici dell'11-12/11 e non costituiscono novità di questa esecuzione.

## Test con fonte

- Commit `f9009aee…`: gate documentato **V3 5.352**, Dataset Builder **158**, Jest **152**; righe classiche escluse dal training.
- Candidato extbackup `f60b90d6…`: 67 test dichiarati; esiti tecnici e semantici separati.
- I test non sono stati rieseguiti in questo checkpoint; i risultati provengono dai commit e dal diario e non sono presentati come GitHub Actions indipendenti.

## Chiavi e servizi senza dati sensibili

- Copia cifrata della chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. È una prova locale e non certifica il backup o restore sulla VPS.
- Nessuna chiave privata, passphrase, token, segreto, comando amministrativo o dettaglio d'accesso è riportato.
- Stato live generale di runner, exit service, app, extbackup e VPS: non verificato da questo checkpoint.

## Eseguito, preparato, non approvato

- **Eseguito nel repository:** esclusione deterministica di Falco/Toro dal training a `f9009aee…`; piano RC aggiornato; test dichiarati.
- **Decisione applicata:** conservazione integrale dei classici come storici semanticamente non certificati; priorità Brain Unico.
- **Preparato ma non eseguito:** separazione dell'archivio per componente, installazione extbackup e restore sul PC.
- **Esplicitamente sospeso:** ulteriori diagnosi contabili o prove Termius su Falco/Toro senza nuova richiesta.
- **Non approvato/non eseguito:** modifica degli storici, training dei classici, merge/deploy, cambi servizi/permessi/rischio, ordini, LIVE, API a pagamento.

## Blocker e prossime attività

1. Continuare Brain Unico usando soltanto fonti idonee e attestate; Falco/Toro restano esclusi.
2. Issue #124 P0, archivio candele non ancorato, profilo rischio e mandato nuova run restano blocker.
3. Solo con consenso separato: archivi cifrati per componente, installazione extbackup aggiornato e restore dal file cifrato sul PC.
4. Nessuna nuova indagine sui classici finché il proprietario non cambia esplicitamente decisione.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e l'ultima versione di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare le HEAD di `diario`, integrazione, candidato extbackup, PR #80, Issue #124 e ramo extbackup storico.
3. Conservare Falco/Toro ma non usarli in split, sufficienza o training; non modificare gli originali.
4. Trattare il backup corrente come integrità tecnica verificata per Brain/Arena e semantica non certificata per Falco/Toro.
5. Preservare PAPER, EventJournal e divieto di training su dati non attestati.

---

Checkpoint esclusivamente documentale; nessun segreto o dettaglio operativo d'accesso aggiunto.
