# spira-mcp

MCP server for [Inflectra Spira](https://www.inflectra.com/SpiraPlan/) (SpiraPlan / SpiraTest / SpiraTeam) with proper task filtering, pagination, and full CRUD support — 38 tools.

## Why this exists

The official `mcp-server-spira` package has critical limitations:

| Issue | `mcp-server-spira` | `spira-mcp` |
|-------|:---:|:---:|
| Tasks filtered by their own release | No — filters via parent requirement's release, misses orphaned tasks | **Yes** — filters by the task's own `ReleaseId` field |
| Pagination | Hardcoded 500 rows, silently drops data | **Proper** — loops until all results fetched |
| Search/filter on artifacts | Only on "specification" tools | **All** list tools accept filters (release, status, priority, owner) |
| Single-item retrieval | Only for products and releases | **All** artifact types |
| Create/update artifacts | Only `create_build` and `record_test_run` | **Full CRUD** for requirements, tasks, incidents, test cases, test steps |
| Per-step test results | Not supported | **Full support** — create run, fill per-step pass/fail + actual results |
| Image embedding | Not supported | **`attach_image_to_field`** — inline images visible in Spira UI |
| Artifact linking | Not supported | **`create_association`** — link any two artifacts (RQ↔TC, IN↔RQ, etc.) |
| Retry logic | None | **3 retries** with backoff on 5xx and rate limits |
| `release_id=None` bug | Passes literal `"None"` in URL | **Fixed** |

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

### Claude Code — `.mcp.json`

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

### Pre-authorize tools (`.claude/settings.local.json`)

```json
{
  "permissions": {
    "allow": [
      "mcp__spira__list_products",
      "mcp__spira__get_product",
      "mcp__spira__list_releases",
      "mcp__spira__get_release",
      "mcp__spira__list_requirements",
      "mcp__spira__get_requirement",
      "mcp__spira__create_requirement",
      "mcp__spira__update_requirement",
      "mcp__spira__list_tasks",
      "mcp__spira__get_task",
      "mcp__spira__count_tasks",
      "mcp__spira__create_task",
      "mcp__spira__update_task",
      "mcp__spira__list_incidents",
      "mcp__spira__get_incident",
      "mcp__spira__create_incident",
      "mcp__spira__update_incident",
      "mcp__spira__list_test_cases",
      "mcp__spira__get_test_case",
      "mcp__spira__create_test_case",
      "mcp__spira__update_test_case",
      "mcp__spira__list_test_folders",
      "mcp__spira__create_test_step",
      "mcp__spira__update_test_step",
      "mcp__spira__delete_test_step",
      "mcp__spira__list_test_runs",
      "mcp__spira__get_test_run",
      "mcp__spira__create_test_run",
      "mcp__spira__save_test_run_results",
      "mcp__spira__record_test_run",
      "mcp__spira__upload_document",
      "mcp__spira__attach_document",
      "mcp__spira__attach_image_to_field",
      "mcp__spira__list_documents",
      "mcp__spira__create_association",
      "mcp__spira__list_associations",
      "mcp__spira__delete_association",
      "mcp__spira__create_build"
    ]
  },
  "enableAllProjectMcpServers": true,
  "enabledMcpjsonServers": ["spira"]
}
```

## Available Tools (38)

### Products
- `list_products` — List all accessible products
- `get_product` — Get product details by ID

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

### Test Cases
- `list_test_cases` — List with optional release filter
- `get_test_case` — Get TC with test steps (shows `TestStepId` per step)
- `create_test_case` — Create new TC with type, priority, folder, tags
- `update_test_case` — Update status, priority, owner, folder (move), tags
- `list_test_folders` — Browse folder hierarchy to find folder IDs for moves

### Test Steps
- `create_test_step` — Add a new step to a test case
- `update_test_step` — Update description, expected result, sample data
- `delete_test_step` — Remove a step from a test case

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

### Associations (Linking)
- `create_association` — Link any two artifacts (RQ↔TC, IN↔RQ, IN↔TC, etc.)
- `list_associations` — See existing links on an artifact
- `delete_association` — Remove a link

### Builds
- `create_build` — Create a build entry for a release with commit references

## Filter Reference

### Requirement Status IDs
1=Requested, 2=Planned, 3=In Progress, 4=Developed, 5=Accepted, 6=Rejected, 7=Under Review, 8=Obsolete, 9=Tested, 10=Completed

### Task Status IDs
1=Not Started, 2=In Progress, 3=Completed, 4=Blocked, 5=Deferred, 6=Rejected, 7=Under Review, 8=Obsolete

### Incident Priority / Severity
1=Critical, 2=High, 3=Medium, 4=Low

### Test Case Status IDs
1=Draft, 2=Ready for Review, 3=Rejected, 4=Approved, 5=Obsolete, 6=Ready for Test, 7=Tested

### Execution Status IDs
1=Failed, 2=Passed, 3=Not Run, 4=Not Applicable, 5=Blocked, 6=Caution

### Build Status IDs
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
