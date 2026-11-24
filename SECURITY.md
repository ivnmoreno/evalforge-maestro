# Security Policy

## Supported Versions

Security fixes are released for the latest minor release line:

| Version | Supported |
| --- | --- |
| `0.3.x` | Yes |
| `< 0.3.0` | No |

---

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues, pull requests, or discussions.**

Report suspected vulnerabilities privately using either:

1. **GitHub Private Vulnerability Reporting (Preferred)**:
   [Open a private security advisory](https://github.com/ivnmoreno/evalforge-maestro/security/advisories/new) on `ivnmoreno/evalforge-maestro`.
2. **Email Fallback**:
   Contact [ivnmoreno@gmail.com](mailto:ivnmoreno@gmail.com) with `[SECURITY] evalforge-maestro:` in the subject line.

Please include:
- A clear description of the vulnerability and affected component (`cli`, `judges`, `embeddings`, `storage`, `service`, `adapters`, etc.).
- Minimal reproduction steps or proof-of-concept payload (using synthetic secrets/data only).
- Impact assessment and any suggested mitigation.

We aim to acknowledge reports within **5 business days** and coordinate disclosure and a patched release before publishing details.

---

## Security Architecture & Boundaries

EvalForge Maestro implements defense-in-depth safeguards designed for local, CI, and internal evaluation workflows:

- **Pre-Network Locality Enforcement (`--local-only`)**: Blocks outbound non-loopback judge and embedding endpoints before network calls execute and enforces `LITELLM_LOCAL_MODEL_COST_MAP=True` for air-gapped environments.
- **Opt-In Pre-Network PII Egress Blocking (`--block-pii`)**: Scans outbound remote judge/embedding payloads for selected patterns (email addresses, US SSNs, phone numbers, Luhn-valid payment cards, and secret tokens) via `detect_pii_categories` and blocks requests pre-network (`LocalOnlyPolicyError`, CLI exit code `4`). It is **not** a general-purpose compliance/GDPR classifier and does not silently mutate persisted evaluation text.
- **Credential Scrubbing**: `redact_secrets` and `scrub_secret_text` automatically mask sensitive dictionary keys, `Bearer` headers, URL userinfo credentials, and known provider API key formats (`[REDACTED]`) across logs, traces, resolved configs, SQLite index explanations, and reports.
- **Prompt-Injection Delimiting**: Model-based judges wrap untrusted target outputs and retrieved contexts inside randomized XML/nonce boundaries and validate structured JSON outputs strictly.
- **Artifact Storage Permissions**: Canonical `.evalforge/` directories and run records use atomic writes with `0o700`/`0o600` POSIX permissions where supported by the OS.
- **Optional HTTP Service (`evalforge-maestro serve`)**: Defaults to loopback (`127.0.0.1`), blocks non-loopback binding without a non-empty Bearer token (`EVALFORGE_SERVICE_TOKEN` / `--auth-token`, verified with `hmac.compare_digest`), enforces `local_only=True` by default, rejects oversized payloads (`HTTP 413`), and validates path identifiers against traversal.

### Deployment & Threat-Model Exclusions

The following are outside EvalForge's built-in threat model and must be handled by the operator's environment:

- **Public Edge Exposure of `evalforge-maestro serve`**: The stdlib `ThreadingHTTPServer` targets local development, CI, and trusted internal networks—it provides no TLS termination, rate limiting, bounded worker thread pools, or per-connection socket timeouts. For external exposure, place a reverse proxy / API gateway in front or mount `ServiceApplication` in a production ASGI/WSGI server (see [`docs/remote-service.md`](docs/remote-service.md#21-deployment-boundary--external-exposure)).
- **Live Python Targets (`--target module:callable`)**: Invoking a user-supplied Python target executes that target's code in the caller's process by design. Never point `--target` at untrusted code.
- **Local Filesystem Integrity**: `.evalforge/` provides application-level immutability, not cryptographic protection against an attacker who already has write access to the local filesystem.
