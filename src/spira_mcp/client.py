"""Spira REST API v7 client with proper pagination and filtering."""

import time
import requests


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

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self.session.request(method, url, params=params, json=json_body, timeout=60)

                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", self.RETRY_BACKOFF * (attempt + 1)))
                    time.sleep(wait)
                    continue

                if resp.status_code >= 500:
                    time.sleep(self.RETRY_BACKOFF * (attempt + 1))
                    continue

                if resp.status_code >= 400:
                    msg = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                    raise SpiraApiError(resp.status_code, msg, url)

                if not resp.content:
                    return None
                return resp.json()

            except requests.ConnectionError as e:
                last_error = e
                time.sleep(self.RETRY_BACKOFF * (attempt + 1))

        raise SpiraApiError(0, f"Failed after {self.MAX_RETRIES} retries: {last_error}", path)

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    def _post(self, path, body=None, params=None):
        return self._request("POST", path, params=params, json_body=body)

    def _put(self, path, body=None):
        return self._request("PUT", path, json_body=body)

    # ──────────────────────────────────────────────
    #  Pagination helpers
    # ──────────────────────────────────────────────

    def _paginate_get(self, path, params=None, start_key="starting_row", size_key="number_of_rows"):
        """Paginate a GET endpoint until fewer than page_size results are returned."""
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
            if len(batch) < self.DEFAULT_PAGE_SIZE:
                break
            start += self.DEFAULT_PAGE_SIZE

        return all_results

    def _paginate_post(self, path, body=None, params=None, start_key="starting_row", size_key="number_of_rows"):
        """Paginate a POST /search endpoint."""
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
            if isinstance(value, int):
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
    #  Releases
    # ──────────────────────────────────────────────

    def get_releases(self, product_id, active_only=True):
        return self._get(f"projects/{product_id}/releases", {"active_only": str(active_only).lower()}) or []

    def get_release(self, product_id, release_id):
        return self._get(f"projects/{product_id}/releases/{release_id}")

    def search_releases(self, product_id, **filter_kwargs):
        filters = self._build_filters(**filter_kwargs)
        return self._paginate_post(
            f"projects/{product_id}/releases/search",
            body=filters,
            start_key="start_row", size_key="number_rows",
        )

    # ──────────────────────────────────────────────
    #  Requirements
    # ──────────────────────────────────────────────

    def get_requirements(self, product_id, release_id=None, status_id=None,
                         importance_id=None, owner_id=None):
        filters = self._build_filters(
            ReleaseId=release_id,
            RequirementStatusId=status_id,
            ImportanceId=importance_id,
            OwnerId=owner_id,
        )
        if filters:
            return self._paginate_post(f"projects/{product_id}/requirements/search", body=filters)
        return self._paginate_get(f"projects/{product_id}/requirements")

    def get_requirement(self, product_id, requirement_id):
        return self._get(f"projects/{product_id}/requirements/{requirement_id}")

    def get_requirement_children(self, product_id, requirement_id):
        return self._get(f"projects/{product_id}/requirements/{requirement_id}/children") or []

    def get_requirement_steps(self, product_id, requirement_id):
        return self._get(f"projects/{product_id}/requirements/{requirement_id}/steps") or []

    # ──────────────────────────────────────────────
    #  Tasks — THE KEY FIX
    # ──────────────────────────────────────────────

    def get_tasks(self, product_id, release_id=None, status_id=None, owner_id=None):
        """Get tasks filtered by their OWN release, not their parent requirement's release.

        Strategy:
        1. Try undocumented POST /tasks/search with RemoteFilter[] (existed in v5, may work on v7)
        2. Fallback: fetch all tasks via GET /tasks/new with pagination, filter client-side
        """
        filters = self._build_filters(
            ReleaseId=release_id,
            TaskStatusId=status_id,
            OwnerId=owner_id,
        )

        # Strategy 1: Try server-side search (undocumented but may work)
        if filters:
            try:
                results = self._paginate_post(
                    f"projects/{product_id}/tasks/search",
                    body=filters,
                )
                return results
            except SpiraApiError as e:
                if e.status_code in (404, 405, 400):
                    pass  # Endpoint doesn't exist on this Spira version, fall back
                else:
                    raise

        # Strategy 2: Fetch all tasks, filter client-side
        all_tasks = self._fetch_all_tasks(product_id)

        if release_id is not None:
            all_tasks = [t for t in all_tasks if t.get("ReleaseId") == release_id]
        if status_id is not None:
            all_tasks = [t for t in all_tasks if t.get("TaskStatusId") == status_id]
        if owner_id is not None:
            all_tasks = [t for t in all_tasks if t.get("OwnerId") == owner_id]

        return all_tasks

    def _fetch_all_tasks(self, product_id):
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
            if len(batch) < self.DEFAULT_PAGE_SIZE:
                break
            start_row += self.DEFAULT_PAGE_SIZE

        return all_tasks

    def get_task(self, product_id, task_id):
        return self._get(f"projects/{product_id}/tasks/{task_id}")

    def count_tasks(self, product_id, release_id=None, status_id=None):
        filters = self._build_filters(ReleaseId=release_id, TaskStatusId=status_id)
        return self._post(f"projects/{product_id}/tasks/count", body=filters or [])

    # ──────────────────────────────────────────────
    #  Incidents
    # ──────────────────────────────────────────────

    def get_incidents(self, product_id, release_id=None, status_id=None,
                      priority_id=None, severity_id=None, owner_id=None):
        filters = self._build_filters(
            DetectedReleaseId=release_id,
            IncidentStatusId=status_id,
            PriorityId=priority_id,
            SeverityId=severity_id,
            OwnerId=owner_id,
        )
        if filters:
            return self._paginate_post(
                f"projects/{product_id}/incidents/search",
                body=filters,
                start_key="start_row", size_key="number_rows",
            )
        return self._paginate_post(
            f"projects/{product_id}/incidents/search",
            body=[],
            start_key="start_row", size_key="number_rows",
        )

    def get_incident(self, product_id, incident_id):
        return self._get(f"projects/{product_id}/incidents/{incident_id}")

    # ──────────────────────────────────────────────
    #  Test Cases
    # ──────────────────────────────────────────────

    def get_test_cases(self, product_id, release_id=None):
        params = {}
        if release_id is not None:
            params["release_id"] = release_id
        return self._paginate_get(f"projects/{product_id}/test-cases", params)

    def get_test_case(self, product_id, test_case_id):
        return self._get(f"projects/{product_id}/test-cases/{test_case_id}")

    def get_test_steps(self, product_id, test_case_id):
        return self._get(f"projects/{product_id}/test-cases/{test_case_id}/test-steps") or []

    def get_test_cases_by_release(self, product_id, release_id):
        """Uses the dedicated /releases/{id}/test-cases sub-resource endpoint."""
        return self._get(f"projects/{product_id}/releases/{release_id}/test-cases") or []

    # ──────────────────────────────────────────────
    #  Test Runs
    # ──────────────────────────────────────────────

    def get_test_runs(self, product_id):
        return self._paginate_get(
            f"projects/{product_id}/test-runs",
            params={"sort_field": "EndDate", "sort_direction": "DESC"},
        )

    def record_test_run(self, product_id, test_case_id, execution_status_id,
                        test_name, short_message="", long_message="", error_count=0):
        body = [{
            "TestCaseId": test_case_id,
            "ExecutionStatusId": execution_status_id,
            "RunnerName": test_name,
            "RunnerMessage": short_message,
            "RunnerStackTrace": long_message,
            "CountFailures": error_count,
            "RunnerTestName": test_name,
        }]
        return self._post(f"projects/{product_id}/test-runs/record", body=body)

    # ──────────────────────────────────────────────
    #  Builds
    # ──────────────────────────────────────────────

    def create_build(self, product_id, release_id, name, description="",
                     build_status_id=1, commits=None):
        body = {
            "Name": name,
            "Description": description,
            "BuildStatusId": build_status_id,
            "Revisions": [{"RevisionKey": c} for c in (commits or [])],
        }
        return self._post(f"projects/{product_id}/releases/{release_id}/builds", body=body)
