import time
import logging
import sys
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


# -----------------------------
# Logger setup
# -----------------------------
logger = logging.getLogger("insighta")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

handler.setFormatter(formatter)

# prevent duplicate handlers in reload/dev
if not logger.handlers:
    logger.addHandler(handler)


# -----------------------------
# Middleware
# -----------------------------
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()

        response = await call_next(request)

        duration_ms = round((time.time() - start) * 1000)

        logger.info(
            "%s %s %s %sms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms
        )

        return response