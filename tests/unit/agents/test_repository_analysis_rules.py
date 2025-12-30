"""
Tests for repository analysis rule generation.

Tests the new separated architecture with proper data models and generators.
"""

import pytest
from pydantic import ValidationError

from src.agents.repository_analysis_agent.generators import (
    analyze_pr_bad_habits,
    generate_description_rule,
    generate_file_protection_rules,
    generate_recommendations,
    generate_test_coverage_rule,
    get_language_patterns,
)
from src.agents.repository_analysis_agent.models import (
    ContributingGuidelinesAnalysis,
    PullRequestSample,
    RepositoryAnalysisState,
    RepositoryFeatures,
)
from src.agents.repository_analysis_agent.rules import (
    DescriptionRule,
    FileProtectionRule,
    RuleRecommendation,
    TestCoverageRule,
    to_rules_yaml,
    to_yaml_rule,
)


class TestLanguagePatterns:
    """Test language-specific pattern generation."""

    def test_python_patterns(self):
        """Test Python language patterns."""
        source, test = get_language_patterns("Python")
        assert "**/*.py" in source
        assert "**/*.pyx" in source
        assert "**/tests/**" in test
        assert "**/*_test.py" in test

    def test_typescript_patterns(self):
        """Test TypeScript language patterns."""
        source, test = get_language_patterns("TypeScript")
        assert "**/*.ts" in source
        assert "**/*.tsx" in source
        assert "**/*.spec.ts" in test
        assert "**/*.test.ts" in test

    def test_unknown_language_patterns(self):
        """Test fallback patterns for unknown languages."""
        source, test = get_language_patterns(None)
        assert "**/*.py" in source
        assert "**/*.js" in source
        assert "**/tests/**" in test
        assert "**/*_test.*" in test


class TestPrAnalysis:
    """Test PR habit analysis."""

    def test_analyze_pr_bad_habits_no_prs(self):
        """Test analysis with no PRs."""
        state = RepositoryAnalysisState(repository_full_name="test/repo", installation_id=123)
        result = analyze_pr_bad_habits(state)
        assert result["total_analyzed"] == 0
        assert result["missing_tests"] == 0

    def test_analyze_pr_bad_habits_with_prs(self):
        """Test analysis with PR samples."""
        pr1 = PullRequestSample(
            number=1,
            title="Add new feature",
            state="merged",
            merged=True,
            additions=100,
            deletions=10,
            changed_files=5
        )
        pr2 = PullRequestSample(
            number=2,
            title="Fix test coverage",
            state="merged",
            merged=True,
            additions=50,
            deletions=5,
            changed_files=3
        )

        state = RepositoryAnalysisState(
            repository_full_name="test/repo",
            installation_id=123,
            pr_samples=[pr1, pr2]
        )

        result = analyze_pr_bad_habits(state)
        assert result["total_analyzed"] == 2
        assert result["missing_tests"] >= 0  # May detect missing tests


class TestRuleGeneration:
    """Test individual rule generation functions."""

    def test_generate_test_coverage_rule_python(self):
        """Test test coverage rule generation for Python."""
        pr_issues = {"missing_tests": 1, "total_analyzed": 5}
        contributing = ContributingGuidelinesAnalysis(content="Please add tests")

        recommendation = generate_test_coverage_rule("Python", pr_issues, contributing)

        assert isinstance(recommendation, RuleRecommendation)
        assert isinstance(recommendation.rule, TestCoverageRule)
        assert recommendation.confidence > 0.7
        assert "**/*.py" in recommendation.rule.source_patterns

    def test_generate_description_rule_with_issues(self):
        """Test description rule generation when PR issues detected."""
        pr_issues = {"short_titles": 2, "total_analyzed": 5}

        recommendation = generate_description_rule(pr_issues)

        assert isinstance(recommendation, RuleRecommendation)
        assert isinstance(recommendation.rule, DescriptionRule)
        assert recommendation.confidence > 0.7
        assert "inadequate titles" in recommendation.reasoning.lower()

    def test_generate_file_protection_rules(self):
        """Test file protection rule generation."""
        features = RepositoryFeatures(
            has_workflows=True,
            has_codeowners=True,
            workflow_count=3
        )

        recommendations = generate_file_protection_rules(features)

        assert len(recommendations) >= 2  # workflows + codeowners
        workflow_rule = next(r for r in recommendations if "workflows" in r.reasoning.lower())
        assert isinstance(workflow_rule.rule, FileProtectionRule)
        assert ".github/workflows/**" in workflow_rule.rule.file_patterns

    def test_generate_recommendations_complete(self):
        """Test complete recommendation generation."""
        pr_samples = [
            PullRequestSample(
                number=1,
                title="Add feature",
                state="merged",
                merged=True,
                additions=100,
                deletions=10,
                changed_files=5
            )
        ]

        state = RepositoryAnalysisState(
            repository_full_name="test/repo",
            installation_id=123,
            repository_features=RepositoryFeatures(language="Python", has_workflows=True),
            pr_samples=pr_samples,
            contributing_analysis=ContributingGuidelinesAnalysis(
                content="Add tests for all features",
                requires_tests=True
            )
        )

        recommendations = generate_recommendations(state)

        assert len(recommendations) >= 2  # test coverage + file protection
        assert any(isinstance(r.rule, TestCoverageRule) for r in recommendations)
        assert any(isinstance(r.rule, FileProtectionRule) for r in recommendations)


class TestYamlGeneration:
    """Test YAML generation from rule objects."""

    def test_to_yaml_rule_test_coverage(self):
        """Test YAML generation for test coverage rule."""
        rule = TestCoverageRule(
            source_patterns=["**/*.py", "**/*.js"],
            test_patterns=["**/tests/**", "**/*_test.py"]
        )

        recommendation = RuleRecommendation(
            rule=rule,
            confidence=0.8,
            reasoning="Based on repository analysis",
            strategy_used="hybrid"
        )

        yaml_content = to_yaml_rule(recommendation)

        assert "description: Require tests when code changes" in yaml_content
        assert "source_patterns:" in yaml_content
        assert "- '**/*.py'" in yaml_content
        assert "test_patterns:" in yaml_content
        assert "- '**/tests/**'" in yaml_content

    def test_to_yaml_rule_file_protection(self):
        """Test YAML generation for file protection rule."""
        rule = FileProtectionRule(
            file_patterns=[".github/workflows/**"],
            description="Protect CI/CD workflows",
            severity="high"
        )

        recommendation = RuleRecommendation(
            rule=rule,
            confidence=0.9,
            reasoning="Repository has workflows",
            strategy_used="static"
        )

        yaml_content = to_yaml_rule(recommendation)

        assert "description: Protect CI/CD workflows" in yaml_content
        assert "severity: high" in yaml_content
        assert "file_patterns:" in yaml_content
        assert "- .github/workflows/**" in yaml_content

    def test_to_rules_yaml_multiple_rules(self):
        """Test complete rules YAML generation."""
        rule1 = TestCoverageRule(
            source_patterns=["**/*.py"],
            test_patterns=["**/tests/**"]
        )
        rule2 = DescriptionRule(min_description_length=50)

        recommendations = [
            RuleRecommendation(rule=rule1, confidence=0.8, reasoning="test", strategy_used="hybrid"),
            RuleRecommendation(rule=rule2, confidence=0.7, reasoning="desc", strategy_used="static")
        ]

        yaml_content = to_rules_yaml(recommendations)

        assert "rules:" in yaml_content
        assert "Require tests when code changes" in yaml_content
        assert "Ensure PRs include context" in yaml_content


class TestRuleValidation:
    """Test rule object validation."""

    def test_test_coverage_rule_validation(self):
        """Test TestCoverageRule validation."""
        # Valid rule
        rule = TestCoverageRule(
            source_patterns=["**/*.py"],
            test_patterns=["**/tests/**"]
        )
        assert rule.source_patterns == ["**/*.py"]
        assert rule.test_patterns == ["**/tests/**"]

        # Invalid confidence
        with pytest.raises(ValidationError):
            RuleRecommendation(
                rule=rule,
                confidence=1.5,  # Invalid
                reasoning="test",
                strategy_used="hybrid"
            )

    def test_file_protection_rule_validation(self):
        """Test FileProtectionRule validation."""
        rule = FileProtectionRule(
            file_patterns=["**/*.key"],
            description="Protect secrets",
            severity="critical"
        )
        assert rule.severity == "critical"
        assert rule.file_patterns == ["**/*.key"]
