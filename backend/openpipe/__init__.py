"""OpenPipe integration exports.

BUG-14 fix: the original file exported only `llm_call` (synchronous) but every
caller in the codebase uses `allm_call` (async wrapper). Exporting the wrong
symbol was misleading and would cause AttributeError for any caller that
imported from this package rather than directly from backend.openpipe.logger.
"""

from backend.openpipe.logger import allm_call, llm_call

__all__ = ["allm_call", "llm_call"]