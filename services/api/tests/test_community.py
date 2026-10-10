import io
import csv
import zipfile
from xml.sax.saxutils import escape

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.importers import community as c
from app.main import app
from app.models.database import Base, VersionedRecord
from app.repositories.catalog import get_catalog
from app.optimizer.solver import solve
from app.schemas.domain import SolveRequest


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/guides.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(c, "Session", sessionmaker(engine))
    yield
    engine.dispose()


def metadata(game="TFT", **kwargs):
    return c.Attribution(
        game_id=game,
        ruleset_id=f"fixture_{game.lower()}_v1",
        source_title="Test guide",
        attribution="Community author",
        license_status="unknown",
        **kwargs,
    )


def payload(game="TFT", uncertain=False):
    catalog = get_catalog(game, f"fixture_{game.lower()}_v1")
    emblem = catalog.emblems[0]
    holder = next(u for u in catalog.champions if c.FixtureRules().legal(u, emblem))
    return (
        "emblem_name,emblem_icon_ref,recommended_holders,composition_aliases,label_status,notes\n"
        f"{emblem.zh_CN},icons/example.png,{holder.en_US},测试阵容|Test comp,"
        f"{'uncertain' if uncertain else 'unverified'},source note\n"
    ).encode("utf-8-sig")


def xlsx(rows, sheets=("Guides",)):
    """Independent minimal OOXML fixture (no workbook writer dependency)."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + "".join(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
            + "".join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheets, 1))
            + "</sheets></workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + "</Relationships>",
        )
        xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        for i, row in enumerate(rows, 1):
            xml += (
                f'<row r="{i}">'
                + "".join(
                    f'<c r="{chr(65 + j)}{i}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for j, v in enumerate(row)
                )
                + "</row>"
            )
        xml += "</sheetData></worksheet>"
        for i in range(1, len(sheets) + 1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return stream.getvalue()


@pytest.mark.parametrize("game", ["TFT", "JCC"])
def test_matching_isolation(game):
    batch = c.import_guide(payload(game), "guide.csv", metadata(game))
    row = batch["rows"][0]
    assert row["current"]["status"] == "matched"
    assert row["current"]["emblem_id"] in {e.id for e in get_catalog(game, batch["ruleset_id"]).emblems}
    assert row["current"]["aliases"] == ["测试阵容", "Test comp"]
    assert batch["kind"] == "community_recommendation" and batch["verification_status"] == "unverified"
    assert len(c.list_imports(game, batch["ruleset_id"])) == 1
    other = "JCC" if game == "TFT" else "TFT"
    assert c.list_imports(other, f"fixture_{other.lower()}_v1") == []


def test_xlsx_equivalence_and_sheets():
    rows = list(csv.reader(io.StringIO(payload().decode("utf-8-sig"))))
    assert c.parse_file(payload(), "a.csv")[0] == c.parse_file(xlsx(rows), "a.xlsx")[0]
    multi = xlsx(rows, ("Guides", "Other"))
    with pytest.raises(ValueError, match="sheet"):
        c.parse_file(multi, "a.xlsx")
    assert c.parse_file(multi, "a.xlsx", "Other")[1] == "Other"
    with pytest.raises(ValueError, match="不存在"):
        c.parse_file(multi, "a.xlsx", "Missing")
    assert c.import_guide(xlsx(rows), "a.xlsx", metadata())["rows"][0]["current"]["status"] == "matched"


@pytest.mark.parametrize(
    "content,filename",
    [
        (b"emblem_name,win_rate\nx,0.8", "a.csv"),
        (b"emblem_name,emblem_name\nx,x", "a.csv"),
        (b"notes\nx", "a.csv"),
        (b"emblem_name\nx,y", "a.csv"),
        (b"emblem_name\n=1+1", "a.csv"),
        (b"emblem_name,label_status\nx,verified", "a.csv"),
        (b"emblem_name\n", "a.csv"),
        (b"emblem_name\n\x00x", "a.csv"),
        (b"\xff", "a.csv"),
        (b"badzip", "a.xlsx"),
        (b"x", "a.xls"),
        (b"x" * (c.MAX_BYTES + 1), "a.csv"),
        (b"emblem_name\n" + b"x\n" * 1001, "a.csv"),
    ],
)
def test_invalid_files_atomic(content, filename):
    with pytest.raises(ValueError):
        c.import_guide(content, filename, metadata())
    assert c.list_imports("TFT", "fixture_tft_v1") == []


@pytest.mark.parametrize(
    "replacement", ['<c r="A2"><f>1+1</f></c>', '<c r="A2"><v>123</v></c>', '<c r="A2" t="e"><v>#VALUE!</v></c>']
)
def test_xlsx_cells_rejected(replacement):
    original = xlsx([["emblem_name"], ["value"]])
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(stream, "w") as dest:
        for name in source.namelist():
            value = source.read(name)
            if name.endswith("sheet1.xml"):
                value = value.replace(b'<c r="A2" t="inlineStr"><is><t>value</t></is></c>', replacement.encode())
            dest.writestr(name, value)
    with pytest.raises(ValueError):
        c.parse_file(stream.getvalue(), "a.xlsx")


def test_unknown_ambiguous_illegal_labels():
    catalog = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    for emblem in catalog.emblems[:2]:
        emblem.aliases.append("ambiguous")
    assert c.evaluate({"emblem_name": "ambiguous"}, catalog)["status"] == "needs_review"
    emblem = catalog.emblems[0]
    native = next(u for u in catalog.champions if emblem.trait_id in u.traits)
    assert c.evaluate({"emblem_name": emblem.id, "recommended_holders": native.id}, catalog)["issues"]
    foreign = get_catalog("JCC", "fixture_jcc_v1").emblems[0].id
    assert c.evaluate({"emblem_name": foreign}, catalog)["emblem_id"] is None
    assert c.evaluate({"emblem_icon_ref": "https://example.org/icon.png"}, catalog)["status"] == "needs_review"
    assert c.resolve("  " + emblem.en_US.upper() + " ", catalog.emblems).id == emblem.id


def correction(row, **kwargs):
    return c.Correction(
        expected_revision=row["revision"],
        emblem_name=row["raw"]["emblem_name"],
        recommended_holders=row["raw"]["recommended_holders"],
        reviewer="Reviewer",
        correction_note="Checked catalog",
        **kwargs,
    )


def test_audit_idempotency_conflicts():
    batch = c.import_guide(payload(uncertain=True), "a.csv", metadata())
    row = batch["rows"][0]
    assert row["current"]["status"] == "needs_review"
    reviewed = c.correct_row(batch["id"], row["id"], correction(row, confirm=True))["rows"][0]
    assert reviewed["current"]["status"] == "reviewed" and reviewed["revision"] == 2
    assert reviewed["raw"] == row["raw"] and reviewed["history"][0]["before"] == row["current"]
    assert reviewed["history"][0]["reviewer"] == "Reviewer"
    assert c.import_guide(payload(uncertain=True), "a.csv", metadata())["rows"][0] == reviewed
    with pytest.raises(RuntimeError):
        c.correct_row(batch["id"], row["id"], correction(row))
    with pytest.raises(ValueError, match="无法确认"):
        c.correct_row(
            batch["id"], row["id"], correction(reviewed, confirm=True).model_copy(update={"emblem_name": "unknown"})
        )
    assert c.get_import(batch["id"])["rows"][0]["revision"] == 2
    with pytest.raises(LookupError):
        c.correct_row("other", row["id"], correction(reviewed))


def test_optimizer_and_statistics_unchanged():
    catalog = get_catalog("TFT", "fixture_tft_v1")
    request = SolveRequest(
        game_id="TFT", ruleset_id=catalog.id, emblem_ids=[e.id for e in catalog.emblems[:3]], top_k=1
    )
    before = solve(catalog, request)
    c.import_guide(payload(), "a.csv", metadata())
    after = solve(catalog, request)
    assert before["candidates"][0]["objective_value"] == after["candidates"][0]["objective_value"]
    assert before["candidates"][0]["traits"] == after["candidates"][0]["traits"]
    with c.Session() as session:
        assert session.scalars(select(VersionedRecord)).all() == []


def test_http_contract():
    client = TestClient(app)
    data = metadata().model_dump(exclude_none=True)
    response = client.post("/api/v1/guides/import", data=data, files={"file": ("a.csv", payload(), "text/csv")})
    assert response.status_code == 200, response.text
    batch = response.json()
    assert client.get(f"/api/v1/guides/{batch['id']}").json() == batch
    row = batch["rows"][0]
    endpoint = f"/api/v1/guides/{batch['id']}/rows/{row['id']}"
    body = correction(row, confirm=True).model_dump()
    assert client.patch(endpoint, json=body).status_code == 200
    assert client.patch(endpoint, json=body).status_code == 409
    assert client.get("/api/v1/guides/missing").status_code == 404
    assert client.get("/api/v1/guides", params={"game_id": "JCC", "ruleset_id": "fixture_tft_v1"}).status_code == 422
    for change in ({"attribution": ""}, {"source_url": "file:///etc/passwd"}, {"license_status": "verified"}):
        assert (
            client.post(
                "/api/v1/guides/import", data={**data, **change}, files={"file": ("a.csv", payload())}
            ).status_code
            == 422
        )
    assert (
        client.options(
            endpoint, headers={"Origin": "http://127.0.0.1:3000", "Access-Control-Request-Method": "PATCH"}
        ).status_code
        == 200
    )


def test_manual_label_change_draft_then_confirm_and_raw_whitespace():
    original = b"emblem_name,emblem_icon_ref,recommended_holders,label_status\n  typo  ,icon.png,unknown,uncertain\n"
    batch = c.import_guide(original, "a.csv", metadata())
    row = batch["rows"][0]
    assert row["raw"]["emblem_name"] == "  typo  "
    body = c.Correction(
        expected_revision=1,
        emblem_name="tft_emblem_0",
        recommended_holders="tft_unit_1",
        reviewer="QA",
        correction_note="Corrected source typo",
    )
    draft = c.correct_row(batch["id"], row["id"], body)["rows"][0]
    assert draft["current"]["emblem_id"] == "tft_emblem_0"
    assert draft["current"]["holders"][0]["champion_id"] == "tft_unit_1"
    assert draft["current"]["status"] == "needs_review"
    confirmed = c.correct_row(batch["id"], row["id"], body.model_copy(update={"expected_revision": 2, "confirm": True}))
    assert confirmed["rows"][0]["current"]["status"] == "reviewed"
    assert confirmed["rows"][0]["raw"] == row["raw"]
    assert len(confirmed["rows"][0]["history"]) == 2


def test_catalog_change_blocks_review(monkeypatch):
    batch = c.import_guide(payload(), "a.csv", metadata())
    catalog = get_catalog("TFT", "fixture_tft_v1").model_copy(deep=True)
    catalog.champions[0].zh_CN = "Changed catalog"
    monkeypatch.setattr(c, "get_catalog", lambda *_: catalog)
    row = batch["rows"][0]
    with pytest.raises(RuntimeError, match="目录内容已改变"):
        c.correct_row(batch["id"], row["id"], correction(row, confirm=True))


def test_migration_preserves_existing_records(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect, text

    url = f"sqlite:///{tmp_path}/migration.db"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0001")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO games (id, name) VALUES ('TFT', 'Existing game')"))
    command.upgrade(config, "head")
    assert {"community_imports", "community_rows"} <= set(inspect(engine).get_table_names())
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM games")).scalar_one() == "Existing game"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0003"
    command.downgrade(config, "0001")
    assert "community_imports" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    engine.dispose()


def test_concurrent_identical_imports():
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(lambda _: c.import_guide(payload(), "a.csv", metadata()), range(4)))
    assert len({batch["id"] for batch in batches}) == 1
    assert len(c.list_imports("TFT", "fixture_tft_v1")) == 1
    assert all(len(batch["rows"]) == 1 for batch in batches)


@pytest.mark.parametrize("name", ["xl/externalLinks/link1.xml", "xl/vbaProject.bin"])
def test_external_links_and_macros_rejected(name):
    original = xlsx([["emblem_name"], ["tft_emblem_0"]])
    stream = io.BytesIO(original)
    with zipfile.ZipFile(stream, "a") as archive:
        archive.writestr(name, "rejected")
    with pytest.raises(ValueError, match="外部链接或宏"):
        c.parse_file(stream.getvalue(), "a.xlsx")


def test_xlsx_archive_and_dimension_limits():
    stream = io.BytesIO(xlsx([["emblem_name"], ["tft_emblem_0"]]))
    with zipfile.ZipFile(stream, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("oversize.xml", b"x" * (20 * 1024 * 1024))
    with pytest.raises(ValueError, match="解压大小"):
        c.parse_file(stream.getvalue(), "a.xlsx")
    with pytest.raises(ValueError, match="1000"):
        c.parse_file(xlsx([["emblem_name"]] + [["x"]] * 1001), "a.xlsx")
    with pytest.raises(ValueError, match="6 列"):
        c.parse_file(xlsx([["x"] * 7]), "a.xlsx")
