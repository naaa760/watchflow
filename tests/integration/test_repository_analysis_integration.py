"""
Integration tests for repository analysis end-to-end flow.

Tests the complete flow from repository analysis request to rule generation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.repository_analysis_agent.agent import RepositoryAnalysisAgent
from src.agents.repository_analysis_agent.models import (
    ContributingGuidelinesAnalysis,
    PullRequestSample,
    RepositoryAnalysisRequest,
    RepositoryAnalysisState,
    RepositoryFeatures,
)


@pytest.mark.asyncio
class TestRepositoryAnalysisIntegration:
    """Integration tests for the complete repository analysis flow."""

    async def test_full_analysis_flow_python_repo(self):
        """Test complete analysis flow for a Python repository."""
        # Create a mock agent
        agent = RepositoryAnalysisAgent()

        with patch('src.agents.repository_analysis_agent.nodes.github_client') as mock_client:
            # Mock all the client methods used by the analysis
            mock_client.get_repository = AsyncMock(return_value={
                "language": "Python",
                "default_branch": "main"
            })

            mock_client.list_pull_requests = AsyncMock(return_value=[
                {
                    "number": 1,
                    "title": "Add new feature",
                    "state": "merged",
                    "merged_at": "2024-01-01T00:00:00Z",
                    "additions": 100,
                    "deletions": 10,
                    "changed_files": 5
                },
                {
                    "number": 2,
                    "title": "Fix bug",
                    "state": "merged",
                    "merged_at": "2024-01-02T00:00:00Z",
                    "additions": 20,
                    "deletions": 5,
                    "changed_files": 2
                }
            ])

            mock_client.get_file_content = AsyncMock(side_effect=lambda *args, **kwargs: {
                ("test/python-repo", "CONTRIBUTING.md"): """
                # Contributing Guidelines

                Please add tests for all new features.
                Follow PEP 8 style guidelines.
                """,
                ("test/python-repo", ".github/CONTRIBUTING.md"): None,
                ("test/python-repo", ".github/CODEOWNERS"): "CODEOWNERS content",
            }.get((args[0], args[1])))

            mock_client.list_directory_any_auth = AsyncMock(return_value=[
                {"name": "ci.yml"},
                {"name": "lint.yml"}
            ])

            mock_client.get_repository_contributors = AsyncMock(return_value=[
                {"login": "user1"},
                {"login": "user2"}
            ])

            # Execute the analysis
            request = RepositoryAnalysisRequest(
                repository_full_name="test/python-repo",
                installation_id=123,
                max_prs=10
            )

            result = await agent.execute(
                repository_full_name=request.repository_full_name,
                installation_id=request.installation_id
            )

            # Verify the result
            assert result.success is True
            assert "analysis_response" in result.data

            response = result.data["analysis_response"]

            # Check that rules were generated
            assert len(response.recommendations) >= 2  # At least test coverage and description rules

            # Check that rules YAML was generated
            assert "rules:" in response.rules_yaml
            assert "Require tests when code changes" in response.rules_yaml

            # Check analysis summary
            assert "repository_features" in response.analysis_summary
            assert response.analysis_summary["repository_features"]["language"] == "Python"

    async def test_analysis_with_no_contributing_guidelines(self):
        """Test analysis flow when repository has no contributing guidelines."""
        agent = RepositoryAnalysisAgent()

        with patch('src.agents.repository_analysis_agent.nodes.github_client') as mock_client:
            mock_client.get_repository = AsyncMock(return_value={
                "language": "JavaScript",
                "default_branch": "main"
            })

            mock_client.list_pull_requests = AsyncMock(return_value=[])
            mock_client.get_file_content = AsyncMock(return_value=None)  # No contributing file
            mock_client.list_directory_any_auth = AsyncMock(return_value=[])
            mock_client.get_repository_contributors = AsyncMock(return_value=[])

            request = RepositoryAnalysisRequest(
                repository_full_name="test/js-repo",
                installation_id=456,
                max_prs=5
            )

            result = await agent.execute(
                repository_full_name=request.repository_full_name,
                installation_id=request.installation_id
            )

            assert result.success is True
            response = result.data["analysis_response"]

            # Should still generate basic rules
            assert len(response.recommendations) >= 1
            assert "JavaScript" in response.analysis_summary["repository_features"]["language"]

    async def test_analysis_failure_handling(self):
        """Test that analysis handles failures gracefully."""
        agent = RepositoryAnalysisAgent()

        with patch('src.agents.repository_analysis_agent.nodes.github_client') as mock_client:
            # Mock repository fetch failure
            mock_client.get_repository = AsyncMock(return_value=None)

            request = RepositoryAnalysisRequest(
                repository_full_name="test/failing-repo",
                installation_id=789,
                max_prs=5
            )

            result = await agent.execute(
                repository_full_name=request.repository_full_name,
                installation_id=request.installation_id
            )

            # Should fail gracefully
            assert result.success is False
            assert "Could not fetch repository data" in result.message

    async def test_rules_contain_proper_patterns(self):
        """Test that generated rules contain appropriate language-specific patterns."""
        agent = RepositoryAnalysisAgent()

        with patch('src.agents.repository_analysis_agent.nodes.github_client') as mock_client:
            mock_client.get_repository = AsyncMock(return_value={
                "language": "Go",
                "default_branch": "main"
            })

            mock_client.list_pull_requests = AsyncMock(return_value=[])
            mock_client.get_file_content = AsyncMock(return_value=None)
            mock_client.list_directory_any_auth = AsyncMock(return_value=[])
            mock_client.get_repository_contributors = AsyncMock(return_value=[])

            request = RepositoryAnalysisRequest(
                repository_full_name="test/go-repo",
                installation_id=101,
                max_prs=5
            )

            result = await agent.execute(
                repository_full_name=request.repository_full_name,
                installation_id=request.installation_id
            )

            assert result.success is True
            response = result.data["analysis_response"]

            # Find the test coverage rule
            test_rule = None
            for rec in response.recommendations:
                if "Require tests when code changes" in rec.yaml_rule:
                    test_rule = rec
                    break

            assert test_rule is not None
            assert "**/*.go" in test_rule.yaml_rule
            assert "**/*_test.go" in test_rule.yaml_rule
