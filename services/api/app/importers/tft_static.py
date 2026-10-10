"""Fixed-snapshot TFT import. No live HTTP requests occur during optimization."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from app.data_validation.catalog import validate_catalog
from app.schemas.domain import Ruleset

ROOT = Path(__file__).resolve().parents[4]
OVERVIEW = "https://teamfighttactics.leagueoflegends.com/en-sg/news/game-updates/enchanted-wilds-overview/"
PATCH = "https://teamfighttactics.leagueoflegends.com/en-us/news/game-updates/teamfight-tactics-patch-18-4/"


def snapshot(folder, entry):
    content = (folder / entry["filename"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError(f"Snapshot checksum mismatch: {entry['filename']}")
    return json.loads(content)


def scoped(data, prefix):
    rows = [v for k, v in data["data"].items() if k.startswith(prefix)]
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate official entity IDs")
    return {r["id"]: r for r in rows}


def import_snapshot(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest["game"] != "TFT" or manifest["mode"] != "standard" or not manifest["mutator"]:
        raise ValueError("Explicit TFT standard mode selection required")
    if tuple(manifest[key] for key in ["set_number", "mutator", "patch", "resource_patch"]) != (
        18,
        "TFTSet18",
        "18.4",
        "16.20.1",
    ):
        raise ValueError("Unreviewed set/patch/resource profile; a new rules audit is required")
    filenames = [entry["filename"] for entry in manifest["snapshots"]]
    if len(filenames) != len(set(filenames)):
        raise ValueError("Duplicate snapshot identity")
    folder = ROOT / manifest["snapshot_directory"]
    data = {e["filename"]: snapshot(folder, e) for e in manifest["snapshots"]}
    en, zh = data["en_us.json"], data["zh_cn.json"]

    def select(blob):
        matches = [
            s for s in blob["setData"] if s["number"] == manifest["set_number"] and s["mutator"] == manifest["mutator"]
        ]
        if len(matches) != 1:
            raise ValueError("Set/mode must resolve uniquely")
        return matches[0]

    se, sz = select(en), select(zh)
    # The upstream display name is stale (Set10). Never use it as the identity.
    traits_en = {t["apiName"]: t for t in se["traits"]}
    traits_zh = {t["apiName"]: t for t in sz["traits"]}
    if len(traits_en) != len(se["traits"]) or traits_en.keys() != traits_zh.keys():
        raise ValueError("Duplicate/mismatched localized traits")
    official = {}
    for kind, prefix in manifest["official_prefixes"].items():
        official[kind] = {
            locale: scoped(data[f"ddragon-{kind}-{locale}.json"], prefix) for locale in ["en_US", "zh_CN"]
        }
        if kind == "trait":
            official[kind] = {
                locale: {key: rows[key] for key in manifest["required_trait_ids"]}
                for locale, rows in official[kind].items()
            }
        if official[kind]["en_US"].keys() != official[kind]["zh_CN"].keys():
            raise ValueError("Official locale IDs differ")
    if official["champion"]["en_US"].keys() != set(manifest["required_champion_ids"]):
        raise ValueError("Missing/extra required champions for selected set")
    build = data["content-metadata.json"]["version"]
    if build != manifest["build_version"]:
        raise ValueError("Mixed build metadata")
    for kind in official:
        for locale in ["en_US", "zh_CN"]:
            if data[f"ddragon-{kind}-{locale}.json"]["version"] != manifest["resource_patch"]:
                raise ValueError("Mixed official resource patch")
    base = dict(
        game="TFT",
        patch=manifest["patch"],
        set=str(manifest["set_number"]),
        mode="standard",
        source=manifest["source"],
        imported_at=manifest["imported_at"],
        verification_status="verified",
    )

    def entity(cid, kind):
        a, b = official[kind]["en_US"][cid], official[kind]["zh_CN"][cid]
        full = a["image"]["full"]
        if "/" in full or "\\" in full or not full.endswith(".png") or b["image"]["full"] != full:
            raise ValueError("Invalid official icon reference")
        return dict(
            **base,
            id=cid,
            en_US=a["name"],
            zh_CN=b["name"],
            icon_path=f"https://ddragon.leagueoflegends.com/cdn/{manifest['resource_patch']}/img/tft-{kind}/{quote(full)}",
            verification_evidence=[
                e["url"] for e in manifest["snapshots"] if e["filename"].startswith(f"ddragon-{kind}")
            ],
        )

    if traits_en.keys() != official["trait"]["en_US"].keys():
        raise ValueError("Official/CD trait membership differs")
    traits = []
    for tid, t in traits_en.items():
        row = entity(tid, "trait")
        if row["en_US"] != t["name"] or row["zh_CN"] != traits_zh[tid]["name"]:
            raise ValueError("Trait translation disagreement")
        counts = [effect["minUnits"] for effect in t["effects"]]
        if counts != [effect["minUnits"] for effect in traits_zh[tid]["effects"]]:
            raise ValueError("Threshold locales disagree")
        unsupported = manifest["unsupported_traits"].get(tid)
        if not unsupported and (any(not isinstance(v, int) or v <= 0 for v in counts) or counts != sorted(set(counts))):
            raise ValueError(f"Invalid trait thresholds: {tid}")
        row.update(
            description=t["desc"],
            supported=not bool(unsupported),
            special_conditions=unsupported,
            thresholds=[] if unsupported else [dict(count=n, utility=i + 1) for i, n in enumerate(counts)],
        )
        if unsupported:
            row["verification_status"] = "unsupported"
        traits.append(row)
    names = [{t["name"]: t["apiName"] for t in s["traits"]} for s in [se, sz]]
    if any(len(mapping) != len(s["traits"]) for mapping, s in zip(names, [se, sz])):
        raise ValueError("Ambiguous localized trait names")
    champions = []
    cd_units = [{c["apiName"]: c for c in s["champions"]} for s in [se, sz]]
    if any(len(mapping) != len(s["champions"]) for mapping, s in zip(cd_units, [se, sz])):
        raise ValueError("Duplicate source champion IDs")
    for cid in manifest["required_champion_ids"]:
        if any(cid not in units for units in cd_units):
            raise ValueError(f"Missing required champion: {cid}")
        c, z = cd_units[0][cid], cd_units[1][cid]
        row = entity(cid, "champion")
        native = [names[i][name] for i, unit in enumerate([c, z]) for name in unit["traits"]]
        a, b = native[: len(c["traits"])], native[len(c["traits"]) :]
        if a != b or not a or not 1 <= c["cost"] <= 5 or c["cost"] != z["cost"]:
            raise ValueError("Invalid native traits/cost/locale membership")
        if c["cost"] != official["champion"]["en_US"][cid]["tier"]:
            raise ValueError("Official/CD champion cost disagrees")
        row.update(cost=c["cost"], traits=a, description=c["ability"]["desc"])
        if "DA_18_Rival" in a or cid == "DA_Lux18_Base":
            row.update(
                available=False,
                unlock_condition="未支持宿敌进化或未选择化身阵营",
                verification_status="partially_verified",
            )
        if "DA_18_LuxUniqueTrait" in a:
            row["exclusive_group"] = "DA_18_Lux"
            row["trait_weights"] = {tid: 2 for tid in a if tid != "DA_18_LuxUniqueTrait"}
        if cid == "DA_18_ElderDragon":
            row.update(board_slots=2, trait_weights={"DA_Riftbeast18": 2})
        champions.append(row)
    item_by_id = {i["apiName"]: i for i in en["items"]}
    if len(item_by_id) != len(en["items"]):
        raise ValueError("Duplicate source item IDs")
    membership = set(se["items"])
    emblems = []
    for eid, association in manifest["emblem_associations"].items():
        if eid not in membership or eid not in item_by_id or eid not in official["item"]["en_US"]:
            raise ValueError("Emblem outside selected set")
        tid = association["trait_id"]
        row = entity(eid, "item")
        # Explicit reviewed IDs + BOTH official translations, not a substring ID guess.
        if tid not in traits_en or row["en_US"] != traits_en[tid]["name"] + " Emblem":
            raise ValueError("Invalid reviewed emblem association")
        if row["zh_CN"] != association["zh_CN"]:
            raise ValueError("Emblem translation changed since review")
        native_associations = item_by_id[eid]["associatedTraits"]
        if native_associations and native_associations != [tid]:
            raise ValueError("Reviewed/source emblem association disagrees")
        row.update(
            trait_id=tid,
            available=association["enabled"],
            verification_evidence=row["verification_evidence"] + association["evidence"],
        )
        if not association["enabled"]:
            row["verification_status"] = "unverified"
        emblems.append(row)
    official_emblems = {eid for eid, v in official["item"]["en_US"].items() if v["name"].endswith(" Emblem")}
    if official_emblems != set(manifest["emblem_associations"]):
        raise ValueError("Missing/extra emblem review entries")
    readiness = dict(
        source_kind="riot_and_communitydragon",
        set_name=manifest["set_name"],
        resource_patch=manifest["resource_patch"],
        build_version=build,
        last_verified_at=manifest["reviewed_at"],
        live_as_of=manifest["live_as_of"],
        optimization_enabled=True,
        scope=manifest["scope"],
        completeness=sum(c["available"] if "available" in c else True for c in champions) / len(champions),
        required_champion_ids=manifest["required_champion_ids"],
        snapshots=manifest["snapshots"],
        rule_checks=manifest["rule_checks"],
        unsupported_mechanics=manifest["unsupported_mechanics"],
        excluded_entities=[
            dict(id=c["apiName"], reason="非所选标准模式商店棋子")
            for c in se["champions"]
            if c["apiName"] not in manifest["required_champion_ids"]
        ],
    )
    raw = dict(
        **base,
        id=manifest["ruleset_id"],
        zh_CN=manifest["set_name_zh"] + " · 已验证计数范围",
        en_US=manifest["set_name"],
        allow_duplicate_emblems=True,
        allow_unused_emblems=True,
        max_same_emblem_per_holder=1,
        champions=champions,
        traits=traits,
        emblems=emblems,
        license_status="Riot copyrighted static assets; CommunityDragon public extraction; no third-party statistics",
        data_readiness=readiness,
        trait_count_limits={"DA_Riftbeast18": 9},
        incompatible_trait_pairs=[["DA_18_Lunar", "DA_18_Solar"]],
    )
    raw["verification_status"] = "partially_verified"
    report = validate_catalog(raw)
    if not report["valid"]:
        raise ValueError(report["issues"])
    return Ruleset.model_validate(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = import_snapshot(args.manifest)
    Path(args.output).write_text(result.model_dump_json(indent=2))
    print(json.dumps(validate_catalog(result.model_dump()), ensure_ascii=False, indent=2))
