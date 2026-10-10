from fastapi import APIRouter, HTTPException

from app.meta.engine import analyze
from app.meta.schemas import AdaptRequest, StrategyRequest

router = APIRouter(tags=["Phase 1 internal emblem strategy"])


def guarded(fn):
    try:
        return fn()
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/api/v1/emblem-strategy/analyze")
def strategy(request: StrategyRequest):
    return guarded(lambda: analyze(request))


@router.post("/api/v1/meta/adapt")
def adapt(request: AdaptRequest):
    return guarded(lambda: analyze(request, retain_subsets=False))
