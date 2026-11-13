"""The storage-usage Lambda (lambdas/storage_usage/handler.py), against a moto-mocked S3 bucket."""

import json
import urllib.error
from datetime import datetime

import boto3
import pytest

from app.storage import S3Storage
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

    def fake_send_report(url, body, token):
        reports.append({"url": url, "body": body, "token": token})
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

    def send_through_test_client(url, body, token):
        path = url.removeprefix(API)
        return client.put(path, json=body, headers={"Authorization": f"Bearer {token}"}).status_code

    monkeypatch.setattr(handler, "send_report", send_through_test_client)

    handler.lambda_handler(s3_event(s3_bucket, f"projects/{project['id']}/documents/a"), None, s3=s3_client)

    assert storage_used(project["id"]) == 350
