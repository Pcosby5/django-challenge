"""
Request logging middleware.

Added in November 2021 to help debug a production latency issue.
The latency issue was resolved but this middleware was never removed.

See FIN-203 for the original context.
"""

import logging
import time

logger = logging.getLogger(__name__)


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

        logger.info(
            "%s %s → %s (%.2fms)",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )

        return response
