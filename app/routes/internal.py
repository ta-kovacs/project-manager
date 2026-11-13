"""Endpoints for our own AWS Lambda functions; they authenticate with INTERNAL_API_TOKEN, not a user's JWT."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_internal_token
from app.schemas.project_schema import StorageUsageReport
from app.services import project_service

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
    responses={401: {"description": "Missing or invalid internal token"}},
)


@router.put(
    "/projects/{project_id}/storage-usage",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"description": "Project doesn't exist"}},
)
def report_storage_usage(
    project_id: int,
    report: StorageUsageReport,
    session: Session = Depends(get_db),
):
    """Store the total size of a project's files as measured in S3 (called by the storage-usage Lambda).

    The total replaces the API's own running count, which is what uploads are checked against
    (PROJECT_STORAGE_LIMIT). A report older than the last one stored is accepted but ignored.
    """
    try:
        project_service.record_measured_storage(session, project_id, report.total_size_bytes, report.measured_at)
    except project_service.ProjectNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Project not found") from None
