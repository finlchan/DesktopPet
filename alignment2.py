"""Alignment(2) — OSCH design alignment (Hv / Va / crossfall) math.

Ported from Calulation_Macro_FAI.xlsm sheets OSCH2_AIn / OSCH2_VIn /
OSCH3_LRHS / OSCH_SUR. Densifies horizontal geometry (STRAIGHT / R / SC /
CC / TS / CS), evaluates vertical LIN/PAR levels, and compares survey
points to the design centreline.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

AlignPoint = Tuple[float, float, float, float]  # chainage, E, N, level
HorizSeg = Dict[str, Any]
VertSeg = Dict[str, Any]
CrossSeg = Dict[str, Any]


def _atan2_excel(x: float, y: float) -> float:
    """Excel ATAN2(x, y) ≡ Python atan2(y, x). VBA passes (ΔN, ΔE)."""
    return math.atan2(y, x)


def _cell_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number != number:
            return None
        return number
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _norm_header(text: Any) -> str:
    return (
        str(text or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "")
    )


def _load_workbook_sheets(path: Path) -> Dict[str, List[List[Any]]]:
    """Return {sheet_name: rows} for .xlsx/.xlsm/.xls."""
    path = Path(path)
    suffix = path.suffix.lower()
    sheets: Dict[str, List[List[Any]]] = {}
    if suffix in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError as exc:
            raise ImportError(
                "openpyxl is required to read .xlsx/.xlsm (pip install openpyxl)"
            ) from exc
        wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
        try:
            for name in wb.sheetnames:
                ws = wb[name]
                rows = [list(r) for r in ws.iter_rows(values_only=True)]
                sheets[name] = rows
        finally:
            wb.close()
        return sheets
    if suffix == ".xls":
        try:
            import xlrd
        except ImportError as exc:
            raise ImportError(
                "xlrd is required to read .xls (pip install xlrd)"
            ) from exc
        wb = xlrd.open_workbook(str(path))
        for name in wb.sheet_names():
            sh = wb.sheet_by_name(name)
            rows = [
                [sh.cell_value(r, c) for c in range(sh.ncols)]
                for r in range(sh.nrows)
            ]
            sheets[name] = rows
        return sheets
    raise ValueError(
        f"Unsupported file type '{suffix or path.name}'. Use .xlsm, .xlsx, or .xls"
    )


def _find_sheet(sheets: Dict[str, List[List[Any]]], *candidates: str) -> List[List[Any]]:
    lower = {k.lower(): k for k in sheets}
    for cand in candidates:
        key = lower.get(cand.lower())
        if key is not None:
            return sheets[key]
    # Fuzzy: ignore I/l confusion in Aln/AIn
    for want in candidates:
        want_n = _norm_header(want)
        for name, key in lower.items():
            if _norm_header(name) == want_n:
                return sheets[key]
            # OSCH2_AIn vs OSCH2_Aln
            if want_n.replace("aln", "ain") == _norm_header(name).replace("aln", "ain"):
                return sheets[key]
    raise ValueError(
        "Missing sheet "
        + " / ".join(candidates)
        + f" (found: {', '.join(sheets.keys()) or 'none'})"
    )


def parse_horizontal_rows(rows: Sequence[Sequence[Any]]) -> List[HorizSeg]:
    if not rows:
        raise ValueError("Horizontal sheet is empty")
    segs: List[HorizSeg] = []
    for row in rows[1:]:
        if not row or all(c is None or c == "" for c in row):
            continue
        ch = _cell_float(row[0] if len(row) > 0 else None)
        east = _cell_float(row[1] if len(row) > 1 else None)
        north = _cell_float(row[2] if len(row) > 2 else None)
        typ = str(row[3] if len(row) > 3 else "").strip().upper()
        if ch is None or east is None or north is None or not typ:
            continue
        segs.append(
            {
                "chainage": ch,
                "easting": east,
                "northing": north,
                "type": typ,
                "param": _cell_float(row[4] if len(row) > 4 else None),
                "arc_length": _cell_float(row[5] if len(row) > 5 else None),
                "pc_easting": _cell_float(row[6] if len(row) > 6 else None),
                "pc_northing": _cell_float(row[7] if len(row) > 7 else None),
                "lhs_os": _cell_float(row[8] if len(row) > 8 else None) or 0.0,
                "rhs_os": _cell_float(row[9] if len(row) > 9 else None) or 0.0,
            }
        )
    if len(segs) < 2:
        raise ValueError("Need ≥2 horizontal alignment rows")
    return segs


def parse_vertical_rows(rows: Sequence[Sequence[Any]]) -> List[VertSeg]:
    if not rows:
        raise ValueError("Vertical sheet is empty")
    segs: List[VertSeg] = []
    for row in rows[1:]:
        if not row or all(c is None or c == "" for c in row[:5]):
            continue
        typ = str(row[0] if len(row) > 0 else "").strip().upper()
        # Support TPYE typo header layouts: TYPE/CHAINAGE/LEVEL/GRADE%/VC
        # Also allow CHAINAGE first if TYPE missing.
        if typ in ("LIN", "PAR"):
            ch = _cell_float(row[1] if len(row) > 1 else None)
            level = _cell_float(row[2] if len(row) > 2 else None)
            grade = _cell_float(row[3] if len(row) > 3 else None)
            vc = _cell_float(row[4] if len(row) > 4 else None)
        else:
            # Fallback: CHAINAGE, LEVEL, GRADE, VC (no type → treat as LIN)
            ch = _cell_float(row[0] if len(row) > 0 else None)
            level = _cell_float(row[1] if len(row) > 1 else None)
            grade = _cell_float(row[2] if len(row) > 2 else None)
            vc = _cell_float(row[3] if len(row) > 3 else None)
            typ = "LIN"
        if ch is None or level is None:
            continue
        segs.append(
            {
                "type": typ if typ in ("LIN", "PAR") else "LIN",
                "chainage": ch,
                "level": level,
                "grade": grade if grade is not None else 0.0,
                "vc_length": vc,
            }
        )
    if len(segs) < 2:
        raise ValueError("Need ≥2 vertical alignment rows")
    return segs


def parse_crossfall_rows(rows: Sequence[Sequence[Any]]) -> List[CrossSeg]:
    segs: List[CrossSeg] = []
    if not rows:
        return segs
    for row in rows[1:]:
        if not row:
            continue
        ch = _cell_float(row[0] if len(row) > 0 else None)
        if ch is None:
            continue
        segs.append(
            {
                "chainage": ch,
                "left_fall": _cell_float(row[1] if len(row) > 1 else None) or 0.0,
                "right_fall": _cell_float(row[2] if len(row) > 2 else None) or 0.0,
                "left_len": _cell_float(row[3] if len(row) > 3 else None) or 0.0,
                "right_len": _cell_float(row[4] if len(row) > 4 else None) or 0.0,
            }
        )
    return segs


def vertical_level_at(verts: Sequence[VertSeg], chainage: float) -> Optional[float]:
    """Port of CalculateLevel — LIN / PAR vertical curves."""
    if len(verts) < 2:
        return None
    ch = float(chainage)
    for i in range(len(verts) - 1):
        a, b = verts[i], verts[i + 1]
        if ch < a["chainage"] or ch > b["chainage"]:
            continue
        start_ch = a["chainage"]
        start_lv = a["level"]
        start_g = a["grade"]
        end_g = b["grade"]
        if a["type"] == "LIN":
            return start_lv + (ch - start_ch) * start_g
        if a["type"] == "PAR":
            vc = a.get("vc_length")
            if vc is None or abs(vc) < 1e-12:
                return start_lv + (ch - start_ch) * start_g
            grade_change = end_g - start_g
            t = ch - start_ch
            return (
                start_lv
                + start_g * t
                + (vc / 2.0) * grade_change * (t / vc) ** 2
            )
    # Extrapolate with end grades.
    if ch < verts[0]["chainage"]:
        a = verts[0]
        return a["level"] + (ch - a["chainage"]) * a["grade"]
    b = verts[-1]
    return b["level"] + (ch - b["chainage"]) * b["grade"]


def crossfall_at(cross: Sequence[CrossSeg], chainage: float) -> Tuple[float, float, float, float]:
    """Linear interpolate L/R crossfall % and widths. Returns (lcf, rcf, llen, rlen)."""
    if not cross:
        return 0.0, 0.0, 0.0, 0.0
    ch = float(chainage)
    if ch <= cross[0]["chainage"]:
        c = cross[0]
        return c["left_fall"], c["right_fall"], c["left_len"], c["right_len"]
    if ch >= cross[-1]["chainage"]:
        c = cross[-1]
        return c["left_fall"], c["right_fall"], c["left_len"], c["right_len"]
    for i in range(len(cross) - 1):
        a, b = cross[i], cross[i + 1]
        if a["chainage"] <= ch <= b["chainage"]:
            span = b["chainage"] - a["chainage"]
            t = 0.0 if abs(span) < 1e-15 else (ch - a["chainage"]) / span
            return (
                a["left_fall"] + (b["left_fall"] - a["left_fall"]) * t,
                a["right_fall"] + (b["right_fall"] - a["right_fall"]) * t,
                a["left_len"] + (b["left_len"] - a["left_len"]) * t,
                a["right_len"] + (b["right_len"] - a["right_len"]) * t,
            )
    c = cross[-1]
    return c["left_fall"], c["right_fall"], c["left_len"], c["right_len"]


def _emit(
    out: List[Dict[str, float]],
    ch: float,
    east: float,
    north: float,
    lhs_e: float,
    lhs_n: float,
    rhs_e: float,
    rhs_n: float,
) -> None:
    out.append(
        {
            "chainage": ch,
            "easting": east,
            "northing": north,
            "lhs_easting": lhs_e,
            "lhs_northing": lhs_n,
            "rhs_easting": rhs_e,
            "rhs_northing": rhs_n,
        }
    )


def densify_horizontal(
    segs: Sequence[HorizSeg], *, step: float = 1.0
) -> List[Dict[str, float]]:
    """Port of GenerateAlignmentPointsFromStructuredData (1 m centreline)."""
    if step <= 0:
        raise ValueError("step must be > 0")
    out: List[Dict[str, float]] = []
    pi = math.pi

    for i, seg in enumerate(segs):
        typ = seg["type"]
        ch0 = float(seg["chainage"])
        start_e = float(seg["easting"])
        start_n = float(seg["northing"])
        l_os = float(seg["lhs_os"])
        r_os = float(seg["rhs_os"])

        if typ == "STRAIGHT":
            if i + 1 >= len(segs):
                continue
            length = float(seg["param"] or 0.0)
            ch1 = ch0 + length
            end_e = float(segs[i + 1]["easting"])
            end_n = float(segs[i + 1]["northing"])
            span = ch1 - ch0
            if abs(span) < 1e-12:
                continue
            dist = math.hypot(end_e - start_e, end_n - start_n)
            if dist < 1e-12:
                continue
            # Perpendicular offsets (VBA sign convention).
            off_re = r_os * (end_n - start_n) / dist
            off_rn = r_os * (start_e - end_e) / dist
            off_le = l_os * (end_n - start_n) / dist
            off_ln = l_os * (start_e - end_e) / dist
            ch = ch0
            while ch <= ch1 + 1e-9:
                t = (ch - ch0) / span
                cur_e = start_e + (end_e - start_e) * t
                cur_n = start_n + (end_n - start_n) * t
                _emit(
                    out,
                    ch,
                    cur_e,
                    cur_n,
                    cur_e - off_le,
                    cur_n - off_ln,
                    cur_e + off_re,
                    cur_n + off_rn,
                )
                ch += step

        elif typ in ("R", "SC", "CC"):
            radius = float(seg["param"] or 0.0)
            arc = float(seg["arc_length"] or 0.0)
            if abs(radius) < 1e-12 or abs(arc) < 1e-12:
                continue
            ch1 = ch0 + arc
            center_e = float(seg["pc_easting"] or 0.0)
            center_n = float(seg["pc_northing"] or 0.0)
            angle_start = _atan2_excel(start_n - center_n, start_e - center_e)
            total_angle = arc / radius  # signed via radius sign
            span = ch1 - ch0
            ch = ch0
            while ch <= ch1 + 1e-9:
                frac = (ch - ch0) / span
                ang = angle_start + total_angle * frac
                cur_e = center_e + abs(radius) * math.sin(ang)
                cur_n = center_n + abs(radius) * math.cos(ang)
                if radius > 0:
                    l_e = center_e + (abs(radius) + l_os) * math.sin(ang)
                    l_n = center_n + (abs(radius) + l_os) * math.cos(ang)
                    r_e = center_e + (abs(radius) - r_os) * math.sin(ang)
                    r_n = center_n + (abs(radius) - r_os) * math.cos(ang)
                else:
                    l_e = center_e + (abs(radius) - l_os) * math.sin(ang)
                    l_n = center_n + (abs(radius) - l_os) * math.cos(ang)
                    r_e = center_e + (abs(radius) + r_os) * math.sin(ang)
                    r_n = center_n + (abs(radius) + r_os) * math.cos(ang)
                _emit(out, ch, cur_e, cur_n, l_e, l_n, r_e, r_n)
                ch += step

        elif typ == "TS":
            if i + 1 >= len(segs):
                continue
            radius = float(segs[i + 1]["param"] or 0.0)
            length = float(seg["param"] or 0.0)
            if abs(length) < 1e-12 or abs(radius) < 1e-12:
                continue
            ch1 = ch0 + length
            e_pi = float(seg["pc_easting"] or 0.0)
            n_pi = float(seg["pc_northing"] or 0.0)
            theta_ts = _atan2_excel(n_pi - start_n, e_pi - start_e)
            up_e = 0.0
            up_n = 0.0
            first = True
            ch = ch0
            while ch <= ch1 + 1e-9:
                ds = ch - ch0
                # VBA: theta_New = theta_TS + (ds^2 * 5729.578) / (L * 200 * R)
                theta_new = theta_ts + (ds ** 2 * 5729.578) / (length * 200.0 * radius)
                a_ts = theta_new - theta_ts  # degrees
                ar = a_ts * pi / 180.0
                xe = (
                    1.0
                    - ((ar ** 2) / 10.0)
                    + ((ar ** 4) / 216.0)
                    - ((ar ** 6) / 9360.0)
                    + ((ar ** 8) / 685440.0)
                )
                ye = (
                    (ar / 3.0)
                    - ((ar ** 3) / 42.0)
                    + ((ar ** 5) / 1320.0)
                    - ((ar ** 7) / 75600.0)
                    + ((ar ** 9) / 6894720.0)
                )
                cur_e = (
                    start_e
                    + math.sin(theta_ts) * ds * xe
                    + math.sin(theta_ts + pi / 2) * ds * ye
                )
                cur_n = (
                    start_n
                    + math.cos(theta_ts) * ds * xe
                    + math.cos(theta_ts + pi / 2) * ds * ye
                )
                if first:
                    th = _atan2_excel(n_pi - cur_n, e_pi - cur_e)
                    th_l = th - pi / 2
                    os_ln = cur_n + l_os * math.cos(th_l)
                    os_le = cur_e + l_os * math.sin(th_l)
                    th_r = th + pi / 2
                    os_rn = cur_n + r_os * math.cos(th_r)
                    os_re = cur_e + r_os * math.sin(th_r)
                    first = False
                else:
                    th = _atan2_excel(up_n - cur_n, up_e - cur_e)
                    th_l = th + pi / 2
                    os_ln = cur_n + l_os * math.cos(th_l)
                    os_le = cur_e + l_os * math.sin(th_l)
                    th_r = th - pi / 2
                    os_rn = cur_n + r_os * math.cos(th_r)
                    os_re = cur_e + r_os * math.sin(th_r)
                up_e, up_n = cur_e, cur_n
                _emit(out, ch, cur_e, cur_n, os_le, os_ln, os_re, os_rn)
                ch += step

        elif typ == "CS":
            if i == 0:
                continue
            radius = float(segs[i - 1]["param"] or 0.0)
            length = float(seg["param"] or 0.0)
            if i + 1 >= len(segs) or abs(length) < 1e-12 or abs(radius) < 1e-12:
                continue
            ch1 = ch0 + length
            e_pi = float(seg["pc_easting"] or 0.0)
            n_pi = float(seg["pc_northing"] or 0.0)
            final_e = float(segs[i + 1]["easting"])
            final_n = float(segs[i + 1]["northing"])
            theta = _atan2_excel(n_pi - final_n, e_pi - final_e)
            a_cs = math.sqrt(length * abs(radius))
            up_e = 0.0
            up_n = 0.0
            first = True
            ch = ch0
            while ch <= ch1 + 1e-9:
                real_len = ch1 - ch
                xe = real_len - ((real_len ** 5) / (40.0 * (a_cs ** 4)))
                ye = (real_len ** 3) / (6.0 * (a_cs ** 2))
                cur_e = final_e + xe * math.sin(theta)
                cur_n = final_n + xe * math.cos(theta)
                if radius > 0:
                    cur_e += ye * math.sin(theta - pi / 2)
                    cur_n += ye * math.cos(theta - pi / 2)
                else:
                    cur_e += ye * math.sin(theta + pi / 2)
                    cur_n += ye * math.cos(theta + pi / 2)
                if first:
                    th = _atan2_excel(n_pi - cur_n, e_pi - cur_e)
                    th_l = th + pi / 2
                    os_ln = cur_n + l_os * math.cos(th_l)
                    os_le = cur_e + l_os * math.sin(th_l)
                    th_r = th - pi / 2
                    os_rn = cur_n + r_os * math.cos(th_r)
                    os_re = cur_e + r_os * math.sin(th_r)
                    first = False
                else:
                    th = _atan2_excel(up_n - cur_n, up_e - cur_e)
                    th_l = th + pi / 2
                    os_ln = cur_n + l_os * math.cos(th_l)
                    os_le = cur_e + l_os * math.sin(th_l)
                    th_r = th - pi / 2
                    os_rn = cur_n + r_os * math.cos(th_r)
                    os_re = cur_e + r_os * math.sin(th_r)
                up_e, up_n = cur_e, cur_n
                _emit(out, ch, cur_e, cur_n, os_le, os_ln, os_re, os_rn)
                ch += step
        else:
            # Unknown segment types are skipped (VBA would MsgBox).
            continue

    # Deduplicate near-identical chainages from segment joints.
    if not out:
        raise ValueError("No densified horizontal points generated")
    deduped: List[Dict[str, float]] = [out[0]]
    for pt in out[1:]:
        if abs(pt["chainage"] - deduped[-1]["chainage"]) < 1e-9:
            deduped[-1] = pt
        else:
            deduped.append(pt)
    return deduped


def build_design_points(
    horiz: Sequence[HorizSeg],
    verts: Sequence[VertSeg],
    *,
    step: float = 1.0,
) -> List[AlignPoint]:
    """Dense (chainage, E, N, level) design centreline."""
    dens = densify_horizontal(horiz, step=step)
    points: List[AlignPoint] = []
    for pt in dens:
        lv = vertical_level_at(verts, pt["chainage"])
        if lv is None:
            continue
        points.append((pt["chainage"], pt["easting"], pt["northing"], float(lv)))
    if len(points) < 2:
        raise ValueError("Design densify produced <2 points with levels")
    return points


def parse_alignment2_workbook(path: str | Path) -> Dict[str, Any]:
    """
    Load OSCH design workbook.

    Returns dict with keys: horizontal, vertical, crossfall, points
    (densified AlignPoint list), meta.
    """
    sheets = _load_workbook_sheets(Path(path))
    h_rows = _find_sheet(sheets, "OSCH2_AIn", "OSCH2_Aln", "OSCH2_AIN")
    try:
        v_rows = _find_sheet(sheets, "OSCH2_VIn", "OSCH2_Vln", "OSCH2_VIN")
    except ValueError:
        v_rows = _find_sheet(sheets, "OSCH2_Vln", "OSCH2_VIn")
    try:
        c_rows = _find_sheet(sheets, "OSCH3_LRHS")
    except ValueError:
        c_rows = []

    horiz = parse_horizontal_rows(h_rows)
    verts = parse_vertical_rows(v_rows)
    cross = parse_crossfall_rows(c_rows) if c_rows else []
    points = build_design_points(horiz, verts, step=1.0)
    return {
        "horizontal": horiz,
        "vertical": verts,
        "crossfall": cross,
        "points": points,
        "meta": {
            "ch_start": points[0][0],
            "ch_end": points[-1][0],
            "count": len(points),
        },
    }


def design_at_chainage(
    points: Sequence[AlignPoint],
    chainage: float,
    cross: Optional[Sequence[CrossSeg]] = None,
) -> Dict[str, float]:
    """Interpolate dense design list at chainage; optional crossfall levels."""
    # Local import-style reuse of Alignment(1) lerp via inline.
    if len(points) < 2:
        raise ValueError("Import a design alignment first")
    ch = float(chainage)
    # Exact / bracket search.
    if ch <= points[0][0]:
        a, b = points[0], points[1]
    elif ch >= points[-1][0]:
        a, b = points[-2], points[-1]
    else:
        a = b = points[0]
        for i in range(len(points) - 1):
            if points[i][0] <= ch <= points[i + 1][0]:
                a, b = points[i], points[i + 1]
                break
    span = b[0] - a[0]
    t = 0.0 if abs(span) < 1e-15 else (ch - a[0]) / span
    east = a[1] + (b[1] - a[1]) * t
    north = a[2] + (b[2] - a[2]) * t
    level = a[3] + (b[3] - a[3]) * t
    out = {
        "chainage": ch,
        "easting": east,
        "northing": north,
        "level": level,
    }
    if cross:
        lcf, rcf, llen, rlen = crossfall_at(cross, ch)
        out["left_fall"] = lcf
        out["right_fall"] = rcf
        out["left_level"] = level + (lcf / 100.0) * llen
        out["right_level"] = level + (rcf / 100.0) * rlen
    return out


def survey_vs_design(
    points: Sequence[AlignPoint],
    northing: float,
    easting: float,
    level: float,
) -> Dict[str, float]:
    """
    OSCH_SUR comparison: nearest plan projection onto densified design.

    Input order matches the macro sheet (N, E, Level). Offset sign: left
    negative / right positive via 2D cross product along the segment.
    Chainage is the design chainage at the projected point (not the buggy
    cumulative VBA value).
    """
    if len(points) < 2:
        raise ValueError("Import a design alignment first")
    y = float(easting)  # sheet uses x=N, y=E in VBA; keep EN clear here
    x = float(northing)
    lv = float(level)

    best = None
    for i in range(len(points) - 1):
        # Design stored as (ch, E, N, Lv); VBA loop used (N, E, Lv).
        n1, e1, lv1 = points[i][2], points[i][1], points[i][3]
        n2, e2, lv2 = points[i + 1][2], points[i + 1][1], points[i + 1][3]
        dn, de = n2 - n1, e2 - e1
        den = dn * dn + de * de
        if den < 1e-24:
            t = 0.0
        else:
            # Project survey (N,E)=(x,y) onto segment in N/E space.
            t = ((x - n1) * dn + (y - e1) * de) / den
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
        proj_n = n1 + t * dn
        proj_e = e1 + t * de
        proj_lv = lv1 + t * (lv2 - lv1)
        # Offset distance with side: cross = dn*(E-e1) - de*(N-n1) using VBA vars
        # VBA: crossProduct = (X2-X1)*(y-Y1) - (Y2-Y1)*(x-X1)
        # with X=N, Y=E, x=surveyN, y=surveyE
        cross = dn * (y - e1) - de * (x - n1)
        offset = math.hypot(x - proj_n, y - proj_e)
        if cross < 0:
            offset = -offset
        ch = points[i][0] + t * (points[i + 1][0] - points[i][0])
        cand = (abs(offset), ch, offset, lv - proj_lv, proj_e, proj_n, proj_lv)
        if best is None or cand[0] < best[0]:
            best = cand

    assert best is not None
    _abs_off, ch, offset, d_lv, pe, pn, plv = best
    return {
        "chainage": ch,
        "offset": offset,
        "level_diff": d_lv,
        "design_easting": pe,
        "design_northing": pn,
        "design_level": plv,
    }
