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


_CLIENT_CACHE = {}


def _get_client():
    """Return a SpiraClient for the env-configured instance.

    Cached per credentials so the underlying requests.Session (and its connection
    pool) is reused across tool calls instead of re-handshaking TLS every time
    (fix.md F14).
    """
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

    key = (base_url, username, api_key)
    client = _CLIENT_CACHE.get(key)
    if client is None:
        client = SpiraClient(base_url, username, api_key)
        _CLIENT_CACHE[key] = client
    return client


def _custom_meta(client, product_id, artifact_type_name):
    """Fetch custom-property metadata for an artifact type via product_id.

    Resolves the product's template_id, then returns the indexed metadata
    (cached per-process). Used by single-artifact formatters to decode
    list-type custom-property option IDs to their display labels.
    """
    template_id = client.get_template_id_for_product(product_id)
    return client.get_custom_properties_for_artifact_type(template_id, artifact_type_name)


def _resolved_custom_filters(client, product_id, artifact_type_name, custom_property_filters):
    """Resolve a {name: value} custom-filter dict into validated RemoteFilter entries."""
    if not custom_property_filters:
        return []
    template_id = client.get_template_id_for_product(product_id)
    return client.resolve_custom_filters_for(template_id, artifact_type_name, custom_property_filters)


def _resolved_custom_values(client, product_id, artifact_type_name, custom_properties):
    """Resolve a {name: value} custom-write dict into CustomProperties body entries."""
    if not custom_properties:
        return None
    template_id = client.get_template_id_for_product(product_id)
    return client.resolve_custom_values_for(template_id, artifact_type_name, custom_properties)


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
    """List artifact types AND template-specific statuses/priorities/importances/severities.

    THE discovery tool for valid IDs to pass to create/update tools — status, priority,
    importance and severity IDs vary per template; never assume the Spira defaults.
    Get the template_id from the product details (get_product) or list_templates.
    """
    client = _get_client()
    types = client.get_artifact_types(template_id)
    return formatters.format_artifact_types(types)


@mcp.tool()
def list_custom_properties(
    artifact_type_name: str,
    template_id: int | None = None,
    product_id: int | None = None,
) -> str:
    """List custom properties (custom fields) for one artifact type in a template.

    Shows each field's slot (Custom_XX), display name, type, and — for list-type
    fields — the full option list with each option's CustomPropertyValueId.
    Use this to discover field slots and option IDs for filtering or updating
    artifacts.

    Required:
    - artifact_type_name: One of TestCase, Requirement, Task, Incident, Risk, Release, TestSet, TestStep

    Provide either:
    - template_id: The product template ID
    - product_id: The product ID (template is resolved automatically)
    """
    if template_id is None and product_id is None:
        return "Provide either template_id or product_id."

    client = _get_client()
    if template_id is None:
        template_id = client.get_template_id_for_product(product_id)

    meta = client.get_custom_properties_for_artifact_type(template_id, artifact_type_name)
    return formatters.format_custom_properties(artifact_type_name, meta["fields"])


# ──────────────────────────────────────────────
#  Users & Components
# ──────────────────────────────────────────────

@mcp.tool()
def list_users(product_id: int) -> str:
    """List the active users of a product with their user IDs, roles, and emails.

    Use this to resolve a person's name to the owner_id / user ID that the
    create/update tools expect (e.g. "assign to John" -> UserId).
    """
    client = _get_client()
    users = client.get_project_users(product_id)
    return formatters.format_users(users)


@mcp.tool()
def list_components(product_id: int, active_only: bool = True) -> str:
    """List the components of a product (ComponentId + name).

    Components categorize requirements, test cases, and incidents within a product.
    """
    client = _get_client()
    components = client.get_components(product_id, active_only=active_only)
    return formatters.format_components(components)


# ──────────────────────────────────────────────
#  Comments
# ──────────────────────────────────────────────

@mcp.tool()
def list_comments(product_id: int, artifact_type: str, artifact_id: int) -> str:
    """List the comments on an incident, task, or requirement.

    - artifact_type: incident, task, or requirement
    - artifact_id: The ID of the artifact
    """
    client = _get_client()
    comments = client.get_comments(product_id, artifact_type, artifact_id)
    prefix = {"incident": "IN", "task": "TK", "requirement": "RQ"}.get(artifact_type, "?")
    return formatters.format_comments(f"{prefix}:{artifact_id}", comments)


@mcp.tool()
def add_comment(product_id: int, artifact_type: str, artifact_id: int, text: str) -> str:
    """Add a comment to an incident, task, or requirement.

    - artifact_type: incident, task, or requirement
    - artifact_id: The ID of the artifact
    - text: Comment text (supports HTML)
    """
    client = _get_client()
    client.add_comment(product_id, artifact_type, artifact_id, text)
    prefix = {"incident": "IN", "task": "TK", "requirement": "RQ"}.get(artifact_type, "?")
    return f"Comment added to {prefix}:{artifact_id}."


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


@mcp.tool()
def add_test_cases_to_release(product_id: int, release_id: int, test_case_ids: list[int]) -> str:
    """Map test cases to a release/sprint so they appear in its test plan.

    Mapped test cases show up in list_test_cases(release_id=...) and count toward
    the release's execution metrics.
    """
    client = _get_client()
    client.add_test_cases_to_release(product_id, release_id, test_case_ids)
    ids = ", ".join(f"TC:{t}" for t in test_case_ids)
    return f"Mapped {ids} to RL:{release_id}."


@mcp.tool()
def remove_test_case_from_release(product_id: int, release_id: int, test_case_id: int) -> str:
    """Remove a test case from a release/sprint's test plan."""
    client = _get_client()
    client.remove_test_case_from_release(product_id, release_id, test_case_id)
    return f"TC:{test_case_id} removed from RL:{release_id}."


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
    custom_property_filters: dict | None = None,
    limit: int | None = None,
) -> str:
    """List requirements for a product with optional filters.

    Filters (all optional):
    - release_id: Filter by release/sprint the requirement is assigned to
    - status_id: Filter by status (1=Requested, 2=Planned, 3=In Progress, 4=Developed, 5=Accepted, 6=Rejected, 7=Under Review, 8=Obsolete, 9=Tested, 10=Completed)
    - importance_id: Filter by importance (1=Critical, 2=High, 3=Medium, 4=Low)
    - owner_id: Filter by owner user ID
    - custom_property_filters: {"<custom field name>": <value>} — names and list-option
      labels are resolved against template metadata (discover via list_custom_properties).
      Unknown names/labels error out instead of being silently ignored by Spira.
    - limit: Return at most N requirements (default: all — large products can return thousands)

    Note: status/importance IDs are template-specific — the legends above are Spira
    defaults and may not match this instance (see update_requirement note).
    """
    client = _get_client()
    requirements = client.get_requirements(
        product_id,
        release_id=release_id,
        status_id=status_id,
        importance_id=importance_id,
        owner_id=owner_id,
        limit=limit,
        extra_filters=_resolved_custom_filters(client, product_id, "Requirement", custom_property_filters),
    )
    out = formatters.format_requirements(requirements)
    if limit is not None and len(requirements) == limit:
        out += f"\n\n_Showing first {limit} — more may exist; raise limit or add filters._"
    return out


@mcp.tool()
def get_requirement(product_id: int, requirement_id: int) -> str:
    """Get a single requirement with its details, steps, and child requirements."""
    client = _get_client()
    req = client.get_requirement(product_id, requirement_id)
    children = client.get_requirement_children(product_id, requirement_id)
    steps = client.get_requirement_steps(product_id, requirement_id)
    custom_meta = _custom_meta(client, product_id, "Requirement")
    return formatters.format_requirement(req, children=children, steps=steps, custom_meta=custom_meta)


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
    custom_properties: dict | None = None,
) -> str:
    """Create a new requirement in Spira.

    Required:
    - name: Requirement title

    Optional:
    - description: Detailed description (supports HTML)
    - requirement_type_id: Type (project-specific)
    - importance_id: 1=Critical, 2=High, 3=Medium, 4=Low (Spira default — template-specific, see update_requirement note)
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign to
    - parent_requirement_id: Create as a child of this requirement
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
    """
    client = _get_client()
    result = client.create_requirement(
        product_id, name, description,
        requirement_type_id=requirement_type_id,
        importance_id=importance_id,
        owner_id=owner_id,
        release_id=release_id,
        parent_requirement_id=parent_requirement_id,
        custom_properties=_resolved_custom_values(client, product_id, "Requirement", custom_properties),
    )
    req_id = result.get("RequirementId", "?") if isinstance(result, dict) else "?"
    custom_meta = _custom_meta(client, product_id, "Requirement")
    return f"Requirement created: **RQ:{req_id}** — {name}\n\n{formatters.format_requirement(result, custom_meta=custom_meta)}"


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
    custom_properties: dict | None = None,
) -> str:
    """Update a requirement. Only pass the fields you want to change.
    Fields can only be SET, not cleared — None/omitted leaves a field unchanged.

    Note: status/importance IDs are template-specific. The 1=Critical/2=High/3=Medium/4=Low
    mapping is the Spira default but does NOT apply to all instances — many templates use
    custom IDs. To find the valid IDs for this product's template, use the list_artifact_types tool
    (statuses/importances included; use list_custom_properties for custom fields).

    Fields (all optional):
    - name: Requirement title
    - description: Detailed description (supports HTML)
    - requirement_status_id: status ID (template-specific — see note above)
    - importance_id: importance ID (template-specific — see note above)
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign to
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
    """
    updates = {}
    if name is not None:
        updates["Name"] = name
    if description is not None:
        updates["Description"] = description
    if requirement_status_id is not None:
        # PUT-body field is StatusId — "RequirementStatusId" is silently ignored by
        # Spira (fix.md F1). The search FILTER property is RequirementStatusId though;
        # the two namespaces differ — don't unify them (fix.md F2).
        updates["StatusId"] = requirement_status_id
    if importance_id is not None:
        updates["ImportanceId"] = importance_id
    if owner_id is not None:
        updates["OwnerId"] = owner_id
    if release_id is not None:
        updates["ReleaseId"] = release_id

    client = _get_client()
    resolved_customs = _resolved_custom_values(client, product_id, "Requirement", custom_properties)
    if not updates and not resolved_customs:
        return "No fields to update. Pass at least one field to change."

    result = client.update_requirement(product_id, requirement_id, custom_properties=resolved_customs, **updates)
    custom_meta = _custom_meta(client, product_id, "Requirement")
    return f"Requirement RQ:{requirement_id} updated successfully.\n\n{formatters.format_requirement(result, custom_meta=custom_meta)}"


# ──────────────────────────────────────────────
#  Tasks — THE KEY FIX
# ──────────────────────────────────────────────

@mcp.tool()
def list_tasks(
    product_id: int,
    release_id: int | None = None,
    status_id: int | None = None,
    owner_id: int | None = None,
    limit: int | None = None,
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
    - limit: Return at most N tasks (default: all — large products can return thousands)

    Note: status IDs are template-specific — the legend above is the Spira default
    and may not match this instance (see update_task note).
    """
    client = _get_client()
    tasks = client.get_tasks(
        product_id,
        release_id=release_id,
        status_id=status_id,
        owner_id=owner_id,
        limit=limit,
    )
    out = formatters.format_tasks(tasks)
    if limit is not None and len(tasks) == limit:
        out += f"\n\n_Showing first {limit} — more may exist; raise limit or add filters._"
    return out


@mcp.tool()
def get_task(product_id: int, task_id: int) -> str:
    """Get a single task by ID with full details."""
    client = _get_client()
    task = client.get_task(product_id, task_id)
    custom_meta = _custom_meta(client, product_id, "Task")
    return formatters.format_task(task, custom_meta=custom_meta)


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
    custom_properties: dict | None = None,
) -> str:
    """Create a new task in Spira.

    Required:
    - name: Task title

    Optional:
    - description: Detailed description
    - task_status_id: 1=Not Started (default), 2=In Progress, 3=Completed, 4=Blocked, 5=Deferred
    - task_priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
      (status/priority IDs are Spira defaults — template-specific, see update_task note)
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign to
    - requirement_id: Parent requirement to link to
    - estimated_effort: Estimated effort in minutes
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
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
        custom_properties=_resolved_custom_values(client, product_id, "Task", custom_properties),
    )
    task_id = result.get("TaskId", "?") if isinstance(result, dict) else "?"
    custom_meta = _custom_meta(client, product_id, "Task")
    return f"Task created: **TK:{task_id}** — {name}\n\n{formatters.format_task(result, custom_meta=custom_meta)}"


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
    custom_properties: dict | None = None,
) -> str:
    """Update a task. Only pass the fields you want to change.
    Fields can only be SET, not cleared — None/omitted leaves a field unchanged.

    Note: status/priority IDs are template-specific. The defaults below are common but
    do NOT apply to all instances. To find the valid IDs for this product's
    template, use the list_artifact_types tool (statuses/priorities included).

    Fields (all optional):
    - name: Task name
    - description: Task description
    - task_status_id: status ID (template-specific — see note above)
    - task_priority_id: priority ID (template-specific — see note above)
    - owner_id: User ID to assign
    - release_id: Release/sprint to assign the task to
    - estimated_effort: Estimated effort in minutes
    - actual_effort: Actual effort in minutes
    - remaining_effort: Remaining effort in minutes
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
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

    client = _get_client()
    resolved_customs = _resolved_custom_values(client, product_id, "Task", custom_properties)
    if not updates and not resolved_customs:
        return "No fields to update. Pass at least one field to change."

    result = client.update_task(product_id, task_id, custom_properties=resolved_customs, **updates)
    custom_meta = _custom_meta(client, product_id, "Task")
    return f"Task TK:{task_id} updated successfully.\n\n{formatters.format_task(result, custom_meta=custom_meta)}"


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
    custom_property_filters: dict | None = None,
    limit: int | None = None,
) -> str:
    """List incidents for a product with optional filters.

    Filters (all optional):
    - release_id: Filter by detected release
    - status_id: Filter by incident status
    - priority_id: Filter by priority (1=Critical, 2=High, 3=Medium, 4=Low)
    - severity_id: Filter by severity (1=Critical, 2=High, 3=Medium, 4=Low)
    - owner_id: Filter by owner user ID
    - custom_property_filters: {"<custom field name>": <value>} — names and list-option
      labels are resolved against template metadata (discover via list_custom_properties).
      Unknown names/labels error out instead of being silently ignored by Spira.
    - limit: Return at most N incidents (default: all — large products can return thousands)

    Note: status/priority/severity IDs are template-specific — the legends above are
    Spira defaults and may not match this instance (see update_incident note).
    """
    client = _get_client()
    incidents = client.get_incidents(
        product_id,
        release_id=release_id,
        status_id=status_id,
        priority_id=priority_id,
        severity_id=severity_id,
        owner_id=owner_id,
        limit=limit,
        extra_filters=_resolved_custom_filters(client, product_id, "Incident", custom_property_filters),
    )
    out = formatters.format_incidents(incidents)
    if limit is not None and len(incidents) == limit:
        out += f"\n\n_Showing first {limit} — more may exist; raise limit or add filters._"
    return out


@mcp.tool()
def get_incident(product_id: int, incident_id: int) -> str:
    """Get a single incident by ID with full details."""
    client = _get_client()
    incident = client.get_incident(product_id, incident_id)
    custom_meta = _custom_meta(client, product_id, "Incident")
    return formatters.format_incident(incident, custom_meta=custom_meta)


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
    custom_properties: dict | None = None,
) -> str:
    """Create a new incident/bug in Spira.

    Required:
    - name: Incident title

    Optional:
    - description: Detailed description (supports HTML)
    - incident_type_id: Type of incident (project-specific, check get_product for available types)
    - priority_id: 1=Critical, 2=High, 3=Medium, 4=Low
    - severity_id: 1=Critical, 2=High, 3=Medium, 4=Low
      (priority/severity IDs are Spira defaults — template-specific, see update_incident note)
    - owner_id: User ID to assign
    - detected_release_id: Release where the bug was found
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
    """
    client = _get_client()
    result = client.create_incident(
        product_id, name, description,
        incident_type_id=incident_type_id,
        priority_id=priority_id,
        severity_id=severity_id,
        owner_id=owner_id,
        detected_release_id=detected_release_id,
        custom_properties=_resolved_custom_values(client, product_id, "Incident", custom_properties),
    )
    inc_id = result.get("IncidentId", "?") if isinstance(result, dict) else "?"
    custom_meta = _custom_meta(client, product_id, "Incident")
    return f"Incident created: **IN:{inc_id}** — {name}\n\n{formatters.format_incident(result, custom_meta=custom_meta)}"


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
    custom_properties: dict | None = None,
) -> str:
    """Update an incident. Only pass the fields you want to change.
    Fields can only be SET, not cleared — None/omitted leaves a field unchanged.

    Note: status/priority/severity IDs are template-specific. To find the valid IDs for
    this product's template, use the list_artifact_types tool (statuses/priorities/severities included).

    Fields (all optional):
    - name: Incident title
    - description: Detailed description (supports HTML)
    - incident_status_id: status ID (template-specific — see note above)
    - priority_id: priority ID (template-specific — see note above)
    - severity_id: severity ID (template-specific — see note above)
    - owner_id: User ID to assign
    - detected_release_id: Release where the bug was found
    - resolved_release_id: Release where the bug was fixed
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
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

    client = _get_client()
    resolved_customs = _resolved_custom_values(client, product_id, "Incident", custom_properties)
    if not updates and not resolved_customs:
        return "No fields to update. Pass at least one field to change."

    result = client.update_incident(product_id, incident_id, custom_properties=resolved_customs, **updates)
    custom_meta = _custom_meta(client, product_id, "Incident")
    return f"Incident IN:{incident_id} updated successfully.\n\n{formatters.format_incident(result, custom_meta=custom_meta)}"


# ──────────────────────────────────────────────
#  Test Cases
# ──────────────────────────────────────────────

@mcp.tool()
def list_test_cases(
    product_id: int,
    release_id: int | None = None,
    custom_property_filters: dict | None = None,
    limit: int | None = None,
) -> str:
    """List test cases for a product, optionally filtered by release and/or custom fields.

    - release_id: Filter to test cases mapped to this release/sprint
    - custom_property_filters: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"}.
      Names and list-option labels are resolved against template metadata (discover via
      list_custom_properties). Unknown names/labels error out instead of being silently
      ignored by Spira.
    - limit: Return at most N test cases (default: all — large products can return thousands)
    """
    client = _get_client()
    # Root endpoint takes release_id directly and returns full objects; the
    # /releases/{id}/test-cases sub-resource returns bare ID pairs (fix.md F3).
    if custom_property_filters:
        filters = _resolved_custom_filters(client, product_id, "TestCase", custom_property_filters)
        test_cases = client.search_test_cases(product_id, filters, release_id=release_id, limit=limit)
    else:
        test_cases = client.get_test_cases(product_id, release_id=release_id, limit=limit)
    out = formatters.format_test_cases(test_cases)
    if limit is not None and len(test_cases) == limit:
        out += f"\n\n_Showing first {limit} — more may exist; raise limit or add filters._"
    return out


@mcp.tool()
def get_test_case(product_id: int, test_case_id: int) -> str:
    """Get a single test case by ID with its test steps."""
    client = _get_client()
    tc = client.get_test_case(product_id, test_case_id)
    steps = client.get_test_steps(product_id, test_case_id)
    custom_meta = _custom_meta(client, product_id, "TestCase")
    return formatters.format_test_case(tc, steps=steps, custom_meta=custom_meta)


@mcp.tool()
def list_test_coverage(product_id: int, requirement_id: int) -> str:
    """List the test cases covering a requirement (Spira's Test Coverage relationship).

    Test Coverage is the dedicated, first-class link between Requirements and Test Cases
    in Spira. It drives the requirement's CoverageCount* metrics and the "Test Coverage"
    UI tab. It is NOT the same as a generic Association — associations don't count for
    coverage and don't show up in the Test Coverage view.

    Use this tool when you want to know which tests cover a requirement.
    To add or remove a coverage link, use create_test_coverage / delete_test_coverage.
    """
    client = _get_client()
    test_cases = client.get_test_coverage_for_requirement(product_id, requirement_id)
    return formatters.format_test_coverage_for_requirement(requirement_id, test_cases)


@mcp.tool()
def list_covered_requirements(product_id: int, test_case_id: int) -> str:
    """List the requirements a test case covers (reverse of list_test_coverage).

    Same first-class Test Coverage relationship as list_test_coverage, viewed from
    the test case side.
    To add or remove a coverage link, use create_test_coverage / delete_test_coverage.
    """
    client = _get_client()
    requirements = client.get_requirements_covered_by_test_case(product_id, test_case_id)
    return formatters.format_requirements_covered_by_test_case(test_case_id, requirements)


@mcp.tool()
def create_test_coverage(product_id: int, requirement_id: int, test_case_id: int) -> str:
    """Add a Test Coverage link so the test case covers the requirement.

    This is Spira's first-class coverage relationship — it updates the requirement's
    CoverageCount* metrics and shows up in the "Test Coverage" UI tab. Use this (NOT
    create_association) to link a test case to a requirement.
    """
    client = _get_client()
    client.add_test_coverage(product_id, requirement_id, test_case_id)
    return f"Test coverage added: TC:{test_case_id} now covers RQ:{requirement_id}."


@mcp.tool()
def delete_test_coverage(product_id: int, requirement_id: int, test_case_id: int) -> str:
    """Remove a Test Coverage link between a requirement and a test case.

    Use list_test_coverage first to see which test cases cover the requirement.
    """
    client = _get_client()
    client.remove_test_coverage(product_id, requirement_id, test_case_id)
    return f"Test coverage removed: TC:{test_case_id} no longer covers RQ:{requirement_id}."


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
    custom_properties: dict | None = None,
) -> str:
    """Create a new test case in Spira.

    Required:
    - name: Test case title

    Optional:
    - description: Detailed description (supports HTML)
    - test_case_type_id: Type (project-specific)
    - test_case_priority_id: 1=Critical, 2=High, 3=Medium, 4=Low (Spira default — template-specific, see update_test_case note)
    - owner_id: User ID to assign
    - test_case_folder_id: Folder to place it in (null = root)
    - estimated_duration: Estimated duration in minutes
    - tags: Comma-separated tags
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
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
        custom_properties=_resolved_custom_values(client, product_id, "TestCase", custom_properties),
    )
    tc_id = result.get("TestCaseId", "?") if isinstance(result, dict) else "?"
    custom_meta = _custom_meta(client, product_id, "TestCase")
    return f"Test case created: **TC:{tc_id}** — {name}\n\n{formatters.format_test_case(result, custom_meta=custom_meta)}"


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
    custom_properties: dict | None = None,
) -> str:
    """Update a test case. Only pass the fields you want to change — all others are preserved.
    Fields can only be SET, not cleared — None/omitted leaves a field unchanged.

    Automatically handles optimistic concurrency (GETs current state first, then PUTs).

    Note: status/priority IDs are template-specific. The 1=Draft etc. mapping is the
    Spira default but does NOT apply to all instances. To find the valid IDs for this
    product's template, use the list_artifact_types tool (statuses/priorities included).

    Fields (all optional — only pass what you want to change):
    - name: Test case name
    - description: Test case description (supports HTML)
    - test_case_status_id: status ID (template-specific — see note above)
    - test_case_priority_id: priority ID (template-specific — see note above)
    - test_case_type_id: Type of test case
    - owner_id: User ID to assign
    - estimated_duration: Estimated duration in minutes
    - test_case_folder_id: Move to a different folder
    - tags: Comma-separated tags
    - custom_properties: {"<custom field name>": <value>}, e.g. {"Automated": "Yes"} — labels resolved to option IDs via template metadata; unknown names/labels error out
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

    client = _get_client()
    resolved_customs = _resolved_custom_values(client, product_id, "TestCase", custom_properties)
    if not updates and not resolved_customs:
        return "No fields to update. Pass at least one field to change."

    result = client.update_test_case(product_id, test_case_id, custom_properties=resolved_customs, **updates)
    custom_meta = _custom_meta(client, product_id, "TestCase")
    return f"Test case TC:{test_case_id} updated successfully.\n\n{formatters.format_test_case(result, custom_meta=custom_meta)}"


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
def list_test_runs(product_id: int, limit: int | None = None) -> str:
    """List recent test runs for a product, sorted by most recent first.

    - limit: Return at most N runs (default: all — long-lived products accumulate
      thousands of runs; a limit of 20-50 is usually plenty)
    """
    client = _get_client()
    runs = client.get_test_runs(product_id, limit=limit)
    out = formatters.format_test_runs(runs)
    if limit is not None and len(runs) == limit:
        out += f"\n\n_Showing first {limit} — more may exist; raise limit._"
    return out


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
    """Preview test run shells for test cases — shows the steps each run will contain.

    NOTE: shells are NOT persisted (Spira returns them with TestRunId=0). To actually
    execute and save a run, call save_test_run_results with test_case_id — it creates
    the shell, applies your per-step results, and saves, all in one call.

    - test_case_ids: List of test case IDs to preview runs for, e.g. [290, 283]
    - release_id: Optional release to associate the runs with
    """
    client = _get_client()
    runs = client.create_test_runs(product_id, test_case_ids, release_id=release_id)
    if not runs:
        return "No test run shells returned."
    lines = [f"Prepared {len(runs)} test run shell(s) — NOT yet saved:\n"]
    for r in (runs if isinstance(runs, list) else [runs]):
        steps = r.get("TestRunSteps") or []
        positions = [s.get("Position") for s in steps]
        lines.append(
            f"- TC:{r.get('TestCaseId')} — {len(steps)} steps pre-populated "
            f"(positions: {positions})"
        )
    lines.append(
        "\nCall save_test_run_results(test_case_id=..., step_results=[...]) to execute and save."
    )
    return "\n".join(lines)


@mcp.tool()
def save_test_run_results(
    product_id: int,
    step_results: list[dict],
    test_case_id: int | None = None,
    release_id: int | None = None,
    test_run_id: int | None = None,
    end_date: str | None = None,
) -> str:
    """Execute a test case and save per-step results as a new test run (KB684 flow).

    Recommended usage: pass test_case_id — this creates a run shell, applies your
    per-step results, and saves it in ONE call. (Shells are not persisted until
    saved, and Spira rejects re-saving an already-saved run — verified live — so
    the one-shot path is the reliable one.)

    Do NOT set the overall test run status — Spira calculates it from the step statuses.

    Parameters:
    - test_case_id: Test case to execute (recommended path)
    - release_id: Optional release/sprint to record the run against (with test_case_id)
    - test_run_id: ADVANCED alternative — an existing pending run to fill in; most
      instances reject re-saving an already-saved run with a 400
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
    if (test_case_id is None) == (test_run_id is None):
        return ("Provide exactly one of test_case_id (recommended — creates and saves "
                "a new run) or test_run_id (existing pending run).")

    if test_case_id is not None:
        shells = client.create_test_runs(product_id, [test_case_id], release_id=release_id)
        if not shells:
            return f"Could not create a test run shell for TC:{test_case_id}."
        run = shells[0]
    else:
        run = client.get_test_run(product_id, test_run_id)
        if not run:
            return f"Test run #{test_run_id} not found."

    run_label = f"TC:{test_case_id}" if test_case_id is not None else f"#{test_run_id}"
    steps = run.get("TestRunSteps") or []
    if not steps:
        return f"Test run for {run_label} has no steps."

    # Validate every entry up front — a typo'd position used to be silently
    # dropped, saving the run with that step still "Not Run" (fix.md F8).
    valid_positions = sorted(s.get("Position") for s in steps if s.get("Position") is not None)
    result_lookup = {}
    problems = []
    for i, sr in enumerate(step_results, 1):
        if not isinstance(sr, dict) or "position" not in sr or "execution_status_id" not in sr:
            problems.append(f"entry #{i} must be an object with 'position' and 'execution_status_id'")
            continue
        if sr["position"] not in valid_positions:
            problems.append(f"entry #{i}: position {sr['position']} not in this run "
                            f"(valid positions: {valid_positions})")
            continue
        result_lookup[sr["position"]] = sr
    if problems:
        return "step_results invalid — nothing was saved:\n- " + "\n- ".join(problems)

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

    # Set end date. Spira's end_date query param requires yyyy-MM-ddTHH:mm:ss.fff —
    # a trailing 'Z' is rejected with a 406 (verified live).
    if not end_date:
        end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000")
    end_date = end_date.rstrip("Zz")

    run["EndDate"] = end_date
    # Remove overall ExecutionStatusId — let Spira calculate from steps
    run.pop("ExecutionStatusId", None)

    # end_date also goes in the query string per KB684 (fix.md F8)
    result = client.save_test_runs(product_id, [run], end_date)
    saved = result[0] if isinstance(result, list) and result else result
    saved_id = saved.get("TestRunId") if isinstance(saved, dict) else None
    return (f"Test run for {run_label} saved successfully (Run #{saved_id}).\n\n"
            f"{formatters.format_test_run(saved)}")


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
    test_set_id: int | None = None,
    build_id: int | None = None,
) -> str:
    """Record an automated test run result (simple, no per-step detail).

    For per-step results, use save_test_run_results instead.

    execution_status_id: 1=Failed, 2=Passed, 3=Not Run, 4=Not Applicable, 5=Blocked, 6=Caution
    """
    client = _get_client()
    result = client.record_test_run(
        product_id, test_case_id, execution_status_id,
        test_name, short_message, long_message, error_count,
        release_id=release_id, test_set_id=test_set_id, build_id=build_id,
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
    folder_id: int | None = None,
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
    doc = client.upload_document(product_id, filename, binary_data, description, folder_id=folder_id)

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
    import html
    import os

    # Step 1: validate everything and resolve the target BEFORE uploading, so bad
    # input can't orphan an uploaded document (fix.md F9).
    valid_targets = ("test_step", "test_case", "incident", "requirement", "task")
    if target_type not in valid_targets:
        return f"Unknown target_type '{target_type}'. Use: {', '.join(valid_targets)}"

    field_map = {
        "description": "Description",
        "expected_result": "ExpectedResult",
    }
    api_field = field_map.get(field)
    if not api_field:
        return f"Unknown field '{field}'. Use: {', '.join(field_map.keys())}"
    if field == "expected_result" and target_type != "test_step":
        # Only test steps have ExpectedResult — Spira would silently drop the
        # unknown field and the image would be lost (fix.md F9).
        return ("field='expected_result' only exists on test steps. "
                "Use field='description' for other artifact types.")
    if target_type == "test_step" and not test_case_id:
        return "test_case_id is required when target_type is 'test_step'."

    if not os.path.exists(file_path):
        return f"File not found: {file_path}"

    client = _get_client()
    if target_type == "test_step":
        steps = client.get_test_steps(product_id, test_case_id)
        step = next((s for s in steps if s.get("TestStepId") == target_id), None)
        if not step:
            return f"Test step {target_id} not found in TC:{test_case_id}."
        current_content = step.get(api_field) or ""
    elif target_type == "test_case":
        current_content = (client.get_test_case(product_id, target_id) or {}).get(api_field) or ""
    elif target_type == "incident":
        current_content = (client.get_incident(product_id, target_id) or {}).get(api_field) or ""
    elif target_type == "requirement":
        current_content = (client.get_requirement(product_id, target_id) or {}).get(api_field) or ""
    else:  # task
        current_content = (client.get_task(product_id, target_id) or {}).get(api_field) or ""

    # Step 2: upload the file
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        binary_data = base64.b64encode(f.read()).decode("ascii")

    doc = client.upload_document(product_id, filename, binary_data)
    doc_id = doc.get("AttachmentId") if isinstance(doc, dict) else None
    if not doc_id:
        return "Failed to upload document — no AttachmentId returned."

    # Step 3: build the <img> tag (escape user-provided text for the HTML field)
    img_tag = f'<img src="/{product_id}/Attachment/{doc_id}.aspx" alt="{html.escape(filename, quote=True)}" />'
    if caption:
        img_tag = f'<p>{img_tag}</p><p><em>{html.escape(caption)}</em></p>'
    else:
        img_tag = f'<p>{img_tag}</p>'

    # Step 4: append to the target field, preserving existing content
    new_content = current_content + img_tag
    if target_type == "test_step":
        client.update_test_step(product_id, test_case_id, target_id, **{api_field: new_content})
    elif target_type == "test_case":
        client.update_test_case(product_id, target_id, **{api_field: new_content})
    elif target_type == "incident":
        client.update_incident(product_id, target_id, **{api_field: new_content})
    elif target_type == "requirement":
        client.update_requirement(product_id, target_id, **{api_field: new_content})
    else:  # task
        client.update_task(product_id, target_id, **{api_field: new_content})

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
    """Link two Spira artifacts together as a generic Association.

    IMPORTANT — this is NOT the right tool for linking a Test Case to a Requirement.
    Test Case <-> Requirement linking in Spira is a separate first-class relationship
    called "Test Coverage" — it drives the requirement's CoverageCount* metrics and the
    "Test Coverage" UI tab. Generic Associations show up only on the "Associations" tab
    and do NOT count toward coverage. Use list_test_coverage / list_covered_requirements
    to read coverage and create_test_coverage / delete_test_coverage to modify it.

    Use this tool for generic links such as:
    - bug <-> requirement (incident -> requirement)
    - bug <-> test case (incident -> test_case)
    - test case <-> test case (related-to relationships)
    - task <-> task

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


@mcp.tool()
def get_test_set(product_id: int, test_set_id: int) -> str:
    """Get a single test set with its status and per-status execution counts."""
    client = _get_client()
    ts = client.get_test_set(product_id, test_set_id)
    return formatters.format_test_set(ts)


@mcp.tool()
def list_test_set_test_cases(product_id: int, test_set_id: int) -> str:
    """List the test cases that belong to a test set (full details per test case)."""
    client = _get_client()
    test_cases = client.get_test_set_test_cases(product_id, test_set_id)
    return formatters.format_test_cases(test_cases)


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

# Minimal means minimal: resist growing that preset — it exists for tiny contexts.
# Only "full" bypasses filtering entirely (the None sentinel, not an actual list).
# Read_only must never gain a mutating tool; automation relies on that promise.
# Presets are allowlists, not permissions — the API key still gates real access.
# Hence new tools land in "full" automatically but join other presets explicitly.
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
        "list_users", "list_components", "list_comments",
        "get_my_tasks", "get_my_incidents", "get_my_requirements", "get_my_test_cases", "get_my_test_sets",
        "list_releases", "get_release",
        "list_requirements", "get_requirement",
        "list_tasks", "get_task", "count_tasks",
        "list_incidents", "get_incident",
        "list_test_cases", "get_test_case", "list_test_folders",
        "list_test_coverage", "list_covered_requirements",
        "list_test_runs", "get_test_run",
        "list_risks", "list_test_sets", "get_test_set", "list_test_set_test_cases",
        "list_automation_hosts",
        "list_documents", "list_associations",
    ],
    "dev": [
        "list_products", "get_product",
        "get_my_tasks", "get_my_incidents", "get_my_requirements",
        "list_users", "list_components", "list_comments", "add_comment",
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
        "list_users", "list_components", "list_comments", "add_comment",
        "list_releases", "get_release",
        "add_test_cases_to_release", "remove_test_case_from_release",
        "list_requirements", "get_requirement",
        "list_tasks", "get_task", "count_tasks", "update_task",
        "list_incidents", "get_incident", "create_incident", "update_incident",
        "list_test_cases", "get_test_case", "create_test_case", "update_test_case", "list_test_folders",
        "list_test_coverage", "list_covered_requirements", "create_test_coverage", "delete_test_coverage",
        "create_test_step", "update_test_step", "delete_test_step",
        "list_test_runs", "get_test_run", "create_test_run", "save_test_run_results", "record_test_run",
        "list_test_sets", "get_test_set", "list_test_set_test_cases",
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

    Unknown names are reported to stderr; a config that matches no tools at all
    aborts startup instead of silently serving a zero-tool server (fix.md F11).
    """
    tools_config = os.environ.get("SPIRA_MCP_TOOLS", "").strip()
    if not tools_config or tools_config == "full":
        return

    try:
        registered = mcp._tool_manager._tools
    except AttributeError:
        print("spira-mcp: tool filtering unavailable — mcp package internals changed; "
              "running with all tools enabled.", file=sys.stderr)
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
        for name in sorted(allowed - set(registered)):
            print(f"spira-mcp: SPIRA_MCP_TOOLS entry {name!r} matches no tool — ignored. "
                  f"(Presets: {', '.join(sorted(TOOL_PRESETS))})", file=sys.stderr)

    if not allowed & set(registered):
        raise SystemExit(
            f"spira-mcp: SPIRA_MCP_TOOLS={tools_config!r} matches no tools — the server "
            f"would start with zero tools. Valid presets: {', '.join(sorted(TOOL_PRESETS))}."
        )

    # Remove tools not in the allowed set
    for name in list(registered):
        if name not in allowed:
            del registered[name]


# ──────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────

def main():
    _apply_tool_filter()
    mcp.run()


if __name__ == "__main__":
    main()
