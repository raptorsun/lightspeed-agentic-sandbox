# Behavioral spec: configuration, environment, deployment

Audience: AI agents (Claude). Precision over narrative.

Cross-references: how options are consumed in code → `how/provider-architecture.md`. HTTP fields → `run-api.md`. Provider options → `provider-contract.md`.

## Behavioral Rules

1. **Operator env var contract.** The operator sets generic `LIGHTSPEED_*` env vars on the sandbox pod template. The sandbox MUST NOT depend on the operator setting any SDK-specific env vars. The operator sets:

    | Env var | Required | Description |
    |---|---|---|
    | `LIGHTSPEED_PROVIDER` | Yes | Hosting backend: `anthropic`, `vertex`, `openai`, `azure`, `bedrock` |
    | `LIGHTSPEED_MODEL` | Yes | Model identifier (e.g. `claude-sonnet-4-20250514`) |
    | `LIGHTSPEED_MODEL_PROVIDER` | When provider=`vertex` | Model family on Vertex: `Anthropic`, `Google`, `OpenAI` |
    | `LIGHTSPEED_PROVIDER_URL` | When URL set on provider config | Optional API endpoint override |
    | `LIGHTSPEED_PROVIDER_PROJECT` | When provider=`vertex` | Cloud project ID |
    | `LIGHTSPEED_PROVIDER_REGION` | When provider=`vertex` or `bedrock` | Cloud region |
    | `LIGHTSPEED_PROVIDER_API_VERSION` | When provider=`azure` | API version |

    Credentials are mounted via `envFrom` (all secret keys as env vars) AND as files at `/var/run/secrets/llm-credentials/`.

    The operator also sets audit, observability, and MCP env vars:

    | Env var | Required | Description |
    |---|---|---|
    | `LIGHTSPEED_AUDIT_ENABLED` | No | When `"true"`, structured audit event logging is enabled. Default: disabled. |
    | `OTEL_EXPORTER_OTLP_ENDPOINT` | No | OTLP gRPC endpoint for span export (e.g. `jaeger-otlp-grpc.observability.svc:4317`). When absent, tracing is no-op. |
    | `LIGHTSPEED_MCP_SERVERS` | No | JSON array of MCP server configs. See rule 20. When absent, no MCP servers are configured. |

2. **Provider configuration mapping.** On startup, the sandbox MUST read the generic env vars from rule 1 and set the SDK-specific env vars required by each provider SDK. This mapping runs before the FastAPI app starts. The mapping logic:

    | `LIGHTSPEED_PROVIDER` | `LIGHTSPEED_MODEL_PROVIDER` | SDK | SDK env vars set |
    |---|---|---|---|
    | `anthropic` | *(derived)* | — | Pending rerouting [PLANNED: OLS-3473] |
    | `vertex` | `anthropic` | — | Pending rerouting [PLANNED: OLS-3473] |
    | `vertex` | `google` | `gemini` | `GEMINI_MODEL`, `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_APPLICATION_CREDENTIALS` |
    | `vertex` | `openai` | `openai` | `OPENAI_MODEL`, `OPENAI_BASE_URL`, `GOOGLE_APPLICATION_CREDENTIALS` |
    | `openai` | *(derived)* | `openai` | `OPENAI_MODEL` |
    | `azure` | *(derived)* | `openai` | `OPENAI_MODEL`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_VERSION` |
    | `bedrock` | *(derived)* | — | Pending rerouting [PLANNED: OLS-3473] |

    `LIGHTSPEED_PROVIDER_URL` MUST be mapped to the SDK-appropriate URL env var when set (e.g. `ANTHROPIC_BASE_URL`, `OPENAI_BASE_URL`). `LIGHTSPEED_PROVIDER_PROJECT` and `LIGHTSPEED_PROVIDER_REGION` MUST be mapped to the provider-specific project/region vars. Credential files at `/var/run/secrets/llm-credentials/` MUST be referenced via `GOOGLE_APPLICATION_CREDENTIALS` for Vertex providers that require file-based credentials.

3. **Provider selection.** `resolve_sdk()` returns a `ResolvedSDK` whose `name` field selects the backend SDK (`gemini` or `openai`). This is determined by the configuration mapping (rule 2), not by the operator. Unknown values are rejected at startup. [PLANNED: OLS-3473] The `anthropic`, `vertex/anthropic`, and `bedrock` paths previously resolved to the `claude` SDK which is being removed; these paths are pending rerouting to alternative agentic SDKs.

4. **Default provider.** When `LIGHTSPEED_PROVIDER` is unset, the provider defaults to `anthropic`. [PLANNED: OLS-3473] This default must be updated once the `anthropic` path is rerouted or removed.

5. **Model resolution.** `LIGHTSPEED_MODEL` is the canonical model input. The provider configuration mapping (rule 2) sets the SDK-specific model var (`ANTHROPIC_MODEL`, `GEMINI_MODEL`, or `OPENAI_MODEL`) from `LIGHTSPEED_MODEL`. SDK-specific model vars MAY also be read directly for backward compatibility when `LIGHTSPEED_MODEL` is unset; if all are unset, use the package default model constant.

6. **Router override.** Callers of the library `build_router` may pass an explicit `model` string; when provided, it overrides environment-based resolution for that router instance.

7. **Skills directory.** `LIGHTSPEED_SKILLS_DIR` sets the filesystem root for skills and provider `cwd`. Default when unset is the container default path under `/app`.

8. **Provider credentials.** API authentication uses the conventional env vars expected by each vendor SDK (Anthropic, Google/Gemini, OpenAI). These are populated from the credentials secret mounted via `envFrom` by the operator, and optionally from the file mount at `/var/run/secrets/llm-credentials/` for file-based credentials. The sandbox configuration mapping (rule 2) sets any additional credential-related env vars (e.g. `GOOGLE_APPLICATION_CREDENTIALS` path).

9. **Vertex / Google GenAI.** `GOOGLE_GENAI_USE_VERTEXAI` toggles Vertex behavior for the Gemini adapter (tool composition rules per `provider-contract.md`). Set by the configuration mapping when `LIGHTSPEED_PROVIDER=vertex` and `LIGHTSPEED_MODEL_PROVIDER=Google`.

10. **OpenAI base URL.** `OPENAI_BASE_URL` overrides the OpenAI client base URL when set. Mapped from `LIGHTSPEED_PROVIDER_URL` by the configuration mapping for `openai` and `vertex`/`OpenAI` providers.

11. **~~Claude via Vertex.~~** Removed. [PLANNED: OLS-3473] The `vertex/anthropic` path is pending rerouting to an alternative agentic SDK.

12. **Router defaults — `max_turns`.** The router supplies a built-in default maximum turn count to provider options when routes are registered (not exposed on `RunRequest`).

13. **Router defaults — `default_timeout_ms`.** The router supplies a built-in default milliseconds timeout for the run handler when `RunRequest.timeout_ms` is null.

14. **Process entry.** The container process invokes Uvicorn serving the FastAPI app on TCP port `8080` on all interfaces.

15. **Container filesystem layout.** `/app` is the agent workspace (skills and node_modules only). Application source lives at `/opt/lightspeed/src/`, outside the agent-visible tree to prevent context pollution. A read-only skills mount path, a writable per-pod workspace path under system temp, and a writable home directory path for the non-root runtime user are provisioned with ownership for that UID. LLM credential files are mounted read-only at `/var/run/secrets/llm-credentials/`.

16. **Python load path.** Runtime sets process environment so application source under `/opt/lightspeed/src` and installed site-packages are on `PYTHONPATH` as defined in the image.

17. **Hermetic / Konflux build inputs.** Release images are built with network isolation after prefetch: per-architecture Python requirements files with hashes, RPM lockfile input, and generic binary lockfile for oc/ripgrep. Regeneration of those artifacts is via the project automation commands (see implementation notes in `how/provider-architecture.md`). [PLANNED: OLS-3473] npm lockfile for Claude Code CLI removed.

18. **Non-hermetic fallback.** When prefetch directories are absent, the container build recipe may fetch selected binaries from external URLs for developer builds.

19. **System packages — minimum expectations.** Runtime image includes Bash, Git, OpenShift CLI (`oc`), Kubernetes CLI (`kubectl`), ripgrep, and supporting OS utilities for debugging and archives per the container recipe. [PLANNED: OLS-3473] Node.js removed — was only needed for Claude Code CLI.

20. **MCP server configuration.** When `LIGHTSPEED_MCP_SERVERS` is set, the sandbox MUST parse it as a JSON array of MCP server entries. Each entry has the shape `{"name": string, "url": string, "timeout": int, "headers": [{"name": string, "source": string, "secretName"?: string}]}`. The sandbox MUST build SDK-native MCP client configs from this array and pass them into provider adapters via `ProviderQueryOptions.mcp_servers` (see `provider-contract.md`). When the env var is absent or empty, no MCP servers are configured.

21. **MCP header resolution.** For each header in an MCP server entry, the sandbox MUST resolve the value based on the `source` field:

    | `source` | Resolution |
    |---|---|
    | `ServiceAccountToken` | Read the projected SA token from `/var/run/secrets/kubernetes.io/serviceaccount/token` and format as `Bearer <token>`. |
    | `Secret` | Read the first file from `/var/secrets/mcp/<secretName>/` where `secretName` is the `secretName` field on the header entry. |
    | `Client` | Skip — not resolved by the sandbox. Reserved for future client-passthrough flows. |

22. **MCP transport.** The sandbox MUST use Streamable HTTP as the MCP transport when connecting to remote MCP servers. SSE transport (deprecated in MCP spec since 2025-03-26) MUST NOT be used for new connections.

## Configuration Surface

| Variable / field | Role |
|------------------|------|
| `LIGHTSPEED_PROVIDER` | Hosting backend from operator (see rule 1). Replaces direct SDK selection. |
| `LIGHTSPEED_MODEL` | Model identifier from operator (see rule 1). |
| `LIGHTSPEED_MODEL_PROVIDER` | Model family on Vertex from operator (see rule 1). |
| `LIGHTSPEED_PROVIDER_URL` | Optional API endpoint override from operator (see rule 1). |
| `LIGHTSPEED_PROVIDER_PROJECT` | Cloud project ID from operator (see rule 1). |
| `LIGHTSPEED_PROVIDER_REGION` | Cloud region from operator (see rule 1). |
| `LIGHTSPEED_PROVIDER_API_VERSION` | API version from operator (see rule 1). |
| `GEMINI_MODEL`, `OPENAI_MODEL` | Internal: SDK-specific model vars. Set by configuration mapping (rule 2), not operator. |
| `LIGHTSPEED_SKILLS_DIR` | Skill root and provider working directory default. |
| `GOOGLE_API_KEY`, `GEMINI_API_KEY` | Google GenAI credential (from credentials secret envFrom). |
| `OPENAI_API_KEY` | OpenAI SDK credential (from credentials secret envFrom). |
| `GOOGLE_GENAI_USE_VERTEXAI` | Internal: Vertex mode for Gemini adapter. Set by configuration mapping. |
| `OPENAI_BASE_URL` | Internal: OpenAI-compatible endpoint. Set by configuration mapping. |
| `LIGHTSPEED_AUDIT_ENABLED` | Audit event logging toggle. Set by operator from `AgenticOLSConfig`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP gRPC endpoint for span export. Set by operator from `AgenticOLSConfig`. |
| `LIGHTSPEED_MCP_SERVERS` | JSON array of MCP server configs with URLs, timeouts, and header sources. Set by operator from `ToolsSpec.mcpServers` and auto-injected defaults. |
| `/var/run/secrets/llm-credentials/` | LLM credential files mounted by operator (unconditional). |
| `/var/run/secrets/kubernetes.io/serviceaccount/token` | Projected SA token for MCP `ServiceAccountToken` header resolution. |
| `/var/secrets/mcp/<secretName>/` | MCP header secret files mounted by operator for `Secret`-sourced headers. |
| `build_router(..., skills_dir=..., model=..., max_turns=..., default_timeout_ms=...)` | Library-level defaults when embedding the router. |

## Constraints

- `RunRequest` does not carry provider name, model, max turns, or budget; changing those requires env vars, router constructor args, or future API extensions.
- Optional Python extras gate which provider SDKs are installed in a given environment; the image recipe installs all extras.
- Bedrock previously assumed Claude SDK which is being removed. [PLANNED: OLS-3473] Bedrock path pending rerouting to an alternative agentic SDK. When Bedrock support for other model families is needed, a `modelProvider` field should be added to the `AWSBedrockConfig` CRD (similar to `googleCloudVertex.modelProvider`).

## Planned Changes

- Remove Claude SDK (`claude-agent-sdk`, `@anthropic-ai/claude-code` binary, Node.js runtime) from container image and all config paths. Reroute `anthropic`, `vertex/anthropic`, `bedrock` to alternative agentic SDKs. [PLANNED: OLS-3473]
- TLS termination, mTLS, and network policies for operator-to-sandbox traffic. [PLANNED: OLS-3038–OLS-3043]
- Konflux pipeline and lockfile policy updates as Red Hat platform requirements evolve. [PLANNED: OLS-2894]
- `Client` header source type resolution when client-passthrough MCP auth flows are implemented.
