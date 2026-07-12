"""The ledger: a multi-currency, local-first, content-free flight recorder for AI work.

Public surface: get_ledger_db (connection), SyncLedgerSink/DefaultLedgerSink (write),
forecost.ledger.queries (read-only, used by estimate/ and policy/).
"""

from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import DefaultLedgerSink, SyncLedgerSink

__all__ = ["DefaultLedgerSink", "SyncLedgerSink", "get_ledger_db"]
