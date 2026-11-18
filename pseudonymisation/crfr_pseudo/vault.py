"""Encrypted mapping between pseudonyms and original values (backlog E3.4).

* Pseudonyms are typed and numbered per session: ``<PERSONNE_1>``, ``<NIR_1>``. The same value gets
  the same pseudonym for the whole session, so a conversation stays coherent across turns.
* Originals are stored encrypted (AES-256-GCM); the lookup index is an HMAC of the normalised value,
  never the value itself. The session id is stored as an HMAC too.
* Every entry has a time to live, extended when used; expired entries are deleted and cannot be
  re-identified.
* The key comes from the environment at start-up (``CRFR_VAULT_KEY``, 32 bytes in base64). Without
  it, a random key lives in memory only: restarting the process forgets every mapping (local demo).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .checksums import compact

SCHEMA = """
CREATE TABLE IF NOT EXISTS pseudonyms (
  session TEXT NOT NULL, type TEXT NOT NULL, n INTEGER NOT NULL,
  lookup TEXT NOT NULL, nonce BLOB NOT NULL, ciphertext BLOB NOT NULL, expires REAL NOT NULL,
  PRIMARY KEY (session, type, n)
);
CREATE UNIQUE INDEX IF NOT EXISTS pseudonyms_lookup ON pseudonyms (session, lookup);
"""
COMPACT_TYPES = {"NIR", "IBAN", "CARTE", "SIRET", "SIREN", "NUMERO_FISCAL", "TELEPHONE"}


class VaultError(RuntimeError):
    pass


def key_from_env(variable: str = "CRFR_VAULT_KEY") -> bytes | None:
    raw = os.environ.get(variable)
    if not raw:
        return None
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise VaultError(f"{variable} must be 32 bytes in base64")
    return key


def normalise(kind: str, value: str) -> str:
    text = unicodedata.normalize("NFKC", value).strip()
    if kind in COMPACT_TYPES:
        text = compact(text).upper().replace("+33", "0").replace("0033", "0")
    return " ".join(text.casefold().split())


class Vault:
    def __init__(self, path: Path | str = ":memory:", key: bytes | None = None, ttl_s: float = 3600, clock=time.time):
        key = key or os.urandom(32)
        if len(key) != 32:
            raise VaultError("vault key must be 32 bytes")
        self._aead = AESGCM(key)
        self._mac_key = hmac.new(key, b"crfr-vault-index", hashlib.sha256).digest()
        self.ttl_s, self._clock = ttl_s, clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None, timeout=5)
        if str(path) != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def _mac(self, *parts: str) -> str:
        return hmac.new(self._mac_key, "\x1f".join(parts).encode(), hashlib.sha256).hexdigest()

    def pseudonym(self, session: str, kind: str, value: str) -> str:
        sid, now = self._mac("session", session), self._clock()
        lookup = self._mac("value", kind, normalise(kind, value))
        with self._lock:
            self._purge(now)
            row = self._db.execute(
                "SELECT n FROM pseudonyms WHERE session = ? AND lookup = ?", (sid, lookup)
            ).fetchone()
            if row:
                n = row[0]
                self._db.execute(
                    "UPDATE pseudonyms SET expires = ? WHERE session = ? AND lookup = ?",
                    (now + self.ttl_s, sid, lookup),
                )
            else:
                n = (
                    1
                    + self._db.execute(
                        "SELECT COALESCE(MAX(n), 0) FROM pseudonyms WHERE session = ? AND type = ?", (sid, kind)
                    ).fetchone()[0]
                )
                nonce = os.urandom(12)
                sealed = self._aead.encrypt(nonce, value.encode(), f"{sid}|{kind}|{n}".encode())
                self._db.execute(
                    "INSERT INTO pseudonyms VALUES (?,?,?,?,?,?,?)",
                    (sid, kind, n, lookup, nonce, sealed, now + self.ttl_s),
                )
        return f"<{kind}_{n}>"

    def original(self, session: str, kind: str, n: int) -> str | None:
        sid, now = self._mac("session", session), self._clock()
        with self._lock:
            self._purge(now)
            row = self._db.execute(
                "SELECT nonce, ciphertext FROM pseudonyms WHERE session = ? AND type = ? AND n = ?", (sid, kind, n)
            ).fetchone()
            if not row:
                return None
            self._db.execute(
                "UPDATE pseudonyms SET expires = ? WHERE session = ? AND type = ? AND n = ?",
                (now + self.ttl_s, sid, kind, n),
            )
        return self._aead.decrypt(row[0], row[1], f"{sid}|{kind}|{n}".encode()).decode()

    def _purge(self, now: float) -> None:
        self._db.execute("DELETE FROM pseudonyms WHERE expires <= ?", (now,))

    def raw_rows(self) -> list[tuple]:
        """For tests: everything stored, to prove that no original is kept in clear."""
        with self._lock:
            return list(self._db.execute("SELECT * FROM pseudonyms"))
