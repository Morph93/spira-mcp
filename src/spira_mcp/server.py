"""Spira MCP Server — tools for Inflectra Spira with proper filtering and pagination.

Fixes over mcp-server-spira:
- Tasks filtered by their OWN release, not their parent requirement's release
- Proper pagination on all endpoints (no hardcoded 500 row limits)
- POST /search endpoints used for server-side filtering (requirements, incidents, test cases)
- Single-item retrieval for all artifact types
- Retry logic with backoff
- Clean markdown formatting
"""

import os
import sys

from mcp.server.fastmcp import FastMCP

from spira_mcp.client import SpiraClient, SpiraApiError
from spira_mcp import formatters

mcp = FastMCP(
    "spira-mcp",
    instructions="MCP server for Inflectra Spira with proper task filtering and pagination",
)


def _get_client():
    """Create a SpiraClient from environment variables."""
    base_url = os.environ.get("INFLECTRA_SPIRA_BASE_URL")
    username = os.environ.get("INFLECTRA_SPIRA_USERNAME")
    api_key = os.environ.get("INFLECTRA_SPIRA_API_KEY")

    missing = []
    if not base_url:
        missing.append("INFLECTRA_SPIRA_BASE_URL")
    if not username:
        missing.append("INFLECTRA_SPIRA_USERNAME")
    if not api_key:
        missing.append("INFLECTRA_SPIRA_API_KEY")

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return SpiraClient(base_url, username, api_key)


# ──────────────────────────────────────────────
#  Products
# ──────────────────────────────────────────────

@mcp.tool()
def list_products() -> str:
    """List all Spira products/projects accessible to the current user."""
    client = _get_client()
    products = client.get_products()
    return formatters.format_products(products)


@mcp.tool()
def get_product(product_id: int) -> str:
    """Get details of a specific Spira product by ID."""
    client = _get_client()
    product = client.get_product(product_id)
    return formatters.format_product(product)


# ──────────────────────────────────────────────
#  Releases / Sprints
# ──────────────────────────────────────────────

@mcp.tool()
def list_releases(product_id: int, active_only: bool = True) -> str:
    """List releases/sprints for a product. Set active_only=False to include completed/closed releases."""
    client = _get_client()
    releases = client.get_releases(product_id, active_only=active_only)
    return formatters.format_releases(releases)


@mcp.tool()
def get_release(product_id: int, release_id: int) -> str:
    """Get details of a specific release/sprint."""
    client = _get_client()
    release = client.get_release(product_id, release_id)
    return formatters.format_release(release)


# ──────────────────────────────────────────────
#  Requirements
# ──────────────────────────────────────────────

@mcp.tool()
def list_requirements(
    product_id: int,
    release_id: int | None = None,
    status_id: int | None = None,
    importance_id: int | None = None,
    owner_id: int | None = None,
) -> str:
    """List requirements for a product with optional filters.

    Filters (all optional):
    - release_id: Filter by release/sprint the requirement is assigned to
    - status_id: Filter by status (1=Requested, 2=Planned, 3=In Progress, 4=Developed, 5=Accepted, 6=Rejected, 7=Under Review, 8=Obsolete, 9=Tested, 10=Completed)
    - importance_id: Filter by importance (1=Critical, 2=High, 3=Medium, 4=Low)
    - owner_id: Filter by owner user ID
    """
    client = _get_client()
    requirements = client.get_requirements(
        product_id,
        release_id=release_id,
        status_id=status_id,
        importance_id=importance_id,
        owner_id=owner_id,
    )
    return formatters.format_requirements(requirements)


@mcp.tool()
def get_requirement(product_id: int, requirement_id: int) -> str:
    """Get a single requirement with its details, steps, and child requirements."""
    client = _get_client()
    req = client.get_requirement(product_id, requirement_id)
    children = client.get_requirement_children(product_id, requirement_id)
    steps = client.get_requirement_steps(product_id, requirement_id)
    return formatters.format_requirement(req, children=children, steps=steps)


# ──────────────────────────────────────────────
#  Tasks — THE KEY FIX
# ──────────────────────────────────────────────

@mcp.tool()
def list_tasks(
    product_id: int,
    release_id: int | None = None,
    status_id: int | None = None,
    owner_id: int | None = None,
) -> str:
    """List tasks for a product with optional filters.

    IMPORTANT: Unlike mcp-server-spira, this filters by the TASK's own release
    assignment, not its parent requirement's release. Tasks without a requirement,
    or with a requirement assigned to a different sprint, will still be found if
    the task itself is assigned to the specified release.

    Filters (all optional):
    - release_id: Filter by the task's own release/sprint assignment
    - status_id: Filter by status (1=Not Started, 2=In Progress, 3=Completed, 4=Blocked, 5=Deferred)
    - owner_id: Filter by owner user ID
    """
    client = _get_client()
    tasks = client.get_tasks(
        product_id,
        release_id=release_id,
        status_id=status_id,
        owner_id=owner_id,
    )
    return formatters.format_tasks(tasks)


@mcp.tool()
def get_task(product_id: int, task_id: int) -> str:
    """Get a single task by ID with full details."""
    client = _get_client()
    task = client.get_task(product_id, task_id)
    return formatters.format_task(task)


@mcp.tool()
def count_tasks(product_id: int, release_id: int | None = None, status_id: int | None = None) -> str:
    """Get a count of tasks matching filters. Uses server-side filtering (fast, no data transfer).

    Useful to check how many tasks exist before fetching them all.
    """
    client = _get_client()
    count = client.count_tasks(product_id, release_id=release_id, status_id=status_id)
    parts = [f"Task count for PR:{product_id}"]
    if release_id:
        parts.append(f"release RL:{release_id}")
    if status_id:
        parts.append(f"status #{status_id}")
    return f"{' | '.join(parts)}: **{count}**"


# ──────────────────────────────────────────────
#  Incidents
# ──────────────────────────────────────────────

@mcp.tool()
def list_incidents(
    product_id: int,
    release_id: int | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    severity_id: int | None = None,
    owner_id: int | None = None,
) -> str:
    """List incidents for a product with optional filters.

    Filters (all optional):
    - release_id: Filter by detected release
    - status_id: Filter by incident status
    - priority_id: Filter by priority (1=Critical, 2=High, 3=Medium, 4=Low)
    - severity_id: Filter by severity (1=Critical, 2=High, 3=Medium, 4=Low)
    - owner_id: Filter by owner user ID
    """
    client = _get_client()
    incidents = client.get_incidents(
        product_id,
        release_id=release_id,
        status_id=status_id,
        priority_id=priority_id,
        severity_id=severity_id,
        owner_id=owner_id,
    )
    return formatters.format_incidents(incidents)


@mcp.tool()
def get_incident(product_id: int, incident_id: int) -> str:
    """Get a single incident by ID with full details."""
    client = _get_client()
    incident = client.get_incident(product_id, incident_id)
    return formatters.format_incident(incident)


# ──────────────────────────────────────────────
#  Test Cases
# ──────────────────────────────────────────────

@mcp.tool()
def list_test_cases(product_id: int, release_id: int | None = None) -> str:
    """List test cases for a product, optionally filtered by release.

    - release_id: Filter to test cases mapped to this release/sprint
    """
    client = _get_client()
    if release_id:
        test_cases = client.get_test_cases_by_release(product_id, release_id)
    else:
        test_cases = client.get_test_cases(product_id)
    return formatters.format_test_cases(test_cases)


@mcp.tool()
def get_test_case(product_id: int, test_case_id: int) -> str:
    """Get a single test case by ID with its test steps."""
    client = _get_client()
    tc = client.get_test_case(product_id, test_case_id)
    steps = client.get_test_steps(product_id, test_case_id)
    return formatters.format_test_case(tc, steps=steps)


# ──────────────────────────────────────────────
#  Test Runs
# ──────────────────────────────────────────────

@mcp.tool()
def list_test_runs(product_id: int) -> str:
    """List recent test runs for a product, sorted by most recent first."""
    client = _get_client()
    runs = client.get_test_runs(product_id)
    return formatters.format_test_runs(runs)


@mcp.tool()
def record_test_run(
    product_id: int,
    test_case_id: int,
    execution_status_id: int,
    test_name: str,
    short_message: str = "",
    long_message: str = "",
    error_count: int = 0,
) -> str:
    """Record an automated test run result.

    execution_status_id: 1=Failed, 2=Passed, 3=Not Run, 4=Not Applicable, 5=Blocked, 6=Caution
    """
    client = _get_client()
    result = client.record_test_run(
        product_id, test_case_id, execution_status_id,
        test_name, short_message, long_message, error_count,
    )
    return f"Test run recorded for TC:{test_case_id} — Status: {formatters.EXECUTION_STATUSES.get(execution_status_id, '?')}"


# ──────────────────────────────────────────────
#  Builds
# ──────────────────────────────────────────────

@mcp.tool()
def create_build(
    product_id: int,
    release_id: int,
    name: str,
    description: str = "",
    build_status_id: int = 1,
    commits: list[str] | None = None,
) -> str:
    """Create a build entry for a release.

    build_status_id: 1=Succeeded, 2=Failed, 3=Unstable, 4=Aborted
    commits: List of commit hashes/revision keys to associate
    """
    client = _get_client()
    result = client.create_build(
        product_id, release_id, name, description, build_status_id, commits,
    )
    build_id = result.get("BuildId", "?") if isinstance(result, dict) else "?"
    return f"Build created: **{name}** (Build #{build_id}) for RL:{release_id}"


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
