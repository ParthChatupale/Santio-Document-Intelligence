"""Bounded transport retries, separate from answer repair and retrieval recovery."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import random
import time


def temporary_error(exc):
    """Never retry credentials, missing models, bad requests or validation errors."""
    import httpx
    from openai import APIConnectionError, APITimeoutError
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is not None:
        return status in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, (APIConnectionError, APITimeoutError, httpx.TransportError, TimeoutError, ConnectionError))


def retry_after_seconds(exc, now=None):
    """Read seconds or HTTP-date without persisting provider headers/bodies."""
    headers = getattr(getattr(exc, "response", None), "headers", {})
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = date.timestamp() - (time.time() if now is None else now)
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


class ProviderRetries:
    """At most two extra attempts per request and 60s of waits per question.

    One instance is shared across planning, reranking, generation, answer repair,
    and retrieval recovery. Network/model execution time is separate from the
    waiting budget. Workers can be cancelled by their existing process owner.
    """
    def __init__(self, *, max_retries=2, wait_budget=60.0, sleep=None, clock=None, jitter=None):
        self.max_retries, self.wait_budget = max_retries, wait_budget
        self.waited = 0.0
        self.events = []
        self.sleep = sleep or time.sleep
        self.clock = clock or time.time
        self.jitter = jitter or (lambda: random.uniform(0, 1))

    def summary(self):
        return {"maximum_retries_per_request": self.max_retries,
                "wait_budget_seconds": self.wait_budget, "waited_seconds": round(self.waited, 3),
                "events": list(self.events)}

    def run(self, operation, stage, *, on_trace=None, progress=None):
        def emit(name, data):
            entry = {"stage": stage, **data}
            self.events.append({"event": name, **entry})
            if on_trace:
                on_trace(name, entry)

        for attempt in range(self.max_retries + 1):
            emit("Provider request attempt", {"provider_attempt": attempt + 1})
            try:
                result = operation()
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if status is None:
                    status = getattr(getattr(exc, "response", None), "status_code", None)
                reason = "rate_limit" if status == 429 else "temporary_failure"
                detail = {"provider_attempt": attempt + 1, "error_type": type(exc).__name__, "http_status": status}
                if not temporary_error(exc):
                    emit("Provider request stopped", {**detail, "reason": "non_retryable"})
                    raise
                if attempt >= self.max_retries:
                    emit("Provider retries exhausted", {**detail, "reason": "attempt_limit"})
                    raise
                delay = retry_after_seconds(exc, self.clock())
                if delay is None:
                    delay = 4.0 * 2 ** attempt + self.jitter()
                remaining = max(0.0, self.wait_budget - self.waited)
                if remaining <= 0 or delay > remaining:
                    emit("Provider retries exhausted", {**detail, "reason": "wait_budget",
                         "requested_wait_seconds": round(delay, 3), "remaining_wait_seconds": round(remaining, 3)})
                    raise
                emit("Provider retry waiting", {**detail, "reason": reason, "retry_number": attempt + 1,
                     "maximum_retries": self.max_retries, "wait_seconds": delay,
                     "retry_at": datetime.fromtimestamp(self.clock() + delay, timezone.utc).isoformat()})
                if progress:
                    progress(f"Waiting to retry {stage} in {math.ceil(delay)} seconds (retry {attempt+1}/{self.max_retries})")
                # Short sleeps keep individual waits bounded. The question worker
                # is terminated immediately by Cancel, including during this wait.
                self.waited += delay
                left = delay
                while left > 0:
                    step = min(left, 0.5)
                    self.sleep(step)
                    left -= step
                emit("Provider retry resumed", {"retry_number": attempt + 1, "provider_attempt": attempt + 2})
                if progress:
                    progress(f"Retrying {stage} (retry {attempt+1}/{self.max_retries})")
            else:
                emit("Provider request succeeded", {"provider_attempt": attempt + 1})
                return result


def provider_error_message(exc):
    """Public, actionable errors with no provider payload or credentials."""
    status = getattr(exc, "status_code", None)
    if status == 429:
        return "NVIDIA is rate-limiting requests. Automatic retries reached their attempt or waiting limit. Please try again shortly."
    if temporary_error(exc):
        return "The model service is temporarily unavailable. Automatic retries reached their attempt or waiting limit. Please try again."
    if status in {401, 403}:
        return "The model service rejected access. Check the server API key and account permissions."
    if status == 404:
        return "The configured model endpoint was not found or is unavailable to this account. Check the server model setting."
    return "The model request failed. Check the saved question log and server model settings."
