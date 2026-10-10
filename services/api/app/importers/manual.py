"""Explicitly invoked local fixture importer; no network access or scraping."""

import argparse
import json
from pathlib import Path
from app.models.database import Game, Session, VersionedRecord
from app.schemas.domain import Ruleset


def import_json(path):
    dataset = Ruleset.model_validate(json.loads(Path(path).read_text()))
    with Session.begin() as session:
        session.merge(Game(id=dataset.game, name=dataset.game))
        for kind, records in [
            ("Ruleset", [dataset]),
            ("Champion", dataset.champions),
            ("Trait", dataset.traits),
            ("Emblem", dataset.emblems),
        ]:
            for entity in records:
                session.merge(
                    VersionedRecord(
                        game_id=dataset.game,
                        ruleset_id=dataset.id,
                        kind=kind,
                        entity_id=entity.id,
                        patch=entity.patch,
                        set_id=entity.set,
                        mode=entity.mode,
                        source=entity.source,
                        imported_at=entity.imported_at,
                        verification_status=entity.verification_status,
                        payload=entity.model_dump(),
                    )
                )
    return dataset


def export_json(game_id, ruleset_id, path):
    with Session() as session:
        row = session.get(VersionedRecord, (game_id, ruleset_id, "Ruleset", ruleset_id))
        if row is None:
            raise ValueError("Unknown ruleset")
        Path(path).write_text(json.dumps(row.payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    import_json(args.path)
