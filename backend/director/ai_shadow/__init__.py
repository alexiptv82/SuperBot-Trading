"""AI in ombra (DeepSeek): un trader virtuale che legge i grafici e decide, in un conto finto tutto suo.

Processo SEPARATO dai bot: dati di mercato pubblici (nessuna chiave di trading), nessun ordine vero, nessun accesso ai
dati dei bot. La chiave del modello arriva solo dall'ambiente del container e non viene mai scritta da nessuna parte.
Solo libreria standard di Python (piu' `desk.engine`, anch'esso senza dipendenze).
"""
SCHEMA = 1
VERSION = "ai-shadow-1.0"
