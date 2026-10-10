import json
import csv
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.data_validation.catalog import validate_catalog
from app.importers.game_manual import COLUMNS, MAX_BYTES, ManualMetadata, import_manual

router = APIRouter(prefix="/api/v1/data", tags=["static game data review"])


@router.get("/manual-template")
def template():
    return dict(
        columns=COLUMNS,
        verification_states=["VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "SYNTHETIC", "UNSUPPORTED"],
        game="JCC",
        activated=False,
    )


@router.post("/validate")
def validate(raw: dict):
    return validate_catalog(raw)


@router.post("/manual/validate")
async def manual(file: UploadFile = File(...), metadata: str = Form(...)):
    try:
        content = await file.read(MAX_BYTES + 1)
        parsed = ManualMetadata.model_validate(json.loads(metadata))
        return await run_in_threadpool(import_manual, content, file.filename or "", parsed)
    except (ValueError, KeyError, UnicodeError, OSError, csv.Error, zipfile.BadZipFile) as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        await file.close()
