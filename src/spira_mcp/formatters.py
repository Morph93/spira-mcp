"""Format Spira API responses into clean markdown for LLM consumption."""

import html as _html
import re as _re


def _strip_html(text, limit=None):
    """Strip rich-text HTML to plain text for LIST views (single-artifact views keep
    full HTML). Saves tokens and keeps excerpts readable (fix.md F21)."""
    if not text:
        return ""
    text = _re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>", " ", text, flags=_re.I)
    text = _re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text)
    text = _re.sub(r"\s+", " ", text).strip()
    return text[:limit] if limit else text


def _v(obj, key, default=""):
    """Like obj.get(key, default), but also applies the default when the value is
    an explicit None — Spira returns nulls, not missing keys (fix.md F16)."""
    val = obj.get(key)
    return default if val is None else val


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


def _custom_props(obj, custom_meta=None):
    """Format custom properties.

    With custom_meta (from client.get_custom_properties_for_artifact_type), resolves
    list-type option IDs to labels (e.g. "545" -> "Automated (545)").
    """
    props = obj.get("CustomProperties")
    if not props:
        return ""
    lines = []
    for p in props:
        defn = p.get("Definition") or {}
        name = defn.get("Name") or defn.get("CustomPropertyFieldName") or "?"
        slot = defn.get("CustomPropertyFieldName")
        val = _resolve_custom_value(p, slot, custom_meta)
        if val not in (None, "", []):
            lines.append(f"  - {name}: {val}")
    if not lines:
        return ""
    return "**Custom Properties:**\n" + "\n".join(lines) + "\n"


def _resolve_custom_value(prop, slot, custom_meta):
    """Resolve a custom-property value, decoding list-type option IDs to labels when metadata exists."""
    options = None
    if custom_meta and slot:
        options = custom_meta.get("options", {}).get(slot)

    int_val = prop.get("IntegerValue")
    int_list = prop.get("IntegerListValue")
    str_val = prop.get("StringValue")
    bool_val = prop.get("BooleanValue")
    date_val = prop.get("DateTimeValue")
    decimal_val = prop.get("DecimalValue")

    if int_val is not None:
        if options:
            label = options["id_to_label"].get(int_val)
            if label is not None:
                return f"{label} ({int_val})"
        return int_val
    if int_list:
        if options:
            return ", ".join(
                f"{options['id_to_label'][v]} ({v})" if v in options["id_to_label"] else str(v)
                for v in int_list
            )
        return ", ".join(str(v) for v in int_list)
    if str_val is not None:
        return str_val
    if bool_val is not None:
        return "Yes" if bool_val else "No"
    if date_val is not None:
        return date_val[:10] if isinstance(date_val, str) else str(date_val)
    if decimal_val is not None:
        return decimal_val
    return None


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
            lines.append(f"  {_strip_html(p['Description'], 200)}")
    return "\n".join(lines)


def format_product(p):
    if not p:
        return "Product not found."
    parts = [
        f"# Product [PR:{p.get('ProjectId')}] — {p.get('Name')}\n",
        _field(p, "Description"),
        _field(p, "CreationDate", "Created"),
        _field(p, "Website"),
        # RemoteProject has ProjectGroupId but no ProjectGroupName (fix.md F7)
        _id_field(p, "ProjectGroupId", "Program", "PG:"),
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
            f"**Tasks:** {_v(r, 'TaskCount', 0)} | **% Complete:** {_v(r, 'PercentComplete', 0)}%\n"
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
        f"**Version:** {_v(r, 'VersionNumber')}\n"
        f"**Start Date:** {(r.get('StartDate') or '')[:10]}\n"
        f"**End Date:** {(r.get('EndDate') or '')[:10]}\n"
        f"**Tasks:** {_v(r, 'TaskCount', 0)} | **% Complete:** {_v(r, 'PercentComplete', 0)}%\n"
        f"**Planned Effort:** {_v(r, 'PlannedEffort', '-')} | **Available Effort:** {_v(r, 'AvailableEffort', '-')}\n"
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
            desc = _strip_html(r["Description"], 500)
            lines.append(f"**Description:** {desc}\n")
    return "\n".join(lines)


def format_requirement(r, children=None, steps=None, custom_meta=None):
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
        _custom_props(r, custom_meta=custom_meta),
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
            f"**Status:** {status} | **Priority:** {_v(t, 'TaskPriorityName', '?')}\n"
            f"**Owner:** {_v(t, 'OwnerName', 'Unassigned')}\n"
            f"**Release:** {_task_release(t)}\n"
            f"**Requirement:** {_task_requirement(t)}\n"
        )
        if t.get("EstimatedEffort") or t.get("ActualEffort"):
            lines.append(
                f"**Estimated:** {_v(t, 'EstimatedEffort', '-')} min | "
                f"**Actual:** {_v(t, 'ActualEffort', '-')} min | "
                f"**Remaining:** {_v(t, 'RemainingEffort', '-')} min\n"
            )
    return "\n".join(lines)


def _task_release(t):
    """'2.1.0 (RL:6601)' or 'Unassigned' — never '(RL:None)'."""
    rel_id = t.get("ReleaseId")
    if rel_id is None:
        return "Unassigned"
    return f"{_v(t, 'ReleaseVersionNumber', '?')} (RL:{rel_id})"


def _task_requirement(t):
    """'Login flow (RQ:45236)' or 'None' — never '(RQ:None)'."""
    req_id = t.get("RequirementId")
    if req_id is None:
        return "None"
    return f"{_v(t, 'RequirementName', '?')} (RQ:{req_id})"


def format_task(t, custom_meta=None):
    if not t:
        return "Task not found."
    status = TASK_STATUSES.get(t.get("TaskStatusId"), f"Status #{t.get('TaskStatusId')}")
    return (
        f"# Task [TK:{t.get('TaskId')}] — {t.get('Name')}\n\n"
        f"**Status:** {status}\n"
        f"**Priority:** {_v(t, 'TaskPriorityName', '?')}\n"
        f"**Owner:** {_v(t, 'OwnerName', 'Unassigned')}\n"
        f"**Release:** {_task_release(t)}\n"
        f"**Requirement:** {_task_requirement(t)}\n"
        f"**Start Date:** {(t.get('StartDate') or '')[:10]}\n"
        f"**End Date:** {(t.get('EndDate') or '')[:10]}\n"
        f"**Created:** {(t.get('CreationDate') or '')[:10]}\n"
        f"**Estimated:** {_v(t, 'EstimatedEffort', '-')} min | "
        f"**Actual:** {_v(t, 'ActualEffort', '-')} min | "
        f"**Remaining:** {_v(t, 'RemainingEffort', '-')} min\n"
        f"{_field(t, 'Description')}"
        f"{_custom_props(t, custom_meta=custom_meta)}"
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


def format_incident(i, custom_meta=None):
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
        f"{_custom_props(i, custom_meta=custom_meta)}"
    )


# ──────────────────────────────────────────────
#  Test Cases
# ──────────────────────────────────────────────

EXECUTION_STATUSES = {
    1: "Failed", 2: "Passed", 3: "Not Run", 4: "Not Applicable",
    5: "Blocked", 6: "Caution",
}


def format_test_coverage_for_requirement(requirement_id, test_cases):
    """Format the list of test cases covering a requirement."""
    if not test_cases:
        return f"# Test Coverage for RQ:{requirement_id}\n\nNo test cases cover this requirement.\n"
    lines = [f"# Test Coverage for RQ:{requirement_id} ({len(test_cases)} test case(s))\n"]
    for tc in test_cases:
        exec_status = EXECUTION_STATUSES.get(tc.get("ExecutionStatusId"), "Not Run")
        lines.append(
            f"- **[TC:{tc.get('TestCaseId')}]** {tc.get('Name', '?')}  \n"
            f"  Status: {tc.get('TestCaseStatusName', '?')} | "
            f"Execution: {exec_status} | "
            f"Priority: {tc.get('TestCasePriorityName', '?')}"
        )
    return "\n".join(lines) + "\n"


def format_requirements_covered_by_test_case(test_case_id, requirements):
    """Format the list of requirements a test case covers."""
    if not requirements:
        return f"# Requirements Covered by TC:{test_case_id}\n\nThis test case does not cover any requirements.\n"
    lines = [f"# Requirements Covered by TC:{test_case_id} ({len(requirements)} requirement(s))\n"]
    for r in requirements:
        lines.append(
            f"- **[RQ:{r.get('RequirementId')}]** {r.get('Name', '?')}  \n"
            f"  Status: {r.get('StatusName', '?')} | "
            f"Importance: {r.get('ImportanceName', '?')} | "
            f"Type: {r.get('RequirementTypeName', '?')}"
        )
    return "\n".join(lines) + "\n"


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


def format_test_case(tc, steps=None, custom_meta=None):
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
        _custom_props(tc, custom_meta=custom_meta),
    ]
    if steps:
        parts.append("\n## Test Steps\n")
        for i, s in enumerate(steps, 1):
            step_id = s.get("TestStepId", "?")
            parts.append(f"### Step {i} (TestStepId: {step_id}): {s.get('Description', '')}\n")
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
        # RunnerName only exists on automated runs; manual runs carry TesterId (fix.md F7)
        runner = r.get("RunnerName") or (
            f"Tester #{r.get('TesterId')}" if r.get("TesterId") else "?")
        lines.append(
            f"## Run #{r.get('TestRunId')} — {r.get('Name', '?')}\n"
            f"**Status:** {exec_status} | "
            f"**Test Case:** TC:{r.get('TestCaseId', '?')}\n"
            f"**Date:** {(r.get('EndDate') or '')[:19]}\n"
            f"**Runner:** {runner}\n"
        )
    return "\n".join(lines)


def format_test_run(r):
    if not r:
        return "Test run not found."
    exec_status = EXECUTION_STATUSES.get(r.get("ExecutionStatusId"), "?")
    parts = [
        f"# Test Run #{r.get('TestRunId')} — {r.get('Name', '?')}\n\n",
        f"**Status:** {exec_status}\n",
        f"**Test Case:** TC:{r.get('TestCaseId', '?')}\n",
        f"**Type:** {'Manual' if r.get('TestRunTypeId') == 1 else 'Automated'}\n",
        f"**Tester:** {r.get('TesterName') or r.get('TesterId', '?')}\n",
        f"**Release:** {r.get('ReleaseVersionNumber', '?')}\n",
        f"**Start:** {(r.get('StartDate') or '')[:19]}\n",
        f"**End:** {(r.get('EndDate') or '')[:19]}\n",
    ]
    steps = r.get("TestRunSteps") or []
    if steps:
        parts.append(f"\n## Test Run Steps ({len(steps)} steps)\n")
        for s in steps:
            step_status = EXECUTION_STATUSES.get(s.get("ExecutionStatusId"), "?")
            pos = s.get("Position", "?")
            parts.append(
                f"### Step {pos} (TestRunStepId: {s.get('TestRunStepId', '?')})\n"
                f"**Status:** {step_status}\n"
                f"**Description:** {s.get('Description', '')}\n"
                f"**Expected Result:** {s.get('ExpectedResult', '')}\n"
                f"**Actual Result:** {s.get('ActualResult', '')}\n"
                f"**Sample Data:** {s.get('SampleData', '')}\n"
            )
    return "".join(parts)


def format_document(d):
    if not d:
        return "Document not found."
    return (
        f"# Document [DC:{d.get('AttachmentId', '?')}] — {d.get('FilenameOrUrl', '?')}\n\n"
        f"**Description:** {d.get('Description', '')}\n"
        f"**Size:** {d.get('Size', '?')} bytes\n"
        f"**Author:** {d.get('AuthorName', '?')}\n"
        f"**Uploaded:** {(d.get('UploadDate') or '')[:19]}\n"
        f"**Version:** {d.get('CurrentVersion', '')}\n"
    )


def format_documents(docs):
    if not docs:
        return "No documents found."
    lines = [f"# Documents ({len(docs)} total)\n"]
    for d in docs:
        lines.append(
            f"- **DC:{d.get('AttachmentId', '?')}** — {d.get('FilenameOrUrl', '?')} "
            f"({d.get('Size', '?')} bytes, {(d.get('UploadDate') or '')[:10]})\n"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Test Case Folders
# ──────────────────────────────────────────────

def format_test_folders(folders):
    if not folders:
        return "No test case folders found."
    lines = ["# Test Case Folders\n"]

    # Build parent-child lookup for indentation
    by_id = {f.get("TestCaseFolderId"): f for f in folders}

    def _depth(folder):
        d = 0
        parent = folder.get("ParentTestCaseFolderId")
        while parent and parent in by_id and d < 10:
            d += 1
            parent = by_id[parent].get("ParentTestCaseFolderId")
        return d

    for f in folders:
        indent = "  " * _depth(f)
        # RemoteTestCaseFolder has no CountTestCases — sum the per-status counts (fix.md F7)
        count = sum(f.get(k) or 0 for k in (
            "CountPassed", "CountFailed", "CountCaution",
            "CountBlocked", "CountNotRun", "CountNotApplicable"))
        lines.append(
            f"{indent}- **Folder #{f.get('TestCaseFolderId', '?')}** — {f.get('Name', '?')} "
            f"({count} test cases)\n"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Associations
# ──────────────────────────────────────────────

ARTIFACT_TYPE_NAMES = {
    1: "Requirement", 2: "Test Case", 3: "Incident", 4: "Release",
    5: "Test Run", 6: "Task", 7: "Test Step", 8: "Test Set",
    9: "Automation Host", 13: "Document", 14: "Risk",
}

LINK_TYPE_NAMES = {
    1: "Related To", 2: "Depends On", 3: "Is Depended On By",
}


def format_associations(associations):
    if not associations:
        return "No associations found."
    lines = [f"# Associations ({len(associations)} total)\n"]
    for a in associations:
        src_type = ARTIFACT_TYPE_NAMES.get(a.get("SourceArtifactTypeId"), "?")
        dest_type = a.get("DestArtifactTypeName") or ARTIFACT_TYPE_NAMES.get(a.get("DestArtifactTypeId"), "?")
        link_type = a.get("ArtifactLinkTypeName") or LINK_TYPE_NAMES.get(a.get("ArtifactLinkTypeId"), "?")
        lines.append(
            f"- **Link #{a.get('ArtifactLinkId', '?')}** — "
            f"{src_type} #{a.get('SourceArtifactId', '?')} → "
            f"{dest_type} #{a.get('DestArtifactId', '?')} "
            f"({a.get('DestArtifactName', '')})\n"
            f"  **Type:** {link_type}"
        )
        if a.get("Comment"):
            lines.append(f" | **Comment:** {a['Comment']}")
        lines.append("\n")
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Programs
# ──────────────────────────────────────────────

def format_programs(programs):
    if not programs:
        return "No programs found."
    lines = ["# Programs\n"]
    for p in programs:
        # v7 returns ProgramId; ProjectGroupId kept as fallback for v6-era shapes (fix.md F7)
        pg_id = p.get("ProgramId", p.get("ProjectGroupId", "?"))
        lines.append(
            f"- **PG:{pg_id}** — {p.get('Name', '?')}\n"
            f"  {_strip_html(p.get('Description'), 200)}\n"
        )
    return "\n".join(lines)


def format_milestones(milestones):
    if not milestones:
        return "No milestones found."
    lines = [f"# Milestones ({len(milestones)} total)\n"]
    for m in milestones:
        # v7 field is StatusName, not MilestoneStatusName (fix.md F7)
        lines.append(
            f"- **ML:{m.get('MilestoneId', '?')}** — {m.get('Name', '?')}\n"
            f"  **Status:** {m.get('StatusName', m.get('MilestoneStatusName', '?'))} | "
            f"**Start:** {(m.get('StartDate') or '')[:10]} | "
            f"**End:** {(m.get('EndDate') or '')[:10]}\n"
        )
    return "\n".join(lines)


def format_capabilities(capabilities):
    if not capabilities:
        return "No capabilities found."
    lines = [f"# Capabilities ({len(capabilities)} total)\n"]
    for c in capabilities:
        lines.append(
            f"- **CP:{c.get('CapabilityId', '?')}** — {c.get('Name', '?')}\n"
            f"  **Status:** {c.get('CapabilityStatusName', '?')} | "
            f"**Priority:** {c.get('CapabilityPriorityName', '?')}\n"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Templates
# ──────────────────────────────────────────────

def format_templates(templates):
    if not templates:
        return "No templates found."
    lines = ["# Product Templates\n"]
    for t in templates:
        lines.append(f"- **PT:{t.get('ProjectTemplateId', '?')}** — {t.get('Name', '?')}\n")
    return "\n".join(lines)


def format_template(t):
    if not t:
        return "Template not found."
    return (
        f"# Template [PT:{t.get('ProjectTemplateId', '?')}] — {t.get('Name', '?')}\n\n"
        f"{_field(t, 'Description')}"
        f"**Active:** {t.get('IsActive', '?')}\n"
    )


def _lookup_item_id(item):
    """Find the *Id value in a template lookup row (RequirementStatusId, PriorityId, …)."""
    for k, v in item.items():
        if k.endswith("Id") and k != "ProjectTemplateId":
            return v
    return "?"


def format_artifact_types(types_by_artifact):
    """Render {artifact: {category: [items]}} — types, statuses, priorities,
    importances, severities per artifact (template-specific IDs)."""
    if not types_by_artifact:
        return "No artifact types found."
    lines = ["# Artifact Types & Template Values\n"]
    for artifact, categories in types_by_artifact.items():
        lines.append(f"\n## {artifact}\n")
        if isinstance(categories, list):  # legacy shape: bare list of types
            categories = {"types": categories}
        for category, items in categories.items():
            lines.append(f"\n### {category}\n")
            for t in (items if isinstance(items, list) else [items]):
                lines.append(f"- **ID {_lookup_item_id(t)}** — {t.get('Name', '?')}\n")
    return "\n".join(lines)


def format_users(users):
    if not users:
        return "No users found."
    lines = [f"# Project Users ({len(users)} total)\n"]
    for u in users:
        name = u.get("FullName") or f"{_v(u, 'FirstName')} {_v(u, 'LastName')}".strip() or _v(u, "UserName", "?")
        lines.append(
            f"- **UserId {u.get('UserId', '?')}** — {name} ({_v(u, 'UserName', '?')}) | "
            f"**Role:** {_v(u, 'ProjectRoleName', '?')} | **Email:** {_v(u, 'EmailAddress', '?')}\n"
        )
    return "\n".join(lines)


def format_components(components):
    if not components:
        return "No components found."
    lines = [f"# Components ({len(components)} total)\n"]
    for c in components:
        active = "" if c.get("IsActive", True) else " (inactive)"
        lines.append(f"- **ComponentId {c.get('ComponentId', '?')}** — {c.get('Name', '?')}{active}\n")
    return "\n".join(lines)


def format_comments(label, comments):
    if not comments:
        return f"No comments on {label}."
    lines = [f"# Comments on {label} ({len(comments)} total)\n"]
    for cm in comments:
        author = cm.get("UserName") or f"UserId {cm.get('UserId', '?')}"
        lines.append(
            f"- **{author}** ({(cm.get('CreationDate') or '')[:16]}): "
            f"{_strip_html(cm.get('Text'))}\n"
        )
    return "\n".join(lines)


def format_test_set(ts):
    if not ts:
        return "Test set not found."
    counts = []
    for key, label in (("CountPassed", "passed"), ("CountFailed", "failed"),
                       ("CountBlocked", "blocked"), ("CountCaution", "caution"),
                       ("CountNotRun", "not run"), ("CountNotApplicable", "n/a")):
        val = ts.get(key)
        if val:
            counts.append(f"{val} {label}")
    return (
        f"# Test Set [TX:{ts.get('TestSetId', '?')}] — {ts.get('Name', '?')}\n\n"
        f"**Status:** {_v(ts, 'TestSetStatusName', '?')}\n"
        f"**Execution:** {', '.join(counts) if counts else 'no results'}\n"
        f"**Release:** {_v(ts, 'ReleaseVersionNumber', 'Unassigned')}\n"
        f"**Planned Date:** {(ts.get('PlannedDate') or '')[:10]}\n"
        f"**Owner:** {_v(ts, 'OwnerName', 'Unassigned')}\n"
        f"{_field(ts, 'Description')}"
    )


def format_custom_properties(artifact_type_name, fields):
    """Format custom-property metadata for one artifact type.

    Shows each field's slot, display name, type, and — for list-type fields — the
    full option list with each option's CustomPropertyValueId.
    """
    if not fields:
        return f"No custom properties defined for {artifact_type_name}."
    lines = [f"# Custom Properties: {artifact_type_name} ({len(fields)} total)\n"]
    for f in fields:
        name = f.get("Name", "?")
        slot = f.get("CustomPropertyFieldName") or f"Custom_{(f.get('PropertyNumber') or 0):02d}"
        type_name = f.get("CustomPropertyTypeName") or f.get("CustomPropertyTypeId", "?")
        lines.append(f"\n## {slot} — {name}\n")
        lines.append(f"**Type:** {type_name}\n")
        custom_list = f.get("CustomList")
        if custom_list:
            list_name = custom_list.get("Name", "?")
            values = custom_list.get("Values") or []
            lines.append(f"**List:** {list_name} ({len(values)} options)\n")
            for v in values:
                vid = v.get("CustomPropertyValueId", "?")
                vname = v.get("Name", "?")
                lines.append(f"- **{vid}** — {vname}\n")
    return "".join(lines)


# ──────────────────────────────────────────────
#  My Work
# ──────────────────────────────────────────────

def format_my_tasks(tasks):
    if not tasks:
        return "No tasks assigned to you."
    lines = [f"# My Tasks ({len(tasks)} total)\n"]
    for t in tasks:
        lines.append(
            f"- **TK:{t.get('TaskId', '?')}** — {t.get('Name', '?')} | "
            f"**Status:** {t.get('TaskStatusName', '?')} | "
            f"**Project:** {t.get('ProjectName', '?')}\n"
        )
    return "\n".join(lines)


def format_my_incidents(incidents):
    if not incidents:
        return "No incidents assigned to you."
    lines = [f"# My Incidents ({len(incidents)} total)\n"]
    for i in incidents:
        lines.append(
            f"- **IN:{i.get('IncidentId', '?')}** — {i.get('Name', '?')} | "
            f"**Status:** {i.get('IncidentStatusName', '?')} | "
            f"**Priority:** {i.get('PriorityName', '?')} | "
            f"**Project:** {i.get('ProjectName', '?')}\n"
        )
    return "\n".join(lines)


def format_my_requirements(requirements):
    if not requirements:
        return "No requirements assigned to you."
    lines = [f"# My Requirements ({len(requirements)} total)\n"]
    for r in requirements:
        lines.append(
            f"- **RQ:{r.get('RequirementId', '?')}** — {r.get('Name', '?')} | "
            f"**Status:** {r.get('StatusName', '?')} | "
            f"**Project:** {r.get('ProjectName', '?')}\n"
        )
    return "\n".join(lines)


def format_my_test_cases(test_cases):
    if not test_cases:
        return "No test cases assigned to you."
    lines = [f"# My Test Cases ({len(test_cases)} total)\n"]
    for tc in test_cases:
        lines.append(
            f"- **TC:{tc.get('TestCaseId', '?')}** — {tc.get('Name', '?')} | "
            f"**Status:** {tc.get('TestCaseStatusName', '?')} | "
            f"**Project:** {tc.get('ProjectName', '?')}\n"
        )
    return "\n".join(lines)


def format_my_test_sets(test_sets):
    if not test_sets:
        return "No test sets assigned to you."
    lines = [f"# My Test Sets ({len(test_sets)} total)\n"]
    for ts in test_sets:
        lines.append(
            f"- **TX:{ts.get('TestSetId', '?')}** — {ts.get('Name', '?')} | "
            f"**Status:** {ts.get('TestSetStatusName', '?')} | "
            f"**Project:** {ts.get('ProjectName', '?')}\n"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Risks
# ──────────────────────────────────────────────

def format_risks(risks):
    if not risks:
        return "No risks found."
    lines = [f"# Risks ({len(risks)} total)\n"]
    for r in risks:
        lines.append(
            f"## [RK:{r.get('RiskId', '?')}] — {r.get('Name', '?')}\n"
            f"**Status:** {r.get('RiskStatusName', '?')} | "
            f"**Type:** {r.get('RiskTypeName', '?')}\n"
            f"**Probability:** {r.get('RiskProbabilityName', '?')} | "
            f"**Impact:** {r.get('RiskImpactName', '?')}\n"
            f"**Owner:** {r.get('OwnerName', 'Unassigned')}\n"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Test Sets
# ──────────────────────────────────────────────

def format_test_sets(test_sets):
    if not test_sets:
        return "No test sets found."
    lines = [f"# Test Sets ({len(test_sets)} total)\n"]
    for ts in test_sets:
        # RemoteTestSet has no ExecutionStatusId — execution state lives in the
        # per-status Count* fields (fix.md F7).
        counts = []
        for key, label in (("CountPassed", "passed"), ("CountFailed", "failed"),
                           ("CountBlocked", "blocked"), ("CountCaution", "caution"),
                           ("CountNotRun", "not run"), ("CountNotApplicable", "n/a")):
            val = ts.get(key)
            if val:
                counts.append(f"{val} {label}")
        exec_summary = ", ".join(counts) if counts else "no results"
        lines.append(
            f"## [TX:{ts.get('TestSetId', '?')}] — {ts.get('Name', '?')}\n"
            f"**Status:** {ts.get('TestSetStatusName', '?')} | "
            f"**Execution:** {exec_summary}\n"
            f"**Planned Date:** {(ts.get('PlannedDate') or '')[:10]}\n"
            f"**Owner:** {ts.get('OwnerName', 'Unassigned')}\n"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────
#  Automation Hosts
# ──────────────────────────────────────────────

def format_automation_hosts(hosts):
    if not hosts:
        return "No automation hosts found."
    lines = [f"# Automation Hosts ({len(hosts)} total)\n"]
    for h in hosts:
        # v7 field is Active; IsActive kept as fallback for older instances (fix.md F7)
        lines.append(
            f"- **AH:{h.get('AutomationHostId', '?')}** — {h.get('Name', '?')}\n"
            f"  **Token:** {h.get('Token', '?')} | "
            f"**Active:** {h.get('Active', h.get('IsActive', '?'))}\n"
        )
    return "\n".join(lines)
