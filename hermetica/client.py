import email.utils
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Iterator, Optional

from .operations import Operations


class HermeticaError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message, self.details = status, code, message, details


class Client(Operations):
    """Standard library only. `Client("hm_sk_...", base_url="https://api.example.com")`."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:4000", workspace_id: Optional[str] = None, timeout: float = 30.0, max_retries: int = 3):
        self.api_key, self.base_url, self.workspace_id, self.timeout = api_key, base_url.rstrip("/"), workspace_id, timeout
        self.max_retries = max_retries

    def request(self, method: str, path: str, *, path_params: Optional[Dict[str, Any]] = None, query: Optional[Dict[str, Any]] = None, body: Any = None, idempotency_key: Optional[str] = None) -> Any:
        path = re.sub(r"\{(\w+)\}", lambda m: urllib.parse.quote(str((path_params or {})[m.group(1)]), safe=""), path)
        q = urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v is not None}, doseq=True)
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if self.workspace_id:
            headers["X-Workspace-Id"] = self.workspace_id
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if method != "GET":
            headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())  # a retry with the same key never repeats the action
        req = urllib.request.Request(self.base_url + path + ("?" + q if q else ""), data=data, method=method, headers=headers)
        # Every call is safe to replay: a GET, or a non-GET carrying the same Idempotency-Key on every attempt.
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as res:
                    text = res.read().decode()
                return json.loads(text) if text else None
            except urllib.error.HTTPError as e:
                text = e.read().decode()
                if (e.code == 429 or e.code >= 500) and attempt < self.max_retries:
                    wait = _retry_after(e.headers.get("Retry-After") if e.headers else None)
                    time.sleep(_backoff(attempt) if wait is None else wait)
                    attempt += 1
                    continue
                err = (json.loads(text) if text else {}).get("error", {}) if text.startswith("{") else {}
                raise HermeticaError(e.code, err.get("code", "http_error"), err.get("message", text[:200]), err.get("details")) from None
            except OSError:  # network error or timeout (URLError is an OSError)
                if attempt >= self.max_retries:
                    raise
                time.sleep(_backoff(attempt))
                attempt += 1

    def paginate(self, operation: str, query: Optional[Dict[str, Any]] = None, path: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
        """Yield every item of a list operation, following `nextCursor`. `operation` is the method name, e.g. "get_v1_profiles"."""
        q = dict(query or {})
        while True:
            page = getattr(self, operation)(path=path, query=q)
            yield from page.get("items", [])
            if not page.get("nextCursor"):
                return
            q["cursor"] = page["nextCursor"]


def _backoff(attempt: int) -> float:
    """Full jitter: a random wait up to 0.25 s * 2^attempt, capped at 8 s."""
    return random.random() * min(8.0, 0.25 * 2 ** attempt)


def _retry_after(value: Optional[str]) -> Optional[float]:
    """Retry-After as delta-seconds or an HTTP date, in seconds; None when absent or unparseable."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        at = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, at.timestamp() - time.time())
