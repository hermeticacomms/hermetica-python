# Hermetica Python client

Generated from `docs/api/openapi.json` by `node scripts/gen-sdks.mjs` (2042 operations). Standard library only.

```python
from hermetica import Client, HermeticaError

hm = Client("hm_sk_...", base_url="https://api.example.com")
page = hm.get_v1_profiles(query={"limit": 25})
for profile in hm.paginate("get_v1_profiles", query={"limit": 100}):
    print(profile["id"])
hm.post_v1_events(body={"name": "signed_up", "profile": {"email": "ada@example.com"}}, idempotency_key="signup-ada-1")
```

- One method per operationId, snake_case. Arguments: `path` (path params), `query`, `body`, `idempotency_key`.
- Every non-GET call sends an `Idempotency-Key` (random unless you pass one); reuse yours when you retry a call yourself.
- Network errors, 429 and 5xx are retried automatically with exponential backoff and jitter, honouring `Retry-After`. Every attempt
  of a call sends the same `Idempotency-Key`, so a retried write never runs twice. `Client(..., max_retries=3)` is the default; `0` turns retries off.
- Errors raise `HermeticaError` with `status`, `code`, `message`, `details`.
- Consent and suppression are enforced by the API; the client cannot bypass them.
- Regenerate after the API changes: `node scripts/gen-sdks.mjs`.
