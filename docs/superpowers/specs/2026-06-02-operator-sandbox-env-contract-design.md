# OLS-3200: Operator-Sandbox Generic Env Var Contract

## Problem

The operator currently sets SDK-specific env vars (`ANTHROPIC_MODEL`,
`CLAUDE_CODE_USE_VERTEX`, `OPENAI_BASE_URL`, etc.) on sandbox pod templates.
This couples the operator to provider SDK internals and requires operator
changes whenever a new provider or SDK configuration is added.

## Decision

Replace all SDK-specific env vars with generic `LIGHTSPEED_*` vars set by the
operator. The sandbox maps these to SDK-specific env vars internally via a
configuration mapping module.

## Contract

### Operator → Sandbox env vars

The operator sets these generic vars on the sandbox pod template:

| Env var | Required | Source |
|---|---|---|
| `LIGHTSPEED_PROVIDER` | Yes | `LLMProvider.spec.type` → lowercase (`anthropic`, `vertex`, `openai`, `azure`, `bedrock`) |
| `LIGHTSPEED_MODEL` | Yes | `Agent.spec.model` |
| `LIGHTSPEED_MODEL_PROVIDER` | When `vertex` | `googleCloudVertex.modelProvider` (`Anthropic`, `Google`, `OpenAI`) |
| `LIGHTSPEED_PROVIDER_URL` | No | URL override from provider config; for Azure, `url` overrides `endpoint` |
| `LIGHTSPEED_PROVIDER_PROJECT` | No | `googleCloudVertex.projectID` |
| `LIGHTSPEED_PROVIDER_REGION` | No | `googleCloudVertex.region` or `awsBedrock.region` |
| `LIGHTSPEED_PROVIDER_API_VERSION` | No | `azureOpenAI.apiVersion` |

Credentials are mounted unconditionally for all providers via:
- `envFrom` secretRef (all secret keys as env vars)
- Volume mount at `/var/run/secrets/llm-credentials/` (whole secret as files, read-only)

The operator MUST NOT set any SDK-specific env vars.

### Provider type mapping

| CRD `spec.type` | `LIGHTSPEED_PROVIDER` |
|---|---|
| `Anthropic` | `anthropic` |
| `GoogleCloudVertex` | `vertex` |
| `OpenAI` | `openai` |
| `AzureOpenAI` | `azure` |
| `AWSBedrock` | `bedrock` |

### Azure URL resolution (operator-side)

`AzureOpenAI` has both `endpoint` (required, the Azure resource URL) and `url`
(optional, proxy override). The operator resolves: when `url` is set it
overrides `endpoint`; the winning value becomes `LIGHTSPEED_PROVIDER_URL`.

## Sandbox: Configuration Mapping

### Module: `src/lightspeed_agentic/config.py`

Exports `resolve_sdk() -> str`. Called once at the top of `app.py` before
provider construction. Reads `LIGHTSPEED_*` env vars, sets SDK-specific env
vars in `os.environ`, returns the SDK name (`"claude"`, `"gemini"`, or
`"openai"`).

### Mapping table

| `LIGHTSPEED_PROVIDER` | `LIGHTSPEED_MODEL_PROVIDER` | SDK name | SDK env vars set |
|---|---|---|---|
| `anthropic` | — | `claude` | `ANTHROPIC_MODEL` |
| `vertex` | `Anthropic` | `claude` | `ANTHROPIC_MODEL`, `CLAUDE_CODE_USE_VERTEX=1`, `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION`, `GOOGLE_APPLICATION_CREDENTIALS=/var/run/secrets/llm-credentials/GOOGLE_APPLICATION_CREDENTIALS` |
| `vertex` | `Google` | `gemini` | `GEMINI_MODEL`, `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` |
| `vertex` | `OpenAI` | `openai` | `OPENAI_MODEL`, `OPENAI_BASE_URL` |
| `openai` | — | `openai` | `OPENAI_MODEL` |
| `azure` | — | `openai` | `OPENAI_MODEL`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION` |
| `bedrock` | — | `claude` | `ANTHROPIC_MODEL`, `CLAUDE_CODE_USE_BEDROCK=1`, `AWS_REGION` |

Additional mappings:
- `LIGHTSPEED_MODEL` → the appropriate `*_MODEL` var per row above
- `LIGHTSPEED_PROVIDER_URL` → the appropriate URL var (`ANTHROPIC_BASE_URL`,
  `OPENAI_BASE_URL`, or `AZURE_OPENAI_ENDPOINT`) when set
- `LIGHTSPEED_PROVIDER_PROJECT` → `ANTHROPIC_VERTEX_PROJECT_ID` (Vertex/Anthropic),
  `GOOGLE_CLOUD_PROJECT` (Vertex/Google)
- `LIGHTSPEED_PROVIDER_REGION` → `CLOUD_ML_REGION` (Vertex/Anthropic),
  `GOOGLE_CLOUD_LOCATION` (Vertex/Google), `AWS_REGION` (Bedrock)
- `LIGHTSPEED_PROVIDER_API_VERSION` → `AZURE_OPENAI_API_VERSION` (Azure)

Credentials (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`,
`AWS_ACCESS_KEY_ID`, etc.) arrive via `envFrom` and need no mapping.

### Default behavior

When `LIGHTSPEED_PROVIDER` is unset, default to `anthropic` (SDK: `claude`).
When `LIGHTSPEED_MODEL` is unset, the SDK-specific model var is not set and the
existing per-provider fallback in `routes/__init__.py` uses the package
`DEFAULT_MODEL` constant.

### Error handling

`LIGHTSPEED_PROVIDER=vertex` without `LIGHTSPEED_MODEL_PROVIDER` raises a
clear error at startup.

## Sandbox: Impact on Existing Modules

### `app.py`

```python
from lightspeed_agentic.config import resolve_sdk

sdk_name = resolve_sdk()
provider = create_provider(sdk_name)
router = build_router(provider, ...)
register_ready_route(app, sdk_name=sdk_name)
```

### `factory.py`

`create_provider(name: str)` takes a required SDK name argument. Removes
`os.environ.get("LIGHTSPEED_AGENT_PROVIDER", "claude")` fallback.

### `health.py`

`register_ready_route(app, sdk_name=...)` receives the SDK name directly.
`_provider_name()` removed — no `LIGHTSPEED_AGENT_PROVIDER` env var exists.
Readiness checks (`check_provider_env`, `check_provider_endpoint`) receive the
SDK name from the caller chain.

### Provider files

Zero changes. They read SDK env vars set by `resolve_sdk()`.

### `routes/__init__.py`

No change. Model resolution uses `provider.name` to look up `*_MODEL` env vars,
which `resolve_sdk()` already set.

### Eval/e2e credential files

Out of scope. These detect SDK-level credentials for local dev runs and are
not part of the operator-sandbox contract.

## Deprecated: `LIGHTSPEED_AGENT_PROVIDER`

Removed from the codebase. Replaced by `LIGHTSPEED_PROVIDER` (generic hosting
backend). The SDK name is an internal return value from `resolve_sdk()`, not an
env var.

## Deprecated: `LIGHTSPEED_MODE`

Not part of this contract. The operator may continue setting it independently;
the sandbox does not consume it.

## Operator: `patchLLMCredentials` Rewrite

### File: `controller/proposal/sandbox_templates.go`

The function switches on `LLMProviderType` and now sets only `LIGHTSPEED_*`
env vars.

**Always set (all providers):**
- `LIGHTSPEED_PROVIDER` from type mapping table above
- `LIGHTSPEED_MODEL` from `Agent.spec.model`
- `envFrom` — credentials secret (unconditional)
- Volume `llm-credentials` at `/var/run/secrets/llm-credentials/` (unconditional, read-only)

**Per provider type:**

| `spec.type` | Additional vars |
|---|---|
| `Anthropic` | `LIGHTSPEED_PROVIDER_URL` if `url` set |
| `GoogleCloudVertex` | `LIGHTSPEED_MODEL_PROVIDER`, `LIGHTSPEED_PROVIDER_PROJECT`, `LIGHTSPEED_PROVIDER_REGION`, `LIGHTSPEED_PROVIDER_URL` if `url` set |
| `OpenAI` | `LIGHTSPEED_PROVIDER_URL` if `url` set |
| `AzureOpenAI` | `LIGHTSPEED_PROVIDER_URL` (from `endpoint`, overridden by `url`), `LIGHTSPEED_PROVIDER_API_VERSION` if set |
| `AWSBedrock` | `LIGHTSPEED_PROVIDER_REGION`, `LIGHTSPEED_PROVIDER_URL` if `url` set |

**Removed env vars:**
`ANTHROPIC_MODEL`, `CLAUDE_CODE_USE_VERTEX`, `GCP_PROJECT`, `GCP_REGION`,
`GOOGLE_APPLICATION_CREDENTIALS`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_VERSION`, `CLAUDE_CODE_USE_BEDROCK`, `AWS_REGION`,
`OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`.

**Credential mount path:** `/var/secrets/google` → `/var/run/secrets/llm-credentials/`.
Unconditional for all providers.

### Hash stability

`computeTemplateHash` hashes CRD content (LLM spec, model, skills, etc.), not
env var names. The hash changes because LLM spec content changes are what
drives template derivation — this is correct behavior.

## Testing

### Sandbox: `config.py` unit tests
- All 7 provider combinations: assert correct SDK vars and SDK name.
- Default: `LIGHTSPEED_PROVIDER` unset → `anthropic` → `"claude"`.
- Error: `vertex` without `LIGHTSPEED_MODEL_PROVIDER` → startup error.
- URL mapping: `LIGHTSPEED_PROVIDER_URL` → correct SDK URL var per provider.
- Isolation: `monkeypatch.setenv` / `monkeypatch.delenv`.

### Sandbox: existing test updates
- `factory.py`: `create_provider` takes required `name` arg.
- `health.py`: receives `sdk_name` arg, no env var reading.

### Operator: `sandbox_templates_test.go`
- Assert `LIGHTSPEED_PROVIDER`, `LIGHTSPEED_MODEL` instead of `ANTHROPIC_MODEL`.
- Assert no SDK-specific env vars present.
- Assert unconditional `envFrom` + volume mount for all provider types.
- Azure: `url` overrides `endpoint` for `LIGHTSPEED_PROVIDER_URL`.

## Deployment

Both repos merged together. Coordinated release — no backward compatibility
period.

## References

- Jira: [OLS-3200](https://redhat.atlassian.net/browse/OLS-3200)
- Operator spec PR: [openshift/lightspeed-agentic-operator#20](https://github.com/openshift/lightspeed-agentic-operator/pull/20) (merged)
- Sandbox spec PR: [openshift/lightspeed-agentic-sandbox#60](https://github.com/openshift/lightspeed-agentic-sandbox/pull/60) (merged)
- Supersedes: OLS-3044, OLS-3051
