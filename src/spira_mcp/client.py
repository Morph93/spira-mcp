"""Spira REST API v7 client with proper pagination and filtering."""

import time
import requests


SUPPORTED_ARTIFACT_TYPES = frozenset({
    "Requirement", "TestCase", "Task", "Incident",
    "Risk", "Release", "TestSet", "TestStep", "TestRun",
})

# Per-process caches — template metadata is effectively static during an MCP session.
_CUSTOM_PROPS_CACHE = {}      # (template_id, artifact_type_name) -> indexed metadata
_PRODUCT_TEMPLATE_CACHE = {}  # product_id -> template_id


# CustomPropertyTypeId -> artifact-body value slot. Per the design rules in
# docs/plan-dynamic-custom-properties.md this wire-format mapping is the ONLY
# hardcoded piece of the custom-property system — everything else (field names,
# option labels/IDs) is resolved from template metadata at runtime.
CUSTOM_PROP_VALUE_SLOTS = {
    1: "StringValue",       # Text
    2: "IntegerValue",      # Integer
    3: "DecimalValue",      # Decimal
    4: "BooleanValue",      # Boolean
    5: "DateTimeValue",     # Date
    6: "IntegerValue",      # List (option id)
    7: "IntegerListValue",  # MultiList (option ids)
    8: "IntegerValue",      # User (user id)
    10: "IntegerValue",     # Release (release id)
}


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    if s in ("false", "no", "n", "0"):
        return False
    raise ValueError(f"Cannot interpret {value!r} as a boolean")


def _resolve_custom_field(meta, name):
    """Find a custom-property field by display name or Custom_XX slot. Errors out on
    unknown names — Spira silently ignores unknown filter properties and returns the
    full unfiltered list (fix.md F2), so nothing unvalidated may ever be sent."""
    field = meta["by_name"].get(name) or meta["by_slot"].get(name)
    if not field:
        available = sorted(meta["by_name"])
        raise ValueError(
            f"Unknown custom property {name!r}. "
            f"Available: {', '.join(available) or '(none defined for this artifact type)'}"
        )
    return field


def _resolve_option_id(meta, field, value):
    """Resolve a list-option label (or validate a raw option id) to the option id."""
    slot = field.get("CustomPropertyFieldName")
    options = meta["options"].get(slot) or {"label_to_id": {}, "id_to_label": {}}
    if isinstance(value, int) and not isinstance(value, bool):
        if value in options["id_to_label"]:
            return value
        raise ValueError(
            f"{value} is not a valid option id for {field.get('Name')!r}. "
            f"Options: " + ", ".join(f"{i}={l}" for i, l in options["id_to_label"].items())
        )
    label = str(value)
    if label in options["label_to_id"]:
        return options["label_to_id"][label]
    raise ValueError(
        f"{label!r} is not a valid option for {field.get('Name')!r}. "
        f"Options: {', '.join(options['label_to_id']) or '(none)'}"
    )


def resolve_custom_filters(meta, name_to_value):
    """Resolve {field name or Custom_XX: value} into validated RemoteFilter entries."""
    entries = []
    for name, value in (name_to_value or {}).items():
        field = _resolve_custom_field(meta, name)
        slot = field["CustomPropertyFieldName"]
        type_id = field.get("CustomPropertyTypeId")
        f = {"PropertyName": slot}
        if type_id == 1:
            f["StringValue"] = str(value)
        elif type_id in (2, 8, 10):
            f["IntValue"] = int(value)
        elif type_id == 4:
            f["IntValue"] = 1 if _parse_bool(value) else 0
        elif type_id == 6:
            f["IntValue"] = _resolve_option_id(meta, field, value)
        elif type_id == 7:
            vals = value if isinstance(value, (list, tuple)) else [value]
            f["MultiValue"] = [_resolve_option_id(meta, field, v) for v in vals]
        else:
            raise ValueError(
                f"Filtering on custom property type "
                f"{field.get('CustomPropertyTypeName') or type_id} ({field.get('Name')!r}) "
                f"is not supported"
            )
        entries.append(f)
    return entries


def resolve_custom_values(meta, name_to_value):
    """Resolve {field name: value} into artifact-body CustomProperties entries."""
    entries = []
    for name, value in (name_to_value or {}).items():
        field = _resolve_custom_field(meta, name)
        slot = field["CustomPropertyFieldName"]
        type_id = field.get("CustomPropertyTypeId")
        num = field.get("PropertyNumber")
        if num is None:
            try:
                num = int(slot.split("_")[1])
            except (IndexError, ValueError):
                raise ValueError(f"Cannot determine PropertyNumber for {name!r} ({slot})")
        e = {"PropertyNumber": num}
        if type_id == 1:
            e["StringValue"] = str(value)
        elif type_id == 2:
            e["IntegerValue"] = int(value)
        elif type_id == 3:
            e["DecimalValue"] = float(value)
        elif type_id == 4:
            e["BooleanValue"] = _parse_bool(value)
        elif type_id == 5:
            e["DateTimeValue"] = str(value)
        elif type_id == 6:
            e["IntegerValue"] = _resolve_option_id(meta, field, value)
        elif type_id == 7:
            vals = value if isinstance(value, (list, tuple)) else [value]
            e["IntegerListValue"] = [_resolve_option_id(meta, field, v) for v in vals]
        elif type_id in (8, 10):
            e["IntegerValue"] = int(value)
        else:
            raise ValueError(
                f"Unsupported custom property type "
                f"{field.get('CustomPropertyTypeName') or type_id} ({field.get('Name')!r})"
            )
        entries.append(e)
    return entries


def _merge_custom_properties(current, entries):
    """Replace/append CustomProperties entries (by PropertyNumber) on a fetched artifact."""
    existing = current.get("CustomProperties") or []
    by_num = {p.get("PropertyNumber"): p for p in existing if isinstance(p, dict)}
    for e in entries:
        target = by_num.get(e["PropertyNumber"])
        if target is not None:
            target.update({k: v for k, v in e.items() if k != "PropertyNumber"})
        else:
            existing.append(e)
    current["CustomProperties"] = existing


def _build_custom_prop_index(fields):
    """Index custom-property fields for O(1) lookup by slot, name, and option label/id."""
    by_slot = {}
    by_name = {}
    options = {}
    for f in fields:
        slot = f.get("CustomPropertyFieldName")
        name = f.get("Name")
        if slot:
            by_slot[slot] = f
        if name:
            by_name[name] = f
        custom_list = f.get("CustomList")
        if custom_list and slot:
            label_to_id = {}
            id_to_label = {}
            for v in custom_list.get("Values") or []:
                vid = v.get("CustomPropertyValueId")
                vname = v.get("Name")
                if vid is not None and vname is not None:
                    label_to_id[vname] = vid
                    id_to_label[vid] = vname
            if label_to_id:
                options[slot] = {"label_to_id": label_to_id, "id_to_label": id_to_label}
    return {"fields": fields, "by_slot": by_slot, "by_name": by_name, "options": options}


class SpiraApiError(Exception):
    """Raised when the Spira API returns an error response."""

    def __init__(self, status_code, message, url=""):
        self.status_code = status_code
        self.url = url
        super().__init__(f"Spira API {status_code} at {url}: {message}")


class SpiraClient:
    """HTTP client for Spira REST API v7.

    Handles authentication, pagination, retries, and the task-filtering workaround.
    """

    API_PATH = "/Services/v7_0/RestService.svc"
    MAX_RETRIES = 3
    RETRY_BACKOFF = 1  # seconds
    DEFAULT_PAGE_SIZE = 500

    def __init__(self, base_url, username, api_key):
        self.base_url = base_url.rstrip("/") + self.API_PATH
        self.session = requests.Session()
        self.session.headers.update({
            "username": username,
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    # ──────────────────────────────────────────────
    #  HTTP primitives with retry
    # ──────────────────────────────────────────────

    def _request(self, method, path, params=None, json_body=None):
        url = f"{self.base_url}/{path}"
        last_error = None
        last_status = None

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self.session.request(method, url, params=params, json=json_body, timeout=60)

                if resp.status_code == 429:
                    last_status, last_error = 429, resp.text[:200]
                    time.sleep(self._retry_after_seconds(resp, attempt))
                    continue

                if resp.status_code >= 500:
                    last_status, last_error = resp.status_code, resp.text[:200]
                    time.sleep(self.RETRY_BACKOFF * (attempt + 1))
                    continue

                if resp.status_code >= 400:
                    msg = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                    raise SpiraApiError(resp.status_code, msg, url)

                if not resp.content:
                    return None
                try:
                    return resp.json()
                except ValueError:
                    raise SpiraApiError(resp.status_code, f"Non-JSON response body: {resp.text[:200]}", url)

            except (requests.ConnectionError, requests.Timeout) as e:
                last_status, last_error = 0, e
                time.sleep(self.RETRY_BACKOFF * (attempt + 1))

        raise SpiraApiError(last_status or 0, f"Failed after {self.MAX_RETRIES} retries: {last_error}", url)

    def _retry_after_seconds(self, resp, attempt):
        """Parse a Retry-After header (seconds form); fall back to backoff on the
        HTTP-date form or a missing header."""
        try:
            return int(resp.headers.get("Retry-After"))
        except (TypeError, ValueError):
            return self.RETRY_BACKOFF * (attempt + 1)

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    def _post(self, path, body=None, params=None):
        return self._request("POST", path, params=params, json_body=body)

    def _put(self, path, body=None, params=None):
        return self._request("PUT", path, params=params, json_body=body)

    # ──────────────────────────────────────────────
    #  Pagination helpers
    # ──────────────────────────────────────────────

    def _paginate_get(self, path, params=None, start_key="starting_row", size_key="number_of_rows", max_rows=None):
        """Paginate a GET endpoint until fewer than page_size results are returned.

        max_rows: stop fetching once this many rows are collected (None = all).
        """
        params = dict(params or {})
        all_results = []
        start = 1

        while True:
            params[start_key] = start
            params[size_key] = self.DEFAULT_PAGE_SIZE
            batch = self._get(path, params)
            if not batch:
                break
            all_results.extend(batch)
            if max_rows is not None and len(all_results) >= max_rows:
                return all_results[:max_rows]
            if len(batch) < self.DEFAULT_PAGE_SIZE:
                break
            start += self.DEFAULT_PAGE_SIZE

        return all_results

    def _paginate_post(self, path, body=None, params=None, start_key="starting_row", size_key="number_of_rows", max_rows=None):
        """Paginate a POST /search endpoint. max_rows: stop early (None = all)."""
        params = dict(params or {})
        all_results = []
        start = 1

        while True:
            params[start_key] = start
            params[size_key] = self.DEFAULT_PAGE_SIZE
            batch = self._post(path, body=body, params=params)
            if not batch:
                break
            all_results.extend(batch)
            if max_rows is not None and len(all_results) >= max_rows:
                return all_results[:max_rows]
            if len(batch) < self.DEFAULT_PAGE_SIZE:
                break
            start += self.DEFAULT_PAGE_SIZE

        return all_results

    # ──────────────────────────────────────────────
    #  Filter builder
    # ──────────────────────────────────────────────

    @staticmethod
    def _build_filters(**kwargs):
        """Build a RemoteFilter[] array from keyword arguments.

        Supports: int values → IntValue, str values → StringValue,
        list values → MultiValue, dict with StartDate/EndDate → DateRangeValue.
        """
        filters = []
        for prop_name, value in kwargs.items():
            if value is None:
                continue
            f = {"PropertyName": prop_name}
            if isinstance(value, bool):
                # bool is an int subclass — check first so True doesn't serialize
                # as IntValue: true (fix.md F17)
                f["IntValue"] = int(value)
            elif isinstance(value, int):
                f["IntValue"] = value
            elif isinstance(value, str):
                f["StringValue"] = value
            elif isinstance(value, list):
                f["MultiValue"] = value
            elif isinstance(value, dict):
                f["DateRangeValue"] = value
            filters.append(f)
        return filters

    # ──────────────────────────────────────────────
    #  Products
    # ──────────────────────────────────────────────

    def get_products(self):
        return self._get("projects") or []

    def get_product(self, product_id):
        return self._get(f"projects/{product_id}")

    # ──────────────────────────────────────────────
    #  Programs
    # ──────────────────────────────────────────────

    def get_programs(self):
        return self._get("programs") or []

    def get_program_products(self, program_id):
        products = self._get("projects") or []
        return [p for p in products if p.get("ProjectGroupId") == program_id]

    def get_milestones(self, program_id):
        return self._get(f"programs/{program_id}/milestones") or []

    def get_capabilities(self, program_id):
        # The POST search variant takes starting_row/number_of_rows + a RemoteFilter[]
        # body; current_page/page_size belong to the GET variant (fix.md F5).
        return self._paginate_post(
            f"programs/{program_id}/capabilities/search",
            body=[],
        )

    # ──────────────────────────────────────────────
    #  Templates
    # ──────────────────────────────────────────────

    def get_product_templates(self):
        return self._get("project-templates") or []

    def get_product_template(self, template_id):
        return self._get(f"project-templates/{template_id}")

    def get_artifact_types(self, template_id):
        """Get artifact types AND statuses/priorities/importances/severities for a template.

        Returns {artifact: {category: [items]}}. Each category fetch is tolerant of
        404/401 so one missing endpoint doesn't break the whole discovery call.
        """
        categories = {
            "requirements": ["types", "statuses", "importances"],
            "test-cases": ["types", "statuses", "priorities"],
            "tasks": ["types", "statuses", "priorities"],
            "risks": ["types", "statuses", "probabilities", "impacts"],
            "incidents": ["types", "statuses", "priorities", "severities"],
        }
        result = {}
        for artifact, cats in categories.items():
            for cat in cats:
                try:
                    items = self._get(f"project-templates/{template_id}/{artifact}/{cat}")
                except SpiraApiError:
                    continue
                if items:
                    result.setdefault(artifact, {})[cat] = items
        return result

    def get_template_id_for_product(self, product_id):
        """Resolve a product's template_id, with per-process caching."""
        if product_id in _PRODUCT_TEMPLATE_CACHE:
            return _PRODUCT_TEMPLATE_CACHE[product_id]
        product = self.get_product(product_id)
        if not product:
            raise SpiraApiError(404, f"Product {product_id} not found", "")
        template_id = product.get("ProjectTemplateId")
        if template_id is None:
            raise SpiraApiError(0, f"Product {product_id} has no ProjectTemplateId", "")
        _PRODUCT_TEMPLATE_CACHE[product_id] = template_id
        return template_id

    def get_custom_properties_for_artifact_type(self, template_id, artifact_type_name):
        """Fetch custom-property metadata for one artifact type, with indexed cache.

        Returns a dict with keys: 'fields' (raw list), 'by_slot' (Custom_XX -> field),
        'by_name' (display name -> field), 'options' ({slot: {label_to_id, id_to_label}}).
        """
        cache_key = (template_id, artifact_type_name)
        if cache_key in _CUSTOM_PROPS_CACHE:
            return _CUSTOM_PROPS_CACHE[cache_key]
        if artifact_type_name not in SUPPORTED_ARTIFACT_TYPES:
            raise ValueError(
                f"Unknown artifact_type_name '{artifact_type_name}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_ARTIFACT_TYPES))}"
            )
        fields = self._get(f"project-templates/{template_id}/custom-properties/{artifact_type_name}") or []
        indexed = _build_custom_prop_index(fields)
        _CUSTOM_PROPS_CACHE[cache_key] = indexed
        return indexed

    def resolve_custom_filters_for(self, template_id, artifact_type_name, name_to_value):
        """Resolve {name: value} custom filters against template metadata (fix.md F20)."""
        meta = self.get_custom_properties_for_artifact_type(template_id, artifact_type_name)
        return resolve_custom_filters(meta, name_to_value)

    def resolve_custom_values_for(self, template_id, artifact_type_name, name_to_value):
        """Resolve {name: value} custom writes against template metadata (fix.md F20)."""
        meta = self.get_custom_properties_for_artifact_type(template_id, artifact_type_name)
        return resolve_custom_values(meta, name_to_value)

    # ──────────────────────────────────────────────
    #  Users & Components
    # ──────────────────────────────────────────────

    def get_project_users(self, product_id):
        """Active users that are members of the project, with their roles."""
        return self._get(f"projects/{product_id}/users") or []

    def get_components(self, product_id, active_only=True):
        return self._get(
            f"projects/{product_id}/components",
            params={"active_only": str(active_only).lower(), "include_deleted": "false"},
        ) or []

    # ──────────────────────────────────────────────
    #  Comments
    # ──────────────────────────────────────────────

    _COMMENT_PATHS = {"incident": "incidents", "task": "tasks", "requirement": "requirements"}

    def get_comments(self, product_id, artifact_type, artifact_id):
        seg = self._COMMENT_PATHS.get(artifact_type)
        if not seg:
            raise ValueError(
                f"Comments are supported for: {', '.join(sorted(self._COMMENT_PATHS))}")
        return self._get(f"projects/{product_id}/{seg}/{artifact_id}/comments") or []

    def add_comment(self, product_id, artifact_type, artifact_id, text):
        seg = self._COMMENT_PATHS.get(artifact_type)
        if not seg:
            raise ValueError(
                f"Comments are supported for: {', '.join(sorted(self._COMMENT_PATHS))}")
        body = {"ArtifactId": artifact_id, "Text": text}
        if artifact_type == "incident":
            # Incident comments POST takes an ARRAY of RemoteComment; requirement
            # and task take a single object (per the instance's own contract pages).
            return self._post(f"projects/{product_id}/{seg}/{artifact_id}/comments", body=[body])
        return self._post(f"projects/{product_id}/{seg}/{artifact_id}/comments", body=body)

    # ──────────────────────────────────────────────
    #  My Work
    # ──────────────────────────────────────────────

    def get_my_tasks(self):
        return self._get("tasks") or []

    def get_my_incidents(self):
        return self._get("incidents") or []

    def get_my_requirements(self):
        return self._get("requirements") or []

    def get_my_test_cases(self):
        return self._get("test-cases") or []

    def get_my_test_sets(self):
        return self._get("test-sets") or []

    # ──────────────────────────────────────────────
    #  Releases
    # ──────────────────────────────────────────────

    def get_releases(self, product_id, active_only=True, release_type_id=None):
        releases = self._get(f"projects/{product_id}/releases", {"active_only": str(active_only).lower()}) or []
        if release_type_id is not None:
            releases = [r for r in releases if r.get("ReleaseTypeId") == release_type_id]
        # Sort by StartDate descending (most recent first)
        releases.sort(key=lambda r: r.get("StartDate") or "", reverse=True)
        return releases

    def get_release(self, product_id, release_id):
        return self._get(f"projects/{product_id}/releases/{release_id}")

    # ──────────────────────────────────────────────
    #  Requirements
    # ──────────────────────────────────────────────

    def get_requirements(self, product_id, release_id=None, status_id=None,
                         importance_id=None, owner_id=None, limit=None, extra_filters=None):
        # NOTE: the FILTER property for status really is RequirementStatusId (entity
        # name); the PUT-body field is StatusId. Verified live — see fix.md F2.
        filters = self._build_filters(
            ReleaseId=release_id,
            RequirementStatusId=status_id,
            ImportanceId=importance_id,
            OwnerId=owner_id,
        )
        if extra_filters:
            filters.extend(extra_filters)
        if filters:
            return self._paginate_post(f"projects/{product_id}/requirements/search",
                                       body=filters, max_rows=limit)
        return self._paginate_get(f"projects/{product_id}/requirements", max_rows=limit)

    def get_requirement(self, product_id, requirement_id):
        return self._get(f"projects/{product_id}/requirements/{requirement_id}")

    def get_requirement_children(self, product_id, requirement_id):
        return self._get(f"projects/{product_id}/requirements/{requirement_id}/children") or []

    def get_requirement_steps(self, product_id, requirement_id):
        return self._get(f"projects/{product_id}/requirements/{requirement_id}/steps") or []

    def create_requirement(self, product_id, name, description="", requirement_type_id=None,
                           importance_id=None, owner_id=None, release_id=None,
                           parent_requirement_id=None, custom_properties=None):
        body = {"Name": name, "Description": description}
        if requirement_type_id is not None:
            body["RequirementTypeId"] = requirement_type_id
        if importance_id is not None:
            body["ImportanceId"] = importance_id
        if owner_id is not None:
            body["OwnerId"] = owner_id
        if release_id is not None:
            body["ReleaseId"] = release_id
        if custom_properties:
            body["CustomProperties"] = custom_properties
        if parent_requirement_id is not None:
            # Child-create route is /requirements/parent/{id} — POST to
            # /requirements/{id} is 405 (verified live, fix.md F4).
            return self._post(
                f"projects/{product_id}/requirements/parent/{parent_requirement_id}", body=body)
        return self._post(f"projects/{product_id}/requirements", body=body)

    def update_requirement(self, product_id, requirement_id, custom_properties=None, **updates):
        """Update a requirement. GETs current state first for concurrency, merges updates, PUTs back.

        Spira's PUT returns 200 with no body, so we re-fetch the requirement to return
        the canonical updated object for downstream formatting.
        """
        current = self.get_requirement(product_id, requirement_id)
        if not current:
            raise SpiraApiError(404, f"Requirement {requirement_id} not found", "")
        for key, value in updates.items():
            if value is not None:
                current[key] = value
        if custom_properties:
            _merge_custom_properties(current, custom_properties)
        self._put(f"projects/{product_id}/requirements", body=current)
        return self.get_requirement(product_id, requirement_id)

    # ──────────────────────────────────────────────
    #  Tasks — THE KEY FIX
    # ──────────────────────────────────────────────

    def get_tasks(self, product_id, release_id=None, status_id=None, owner_id=None, limit=None):
        """Get tasks filtered by their OWN release, not their parent requirement's release.

        Strategy:
        1. Try undocumented POST /tasks/search with RemoteFilter[] (existed in v5, may work on v7)
        2. Fallback: fetch all tasks via GET /tasks/new with pagination, filter client-side

        limit: return at most N tasks (None = all).
        """
        filters = self._build_filters(
            ReleaseId=release_id,
            TaskStatusId=status_id,
            OwnerId=owner_id,
        )

        def _apply(tasks):
            if release_id is not None:
                tasks = [t for t in tasks if t.get("ReleaseId") == release_id]
            if status_id is not None:
                tasks = [t for t in tasks if t.get("TaskStatusId") == status_id]
            if owner_id is not None:
                tasks = [t for t in tasks if t.get("OwnerId") == owner_id]
            return tasks if limit is None else tasks[:limit]

        # Strategy 1: Try server-side search (undocumented but may work)
        if filters:
            try:
                results = self._paginate_post(
                    f"projects/{product_id}/tasks/search",
                    body=filters,
                    max_rows=limit,
                )
                # Re-apply the filters client-side: if the undocumented endpoint
                # ignores unknown filter properties it returns everything, and
                # Spira gives no error for that (fix.md F13).
                return _apply(results)
            except SpiraApiError as e:
                if e.status_code in (404, 405, 400):
                    pass  # Endpoint doesn't exist on this Spira version, fall back
                else:
                    raise

        # Strategy 2: Fetch all tasks, filter client-side. With filters present we
        # must fetch everything before filtering; only an unfiltered call can stop early.
        all_tasks = self._fetch_all_tasks(product_id, max_rows=limit if not filters else None)
        return _apply(all_tasks)

    def _fetch_all_tasks(self, product_id, max_rows=None):
        """Fetch all tasks using GET /tasks/new with proper pagination."""
        all_tasks = []
        start_row = 1

        while True:
            batch = self._get(
                f"projects/{product_id}/tasks/new",
                params={
                    "creation_date": "2000-01-01T00:00:00.000",
                    "start_row": start_row,
                    "number_of_rows": self.DEFAULT_PAGE_SIZE,
                },
            )
            if not batch:
                break
            all_tasks.extend(batch)
            if max_rows is not None and len(all_tasks) >= max_rows:
                return all_tasks[:max_rows]
            if len(batch) < self.DEFAULT_PAGE_SIZE:
                break
            start_row += self.DEFAULT_PAGE_SIZE

        return all_tasks

    def get_task(self, product_id, task_id):
        return self._get(f"projects/{product_id}/tasks/{task_id}")

    def count_tasks(self, product_id, release_id=None, status_id=None):
        filters = self._build_filters(ReleaseId=release_id, TaskStatusId=status_id)
        return self._post(f"projects/{product_id}/tasks/count", body=filters or [])

    def create_task(self, product_id, name, description="", task_status_id=1,
                    task_priority_id=None, owner_id=None, release_id=None,
                    requirement_id=None, estimated_effort=None, custom_properties=None):
        body = {"Name": name, "Description": description, "TaskStatusId": task_status_id}
        if task_priority_id is not None:
            body["TaskPriorityId"] = task_priority_id
        if owner_id is not None:
            body["OwnerId"] = owner_id
        if release_id is not None:
            body["ReleaseId"] = release_id
        if requirement_id is not None:
            body["RequirementId"] = requirement_id
        if estimated_effort is not None:
            body["EstimatedEffort"] = estimated_effort
        if custom_properties:
            body["CustomProperties"] = custom_properties
        return self._post(f"projects/{product_id}/tasks", body=body)

    def update_task(self, product_id, task_id, custom_properties=None, **updates):
        """Update a task. GETs current state first for concurrency, merges updates, PUTs back.

        Spira's PUT returns 200 with no body, so we re-fetch the task to return
        the canonical updated object for downstream formatting.
        """
        current = self.get_task(product_id, task_id)
        if not current:
            raise SpiraApiError(404, f"Task {task_id} not found", "")
        for key, value in updates.items():
            if value is not None:
                current[key] = value
        if custom_properties:
            _merge_custom_properties(current, custom_properties)
        self._put(f"projects/{product_id}/tasks", body=current)
        return self.get_task(product_id, task_id)

    # ──────────────────────────────────────────────
    #  Incidents
    # ──────────────────────────────────────────────

    def get_incidents(self, product_id, release_id=None, status_id=None,
                      priority_id=None, severity_id=None, owner_id=None, limit=None,
                      extra_filters=None):
        # _build_filters returns [] when every filter is None — one call covers both cases
        filters = self._build_filters(
            DetectedReleaseId=release_id,
            IncidentStatusId=status_id,
            PriorityId=priority_id,
            SeverityId=severity_id,
            OwnerId=owner_id,
        )
        if extra_filters:
            filters.extend(extra_filters)
        return self._paginate_post(
            f"projects/{product_id}/incidents/search",
            body=filters,
            start_key="start_row", size_key="number_rows",
            max_rows=limit,
        )

    def get_incident(self, product_id, incident_id):
        return self._get(f"projects/{product_id}/incidents/{incident_id}")

    def create_incident(self, product_id, name, description="", incident_type_id=None,
                        priority_id=None, severity_id=None, owner_id=None,
                        detected_release_id=None, custom_properties=None):
        body = {"Name": name, "Description": description}
        if incident_type_id is not None:
            body["IncidentTypeId"] = incident_type_id
        if priority_id is not None:
            body["PriorityId"] = priority_id
        if severity_id is not None:
            body["SeverityId"] = severity_id
        if owner_id is not None:
            body["OwnerId"] = owner_id
        if detected_release_id is not None:
            body["DetectedReleaseId"] = detected_release_id
        if custom_properties:
            body["CustomProperties"] = custom_properties
        return self._post(f"projects/{product_id}/incidents", body=body)

    def update_incident(self, product_id, incident_id, custom_properties=None, **updates):
        """Update an incident. GETs current state first for concurrency, merges updates, PUTs back.

        Note: unlike requirements/tasks/test-cases, Spira's incident update uses the
        individual-resource URL (.../incidents/{id}), not the collection URL.
        """
        current = self.get_incident(product_id, incident_id)
        if not current:
            raise SpiraApiError(404, f"Incident {incident_id} not found", "")
        for key, value in updates.items():
            if value is not None:
                current[key] = value
        if custom_properties:
            _merge_custom_properties(current, custom_properties)
        self._put(f"projects/{product_id}/incidents/{incident_id}", body=current)
        return self.get_incident(product_id, incident_id)

    # ──────────────────────────────────────────────
    #  Test Cases
    # ──────────────────────────────────────────────

    def get_test_cases(self, product_id, release_id=None, limit=None):
        params = {}
        if release_id is not None:
            params["release_id"] = release_id
        return self._paginate_get(f"projects/{product_id}/test-cases", params, max_rows=limit)

    def search_test_cases(self, product_id, filters, release_id=None, limit=None):
        """POST /test-cases/search with RemoteFilter[] (incl. Custom_XX filters)."""
        params = {}
        if release_id is not None:
            params["release_id"] = release_id
        return self._paginate_post(
            f"projects/{product_id}/test-cases/search",
            body=filters, params=params, max_rows=limit,
        )

    def get_test_case(self, product_id, test_case_id):
        return self._get(f"projects/{product_id}/test-cases/{test_case_id}")

    def get_test_steps(self, product_id, test_case_id):
        return self._get(f"projects/{product_id}/test-cases/{test_case_id}/test-steps") or []

    def get_test_cases_by_release(self, product_id, release_id):
        """Raw release->test-case mapping pairs: [{ReleaseId, TestCaseId}] — IDs only.

        Not suitable for display (no names/statuses — fix.md F3). For a
        release-filtered test-case list use get_test_cases(product_id, release_id):
        the root endpoint accepts release_id and returns full objects.
        """
        return self._get(f"projects/{product_id}/releases/{release_id}/test-cases") or []

    def add_test_cases_to_release(self, product_id, release_id, test_case_ids):
        """Map test cases to a release. The POST body is a bare array of test case
        IDs — a {ReleaseId, TestCaseId} object body gets a 400 (verified live)."""
        return self._post(
            f"projects/{product_id}/releases/{release_id}/test-cases",
            body=list(test_case_ids),
        )

    def remove_test_case_from_release(self, product_id, release_id, test_case_id):
        return self._request(
            "DELETE",
            f"projects/{product_id}/releases/{release_id}/test-cases/{test_case_id}",
        )

    # ──────────────────────────────────────────────
    #  Test Coverage (Requirement <-> Test Case)
    # ──────────────────────────────────────────────
    #
    # Coverage is Spira's first-class relationship between Requirements and Test Cases.
    # It drives the requirement's CoverageCount* metrics and the "Test Coverage" UI tab.
    # NOT the same as Associations — associations are generic free-form links and don't
    # affect coverage metrics.
    #
    # Reads use the per-artifact sub-resources below. Writes go to the project-level
    # /requirements/test-cases endpoint with a {RequirementId, TestCaseId} body.
    # POSTing to the per-requirement URL (.../requirements/{id}/test-cases) returns
    # 405 — that wrong URL is how coverage was long believed to be read-only
    # (verified writable live 2026-06-11, fix.md F6).

    def get_test_coverage_for_requirement(self, product_id, requirement_id):
        """List the test cases covering a requirement."""
        return self._get(f"projects/{product_id}/requirements/{requirement_id}/test-cases") or []

    def get_requirements_covered_by_test_case(self, product_id, test_case_id):
        """List the requirements a test case covers."""
        return self._get(f"projects/{product_id}/test-cases/{test_case_id}/requirements") or []

    def add_test_coverage(self, product_id, requirement_id, test_case_id):
        """Add a coverage link so the test case covers the requirement."""
        return self._post(
            f"projects/{product_id}/requirements/test-cases",
            body={"RequirementId": requirement_id, "TestCaseId": test_case_id},
        )

    def remove_test_coverage(self, product_id, requirement_id, test_case_id):
        """Remove a coverage link between a requirement and a test case."""
        return self._request(
            "DELETE",
            f"projects/{product_id}/requirements/test-cases",
            json_body={"RequirementId": requirement_id, "TestCaseId": test_case_id},
        )

    def create_test_case(self, product_id, name, description="", test_case_type_id=None,
                         test_case_priority_id=None, owner_id=None, test_case_folder_id=None,
                         estimated_duration=None, tags="", custom_properties=None):
        body = {"Name": name, "Description": description, "TestCaseStatusId": 0}
        if test_case_type_id is not None:
            body["TestCaseTypeId"] = test_case_type_id
        if test_case_priority_id is not None:
            body["TestCasePriorityId"] = test_case_priority_id
        if owner_id is not None:
            body["OwnerId"] = owner_id
        if test_case_folder_id is not None:
            body["TestCaseFolderId"] = test_case_folder_id
        if estimated_duration is not None:
            body["EstimatedDuration"] = estimated_duration
        if tags:
            body["Tags"] = tags
        if custom_properties:
            body["CustomProperties"] = custom_properties
        return self._post(f"projects/{product_id}/test-cases", body=body)

    def update_test_case(self, product_id, test_case_id, custom_properties=None, **updates):
        """Update a test case. GETs current state first for ConcurrencyDate.

        Merges `updates` into the existing object and PUTs the result.
        Spira's PUT returns 200 with no body, so we re-fetch the test case to return
        the canonical updated object for downstream formatting.
        """
        current = self.get_test_case(product_id, test_case_id)
        if not current:
            raise SpiraApiError(404, f"Test case {test_case_id} not found", "")

        for key, value in updates.items():
            if value is not None:
                current[key] = value

        if custom_properties:
            _merge_custom_properties(current, custom_properties)
        self._put(f"projects/{product_id}/test-cases", body=current)
        return self.get_test_case(product_id, test_case_id)

    def update_test_step(self, product_id, test_case_id, test_step_id, **updates):
        """Update a single test step. GETs current state first for ConcurrencyDate.

        Merges `updates` into the existing step and PUTs the result. Spira's PUT
        returns 200 with no body, so we re-fetch and return the canonical step.
        """
        steps = self.get_test_steps(product_id, test_case_id)
        current = next((s for s in steps if s.get("TestStepId") == test_step_id), None)
        if not current:
            raise SpiraApiError(404, f"Test step {test_step_id} not found in TC:{test_case_id}", "")

        for key, value in updates.items():
            if value is not None:
                current[key] = value

        self._put(f"projects/{product_id}/test-cases/{test_case_id}/test-steps", body=current)
        steps_after = self.get_test_steps(product_id, test_case_id)
        return next((s for s in steps_after if s.get("TestStepId") == test_step_id), None)

    def create_test_step(self, product_id, test_case_id, description,
                         expected_result="", sample_data=""):
        body = {
            "Description": description,
            "ExpectedResult": expected_result,
            "SampleData": sample_data,
        }
        return self._post(f"projects/{product_id}/test-cases/{test_case_id}/test-steps", body=body)

    def delete_test_step(self, product_id, test_case_id, test_step_id):
        return self._request("DELETE", f"projects/{product_id}/test-cases/{test_case_id}/test-steps/{test_step_id}")

    # ──────────────────────────────────────────────
    #  Test Runs
    # ──────────────────────────────────────────────

    def get_test_runs(self, product_id, limit=None):
        return self._paginate_get(
            f"projects/{product_id}/test-runs",
            params={"sort_field": "EndDate", "sort_direction": "DESC"},
            max_rows=limit,
        )

    def get_test_run(self, product_id, test_run_id):
        """Get a manual test run with its steps included."""
        return self._get(f"projects/{product_id}/test-runs/{test_run_id}/manual")

    def create_test_runs(self, product_id, test_case_ids, release_id=None):
        """Create test run shells from test case IDs. Returns runs with steps pre-populated."""
        params = {}
        if release_id is not None:
            params["release_id"] = release_id
        return self._post(f"projects/{product_id}/test-runs/create", body=test_case_ids, params=params)

    def save_test_runs(self, product_id, test_runs, end_date=None):
        """Save test runs with step-level results.

        test_runs: array of RemoteManualTestRun objects with TestRunSteps populated.
        end_date: ISO datetime string — sent as the end_date QUERY param per KB684
        (it was previously accepted but never sent — fix.md F8).
        """
        params = {"end_date": end_date} if end_date else None
        return self._put(
            f"projects/{product_id}/test-runs",
            body=test_runs,
            params=params,
        )

    def record_test_run(self, product_id, test_case_id, execution_status_id,
                        test_name, short_message="", long_message="", error_count=0,
                        release_id=None, test_set_id=None, build_id=None):
        # Spira's /test-runs/record endpoint takes a single object, not an array.
        # Sending an array fails with "Cannot deserialize the current JSON array... into type".
        body = {
            "TestCaseId": test_case_id,
            "ExecutionStatusId": execution_status_id,
            "RunnerName": test_name,
            "RunnerMessage": short_message,
            "RunnerStackTrace": long_message,
            "CountFailures": error_count,
            "RunnerTestName": test_name,
        }
        if release_id is not None:
            body["ReleaseId"] = release_id
        if test_set_id is not None:
            body["TestSetId"] = test_set_id
        if build_id is not None:
            body["BuildId"] = build_id
        return self._post(f"projects/{product_id}/test-runs/record", body=body)

    # ──────────────────────────────────────────────
    #  Documents & Attachments
    # ──────────────────────────────────────────────

    def upload_document(self, product_id, filename, binary_data_base64, description="",
                        folder_id=None):
        """Upload a file to Spira. binary_data_base64 is the file content as base64 string."""
        # The API expects an array of byte values, but accepts base64 in the JSON
        body = {
            "BinaryData": binary_data_base64,
            "FilenameOrUrl": filename,
            "Description": description,
            "AttachmentTypeId": 1,  # File
        }
        if folder_id is not None:
            body["ProjectAttachmentFolderId"] = folder_id
        return self._post(f"projects/{product_id}/documents/file", body=body)

    def attach_document_to_artifact(self, product_id, artifact_type_id, artifact_id, document_id):
        """Attach an existing document to an artifact."""
        return self._post(
            f"projects/{product_id}/artifact-types/{artifact_type_id}/artifacts/{artifact_id}/documents/{document_id}")

    def get_artifact_documents(self, product_id, artifact_type_id, artifact_id):
        """List documents attached to an artifact."""
        return self._get(
            f"projects/{product_id}/artifact-types/{artifact_type_id}/artifacts/{artifact_id}/documents") or []

    # ──────────────────────────────────────────────
    #  Test Case Folders
    # ──────────────────────────────────────────────

    def get_test_case_folders(self, product_id):
        # Spira's endpoint is `test-folders`, not `test-case-folders` (which 404s).
        return self._get(f"projects/{product_id}/test-folders") or []

    # ──────────────────────────────────────────────
    #  Associations
    # ──────────────────────────────────────────────

    def create_association(self, product_id, source_artifact_type_id, source_artifact_id,
                           dest_artifact_type_id, dest_artifact_id, artifact_link_type_id=1,
                           comment=""):
        body = {
            "SourceArtifactId": source_artifact_id,
            "SourceArtifactTypeId": source_artifact_type_id,
            "DestArtifactId": dest_artifact_id,
            "DestArtifactTypeId": dest_artifact_type_id,
            "ArtifactLinkTypeId": artifact_link_type_id,
            "Comment": comment,
        }
        return self._post(f"projects/{product_id}/associations", body=body)

    def get_associations(self, product_id, artifact_type_id, artifact_id):
        return self._get(f"projects/{product_id}/associations/{artifact_type_id}/{artifact_id}") or []

    def delete_association(self, product_id, artifact_link_id):
        return self._request("DELETE", f"projects/{product_id}/associations/{artifact_link_id}")

    # ──────────────────────────────────────────────
    #  Builds
    # ──────────────────────────────────────────────

    # ──────────────────────────────────────────────
    #  Risks
    # ──────────────────────────────────────────────

    def get_risks(self, product_id, release_id=None):
        filters = self._build_filters(ReleaseId=release_id) if release_id else []
        return self._paginate_post(
            f"projects/{product_id}/risks",
            body=filters,
            params={"sort_field": "CreationDate", "sort_direction": "DESC"},
        )

    # ──────────────────────────────────────────────
    #  Test Sets
    # ──────────────────────────────────────────────

    def get_test_sets(self, product_id):
        """Get all test sets in a product — root-level plus those inside folders.

        Spira's `/test-sets` endpoint returns root-level test sets but requires
        starting_row/number_of_rows params (it 406s without them). Sets inside
        folders are fetched via the per-folder sub-resource.
        """
        all_sets = list(self._paginate_get(f"projects/{product_id}/test-sets") or [])
        seen = {s.get("TestSetId") for s in all_sets if s.get("TestSetId") is not None}

        folders = self._get(f"projects/{product_id}/test-set-folders") or []
        for folder in folders:
            folder_id = folder.get("TestSetFolderId")
            if folder_id is None:
                continue
            # Paginate — a fixed 500-row fetch silently truncated big folders (fix.md F15)
            sets = self._paginate_get(
                f"projects/{product_id}/test-set-folders/{folder_id}/test-sets",
            )
            for s in sets:
                sid = s.get("TestSetId")
                if sid is not None and sid not in seen:
                    all_sets.append(s)
                    seen.add(sid)
        return all_sets

    def get_test_set(self, product_id, test_set_id):
        return self._get(f"projects/{product_id}/test-sets/{test_set_id}")

    def get_test_set_test_cases(self, product_id, test_set_id):
        """Test cases in a test set — returns full RemoteTestCase objects."""
        return self._get(f"projects/{product_id}/test-sets/{test_set_id}/test-cases") or []

    # ──────────────────────────────────────────────
    #  Automation Hosts
    # ──────────────────────────────────────────────

    def get_automation_hosts(self, product_id):
        return self._get(f"projects/{product_id}/automation-hosts") or []

    # ──────────────────────────────────────────────
    #  Builds
    # ──────────────────────────────────────────────

    def create_build(self, product_id, release_id, name, description="",
                     build_status_id=1, commits=None):
        # ReleaseId must also appear in the body — Spira deserializes it from the body,
        # not the URL, and missing it surfaces as "associated release/sprint RL0 does not exist".
        body = {
            "Name": name,
            "Description": description,
            "ReleaseId": release_id,
            "BuildStatusId": build_status_id,
            "Revisions": [{"RevisionKey": c} for c in (commits or [])],
        }
        return self._post(f"projects/{product_id}/releases/{release_id}/builds", body=body)
