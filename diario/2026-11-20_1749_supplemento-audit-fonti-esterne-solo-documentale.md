# Supplemento verificabile SuperBot-Trading — 20/11/2026 17:49 Europe/Rome

Questo supplemento completa il checkpoint delle 17:46 senza sostituirlo.

## Nuova HEAD verificata

- `integration/brain-unico-20261119` è avanzato da `f9009aee2432a31e6304032ffb000fe5eba88243` a `bead82a349e71868d112e1e5eb513f8e666b1e14`.
- Il nuovo commit è **solo documentale**: audit esplorativo in sola lettura di quattro fonti pubbliche sul trading AI.
- Nessun dataset è stato importato, nessun codice di terzi eseguito, nessuna API a pagamento usata e nessuna modifica è stata apportata a runtime, strategie, parametri o training.

## Risultato dell'audit

- Nessuna delle quattro fonti valutate offre trade crypto perpetual per singola operazione con contesto decisionale e provenienza attestabile, quindi **nessuna è idonea come sorgente dati per Brain Unico**.
- Il loro possibile valore è soltanto metodologico: cattura del profitto, leva rispetto alla volatilità, coerenza delle decisioni, dominanza dei campi del prompt e controllo deterministico delle affermazioni del modello.
- Qualunque analisi controfattuale sui nostri journal attestati resta una proposta in attesa di approvazione; nessuna promozione automatica a training o runtime.
- Falco/Toro restano conservati ma `semantic_not_certified` ed esclusi dal training come stabilito nel checkpoint delle 17:46.

## Stato invariato

- Candidato extbackup `f60b90d64521cd8834f6f99d85d7fe04f8187d99`; integrità tecnica Brain/Arena verificata, semantica Falco/Toro non certificata.
- RC84 PR #80 open/draft; Issue #124 open/P0; extbackup storico `3dc2116a08058f57fc14b695431f6e3fa1a1ca45` non installato/certificato.
- Verifica PC della chiave age `ESITO: VERIFICA OK` e chiave pubblica coincidente: prova locale, non certificazione VPS.
- Nessun merge, deploy, modifica VPS, riavvio, reset, ordine, training, LIVE o API a pagamento da questo checkpoint.

## Ripresa

Usare `bead82a349e71868d112e1e5eb513f8e666b1e14` come HEAD dell'integrazione; trattare l'audit esterno come documentazione/proposta, non come dati acquisiti né funzionalità approvata.
