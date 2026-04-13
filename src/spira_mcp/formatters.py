"""Format Spira API responses into clean markdown for LLM consumption."""


def _field(obj, key, label=None, prefix=""):
    """Extract a field value, return formatted string or empty string if missing/None."""
    val = obj.get(key)
    if val is None:
        return ""
    label = label or key
    return f"**{label}:** {prefix}{val}\n"


def _id_field(obj, key, label, prefix):
    """Format an ID field like RQ:123 or TC:456."""
    val = obj.get(key)
    if val is None:
        return ""
    return f"**{label}:** {prefix}{val}\n"


def _custom_props(obj):
    """Format custom properties if present."""
    props = obj.get("CustomProperties")
    if not props:
        return ""
    lines = []
    for p in props:
        name = p.get("Definition", {}).get("Name") or p.get("PropertyNumber", "?")
        val = (p.get("StringValue") or p.get("IntegerValue") or
               p.get("BooleanValue") or p.get("DateTimeValue") or
               p.get("IntegerListValue") or "")
        if val not in (None, "", []):
            lines.append(f"  - {name}: {val}")
    if not lines:
        return ""
    return "**Custom Properties:**\n" + "\n".join(lines) + "\n"


# ──────────────────────────────────────────────
#  Products
# ──────────────────────────────────────────────

def format_products(products):
    if not products:
        return "No products found."
    lines = ["# Products\n"]
    for p in products:
        lines.append(f"- **PR:{p.get('ProjectId')}** — {p.get('Name')}")
        if p.get("Description"):
            lines.append(f"  {p['Description'][:200]}")
    return "\n".join(lines)


def format_product(p):
    if not p:
        return "Product not found."
    parts = [
        f"# Product [PR:{p.get('ProjectId')}] — {p.get('Name')}\n",
        _field(p, "Description"),
        _field(p, "CreationDate", "Created"),
        _field(p, "Website"),
        _field(p, "ProjectGroupName", "Program"),
    ]
    return "".join(parts)


# ──────────────────────────────────────────────
#  Releases
# ──────────────────────────────────────────────

RELEASE_STATUSES = {1: "Planned", 2: "In Progress", 3: "Completed", 4: "Closed", 5: "Deferred", 6: "Cancelled"}
RELEASE_TYPES = {1: "Major Release", 2: "Minor Release", 3: "Sprint/Iteration", 4: "Phase"}


def format_releases(releases):
    if not releases:
        return "No releases found."
    lines = ["# Releases\n"]
    for r in releases:
        status = RELEASE_STATUSES.get(r.get("ReleaseStatusId"), "Unknown")
        rtype = RELEASE_TYPES.get(r.get("ReleaseTypeId"), "")
        start = (r.get("StartDate") or "")[:10]
        end = (r.get("EndDate") or "")[:10]
        lines.append(
            f"## Release [RL:{r.get('ReleaseId')}] — {r.get('Name')}\n"
            f"**Status:** {status} | **Type:** {rtype}\n"
            f"**Start Date:** {start} | **End Date:** {end}\n"
            f"**Tasks:** {r.get('TaskCount', 0)} | **% Complete:** {r.get('PercentComplete', 0)}%\n"
        )
    return "\n".join(lines)


def format_release(r):
    if not r:
        return "Release not found."
    status = RELEASE_STATUSES.get(r.get("ReleaseStatusId"), "Unknown")
    rtype = RELEASE_TYPES.get(r.get("ReleaseTypeId"), "")
    return (
        f"# Release [RL:{r.get('ReleaseId')}] — {r.get('Name')}\n\n"
        f"**Status:** {status} | **Type:** {rtype}\n"
        f"**Version:** {r.get('VersionNumber', '')}\n"
        f"**Start Date:** {(r.get('StartDate') or '')[:10]}\n"
        f"**End Date:** {(r.get('EndDate') or '')[:10]}\n"
        f"**Tasks:** {r.get('TaskCount', 0)} | **% Complete:** {r.get('PercentComplete', 0)}%\n"
        f"**Planned Effort:** {r.get('PlannedEffort', '')} | **Available Effort:** {r.get('AvailableEffort', '')}\n"
        f"{_field(r, 'Description')}"
    )


# ──────────────────────────────────────────────
#  Requirements
# ──────────────────────────────────────────────

def format_requirements(requirements):
    if not requirements:
        return "No requirements found."
    lines = [f"# Requirements ({len(requirements)} total)\n"]
    for r in requirements:
        lines.append(
            f"## [RQ:{r.get('RequirementId')}] — {r.get('Name')}\n"
            f"**Status:** {r.get('StatusName', '?')} | "
            f"**Importance:** {r.get('ImportanceName', '?')} | "
            f"**Type:** {r.get('RequirementTypeName', '?')}\n"
            f"**Release:** {r.get('ReleaseVersionNumber', 'Unassigned')}\n"
            f"**Owner:** {r.get('OwnerName', 'Unassigned')}\n"
        )
        if r.get("Description"):
            desc = r["Description"][:500].replace("\n", " ")
            lines.append(f"**Description:** {desc}\n")
    return "\n".join(lines)


def format_requirement(r, children=None, steps=None):
    if not r:
        return "Requirement not found."
    parts = [
        f"# Requirement [RQ:{r.get('RequirementId')}] — {r.get('Name')}\n\n",
        f"**Status:** {r.get('StatusName', '?')}\n",
        f"**Importance:** {r.get('ImportanceName', '?')}\n",
        f"**Type:** {r.get('RequirementTypeName', '?')}\n",
        f"**Release:** {r.get('ReleaseVersionNumber', 'Unassigned')}\n",
        f"**Owner:** {r.get('OwnerName', 'Unassigned')}\n",
        f"**Created:** {(r.get('CreationDate') or '')[:10]}\n",
        _field(r, "Description"),
        _custom_props(r),
    ]
    if steps:
        parts.append("\n## Requirement Steps\n")
        for i, s in enumerate(steps, 1):
            parts.append(f"{i}. {s.get('Description', '')}\n")
            if s.get("ExpectedResult"):
                parts.append(f"   **Expected:** {s['ExpectedResult']}\n")
    if children:
        parts.append("\n## Child Requirements\n")
        for c in children:
            parts.append(f"- [RQ:{c.get('RequirementId')}] {c.get('Name')} ({c.get('StatusName', '?')})\n")
    return "".join(parts)


# ──────────────────────────────────────────────
#  Tasks
# ──────────────────────────────────────────────

TASK_STATUSES = {
    1: "Not Started", 2: "In Progress", 3: "Completed", 4: "Blocked",
    5: "Deferred", 6: "Rejected", 7: "Under Review", 8: "Obsolete",
}


def format_tasks(tasks):
    if not tasks:
        return "No tasks found."
    lines = [f"# Tasks ({len(tasks)} total)\n"]
    for t in tasks:
        status = TASK_STATUSES.get(t.get("TaskStatusId"), f"Status #{t.get('TaskStatusId')}")
        lines.append(
            f"## [TK:{t.get('TaskId')}] — {t.get('Name')}\n"
            f"**Status:** {status} | **Priority:** {t.get('TaskPriorityName', '?')}\n"
            f"**Owner:** {t.get('OwnerName', 'Unassigned')}\n"
            f"**Release:** {t.get('ReleaseVersionNumber', 'Unassigned')} (RL:{t.get('ReleaseId', '?')})\n"
            f"**Requirement:** {t.get('RequirementName', 'None')} (RQ:{t.get('RequirementId', '?')})\n"
        )
        if t.get("EstimatedEffort") or t.get("ActualEffort"):
            lines.append(
                f"**Estimated:** {t.get('EstimatedEffort', '-')} min | "
                f"**Actual:** {t.get('ActualEffort', '-')} min | "
                f"**Remaining:** {t.get('RemainingEffort', '-')} min\n"
            )
    return "\n".join(lines)


def format_task(t):
    if not t:
        return "Task not found."
    status = TASK_STATUSES.get(t.get("TaskStatusId"), f"Status #{t.get('TaskStatusId')}")
    return (
        f"# Task [TK:{t.get('TaskId')}] — {t.get('Name')}\n\n"
        f"**Status:** {status}\n"
        f"**Priority:** {t.get('TaskPriorityName', '?')}\n"
        f"**Owner:** {t.get('OwnerName', 'Unassigned')}\n"
        f"**Creator:** {t.get('CreatorName', '?')}\n"
        f"**Release:** {t.get('ReleaseVersionNumber', 'Unassigned')} (RL:{t.get('ReleaseId', '?')})\n"
        f"**Requirement:** {t.get('RequirementName', 'None')} (RQ:{t.get('RequirementId', '?')})\n"
        f"**Start Date:** {(t.get('StartDate') or '')[:10]}\n"
        f"**End Date:** {(t.get('EndDate') or '')[:10]}\n"
        f"**Created:** {(t.get('CreationDate') or '')[:10]}\n"
        f"**Estimated:** {t.get('EstimatedEffort', '-')} min | "
        f"**Actual:** {t.get('ActualEffort', '-')} min | "
        f"**Remaining:** {t.get('RemainingEffort', '-')} min\n"
        f"{_field(t, 'Description')}"
        f"{_custom_props(t)}"
    )


# ──────────────────────────────────────────────
#  Incidents
# ──────────────────────────────────────────────

def format_incidents(incidents):
    if not incidents:
        return "No incidents found."
    lines = [f"# Incidents ({len(incidents)} total)\n"]
    for i in incidents:
        lines.append(
            f"## [IN:{i.get('IncidentId')}] — {i.get('Name')}\n"
            f"**Status:** {i.get('IncidentStatusName', '?')} | "
            f"**Priority:** {i.get('PriorityName', '?')} | "
            f"**Severity:** {i.get('SeverityName', '?')}\n"
            f"**Type:** {i.get('IncidentTypeName', '?')}\n"
            f"**Owner:** {i.get('OwnerName', 'Unassigned')} | "
            f"**Opener:** {i.get('OpenerName', '?')}\n"
            f"**Detected Release:** {i.get('DetectedReleaseVersionNumber', '?')}\n"
            f"**Resolved Release:** {i.get('ResolvedReleaseVersionNumber', '?')}\n"
        )
    return "\n".join(lines)


def format_incident(i):
    if not i:
        return "Incident not found."
    return (
        f"# Incident [IN:{i.get('IncidentId')}] — {i.get('Name')}\n\n"
        f"**Status:** {i.get('IncidentStatusName', '?')}\n"
        f"**Priority:** {i.get('PriorityName', '?')}\n"
        f"**Severity:** {i.get('SeverityName', '?')}\n"
        f"**Type:** {i.get('IncidentTypeName', '?')}\n"
        f"**Owner:** {i.get('OwnerName', 'Unassigned')}\n"
        f"**Opener:** {i.get('OpenerName', '?')}\n"
        f"**Detected Release:** {i.get('DetectedReleaseVersionNumber', '?')}\n"
        f"**Resolved Release:** {i.get('ResolvedReleaseVersionNumber', '?')}\n"
        f"**Created:** {(i.get('CreationDate') or '')[:10]}\n"
        f"**Closed:** {(i.get('ClosedDate') or '')[:10]}\n"
        f"{_field(i, 'Description')}"
        f"{_custom_props(i)}"
    )


# ──────────────────────────────────────────────
#  Test Cases
# ──────────────────────────────────────────────

EXECUTION_STATUSES = {
    1: "Failed", 2: "Passed", 3: "Not Run", 4: "Not Applicable",
    5: "Blocked", 6: "Caution",
}


def format_test_cases(test_cases):
    if not test_cases:
        return "No test cases found."
    lines = [f"# Test Cases ({len(test_cases)} total)\n"]
    for tc in test_cases:
        exec_status = EXECUTION_STATUSES.get(tc.get("ExecutionStatusId"), "?")
        lines.append(
            f"## [TC:{tc.get('TestCaseId')}] — {tc.get('Name')}\n"
            f"**Status:** {tc.get('TestCaseStatusName', '?')} | "
            f"**Execution:** {exec_status} | "
            f"**Priority:** {tc.get('TestCasePriorityName', '?')}\n"
            f"**Owner:** {tc.get('OwnerName', 'Unassigned')}\n"
            f"**Type:** {tc.get('TestCaseTypeName', '?')}\n"
        )
    return "\n".join(lines)


def format_test_case(tc, steps=None):
    if not tc:
        return "Test case not found."
    exec_status = EXECUTION_STATUSES.get(tc.get("ExecutionStatusId"), "?")
    parts = [
        f"# Test Case [TC:{tc.get('TestCaseId')}] — {tc.get('Name')}\n\n",
        f"**Status:** {tc.get('TestCaseStatusName', '?')}\n",
        f"**Execution:** {exec_status}\n",
        f"**Priority:** {tc.get('TestCasePriorityName', '?')}\n",
        f"**Type:** {tc.get('TestCaseTypeName', '?')}\n",
        f"**Owner:** {tc.get('OwnerName', 'Unassigned')}\n",
        f"**Author:** {tc.get('AuthorName', '?')}\n",
        f"**Created:** {(tc.get('CreationDate') or '')[:10]}\n",
        f"**Automated:** {'Yes' if tc.get('AutomationEngineId') else 'No'}\n",
        _field(tc, "Description"),
        _custom_props(tc),
    ]
    if steps:
        parts.append("\n## Test Steps\n")
        for i, s in enumerate(steps, 1):
            parts.append(f"### Step {i}: {s.get('Description', '')}\n")
            if s.get("ExpectedResult"):
                parts.append(f"**Expected Result:** {s['ExpectedResult']}\n")
            if s.get("SampleData"):
                parts.append(f"**Sample Data:** {s['SampleData']}\n")
    return "".join(parts)


# ──────────────────────────────────────────────
#  Test Runs
# ──────────────────────────────────────────────

def format_test_runs(runs):
    if not runs:
        return "No test runs found."
    lines = [f"# Test Runs ({len(runs)} total)\n"]
    for r in runs:
        exec_status = EXECUTION_STATUSES.get(r.get("ExecutionStatusId"), "?")
        lines.append(
            f"## Run #{r.get('TestRunId')} — {r.get('Name', '?')}\n"
            f"**Status:** {exec_status} | "
            f"**Test Case:** TC:{r.get('TestCaseId', '?')}\n"
            f"**Date:** {(r.get('EndDate') or '')[:19]}\n"
            f"**Runner:** {r.get('RunnerName', '?')}\n"
        )
    return "\n".join(lines)
