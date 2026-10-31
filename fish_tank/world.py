"""Local free-swim simulation: motion, food, leave-view (away stub)."""

from __future__ import annotations

import math
import random
import time
import uuid
from typing import List

from .facing import facing_from_velocity
from .model import WORLD_H, WORLD_W, FishEntity, TankState
from .species import FISH_KEYS


# Chance per second that an unowned fish near the rim decides to leave.
LEAVE_CHANCE_PER_SEC = 0.015
# How long an "away" fish stays out before optionally returning (local stub).
AWAY_MIN_SEC = 45.0
AWAY_MAX_SEC = 180.0
# Chance per second an away fish returns into the local view (Phase 1 stub;
# Phase 2 would come from public-sea assignment).
RETURN_CHANCE_PER_SEC = 0.02


def _clamp_world(f: FishEntity) -> None:
    margin = 20.0
    if f.x < margin:
        f.x = margin
        f.vx = abs(f.vx)
    elif f.x > WORLD_W - margin:
        f.x = WORLD_W - margin
        f.vx = -abs(f.vx)
    if f.y < margin:
        f.y = margin
        f.vy = abs(f.vy)
    elif f.y > WORLD_H - margin:
        f.y = WORLD_H - margin
        f.vy = -abs(f.vy)


def _near_rim(f: FishEntity, rim: float = 80.0) -> bool:
    return (
        f.x < rim
        or f.x > WORLD_W - rim
        or f.y < rim
        or f.y > WORLD_H - rim
    )


def _wander(f: FishEntity, dt: float) -> None:
    # Soft steering noise.
    f.vx += random.uniform(-25, 25) * dt
    f.vy += random.uniform(-15, 15) * dt
    speed = math.hypot(f.vx, f.vy)
    max_speed = 55.0 if not f.owned else 40.0
    if speed > max_speed:
        f.vx *= max_speed / speed
        f.vy *= max_speed / speed
    f.x += f.vx * dt
    f.y += f.vy * dt
    prev = getattr(f, "facing", 2)
    f.facing = facing_from_velocity(f.vx, f.vy, prev=prev)
    f.facing_right = f.facing in (1, 2, 3)  # NE/E/SE legacy
    _clamp_world(f)


def _seek_food(f: FishEntity, state: TankState, dt: float) -> None:
    if not state.food_pellets or f.fullness >= 0.95:
        return
    # Nearest pellet.
    best = min(
        state.food_pellets,
        key=lambda p: (p["x"] - f.x) ** 2 + (p["y"] - f.y) ** 2,
    )
    dx, dy = best["x"] - f.x, best["y"] - f.y
    dist = math.hypot(dx, dy) or 1.0
    f.vx += (dx / dist) * 40 * dt
    f.vy += (dy / dist) * 40 * dt
    if dist < 18:
        f.fullness = min(1.0, f.fullness + 0.12)
        best["life"] = 0


def tick(state: TankState, dt: float) -> List[str]:
    """Advance local simulation by ``dt`` seconds. Returns log lines."""
    logs: List[str] = []
    now = time.monotonic()

    # Food pellets drift down.
    alive = []
    for p in state.food_pellets:
        p["y"] += p.get("vy", 20) * dt
        p["life"] = p.get("life", 1) - dt
        if p["life"] > 0 and p["y"] < WORLD_H - 10:
            alive.append(p)
    state.food_pellets = alive

    # Active fish.
    for f in list(state.fish):
        if f.away:
            if now >= f.away_until and random.random() < RETURN_CHANCE_PER_SEC * dt:
                f.away = False
                f.away_until = 0.0
                # Re-enter near a rim.
                side = random.choice(("l", "r", "t", "b"))
                if side == "l":
                    f.x, f.y = 30, random.uniform(100, WORLD_H - 100)
                    f.vx = abs(f.vx) + 20
                elif side == "r":
                    f.x, f.y = WORLD_W - 30, random.uniform(100, WORLD_H - 100)
                    f.vx = -abs(f.vx) - 20
                elif side == "t":
                    f.x, f.y = random.uniform(100, WORLD_W - 100), 30
                    f.vy = abs(f.vy) + 15
                else:
                    f.x, f.y = random.uniform(100, WORLD_W - 100), WORLD_H - 30
                    f.vy = -abs(f.vy) - 15
                sp = f.market_label()
                logs.append(f"訪客回來／Visitor returned: {sp}")
            continue

        _seek_food(f, state, dt)
        _wander(f, dt)
        # Age / hunger slowly.
        f.age_days += dt / 86400.0 * 12.0  # accelerated local day
        f.fullness = max(0.0, f.fullness - 0.01 * dt)
        if f.fullness < 0.15:
            f.health = max(0.0, f.health - 0.02 * dt)
        elif f.fullness > 0.5:
            f.health = min(1.0, f.health + 0.005 * dt)

        # Leave local view (unowned free swimmers) — away stub, no public server.
        if (
            not f.owned
            and _near_rim(f)
            and random.random() < LEAVE_CHANCE_PER_SEC * dt
        ):
            f.away = True
            f.away_until = now + random.uniform(AWAY_MIN_SEC, AWAY_MAX_SEC)
            logs.append(
                f"游出視野／Left view (away stub): {f.market_label()}"
            )

    # Occasional wild spawn into view (local stub for public-sea visitor).
    if (
        len(state.active_fish()) < 8
        and random.random() < 0.008 * dt
    ):
        key = random.choice(FISH_KEYS)
        rare = random.random() < 0.1
        nf = FishEntity(
            id=str(uuid.uuid4())[:8],
            species_key=key,
            x=random.choice([40, WORLD_W - 40]),
            y=random.uniform(80, WORLD_H - 80),
            vx=random.uniform(-30, 30),
            vy=random.uniform(-12, 12),
            rare=rare,
            health=random.uniform(0.6, 1.0),
            fullness=random.uniform(0.3, 0.7),
            age_days=random.uniform(0.5, 20),
        )
        state.fish.append(nf)
        logs.append(f"野生游入／Wild visit (local stub): {nf.market_label()}")

    return logs
