"""The ledger: a multi-currency, local-first, content-free flight recorder for AI work.

Public surface: get_ledger_db (connection), SyncLedgerSink (write), and
forecost.ledger.queries (read-only, used by estimate/ and policy/).
"""

from forecost.ledger.db import get_ledger_db
from forecost.ledger.sink import SyncLedgerSink

__all__ = ["SyncLedgerSink", "get_ledger_db"]
