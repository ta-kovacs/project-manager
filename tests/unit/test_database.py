"""The Database interface (app/db/interface.py), for both backends.

`any_db` runs each test once with the ORM backend and once with the SQL backend, so the two must behave
the same. The API tests cover both too, but only the one TEST_DATABASE_ACCESS selects per run. The SQL
backend (psycopg) needs PostgreSQL: on the default SQLite database its half is skipped.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.db.interface import ConflictError
from app.db.records import NewDocument, ProjectRole


def as_utc(moment):
    """Timestamps come back naive from SQLite (stored as UTC) and in the session's time zone from PostgreSQL."""
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def new_document(name="spec.pdf", size=10):
    return NewDocument(f"projects/documents/{name}", name, "application/pdf", size)


@pytest.fixture
def alice(any_db):
    user = any_db.users.create("alice", "hash-a")
    any_db.commit()
    return user


@pytest.fixture
def bob(any_db):
    user = any_db.users.create("bob", "hash-b")
    any_db.commit()
    return user


@pytest.fixture
def project(any_db, alice):
    project = any_db.projects.create("Apollo", "Land on the moon", alice.id)
    any_db.commit()
    return project


# --- users --------------------------------------------------------------------------------------


def test_created_user_can_be_found(any_db, alice):
    assert any_db.users.get_by_id(alice.id) == alice
    assert any_db.users.get_by_username("alice") == alice
    assert (alice.username, alice.password_hash) == ("alice", "hash-a")


def test_missing_user_is_none(any_db):
    assert any_db.users.get_by_id(1) is None
    assert any_db.users.get_by_username("nobody") is None


def test_taken_username_conflicts(any_db, alice):
    with pytest.raises(ConflictError):
        any_db.users.create("alice", "other-hash")
    any_db.rollback()

    assert any_db.users.get_by_username("alice") == alice


def test_uncommitted_changes_are_rolled_back(any_db):
    any_db.users.create("carol", "hash")
    any_db.rollback()

    assert any_db.users.get_by_username("carol") is None


# --- projects -----------------------------------------------------------------------------------


def test_created_project_has_owner_and_no_documents(any_db, project, alice):
    assert (project.name, project.description) == ("Apollo", "Land on the moon")
    assert project.owner == alice
    assert project.documents == ()
    assert (project.storage_used_bytes, project.storage_measured_at) == (0, None)
    assert any_db.projects.get_membership(project.id, alice.id).role == ProjectRole.OWNER
    assert any_db.projects.get(project.id) == project


def test_missing_project_is_none(any_db):
    assert any_db.projects.get(1) is None


def test_project_lists_its_documents_oldest_first(any_db, project):
    any_db.documents.create_many(project.id, [new_document("b.pdf"), new_document("a.pdf")])
    any_db.commit()

    names = [d.original_filename for d in any_db.projects.get(project.id).documents]
    assert names == ["b.pdf", "a.pdf"]


def test_list_for_user_includes_owned_and_joined_projects(any_db, alice, bob, project):
    bobs = any_db.projects.create("Gemini", None, bob.id)
    any_db.projects.create("Mercury", None, bob.id)
    any_db.projects.add_member(bobs.id, alice.id, ProjectRole.PARTICIPANT)
    any_db.commit()

    assert [p.name for p in any_db.projects.list_for_user(alice.id)] == ["Apollo", "Gemini"]
    assert [p.owner for p in any_db.projects.list_for_user(alice.id)] == [alice, bob]


def test_update_replaces_details(any_db, project):
    updated = any_db.projects.update(project.id, "Artemis", None)
    any_db.commit()

    assert (updated.name, updated.description) == ("Artemis", None)
    assert any_db.projects.get(project.id) == updated


def test_delete_removes_project_documents_and_memberships(any_db, project, alice, bob):
    any_db.projects.add_member(project.id, bob.id, ProjectRole.PARTICIPANT)
    [document] = any_db.documents.create_many(project.id, [new_document()])
    other = any_db.projects.create("Gemini", None, bob.id)
    any_db.commit()

    any_db.projects.delete(project.id)
    any_db.commit()

    assert any_db.projects.get(project.id) is None
    assert any_db.documents.get(document.id) is None
    assert any_db.projects.get_membership(project.id, bob.id) is None
    assert any_db.projects.get(other.id) is not None


# --- members ------------------------------------------------------------------------------------


def test_added_member_has_their_role(any_db, project, bob):
    membership = any_db.projects.add_member(project.id, bob.id, ProjectRole.PARTICIPANT)
    any_db.commit()

    assert (membership.project_id, membership.user, membership.role) == (project.id, bob, ProjectRole.PARTICIPANT)
    assert any_db.projects.get_membership(project.id, bob.id) == membership


def test_non_member_has_no_membership(any_db, project, bob):
    assert any_db.projects.get_membership(project.id, bob.id) is None


def test_adding_a_member_twice_conflicts(any_db, project, bob):
    any_db.projects.add_member(project.id, bob.id, ProjectRole.PARTICIPANT)
    any_db.commit()

    with pytest.raises(ConflictError):
        any_db.projects.add_member(project.id, bob.id, ProjectRole.PARTICIPANT)
    any_db.rollback()


def test_a_second_owner_conflicts(any_db, project, bob):
    with pytest.raises(ConflictError):
        any_db.projects.add_member(project.id, bob.id, ProjectRole.OWNER)
    any_db.rollback()


# --- storage usage ------------------------------------------------------------------------------


def storage_used(any_db, project):
    return any_db.projects.get(project.id).storage_used_bytes


def test_storage_is_adjusted_within_the_limit(any_db, project):
    assert any_db.projects.adjust_storage_used(project.id, 40, limit=64)
    assert any_db.projects.adjust_storage_used(project.id, 24, limit=64)
    assert not any_db.projects.adjust_storage_used(project.id, 1, limit=64)
    any_db.commit()

    assert storage_used(any_db, project) == 64


def test_storage_can_be_released_and_never_goes_below_zero(any_db, project):
    any_db.projects.adjust_storage_used(project.id, 10)
    any_db.projects.adjust_storage_used(project.id, -25)
    any_db.commit()

    assert storage_used(any_db, project) == 0


def test_adjusting_a_missing_project_changes_nothing(any_db):
    assert not any_db.projects.adjust_storage_used(1, 10)


def test_newer_measurement_replaces_the_usage_and_older_one_is_ignored(any_db, project):
    now = datetime(2026, 11, 9, 10, 0, tzinfo=UTC)

    assert any_db.projects.record_measured_storage(project.id, 100, now)
    assert any_db.projects.record_measured_storage(project.id, 200, now + timedelta(seconds=5))
    assert not any_db.projects.record_measured_storage(project.id, 300, now + timedelta(seconds=1))
    any_db.commit()

    stored = any_db.projects.get(project.id)
    assert stored.storage_used_bytes == 200
    assert as_utc(stored.storage_measured_at) == now + timedelta(seconds=5)


def test_measurement_for_a_missing_project_is_not_stored(any_db):
    assert not any_db.projects.record_measured_storage(1, 100, datetime.now(UTC))


# --- documents ----------------------------------------------------------------------------------


def test_created_documents_can_be_found(any_db, project):
    created = any_db.documents.create_many(project.id, [new_document("a.pdf", 10), new_document("b.pdf", 20)])
    any_db.commit()

    assert [(d.original_filename, d.size_bytes, d.project_id) for d in created] == [
        ("a.pdf", 10, project.id),
        ("b.pdf", 20, project.id),
    ]
    assert any_db.documents.list_for_project(project.id) == created
    assert any_db.documents.get(created[0].id) == created[0]


def test_documents_of_a_project_without_any_are_empty(any_db, project):
    assert any_db.documents.list_for_project(project.id) == []


def test_duplicate_storage_key_is_rejected(any_db, project):
    any_db.documents.create_many(project.id, [new_document("a.pdf")])
    any_db.commit()

    with pytest.raises(Exception):  # noqa: B017  (the database's own integrity error)
        any_db.documents.create_many(project.id, [new_document("a.pdf")])
    any_db.rollback()


def test_update_replaces_the_file_details(any_db, project):
    [document] = any_db.documents.create_many(project.id, [new_document()])
    updated = any_db.documents.update(document.id, "new-key", "report.docx", "application/x-test", 99)
    any_db.commit()

    assert updated == any_db.documents.get(document.id)
    assert (updated.storage_key, updated.original_filename, updated.content_type, updated.size_bytes) == (
        "new-key",
        "report.docx",
        "application/x-test",
        99,
    )


def test_delete_removes_only_that_document(any_db, project):
    first, second = any_db.documents.create_many(project.id, [new_document("a.pdf"), new_document("b.pdf")])
    any_db.documents.delete(first.id)
    any_db.commit()

    assert any_db.documents.list_for_project(project.id) == [second]
