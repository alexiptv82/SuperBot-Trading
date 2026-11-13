# Checkpoint verificabile — PR #96 Step0 NO-GO; Step0′ funding solo proposto

**Data:** 13/11/2026 18:44 Europe/Rome  
**Ambito:** sola documentazione; esclusivamente PAPER; storici ed EventJournal da preservare.

## Esito verificato del Passo 0 Toro BB100 V1

Il resume detached ha completato il replay su **cinque mercati Bitget, 365 giorni, barre 1H/4H**, con uscite fisse 4/8/12 ore e costo stress uniforme dello 0,10% del nozionale. Output finale documentato: `DATA_READY_FOR_HUMAN_REVIEW evaluated=5 approved=0` e report JSON presente.

Il risultato strategico è **NO-GO**: non collegare Toro V1 al runner e non riattivarlo con questa logica. I 19/19 test tecnici restano PASS ma certificano il codice isolato, non redditività.

### Risultati riportati

| Simbolo | 4h n / avg net | 8h n / avg net | 12h n / avg net |
|---|---:|---:|---:|
| BTC | 66 / −0,2039% | 54 / −0,3184% | 46 / −0,3341% |
| ETH | 65 / −0,1475% | 51 / −0,0946% | 43 / −0,1713% |
| SOL | 67 / **segno da verificare** | 54 / +0,0205% | 50 / +0,1867% |
| BNB | 68 / −0,1159% | 54 / −0,1323% | 47 / −0,2659% |
| XRP | 73 / −0,1589% | 63 / −0,3123% | 52 / −0,1338% |
| Totale riportato | 339 / −0,1305% | 276 / −0,1729% | 238 / −0,1380% |

**Anomalia SOL 4h:** il log cronologico riporta `avg_net=0.000257`, cioè **+0,0257%**, mentre la tabella manuale finale riporta −0,0257%. La fonte primaria `step0_SOLUSDT_result.json` non è stata letta direttamente in questo checkpoint. Se il segno corretto è positivo, la media pesata 4h è circa −0,1204%, quindi il verdetto NO-GO non cambia. Le medie lorde aggregate riportate restano negative anche riaggiungendo i 10 bps: circa −0,0305%/−0,0729%/−0,0380% secondo la tabella, con la stessa riserva sul segno SOL 4h.

SOL 12h, pur positivo, ha 50 trade e percentile random 0,912, sotto la soglia 0,95: selezionarlo dopo aver visto il test sarebbe data snooping. Il replay non prova fill post-only, stop, Profit Guardian, leva, slippage/funding effettivo o correlazioni di portafoglio.

## PR, rami e test

- [PR #96](https://github.com/alexiptv82/SuperBot-Trading/pull/96): aperta, Draft, non mergiata, research-only.
- Ramo `work/toro-profit-hunter-v1-20261113`; base `0e29a73a36f668643da4088178bacb8616a45ac0`; HEAD `0a4574de847ee518b5d480f8e3f50a5ae139e317`; 27 commit, 9 file.
- Resume: `f89487c2f66993c3a4619042e44882182ad72ea3`; launcher detached: `0a4574de847ee518b5d480f8e3f50a5ae139e317`.
- Test core: 19/19 PASS con stage invariato, ma Step0 strategico NO-GO.
- Nessun merge, deploy, GitHub Actions o modifica operativa derivata dal report.

## Rapporto Claude e nuova ipotesi

È stato ricevuto e analizzato in sola lettura il rapporto completo di 270 righe. Conferma il NO-GO BB100 V1 e propone **una sola ipotesi indipendente**, non ancora provata: funding negativo estremo settled + recupero del prezzo.

Specificazione proposta:
- funding <=10° percentile rolling 90 giorni;
- minimo prezzo 7 giorni nelle 24 ore precedenti e conferma 1H entro 12 ore;
- veto ATR >95° percentile 30 giorni e dump BTC;
- un evento per simbolo;
- uscita 8/24h, con 24h primaria e funding regolato;
- tre benchmark random/ablation, incluso lo stesso innesco senza condizione funding;
- bootstrap a blocchi di giorni e salvataggio dei singoli trade;
- cinque simboli hold-out e successiva ombra Bitget di otto settimane.

Sei gate GO proposti, tutti obbligatori: almeno 150 trade e 60 giorni-evento; lordo medio 24h con funding >=25 bp e limite inferiore IC95% >10 bp; positivo separatamente in validazione e test; sopra il 95° percentile di tutti i tre benchmark; nessun mese >30% del profitto e risultato positivo senza il 5% dei migliori trade; positivo sui cinque simboli hold-out.

**Stato decisionale:** il rapporto è una proposta. Nessuna autorizzazione esplicita accessibile al Passo 0′, all'uso di dati proxy o alla modifica del rischio. Non avviare test o cambiare configurazioni finché non esiste consenso verificato.

## Gate dati e rischio

- API Bitget funding ufficiale: ultimi 90 giorni; non basta per il disegno 2020–2026.
- Binance è proposto soltanto come proxy: richiede provenienza/hash, timestamp settlement senza lookahead, gestione variazioni intervallo e distinzione esplicita dalla validazione Bitget.
- Il rischio aperto candidato 40 è incoerente con daily loss 30; anche 32 può superarlo con due stop. Il rapporto suggerisce riduzione, ma nessun valore è approvato o implementato.
- Prima di modificare il rischio servono decisione utente e vincolo coerente tra perdita realizzata, worst-case open risk e buffer esecuzione.

## Tre portafogli PAPER

- **Brain:** unpause guarded già verificato, runner attivo ed exit healthy nell'ultimo controllo disponibile; nessuna nuova prova del primo ciclo completo sugli otto simboli, aperture/chiusure o PnL.
- **Falco:** SHORT originale congelato; non riattivato. Prima di avvio separato serve gate SHORT_ONLY sulla baseline VPS.
- **Toro:** BB100 V1 bocciato e sospeso; nuova ipotesi funding solo proposta. Nessuna integrazione o riattivazione.

## Backup, chiavi e storico

- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup/restore VPS.
- `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- RC84 PR #80 resta riferimento storico.
- Solo PAPER; storici ed EventJournal devono restare integri.
- Nessun segreto, token, passphrase, chiave privata o dettaglio utile all'accesso VPS registrato.

## Prossimi passi / ripresa

1. Chiudere la discrepanza SOL 4h leggendo il valore puntuale dal JSON originale; il NO-GO non dipende da tale correzione.
2. Non integrare né riavviare Toro BB100 V1; mantenere PR #96 Draft/research.
3. Prima di qualsiasi Step0′ ottenere autorizzazione esplicita, fissare cinque simboli, 24h primaria/8h riportata, tre benchmark inclusa ablation senza funding, fonti dati e sei soglie GO.
4. Se il test preregistrato fallisce, fermare questa linea LONG rules-only senza retuning sullo stesso dataset; non generalizzare a tutti i LONG possibili.
5. Non cambiare rischi, non avviare Falco/Toro e non toccare Brain senza mandato separato.
