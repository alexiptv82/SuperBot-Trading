# Toro–Brain: audit delle classificazioni offline (15 novembre 2026)

**Stato:** candidato su ramo isolato, NON installato e NON autorizzato a modificare il trading.
**Base:** `e9aa92fdbfcaa9b28450205ad03fd42c8dd53d2a` (Fable, confronto v1).

## Perche' esiste
Il confronto v1 confondeva decisioni diverse: chiamava NO_TRADE un rifiuto del motore senza proposta conservata; poteva chiamare "proposta respinta" una proposta per cui non esisteva alcuna decisione nello stesso ciclo; e privilegiava LONG se nella finestra di 24h erano aperte posizioni di entrambi i lati.

## Modifiche al solo laboratorio
- `cross_compare_v2`: join su **timestamp e simbolo** tra proposta osservata e decisione presente nel journal; senza decisione corrispondente il motivo rimane **ignoto**.
- Distingue `NO_TRADE` del modello (`DRAFT`), `RESPINTO_LATO_IGNOTO`, `PROPOSTA_ESITO_IGNOTO`, `APPROVATO_NON_ESEGUITO`, `MISTO_aperto`, e rifiuti con lato noto.
- Per le ipotesi statistiche conta soltanto gli esiti Toro **eseguito_virtuale** e **chiusa** con `R` finito; non promuove proposte, posizioni aperte o slot rifiutati a osservazioni di performance.
- Non modifica H3, capitale, leva, stop, risk gate, aperture, uscite o policy; nessuna esecuzione di trading.
- Test sintetici aggiornati e nuovi scenari aggiunti: rifiuto senza osservatore, approvazione senza fill, proposta non collegata, finestra con aperture LONG+SHORT, esclusione delle operazioni Toro non chiuse.

## Limiti ancora presenti
- Il journal Brain non salva il **motivo tecnico specifico** del rifiuto del RiskQuote: `risk_rejected` e' generico. Il file opzionale delle proposte conserva il lato, non la causa del rifiuto. Una patch runtime distinta e un nuovo collaudo sarebbero necessari.
- La correlazione `(timestamp, symbol)` e' osservazionale, non un identificatore univoco della richiesta; collisioni o log mancanti restano possibili. Se l'osservatorio non e' installato, LONG e SHORT rifiutati non possono essere ricostruiti retroattivamente.
- Il confronto valuta gli esiti di Toro **condizionati** alla vista di Brain, non l'abilita' statistica di Brain contro un baseline causale nello stesso istante.
- L'ultima versione non e' stata eseguita in GitHub Actions: evitare consumo di minuti senza approvazione. I test aggiunti sono da eseguire localmente prima dell'uso.
- I dati del journal effettivo della VPS Singapore non sono accessibili dal connettore GitHub. Serve audit in sola lettura eseguito sul server per validare le metriche reali.

## Prossimo gate
1. Eseguire audit VPS read-only firmato da commit `907803c8689b9f5f5afbfc453854fdf5c068ba43` e confrontare eventuali anomalie del journal.
2. Eseguire offline `pytest -q research/long_lab_fable/test_cross_compare.py` sul ramo di questa patch.
3. Solo dopo una conferma sull'evidenza real-world, valutare con l'utente se installare osservatorio Brain e correzione web Chiudi Trade; mai fare deploy impliciti.
4. Non cambiare il funding contabilizzato, parametri di rischio o strategie senza scelta esplicita dell'operatore.

**PAPER-only · nessun merge/deploy · nessun GitHub Actions avviato da questa revisione.**
