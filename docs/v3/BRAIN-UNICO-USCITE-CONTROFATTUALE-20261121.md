# Brain Unico: confronto controfattuale delle uscite (preregistrazione, 21/11/2026)

**Natura:** preparazione. Nessuna analisi è stata eseguita su dati reali e il runtime non cambia (`exit_policy.json` invariato). L'analisi si farà **dopo la preparazione della RC**, solo su dati attestati (Fase A approvata).

**Preregistrazione:** `ops/brain-unico/exits/preregistration.json`, SHA-256 `acfb5f9f958aaf7ebe8f14f92cedf6739345cee44fa686c346c1eba247f74650`. Una modifica richiede una nuova versione datata, mai una correzione silenziosa.

## Bracci (stesse entrate, stesse candele 1m, stessi costi)
| Famiglia | Bracci registrati | Idea |
|---|---|---|
| Riferimento | A0: stop, take-profit 2R, 24 h (= `exits.py`) | regola attuale |
| Pareggio | BE_075, BE_100: stop all'ingresso + costi dopo 0,75 R / 1 R | non trasformare un vincente in perdente |
| Trailing | TR_100_075, TR_100_100 (con TP 2R); TR_100_100_senza_tp | seguire il prezzo dopo 1 R |
| Protezione dei profitti | PR_100_033, PR_100_050: blocca il 33 % / 50 % dell'escursione favorevole dopo 1 R | ridurre la restituzione |
| Inversione | INV_EMA20_1H: uscita alla chiusura oraria oltre l'EMA 20 a 1 h | approssimazione dell'inversione della tesi |

## Regole fissate in anticipo
- **Dati:**
  - solo posizioni Brain V3 e Arena con input e candele **attestati**;
  - esclusi Falco e Toro (non certificati), i dati non attestati e le fonti esterne.
- **Divisione del campione:**
  - per giorno UTC: 60 % calibrazione, 1 giorno di embargo (≥ 24 h di durata massima), 40 % test;
  - **un** parametro per famiglia, scelto solo sulla calibrazione;
  - il test non influenza la scelta.
- **Criterio di superiorità:** differenza appaiata (stesso trade) rispetto ad A0, con bootstrap a blocchi per giorno, 10.000 campioni, seme fisso e correzione di Holm sulle 4 famiglie. "Superiore" **solo se**:
  - il limite inferiore dell'intervallo è > 0;
  - il drawdown in R non peggiora oltre il 10 %;
  - ci sono almeno 100 trade e 20 giorni nel test;
  - la conclusione vale in **tutti** gli scenari di funding (tassi attestati se disponibili; 0; +0,01 %; +0,03 % per scadenza) e con lo stesso braccio scelto.

  In ogni altro caso l'esito è "non dimostrato" o "campione insufficiente".
- **Costi uguali per tutti:**
  - commissione 6 bp per lato;
  - slippage 2 bp sulle uscite a stop e su quelle a mercato;
  - take-profit al prezzo esatto.
- **Nessuno sguardo avanti:** break-even, trailing e protezione si aggiornano a candela chiusa e valgono dalla successiva. Se stop e take-profit cadono nella stessa candela, vince lo stop, come nel runtime.
- **Esito:** solo una proposta al proprietario.

## Verifiche dello strumento (`backend/tests/test_v3_exit_lab.py`, 15 test, nella suite del gate)
- **Riferimento:** A0 riproduce `evaluate_exit` del runtime su 300 percorsi casuali e nel caso di stop e target nella stessa candela.
- **Assenza di sguardo avanti** nel trailing.
- **Regole dei bracci:** pareggio con costi, protezione dei profitti, inversione solo con storia nota, funding a scadenza.
- **Costi:** identici per tutti i bracci.
- **Regole statistiche:**
  - rifiuto dei dati non attestati;
  - campione insufficiente;
  - un effetto vero viene trovato;
  - un effetto visto solo in calibrazione viene smentito fuori campione;
  - embargo;
  - accordo richiesto tra gli scenari di funding.
- **Mutazioni:** invertendo la priorità tra stop e target, o introducendo lo sguardo avanti, i test falliscono.

## Limiti dichiarati
- **Effetti di secondo ordine:** la valutazione è per trade in R. Uscite diverse avrebbero liberato il simbolo per entrate non osservate, e questo effetto non è stimato.
- **Inversione della tesi:** il runner oggi non consulta il modello sui simboli con posizione aperta, quindi INV è una regola deterministica, non la tesi del modello. Se INV mostra valore, una vera uscita su tesi richiede un esperimento separato.
- **Ordine nella candela:** dentro la candela da 1 minuto l'ordine dei prezzi è ignoto.

## Che cosa serve per eseguire l'analisi (dopo la RC)
- Posizioni aperte e chiuse dal journal Brain V3 e Arena, con input attestati tramite le ancore.
- Candele da 1 minuto **attestate** per ogni posizione, più la storia a 1 h per l'EMA. Serve l'ancora dell'archivio delle candele, registrata dal proprietario.
- Tassi di funding attestati, se disponibili. Altrimenti valgono solo gli scenari dichiarati.
