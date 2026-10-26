"""Read-only recent closed-position bias, using native close_ms/side/net schema.

No profit predictions. Defaults (3 positions, >=2/3 losing, aggregate net <0,
multiplier 0.5) are explicit research choices, pending replay and review.
Partial closes of one position are aggregated, not counted as independent bets.
"""
from __future__ import annotations

import json
import math
import os
import time


class EpisodeMemory:
    def __init__(self, *, clock=time.time, min_positions=3, loss_modifier=0.5,
                 max_bytes=64 * 1024 * 1024, max_line_bytes=65536):
        if min_positions < 1 or not 0 <= loss_modifier <= 1 or max_bytes < 1 or max_line_bytes < 1:
            raise ValueError("invalid memory settings")
        self.clock, self.min_positions = clock, min_positions
        self.loss_modifier = float(loss_modifier)
        self.max_bytes, self.max_line_bytes = max_bytes, max_line_bytes

    @staticmethod
    def _neutral():
        return {"long_modifier": 1.0, "short_modifier": 1.0,
                "long_positions": 0, "short_positions": 0, "valid": False}

    def get_bias(self, trade_history_path, hours=3):
        """Missing/unreadable/oversized file -> neutral, malformed records skipped.

        Snapshot the file size to avoid following concurrent appends; ignore an
        unterminated last line. No writes, filesystem cache or file creation.
        Timestamps are milliseconds since epoch, including UTC window endpoints.
        """
        neutral = self._neutral()
        try:
            now = float(self.clock()) * 1000
            hours = float(hours)
            if not math.isfinite(now) or not math.isfinite(hours) or hours <= 0:
                return neutral
            cutoff = now - hours * 3_600_000
            groups, seen = {}, set()
            with open(trade_history_path, "rb") as stream:
                remaining = os.fstat(stream.fileno()).st_size
                if remaining > self.max_bytes:
                    return neutral
                while remaining:
                    line = stream.readline(min(remaining, self.max_line_bytes + 1))
                    if not line:
                        return neutral  # truncated concurrently
                    remaining -= len(line)
                    if len(line) > self.max_line_bytes:
                        return neutral
                    if not line.endswith(b"\n"):
                        break
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            continue
                        stamp, net = float(row["close_ms"]), float(row["net"])
                        if not math.isfinite(stamp) or not math.isfinite(net) or not cutoff <= stamp <= now:
                            continue
                        side = row["side"]
                        if isinstance(side, bool) or side not in (1, -1, "long", "short", "LONG", "SHORT"):
                            continue
                        direction = "long" if side in (1, "long", "LONG") else "short"
                        # Stable capital event ID when available; otherwise exact record.
                        event = str(row.get("capital_event_id") or json.dumps(row, sort_keys=True))
                        if event in seen:
                            continue
                        seen.add(event)
                        # Full position identity avoids mixing runs or account IDs.
                        if row.get("id") is None or row.get("open_ms") is None or not row.get("symbol"):
                            continue
                        key = (str(row.get("account", "")), str(row.get("run_no", "")),
                               str(row["symbol"]), str(row["id"]), str(row["open_ms"]), direction)
                        groups[key] = groups.get(key, 0.0) + net
                    except (ValueError, TypeError, KeyError, UnicodeError):
                        continue
            result = self._neutral()
            result["valid"] = True
            for direction in ("long", "short"):
                values = [net for key, net in groups.items() if key[-1] == direction]
                result[direction + "_positions"] = len(values)
                if (len(values) >= self.min_positions and sum(values) < 0
                        and sum(v < 0 for v in values) / len(values) >= 2 / 3):
                    result[direction + "_modifier"] = self.loss_modifier
            return result
        except Exception:
            return neutral
