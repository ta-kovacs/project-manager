"""AWS Lambda: sum the size of each project's files in S3 and enforce the per-project storage limit.

Triggered by S3 `ObjectCreated:*` and `ObjectRemoved:*` events for keys under `projects/`. For every
project an event touches it:

1. lists `projects/<id>/documents/` and adds up the object sizes;
2. if the event uploaded files and the total is over PROJECT_STORAGE_LIMIT, rejects the newly uploaded
   files, newest first, until the project fits again: it reports them to
   `POST /internal/projects/<id>/rejected-files` (the API removes their documents), then deletes them
   from S3. Files that were already stored are never removed;
3. sends the resulting total to `PUT /internal/projects/<id>/storage-usage`, which the API stores as the
   project's usage. The API checks uploads against it too, so most over-limit uploads are refused (413)
   before they reach S3; the Lambda enforces the limit on whatever does reach S3.

Invoke it by hand with `{"recompute_all": true}` to measure every project in DOCUMENTS_BUCKET, e.g. right
after setting it up, so projects created before it existed get their usage measured.

Only boto3 (included in the Lambda Python runtime) and the standard library are used, so the deployment
package is this one file.

Environment variables:
  API_BASE_URL                   where the API is reachable, e.g. https://pm.example.com or http://10.0.1.23
  INTERNAL_API_TOKEN_PARAMETER   name of the SSM SecureString holding the API's INTERNAL_API_TOKEN
                                 (e.g. /project-manager/internal-api-token); read once per cold start
  INTERNAL_API_TOKEN             the token itself; used instead of the parameter when set (tests, local runs)
  DOCUMENTS_BUCKET               the documents bucket; only needed for `recompute_all`
  PROJECT_STORAGE_LIMIT          most bytes one project's files may take up (default 104857600, 100 MB);
                                 keep it equal to the API's PROJECT_STORAGE_LIMIT
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Matches the keys the API stores documents under (app/services/document_service.py).
_DOCUMENT_KEY = re.compile(r"^projects/(\d+)/documents/")

_REQUEST_TIMEOUT_SECONDS = 10

# The API's default (app/config.py).
_DEFAULT_STORAGE_LIMIT = 100 * 1024 * 1024

_clients: dict = {}
_token: str | None = None


def _client(service: str):
    # Created once per Lambda container and reused across invocations.
    if service not in _clients:
        _clients[service] = boto3.client(service)
    return _clients[service]


def _internal_api_token() -> str:
    global _token
    if _token is None:
        if os.environ.get("INTERNAL_API_TOKEN"):
            _token = os.environ["INTERNAL_API_TOKEN"]
        else:
            response = _client("ssm").get_parameter(
                Name=os.environ["INTERNAL_API_TOKEN_PARAMETER"], WithDecryption=True
            )
            _token = response["Parameter"]["Value"]
    return _token


def projects_in_event(event: dict) -> set[tuple[str, int]]:
    """The (bucket, project id) pairs whose documents an S3 event notification is about."""
    projects = set()
    for record in event.get("Records", []):
        s3 = record.get("s3")
        if not s3:
            continue
        # Keys arrive URL-encoded (spaces as "+").
        key = unquote_plus(s3["object"]["key"])
        match = _DOCUMENT_KEY.match(key)
        if match:
            projects.add((s3["bucket"]["name"], int(match.group(1))))
        else:
            logger.info("Ignoring %s: not a project document", key)
    return projects


def uploads_in_event(event: dict) -> dict[tuple[str, int], list[str]]:
    """The keys of the files an S3 event uploaded (ObjectCreated), by (bucket, project id), in event order."""
    uploads: dict[tuple[str, int], list[str]] = {}
    for record in event.get("Records", []):
        s3 = record.get("s3")
        if not s3 or not record.get("eventName", "").startswith("ObjectCreated"):
            continue
        key = unquote_plus(s3["object"]["key"])
        match = _DOCUMENT_KEY.match(key)
        if match:
            uploads.setdefault((s3["bucket"]["name"], int(match.group(1))), []).append(key)
    return uploads


def storage_limit() -> int:
    return int(os.environ.get("PROJECT_STORAGE_LIMIT") or _DEFAULT_STORAGE_LIMIT)


def all_projects(s3, bucket: str) -> set[tuple[str, int]]:
    """(bucket, project id) for every project that has a folder in the bucket."""
    projects = set()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="projects/", Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            project_id = prefix["Prefix"].removeprefix("projects/").rstrip("/")
            if project_id.isdigit():
                projects.add((bucket, int(project_id)))
    return projects


def project_files(s3, bucket: str, project_id: int) -> dict[str, int]:
    """The project's document files: key -> size in bytes."""
    files = {}
    pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"projects/{project_id}/documents/")
    for page in pages:
        files.update({item["Key"]: item["Size"] for item in page.get("Contents", [])})
    return files


def measure_project(s3, bucket: str, project_id: int) -> int:
    """Total size in bytes of the project's document files."""
    return sum(project_files(s3, bucket, project_id).values())


def files_to_reject(files: dict[str, int], uploaded: list[str], limit: int) -> list[str]:
    """Which of the just-uploaded files to remove so the project's `files` fit within `limit`.

    The newest uploads go first, and only as many as needed. Files that were already stored are never
    chosen, so a project can stay over the limit (e.g. after the limit was lowered).
    """
    total = sum(files.values())
    rejected: list[str] = []
    for key in reversed(uploaded):
        if total <= limit:
            break
        if key in files and key not in rejected:
            rejected.append(key)
            total -= files[key]
    return rejected


def send_report(url: str, body: dict, token: str, *, method: str = "PUT") -> int:
    """Send `body` as JSON to `url`; returns the HTTP status (raises for network errors)."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def report_usage(project_id: int, total_size_bytes: int, measured_at: datetime) -> None:
    """Send a project's measured usage to the API."""
    base_url = os.environ["API_BASE_URL"].rstrip("/")
    status = send_report(
        f"{base_url}/internal/projects/{project_id}/storage-usage",
        {"total_size_bytes": total_size_bytes, "measured_at": measured_at.isoformat()},
        _internal_api_token(),
    )
    if status == 404:
        # Deleting a project removes its files, which triggers this function after the project is gone.
        logger.info("Project %s no longer exists; nothing to report", project_id)
    elif not 200 <= status < 300:
        raise RuntimeError(f"The API answered {status} to the usage report for project {project_id}")


def report_rejected(project_id: int, storage_keys: list[str]) -> None:
    """Tell the API which files are rejected, so it removes their documents."""
    base_url = os.environ["API_BASE_URL"].rstrip("/")
    status = send_report(
        f"{base_url}/internal/projects/{project_id}/rejected-files",
        {"storage_keys": storage_keys},
        _internal_api_token(),
        method="POST",
    )
    if status == 404:
        logger.info("Project %s no longer exists; its rejected files are only deleted", project_id)
    elif not 200 <= status < 300:
        raise RuntimeError(f"The API answered {status} to the rejected files of project {project_id}")


def enforce_limit(s3, bucket: str, project_id: int, files: dict[str, int], uploaded: list[str]) -> list[str]:
    """Reject the just-uploaded files that take the project over the limit; returns their keys.

    The API is told first and the files are deleted afterwards. If either step fails the invocation fails
    and Lambda retries it: the files are then still there (or the API already forgot them, which it
    tolerates), so no document is ever left pointing at a deleted file.
    """
    limit = storage_limit()
    rejected = files_to_reject(files, uploaded, limit)
    if rejected:
        report_rejected(project_id, rejected)
        for key in rejected:
            s3.delete_object(Bucket=bucket, Key=key)
            del files[key]
        logger.warning("Project %s went over its %s-byte limit; rejected %s", project_id, limit, rejected)
    if sum(files.values()) > limit:
        logger.warning("Project %s is over its %s-byte limit with files stored before", project_id, limit)
    return rejected


def lambda_handler(event: dict, context=None, *, s3=None) -> dict:
    s3 = s3 or _client("s3")
    if event.get("recompute_all"):
        projects = all_projects(s3, os.environ["DOCUMENTS_BUCKET"])
        uploads = {}
    else:
        projects = projects_in_event(event)
        uploads = uploads_in_event(event)

    reported, failed = [], []
    for bucket, project_id in sorted(projects):
        try:
            # Taken before listing, so a measurement that starts later always counts as newer: the API
            # then keeps the most recent state even when Lambda runs finish out of order.
            measured_at = datetime.now(UTC)
            files = project_files(s3, bucket, project_id)
            rejected = enforce_limit(s3, bucket, project_id, files, uploads.get((bucket, project_id), []))
            total = sum(files.values())
            report_usage(project_id, total, measured_at)
        except Exception:
            logger.exception("Could not measure or report project %s", project_id)
            failed.append(project_id)
        else:
            logger.info("Project %s uses %s bytes", project_id, total)
            result = {"project_id": project_id, "total_size_bytes": total}
            if rejected:
                result["rejected"] = rejected
            reported.append(result)

    if failed:
        # Failing the invocation makes Lambda retry it (twice, for S3 events); measuring is idempotent.
        raise RuntimeError(f"Storage usage not reported for projects {failed}")
    return {"reported": reported}
