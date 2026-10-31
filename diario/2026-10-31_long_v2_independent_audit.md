# 31/10/2026 — LONG Lab v2, audit indipendente della chat principale

L'utente ha caricato `SuperBot_Long_Lab_v2.zip` per il controllo finale. SHA256 verificato: `fa4d7d1ebbe6a547a7275fd4284a0f3c0b2f34ad04e1e3e62e7ad5deb7ce0ffd`. Manifesto 23/23 verificato. Suite offline Python 65/65 PASS. Le modifiche V2 a NO_TRADE, authority advisory e no bid/ask sintetici esistono e funzionano nei test inclusi.

**Audit indipendente:** sei riproduzioni aggiuntive hanno evidenziato:
1. `adapters/brain_adapter.py` converte un flag posizione non bool (anche `short_open='true'`) a `False` invece di rifiutare; così aggira la validazione introdotta nell'engine.
2. Di default `available_at_ms=close_ms` senza dato di disponibilità effettivamente osservata, anche con lag negativo.
3. `adapt_quote` accetta `price=Infinity` all'ingresso dell'adapter (il motore poi può respingerlo).
4. `verify_run` accetta un'alterazione equity intermedia realistica di +0.1 USD che non si riconcilia con il ledger.
5. `verify_run` accetta `max_drawdown=0.95` non verificato su replay che ha drawdown reale molto inferiore.
6. Il feed Brain reale `Feeds.history` fornisce normalmente 120 barre su TF lenti: il laboratorio richiede 200 e produce `NO_TRADE/DATA_UNAVAILABLE`; necessita backfill causale o indisponibilità esplicita.

Confermata la differenza con il ramo reale `work/brain-mtf-packaging-20261031` commit `a161907...`: MTF contiene un riassunto, non le 200 barre LONG necessarie; non è presente nessuna integrazione LONG operativa. Restano OOS economico, leva/liquidazioni, portafoglio LONG+SHORT e isolamento wallet.

**Verdetti:** BRAIN_ADVISORY: DA_CORREGGERE; HAWK_LONG_SHADOW: DA_CORREGGERE; BULL_LONG_SHADOW: DA_CORREGGERE; PAPER_ELIGIBLE: NO per tutti. Il LAB è valido come base offline, non approvato per integrazione o rilascio.

Preparato nell'audit un rapporto markdown, prompt V3 mirato e script dei sei casi avversariali; nessun merge, deploy, VPS, trading, wallet o logica SHORT toccati. I file di audit locali devono essere conservati dall'utente, poiché questo diario non contiene un allegato ZIP.

**Prossimo:** ottenere V3 con prove che i difetti V2 sono risolti; verificare di nuovo, poi eventualmente integrare in ramo isolato la sola osservazione LONG nel Brain. Nessuna approvazione implicita.
