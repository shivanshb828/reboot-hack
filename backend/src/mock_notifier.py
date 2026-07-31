"""
Simulated on-call pager / SMS gateway.

mock_send_page() is the stand-in for a real external API call.  It logs
visibly so you can watch it in the `rbt dev run` terminal and time a
server kill for the mid-execution crash demo.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Incremented each time mock_send_page is actually invoked.
# The test reads this to confirm the call count stays at 1.
_call_count: int = 0


async def mock_send_page(case_id: str) -> str:
    """
    Simulate an SMS / pager API call.

    Returns a confirmation string so that `at_least_once_per_workflow`
    has a concrete value to pickle into RocksDB.  Once this function
    RETURNS and its result is stored, a workflow replay will not invoke
    this function again — it returns the stored string directly.

    Crash window for the demo
    --------------------------
    Kill the server AFTER the '[PAGER] <<< SENT' line appears and BEFORE
    `notify_status` shows 'sent' in the state inspector.  That is the
    window where at_least_once has the memoized result but the state write
    hasn't committed yet.  On restart the workflow reads the memoized
    result (no second call) and commits the state write.

    If you kill during the sleep (before the SENT line), mock_send_page
    WILL be retried — that is the honest "at least once" guarantee.
    Use at_most_once to prevent even that at the cost of permanent failure
    on mid-call crash.
    """
    global _call_count
    _call_count += 1
    logger.info(f"[PAGER] >>> Sending page for case '{case_id}'  (sleeping 1.5 s)...")
    await asyncio.sleep(1.5)
    msg = f"Page delivered for case '{case_id}'"
    logger.info(f"[PAGER] <<< SENT  {msg}")
    return msg
