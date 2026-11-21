# Quickstart & Validation Scenarios: Feature 010 (`010-remote-eval-service`)

## 1. Launch Optional Loopback HTTP Service

```bash
export EVALFORGE_SERVICE_TOKEN="dev-service-token"
evalforge-maestro serve --host 127.0.0.1 --port 8787 --storage-dir .evalforge --mock --local-only
```

In another shell:

```bash
curl -s -H "Authorization: Bearer $EVALFORGE_SERVICE_TOKEN" http://127.0.0.1:8787/health
curl -s -H "Authorization: Bearer $EVALFORGE_SERVICE_TOKEN" "http://127.0.0.1:8787/v1/runs?limit=10"
```

## 2. In-Process & Live HTTP Python Evaluation Call

```python
import json
from evalforge_maestro import ServiceApplication, ServiceConfig, ServiceEvaluateRequest

app = ServiceApplication(
    ServiceConfig(storage_dir=".evalforge", mock_mode=True, local_only=True),
    auth_token="tok-local",
)
status, headers, body = app.handle_request(
    "GET",
    "/health",
    headers={"Authorization": "Bearer tok-local"},
)
assert status == 200
print(json.loads(body))
```

## 3. Run Hybrid/Rerank & Judge Calibration CI Templates

```bash
evalforge-maestro run \
  --config examples/ci/evalforge-hybrid-rerank.toml \
  --strict \
  --json

evalforge-maestro calibrate \
  --samples examples/ci/calibration-samples.jsonl \
  --metric groundedness \
  --min-agreement 0.75 \
  --mock \
  --local-only \
  --json
```
