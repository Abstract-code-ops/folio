"""Dramatiq worker process configuration and actor discovery.

Broker setup and actor registration. When the ``dramatiq`` CLI imports
this package (see docker-compose.yaml), the broker is configured using
``dramatiq-pg`` (PostgreSQL-backed).

In the FastAPI process and test environment, the PostgreSQL broker may
not be available — the setup falls back to ``StubBroker`` so that
``.send()`` calls from the service layer function without error
(though messages go nowhere in stub mode).
"""

from __future__ import annotations

import logging

import dramatiq
from dramatiq.brokers.stub import StubBroker

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Broker ─────────────────────────────────────────────────────
# The ``dramatiq`` CLI sets ``DRAMATIQ_BROKER`` env var, but we
# detect the presence of the real broker package to decide.

_broker = None

try:
    from dramatiq_pg import PostgreSQLBroker

    _broker = PostgreSQLBroker(url=settings.database_url)
    logger.info("Using PostgreSQLBroker for Dramatiq")
except ImportError:
    _broker = StubBroker()
    logger.info("dramatiq-pg not available — using StubBroker")

if _broker is not None:
    dramatiq.set_broker(_broker)

# ── Import actors so they register with the broker ────────────

# Each actor module is imported here to ensure the @dramatiq.actor
# decorator fires after the broker is configured.
from app.workers import note_session  # noqa: F401, E402
