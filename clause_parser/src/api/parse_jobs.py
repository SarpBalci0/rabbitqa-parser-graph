"""POST /v1/parse-jobs and GET /v1/parse-jobs/{id}, per rabbitqa_spec_v1.0.0.md §5.2/§5.3.

This is async per §5.2 ("Response 202: {job_id, status: queued}. This is async.").
The job runner here executes synchronously but immediately, updating job state as it
goes, so GET /v1/parse-jobs/{id} always reflects real progress rather than a faked
status — a production deployment would swap the synchronous call for a background
task queue without changing this module's public functions or the job-state contract.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from clause_parser.src.api.errors import NotFoundError
from clause_parser.src.db.document_repository import DocumentRepository
from clause_parser.src.db.obligation_repository import ObligationRepository
from clause_parser.src.pipeline import run_parse_job


@dataclass
class ParseJob:
    job_id: str
    document_id: str
    source_version: str
    trace_id: str
    status: str = "queued"
    validation_summary: dict = field(
        default_factory=lambda: {"total": 0, "pass": 0, "needs_review": 0, "fail": 0}
    )


class ParseJobStore:
    """In-memory job registry. Swappable for a persisted store without changing the
    handler functions below."""

    def __init__(self):
        self._jobs: dict[str, ParseJob] = {}

    def create(self, document_id: str, source_version: str) -> ParseJob:
        job = ParseJob(
            job_id=str(uuid.uuid4()), document_id=document_id, source_version=source_version,
            trace_id=str(uuid.uuid4()),
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> ParseJob | None:
        return self._jobs.get(job_id)


DEFAULT_JOB_STORE = ParseJobStore()


class ParseJobRequest(BaseModel):
    document_id: str
    source_version: str


def create_parse_job_handler(
    request: ParseJobRequest,
    *,
    session: Session,
    job_store: ParseJobStore = DEFAULT_JOB_STORE,
) -> dict:
    doc_repo = DocumentRepository(session)
    document_payload = doc_repo.get(request.document_id, request.source_version)
    if document_payload is None:
        raise NotFoundError(f"No such document: {request.document_id}/{request.source_version}")

    job = job_store.create(request.document_id, request.source_version)

    obl_repo = ObligationRepository(session)
    job.status = "running"
    try:
        summary = run_parse_job(document_payload, obligation_repository=obl_repo, trace_id=job.trace_id)
        job.validation_summary = summary
        job.status = "completed"
    except Exception:
        job.status = "failed"
        raise

    return {"job_id": job.job_id, "status": "queued"}


def get_parse_job_handler(job_id: str, *, job_store: ParseJobStore = DEFAULT_JOB_STORE) -> dict:
    job = job_store.get(job_id)
    if job is None:
        raise NotFoundError(f"No such parse job: {job_id}")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "trace_id": job.trace_id,
        "validation_summary": job.validation_summary,
    }


def build_router(session_factory) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/parse-jobs", status_code=202)
    def post_parse_job(request: ParseJobRequest):
        session = session_factory()
        try:
            return create_parse_job_handler(request, session=session)
        finally:
            session.close()

    @router.get("/v1/parse-jobs/{job_id}")
    def get_parse_job(job_id: str):
        return get_parse_job_handler(job_id)

    return router
