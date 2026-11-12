# Checkpoint 12/11/2026, 16:50 Europe/Rome — Roadmap proposta: Falco SHORT-only, Toro LONG+SHORT; non applicata

## Nuova decisione/proposta recuperata

Nella conversazione recente l'utente ha proposto tre alternative per rendere il confronto PAPER più leggibile:

1. **Falco solo SHORT**;
2. **Toro LONG+SHORT**, usando per i LONG la nuova strategia ancora da correggere/validare;
3. in alternativa, aggiungere un quarto portafoglio solo SHORT.

La risposta progettuale recuperabile raccomanda come **architettura-obiettivo provvisoria**:

- **Falco:** SHORT-only, configurazione reversibile;
- **Toro:** LONG+SHORT, con strategia LONG nuova sottoposta a filtri e test;
- **Brain:** indipendente, invariato;
- **nessun quarto portafoglio per ora**, per evitare nuova infrastruttura, altro capitale PAPER, altra UI/telemetria e un confronto più difficile da interpretare.

Questa è una decisione di roadmap/esperimento, **non un'autorizzazione a modificare configurazioni o servizi**. Nessuna modifica è stata applicata.

## Motivazione e limite dell'evidenza

L'idea nasce dal rapporto quantitativo provvisorio documentato alle 15:48:

- 6 LONG S25, tutti stop, −270,21 USDT;
- 13 SHORT Rules Scalp, 12 vincenti, +581,13 USDT.

Ma la PR #91 ha dimostrato una lacuna: il comando originario poteva aver letto il layout legacy anziché i wallet RC84 V3. Quindi questi numeri non sono ancora una prova definitiva della versione corrente e non giustificano da soli la rimozione permanente dei LONG.

La scelta SHORT-only di Falco deve quindi essere trattata come **esperimento PAPER reversibile**, non come conclusione “gli SHORT lavorano senza ombra di dubbio in ogni regime”. Campione ridotto, regime di mercato e provenienza dataset vanno ancora controllati.

## Disegno sperimentale desiderato vs implementato

| Componente | Desiderato/proposto | Implementato |
|---|---|---|
| **Falco** | nuove aperture esclusivamente SHORT; uscite delle posizioni storiche sempre gestite; interruttore reversibile | **No**: nessun commit/config/deploy |
| **Toro** | LONG+SHORT; LONG con strategia corretta, candele chiuse e contesto 4h/1d affidabile | **No**: nuova strategia non approvata né applicata |
| **Brain** | indipendente, AI-first, NO_TRADE valido | invariato; resta in pausa |
| **Quarto bot SHORT** | alternativa valutata | scartato/rimandato per ora |
| **Confronto** | stessi periodi, capitale/rischio comparabili, metriche per lato e regime | non avviato |

Non vanno chiuse forzatamente posizioni aperte per ottenere il confronto. Le uscite e gli storici devono continuare a essere preservati.

## Prerequisiti prima di qualunque implementazione

1. Completare la [PR Draft #91](https://github.com/alexiptv82/SuperBot-Trading/pull/91): eseguire i tre test nuovi e rigenerare il rapporto sui wallet RC84 V3 con copie coerenti.
2. Attendere il risultato Cloud/audit indipendente citato nella conversazione; nessun risultato nuovo era ancora disponibile in questa esecuzione.
3. Definire il guardrail in sola configurazione o patch minimale:
   - Falco rifiuta soltanto nuove aperture LONG;
   - SHORT e gestione uscite restano invariati;
   - nessuna interferenza con posizioni già aperte;
   - rollback semplice e verificabile.
4. Per Toro, correggere prima EMA200 4h/storia 1d/candele in formazione e allineamento prompt-motore; testare offline e su banco storico separato.
5. Stabilire una finestra PAPER e metriche predefinite: numero trade minimo, P&L, R medio, PF, drawdown, MAE/MFE, costi/funding e risultati per regime.
6. Approvazione utente separata prima di commit operativo, deploy o resume.

## Stato GitHub e test verificati

- PR #91: Draft/aperta, HEAD `500563a96db0e771f74a580b7278765eae0eaa92`, invariata; tre nuovi test non eseguiti.
- Commit analizzatore precedente: `7a6589f1dd09b6d59e97fbe0055af9b5caa69c9e`, 13 test sintetici dichiarati verdi.
- Nessun ramo/PR/commit trovato per Falco SHORT-only o Toro duale.
- Nessun test della nuova architettura, nessun risultato Cloud nuovo, nessuna prova VPS nuova.

## Stato PAPER consolidato invariato

| Portafoglio | Ultimo stato verificato | Roadmap |
|---|---|---|
| **Falco** | RC84 sotto pausa, heartbeat `draining`; conteggio corrente non noto | candidato SHORT-only reversibile, non applicato |
| **Toro** | RC84 sotto pausa, heartbeat `draining`; conteggio corrente non noto | candidato LONG+SHORT con nuova strategia, non applicato |
| **Brain** | runner `paused`, exit `healthy`; nessun ciclo completo post-RC84 provato | indipendente, invariato |

Restano validi: cutover PR #90 su `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`, sorgente installata `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`; PR #85–#91 Draft/non mergiate; tre pause; resume non autorizzato; relay Telegram post-cutover non verificato.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup VPS o restore off-host. PR #80 resta riferimento storico RC84. PAPER, EventJournal, learning, wallet, snapshot e rollback devono restare preservati.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito:** solo valutazione e documentazione della proposta.
- **Preparato:** architettura-obiettivo e prerequisiti sperimentali.
- **Rilasciato:** nulla.
- **Non approvato/non eseguito:** nessun filtro LONG, nuovo portafoglio, patch, merge, deploy, Action, modifica VPS, restart, resume, reset, ordine, LIVE o API a pagamento.

## Ripresa

La prossima AI deve:

1. leggere prima il rapporto V3 certificato quando disponibile;
2. non trasformare automaticamente la proposta in configurazione;
3. mantenere Falco/Toro/Brain in pausa fino ad autorizzazione separata;
4. se l'utente conferma, preparare una patch PAPER minima e reversibile per Falco SHORT-only, separata dalla nuova strategia LONG di Toro;
5. conservare la baseline attuale per un confronto A/B e non creare un quarto wallet senza nuova decisione esplicita.

**Limite di accesso:** consultati GitHub, Library e soltanto i messaggi recenti effettivamente recuperabili. Nessuna trascrizione integrale di chat eliminate e nessuna verifica live della VPS successiva ai riscontri documentati.
