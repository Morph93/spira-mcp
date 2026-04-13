# spira-mcp

MCP server for [Inflectra Spira](https://www.inflectra.com/SpiraPlan/) (SpiraPlan / SpiraTest / SpiraTeam) with proper task filtering and pagination.

## Why this exists

The official `mcp-server-spira` package has critical limitations:

| Issue | `mcp-server-spira` | `spira-mcp` |
|-------|:---:|:---:|
| Tasks filtered by their own release | No — filters via parent requirement's release, misses orphaned tasks | **Yes** — filters by the task's own `ReleaseId` field |
| Pagination | Hardcoded 500 rows, silently drops data | **Proper** — loops until all results fetched |
| Search/filter on artifacts | Only on "specification" tools | **All** list tools accept filters (release, status, priority, owner) |
| Single-item retrieval | Only for products and releases | **All** artifact types (requirement, task, incident, test case) |
| Retry logic | None | **3 retries** with backoff on 5xx and rate limits |
| `release_id=None` bug | Passes literal `"None"` in URL | **Fixed** — omits parameter when not provided |

## Installation

```bash
pip install spira-mcp
```

Or install from source:

```bash
git clone https://github.com/edetek/spira-mcp.git
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
      "mcp__spira__list_tasks",
      "mcp__spira__get_task",
      "mcp__spira__count_tasks",
      "mcp__spira__list_incidents",
      "mcp__spira__get_incident",
      "mcp__spira__list_test_cases",
      "mcp__spira__get_test_case",
      "mcp__spira__list_test_runs",
      "mcp__spira__record_test_run",
      "mcp__spira__create_build"
    ]
  },
  "enableAllProjectMcpServers": true,
  "enabledMcpjsonServers": ["spira"]
}
```

## Available Tools

### Products
- `list_products` — List all accessible products
- `get_product(product_id)` — Get product details

### Releases / Sprints
- `list_releases(product_id, active_only?)` — List releases
- `get_release(product_id, release_id)` — Get release details

### Requirements
- `list_requirements(product_id, release_id?, status_id?, importance_id?, owner_id?)` — Search with filters
- `get_requirement(product_id, requirement_id)` — Get with steps and children

### Tasks
- `list_tasks(product_id, release_id?, status_id?, owner_id?)` — **Filters by task's own release**
- `get_task(product_id, task_id)` — Get full task details
- `count_tasks(product_id, release_id?, status_id?)` — Server-side count

### Incidents
- `list_incidents(product_id, release_id?, status_id?, priority_id?, severity_id?, owner_id?)` — Search with filters
- `get_incident(product_id, incident_id)` — Get full incident details

### Test Cases
- `list_test_cases(product_id, release_id?)` — List with optional release filter
- `get_test_case(product_id, test_case_id)` — Get with test steps

### Test Runs
- `list_test_runs(product_id)` — Recent test runs
- `record_test_run(...)` — Record automated test result

### Builds
- `create_build(...)` — Create a build entry for a release

## Filter Reference

### Requirement Status IDs
1=Requested, 2=Planned, 3=In Progress, 4=Developed, 5=Accepted, 6=Rejected, 7=Under Review, 8=Obsolete, 9=Tested, 10=Completed

### Task Status IDs
1=Not Started, 2=In Progress, 3=Completed, 4=Blocked, 5=Deferred, 6=Rejected, 7=Under Review, 8=Obsolete

### Incident Priority / Severity
1=Critical, 2=High, 3=Medium, 4=Low

### Execution Status IDs
1=Failed, 2=Passed, 3=Not Run, 4=Not Applicable, 5=Blocked, 6=Caution

### Build Status IDs
1=Succeeded, 2=Failed, 3=Unstable, 4=Aborted

## How Task Filtering Works

The Spira REST API v7 has no `POST /tasks/search` endpoint (unlike requirements, incidents, and test cases). This server uses a two-strategy approach:

1. **Try server-side search** — Attempts `POST /tasks/search` with `RemoteFilter[]` (undocumented endpoint that existed in v5, may work on v7)
2. **Fallback to client-side** — Fetches all tasks via `GET /tasks/new` with proper pagination, then filters by the task's own `ReleaseId`, `TaskStatusId`, and `OwnerId` fields

This means tasks are found even when:
- The task has no parent requirement
- The task's requirement is assigned to a different sprint
- The task's requirement has no sprint at all

## License

MIT
