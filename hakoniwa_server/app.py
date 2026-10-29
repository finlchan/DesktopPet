"""FastAPI app for 箱庭島 — NAS LAN v1 (auth stub: optional API key)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from hakoniwa.model import IslandState

from .store import IslandStore

DEFAULT_PORT = 8787


def _data_dir() -> Path:
    return Path(os.environ.get("HAKONIWA_DATA_DIR") or "/data")


def _api_key() -> Optional[str]:
    key = (os.environ.get("HAKONIWA_API_KEY") or "").strip()
    return key or None


store = IslandStore(_data_dir())
app = FastAPI(
    title="箱庭島",
    description=(
        "NAS-ready island server (v1): home island + multi-island tourism. "
        "Custom auth later."
    ),
    version="0.2.0",
)


class CellAction(BaseModel):
    i: int = Field(..., ge=0, description="row")
    j: int = Field(..., ge=0, description="col")


class PlaceBody(CellAction):
    kind: str = Field(
        ...,
        description=(
            "farm | factory | quarry | defense | missile_base | "
            "harbor | shipyard | breakwater | monument"
        ),
    )


class ExportBody(BaseModel):
    lots: int = Field(1, ge=1, description="food export batches (100 t each)")


class ActionResult(BaseModel):
    ok: bool
    error: Optional[str] = None
    notes: Optional[List[str]] = None
    island: Dict[str, Any]


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """LAN default: no key. If HAKONIWA_API_KEY is set, require matching header."""
    expected = _api_key()
    if expected is None:
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "service": "hakoniwa-island",
        "version": "0.2.0",
        "auth": "api_key" if _api_key() else "none",
        "islands": len(store.list_islands()),
    }


@app.get("/api/v1/island", dependencies=[Depends(require_api_key)])
def get_island() -> Dict[str, Any]:
    return store.snapshot()


@app.put("/api/v1/island", dependencies=[Depends(require_api_key)])
def put_island(body: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be island JSON object")
    state = IslandState.from_dict(body)
    return store.replace(state)


@app.post("/api/v1/island/reset", dependencies=[Depends(require_api_key)])
def reset_island() -> Dict[str, Any]:
    return store.reset()


@app.post("/api/v1/island/place", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def place_building(body: PlaceBody) -> ActionResult:
    msg, island = store.place(body.i, body.j, body.kind)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/remove", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def remove_building(body: CellAction) -> ActionResult:
    msg, island = store.remove(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/landfill", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def landfill(body: CellAction) -> ActionResult:
    msg, island = store.landfill(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/level", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def level(body: CellAction) -> ActionResult:
    msg, island = store.level(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/raise", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def raise_mountain(body: CellAction) -> ActionResult:
    msg, island = store.raise_mountain(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/excavate", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def excavate(body: CellAction) -> ActionResult:
    msg, island = store.excavate(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/afforest", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def afforest(body: CellAction) -> ActionResult:
    msg, island = store.afforest(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/harvest", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def harvest(body: CellAction) -> ActionResult:
    msg, island = store.harvest(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/missile", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def fire_missile(body: CellAction) -> ActionResult:
    msg, island = store.missile(body.i, body.j)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/wait", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def wait_monster() -> ActionResult:
    msg, island = store.wait_monster()
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/export", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def export_food(body: ExportBody) -> ActionResult:
    msg, island = store.export_food(body.lots)
    if msg != "ok":
        return ActionResult(ok=False, error=msg, island=island)
    return ActionResult(ok=True, island=island)


@app.post("/api/v1/island/turn", response_model=ActionResult, dependencies=[Depends(require_api_key)])
def advance_turn() -> ActionResult:
    notes, island = store.next_turn()
    return ActionResult(ok=True, notes=notes, island=island)


class CommentBody(BaseModel):
    name: str = Field(..., min_length=1, description="visitor display name")
    text: str = Field(..., min_length=1, description="guestbook message")


class CommentsResult(BaseModel):
    ok: bool
    error: Optional[str] = None
    comments: List[Dict[str, Any]]


@app.get("/api/v1/island/comments", dependencies=[Depends(require_api_key)])
def get_comments() -> Dict[str, Any]:
    return {"comments": store.list_comments()}


@app.post(
    "/api/v1/island/comments",
    response_model=CommentsResult,
    dependencies=[Depends(require_api_key)],
)
def post_comment(body: CommentBody) -> CommentsResult:
    msg, comments = store.add_comment(body.name, body.text)
    if msg != "ok":
        return CommentsResult(ok=False, error=msg, comments=comments)
    return CommentsResult(ok=True, comments=comments)


# --- Multi-island tourism (觀光) --------------------------------------------


@app.get("/api/v1/islands", dependencies=[Depends(require_api_key)])
def list_islands() -> Dict[str, Any]:
    """Catalog of browseable islands (home + seeded demos)."""
    return {"islands": store.list_islands()}


@app.get("/api/v1/islands/{island_id}", dependencies=[Depends(require_api_key)])
def get_island_by_id(island_id: str) -> Dict[str, Any]:
    data = store.get_island(island_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Island not found: {island_id}")
    return data


@app.get(
    "/api/v1/islands/{island_id}/comments",
    dependencies=[Depends(require_api_key)],
)
def get_island_comments(island_id: str) -> Dict[str, Any]:
    comments = store.list_island_comments(island_id)
    if comments is None:
        raise HTTPException(status_code=404, detail=f"Island not found: {island_id}")
    return {"comments": comments}


@app.post(
    "/api/v1/islands/{island_id}/comments",
    response_model=CommentsResult,
    dependencies=[Depends(require_api_key)],
)
def post_island_comment(island_id: str, body: CommentBody) -> CommentsResult:
    msg, comments = store.add_island_comment(island_id, body.name, body.text)
    if msg is None:
        raise HTTPException(status_code=404, detail=f"Island not found: {island_id}")
    if msg != "ok":
        return CommentsResult(ok=False, error=msg, comments=comments)
    return CommentsResult(ok=True, comments=comments)
