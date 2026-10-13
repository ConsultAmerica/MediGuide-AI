from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.auth.dependencies import require_user
from src.database.models import User
from src.labs.service import (
    delete_document_labs,
    delete_lab_observation,
    get_observation_detail,
    latest_summary,
    list_tests,
    timeline_for_test,
)

# Lab observations are only ever created by confirming a reviewed document
# (POST /api/documents/v2/{id}/confirm). There is deliberately no route that
# writes observations directly — that would bypass human review and let a
# caller assert arbitrary provenance.
router = APIRouter(prefix="/api/labs", tags=["Lab Timeline"])


@router.get("/tests")
def get_tests(user: User = Depends(require_user)) -> dict[str, object]:
    tests = list_tests(user.id)
    return {"count": len(tests), "tests": tests}


@router.get("/timeline/{test_code}")
def get_timeline(test_code: str, user: User = Depends(require_user)) -> dict[str, object]:
    points = timeline_for_test(test_code, user.id)
    return {
        "test_code": test_code,
        "count": len(points),
        "points": points,
    }


@router.get("/summary")
def get_summary(user: User = Depends(require_user)) -> dict[str, object]:
    points = latest_summary(user.id)
    return {"count": len(points), "points": points}


@router.get("/observations/{observation_id}")
def get_observation(observation_id: str, user: User = Depends(require_user)) -> dict[str, object]:
    detail = get_observation_detail(observation_id, user.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return detail


@router.delete("/observations/{observation_id}")
def remove_observation(observation_id: str, user: User = Depends(require_user)) -> dict[str, object]:
    deleted = delete_lab_observation(observation_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Observation not found.")
    return {"deleted": True, "observation_id": observation_id}


@router.delete("/documents/{document_id}")
def remove_document_labs(document_id: str, user: User = Depends(require_user)) -> dict[str, object]:
    count = delete_document_labs(document_id, user.id)
    return {"deleted": True, "document_id": document_id, "observation_count": count}
