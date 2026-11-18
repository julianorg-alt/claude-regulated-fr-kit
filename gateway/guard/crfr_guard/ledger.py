"""Usage ledger and kill switches, in SQLite.

One row per completed request: who (user, team, application), which model, how many tokens, what
cost. No prompt, no answer, no client address. Quotas and budgets are sums over the current UTC day
and UTC month. Kill switches live in the same file so that the admin command and every guard
replica see the same state on the next request.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .usage import Usage

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
  ts REAL NOT NULL, day TEXT NOT NULL, month TEXT NOT NULL,
  user TEXT NOT NULL, team TEXT, app TEXT NOT NULL, model TEXT NOT NULL,
  input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
  cache_read_input_tokens INTEGER NOT NULL, cache_creation_input_tokens INTEGER NOT NULL,
  cost REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_user ON usage (user, day, month);
CREATE INDEX IF NOT EXISTS usage_team ON usage (team, day, month);
CREATE INDEX IF NOT EXISTS usage_app ON usage (app, day, month);
CREATE TABLE IF NOT EXISTS switches (
  scope TEXT NOT NULL, key TEXT NOT NULL, reason TEXT NOT NULL, ts REAL NOT NULL,
  PRIMARY KEY (scope, key)
);
"""
SWITCH_SCOPES = ("global", "user", "team", "app")


def periods(now: float) -> tuple[str, str]:
    moment = datetime.fromtimestamp(now, UTC)
    return moment.strftime("%Y-%m-%d"), moment.strftime("%Y-%m")


class Ledger:
    def __init__(self, path: Path | str, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=5)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def charge(self, keys: dict[str, str], model: str, usage: Usage, cost: float) -> None:
        now = self._clock()
        day, month = periods(now)
        with self._lock:
            self._db.execute(
                "INSERT INTO usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    now, day, month, keys["user"], keys.get("team"), keys["app"], model,
                    usage.input_tokens, usage.output_tokens,
                    usage.cache_read_input_tokens, usage.cache_creation_input_tokens, cost,
                ),
            )  # fmt: skip

    def tokens_today(self, scope: str, key: str) -> int:
        day, _ = periods(self._clock())
        return int(self._sum(scope, key, "input_tokens + output_tokens + cache_read_input_tokens"
                             " + cache_creation_input_tokens", "day", day))  # fmt: skip

    def cost_this_month(self, scope: str, key: str) -> float:
        _, month = periods(self._clock())
        return float(self._sum(scope, key, "cost", "month", month))

    def _sum(self, scope: str, key: str, expression: str, period: str, value: str) -> float:
        if scope not in ("user", "team", "app"):
            raise ValueError(scope)
        # scope, expression and period come from constants above, never from the request.
        query = f"SELECT COALESCE(SUM({expression}), 0) FROM usage WHERE {scope} = ? AND {period} = ?"  # noqa: S608
        with self._lock:
            return self._db.execute(query, (key, value)).fetchone()[0]

    # Kill switches (E2.6) --------------------------------------------------------------------
    def set_switch(self, scope: str, key: str, reason: str) -> None:
        if scope not in SWITCH_SCOPES:
            raise ValueError(f"unknown scope {scope!r}")
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO switches VALUES (?,?,?,?)", (scope, key if scope != "global" else "*",
                                                                     reason, self._clock())
            )  # fmt: skip

    def clear_switch(self, scope: str, key: str) -> bool:
        with self._lock:
            cursor = self._db.execute(
                "DELETE FROM switches WHERE scope = ? AND key = ?", (scope, key if scope != "global" else "*")
            )
        return cursor.rowcount > 0

    def active_switch(self, keys: dict[str, str]) -> tuple[str, str, str] | None:
        """Return (scope, key, reason) of the first switch that applies, global first."""
        candidates = [("global", "*")] + [(scope, key) for scope, key in keys.items()]
        with self._lock:
            for scope, key in candidates:
                row = self._db.execute(
                    "SELECT reason FROM switches WHERE scope = ? AND key = ?", (scope, key)
                ).fetchone()
                if row:
                    return scope, key, row[0]
        return None

    def switches(self) -> list[tuple[str, str, str, float]]:
        with self._lock:
            return list(self._db.execute("SELECT scope, key, reason, ts FROM switches ORDER BY scope, key"))
