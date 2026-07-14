"""Unit tests for schema conditional constraints."""

from __future__ import annotations

import jsonschema
import pytest

from .schemas import ANALYSIS_WITH_COMPONENTS_SCHEMA

_MINIMAL_OPTION: dict = {
    "title": "Fix it",
    "diagnosis": {
        "summary": "s",
        "confidence": "high",
        "rootCause": "r",
        "token": "t",
    },
    "remediationPlan": {
        "description": "d",
        "actions": [{"type": "t", "description": "d"}],
        "risk": "low",
        "reversible": True,
    },
    "verification": {"description": "d"},
    "rbac": {},
    "components": [
        {
            "type": "t",
            "source": {"generator": "g", "timestamp": "ts"},
            "tokens": {
                "primary": {"value": "v", "valid": True},
                "secondary": {"value": "v", "valid": True},
            },
            "audit": {
                "outcome": "pass",
                "checks_performed": ["c"],
                "findings": [{"check": "c", "result": "r", "severity": "info"}],
            },
        }
    ],
}

_DIAGNOSIS: dict = {"summary": "s", "confidence": "high", "rootCause": "r"}


def test_action_required_true_with_options():
    doc = {"actionRequired": True, "options": [_MINIMAL_OPTION]}
    jsonschema.validate(doc, ANALYSIS_WITH_COMPONENTS_SCHEMA)


def test_action_required_false_with_diagnosis():
    doc = {"actionRequired": False, "options": [], "diagnosis": _DIAGNOSIS}
    jsonschema.validate(doc, ANALYSIS_WITH_COMPONENTS_SCHEMA)


def test_action_required_false_rejects_missing_diagnosis():
    doc = {"actionRequired": False, "options": []}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, ANALYSIS_WITH_COMPONENTS_SCHEMA)


def test_action_required_true_rejects_empty_options():
    doc = {"actionRequired": True, "options": []}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, ANALYSIS_WITH_COMPONENTS_SCHEMA)
