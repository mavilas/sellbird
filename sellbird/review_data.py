"""Private project evidence, imported separately from contact and sending data."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from contextlib import closing, contextmanager
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Firm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=200)
    source_url: str = Field(max_length=2048)
    retrieved_on: date
    published_on: date | None = None
    evidence: str = Field(min_length=1, max_length=1500)
    fit_reason: str = Field(min_length=1, max_length=1500)
    sheets_evidence: str = Field(min_length=1, max_length=1000)
    priority: Literal["P0", "P1", "P2"]
    buyer_role: str = Field(min_length=1, max_length=200)
    validation_needed: str = Field(min_length=1, max_length=1500)
    extra_sources: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
        ):
            raise ValueError("source requires credential-free HTTPS without a query")
        return value

    @field_validator("extra_sources")
    @classmethod
    def safe_extra_sources(cls, values):
        return [cls.safe_source(value) for value in values]

    @model_validator(mode="after")
    def source_date_order(self):
        if self.published_on and self.published_on > self.retrieved_on:
            raise ValueError("source date is after retrieval")
        return self


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    product: str = Field(min_length=1, max_length=2000)
    offer: str = Field(min_length=1, max_length=2000)
    firms: list[Firm] = Field(min_length=1, max_length=500)

    @field_validator("firms")
    @classmethod
    def distinct_firms(cls, firms):
        for attribute in ("id", "name", "source_url"):
            identities = [getattr(firm, attribute).strip().casefold() for firm in firms]
            if len(set(identities)) != len(firms):
                raise ValueError("duplicate firm identity")
        return firms


def read_private_json(path: Path):
    """Refuse symlinks, other owners, broad permissions and oversized inputs."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("requires an owned private regular file")
        raw = stream.read(512001)
        if len(raw) > 512000:
            raise ValueError("private JSON exceeds limit")
        return json.loads(raw)


@contextmanager
def read_connection(path: Path):
    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3
    )
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        connection.close()


def import_dataset(database: Path, dataset: Dataset):
    """One transaction; preserve all native state and reject cross-project reuse.

    Caller must initialize native migrations and make a private SQLite backup
    first. Import never generates prospects, outbox items, model calls or sends.
    """
    with closing(sqlite3.connect(database, timeout=5)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS research_project (singleton INTEGER PRIMARY KEY CHECK(singleton=1), project TEXT NOT NULL, product TEXT NOT NULL, offer TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS research_firms (id TEXT PRIMARY KEY REFERENCES companies(id), payload TEXT NOT NULL)"
        )
        existing = connection.execute("SELECT project FROM research_project").fetchone()
        if existing and existing[0] != dataset.project:
            raise ValueError("database already belongs to another project")
        connection.execute(
            "INSERT OR REPLACE INTO research_project VALUES (1, ?, ?, ?)",
            (dataset.project, dataset.product, dataset.offer),
        )
        for firm in dataset.firms:
            existing = connection.execute(
                "SELECT name,source_url FROM companies WHERE id=?", (firm.id,)
            ).fetchone()
            if existing and tuple(existing) != (firm.name, firm.source_url):
                raise ValueError("firm identifier conflicts with an existing company")
            connection.execute(
                "INSERT OR IGNORE INTO companies (id,name,source,source_url,description,industry) VALUES (?,?,?,?,?,?)",
                (
                    firm.id,
                    firm.name,
                    "reviewed-public-evidence",
                    firm.source_url,
                    firm.evidence,
                    "Accounting and bookkeeping",
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO research_firms VALUES (?,?)",
                (firm.id, firm.model_dump_json()),
            )
        ids = {firm.id for firm in dataset.firms}
        old = connection.execute("SELECT id FROM research_firms").fetchall()
        if any(row[0] not in ids for row in old):
            raise ValueError(
                "import would leave stale project firms; explicit reconciliation required"
            )
    database.chmod(0o600)


def read_project(database: Path):
    with read_connection(database) as connection:
        project = connection.execute(
            "SELECT project,product,offer FROM research_project WHERE singleton=1"
        ).fetchone()
        if project is None:
            raise ValueError("project not initialized")
        firms = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT payload FROM research_firms ORDER BY json_extract(payload,'$.priority'),id"
            )
        ]
    return {
        **dict(project),
        "firms": firms,
        "firm_count": len(firms),
        "status": "research-qualified; pilot need unvalidated",
        "sending_enabled": False,
        "autopilot_enabled": False,
    }
