"""JSON Schema definitions for eval tests.

The ANALYSIS_WITH_COMPONENTS_SCHEMA is a best-effort approximation of the
operator's AnalysisOutputSchema with a components array injected at
options[].components — matching how mergeAgentOutputSchema works in
lightspeed-agentic-operator/controller/agenticrun/schemas.go.

Intentional divergences from the operator schema (eval-specific):
  - reversible is boolean here vs enum (Reversible/Irreversible/Partial) in CRD
  - enum values are lowercase here vs title-case in the CRD
  - diagnosis/components include token sentinels for eval verification

Aligned with operator schema: openshift/lightspeed-agentic-operator#162
Updated for OLS-3422: added top-level actionRequired + diagnosis, options minItems 0
"""

from __future__ import annotations

from typing import Any

ANALYSIS_WITH_COMPONENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "actionRequired": {
            "type": "boolean",
            "description": (
                "Whether remediation action is required."
                " Set to false when the issue is a false alarm or already self-healed."
            ),
        },
        "diagnosis": {
            "type": "object",
            "description": "Top-level root cause analysis. Required when actionRequired is false.",
            "properties": {
                "summary": {"type": "string"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "rootCause": {"type": "string"},
            },
            "required": ["summary", "confidence", "rootCause"],
        },
        "options": {
            "type": "array",
            "minItems": 0,
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "diagnosis": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                            "rootCause": {"type": "string"},
                            "token": {"type": "string"},
                        },
                        "required": ["summary", "confidence", "rootCause", "token"],
                    },
                    "remediationPlan": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "actions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["type", "description"],
                                },
                            },
                            "risk": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "critical"],
                            },
                            "reversible": {"type": "boolean"},
                        },
                        "required": ["description", "actions", "risk", "reversible"],
                    },
                    "verification": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "token": {"type": "string"},
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "command": {"type": "string"},
                                        "expected": {"type": "string"},
                                        "type": {"type": "string"},
                                    },
                                    "required": ["name", "type"],
                                },
                            },
                            "rollbackPlan": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string"},
                                    "command": {"type": "string"},
                                },
                            },
                        },
                        "required": ["description"],
                    },
                    "rbac": {
                        "type": "object",
                        "properties": {
                            "namespaceScoped": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "namespace": {"type": "string"},
                                        "apiGroups": {"type": "array", "items": {"type": "string"}},
                                        "resources": {"type": "array", "items": {"type": "string"}},
                                        "resourceNames": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "verbs": {"type": "array", "items": {"type": "string"}},
                                        "justification": {"type": "string"},
                                    },
                                    "required": [
                                        "apiGroups",
                                        "resources",
                                        "verbs",
                                        "justification",
                                    ],
                                },
                            },
                            "clusterScoped": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "apiGroups": {"type": "array", "items": {"type": "string"}},
                                        "resources": {"type": "array", "items": {"type": "string"}},
                                        "resourceNames": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "verbs": {"type": "array", "items": {"type": "string"}},
                                        "justification": {"type": "string"},
                                    },
                                    "required": [
                                        "apiGroups",
                                        "resources",
                                        "verbs",
                                        "justification",
                                    ],
                                },
                            },
                        },
                    },
                    "components": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "source": {
                                    "type": "object",
                                    "properties": {
                                        "generator": {"type": "string"},
                                        "timestamp": {"type": "string"},
                                        "entropy_bits": {"type": "integer"},
                                    },
                                    "required": ["generator", "timestamp"],
                                },
                                "tokens": {
                                    "type": "object",
                                    "properties": {
                                        "primary": {
                                            "type": "object",
                                            "properties": {
                                                "value": {"type": "string"},
                                                "algorithm": {"type": "string"},
                                                "valid": {"type": "boolean"},
                                            },
                                            "required": ["value", "valid"],
                                        },
                                        "secondary": {
                                            "type": "object",
                                            "properties": {
                                                "value": {"type": "string"},
                                                "algorithm": {"type": "string"},
                                                "valid": {"type": "boolean"},
                                            },
                                            "required": ["value", "valid"],
                                        },
                                    },
                                    "required": ["primary", "secondary"],
                                },
                                "audit": {
                                    "type": "object",
                                    "properties": {
                                        "outcome": {
                                            "type": "string",
                                            "enum": ["pass", "fail", "partial"],
                                        },
                                        "checks_performed": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "findings": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "check": {"type": "string"},
                                                    "result": {"type": "string"},
                                                    "severity": {
                                                        "type": "string",
                                                        "enum": ["info", "warning", "critical"],
                                                    },
                                                    "detail": {"type": "string"},
                                                },
                                                "required": ["check", "result", "severity"],
                                            },
                                        },
                                    },
                                    "required": ["outcome", "checks_performed", "findings"],
                                },
                            },
                            "required": ["type", "source", "tokens", "audit"],
                        },
                    },
                },
                "required": [
                    "title",
                    "diagnosis",
                    "remediationPlan",
                    "rbac",
                    "verification",
                    "components",
                ],
            },
        },
    },
    "required": ["actionRequired", "options"],
    "allOf": [
        {
            "if": {
                "properties": {"actionRequired": {"const": False}},
                "required": ["actionRequired"],
            },
            "then": {
                "required": ["actionRequired", "options", "diagnosis"],
                "properties": {"options": {"maxItems": 0}},
            },
            "else": {
                "properties": {"options": {"minItems": 1}},
            },
        },
    ],
}
