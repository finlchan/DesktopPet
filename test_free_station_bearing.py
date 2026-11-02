#!/usr/bin/env python3
"""Free Station mean-bearing / TESTDEG wrap tests (no GUI).

Run: python test_free_station_bearing.py
"""

from __future__ import annotations

import math
import sys

from desktop_pet import (
    mean_bearing_faces,
    survey_deg,
    survey_dms,
    survey_test_deg,
)


def _approx(a, b, tol=1e-9):
    return abs(float(a) - float(b)) <= tol


def _deg_of_mean(f1, f2):
    m = mean_bearing_faces(f1, f2)
    assert m is not None
    return survey_deg(m)


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        if cond:
            print(f"OK  {name}")
        else:
            failures.append(name)
            print(f"FAIL {name} {detail}", file=sys.stderr)

    # --- survey_test_deg wrap ---
    check("test_deg(360)→0", survey_test_deg(360) == 0, repr(survey_test_deg(360)))
    check("test_deg(360.0)→0", survey_test_deg(360.0) == 0.0, repr(survey_test_deg(360.0)))
    check("test_deg(0)→0", survey_test_deg(0) == 0)
    check("test_deg(361)→1", _approx(survey_test_deg(361), 1.0), repr(survey_test_deg(361)))
    check("test_deg(720)→0", survey_test_deg(720) == 0.0, repr(survey_test_deg(720)))
    check("test_deg(-1)→359", _approx(survey_test_deg(-1), 359), repr(survey_test_deg(-1)))

    # --- mean_bearing_faces: north singularity ---
    m01 = mean_bearing_faces(0, 180)
    check("mean(0,180)==0", m01 == 0 or m01 == 0.0, repr(m01))
    check("mean(0,180) deg==0", _approx(_deg_of_mean(0, 180), 0.0), repr(_deg_of_mean(0, 180)))

    # --- regression: ordinary pair ---
    m45 = mean_bearing_faces(45, 225)
    check("mean(45,225)==45", _approx(m45, 45.0), repr(m45))

    # --- F2-only 180 → 0 (not 360) ---
    m_f2 = mean_bearing_faces(None, 180)
    check("F2-only 180 → 0", m_f2 == 0 or m_f2 == 0.0, repr(m_f2))
    check(
        "F2-only 180 deg==0",
        _approx(survey_deg(m_f2), 0.0),
        repr(survey_deg(m_f2)),
    )

    # --- F1-only 0 stays 0 ---
    check("F1-only 0 → 0", mean_bearing_faces(0, None) == 0)

    # --- near-north: stay near 0, not ~180 ---
    near = _deg_of_mean(0.0001, 180.0001)
    check("near-north abs(deg)<1", abs(near) < 1.0 or abs(near - 360) < 1.0, repr(near))

    # --- sheet-parity sample unchanged ---
    parity = mean_bearing_faces(330.140182, 150.140182)
    check(
        "sheet-parity DD.MMSS",
        _approx(parity, 330.140182, tol=1e-6),
        repr(parity),
    )
    # decimal-degree side should match DEG of F1
    check(
        "sheet-parity deg≈DEG(F1)",
        _approx(survey_deg(parity), survey_deg(330.140182), tol=1e-6),
        repr(survey_deg(parity)),
    )

    # --- DMS round-trip at 0 after wrap ---
    check("survey_dms(0)==0", survey_dms(0) == 0.0)
    check(
        "dms(test_deg(360))==0",
        survey_dms(survey_test_deg(360)) == 0.0,
        repr(survey_dms(survey_test_deg(360))),
    )

    if failures:
        print(f"{len(failures)} failure(s)", file=sys.stderr)
        return 1
    print("test_free_station_bearing: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
