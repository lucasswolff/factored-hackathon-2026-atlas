"""Local, ignored mock-application store. No source-bank tables are modified."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .data_access import ROOT
from .policy import CARDS, OFFER_VERSION


class ApplicationStorageError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ApplicationStore:
    def __init__(self, path: Path = ROOT / "advisor/.local/mock_applications.sqlite"):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS mock_applications (
                application_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                confirmation_token TEXT NOT NULL UNIQUE,
                customer_alias TEXT NOT NULL,
                country TEXT NOT NULL,
                card TEXT NOT NULL,
                offer_version TEXT NOT NULL,
                campaign_id TEXT,
                precheck_status TEXT,
                precheck_reasons TEXT,
                precheck_policy_version TEXT,
                precheck_consent_at TEXT,
                confirmed_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status = 'PENDING_REVIEW'),
                UNIQUE (conversation_id, card)
            )""")
            # Existing local demo databases predate the reviewer queue.
            if "precheck_reasons" not in {row[1] for row in db.execute("PRAGMA table_info(mock_applications)")}:
                db.execute("ALTER TABLE mock_applications ADD COLUMN precheck_reasons TEXT")
            db.execute("""CREATE TABLE IF NOT EXISTS mock_handoffs (
                handoff_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                customer_alias TEXT NOT NULL,
                country TEXT NOT NULL,
                language TEXT NOT NULL,
                card TEXT,
                reason TEXT NOT NULL CHECK (reason = 'CUSTOMER_REQUEST'),
                offer_version TEXT NOT NULL,
                packet TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status = 'PENDING_REVIEW'),
                UNIQUE (conversation_id, reason)
            )""")
            if "packet" not in {row[1] for row in db.execute("PRAGMA table_info(mock_handoffs)")}:
                db.execute("ALTER TABLE mock_handoffs ADD COLUMN packet TEXT")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        os.chmod(self.path, 0o600)
        db.row_factory = sqlite3.Row
        return db

    def read(self, conversation_id: str, card: str) -> dict | None:
        try:
            with self._connect() as db:
                row = db.execute("SELECT * FROM mock_applications WHERE conversation_id = ? AND card = ?",
                                 (conversation_id, card)).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStorageError("Application record could not be read") from exc
        return dict(row) if row else None

    def create_and_verify(self, draft: dict, confirmed_at: str) -> dict:
        """One record per conversation/card, with a separate committed read-back."""
        if draft.get("card") not in CARDS or draft.get("offer_version") != OFFER_VERSION:
            raise ValueError("Unknown card or offer version")
        application_id = "APP-" + secrets.token_hex(6).upper()
        try:
            with self._connect() as db:
                db.execute("""INSERT OR IGNORE INTO mock_applications
                    (application_id, conversation_id, confirmation_token, customer_alias,
                     country, card, offer_version, campaign_id, precheck_status, precheck_reasons,
                     precheck_policy_version, precheck_consent_at, confirmed_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_REVIEW')""",
                    (application_id, draft["conversation_id"], draft["confirmation_token"],
                     draft["customer_alias"], draft["country"], draft["card"],
                     draft["offer_version"], draft["campaign_id"], draft["precheck_status"],
                     json.dumps(draft["precheck_reasons"]) if draft["precheck_reasons"] is not None else None,
                     draft["precheck_policy_version"], draft["precheck_consent_at"], confirmed_at))
        except (sqlite3.Error, KeyError) as exc:
            raise ApplicationStorageError("Application record could not be written") from exc
        record = self.read(draft["conversation_id"], draft["card"])
        if record is None or any(record[key] != draft[key] for key in (
                "conversation_id", "confirmation_token", "customer_alias", "country", "card",
                "offer_version", "campaign_id", "precheck_status", "precheck_policy_version",
                "precheck_consent_at")) or record["status"] != "PENDING_REVIEW":
            raise ApplicationStorageError("Application record did not pass read-back verification")
        if record["precheck_reasons"] != (json.dumps(draft["precheck_reasons"]) if draft["precheck_reasons"] is not None else None):
            raise ApplicationStorageError("Application reasons did not pass read-back verification")
        return record

    def read_handoff(self, conversation_id: str, reason: str) -> dict | None:
        try:
            with self._connect() as db:
                row = db.execute("SELECT * FROM mock_handoffs WHERE conversation_id = ? AND reason = ?",
                                 (conversation_id, reason)).fetchone()
        except sqlite3.Error as exc:
            raise ApplicationStorageError("Handoff record could not be read") from exc
        return dict(row) if row else None

    def create_handoff_and_verify(self, draft: dict, created_at: str) -> dict:
        if (draft.get("reason") != "CUSTOMER_REQUEST" or draft.get("offer_version") != OFFER_VERSION or
            draft.get("card") not in (*CARDS, None) or draft.get("language") not in {"es", "pt"}):
            raise ValueError("Invalid local handoff request")
        handoff_id = "HND-" + secrets.token_hex(6).upper()
        try:
            with self._connect() as db:
                db.execute("""INSERT OR IGNORE INTO mock_handoffs
                    (handoff_id, conversation_id, customer_alias, country, language,
                     card, reason, offer_version, packet, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_REVIEW')""",
                    (handoff_id, draft["conversation_id"], draft["customer_alias"],
                    draft["country"], draft["language"], draft["card"],
                    draft["reason"], draft["offer_version"], json.dumps(draft["packet"]), created_at))
        except (sqlite3.Error, KeyError) as exc:
            raise ApplicationStorageError("Handoff record could not be written") from exc
        record = self.read_handoff(draft["conversation_id"], draft["reason"])
        if record is None or any(record[key] != draft[key] for key in (
                "conversation_id", "customer_alias", "country", "language", "card",
                "reason", "offer_version")) or record["status"] != "PENDING_REVIEW" or \
                record["packet"] != json.dumps(draft["packet"]):
            raise ApplicationStorageError("Handoff record did not pass read-back verification")
        return record

    def review_queue(self) -> dict[str, list[dict]]:
        """Local demo reviewer view; return aliases and action metadata only."""
        try:
            with self._connect() as db:
                applications = [dict(row) for row in db.execute("""SELECT application_id, customer_alias,
                    country, card, campaign_id, precheck_status, precheck_reasons,
                    precheck_policy_version,
                    confirmed_at, status FROM mock_applications ORDER BY confirmed_at DESC""")]
                handoffs = [dict(row) for row in db.execute("""SELECT handoff_id, customer_alias,
                    country, language, card, reason, packet, created_at, status
                    FROM mock_handoffs ORDER BY created_at DESC""")]
        except sqlite3.Error as exc:
            raise ApplicationStorageError("Review queue could not be read") from exc
        for application in applications:
            try:
                application["precheck_reasons"] = (json.loads(application["precheck_reasons"])
                                                   if application["precheck_reasons"] else [])
            except json.JSONDecodeError as exc:
                raise ApplicationStorageError("Application reasons could not be read") from exc
        for handoff in handoffs:
            try:
                handoff["packet"] = json.loads(handoff["packet"]) if handoff["packet"] else None
            except json.JSONDecodeError as exc:
                raise ApplicationStorageError("Handoff packet could not be read") from exc
        return {"applications": applications, "handoffs": handoffs}
