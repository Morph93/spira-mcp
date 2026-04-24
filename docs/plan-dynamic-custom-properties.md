# Plan: Dynamic Custom-Property Support

## Background

Spira artifacts (Test Case, Requirement, Task, Incident, Release, Test Set, Test Step)
carry two parallel sets of fields:

- **System fields** — built-in columns like `Status`, `Priority`, `Owner`, `Type`,
  `Automated` (`AutomationTypeId`), etc.
- **Custom fields** — per-template user-defined columns stored as
  `Custom_01` … `Custom_30` and exposed via
  `/project-templates/{template_id}/custom-properties/{artifact_type}`.

Today `spira_mcp`:

1. Reads custom fields but prints the **raw option ID** instead of the label
   (e.g. `Automated: 545` rather than `Automated: Automated`).
2. Offers no way to **filter** by custom fields server-side.
3. Offers no way to **update** custom fields through `update_*` tools.
4. Has a `list_custom_properties` tool whose implementation hardcodes
   `artifact_type_name=Requirements`, so Test-Case / Task / Incident custom
   fields are unreachable.

### Concrete driver

During a TC audit on MDR (PR:33) we found TC41587's custom `Automated` field
flipped from `545 → 2402` between two reads — but the MCP only showed the
numeric codes, so the change was invisible without hitting the REST API
directly. The template metadata decodes `545 = "Automated"` and `2402 = "Blocked"`,
which is the information the caller actually needs.

---

## Design principles

**Everything is driven by template metadata fetched at runtime. Nothing about
field names, list names, option IDs, or labels is hardcoded in the server.**

The only values permitted in code are Spira's own wire-format constants:

- The finite, stable set of Spira artifact type names
  (`TestCase`, `Requirement`, `Task`, `Incident`, `Release`, `TestStep`, `TestSet`).
- The mapping from Spira's `CustomPropertyTypeId` to the JSON payload slot
  (`Text → StringValue`, `List → IntegerValue`, `MultiList → IntegerListValue`,
  `Date → DateTimeValue`, `User → IntegerValue`, `Boolean → BooleanValue`, etc.).

Everything else — field names, dropdown option labels, which custom fields
exist on which template — is discovered dynamically per
`(template_id, artifact_type)` and cached for the process lifetime.

A new custom field added to any template tomorrow must work instantly with
**zero MCP code changes**.

---

## Scope of the fix

### 1. Metadata discovery — `list_custom_properties`

- Accept `artifact_type_name` as a parameter.
  Supported: `TestCase`, `Requirement`, `Task`, `Incident`, `Release`,
  `TestStep`, `TestSet`.
- Accept **either** `template_id` **or** `product_id` — when `product_id` is
  given, resolve the template via `GET /projects/{product_id}.ProjectTemplateId`
  so callers don't have to know the template layout.
- Return every field's `Name`, `CustomPropertyFieldName` (`Custom_XX`),
  `CustomPropertyTypeId`, `CustomPropertyTypeName`, and — for list-type fields
  — the full `CustomList.Values` with `CustomPropertyValueId ↔ Name`.

### 2. Reads — resolve IDs to labels, everywhere

Affected tools:

- `get_test_case`, `list_test_cases`
- `get_requirement`, `list_requirements`
- `get_task`, `list_tasks`
- `get_incident`, `list_incidents`
- `get_release`, `list_releases`
- `get_test_set`, `list_test_sets`
- Any future `get_*` / `list_*` that returns an artifact

Behavior:

- For every `Custom_XX` present on the response, look it up in the cached
  metadata for the artifact's `(template_id, artifact_type)` and render the
  **field's `Name`** alongside the **resolved label** (or raw string/int/date
  for non-list fields).
- **Do not drop the numeric ID** from the representation when it's a list
  type — include both label and ID (e.g. `Automated: Automated (545)`) so
  round-tripping and debugging are trivial.
- Handle all Spira custom-field type IDs, not just list:
  Text, Integer, Decimal, Boolean, Date, User, List (single), MultiList.

### 3. Name collisions: system vs custom

Spira templates can define a custom field whose `Name` matches a system
field (MDR's custom `Automated` vs the built-in `Automated` being the
canonical example). The server must stay unambiguous:

- **Reads:** render both. Suffix the source when they collide:
  ```
  Automated (system): No
  Automated (custom): Automated (545)
  ```
  Non-colliding names render without the suffix.
- **Filters:** try both sides. If the name is unique in the merged set, use
  it. If it's ambiguous, **error out** with a message pointing at the
  `system:` / `custom:` prefix (accepted as an explicit disambiguator).
- **Writes:** no auto-resolution — see §5.

Collision detection itself is dynamic: diff the system-field set (derived
from the artifact response schema) against the custom-field set (from
template metadata) at tool execution time. No baked-in name lists.

### 4. Filters — server-side, via Spira `/search` POST body

Affected tools: `list_test_cases`, `list_requirements`, `list_tasks`,
`list_incidents` (and any future list tool that hits a `/search` endpoint).

Behavior:

- Accept a generic `custom_property_filters` argument, e.g.
  `{"Automated": "Automated", "TA list": "Oncology"}`.
- Resolve each `<name> → Custom_XX` and each `<value> → CustomPropertyValueId`
  (or typed value) against cached metadata.
- Build the Spira filter body dynamically, one entry per filter:
  `{ "PropertyName": "Custom_01", "IntValue": 545 }` (or `StringValue`,
  `DateRangeValue`, list-of-ints for MultiList, etc. — driven by
  `CustomPropertyTypeId`).
- Continue to support existing system filters (`release_id`, `status_id`,
  `priority_id`) side-by-side.

### 5. Writes — explicit, no auto-resolution

Affected tools: `update_test_case`, `update_requirement`, `update_task`,
`update_incident`, plus `create_*` counterparts that already accept
system fields.

Behavior:

- Add a separate parameter — `custom_properties={<name>: <value>, ...}` —
  distinct from the existing system-field params.
  - Accepting labels **or** raw option IDs is fine; the server resolves
    labels to IDs against cached metadata before posting.
  - Anything unresolved raises before the HTTP call — no silent drops.
- Rationale: silent "try both sides" on a write could route an update to the
  wrong field and be invisible until the next read. Separate params make
  misrouting impossible.
- Payload construction picks the correct Spira slot by `CustomPropertyTypeId`
  — the `type → slot` mapping is the only hardcoded bit (see Design
  principles).

### 6. Caching

- One in-process cache keyed by `(template_id, artifact_type_name)`.
- Populated lazily on first need; never expires within a process
  (template metadata is effectively static during an MCP session).
- Cache miss ⇒ one `GET /project-templates/{template_id}/custom-properties/{artifact_type}`
  call.
- Cache is also keyed internally by `CustomPropertyFieldName` and by `Name`
  (plus option lookups `id → label` and `label → id`) so resolution is O(1).

---

## Out of scope (for this iteration)

- Admin operations on templates (create/delete custom properties, edit
  option lists). Read-only metadata is enough for the use cases above.
- Schema validation of user-supplied values beyond what Spira itself
  enforces. If Spira rejects the update, surface the error.
- A UI-style "describe template" tool. `list_custom_properties` already
  covers that once it accepts `artifact_type_name`.

---

## Files likely to change

- `src/spira_mcp/client.py` — new custom-property fetch + cache; filter-body
  builder; write-payload builder; `resolve_label_to_id` / `resolve_id_to_label`
  helpers.
- `src/spira_mcp/formatters.py` — render merged system+custom fields with
  collision suffixes; decode list-type IDs to labels.
- `src/spira_mcp/server.py` — extend tool signatures (`artifact_type_name`
  on `list_custom_properties`; `custom_property_filters` on list tools;
  `custom_properties` on update/create tools).
- `README.md` — document the new parameters and the `system:` / `custom:`
  prefix convention.

---

## Smoke test plan

Using MDR (product 33, template 33) as the reference:

1. `list_custom_properties(product_id=33, artifact_type_name="TestCase")`
   returns the `Automated` field with its full option list (Automated / Blocked
   / In Progress / Need Review / Not applicable / Postponed / None).
2. `get_test_case(product_id=33, test_case_id=41587)` renders both
   `Automated (system)` and `Automated (custom)` with resolved labels.
3. `list_test_cases(product_id=33, custom_property_filters={"Automated": "Automated"})`
   returns only TCs whose custom Automated = 545, server-side filtered.
4. `update_test_case(product_id=33, test_case_id=41587,
   custom_properties={"Automated": "Automated"})` flips the field back to 545
   and the next `get_test_case` shows the change.
5. Repeat (1)–(2) on a non-MDR product (e.g. IQ, PR:43) to confirm
   zero MDR-specific assumptions leaked into the code.

---

## Rollout

Each of §1–§5 can ship as its own commit and be reviewed independently:

1. Discovery (`list_custom_properties`) — unlocks everything else.
2. Reads — decoded output, collision handling.
3. Filters — server-side `custom_property_filters`.
4. Writes — `custom_properties` on update/create.
5. Docs + smoke-test checklist in README.
