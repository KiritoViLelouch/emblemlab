from fastapi import APIRouter, HTTPException
from app.repositories.catalog import catalogs, get_catalog
from app.schemas.domain import ReforgeRequest, SolveRequest
from app.optimizer.solver import RULES, solve
from app.reforge.service import simulate
from app.reforge.schemas import AnalysisRequest
from app.reforge.rules import get_rule, rules_for
from app.reforge.analyzer import analyze
from app.repositories.catalog import catalog_issues

router = APIRouter()


def catalog_for(request):
    dataset = get_catalog(request.game_id, request.ruleset_id)
    RULES.validate(dataset, request)
    return dataset


def guarded(fn):
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health")
def health():
    return {"status": "ok", "solver": "OR-Tools CP-SAT"}


@router.get("/api/v1/games")
def games(include_synthetic: bool = True):
    return [
        {
            "id": g,
            "name": name,
            "versions": [
                {
                    "patch": d.patch,
                    "ruleset_id": d.id,
                    "name": d.zh_CN,
                    "set": d.set,
                    "mode": d.mode,
                    "verification_state": d.verification_status.upper(),
                    "optimization_enabled": not d.data_readiness or d.data_readiness.optimization_enabled,
                }
                for d in catalogs()
                if d.game == g and (include_synthetic or d.verification_status != "synthetic")
            ],
        }
        for g, name in [("TFT", "TFT 国际服"), ("JCC", "金铲铲之战")]
    ]


@router.get("/api/v1/catalog")
def catalog(game_id: str = "TFT", ruleset_id: str = "fixture_tft_v1"):
    return guarded(lambda: get_catalog(game_id, ruleset_id).model_dump())


@router.post("/api/v1/solve")
def solve_route(request: SolveRequest):
    return guarded(lambda: solve(catalog_for(request), request))


@router.post("/api/v1/holders/rank")
def holders(request: SolveRequest):
    def run():
        dataset = catalog_for(request)
        result = solve(dataset, request.model_copy(update={"top_k": 1}))
        candidate = result["candidates"][0] if result["candidates"] else None
        rankings = []
        if candidate:
            selected = {c["id"] for c in candidate["champions"]}
            for index, eid in enumerate(request.emblem_ids):
                emblem = next(e for e in dataset.emblems if e.id == eid)
                # Evaluate a proposed holder while keeping other emblem assignments fixed.
                options = []
                for c in dataset.champions:
                    if c.id not in selected or not RULES.legal(c, emblem):
                        continue
                    assignments = [a for a in candidate["assignments"] if a["instance_index"] != index]
                    assignments.append(dict(instance_index=index, emblem_id=eid, champion_id=c.id))
                    try:
                        RULES.validate_solution(dataset, request, list(selected), assignments)
                    except ValueError:
                        continue
                    before = RULES.evaluate(
                        dataset, list(selected), [a for a in assignments if a["instance_index"] != index]
                    )
                    after = RULES.evaluate(dataset, list(selected), assignments)
                    gain = sum(t["active"] for t in after) - sum(t["active"] for t in before)
                    utility = sum(t["utility"] for t in after) - sum(t["utility"] for t in before)
                    options.append(
                        dict(
                            champion_id=c.id,
                            name=c.zh_CN,
                            active_trait_gain=gain,
                            breakpoint_utility_gain=utility,
                            ability_compatibility=None,
                            statistics=None,
                            explanation=f"合法；独立羁绊计数 +{sum(t['count'] for t in after) - sum(t['count'] for t in before)}；技能适配未知",
                        )
                    )
                options.sort(key=lambda o: (o["active_trait_gain"], o["breakpoint_utility_gain"]), reverse=True)
                rankings.append(dict(instance_index=index, emblem_id=eid, holders=options))
        return dict(
            candidate=candidate,
            rankings=rankings,
            context="Other emblem assignments fixed to candidate; illegal combinations omitted",
            statistics=None,
        )

    return guarded(run)


@router.post("/api/v1/reforge/simulate")
def reforge(request: ReforgeRequest):
    return guarded(lambda: simulate(catalog_for(request), request))


@router.get("/api/v1/data-health")
def data_health():
    return dict(
        catalog_activation_issues=catalog_issues(),
        current_patch_verified=False,
        statistics_available=False,
        assets_included=False,
        datasets=[
            dict(
                game=d.game,
                id=d.id,
                patch=d.patch,
                set=d.set,
                mode=d.mode,
                source=d.source,
                imported_at=d.imported_at,
                verification_status=d.verification_status,
                license_status=d.license_status,
                champions=len(d.champions),
                traits=len(d.traits),
                emblems=len(d.emblems),
                verification_state=d.verification_status.upper(),
                data_readiness=d.data_readiness.model_dump() if d.data_readiness else None,
            )
            for d in catalogs()
        ],
    )


@router.get("/api/v1/reforge/rules")
def reforge_rules(game_id: str, ruleset_id: str):
    return guarded(lambda: [r.model_dump() for r in rules_for(get_catalog(game_id, ruleset_id))])


@router.post("/api/v1/reforge/analyze")
def reforge_analyze(request: AnalysisRequest):
    def run():
        dataset = catalog_for(request)
        return analyze(dataset, request, get_rule(dataset, request.reforge_rule_id))

    return guarded(run)
