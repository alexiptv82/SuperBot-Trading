# Checkpoint verificabile — 19/11/2026 21:48 Europe/Rome

**Tipo:** delta consolidato rispetto al checkpoint delle 20:49; solo documentazione; PAPER soltanto.

## Correzione dell'incongruenza sulle autorizzazioni

Le conversazioni recenti ora effettivamente accessibili attestano una decisione esplicita dell'utente del 19/11/2026: merge tecnici temporaneamente autorizzati **solo** in `integration/brain-unico-20261119`, subordinati a isolamento dal sistema operativo, test prima/dopo, zero regressioni, conflitti/dipendenze verificati, documentazione e rollback. Restano non autorizzati merge su `main` o rami operativi, deploy, servizi/VPS, stop/restart, soglie operative, reset, backup/storici privilegiati, credenziali, API a pagamento e LIVE.

Il checkpoint delle 20:49 aveva correttamente segnalato che tale consenso non era visibile nella ricerca svolta allora. La nuova evidenza accessibile risolve quel conflitto: la sezione 2 di `AUTORIZZAZIONI.md` è coerente con la decisione utente. Non cancellare il checkpoint precedente: conservarlo come traccia della limitazione di visibilità risolta.

Il commento pubblico di conferma su Issue #113 non risulta presente al controllo (ultimo commento 19/11 15:22:17 UTC); ciò non annulla la decisione recuperata dalla conversazione, ma resta utile per una fonte condivisa.

## Nuovo delta GitHub verificato

- Nuovo commit documentale su `diario`: `f6d43a4445c78da63cfde19b234e57aa89b2496e`, “Claude P0 #124 bis, valutazione #123, rischio v2 rivisto, provenienza autorizzazione”.
- `integration/brain-unico-20261119` è avanzato da `0b86f18b1d96d63c4a443f124c316e1090b8ba41` a `dd414831ef329ab1bc34d517dffffb85731af5bc`, otto commit avanti nel delta.
- Branch P0 `claude/brain-unico-daily-loss-latch-p0-20261119` verificato @ `a177729107231199f802f38e5592ab6e5373ea48`.
- Branch Grok PR #123 `cursor/brain-llm-cost-lab-20261119-31c4` verificato @ `c51c7520b35640518baea217404da9657702d4f5`.
- PR #121/#122/#123 restano open/draft e non mergiate formalmente su GitHub; il loro contenuto è stato integrato nel solo ramo laboratorio autorizzato. PR #120 resta open/draft e non integrata.
- RC84 PR #80 resta open/draft @ `0e29a73a36f668643da4088178bacb8616a45ac0`.

## P0 #124 — seconda correzione necessaria

Il codice precedente `ddd130847ae6ccdd2300b4d4ceba1ccde7e2a75e` conservava un fail-open nello scenario indicato dal proprietario:

1. stato `ok` persistito alle 10:00;
2. perdita oltre soglia alle 10:01, ma fallisce la scrittura del latch;
3. PnL rientra e riavvio alle 10:02.

Sul candidato precedente il riavvio poteva tornare `ok` perché la tolleranza di tre minuti trattava come valido lo stato su disco. Correzione `a177729107231199f802f38e5592ab6e5373ea48`, integrata nel laboratorio con merge `cc35f53278f6dfd79f839accbebbef2660d81a18`:

- tolta la finestra di tolleranza;
- primo controllo dopo ogni avvio: ricostruzione obbligatoria dall'ultimo stato persistito;
- nello stesso processo si evita la ricostruzione soltanto se nessuna chiusura di minuto è stata saltata;
- ricostruzione non riuscita ⇒ `unverified`, recuperabile al primo tentativo riuscito o col nuovo giorno UTC;
- nuove aperture bloccate in incertezza; uscite/sidecar indipendenti.

Claude riferisce sei nuovi test rossi sul codice precedente e verdi sulla correzione; suite P0 5071, integrazione 5087→5095, zero falliti. Evidenza offline, non GitHub Actions e non VPS. Issue #124 resta open; nessun deploy.

## PR #123 Grok — recuperata dal repository, nessun trasferimento manuale

Alla domanda recente dell'utente se il progetto Grok dovesse essere passato a Claude, la risposta consolidata è: **no trasferimento manuale necessario**, perché il lavoro è già nel repository sul branch PR #123. Claude lo ha recuperato, verificato e integrato nel ramo laboratorio autorizzato.

Delta laboratorio:

- commit Grok `cacedcc4e8a0e325a384fdc7514d55342e0f3d29` + diario `c51c7520b35640518baea217404da9657702d4f5`;
- estensione Claude input equivalente al Brain `6d6194326477d02516e19173586aa5e1dae1eba8`;
- merge laboratorio `8fc2139b3fca778a7f66018fe82b0de4e3be3656`;
- prova di equivalenza `context_hash` `4d246639a1bbcc3bcac2f1a0a881934bfcd3f23e`;
- merge finale `dd414831ef329ab1bc34d517dffffb85731af5bc`.

Stato funzionale preparato:

- laboratorio shadow isolato, nessuna importazione dal runtime trading e `may_open=false`;
- DeepSeek resta decisore; PR #120/router gratuito non attivata;
- modelli fissi, nessun `auto`, nessun fallback a catena;
- input costruito dal vero analista L5 con trasporto catturato offline; per le aperture, equivalenza verificabile mediante `paper_open.context_hash`;
- nessun provider chiamato, nessuna chiave, nessun costo, nessun journal operativo modificato.

Test riferiti: 13/13 Grok più 13 Claude = 26 test; mutazioni 9/9; suite integrazione 5095→5120→5121, zero falliti. Non replicati da questo checkpoint e non Actions.

Mancano ancora autorizzazioni separate per storici reali/Fase0, rete/provider, chiavi, chiamate gratuite, FreeLLMAPI sulla VPS o shadow forward. Nessuna di queste attività è autorizzata da questo checkpoint.

## Rischio v2 — correzione aritmetica

Il primo studio e il checkpoint 20:49 contenevano una conclusione troppo forte: “20–50× servirebbero solo con stop sotto 0,3%”. Il documento aggiornato la corregge:

- la leva non cambia la perdita prevista allo stop; cambia margine impegnato e distanza dalla liquidazione;
- con rischio 1–1,5% su equity PAPER 2.000 USDT, leve 20–50× possono essere matematicamente compatibili con margini ridotti;
- il conflitto nasce quando si pretendono contemporaneamente margine fisso 200–350/400, leva elevata, stop non stretto e rischio monetario basso;
- il vincolo corrente perdita/margine ≤21,4% esclude molte combinazioni; il PAPER non simula automaticamente la liquidazione reale;
- commissioni, slippage, gap e distanza dalla liquidazione devono restare nel dimensionamento risk-first.

Questa è analisi/proposta: nessuna soglia, leva, size, floor o parametro runtime è stata modificata. Restano 35% WARN, 50% HALT e hard floor 450 USDT finché l'utente non approva una configurazione diversa.

## Stato consolidato dei tre portafogli PAPER

- **Falco:** storico e logica SHORT preservati; advisor non bloccante nel Brain Unico.
- **Toro:** storico preservato come archivio/benchmark; nessun reset.
- **Brain:** integrazione di laboratorio @ `dd414831…`; Brain Unico non risulta deployato. Brain storico/Arena, EventJournal, memorie, decisioni, trade, posizioni, NO_TRADE e scoreboard vanno preservati integralmente.
- Snapshot non attestati restano esclusi dal training. Il laboratorio LLM non decide né apre trade.
- Arena non deve bloccare lo sviluppo, ma stop/conclusione anticipata, posizioni e backup richiedono consenso operativo distinto.

## Servizi, backup e chiavi

- Nessun controllo live VPS svolto in questa esecuzione. Le osservazioni precedenti restano attribuite al rapporto non-root di Claude.
- Extbackup: branch `work/extbackup-bot-stopped-20261109` verificato @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`. La precedente dicitura “preparato, non installato” confligge col timer riferito da Claude; versione installata, contenuto, cifratura, destinazione off-host e restore non verificati. Backup non certificato.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente. Prova locale, non certificazione del backup o restore VPS.
- Nessun segreto letto o pubblicato.

## Eseguito, preparato, non approvato

- **Eseguito nel ramo laboratorio autorizzato:** seconda correzione P0, integrazione PR #123, input equivalente e prova `context_hash`.
- **Preparato/non operativo:** confronto LLM offline, campione storico proposto, rischio v2 rivisto.
- **Non approvato/non eseguito:** merge su `main`/rami operativi, deploy, Actions, modifiche VPS/servizi, root, reboot, reset, ordini, provider reali, chiavi, API a pagamento, training reale, restore o LIVE.

## Blocker, prossime attività e ripresa

1. Review indipendente di `a177729…` e della catena laboratorio fino a `dd414831…`; replicare offline test e fault scenario prima di qualunque release.
2. Aprire/aggiornare la PR P0 quando i permessi GitHub lo consentono; Issue #124 resta P0 aperta fino alla chiusura formale.
3. Tenere PR #120 non integrata; DeepSeek resta decisore e #123 resta shadow isolato.
4. Per un confronto LLM reale servono consenso separato, copie storiche attestate, protocollo preregistrato e privacy/costi/provider verificati.
5. Nessun deploy finché matrice GO/NO-GO non ha zero P0 e backup/restore attestati.
6. Riprendere da `STATO.md`, `AUTORIZZAZIONI.md`, questo checkpoint, registro integrazione, evidenze P0 e valutazione PR #123. Distinguere sempre test riferiti, replicati, Actions, VPS, approvato, installato e live.

Solo documentazione in questa esecuzione; nessun codice operativo, merge, deploy, Action, VPS, restart, reset, ordine, training o API a pagamento.
