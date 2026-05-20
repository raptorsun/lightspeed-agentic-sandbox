# Evals

End-to-end evaluations that test the `/v1/agent/run` HTTP endpoint against live production containers — matching how the operator invokes the agent in production.

> **Note:** On macOS, the eval suite runs 3 containers in parallel. Ensure the podman machine has at least 8GB: check with `podman info | grep memTotal`, resize with `podman machine set --memory 8192`.

## Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Providers & Models](#providers--models)
- [Credentials](#credentials)
- [Running Evals](#running-evals)
- [Reports](#reports)
- [Adding Skills & Tools](#adding-skills--tools)

## Quick Start

```bash
make eval
```

This builds the production container image, starts 3 live servers (one per provider), runs `test_find_token_skill` against each via HTTP, and tears everything down.

## How It Works

One test (`test_find_token_skill`) validates the entire stack in a single pass:

1. **Skill discovery** — the model is asked to "Find the hidden token using the 'find-token' skill." Each provider's SDK discovers `SKILL.md` from the workspace using its native mechanism.
2. **Tool execution** — the SKILL.md instructs the model to run `find-token.sh`, which generates two random tokens (`DIAG_*`, `VERIFY_*`) and writes them to a `.hidden_token` file on a shared volume.
3. **Complex structured output** — the response must conform to `ANALYSIS_WITH_COMPONENTS_SCHEMA`, which mirrors the operator's `AnalysisOutputSchema` with components: nested objects, arrays, enums, booleans, 4 levels deep.
4. **Token verification** — the test reads `.hidden_token` from the shared volume and verifies both tokens appear in the model's JSON response. The tokens are random per invocation — the model cannot produce them without executing the script.

No prompt hacks, no begging for output format, no telling the model what command to run. The output schema is enforced by each provider's native mechanism.

## Providers & Models

| Provider | Default Model | Override Env Var |
|---|---|---|
| `claude` | `claude-sonnet-4-6` | `ANTHROPIC_MODEL` |
| `gemini` | `gemini-3.1-pro-preview` | `GEMINI_MODEL` |
| `openai` | `gpt-5.4` | `OPENAI_MODEL` |

## Credentials

Providers without valid credentials are automatically skipped.

| Provider | Primary | Fallbacks |
|---|---|---|
| `claude` | `ANTHROPIC_API_KEY` | Vertex AI (`CLAUDE_CODE_USE_VERTEX=1` + gcloud ADC), Bedrock (`CLAUDE_CODE_USE_BEDROCK=1` + AWS creds) |
| `gemini` | `GOOGLE_API_KEY` | `GEMINI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS` file, gcloud ADC |
| `openai` | `OPENAI_API_KEY` | `OPENAI_BASE_URL` (keyless endpoints) |

## Running Evals

`evals/run.sh` starts 3 containers, waits for `/health`, runs pytest against them via HTTP, then tears down. Use `EVAL_ARGS` to pass pytest flags.

```bash
# All providers
make eval

# Single provider
make eval EVAL_ARGS="-k claude"

# Override model for a run
ANTHROPIC_MODEL=claude-opus-4-6 make eval EVAL_ARGS="-k claude"

# Verbose with stdout (debugging)
make eval EVAL_ARGS="-s"
```

## Reports

Generate a JSON report at `evals/report.json`:

```bash
make eval-report
```

## Adding Skills & Tools

```
evals/workspace/
├── skills/
│   └── find-token/
│       ├── SKILL.md              # skill description + usage
│       └── tools/
│           └── find-token.sh     # tool script (co-located with skill)
└── tools/
    └── find-token.sh             # tool script (workspace root)
```

- **Skills** — add a `SKILL.md` under `workspace/skills/<name>/`. Each provider's SDK discovers and loads them automatically. Co-locate tool scripts in `tools/` within the skill directory.
- **Tools** — bash scripts that generate random verification tokens, write them to dot-files on the shared volume, and return structured JSON. The test reads the dot-files to verify the model actually executed the script.
- **Schemas** — JSON Schema dicts in `schemas.py`, passed as `outputSchema` to the `/run` endpoint. The provider enforces structured output using its native mechanism.

Tests are parametrized across all 3 providers automatically.
