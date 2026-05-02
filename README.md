# spira-mcp

MCP server for [Inflectra Spira](https://www.inflectra.com/SpiraPlan/) (SpiraPlan / SpiraTest / SpiraTeam) with proper task filtering, pagination, and full CRUD support — 56 tools.

## Why this exists

The official `mcp-server-spira` package has critical limitations:

| Issue | `mcp-server-spira` | `spira-mcp` |
|-------|:---:|:---:|
| Tasks filtered by their own release | No — filters via parent requirement's release, misses orphaned tasks | **Yes** — filters by the task's own `ReleaseId` field |
| Pagination | Hardcoded 500 rows, silently drops data | **Proper** — loops until all results fetched |
| Search/filter on artifacts | Only on "specification" tools | **All** list tools accept filters (release, status, priority, owner) |
| Single-item retrieval | Only for products and releases | **All** artifact types (requirement, task, incident, test case, test run) |
| Create/update artifacts | Only `create_build` and `record_test_run` | **Full CRUD** for requirements, tasks, incidents, test cases, test steps |
| Per-step test results | Not supported | **Full support** — create run, fill per-step pass/fail + actual results |
| Image embedding | Not supported | **`attach_image_to_field`** — inline `<img>` tags visible in Spira UI |
| Test Coverage (Requirement ↔ Test Case) | Not surfaced | **`list_test_coverage` / `list_covered_requirements`** — read Spira's first-class coverage relationship (the one that drives coverage metrics) |
| Generic associations | Not supported | **`create_association`** — link any two artifacts (incident ↔ requirement, etc.) |
| Custom properties | Raw IDs, no label resolution | **Indexed metadata + label resolution** — list values render as `Label (id)`, falsy values stay visible |
| Document management | Not supported | **Upload, attach, list** documents on any artifact |
| Test case folders | Not supported | **`list_test_folders`** — browse hierarchy, move TCs between folders |
| Test step IDs in output | Steps shown as ordinals only (Step 1, 2, 3) | **`TestStepId`** shown per step — enables precise updates |
| Release listing | No sorting, `active_only` hardcoded to true | **Sorted by date** (most recent first), all types mixed, configurable `active_only` and `limit` |
| Retry logic | None | **3 retries** with backoff on 5xx and rate limits |
| `release_id=None` bug | Passes literal `"None"` in URL | **Fixed** — omits parameter when not provided |
| Task fetch endpoint | Uses `/tasks/new` with `creation_date=1900-01-01` | **Proper date**, with server-side search fallback |

## Installation

```bash
pip install git+https://github.com/Morph93/spira-mcp.git
```

Or clone and install locally:

```bash
git clone https://github.com/Morph93/spira-mcp.git
cd spira-mcp
pip install -e .
```

## Configuration

### Environment Variables

```bash
export INFLECTRA_SPIRA_BASE_URL="https://your-instance.spiraservice.net"
export INFLECTRA_SPIRA_USERNAME="your.email@company.com"
export INFLECTRA_SPIRA_API_KEY="{YOUR-API-KEY-GUID}"
```

### MCP client configuration

Any MCP-compatible client can launch the server with `python3 -m spira_mcp`. Example config:

```json
{
  "mcpServers": {
    "spira": {
      "command": "python3",
      "args": ["-m", "spira_mcp"],
      "env": {
        "INFLECTRA_SPIRA_BASE_URL": "https://your-instance.spiraservice.net",
        "INFLECTRA_SPIRA_USERNAME": "your.email@company.com",
        "INFLECTRA_SPIRA_API_KEY": "{YOUR-API-KEY-GUID}"
      }
    }
  }
}
```

### Tool Filtering (optional)

By default all 56 tools are exposed. To limit which tools are available, set the `SPIRA_MCP_TOOLS` environment variable to a **preset name** or a **comma-separated list of tool names**.

**Presets:**

| Preset | Tools | Description |
|--------|:-----:|-------------|
| `full` | 56 | All tools (default) |
| `qa` | 43 | QA-focused: test cases, test runs, incidents, coverage, documents, associations |
| `dev` | 22 | Dev-focused: tasks, requirements, incidents, risks, associations |
| `read_only` | 36 | All list/get tools, no create/update/delete |
| `minimal` | 12 | Just list/get for core artifacts (products, releases, requirements, tasks, incidents, test cases) |

**Using a preset:**

```json
{
  "mcpServers": {
    "spira": {
      "command": "python3",
      "args": ["-m", "spira_mcp"],
      "env": {
        "INFLECTRA_SPIRA_BASE_URL": "https://your-instance.spiraservice.net",
        "INFLECTRA_SPIRA_USERNAME": "your.email@company.com",
        "INFLECTRA_SPIRA_API_KEY": "{YOUR-API-KEY-GUID}",
        "SPIRA_MCP_TOOLS": "qa"
      }
    }
  }
}
```

**Using a custom list:**

```json
{
  "env": {
    "SPIRA_MCP_TOOLS": "list_products,get_product,list_tasks,get_task,list_incidents,get_incident"
  }
}
```

## Available Tools (56)

### Products
- `list_products` — List all accessible products
- `get_product` — Get product details by ID

### Programs
- `list_programs` — List all programs (groups of products)
- `list_program_products` — List products belonging to a program
- `list_milestones` — List milestones for a program
- `list_capabilities` — List capabilities for a program

### Templates & Configuration
- `list_templates` — List all product templates
- `get_template` — Get template details
- `list_artifact_types` — List artifact types (requirement types, incident types, etc.) for a template — use to discover valid type IDs
- `list_custom_properties` — Custom fields for one artifact type, with full option lists. Takes `artifact_type_name` (TestCase/Requirement/Task/Incident/Risk/Release/TestSet/TestStep) and either `template_id` or `product_id`. Resolves list-value IDs to their labels in artifact output.

### My Work
- `get_my_tasks` — Tasks assigned to current user, across all products
- `get_my_incidents` — Incidents assigned to current user, across all products
- `get_my_requirements` — Requirements assigned to current user, across all products
- `get_my_test_cases` — Test cases assigned to current user, across all products
- `get_my_test_sets` — Test sets assigned to current user, across all products

### Releases / Sprints
- `list_releases` — List releases sorted by date (all types mixed), with `limit` param
- `get_release` — Get single release details

### Requirements
- `list_requirements` — Search with filters (release, status, importance, owner)
- `get_requirement` — Get requirement with steps and children
- `create_requirement` — Create new requirement, optionally as child of another
- `update_requirement` — Update status, importance, owner, release

### Tasks
- `list_tasks` — **Filters by task's OWN release** (key fix over mcp-server-spira)
- `get_task` — Get single task with full details
- `count_tasks` — Server-side count with filters (fast, no data transfer)
- `create_task` — Create task with status, priority, owner, release, requirement link
- `update_task` — Update status, effort, owner, release

### Incidents
- `list_incidents` — Search with filters (release, status, priority, severity, owner)
- `get_incident` — Get single incident with full details
- `create_incident` — Create new bug with type, priority, severity, owner, release
- `update_incident` — Update status, priority, assign, set resolved release

### Risks
- `list_risks` — List risks for a product, optionally filtered by release

### Test Cases
- `list_test_cases` — List with optional release filter
- `get_test_case` — Get TC with test steps (shows `TestStepId` per step)
- `create_test_case` — Create new TC with type, priority, folder, tags
- `update_test_case` — Update status, priority, owner, folder (move), tags
- `list_test_folders` — Browse folder hierarchy to find folder IDs for moves

### Test Coverage (Requirement ↔ Test Case)

Spira's first-class coverage relationship — the one that drives the requirement's `CoverageCount*` metrics and the "Test Coverage" UI tab. **Distinct from generic Associations** — associations don't count toward coverage and don't show up in the Test Coverage view.

- `list_test_coverage` — Test cases covering a requirement (with execution status of each)
- `list_covered_requirements` — Requirements a test case covers

> Coverage is **read-only** through the Spira REST API in current Spira versions. To add or remove a coverage link, use the Spira UI's Test Coverage tab on the requirement (or the test case's Requirements tab).

### Test Steps
- `create_test_step` — Add a new step to a test case
- `update_test_step` — Update description, expected result, sample data
- `delete_test_step` — Remove a step from a test case

### Test Sets
- `list_test_sets` — List all test sets for a product (root-level + folder-nested, deduped)

### Test Runs
- `list_test_runs` — List recent runs sorted by date
- `get_test_run` — Get run with per-step results (status, actual result)
- `create_test_run` — Create run shells from TC IDs with steps pre-populated
- `save_test_run_results` — Save per-step pass/fail and actual result text
- `record_test_run` — Quick automated result (overall pass/fail, supports release and build)

### Documents & Images
- `upload_document` — Upload file to Spira (for logs, CSVs, non-visual attachments)
- `attach_document` — Attach existing document to artifact's Attachments tab
- `attach_image_to_field` — Upload and embed image inline in a rich-text field (the only way to make images visible in Spira UI)
- `list_documents` — List documents attached to an artifact

### Associations (Generic Linking)

For generic free-form links between artifacts. **Not for Test Case ↔ Requirement** — that's Test Coverage (see above), which is a separate Spira concept.

- `create_association` — Link two artifacts (e.g. incident ↔ requirement, incident ↔ test case, task ↔ task)
- `list_associations` — See existing links on an artifact
- `delete_association` — Remove a link

### Automation Hosts
- `list_automation_hosts` — List automation hosts configured for a product

### Builds
- `create_build` — Create a build entry for a release with commit references

## Filter Reference

> ⚠️ Status / priority / importance / severity IDs are **template-specific** and are **not** universal across Spira instances. The Spira-default mappings (e.g. `1=Critical, 2=High, ...`) only apply to templates that haven't customised these lists. To find the valid IDs for your product's template, query the discovery endpoints:
>
> - Requirement importance: `/project-templates/{template_id}/requirements/importances`
> - Requirement / task status: `/project-templates/{template_id}/{requirements|tasks}/statuses`
> - Task priority: `/project-templates/{template_id}/tasks/priorities`
> - Incident priority / severity / status: `/project-templates/{template_id}/incidents/{priorities|severities|statuses}`
> - Test case priority / status: `/project-templates/{template_id}/test-cases/{priorities|statuses}`
>
> Pass `product_id` instead of `template_id` to most tools and the server resolves the template automatically.

### Execution Status IDs (typically stable across templates)
1=Failed, 2=Passed, 3=Not Run, 4=Not Applicable, 5=Blocked, 6=Caution

### Build Status IDs (typically stable across templates)
1=Succeeded, 2=Failed, 3=Unstable, 4=Aborted

### Association Link Types
- `related` — General relationship (default)
- `depends_on` — Source depends on destination
- `is_depended_on_by` — Source is depended on by destination

### Artifact Types (for associations and documents)
requirement, test_case, incident, release, test_run, task, test_step, test_set, document, risk

## How Task Filtering Works

The Spira REST API v7 has no `POST /tasks/search` endpoint (unlike requirements, incidents, and test cases). This server uses a two-strategy approach:

1. **Try server-side search** — Attempts `POST /tasks/search` with `RemoteFilter[]` (undocumented endpoint that existed in v5, may work on v7)
2. **Fallback to client-side** — Fetches all tasks via `GET /tasks/new` with proper pagination, then filters by the task's own `ReleaseId`, `TaskStatusId`, and `OwnerId` fields

This means tasks are found even when:
- The task has no parent requirement
- The task's requirement is assigned to a different sprint
- The task's requirement has no sprint at all

## How Image Embedding Works

Spira's web UI does not display artifact-level attachments inside rich-text fields. To make an image visible inline (in test step descriptions, incident descriptions, etc.), you must embed an `<img>` tag pointing to Spira's internal attachment URL.

`attach_image_to_field` handles this automatically:
1. Uploads the file to Spira
2. Gets the document ID
3. Builds `<img src="/{product_id}/Attachment/{doc_id}.aspx" />`
4. Appends it to the target field while preserving existing content

Use `upload_document` / `attach_document` only for non-visual files (logs, CSVs) or artifacts that have an Attachments tab.

## License

MIT
