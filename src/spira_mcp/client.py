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
        return self._paginate_post(
            f"programs/{program_id}/capabilities/search",
            body=None,
            start_key="current_page", size_key="page_size",
        )

    # ──────────────────────────────────────────────
    #  Templates
    # ──────────────────────────────────────────────

    def get_product_templates(self):
        return self._get("project-templates") or []

    def get_product_template(self, template_id):
        return self._get(f"project-templates/{template_id}")

    def get_artifact_types(self, template_id):
        """Get all artifact types and their statuses/priorities/types for a template."""
        result = {}
        for artifact in ["requirements", "test-cases", "tasks", "risks", "incidents"]:
            types = self._get(f"project-templates/{template_id}/{artifact}/types")
            if types:
                result[artifact] = types
        return result

    def get_custom_properties(self, template_id):
        """Get custom properties for all artifact types in a template."""
        result = {}
        artifact_names = [
            "Requirements", "TestCases", "Tasks", "Incidents",
            "Risks", "Releases", "TestSets", "TestRuns", "Documents",
        ]
        for name in artifact_names:
            props = self._get(f"project-templates/{template_id}/custom-properties/{name}")
            if props:
                result[name] = props
        return result

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

    def create_requirement(self, product_id, name, description="", requirement_type_id=None,
                           importance_id=None, owner_id=None, release_id=None,
                           parent_requirement_id=None):
        body = {"Name": name, "Description": description}
        if requirement_type_id is not None:
            body["RequirementTypeId"] = requirement_type_id
        if importance_id is not None:
            body["ImportanceId"] = importance_id
        if owner_id is not None:
            body["OwnerId"] = owner_id
        if release_id is not None:
            body["ReleaseId"] = release_id
        if parent_requirement_id is not None:
            # Insert as child of specified requirement
            return self._post(
                f"projects/{product_id}/requirements/{parent_requirement_id}", body=body)
        return self._post(f"projects/{product_id}/requirements", body=body)

    def update_requirement(self, product_id, requirement_id, **updates):
        """Update a requirement. GETs current state first for concurrency, merges updates, PUTs back."""
        current = self.get_requirement(product_id, requirement_id)
        if not current:
            raise SpiraApiError(404, f"Requirement {requirement_id} not found", "")
        for key, value in updates.items():
            if value is not None:
                current[key] = value
        return self._put(f"projects/{product_id}/requirements", body=current)

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

    def create_task(self, product_id, name, description="", task_status_id=1,
                    task_priority_id=None, owner_id=None, release_id=None,
                    requirement_id=None, estimated_effort=None):
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
        return self._post(f"projects/{product_id}/tasks", body=body)

    def update_task(self, product_id, task_id, **updates):
        """Update a task. GETs current state first for concurrency, merges updates, PUTs back."""
        current = self.get_task(product_id, task_id)
        if not current:
            raise SpiraApiError(404, f"Task {task_id} not found", "")
        for key, value in updates.items():
            if value is not None:
                current[key] = value
        return self._put(f"projects/{product_id}/tasks", body=current)

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

    def create_incident(self, product_id, name, description="", incident_type_id=None,
                        priority_id=None, severity_id=None, owner_id=None,
                        detected_release_id=None):
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
        return self._post(f"projects/{product_id}/incidents", body=body)

    def update_incident(self, product_id, incident_id, **updates):
        """Update an incident. GETs current state first for concurrency, merges updates, PUTs back."""
        current = self.get_incident(product_id, incident_id)
        if not current:
            raise SpiraApiError(404, f"Incident {incident_id} not found", "")
        for key, value in updates.items():
            if value is not None:
                current[key] = value
        return self._put(f"projects/{product_id}/incidents", body=current)

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

    def create_test_case(self, product_id, name, description="", test_case_type_id=None,
                         test_case_priority_id=None, owner_id=None, test_case_folder_id=None,
                         estimated_duration=None, tags=""):
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
        return self._post(f"projects/{product_id}/test-cases", body=body)

    def update_test_case(self, product_id, test_case_id, **updates):
        """Update a test case. GETs current state first for ConcurrencyDate.

        Merges `updates` into the existing object and PUTs the result.
        Returns the updated test case.
        """
        current = self.get_test_case(product_id, test_case_id)
        if not current:
            raise SpiraApiError(404, f"Test case {test_case_id} not found", "")

        # Merge updates into current object
        for key, value in updates.items():
            if value is not None:
                current[key] = value

        return self._put(f"projects/{product_id}/test-cases", body=current)

    def update_test_step(self, product_id, test_case_id, test_step_id, **updates):
        """Update a single test step. GETs current state first for ConcurrencyDate.

        Merges `updates` into the existing step and PUTs the result.
        Returns the updated test step.
        """
        steps = self.get_test_steps(product_id, test_case_id)
        current = next((s for s in steps if s.get("TestStepId") == test_step_id), None)
        if not current:
            raise SpiraApiError(404, f"Test step {test_step_id} not found in TC:{test_case_id}", "")

        # Merge updates into current step
        for key, value in updates.items():
            if value is not None:
                current[key] = value

        return self._put(f"projects/{product_id}/test-cases/{test_case_id}/test-steps", body=current)

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

    def get_test_runs(self, product_id):
        return self._paginate_get(
            f"projects/{product_id}/test-runs",
            params={"sort_field": "EndDate", "sort_direction": "DESC"},
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

    def save_test_runs(self, product_id, test_runs, end_date):
        """Save test runs with step-level results.

        test_runs: array of RemoteManualTestRun objects with TestRunSteps populated.
        end_date: ISO datetime string for the run completion time.
        """
        return self._put(
            f"projects/{product_id}/test-runs",
            body=test_runs,
        )

    def record_test_run(self, product_id, test_case_id, execution_status_id,
                        test_name, short_message="", long_message="", error_count=0,
                        release_id=None, test_set_id=None, build_id=None):
        body = [{
            "TestCaseId": test_case_id,
            "ExecutionStatusId": execution_status_id,
            "RunnerName": test_name,
            "RunnerMessage": short_message,
            "RunnerStackTrace": long_message,
            "CountFailures": error_count,
            "RunnerTestName": test_name,
        }]
        if release_id is not None:
            body[0]["ReleaseId"] = release_id
        if test_set_id is not None:
            body[0]["TestSetId"] = test_set_id
        if build_id is not None:
            body[0]["BuildId"] = build_id
        return self._post(f"projects/{product_id}/test-runs/record", body=body)

    # ──────────────────────────────────────────────
    #  Documents & Attachments
    # ──────────────────────────────────────────────

    def upload_document(self, product_id, filename, binary_data_base64, description="",
                        folder_id=None):
        """Upload a file to Spira. binary_data_base64 is the file content as base64 string."""
        import base64
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
        return self._get(f"projects/{product_id}/test-case-folders") or []

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
        """Get test sets by iterating through test set folders."""
        folders = self._get(f"projects/{product_id}/test-set-folders") or []
        all_sets = []
        for folder in folders:
            folder_id = folder.get("TestSetFolderId")
            if folder_id is not None:
                sets = self._get(
                    f"projects/{product_id}/test-set-folders/{folder_id}/test-sets",
                    params={"starting_row": 1, "number_of_rows": 500},
                ) or []
                all_sets.extend(sets)
        return all_sets

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
        body = {
            "Name": name,
            "Description": description,
            "BuildStatusId": build_status_id,
            "Revisions": [{"RevisionKey": c} for c in (commits or [])],
        }
        return self._post(f"projects/{product_id}/releases/{release_id}/builds", body=body)
