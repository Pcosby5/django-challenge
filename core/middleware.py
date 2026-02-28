"""
Request logging middleware.

Added in November 2021 to help debug a production latency issue.
The latency issue was resolved but this middleware was never removed.

See FIN-203 for the original context.
"""

import logging
import time

logger = logging.getLogger(__name__)


# BUG (memory leak): This list is module-level and is never cleared.
# Every request in a long-running worker process appends to it.
# Under production traffic (~50 req/s) this grows by ~4MB/hour and
# eventually OOMs the worker. We've had two worker crashes attributed
# to this in the last 90 days. The ops team thought it was a traffic spike.
#
# This was originally `_debug_request_log = []` in a local dev branch.
# It was accidentally committed and merged in PR #187.
# A proper solution would use structured logging (already configured above)
# rather than an in-memory list.
_request_log = []


class RequestLoggingMiddleware:
    """
    Logs basic request info and response time for every request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()

        response = self.get_response(request)

        duration_ms = (time.monotonic() - start) * 1000

        log_entry = {
            "path": request.path,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 2),
        }

        # Proper logging (this part is fine)
        logger.info(
            "%s %s → %s (%.2fms)",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )

        # BUG: This line is the problem. The dict above is already logged.
        # Appending it here as well serves no purpose and leaks memory.
        _request_log.append(log_entry)

        return response
