# Risultati del replay (18/11/2026)

* `structural.json`: esperimento preregistrato (`python -m research.brain_guardian.experiment structural --bars <dir> --seeds 5 --out structural.json`).
* `sizing_check.json`: controllo del dimensionamento aggiunto DOPO la preregistrazione (`python -m research.brain_guardian.sizing_check <dir> sizing_check.json`).
* `candles_SHA256SUMS.txt`: impronte dei CSV Bitget 1m usati (01/10/2026 00:00 UTC - 18/11/2026, 69.549 minuti per simbolo,
  scaricati con `backend/v3/lab_tools/fetch_candles.fetch_rows`). I CSV non sono nel repository: si riscaricano e si confrontano le impronte.
