"""
Rule data structures and generators for Watchflow.

This module provides proper separation between:
- Rule data models (business logic)
- Rule generators (analysis-based recommendations)
- YAML formatters (presentation layer)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WatchflowRule(BaseModel):
    """Core Watchflow rule data structure - independent of YAML formatting."""

    description: str
    enabled: bool = True
    severity: Literal["low", "medium", "high", "critical"]
    event_types: list[str]
    parameters: dict[str, Any] = Field(default_factory=dict)


class TestCoverageRule(WatchflowRule):
    """Rule requiring tests when source code changes."""

    event_types: list[str] = Field(default_factory=lambda: ["pull_request"])
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    description: str = "Require tests when code changes"

    source_patterns: list[str] = Field(default_factory=list, description="Patterns matching source files")
    test_patterns: list[str] = Field(default_factory=list, description="Patterns matching test files")

    def __init__(self, source_patterns: list[str], test_patterns: list[str], **data):
        super().__init__(
            description="Require tests when code changes",
            parameters={
                "source_patterns": source_patterns,
                "test_patterns": test_patterns,
            },
            **data
        )
        self.source_patterns = source_patterns
        self.test_patterns = test_patterns


class DescriptionRule(WatchflowRule):
    """Rule requiring minimum PR description length."""

    event_types: list[str] = Field(default_factory=lambda: ["pull_request"])
    severity: Literal["low", "medium", "high", "critical"] = "low"
    description: str = "Ensure PRs include context"

    min_description_length: int = Field(default=50, description="Minimum characters required in PR body")

    def __init__(self, min_description_length: int = 50, **data):
        super().__init__(
            description="Ensure PRs include context",
            parameters={
                "min_description_length": min_description_length,
            },
            **data
        )
        self.min_description_length = min_description_length


class FileProtectionRule(WatchflowRule):
    """Rule protecting specific file patterns."""

    event_types: list[str] = Field(default_factory=lambda: ["pull_request"])
    severity: Literal["low", "medium", "high", "critical"] = "high"
    description: str = "Protect critical files"

    file_patterns: list[str] = Field(default_factory=list, description="Patterns of files to protect")

    def __init__(self, file_patterns: list[str], description: str, severity: str = "high", **data):
        super().__init__(
            description=description,
            severity=severity,
            parameters={
                "file_patterns": file_patterns,
            },
            **data
        )
        self.file_patterns = file_patterns


class RuleRecommendation(BaseModel):
    """A recommended rule with confidence and reasoning."""

    rule: WatchflowRule
    confidence: float = Field(description="Confidence score (0.0-1.0)", ge=0.0, le=1.0)
    reasoning: str = Field(description="Explanation of why this rule is recommended")
    strategy_used: str = Field(description="Strategy used (static, hybrid, llm)")


def to_yaml_rule(recommendation: RuleRecommendation) -> str:
    """Convert a rule recommendation to YAML format."""
    rule_dict = recommendation.rule.model_dump()

    # Convert to the expected YAML structure
    yaml_dict = {
        "description": rule_dict["description"],
        "enabled": rule_dict["enabled"],
        "severity": rule_dict["severity"],
        "event_types": rule_dict["event_types"],
        "parameters": rule_dict["parameters"],
    }

    import yaml
    return yaml.dump(yaml_dict, default_flow_style=False, sort_keys=False).strip()


def to_rules_yaml(recommendations: list[RuleRecommendation]) -> str:
    """Convert multiple recommendations to a complete rules YAML document."""
    import yaml

    rules_list = []
    for rec in recommendations:
        rule_dict = rec.rule.model_dump()
        rules_list.append({
            "description": rule_dict["description"],
            "enabled": rule_dict["enabled"],
            "severity": rule_dict["severity"],
            "event_types": rule_dict["event_types"],
            "parameters": rule_dict["parameters"],
        })

    return yaml.dump({"rules": rules_list}, default_flow_style=False, sort_keys=False)
