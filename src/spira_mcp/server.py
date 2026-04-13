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
#  Programs
# ──────────────────────────────────────────────

@mcp.tool()
def list_programs() -> str:
    """List all programs (groups of products) in the Spira instance."""
    client = _get_client()
    programs = client.get_programs()
    return formatters.format_programs(programs)


@mcp.tool()
def list_program_products(program_id: int) -> str:
    """List all products belonging to a specific program."""
    client = _get_client()
    products = client.get_program_products(program_id)
    return formatters.format_products(products)


@mcp.tool()
def list_milestones(program_id: int) -> str:
    """List milestones for a program."""
    client = _get_client()
    milestones = client.get_milestones(program_id)
    return formatters.format_milestones(milestones)


@mcp.tool()
def list_capabilities(program_id: int) -> str:
    """List capabilities for a program."""
    client = _get_client()
    capabilities = client.get_capabilities(program_id)
    return formatters.format_capabilities(capabilities)


# ──────────────────────────────────────────────
#  Templates
# ──────────────────────────────────────────────

@mcp.tool()
def list_templates() -> str:
    """List all product templates in the Spira instance."""
    client = _get_client()
    templates = client.get_product_templates()
    return formatters.format_templates(templates)


@mcp.tool()
def get_template(template_id: int) -> str:
    """Get details of a specific product template."""
    client = _get_client()
    template = client.get_product_template(template_id)
    return formatters.format_template(template)


@mcp.tool()
def list_artifact_types(template_id: int) -> str:
    """List all artifact types (requirement types, incident types, task types, etc.) for a template.

    Use this to discover valid type IDs for create/update tools.
    Get the template_id from the product details (get_product) or list_templates.
    """
    client = _get_client()
    types = client.get_artifact_types(template_id)
    return formatters.format_artifact_types(types)


@mcp.tool()
def list_custom_properties(template_id: int) -> str:
    """List all custom properties (custom fields) for all artifact types in a template.

    Shows field names, property numbers (Custom_01, Custom_02, etc.), and types.
    Use this to discover custom field IDs for filtering or updating artifacts.
    """
    client = _get_client()
    props = client.get_custom_properties(template_id)
    return formatters.format_custom_properties(props)


# ──────────────────────────────────────────────
#  My Work
# ──────────────────────────────────────────────

@mcp.tool()
def get_my_tasks() -> str:
    """Get all tasks assigned to the current user, across all products."""
    client = _get_client()
    tasks = client.get_my_tasks()
    return formatters.format_my_tasks(tasks)


@mcp.tool()
def get_my_incidents() -> str:
    """Get all incidents assigned to the current user, across all products."""
    client = _get_client()
    incidents = client.get_my_incidents()
    return formatters.format_my_incidents(incidents)


@mcp.tool()
def get_my_requirements() -> str:
    """Get all requirements assigned to the current user, across all products."""
    client = _get_client()
    requirements = client.get_my_requirements()
    return formatters.format_my_requirements(requirements)


@mcp.tool()
def get_my_test_cases() -> str:
    """Get all test cases assigned to the current user, across all products."""
    client = _get_client()
    test_cases = client.get_my_test_cases()
    return formatters.format_my_test_cases(test_cases)


@mcp.tool()
def get_my_test_sets() -> str:
    """Get all test sets assigned to the current user, across all products."""
    client = _get_client()
    test_sets = client.get_my_test_sets()
    return formatters.format_my_test_sets(test_sets)


# ──────────────────────────────────────────────
#  Releases / Sprints
# ──────────────────────────────────────────────

@mcp.tool()
def list_releases(
    product_id: int,
    active_only: bool = False,
    limit: int | None = None,
) -> str:
    """List releases/sprints for a product, sorted by start date (most recent first).

    Returns all release types (major, minor, sprints, phases) mixed together, sorted
    by most recent first. The words "sprints", "releases", and "iterations" are
    interchangeable — always return all types sorted by date.

    Filters (all optional):
    - active_only: False (default) = all releases. True = only active/in-progress
    - limit: Return only the N most recent releases
    """
    client = _get_client()
    releases = client.get_releases(product_id, active_only=active_only)
    if limit is not None:
        releases = releases[:limit]
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


@mcp.tool()
def create_requirement(
    product_id: int,
    name: str,
    description: str = "",
    requirement_type_id: int | None = None,
    importance_id: int | None = None,
    owner_id: int | None = None,
    release_id: int | None = None,
    parent_requirement_id: int | None = None,
) -> str:
    """Create a new requirement in Spira.

    Required:
    - name: Requirement title

    Optional:
    - description: Detailed description (supports HTML)
    - requirement_type_id: Type (project-specific)
    - importance_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign to
    - parent_requirement_id: Create as a child of this requirement
    """
    client = _get_client()
    result = client.create_requirement(
        product_id, name, description,
        requirement_type_id=requirement_type_id,
        importance_id=importance_id,
        owner_id=owner_id,
        release_id=release_id,
        parent_requirement_id=parent_requirement_id,
    )
    req_id = result.get("RequirementId", "?") if isinstance(result, dict) else "?"
    return f"Requirement created: **RQ:{req_id}** — {name}\n\n{formatters.format_requirement(result)}"


@mcp.tool()
def update_requirement(
    product_id: int,
    requirement_id: int,
    name: str | None = None,
    description: str | None = None,
    requirement_status_id: int | None = None,
    importance_id: int | None = None,
    owner_id: int | None = None,
    release_id: int | None = None,
) -> str:
    """Update a requirement. Only pass the fields you want to change.

    Fields (all optional):
    - name: Requirement title
    - description: Detailed description (supports HTML)
    - requirement_status_id: 1=Requested, 2=Planned, 3=In Progress, 4=Developed, 5=Accepted, 6=Rejected, 7=Under Review, 8=Obsolete, 9=Tested, 10=Completed
    - importance_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign to
    """
    updates = {}
    if name is not None:
        updates["Name"] = name
    if description is not None:
        updates["Description"] = description
    if requirement_status_id is not None:
        updates["RequirementStatusId"] = requirement_status_id
    if importance_id is not None:
        updates["ImportanceId"] = importance_id
    if owner_id is not None:
        updates["OwnerId"] = owner_id
    if release_id is not None:
        updates["ReleaseId"] = release_id

    if not updates:
        return "No fields to update. Pass at least one field to change."

    client = _get_client()
    result = client.update_requirement(product_id, requirement_id, **updates)
    return f"Requirement RQ:{requirement_id} updated successfully.\n\n{formatters.format_requirement(result)}"


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


@mcp.tool()
def create_task(
    product_id: int,
    name: str,
    description: str = "",
    task_status_id: int = 1,
    task_priority_id: int | None = None,
    owner_id: int | None = None,
    release_id: int | None = None,
    requirement_id: int | None = None,
    estimated_effort: int | None = None,
) -> str:
    """Create a new task in Spira.

    Required:
    - name: Task title

    Optional:
    - description: Detailed description
    - task_status_id: 1=Not Started (default), 2=In Progress, 3=Completed, 4=Blocked, 5=Deferred
    - task_priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign to
    - requirement_id: Parent requirement to link to
    - estimated_effort: Estimated effort in minutes
    """
    client = _get_client()
    result = client.create_task(
        product_id, name, description,
        task_status_id=task_status_id,
        task_priority_id=task_priority_id,
        owner_id=owner_id,
        release_id=release_id,
        requirement_id=requirement_id,
        estimated_effort=estimated_effort,
    )
    task_id = result.get("TaskId", "?") if isinstance(result, dict) else "?"
    return f"Task created: **TK:{task_id}** — {name}\n\n{formatters.format_task(result)}"


@mcp.tool()
def update_task(
    product_id: int,
    task_id: int,
    name: str | None = None,
    description: str | None = None,
    task_status_id: int | None = None,
    task_priority_id: int | None = None,
    owner_id: int | None = None,
    release_id: int | None = None,
    estimated_effort: int | None = None,
    actual_effort: int | None = None,
    remaining_effort: int | None = None,
) -> str:
    """Update a task. Only pass the fields you want to change.

    Fields (all optional):
    - name: Task name
    - description: Task description
    - task_status_id: 1=Not Started, 2=In Progress, 3=Completed, 4=Blocked, 5=Deferred, 6=Rejected, 7=Under Review, 8=Obsolete
    - task_priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign the task to
    - estimated_effort: Estimated effort in minutes
    - actual_effort: Actual effort in minutes
    - remaining_effort: Remaining effort in minutes
    """
    updates = {}
    if name is not None:
        updates["Name"] = name
    if description is not None:
        updates["Description"] = description
    if task_status_id is not None:
        updates["TaskStatusId"] = task_status_id
    if task_priority_id is not None:
        updates["TaskPriorityId"] = task_priority_id
    if owner_id is not None:
        updates["OwnerId"] = owner_id
    if release_id is not None:
        updates["ReleaseId"] = release_id
    if estimated_effort is not None:
        updates["EstimatedEffort"] = estimated_effort
    if actual_effort is not None:
        updates["ActualEffort"] = actual_effort
    if remaining_effort is not None:
        updates["RemainingEffort"] = remaining_effort

    if not updates:
        return "No fields to update. Pass at least one field to change."

    client = _get_client()
    result = client.update_task(product_id, task_id, **updates)
    return f"Task TK:{task_id} updated successfully.\n\n{formatters.format_task(result)}"


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


@mcp.tool()
def create_incident(
    product_id: int,
    name: str,
    description: str = "",
    incident_type_id: int | None = None,
    priority_id: int | None = None,
    severity_id: int | None = None,
    owner_id: int | None = None,
    detected_release_id: int | None = None,
) -> str:
    """Create a new incident/bug in Spira.

    Required:
    - name: Incident title

    Optional:
    - description: Detailed description (supports HTML)
    - incident_type_id: Type of incident (project-specific, check get_product for available types)
    - priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - severity_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - owner_id: User ID to assign
    - detected_release_id: Release where the bug was found
    """
    client = _get_client()
    result = client.create_incident(
        product_id, name, description,
        incident_type_id=incident_type_id,
        priority_id=priority_id,
        severity_id=severity_id,
        owner_id=owner_id,
        detected_release_id=detected_release_id,
    )
    inc_id = result.get("IncidentId", "?") if isinstance(result, dict) else "?"
    return f"Incident created: **IN:{inc_id}** — {name}\n\n{formatters.format_incident(result)}"


@mcp.tool()
def update_incident(
    product_id: int,
    incident_id: int,
    name: str | None = None,
    description: str | None = None,
    incident_status_id: int | None = None,
    priority_id: int | None = None,
    severity_id: int | None = None,
    owner_id: int | None = None,
    detected_release_id: int | None = None,
    resolved_release_id: int | None = None,
) -> str:
    """Update an incident. Only pass the fields you want to change.

    Fields (all optional):
    - name: Incident title
    - description: Detailed description (supports HTML)
    - incident_status_id: Status (project-specific IDs — common: 1=New, 2=Open, 3=Assigned, 5=Fixed, 6=Closed, 9=Duplicate)
    - priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - severity_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - owner_id: User ID to assign
    - detected_release_id: Release where the bug was found
    - resolved_release_id: Release where the bug was fixed
    """
    updates = {}
    if name is not None:
        updates["Name"] = name
    if description is not None:
        updates["Description"] = description
    if incident_status_id is not None:
        updates["IncidentStatusId"] = incident_status_id
    if priority_id is not None:
        updates["PriorityId"] = priority_id
    if severity_id is not None:
        updates["SeverityId"] = severity_id
    if owner_id is not None:
        updates["OwnerId"] = owner_id
    if detected_release_id is not None:
        updates["DetectedReleaseId"] = detected_release_id
    if resolved_release_id is not None:
        updates["ResolvedReleaseId"] = resolved_release_id

    if not updates:
        return "No fields to update. Pass at least one field to change."

    client = _get_client()
    result = client.update_incident(product_id, incident_id, **updates)
    return f"Incident IN:{incident_id} updated successfully.\n\n{formatters.format_incident(result)}"


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


@mcp.tool()
def create_test_case(
    product_id: int,
    name: str,
    description: str = "",
    test_case_type_id: int | None = None,
    test_case_priority_id: int | None = None,
    owner_id: int | None = None,
    test_case_folder_id: int | None = None,
    estimated_duration: int | None = None,
    tags: str = "",
) -> str:
    """Create a new test case in Spira.

    Required:
    - name: Test case title

    Optional:
    - description: Detailed description (supports HTML)
    - test_case_type_id: Type (project-specific)
    - test_case_priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - owner_id: User ID to assign
    - test_case_folder_id: Folder to place it in (null = root)
    - estimated_duration: Estimated duration in minutes
    - tags: Comma-separated tags
    """
    client = _get_client()
    result = client.create_test_case(
        product_id, name, description,
        test_case_type_id=test_case_type_id,
        test_case_priority_id=test_case_priority_id,
        owner_id=owner_id,
        test_case_folder_id=test_case_folder_id,
        estimated_duration=estimated_duration,
        tags=tags,
    )
    tc_id = result.get("TestCaseId", "?") if isinstance(result, dict) else "?"
    return f"Test case created: **TC:{tc_id}** — {name}\n\n{formatters.format_test_case(result)}"


@mcp.tool()
def update_test_case(
    product_id: int,
    test_case_id: int,
    name: str | None = None,
    description: str | None = None,
    test_case_status_id: int | None = None,
    test_case_priority_id: int | None = None,
    test_case_type_id: int | None = None,
    owner_id: int | None = None,
    estimated_duration: int | None = None,
    test_case_folder_id: int | None = None,
    tags: str | None = None,
) -> str:
    """Update a test case. Only pass the fields you want to change — all others are preserved.

    Automatically handles optimistic concurrency (GETs current state first, then PUTs).

    Fields (all optional — only pass what you want to change):
    - name: Test case name
    - description: Test case description (supports HTML)
    - test_case_status_id: 1=Draft, 2=Ready for Review, 3=Rejected, 4=Approved, 5=Obsolete, 6=Ready for Test, 7=Tested
    - test_case_priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - test_case_type_id: Type of test case
    - owner_id: User ID to assign
    - estimated_duration: Estimated duration in minutes
    - test_case_folder_id: Move to a different folder
    - tags: Comma-separated tags
    """
    updates = {}
    if name is not None:
        updates["Name"] = name
    if description is not None:
        updates["Description"] = description
    if test_case_status_id is not None:
        updates["TestCaseStatusId"] = test_case_status_id
    if test_case_priority_id is not None:
        updates["TestCasePriorityId"] = test_case_priority_id
    if test_case_type_id is not None:
        updates["TestCaseTypeId"] = test_case_type_id
    if owner_id is not None:
        updates["OwnerId"] = owner_id
    if estimated_duration is not None:
        updates["EstimatedDuration"] = estimated_duration
    if test_case_folder_id is not None:
        updates["TestCaseFolderId"] = test_case_folder_id
    if tags is not None:
        updates["Tags"] = tags

    if not updates:
        return "No fields to update. Pass at least one field to change."

    client = _get_client()
    result = client.update_test_case(product_id, test_case_id, **updates)
    return f"Test case TC:{test_case_id} updated successfully.\n\n{formatters.format_test_case(result)}"


@mcp.tool()
def update_test_step(
    product_id: int,
    test_case_id: int,
    test_step_id: int,
    description: str | None = None,
    expected_result: str | None = None,
    sample_data: str | None = None,
) -> str:
    """Update a single test step. Only pass the fields you want to change.

    Automatically handles optimistic concurrency (GETs current state first, then PUTs).

    Fields (all optional — only pass what you want to change):
    - description: What the tester should do (supports HTML)
    - expected_result: What the tester should see if it passes (supports HTML)
    - sample_data: Test data for execution
    """
    updates = {}
    if description is not None:
        updates["Description"] = description
    if expected_result is not None:
        updates["ExpectedResult"] = expected_result
    if sample_data is not None:
        updates["SampleData"] = sample_data

    if not updates:
        return "No fields to update. Pass at least one field to change."

    client = _get_client()
    result = client.update_test_step(product_id, test_case_id, test_step_id, **updates)
    step_desc = result.get("Description", "")[:100] if isinstance(result, dict) else ""
    return f"Test step #{test_step_id} in TC:{test_case_id} updated successfully.\n\n**Description:** {step_desc}"


@mcp.tool()
def create_test_step(
    product_id: int,
    test_case_id: int,
    description: str,
    expected_result: str = "",
    sample_data: str = "",
) -> str:
    """Add a new test step to a test case. The step is appended at the end.

    Required:
    - description: What the tester should do (supports HTML)

    Optional:
    - expected_result: What the tester should see if it passes (supports HTML)
    - sample_data: Test data for execution
    """
    client = _get_client()
    result = client.create_test_step(product_id, test_case_id, description, expected_result, sample_data)
    step_id = result.get("TestStepId", "?") if isinstance(result, dict) else "?"
    return f"Test step created (TestStepId: {step_id}) in TC:{test_case_id}.\n\n**Description:** {description[:200]}"


@mcp.tool()
def delete_test_step(product_id: int, test_case_id: int, test_step_id: int) -> str:
    """Delete a test step from a test case. Use get_test_case first to find the TestStepId."""
    client = _get_client()
    client.delete_test_step(product_id, test_case_id, test_step_id)
    return f"Test step #{test_step_id} deleted from TC:{test_case_id}."


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
def get_test_run(product_id: int, test_run_id: int) -> str:
    """Get a single test run with its per-step results.

    Shows each step's execution status, description, expected result, and actual result.
    """
    client = _get_client()
    run = client.get_test_run(product_id, test_run_id)
    return formatters.format_test_run(run)


@mcp.tool()
def create_test_run(
    product_id: int,
    test_case_ids: list[int],
    release_id: int | None = None,
) -> str:
    """Create test run shells from test case IDs. Steps are pre-populated from the test cases.

    Use this to start manual test execution. After creating, use save_test_run_results
    to fill in per-step results.

    - test_case_ids: List of test case IDs to create runs for, e.g. [290, 283]
    - release_id: Optional release to associate the runs with
    """
    client = _get_client()
    runs = client.create_test_runs(product_id, test_case_ids, release_id=release_id)
    if not runs:
        return "No test runs created."
    lines = [f"Created {len(runs)} test run(s):\n"]
    for r in (runs if isinstance(runs, list) else [runs]):
        steps = r.get("TestRunSteps") or []
        lines.append(
            f"- **Run #{r.get('TestRunId')}** — TC:{r.get('TestCaseId')} "
            f"({len(steps)} steps pre-populated)"
        )
    return "\n".join(lines)


@mcp.tool()
def save_test_run_results(
    product_id: int,
    test_run_id: int,
    step_results: list[dict],
    end_date: str | None = None,
) -> str:
    """Save test run results with per-step execution status and actual results.

    Fetches the current test run, applies your step results, and saves.
    Do NOT set the overall test run status — Spira calculates it from the step statuses.

    Parameters:
    - test_run_id: The test run ID (from create_test_run or list_test_runs)
    - step_results: Array of step result objects. Each object:
      - position (int, required): Step position number (1-based)
      - execution_status_id (int, required): 1=Failed, 2=Passed, 3=Not Run, 4=N/A, 5=Blocked, 6=Caution
      - actual_result (str, optional): What actually happened during testing
    - end_date: ISO datetime for completion (default: now)

    Example step_results:
    [
        {"position": 1, "execution_status_id": 2, "actual_result": "Login page loaded correctly"},
        {"position": 2, "execution_status_id": 1, "actual_result": "Submit button was disabled unexpectedly"},
        {"position": 3, "execution_status_id": 2, "actual_result": "Data saved successfully"}
    ]
    """
    from datetime import datetime, timezone

    client = _get_client()
    run = client.get_test_run(product_id, test_run_id)
    if not run:
        return f"Test run #{test_run_id} not found."

    steps = run.get("TestRunSteps") or []
    if not steps:
        return f"Test run #{test_run_id} has no steps."

    # Build a lookup by position
    result_lookup = {r["position"]: r for r in step_results}

    # Apply results to each step
    for step in steps:
        pos = step.get("Position")
        if pos in result_lookup:
            sr = result_lookup[pos]
            step["ExecutionStatusId"] = sr["execution_status_id"]
            if "actual_result" in sr:
                step["ActualResult"] = sr["actual_result"]
        # Per KB684: set these to 0 for save
        step["TestRunStepId"] = 0
        step["TestRunId"] = 0

    # Set end date
    if not end_date:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    run["EndDate"] = end_date
    # Remove overall ExecutionStatusId — let Spira calculate from steps
    run.pop("ExecutionStatusId", None)

    result = client.save_test_runs(product_id, [run], end_date)
    saved = result[0] if isinstance(result, list) and result else result
    return f"Test run #{test_run_id} saved successfully.\n\n{formatters.format_test_run(saved)}"


@mcp.tool()
def record_test_run(
    product_id: int,
    test_case_id: int,
    execution_status_id: int,
    test_name: str,
    short_message: str = "",
    long_message: str = "",
    error_count: int = 0,
    release_id: int | None = None,
    build_id: int | None = None,
) -> str:
    """Record an automated test run result (simple, no per-step detail).

    For per-step results, use create_test_run + save_test_run_results instead.

    execution_status_id: 1=Failed, 2=Passed, 3=Not Run, 4=Not Applicable, 5=Blocked, 6=Caution
    """
    client = _get_client()
    result = client.record_test_run(
        product_id, test_case_id, execution_status_id,
        test_name, short_message, long_message, error_count,
        release_id=release_id, build_id=build_id,
    )
    return f"Test run recorded for TC:{test_case_id} — Status: {formatters.EXECUTION_STATUSES.get(execution_status_id, '?')}"


# ──────────────────────────────────────────────
#  Documents & Attachments
# ──────────────────────────────────────────────

ARTIFACT_TYPES = {
    "requirement": 1, "test_case": 2, "incident": 3, "release": 4,
    "test_run": 5, "task": 6, "test_step": 7, "test_set": 8,
    "document": 13, "risk": 14,
}


@mcp.tool()
def upload_document(
    product_id: int,
    file_path: str,
    description: str = "",
    artifact_type: str | None = None,
    artifact_id: int | None = None,
) -> str:
    """Upload a file to Spira as a document and optionally attach it to an artifact's Attachments tab.

    WARNING: This does NOT make images visible inline in Spira's UI. For screenshots or images
    that should be visible inside a field (description, expected result, etc.), use
    attach_image_to_field instead. This tool is for non-visual file attachments (logs, CSVs, etc.)
    or for attaching to artifacts that have an Attachments tab (test_case, incident).

    Parameters:
    - file_path: Local path to the file to upload
    - description: Description of the document
    - artifact_type: If provided with artifact_id, attaches to the artifact's Attachments tab.
      Values: requirement, test_case, incident, release, test_run, task, test_set
    - artifact_id: The ID of the artifact to attach to
    """
    import base64
    import os

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        binary_data = base64.b64encode(f.read()).decode("ascii")

    client = _get_client()
    doc = client.upload_document(product_id, filename, binary_data, description)

    doc_id = doc.get("AttachmentId") if isinstance(doc, dict) else None
    result = f"Document uploaded: **DC:{doc_id}** — {filename}\n\n{formatters.format_document(doc)}"

    # Auto-attach if artifact specified
    if artifact_type and artifact_id and doc_id:
        type_id = ARTIFACT_TYPES.get(artifact_type)
        if type_id:
            client.attach_document_to_artifact(product_id, type_id, artifact_id, doc_id)
            result += f"\nAttached to {artifact_type} #{artifact_id}"
        else:
            result += f"\nWarning: Unknown artifact type '{artifact_type}'. Document uploaded but not attached."

    return result


@mcp.tool()
def attach_document(
    product_id: int,
    document_id: int,
    artifact_type: str,
    artifact_id: int,
) -> str:
    """Attach an existing document to an artifact's Attachments tab.

    WARNING: This does NOT make images visible inline in Spira's UI. For screenshots or images
    that should be visible inside a field, use attach_image_to_field instead.

    - document_id: The DC:XX document ID
    - artifact_type: requirement, test_case, incident, release, test_run, task, test_set
    - artifact_id: The ID of the artifact to attach to
    """
    type_id = ARTIFACT_TYPES.get(artifact_type)
    if not type_id:
        return f"Unknown artifact type '{artifact_type}'. Use: {', '.join(ARTIFACT_TYPES.keys())}"

    client = _get_client()
    client.attach_document_to_artifact(product_id, type_id, artifact_id, document_id)
    return f"Document DC:{document_id} attached to {artifact_type} #{artifact_id}"


@mcp.tool()
def list_documents(
    product_id: int,
    artifact_type: str,
    artifact_id: int,
) -> str:
    """List documents attached to an artifact.

    - artifact_type: requirement, test_case, incident, release, test_run, task, test_step, test_set
    - artifact_id: The ID of the artifact
    """
    type_id = ARTIFACT_TYPES.get(artifact_type)
    if not type_id:
        return f"Unknown artifact type '{artifact_type}'. Use: {', '.join(ARTIFACT_TYPES.keys())}"

    client = _get_client()
    docs = client.get_artifact_documents(product_id, type_id, artifact_id)
    return formatters.format_documents(docs)


@mcp.tool()
def attach_image_to_field(
    product_id: int,
    file_path: str,
    target_type: str,
    target_id: int,
    field: str = "description",
    caption: str = "",
    test_case_id: int | None = None,
) -> str:
    """Upload and attach a screenshot/image so it is VISIBLE inline in Spira's UI.

    Use this whenever the user wants to attach, add, embed, or insert a screenshot or image
    into any Spira artifact. This is the ONLY way to make images visible in the Spira web UI.
    The upload_document and attach_document tools do NOT display images inline.

    Parameters:
    - file_path: Local path to the image file
    - target_type: What to embed into. Values: test_step, test_case, incident, requirement, task
    - target_id: The ID of the target artifact (e.g. TestStepId, TestCaseId, IncidentId)
    - field: Which rich-text field to embed into. Default "description".
      For test_step: "description" or "expected_result"
      For test_case/incident/requirement/task: "description"
    - caption: Optional caption text below the image
    - test_case_id: Required when target_type is "test_step" (the parent test case ID)
    """
    import base64
    import os

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    # Step 1: Upload the file
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        binary_data = base64.b64encode(f.read()).decode("ascii")

    client = _get_client()
    doc = client.upload_document(product_id, filename, binary_data)
    doc_id = doc.get("AttachmentId") if isinstance(doc, dict) else None
    if not doc_id:
        return "Failed to upload document — no AttachmentId returned."

    # Step 2: Build the <img> tag
    img_tag = f'<img src="/{product_id}/Attachment/{doc_id}.aspx" alt="{filename}" />'
    if caption:
        img_tag = f'<p>{img_tag}</p><p><em>{caption}</em></p>'
    else:
        img_tag = f'<p>{img_tag}</p>'

    # Step 3: Get current field content and append the image
    field_map = {
        "description": "Description",
        "expected_result": "ExpectedResult",
    }
    api_field = field_map.get(field)
    if not api_field:
        return f"Unknown field '{field}'. Use: {', '.join(field_map.keys())}"

    if target_type == "test_step":
        if not test_case_id:
            return "test_case_id is required when target_type is 'test_step'."
        steps = client.get_test_steps(product_id, test_case_id)
        step = next((s for s in steps if s.get("TestStepId") == target_id), None)
        if not step:
            return f"Test step {target_id} not found in TC:{test_case_id}."
        current_content = step.get(api_field) or ""
        client.update_test_step(product_id, test_case_id, target_id, **{api_field: current_content + img_tag})

    elif target_type == "test_case":
        tc = client.get_test_case(product_id, target_id)
        current_content = tc.get(api_field) or ""
        client.update_test_case(product_id, target_id, **{api_field: current_content + img_tag})

    elif target_type == "incident":
        inc = client.get_incident(product_id, target_id)
        current_content = inc.get(api_field) or ""
        client.update_incident(product_id, target_id, **{api_field: current_content + img_tag})

    elif target_type == "requirement":
        req = client.get_requirement(product_id, target_id)
        current_content = req.get(api_field) or ""
        client.update_requirement(product_id, target_id, **{api_field: current_content + img_tag})

    elif target_type == "task":
        task = client.get_task(product_id, target_id)
        current_content = task.get(api_field) or ""
        client.update_task(product_id, target_id, **{api_field: current_content + img_tag})

    else:
        return f"Unknown target_type '{target_type}'. Use: test_step, test_case, incident, requirement, task"

    return (
        f"Image embedded successfully.\n\n"
        f"**Document:** DC:{doc_id} ({filename})\n"
        f"**Target:** {target_type} #{target_id} → {field}\n"
        f"**HTML:** `{img_tag}`"
    )


# ──────────────────────────────────────────────
#  Test Case Folders
# ──────────────────────────────────────────────

@mcp.tool()
def list_test_folders(product_id: int) -> str:
    """List all test case folders for a product, showing hierarchy and test case counts.

    Use this to find folder IDs for moving test cases (via update_test_case with test_case_folder_id).
    """
    client = _get_client()
    folders = client.get_test_case_folders(product_id)
    return formatters.format_test_folders(folders)


# ──────────────────────────────────────────────
#  Associations (linking artifacts)
# ──────────────────────────────────────────────

@mcp.tool()
def create_association(
    product_id: int,
    source_type: str,
    source_id: int,
    dest_type: str,
    dest_id: int,
    link_type: str = "related",
    comment: str = "",
) -> str:
    """Link two Spira artifacts together (e.g., requirement to test case, bug to requirement).

    Common use cases:
    - Link requirement to test case: source_type="requirement", dest_type="test_case"
    - Link bug to requirement: source_type="incident", dest_type="requirement"
    - Link bug to test case: source_type="incident", dest_type="test_case"
    - Link test case to test case: source_type="test_case", dest_type="test_case"

    Parameters:
    - source_type: requirement, test_case, incident, release, test_run, task, test_step, test_set, risk
    - source_id: ID of the source artifact
    - dest_type: Same values as source_type
    - dest_id: ID of the destination artifact
    - link_type: "related" (default), "depends_on", or "is_depended_on_by"
    - comment: Optional description of the link
    """
    link_types = {"related": 1, "depends_on": 2, "is_depended_on_by": 3}
    link_type_id = link_types.get(link_type, 1)

    src_type_id = ARTIFACT_TYPES.get(source_type)
    dst_type_id = ARTIFACT_TYPES.get(dest_type)

    if not src_type_id:
        return f"Unknown source_type '{source_type}'. Use: {', '.join(ARTIFACT_TYPES.keys())}"
    if not dst_type_id:
        return f"Unknown dest_type '{dest_type}'. Use: {', '.join(ARTIFACT_TYPES.keys())}"

    client = _get_client()
    result = client.create_association(
        product_id, src_type_id, source_id, dst_type_id, dest_id,
        artifact_link_type_id=link_type_id, comment=comment,
    )
    link_id = result.get("ArtifactLinkId", "?") if isinstance(result, dict) else "?"
    link_name = {"related": "Related To", "depends_on": "Depends On", "is_depended_on_by": "Is Depended On By"}.get(link_type, link_type)
    return (
        f"Association created (Link #{link_id}):\n"
        f"**{source_type}** #{source_id} —[{link_name}]→ **{dest_type}** #{dest_id}"
    )


@mcp.tool()
def list_associations(
    product_id: int,
    artifact_type: str,
    artifact_id: int,
) -> str:
    """List all associations (links) for an artifact.

    Shows what requirements, test cases, incidents, etc. are linked to this artifact.

    - artifact_type: requirement, test_case, incident, release, test_run, task, test_step, test_set, risk
    - artifact_id: The ID of the artifact
    """
    type_id = ARTIFACT_TYPES.get(artifact_type)
    if not type_id:
        return f"Unknown artifact_type '{artifact_type}'. Use: {', '.join(ARTIFACT_TYPES.keys())}"

    client = _get_client()
    associations = client.get_associations(product_id, type_id, artifact_id)
    return formatters.format_associations(associations)


@mcp.tool()
def delete_association(product_id: int, artifact_link_id: int) -> str:
    """Delete an association (link) between two artifacts.

    Use list_associations first to find the Link ID to delete.
    """
    client = _get_client()
    client.delete_association(product_id, artifact_link_id)
    return f"Association (Link #{artifact_link_id}) deleted."


# ──────────────────────────────────────────────
#  Risks
# ──────────────────────────────────────────────

@mcp.tool()
def list_risks(product_id: int, release_id: int | None = None) -> str:
    """List risks for a product, optionally filtered by release.

    - release_id: Filter risks assigned to this release
    """
    client = _get_client()
    risks = client.get_risks(product_id, release_id=release_id)
    return formatters.format_risks(risks)


# ──────────────────────────────────────────────
#  Test Sets
# ──────────────────────────────────────────────

@mcp.tool()
def list_test_sets(product_id: int) -> str:
    """List all test sets for a product."""
    client = _get_client()
    test_sets = client.get_test_sets(product_id)
    return formatters.format_test_sets(test_sets)


# ──────────────────────────────────────────────
#  Automation Hosts
# ──────────────────────────────────────────────

@mcp.tool()
def list_automation_hosts(product_id: int) -> str:
    """List automation hosts configured for a product."""
    client = _get_client()
    hosts = client.get_automation_hosts(product_id)
    return formatters.format_automation_hosts(hosts)


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
#  Tool filtering
# ──────────────────────────────────────────────

TOOL_PRESETS = {
    "minimal": [
        "list_products", "get_product",
        "list_releases", "get_release",
        "list_requirements", "get_requirement",
        "list_tasks", "get_task",
        "list_incidents", "get_incident",
        "list_test_cases", "get_test_case",
    ],
    "read_only": [
        "list_products", "get_product",
        "list_programs", "list_program_products", "list_milestones", "list_capabilities",
        "list_templates", "get_template", "list_artifact_types", "list_custom_properties",
        "get_my_tasks", "get_my_incidents", "get_my_requirements", "get_my_test_cases", "get_my_test_sets",
        "list_releases", "get_release",
        "list_requirements", "get_requirement",
        "list_tasks", "get_task", "count_tasks",
        "list_incidents", "get_incident",
        "list_test_cases", "get_test_case", "list_test_folders",
        "list_test_runs", "get_test_run",
        "list_risks", "list_test_sets", "list_automation_hosts",
        "list_documents", "list_associations",
    ],
    "dev": [
        "list_products", "get_product",
        "get_my_tasks", "get_my_incidents", "get_my_requirements",
        "list_releases", "get_release",
        "list_requirements", "get_requirement",
        "list_tasks", "get_task", "count_tasks", "update_task",
        "list_incidents", "get_incident", "create_incident", "update_incident",
        "list_risks",
        "list_associations", "create_association",
        "list_artifact_types", "list_custom_properties",
    ],
    "qa": [
        "list_products", "get_product",
        "get_my_tasks", "get_my_incidents", "get_my_test_cases", "get_my_test_sets",
        "list_releases", "get_release",
        "list_requirements", "get_requirement",
        "list_tasks", "get_task", "count_tasks", "update_task",
        "list_incidents", "get_incident", "create_incident", "update_incident",
        "list_test_cases", "get_test_case", "create_test_case", "update_test_case", "list_test_folders",
        "create_test_step", "update_test_step", "delete_test_step",
        "list_test_runs", "get_test_run", "create_test_run", "save_test_run_results", "record_test_run",
        "list_test_sets",
        "upload_document", "attach_document", "attach_image_to_field", "list_documents",
        "create_association", "list_associations", "delete_association",
        "list_artifact_types", "list_custom_properties",
    ],
    "full": None,  # No filtering — all tools enabled
}


def _apply_tool_filter():
    """Filter tools based on SPIRA_MCP_TOOLS environment variable.

    Supports:
    - Preset names: "minimal", "read_only", "qa", "full"
    - Comma-separated tool names: "list_products,get_product,list_tasks"
    - Not set or "full": all tools enabled (default)
    """
    tools_config = os.environ.get("SPIRA_MCP_TOOLS", "").strip()
    if not tools_config or tools_config == "full":
        return

    # Check if it's a preset
    if tools_config in TOOL_PRESETS:
        allowed = TOOL_PRESETS[tools_config]
        if allowed is None:
            return  # "full" preset
        allowed = set(allowed)
    else:
        # Treat as comma-separated tool names
        allowed = set(t.strip() for t in tools_config.split(",") if t.strip())

    # Remove tools not in the allowed set
    all_tools = list(mcp._tool_manager._tools.keys())
    for name in all_tools:
        if name not in allowed:
            del mcp._tool_manager._tools[name]


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────

def main():
    _apply_tool_filter()
    mcp.run()


if __name__ == "__main__":
    main()
