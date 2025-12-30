"""
Rule generators for Watchflow.

This module provides functions that generate rule recommendations based on
actual repository analysis, not hardcoded templates.
"""

from __future__ import annotations

from typing import Any

from .models import ContributingGuidelinesAnalysis, RepositoryAnalysisState, RepositoryFeatures
from .rules import DescriptionRule, FileProtectionRule, RuleRecommendation, TestCoverageRule


def get_language_patterns(language: str | None) -> tuple[list[str], list[str]]:
    """
    Get source and test patterns based on repository language.

    This is a more comprehensive mapping than the simple one before.
    """
    patterns_map = {
        "Python": (
            ["**/*.py", "**/*.pyx"],
            ["**/tests/**", "**/*_test.py", "**/test_*.py", "**/*.test.py", "**/test.py"],
        ),
        "TypeScript": (
            ["**/*.ts", "**/*.tsx"],
            ["**/*.spec.ts", "**/*.test.ts", "**/*.spec.tsx", "**/*.test.tsx", "**/tests/**"],
        ),
        "JavaScript": (
            ["**/*.js", "**/*.jsx", "**/*.mjs", "**/*.cjs"],
            ["**/*.test.js", "**/*.spec.js", "**/*.test.jsx", "**/*.spec.jsx", "**/tests/**"],
        ),
        "Go": (
            ["**/*.go"],
            ["**/*_test.go", "**/*.test.go", "**/tests/**"],
        ),
        "Java": (
            ["**/*.java", "**/*.kt", "**/*.scala"],
            ["**/*Test.java", "**/*Tests.java", "**/*Test.kt", "**/test/**", "**/tests/**"],
        ),
        "Rust": (
            ["**/*.rs"],
            ["**/*_test.rs", "**/*.test.rs", "**/tests/**"],
        ),
        "C++": (
            ["**/*.cpp", "**/*.cc", "**/*.cxx", "**/*.c++", "**/*.hpp", "**/*.hxx"],
            ["**/tests/**", "**/*_test.cpp", "**/*_test.h", "**/test_*.cpp"],
        ),
        "C": (
            ["**/*.c", "**/*.h"],
            ["**/tests/**", "**/*_test.c", "**/test_*.c"],
        ),
        "Ruby": (
            ["**/*.rb"],
            ["**/test/**", "**/spec/**", "**/*_test.rb", "**/*_spec.rb"],
        ),
        "PHP": (
            ["**/*.php"],
            ["**/tests/**", "**/*Test.php", "**/*TestCase.php"],
        ),
    }

    if language and language in patterns_map:
        return patterns_map[language]

    # Default fallback for unknown languages
    return (
        ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.js", "**/*.go", "**/*.java", "**/*.rs"],
        ["**/tests/**", "**/*_test.*", "**/test_*.**", "**/*.test.*", "**/*.spec.*"],
    )


def analyze_pr_bad_habits(state: RepositoryAnalysisState) -> dict[str, Any]:
    """
    Analyze PR history to detect bad habits and patterns.

    Returns metrics about PR quality issues.
    """
    if not state.pr_samples:
        return {"total_analyzed": 0, "missing_tests": 0, "short_titles": 0, "large_prs": 0}

    issues = {
        "total_analyzed": len(state.pr_samples),
        "missing_tests": 0,
        "short_titles": 0,
        "large_prs": 0,
    }

    for pr in state.pr_samples:
        # Short titles (likely missing context)
        if pr.title and len(pr.title.strip()) < 15:  # Increased threshold for better detection
            issues["short_titles"] += 1

        # Large PRs (too many changes, hard to review)
        total_changes = (pr.additions or 0) + (pr.deletions or 0)
        if total_changes > 500:  # Large PR threshold
            issues["large_prs"] += 1

        # Estimate missing tests based on patterns
        # This is still heuristic but more sophisticated
        if pr.changed_files and pr.changed_files > 0:
            title_lower = (pr.title or "").lower()
            # Check for test-related keywords in title
            has_test_keywords = any(word in title_lower for word in [
                "test", "tests", "tested", "testing", "spec", "specs",
                "fixture", "mock", "assert", "coverage"
            ])
            # If PR changes many files but no test keywords, likely missing tests
            if pr.changed_files > 3 and not has_test_keywords:
                issues["missing_tests"] += 1

    return issues


def generate_test_coverage_rule(
    language: str | None,
    pr_issues: dict[str, Any],
    contributing: ContributingGuidelinesAnalysis
) -> RuleRecommendation:
    """Generate a test coverage rule based on repository analysis."""

    source_patterns, test_patterns = get_language_patterns(language)

    # Calculate confidence based on evidence
    confidence = 0.7  # Base confidence for requiring tests

    reasoning_parts = [f"Repository uses {language or 'multiple languages'}"]

    # Boost confidence if we detect test issues
    if pr_issues.get("missing_tests", 0) > 0:
        confidence += 0.15
        reasoning_parts.append(f"found {pr_issues['missing_tests']} PRs lacking test coverage")

    # Boost confidence if contributing guidelines require tests
    if contributing.content and contributing.requires_tests:
        confidence += 0.1
        reasoning_parts.append("contributing guidelines require tests")

    # Cap confidence
    confidence = min(0.95, confidence)

    reasoning = ". ".join(reasoning_parts) + "."

    rule = TestCoverageRule(
        source_patterns=source_patterns,
        test_patterns=test_patterns
    )

    return RuleRecommendation(
        rule=rule,
        confidence=confidence,
        reasoning=reasoning,
        strategy_used="hybrid"
    )


def generate_description_rule(pr_issues: dict[str, Any]) -> RuleRecommendation:
    """Generate a PR description requirement rule."""

    confidence = 0.65  # Base confidence
    reasoning = "Encourages better PR context for reviewers"

    if pr_issues.get("short_titles", 0) > 0:
        confidence += 0.15
        reasoning = f"Detected {pr_issues['short_titles']} PRs with inadequate titles. Requires detailed descriptions."

    rule = DescriptionRule(min_description_length=50)

    return RuleRecommendation(
        rule=rule,
        confidence=min(0.9, confidence),
        reasoning=reasoning,
        strategy_used="static" if confidence < 0.75 else "hybrid"
    )


def generate_file_protection_rules(features: RepositoryFeatures) -> list[RuleRecommendation]:
    """Generate rules to protect critical repository files."""

    recommendations = []

    # Protect CI/CD workflows
    if features.has_workflows:
        rule = FileProtectionRule(
            file_patterns=[".github/workflows/**"],
            description="Protect CI/CD workflows",
            severity="high"
        )
        recommendations.append(RuleRecommendation(
            rule=rule,
            confidence=0.9,
            reasoning=f"Repository has {features.workflow_count} CI/CD workflows that need protection",
            strategy_used="static"
        ))

    # Protect CODEOWNERS if present
    if features.has_codeowners:
        rule = FileProtectionRule(
            file_patterns=[".github/CODEOWNERS", "CODEOWNERS"],
            description="Protect CODEOWNERS file",
            severity="medium"
        )
        recommendations.append(RuleRecommendation(
            rule=rule,
            confidence=0.8,
            reasoning="CODEOWNERS file defines review requirements and should be protected",
            strategy_used="static"
        ))

    # Protect security-related files
    security_patterns = ["**/*.key", "**/*.pem", "**/*.crt", "**/secrets/**", "**/*.env"]
    rule = FileProtectionRule(
        file_patterns=security_patterns,
        description="Prevent accidental commits of secrets",
        severity="critical"
    )
    recommendations.append(RuleRecommendation(
        rule=rule,
        confidence=0.85,
        reasoning="Prevents accidental exposure of credentials and secrets",
        strategy_used="static"
    ))

    return recommendations


def generate_recommendations(state: RepositoryAnalysisState) -> list[RuleRecommendation]:
    """
    Generate rule recommendations based on comprehensive repository analysis.

    This function analyzes:
    - Repository language and structure
    - PR history patterns
    - Contributing guidelines
    - Repository features (workflows, CODEOWNERS, etc.)
    """
    recommendations = []

    # Analyze PR patterns
    pr_issues = analyze_pr_bad_habits(state)

    # Always recommend test coverage (customized by language)
    test_rule = generate_test_coverage_rule(
        state.repository_features.language,
        pr_issues,
        state.contributing_analysis
    )
    recommendations.append(test_rule)

    # Recommend description requirements if PR quality issues detected
    if pr_issues.get("short_titles", 0) > 0 or pr_issues.get("total_analyzed", 0) >= 3:
        desc_rule = generate_description_rule(pr_issues)
        recommendations.append(desc_rule)

    # Add file protection rules based on repository features
    file_rules = generate_file_protection_rules(state.repository_features)
    recommendations.extend(file_rules)

    return recommendations

