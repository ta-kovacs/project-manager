"""The storage-usage Lambda (lambdas/storage_usage/handler.py), against a moto-mocked S3 bucket."""

import json
import urllib.error
from datetime import datetime

import boto3
import pytest

from app.main import app
from app.storage import S3Storage, get_storage
from lambdas.storage_usage import handler

API = "https://api.test"


def s3_event(bucket, *keys, event_name="ObjectCreated:Put"):
    """An S3 event notification as Lambda receives it (keys URL-encoded, like S3 sends them)."""
    return {
        "Records": [
            {"eventName": event_name, "s3": {"bucket": {"name": bucket}, "object": {"key": key, "size": 1}}}
            for key in keys
        ]
    }


@pytest.fixture
def lambda_env(monkeypatch, s3_bucket):
    monkeypatch.setenv("API_BASE_URL", API)
    monkeypatch.setenv("INTERNAL_API_TOKEN", "lambda-token")
    monkeypatch.setenv("DOCUMENTS_BUCKET", s3_bucket)
    monkeypatch.setattr(handler, "_token", None)


class _Reports(list):
    """The reports sent; each is answered with `status`."""

    status = 204


@pytest.fixture
def sent_reports(monkeypatch, lambda_env):
    """Records the reports the Lambda sends instead of sending them; set `.status` to answer differently."""
    reports = _Reports()

    def fake_send_report(url, body, token, *, method="PUT"):
        reports.append({"method": method, "url": url, "body": body, "token": token})
        return reports.status

    monkeypatch.setattr(handler, "send_report", fake_send_report)
    return reports


def put(s3_client, bucket, key, size):
    s3_client.put_object(Bucket=bucket, Key=key, Body=b"x" * size)


# --- reading events -----------------------------------------------------------------------------


def test_projects_in_event_finds_each_project_once():
    event = s3_event(
        "docs",
        "projects/7/documents/a",
        "projects/7/documents/b",
        "projects/12/documents/c",
    )

    assert handler.projects_in_event(event) == {("docs", 7), ("docs", 12)}


def test_projects_in_event_ignores_other_keys():
    event = s3_event("docs", "projects/7/usage.json", "uploads/projects/7/documents/a", "projects/x/documents/a")

    assert handler.projects_in_event(event) == set()


def test_projects_in_event_decodes_keys():
    assert handler.projects_in_event(s3_event("docs", "projects/7/documents/my+file%21")) == {("docs", 7)}


def test_projects_in_event_ignores_records_without_s3_data():
    assert handler.projects_in_event({"Records": [{"eventSource": "aws:sqs"}]}) == set()


# --- measuring ----------------------------------------------------------------------------------


def test_measure_project_sums_only_that_projects_documents(s3_client, s3_bucket):
    put(s3_client, s3_bucket, "projects/1/documents/a", 100)
    put(s3_client, s3_bucket, "projects/1/documents/b", 23)
    put(s3_client, s3_bucket, "projects/10/documents/c", 1000)  # "projects/1" is a prefix of it

    assert handler.measure_project(s3_client, s3_bucket, 1) == 123


def test_measure_project_without_files_is_zero(s3_client, s3_bucket):
    assert handler.measure_project(s3_client, s3_bucket, 1) == 0


def test_measure_project_reads_every_page(s3_client, s3_bucket):
    # list_objects_v2 returns at most 1000 keys per page
    for i in range(1005):
        put(s3_client, s3_bucket, f"projects/1/documents/{i}", 1)

    assert handler.measure_project(s3_client, s3_bucket, 1) == 1005


# --- reporting ----------------------------------------------------------------------------------


def test_handler_reports_each_touched_project(s3_client, s3_bucket, sent_reports):
    put(s3_client, s3_bucket, "projects/1/documents/a", 100)
    put(s3_client, s3_bucket, "projects/2/documents/b", 7)

    result = handler.lambda_handler(
        s3_event(s3_bucket, "projects/1/documents/a", "projects/2/documents/b"), None, s3=s3_client
    )

    assert result == {
        "reported": [{"project_id": 1, "total_size_bytes": 100}, {"project_id": 2, "total_size_bytes": 7}]
    }
    assert [(r["url"], r["body"]["total_size_bytes"], r["token"]) for r in sent_reports] == [
        (f"{API}/internal/projects/1/storage-usage", 100, "lambda-token"),
        (f"{API}/internal/projects/2/storage-usage", 7, "lambda-token"),
    ]
    assert datetime.fromisoformat(sent_reports[0]["body"]["measured_at"]).utcoffset().total_seconds() == 0


def test_handler_reports_zero_after_the_last_file_is_removed(s3_client, s3_bucket, sent_reports):
    event = s3_event(s3_bucket, "projects/1/documents/a", event_name="ObjectRemoved:Delete")

    handler.lambda_handler(event, None, s3=s3_client)

    assert sent_reports[0]["body"]["total_size_bytes"] == 0


def test_handler_recompute_all_reports_every_project(s3_client, s3_bucket, sent_reports):
    put(s3_client, s3_bucket, "projects/1/documents/a", 5)
    put(s3_client, s3_bucket, "projects/3/documents/b", 6)
    put(s3_client, s3_bucket, "unrelated/file", 99)

    result = handler.lambda_handler({"recompute_all": True}, None, s3=s3_client)

    assert result == {"reported": [{"project_id": 1, "total_size_bytes": 5}, {"project_id": 3, "total_size_bytes": 6}]}


def test_handler_skips_projects_that_no_longer_exist(s3_client, s3_bucket, sent_reports):
    sent_reports.status = 404

    result = handler.lambda_handler(s3_event(s3_bucket, "projects/1/documents/a"), None, s3=s3_client)

    assert result == {"reported": [{"project_id": 1, "total_size_bytes": 0}]}


def test_handler_fails_when_a_report_is_refused_so_lambda_retries(s3_client, s3_bucket, sent_reports):
    sent_reports.status = 401

    with pytest.raises(RuntimeError, match=r"projects \[1\]"):
        handler.lambda_handler(s3_event(s3_bucket, "projects/1/documents/a"), None, s3=s3_client)


def test_handler_still_reports_other_projects_when_one_fails(s3_client, s3_bucket, monkeypatch, lambda_env):
    sent = []

    def flaky_send_report(url, body, token):
        if "/projects/1/" in url:
            raise urllib.error.URLError("connection refused")
        sent.append(url)
        return 204

    monkeypatch.setattr(handler, "send_report", flaky_send_report)

    with pytest.raises(RuntimeError):
        handler.lambda_handler(
            s3_event(s3_bucket, "projects/1/documents/a", "projects/2/documents/b"), None, s3=s3_client
        )
    assert sent == [f"{API}/internal/projects/2/storage-usage"]


def test_send_report_puts_json_with_the_token(monkeypatch):
    seen = {}

    class FakeResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        seen.update(
            method=request.get_method(),
            url=request.full_url,
            body=json.loads(request.data),
            auth=request.get_header("Authorization"),
            content_type=request.get_header("Content-type"),
        )
        return FakeResponse()

    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen)

    status = handler.send_report(f"{API}/x", {"total_size_bytes": 1}, "tok")

    assert status == 204
    assert seen == {
        "method": "PUT",
        "url": f"{API}/x",
        "body": {"total_size_bytes": 1},
        "auth": "Bearer tok",
        "content_type": "application/json",
    }


def test_send_report_returns_http_error_status(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen)

    assert handler.send_report(f"{API}/x", {}, "tok") == 404


def test_token_is_read_from_ssm_when_not_given_directly(monkeypatch, s3_client):
    # s3_client sets fake AWS credentials and starts moto
    ssm = boto3.client("ssm")
    ssm.put_parameter(Name="/project-manager/internal-api-token", Value="from-ssm", Type="SecureString")
    monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    monkeypatch.setenv("INTERNAL_API_TOKEN_PARAMETER", "/project-manager/internal-api-token")
    monkeypatch.setattr(handler, "_token", None)
    monkeypatch.setitem(handler._clients, "ssm", ssm)

    assert handler._internal_api_token() == "from-ssm"


# --- with the real API --------------------------------------------------------------------------


def test_lambda_corrects_the_apis_storage_usage(
    client, s3_client, s3_bucket, project, auth, internal_token, storage_used, monkeypatch, lambda_env
):
    """S3 holds more than the API counted (e.g. a file left behind by a failed delete): the Lambda's
    measurement replaces the API's count."""
    storage = S3Storage(s3_bucket, client=s3_client)
    storage.save(f"projects/{project['id']}/documents/a", b"x" * 300)
    storage.save(f"projects/{project['id']}/documents/orphan", b"x" * 50)
    monkeypatch.setenv("INTERNAL_API_TOKEN", internal_token)

    def send_through_test_client(url, body, token, *, method="PUT"):
        path = url.removeprefix(API)
        return client.request(method, path, json=body, headers={"Authorization": f"Bearer {token}"}).status_code

    monkeypatch.setattr(handler, "send_report", send_through_test_client)

    handler.lambda_handler(s3_event(s3_bucket, f"projects/{project['id']}/documents/a"), None, s3=s3_client)

    assert storage_used(project["id"]) == 350


# --- enforcing the storage limit ----------------------------------------------------------------

LIMIT = 64


@pytest.fixture
def limit(monkeypatch):
    monkeypatch.setenv("PROJECT_STORAGE_LIMIT", str(LIMIT))
    return LIMIT


def stored_keys(s3_client, bucket):
    return sorted(item["Key"] for item in s3_client.list_objects_v2(Bucket=bucket).get("Contents", []))


def test_uploads_in_event_lists_uploaded_files_by_project():
    event = {
        "Records": [
            *s3_event("docs", "projects/7/documents/a", "projects/7/documents/my+file", "projects/9/documents/c")[
                "Records"
            ],
            *s3_event("docs", "projects/7/documents/old", event_name="ObjectRemoved:Delete")["Records"],
            *s3_event("docs", "projects/7/usage.json")["Records"],
        ]
    }

    assert handler.uploads_in_event(event) == {
        ("docs", 7): ["projects/7/documents/a", "projects/7/documents/my file"],
        ("docs", 9): ["projects/9/documents/c"],
    }


def test_storage_limit_defaults_to_the_apis(monkeypatch):
    monkeypatch.delenv("PROJECT_STORAGE_LIMIT", raising=False)

    assert handler.storage_limit() == 100 * 1024 * 1024


@pytest.mark.parametrize(
    ("files", "uploaded", "expected"),
    [
        pytest.param({"old": 30, "new": 30}, ["new"], [], id="within-the-limit"),
        pytest.param({"old": 40, "new": 30}, ["new"], ["new"], id="over-the-limit"),
        pytest.param({"a": 30, "b": 30, "c": 30}, ["a", "b", "c"], ["c"], id="newest-first-only-as-needed"),
        pytest.param({"a": 30, "b": 30, "c": 30}, ["a", "b", "c", "c"], ["c"], id="each-key-once"),
        pytest.param({"old": 100, "new": 10}, ["new"], ["new"], id="never-older-files"),
        pytest.param({"old": 70}, ["gone"], [], id="uploads-no-longer-stored"),
    ],
)
def test_files_to_reject(files, uploaded, expected):
    assert handler.files_to_reject(files, uploaded, LIMIT) == expected


def test_upload_over_the_limit_is_rejected(s3_client, s3_bucket, sent_reports, limit):
    put(s3_client, s3_bucket, "projects/1/documents/old", 40)
    put(s3_client, s3_bucket, "projects/1/documents/new", 30)

    result = handler.lambda_handler(s3_event(s3_bucket, "projects/1/documents/new"), None, s3=s3_client)

    assert result == {"reported": [{"project_id": 1, "total_size_bytes": 40, "rejected": ["projects/1/documents/new"]}]}
    assert stored_keys(s3_client, s3_bucket) == ["projects/1/documents/old"]
    # The API hears about the rejected file first, then gets the new total.
    assert [
        (r["method"], r["url"], r["body"].get("storage_keys"), r["body"].get("total_size_bytes")) for r in sent_reports
    ] == [
        ("POST", f"{API}/internal/projects/1/rejected-files", ["projects/1/documents/new"], None),
        ("PUT", f"{API}/internal/projects/1/storage-usage", None, 40),
    ]


def test_upload_within_the_limit_is_kept(s3_client, s3_bucket, sent_reports, limit):
    put(s3_client, s3_bucket, "projects/1/documents/new", 64)

    result = handler.lambda_handler(s3_event(s3_bucket, "projects/1/documents/new"), None, s3=s3_client)

    assert result == {"reported": [{"project_id": 1, "total_size_bytes": 64}]}
    assert stored_keys(s3_client, s3_bucket) == ["projects/1/documents/new"]
    assert [r["method"] for r in sent_reports] == ["PUT"]


def test_only_as_many_uploads_as_needed_are_rejected(s3_client, s3_bucket, sent_reports, limit):
    keys = [f"projects/1/documents/{name}" for name in ("a", "b", "c")]
    for key in keys:
        put(s3_client, s3_bucket, key, 30)

    handler.lambda_handler(s3_event(s3_bucket, *keys), None, s3=s3_client)

    assert stored_keys(s3_client, s3_bucket) == keys[:2]


def test_files_stored_before_are_never_removed(s3_client, s3_bucket, sent_reports, limit):
    # e.g. the limit was lowered after the project filled up
    put(s3_client, s3_bucket, "projects/1/documents/old", 100)
    put(s3_client, s3_bucket, "projects/1/documents/new", 10)

    result = handler.lambda_handler(s3_event(s3_bucket, "projects/1/documents/new"), None, s3=s3_client)

    assert stored_keys(s3_client, s3_bucket) == ["projects/1/documents/old"]
    assert result["reported"][0]["total_size_bytes"] == 100


def test_removals_never_reject_anything(s3_client, s3_bucket, sent_reports, limit):
    put(s3_client, s3_bucket, "projects/1/documents/old", 100)
    event = s3_event(s3_bucket, "projects/1/documents/other", event_name="ObjectRemoved:Delete")

    handler.lambda_handler(event, None, s3=s3_client)

    assert stored_keys(s3_client, s3_bucket) == ["projects/1/documents/old"]
    assert [r["method"] for r in sent_reports] == ["PUT"]


def test_nothing_is_deleted_when_the_api_refuses_the_rejection(s3_client, s3_bucket, sent_reports, limit):
    # The invocation fails and Lambda retries it; the file must still be there for the retry.
    put(s3_client, s3_bucket, "projects/1/documents/new", 100)
    sent_reports.status = 500

    with pytest.raises(RuntimeError, match=r"projects \[1\]"):
        handler.lambda_handler(s3_event(s3_bucket, "projects/1/documents/new"), None, s3=s3_client)

    assert stored_keys(s3_client, s3_bucket) == ["projects/1/documents/new"]


def test_rejected_files_of_a_deleted_project_are_still_deleted(s3_client, s3_bucket, sent_reports, limit):
    put(s3_client, s3_bucket, "projects/1/documents/new", 100)
    sent_reports.status = 404

    handler.lambda_handler(s3_event(s3_bucket, "projects/1/documents/new"), None, s3=s3_client)

    assert stored_keys(s3_client, s3_bucket) == []


def test_lambda_rejects_an_upload_over_the_limit_end_to_end(
    client,
    s3_client,
    s3_bucket,
    project,
    upload_documents,
    list_project_documents,
    storage_used,
    db,
    internal_token,
    monkeypatch,
    lambda_env,
    limit,
):
    """A file uploaded through the API takes the project over the Lambda's limit: the Lambda deletes it
    from S3 and the API removes its document."""
    app.dependency_overrides[get_storage] = lambda: S3Storage(s3_bucket, client=s3_client)
    monkeypatch.setenv("INTERNAL_API_TOKEN", internal_token)

    def send_through_test_client(url, body, token, *, method="PUT"):
        path = url.removeprefix(API)
        return client.request(method, path, json=body, headers={"Authorization": f"Bearer {token}"}).status_code

    monkeypatch.setattr(handler, "send_report", send_through_test_client)
    [kept] = upload_documents(project["id"], files=[("kept.pdf", b"x" * 40)]).json()
    [big] = upload_documents(project["id"], files=[("big.pdf", b"x" * 30)]).json()
    kept_key, big_key = (db.documents.get(d["id"]).storage_key for d in (kept, big))

    # S3 sends one event per uploaded file; this is the one for big.pdf.
    result = handler.lambda_handler(s3_event(s3_bucket, big_key), None, s3=s3_client)

    assert result["reported"][0]["rejected"] == [big_key]
    assert stored_keys(s3_client, s3_bucket) == [kept_key]
    assert [d["id"] for d in list_project_documents(project["id"]).json()] == [kept["id"]]
    assert storage_used(project["id"]) == 40
