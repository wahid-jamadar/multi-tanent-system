"""
Rate Limiter for BatchHost-Pro
Sliding-window in-memory rate limiter with per-IP and per-key tracking.
"""

import time
import threading
import logging
from collections import defaultdict
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Tracks request timestamps per key (usually IP address) and rejects
    requests that exceed the configured threshold within the window.
    """

    def __init__(self):
        # key -> list of timestamps
        self._windows = defaultdict(list)
        self._lock = threading.RLock()
        # key -> block_until timestamp (for progressive lockout)
        self._blocked = {}
        # Cleanup old entries every 5 minutes
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # 5 minutes

    def _cleanup_stale_entries(self, now):
        """Remove entries older than the longest window we'd ever use (10 min)."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        max_age = 600  # 10 minutes
        stale_keys = []
        for key, timestamps in self._windows.items():
            self._windows[key] = [t for t in timestamps if now - t < max_age]
            if not self._windows[key]:
                stale_keys.append(key)
        for key in stale_keys:
            del self._windows[key]

        # Clean up expired blocks
        expired_blocks = [k for k, v in self._blocked.items() if now >= v]
        for k in expired_blocks:
            del self._blocked[k]

    def is_blocked(self, key):
        """Check if a key is currently under progressive lockout."""
        now = time.time()
        block_until = self._blocked.get(key)
        if block_until and now < block_until:
            return True, block_until - now
        return False, 0

    def block_key(self, key, duration_seconds):
        """Explicitly block a key for a duration (used for progressive lockout)."""
        with self._lock:
            self._blocked[key] = time.time() + duration_seconds
            logger.warning(
                "RATE_LIMIT key=%s blocked for %ds",
                key, duration_seconds,
            )

    def check(self, key, max_requests, window_seconds):
        """Check if a request is allowed. Returns (allowed, info_dict).

        Args:
            key:            Unique identifier (e.g. IP address, agent token).
            max_requests:   Maximum number of requests in the window.
            window_seconds: Size of the sliding window in seconds.

        Returns:
            Tuple of (is_allowed: bool, info: dict) where info contains:
                - remaining: requests remaining in window
                - reset_in:  seconds until the window resets
                - blocked:   whether the key is under lockout
        """
        now = time.time()
        with self._lock:
            self._cleanup_stale_entries(now)

            # Check explicit block first
            blocked, block_remaining = self.is_blocked(key)
            if blocked:
                return False, {
                    "remaining": 0,
                    "reset_in": int(block_remaining),
                    "blocked": True,
                }

            # Sliding window: keep only timestamps within window
            window_start = now - window_seconds
            self._windows[key] = [
                t for t in self._windows[key] if t > window_start
            ]
            current_count = len(self._windows[key])

            if current_count >= max_requests:
                # Calculate when the oldest request in window expires
                oldest = min(self._windows[key]) if self._windows[key] else now
                reset_in = max(0, int(window_seconds - (now - oldest)))
                logger.warning(
                    "RATE_LIMIT exceeded key=%s count=%d/%d window=%ds",
                    key, current_count, max_requests, window_seconds,
                )
                return False, {
                    "remaining": 0,
                    "reset_in": reset_in,
                    "blocked": False,
                }

            # Allow and record
            self._windows[key].append(now)
            remaining = max_requests - current_count - 1
            return True, {
                "remaining": remaining,
                "reset_in": window_seconds,
                "blocked": False,
            }

    def get_request_count(self, key, window_seconds):
        """Get the current request count for a key in a time window."""
        now = time.time()
        with self._lock:
            window_start = now - window_seconds
            return len([t for t in self._windows[key] if t > window_start])


# ─── Global instance ───────────────────────────────────────────────
rate_limiter = RateLimiter()


# ─── Rate limit tiers ──────────────────────────────────────────────
RATE_TIERS = {
    "critical":  {"max_requests": 5,   "window_seconds": 60},   # Login, etc.
    "agent":     {"max_requests": 60,  "window_seconds": 60},   # Agent heartbeats
    "standard":  {"max_requests": 150, "window_seconds": 60},   # Normal API - raised to accommodate frequent user-facing AJAX updates
    "relaxed":   {"max_requests": 180, "window_seconds": 60},   # Page views
}


def _get_client_key():
    """Extract a meaningful client identifier from the request.

    Uses X-Forwarded-For if behind a reverse proxy, else remote_addr.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # Take the first IP (client IP) from the chain
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limit(tier="standard", key_func=None):
    """Decorator to apply rate limiting to a Flask route.

    Args:
        tier:     One of 'critical', 'agent', 'standard', 'relaxed'.
        key_func: Optional callable returning the rate-limit key.
                  Defaults to client IP address.
    """
    config = RATE_TIERS.get(tier, RATE_TIERS["standard"])

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            key = (key_func() if key_func else _get_client_key())
            # Prefix with tier to keep separate buckets
            full_key = f"{tier}:{key}"

            allowed, info = rate_limiter.check(
                full_key,
                config["max_requests"],
                config["window_seconds"],
            )

            if not allowed:
                logger.warning(
                    "RATE_LIMIT blocked request=%s %s key=%s info=%s",
                    request.method, request.path, key, info,
                )
                response = jsonify({
                    "error": "Too many requests",
                    "message": f"Rate limit exceeded. Try again in {info['reset_in']}s.",
                    "retry_after": info["reset_in"],
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(info["reset_in"])
                response.headers["X-RateLimit-Remaining"] = "0"
                return response

            resp = f(*args, **kwargs)

            # Add rate limit headers to successful responses
            if hasattr(resp, "headers"):
                resp.headers["X-RateLimit-Remaining"] = str(info["remaining"])
                resp.headers["X-RateLimit-Limit"] = str(config["max_requests"])
            return resp

        return wrapped
    return decorator


# ─── Login-specific brute force protection ──────────────────────────
LOGIN_LOCKOUT_THRESHOLDS = [
    (5,  60),    # 5 failures  -> locked 1 minute
    (10, 300),   # 10 failures -> locked 5 minutes
    (20, 1800),  # 20 failures -> locked 30 minutes
]


def check_login_brute_force(ip_address):
    """Check if an IP should be locked out due to repeated login failures.

    Returns (is_blocked, lockout_remaining_seconds).
    """
    blocked, remaining = rate_limiter.is_blocked(f"login_lockout:{ip_address}")
    return blocked, remaining


def record_login_failure(ip_address):
    """Record a failed login and apply progressive lockout if needed."""
    key = f"login_failures:{ip_address}"
    # Use a 30-minute window for counting failures
    rate_limiter.check(key, max_requests=999, window_seconds=1800)

    failure_count = rate_limiter.get_request_count(key, 1800)

    for threshold, lockout_duration in reversed(LOGIN_LOCKOUT_THRESHOLDS):
        if failure_count >= threshold:
            rate_limiter.block_key(f"login_lockout:{ip_address}", lockout_duration)
            logger.warning(
                "RATE_LIMIT login lockout ip=%s failures=%d lockout=%ds",
                ip_address, failure_count, lockout_duration,
            )
            return lockout_duration
    return 0


def record_login_success(ip_address):
    """Clear login failure tracking after a successful login."""
    with rate_limiter._lock:
        rate_limiter._windows.pop(f"login_failures:{ip_address}", None)
        rate_limiter._blocked.pop(f"login_lockout:{ip_address}", None)
