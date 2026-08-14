from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from .regulatory_atomic import AtomicRegulatoryPersistence
from .regulatory_lineage import RegulatoryLineageStore


SourceRole = Literal[
    "discovery",
    "official_registry",
    "binding_publication_index",
    "guidance",
]
ChangeStatus = Literal["pending", "acknowledged", "rejected"]

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
SOURCES_PATH = Path(
    os.getenv("EAY_REGULATORY_SOURCES_PATH", "./config/regulatory_sources.json")
)
MAX_FETCH_BYTES = int(os.getenv("EAY_REGULATORY_MAX_FETCH_BYTES", "3000000"))
USER_AGENT = os.getenv(
    "EAY_REGULATORY_USER_AGENT",
    "EAY-Regulatory-Watcher/0.1 (+local compliance monitoring)",
)

# Regulatory watcher never accepts arbitrary user URLs. Even the configured source
# registry is restricted to known official domains to reduce SSRF/supply-chain risk.
ALLOWED_HOST_SUFFIXES = (
    "tarimorman.gov.tr",
    "resmigazete.gov.tr",
    "kaysis.gov.tr",
    "ticaret.gov.tr",
)


class SourceDefinition(BaseModel):
    id: str = Field(min_length=3, max_length=120)
    name: str = Field(min_length=3, max_length=240)
    url: HttpUrl
    role: SourceRole
    jurisdiction: str = Field(default="TR", max_length=32)
    enabled: bool = True
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    notes: str | None = None


class SourceCheckResult(BaseModel):
    source_id: str
    source_name: str
    state: Literal[
        "baseline",
        "unchanged",
        "changed_relevant",
        "changed_irrelevant",
        "error",
    ]
    fetched_at: datetime
    content_hash: str | None = None
    previous_hash: str | None = None
    change_id: str | None = None
    snapshot_id: str | None = None
    snapshot_chain_hash: str | None = None
    change_chain_hash: str | None = None
    authority_level: str | None = None
    authority_fingerprint: str | None = None
    relevance_hits: list[str] = Field(default_factory=list)
    error: str | None = None


class RegulatoryChange(BaseModel):
    id: str
    source_id: str
    source_name: str
    source_url: str
    source_role: SourceRole
    old_hash: str
    new_hash: str
    diff_excerpt: str
    relevance_hits: list[str]
    status: ChangeStatus
    requires_binding_verification: bool
    authority_assessment: dict[str, object] | None = None
    authority_fingerprint: str | None = None
    lineage_chain_hash: str | None = None
