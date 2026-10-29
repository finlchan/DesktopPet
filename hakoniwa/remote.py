"""Optional HTTP client for 箱庭島 NAS server (stdlib urllib — no extra deps)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from .model import GuestbookEntry, IslandState


class HakoniwaRemoteError(Exception):
    """Network / HTTP / payload failure talking to the island server."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass
class ActionOutcome:
    ok: bool
    error: Optional[str]
    notes: Optional[List[str]]
    island: IslandState


def normalize_base_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    if any(ch.isspace() for ch in raw):
        raise HakoniwaRemoteError(f"無效伺服器網址：{url}")
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HakoniwaRemoteError(f"無效伺服器網址：{url}")
    if any(ch.isspace() for ch in parsed.netloc):
        raise HakoniwaRemoteError(f"無效伺服器網址：{url}")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


class HakoniwaRemote:
    """Thin JSON client for hakoniwa_server FastAPI."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 8.0,
    ):
        self.base_url = normalize_base_url(base_url)
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    def _headers(self, has_body: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if has_body:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        *,
        auth: bool = True,
    ) -> Any:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        data = None
        headers = self._headers(has_body=body is not None)
        if not auth:
            headers.pop("X-API-Key", None)
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")
                parsed = json.loads(detail)
                if isinstance(parsed, dict) and parsed.get("detail"):
                    detail = str(parsed["detail"])
            except Exception:
                pass
            raise HakoniwaRemoteError(
                f"伺服器錯誤 HTTP {e.code}" + (f"：{detail}" if detail else ""),
                status=e.code,
            ) from e
        except urllib.error.URLError as e:
            raise HakoniwaRemoteError(f"無法連線伺服器：{e.reason}") from e
        except TimeoutError as e:
            raise HakoniwaRemoteError("連線逾時") from e
        except json.JSONDecodeError as e:
            raise HakoniwaRemoteError("伺服器回傳非 JSON") from e

    def health(self) -> Dict[str, Any]:
        data = self._request("GET", "/health", auth=False)
        if not isinstance(data, dict) or not data.get("ok"):
            raise HakoniwaRemoteError("健康檢查失敗")
        return data

    def get_island(self) -> IslandState:
        data = self._request("GET", "/api/v1/island")
        if not isinstance(data, dict):
            raise HakoniwaRemoteError("島資料格式錯誤")
        return IslandState.from_dict(data)

    def put_island(self, state: IslandState) -> IslandState:
        data = self._request("PUT", "/api/v1/island", state.to_dict())
        if not isinstance(data, dict):
            raise HakoniwaRemoteError("島資料格式錯誤")
        return IslandState.from_dict(data)

    def reset(self) -> IslandState:
        data = self._request("POST", "/api/v1/island/reset")
        if not isinstance(data, dict):
            raise HakoniwaRemoteError("島資料格式錯誤")
        return IslandState.from_dict(data)

    def _action(self, path: str, body: Optional[Dict[str, Any]] = None) -> ActionOutcome:
        data = self._request("POST", path, body if body is not None else {})
        if not isinstance(data, dict) or "island" not in data:
            raise HakoniwaRemoteError("動作回傳格式錯誤")
        island = IslandState.from_dict(data["island"])
        notes = data.get("notes")
        if notes is not None and not isinstance(notes, list):
            notes = [str(notes)]
        return ActionOutcome(
            ok=bool(data.get("ok")),
            error=(str(data["error"]) if data.get("error") else None),
            notes=[str(n) for n in notes] if notes else None,
            island=island,
        )

    def place(self, i: int, j: int, kind: str) -> ActionOutcome:
        return self._action("/api/v1/island/place", {"i": i, "j": j, "kind": kind})

    def remove(self, i: int, j: int) -> ActionOutcome:
        return self._action("/api/v1/island/remove", {"i": i, "j": j})

    def landfill(self, i: int, j: int) -> ActionOutcome:
        return self._action("/api/v1/island/landfill", {"i": i, "j": j})

    def level(self, i: int, j: int) -> ActionOutcome:
        return self._action("/api/v1/island/level", {"i": i, "j": j})

    def raise_mountain(self, i: int, j: int) -> ActionOutcome:
        return self._action("/api/v1/island/raise", {"i": i, "j": j})

    def afforest(self, i: int, j: int) -> ActionOutcome:
        return self._action("/api/v1/island/afforest", {"i": i, "j": j})

    def harvest(self, i: int, j: int) -> ActionOutcome:
        return self._action("/api/v1/island/harvest", {"i": i, "j": j})

    def missile(self, i: int, j: int) -> ActionOutcome:
        return self._action("/api/v1/island/missile", {"i": i, "j": j})

    def wait_monster(self) -> ActionOutcome:
        return self._action("/api/v1/island/wait", {})

    def export_food(self, lots: int = 1) -> ActionOutcome:
        return self._action("/api/v1/island/export", {"lots": int(lots)})

    def next_turn(self) -> ActionOutcome:
        return self._action("/api/v1/island/turn", {})

    def list_comments(self) -> List[GuestbookEntry]:
        data = self._request("GET", "/api/v1/island/comments")
        if not isinstance(data, dict) or not isinstance(data.get("comments"), list):
            raise HakoniwaRemoteError("留言板格式錯誤")
        out: List[GuestbookEntry] = []
        for item in data["comments"]:
            if not isinstance(item, dict):
                continue
            entry = GuestbookEntry.from_dict(item)
            if entry is not None:
                out.append(entry)
        return out

    def post_comment(self, name: str, text: str) -> Tuple[bool, Optional[str], List[GuestbookEntry]]:
        data = self._request(
            "POST", "/api/v1/island/comments", {"name": name, "text": text}
        )
        if not isinstance(data, dict) or not isinstance(data.get("comments"), list):
            raise HakoniwaRemoteError("留言板回傳格式錯誤")
        comments: List[GuestbookEntry] = []
        for item in data["comments"]:
            if not isinstance(item, dict):
                continue
            entry = GuestbookEntry.from_dict(item)
            if entry is not None:
                comments.append(entry)
        ok = bool(data.get("ok"))
        err = str(data["error"]) if data.get("error") else None
        return ok, err, comments

    def _parse_comments_payload(self, data: Any) -> List[GuestbookEntry]:
        if not isinstance(data, dict) or not isinstance(data.get("comments"), list):
            raise HakoniwaRemoteError("留言板格式錯誤")
        out: List[GuestbookEntry] = []
        for item in data["comments"]:
            if not isinstance(item, dict):
                continue
            entry = GuestbookEntry.from_dict(item)
            if entry is not None:
                out.append(entry)
        return out

    def list_islands(self) -> List[Dict[str, Any]]:
        data = self._request("GET", "/api/v1/islands")
        if not isinstance(data, dict) or not isinstance(data.get("islands"), list):
            raise HakoniwaRemoteError("諸島列表格式錯誤")
        out: List[Dict[str, Any]] = []
        for item in data["islands"]:
            if isinstance(item, dict) and item.get("id"):
                out.append(item)
        return out

    def get_island_by_id(self, island_id: str) -> IslandState:
        data = self._request("GET", f"/api/v1/islands/{island_id}")
        if not isinstance(data, dict):
            raise HakoniwaRemoteError("島資料格式錯誤")
        return IslandState.from_dict(data)

    def list_island_comments(self, island_id: str) -> List[GuestbookEntry]:
        data = self._request("GET", f"/api/v1/islands/{island_id}/comments")
        return self._parse_comments_payload(data)

    def post_island_comment(
        self, island_id: str, name: str, text: str
    ) -> Tuple[bool, Optional[str], List[GuestbookEntry]]:
        data = self._request(
            "POST",
            f"/api/v1/islands/{island_id}/comments",
            {"name": name, "text": text},
        )
        comments = self._parse_comments_payload(data)
        ok = bool(data.get("ok"))
        err = str(data["error"]) if data.get("error") else None
        return ok, err, comments


def try_connect(
    url: str, api_key: str = "", timeout: float = 8.0
) -> Tuple[Optional[HakoniwaRemote], Optional[IslandState], Optional[str]]:
    """Return (client, island, error). On failure client/island are None."""
    try:
        client = HakoniwaRemote(url, api_key=api_key, timeout=timeout)
        client.health()
        island = client.get_island()
        return client, island, None
    except HakoniwaRemoteError as e:
        return None, None, str(e)
    except Exception as e:  # noqa: BLE001 — surface unexpected connect errors
        return None, None, f"連線失敗：{e}"
