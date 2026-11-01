import json
import re
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

    def __init__(self, api_key: str, base_url: str = "http://localhost:4000", workspace_id: Optional[str] = None, timeout: float = 30.0):
        self.api_key, self.base_url, self.workspace_id, self.timeout = api_key, base_url.rstrip("/"), workspace_id, timeout

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
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                text = res.read().decode()
        except urllib.error.HTTPError as e:
            text = e.read().decode()
            err = (json.loads(text) if text else {}).get("error", {}) if text.startswith("{") else {}
            raise HermeticaError(e.code, err.get("code", "http_error"), err.get("message", text[:200]), err.get("details")) from None
        return json.loads(text) if text else None

    def paginate(self, operation: str, query: Optional[Dict[str, Any]] = None, path: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
        """Yield every item of a list operation, following `nextCursor`. `operation` is the method name, e.g. "get_v1_profiles"."""
        q = dict(query or {})
        while True:
            page = getattr(self, operation)(path=path, query=q)
            yield from page.get("items", [])
            if not page.get("nextCursor"):
                return
            q["cursor"] = page["nextCursor"]
