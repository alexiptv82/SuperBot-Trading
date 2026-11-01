# LONG Shadow — public WS stream reader (staging only, 2026-11-01)

Read-only incremental observation added to Draft PR #26, no bot/VPS deploy, no exchange trading endpoints.

**Components:** `backend/long_shadow_stream.py` validates original websocket envelopes, SHA256, session order and 1m/15m/1H/4H snapshot OHLCV; only a `snapshot` physically received after close can enter an analysis bar. Every `kline update` is explicitly classified `UNCONFIRMED_KLINE_UPDATE` and is NEVER treated as an official close. `backend/long_shadow_stream_runner.py` watches growing rotated `ws_raw_frames_*.jsonl` files from a separate public-data recorder, with newline buffering, no write to wallets, no market/broker connection, status-only JSON to stdout.

**Reproducible local tests:** 16/16 PASS (10 stream classification + 6 append/rotation tests). Uses standard library. Source capture file `SuperBot_LONG_LIVE_MTF_RESULT_20261101T161618Z.zip` SHA256 `33eb490e34d7dbfbb208827d3f85edc48f327a3619ca2e33f3a5dfb5d5a84cb2` was independently replayed through stream validator.

| Classified raw WS event | Count |
| --- | ---: |
| Total raw messages | **43,498** |
| Closed snapshots received | 8 |
| books1 quote updates | 40,778 |
| **UNCONFIRMED** kline updates | **2,673** |
| text-pong heartbeat | 29 |
| connection/control messages | 10 |

Important: 8 snapshot payloads were received live and contain 499 historically completed bars per symbol/timeframe; the historical completed bars became AVAILABLE ONLY at the observed snapshot receipt, NOT at historical close. This does not demonstrate a live final-close ack on 1H/4H. The stream reader intentionally does NOT execute LONG V6.1.1 or connect to actual wallet data, so every status has `orders_created=0` and `paper_eligible=false`. The frozen engine and `long_shadow_offline_probe.py` are separate.

**Usage once a separate public research collector is running:** `PYTHONPATH=backend python backend/long_shadow_stream_runner.py --input-dir /path/to/capture --duration-seconds 60` (0 for continuous until explicitly stopped). Watcher does NOT start the collector itself. Do NOT start on VPS production or point it to wallet data. No live service was launched.

**Draft PR:** https://github.com/alexiptv82/SuperBot-Trading/pull/26; CI backend green, React test green on follow-up run, frontend build pending at time of writing. No merge/deploy approval. LONG PAPER_ELIGIBLE=NO, execution/economic evidence not established.