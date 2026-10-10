from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from app.importers.community import (
    MAX_BYTES,
    Attribution,
    Correction,
    correct_row,
    get_import,
    import_guide,
    list_imports,
)

router = APIRouter(prefix="/api/v1/guides", tags=["community guides"])


def run(fn):
    try:
        return fn()
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/import")
async def upload(
    file: UploadFile = File(...),
    game_id: str = Form(...),
    ruleset_id: str = Form(...),
    source_title: str = Form(...),
    attribution: str = Form(...),
    license_status: str = Form(...),
    source_url: str = Form(""),
    sheet: str = Form(""),
):
    try:
        content = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    return await run_in_threadpool(
        run,
        lambda: import_guide(
            content,
            file.filename or "",
            Attribution(
                game_id=game_id,
                ruleset_id=ruleset_id,
                source_title=source_title,
                attribution=attribution,
                license_status=license_status,
                source_url=source_url or None,
                sheet=sheet or None,
            ),
        ),
    )


@router.get("")
def listing(game_id: str, ruleset_id: str):
    return run(lambda: list_imports(game_id, ruleset_id))


@router.get("/{import_id}")
def detail(import_id: str):
    return run(lambda: get_import(import_id))


@router.patch("/{import_id}/rows/{row_id}")
def correction(import_id: str, row_id: str, body: Correction):
    return run(lambda: correct_row(import_id, row_id, body))
