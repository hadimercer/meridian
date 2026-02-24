"""
pipeline/scoring.py
RAG Scoring Engine for Meridian.

Implements the full scoring logic from FRD Section 5:
  - Schedule Health  (milestone completion % vs time elapsed %)
  - Budget Health    (actual spend vs planned spend to date)
  - Blocker Health   (open blocker count and age)
  - Composite RAG    (weighted average of three dimensions)
  - Wizard modifiers (threshold adjustments from wizard_config)

Entry point:
  calculate_rag(workstream_id: str) -> dict
    Reads all inputs from the DB, applies wizard modifiers,
    returns scores dict, and writes result to rag_scores table.
"""

import logging
from datetime import date, datetime, timezone

from psycopg2.extras import RealDictCursor

from pipeline.db import get_pg_connection, get_supabase_admin

logger = logging.getLogger(__name__)


# ─── DEFAULT THRESHOLDS (from FRD Section 5.2) ───────────────────────────────
# These values are the baseline. Wizard modifiers adjust them per workstream.
# All kept here so tuning never requires touching application logic.

SCHEDULE_THRESHOLDS = {
    "green_min":  -10.0,   # SV >= -10%  → Green
    "amber_min":  -25.0,   # SV >= -25%  → Amber
    # SV < -25% → Red
}

BUDGET_THRESHOLDS = {
    "green_min":  -5.0,    # BV >= -5%   → Green
    "amber_min":  -15.0,   # BV >= -15%  → Amber
    # BV < -15% → Red
}

BLOCKER_SCORES = {
    "no_blockers":       100,
    "one_recent":         80,   # 1 blocker, < 3 days
    "one_aging":          55,   # 1 blocker, 3-7 days
    "one_old":            25,   # 1 blocker, > 7 days
    "multiple_max":       40,   # 2+ blockers, any age
    "external_penalty":  -10,   # Applied when Q5 = blocked_external
}

BLOCKER_AGE_THRESHOLDS = {
    "recent_days":  3,
    "aging_days":   7,
}

# ─── DEFAULT COMPOSITE WEIGHTS (from FRD Section 5.4) ────────────────────────

DEFAULT_WEIGHTS = {
    "schedule": 0.40,
    "budget":   0.35,
    "blocker":  0.25,
}

# ─── COMPOSITE RAG THRESHOLDS ────────────────────────────────────────────────

COMPOSITE_THRESHOLDS = {
    "green_min": 70,   # composite >= 70 → Green
    "amber_min": 40,   # composite >= 40 → Amber
    # composite <  40 → Red
}

# ─── STALENESS WINDOWS (days) — driven by Q8 ─────────────────────────────────

STALENESS_WINDOWS = {
    "daily":    2,
    "weekly":   8,
    "biweekly": 16,
    "monthly":  35,
}


# ─── PRIVATE HELPERS ─────────────────────────────────────────────────────────

def _interp(value: float, low: float, high: float, out_low: float, out_high: float) -> float:
    """
    Linearly interpolate value within [low, high] onto [out_low, out_high].

    value is clamped to [low, high] before interpolation so the result always
    stays within [out_low, out_high].  Returns out_low when low == high to
    avoid division by zero.
    """
    if high == low:
        return out_low
    t = max(0.0, min(1.0, (value - low) / (high - low)))
    return out_low + t * (out_high - out_low)


def _get_wizard_config(workstream_id: str) -> dict:
    """
    Query wizard_config and workstreams and return all fields needed by the
    scoring engine in a single flat dict.

    Opens and closes its own psycopg2 connection (called before the main
    scoring connection is opened in calculate_rag).  Missing rows produce an
    empty contribution — callers must tolerate None values for any field.
    """
    sql_wizard = "SELECT * FROM wizard_config WHERE workstream_id = %s"
    sql_ws = (
        "SELECT start_date, end_date, planned_budget "
        "FROM workstreams WHERE id = %s"
    )

    conn = get_pg_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_wizard, (workstream_id,))
            wizard_row = cur.fetchone()

            cur.execute(sql_ws, (workstream_id,))
            ws_row = cur.fetchone()
    finally:
        conn.close()

    config: dict = {}
    if wizard_row:
        config.update(dict(wizard_row))
    if ws_row:
        config.update(dict(ws_row))
    return config


def _apply_wizard_modifiers(config: dict) -> dict:
    """
    Apply all wizard-answer modifiers to the baseline thresholds and weights.

    Modifier application order:
      1. q2 (deadline nature)
      2. q4 (budget exposure)
      3. q5 (dependency level)
      4. q7 (project phase)
      5. q6 (risk level — global compression, applied last)
      6. Weight re-normalisation

    Returns a dict with keys:
      schedule_green, schedule_amber,
      budget_green, budget_amber,
      blocker_recent_days, blocker_aging_days,
      w_schedule, w_budget, w_blocker,
      staleness_days,
      q4_budget_exposure, q5_dependency_level, q7_phase
    """
    # ── Start from defaults ───────────────────────────────────────────────────
    schedule_green = SCHEDULE_THRESHOLDS["green_min"]       # -10.0
    schedule_amber = SCHEDULE_THRESHOLDS["amber_min"]       # -25.0
    budget_green   = BUDGET_THRESHOLDS["green_min"]         #  -5.0
    budget_amber   = BUDGET_THRESHOLDS["amber_min"]         # -15.0
    blocker_recent = float(BLOCKER_AGE_THRESHOLDS["recent_days"])  # 3
    blocker_aging  = float(BLOCKER_AGE_THRESHOLDS["aging_days"])   # 7
    w_schedule     = DEFAULT_WEIGHTS["schedule"]            # 0.40
    w_budget       = DEFAULT_WEIGHTS["budget"]              # 0.35
    w_blocker      = DEFAULT_WEIGHTS["blocker"]             # 0.25

    q2 = config.get("q2_deadline_nature")
    q4 = config.get("q4_budget_exposure")
    q5 = config.get("q5_dependency_level")
    q6 = config.get("q6_risk_level")
    q7 = config.get("q7_phase")
    q8 = config.get("q8_update_frequency", "weekly")

    staleness_days = float(STALENESS_WINDOWS.get(q8) or STALENESS_WINDOWS["weekly"])

    # ── q2: deadline nature ───────────────────────────────────────────────────
    if q2 == "hard_contractual":
        schedule_green = -5.0
        schedule_amber = -15.0
    elif q2 == "ongoing":
        w_schedule     = 0.10
        schedule_green = -20.0
        schedule_amber = -40.0

    # ── q4: budget exposure ───────────────────────────────────────────────────
    if q4 == "client_billable":
        w_budget     = 0.45
        budget_green = -3.0
        budget_amber = -10.0
    elif q4 == "informal_none":
        w_budget = 0.05

    # ── q5: dependency level ──────────────────────────────────────────────────
    if q5 == "blocked_external":
        # 3 → 1.5, truncate to int → 1  |  7 → 3.5, truncate to int → 3
        blocker_recent = float(int(blocker_recent / 2))
        blocker_aging  = float(int(blocker_aging  / 2))

    # ── q7: project phase ─────────────────────────────────────────────────────
    if q7 == "review_closing":
        schedule_green = -10.0          # Hard override regardless of prior mods
    elif q7 == "discovery":
        budget_amber = -20.0

    # ── q6: risk level (global compression — applied last) ────────────────────
    if q6 == "high":
        schedule_green += 5.0
        schedule_amber += 5.0
        budget_green   += 5.0
        budget_amber   += 5.0
    elif q6 == "critical":
        schedule_green += 10.0
        schedule_amber += 10.0
        budget_green   += 10.0
        budget_amber   += 10.0
        staleness_days  = staleness_days / 2.0

    # ── Re-normalise weights so they sum to 1.0 ───────────────────────────────
    total_w = w_schedule + w_budget + w_blocker
    w_schedule = w_schedule / total_w
    w_budget   = w_budget   / total_w
    w_blocker  = w_blocker  / total_w

    return {
        "schedule_green":      schedule_green,
        "schedule_amber":      schedule_amber,
        "budget_green":        budget_green,
        "budget_amber":        budget_amber,
        "blocker_recent_days": int(blocker_recent),
        "blocker_aging_days":  int(blocker_aging),
        "w_schedule":          w_schedule,
        "w_budget":            w_budget,
        "w_blocker":           w_blocker,
        "staleness_days":      staleness_days,
        # Pass-through wizard answers needed inside scoring functions
        "q4_budget_exposure":  q4,
        "q5_dependency_level": q5,
        "q7_phase":            q7,
    }


def _score_schedule(workstream_id: str, thresholds: dict, conn) -> float:
    """
    Calculate schedule health score in the range [0, 100].

    Computes Schedule Variance (SV = milestone_completion_pct - time_elapsed_pct)
    and maps it to a score via linear interpolation across two bands:
      - Amber-to-green band: SV in [amber_min, green_min) → score in [70, 99]
      - Red-to-amber band:   SV in [-100, amber_min)      → score in [1, 69]

    Returns 100 immediately when the workstream has no milestones.

    If q7_phase is 'review_closing', subtracts 10 points per overdue incomplete
    milestone (milestones whose due_date has passed but status != 'complete').
    Final score is clamped to [0, 100].
    """
    sql_ws = (
        "SELECT start_date, end_date FROM workstreams WHERE id = %s"
    )
    sql_milestones = (
        "SELECT status, due_date FROM milestones WHERE workstream_id = %s"
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql_ws, (workstream_id,))
        ws = cur.fetchone()

        cur.execute(sql_milestones, (workstream_id,))
        milestones = cur.fetchall()

    # No milestones → no schedule penalty
    if not milestones:
        return 100.0

    total     = len(milestones)
    complete  = sum(1 for m in milestones if m["status"] == "complete")
    milestone_pct = complete / total * 100.0

    # Time elapsed percentage, clamped 0–100
    today      = date.today()
    start_date = ws["start_date"]
    end_date   = ws["end_date"]
    span_days  = (end_date - start_date).days
    if span_days <= 0:
        time_pct = 100.0
    else:
        time_pct = (today - start_date).days / span_days * 100.0
    time_pct = max(0.0, min(100.0, time_pct))

    sv          = milestone_pct - time_pct
    green_min   = thresholds["schedule_green"]
    amber_min   = thresholds["schedule_amber"]

    if sv >= green_min:
        score = 100.0
    elif sv >= amber_min:
        # Linear interpolation: amber_min → 70, approaching green_min → 99
        score = _interp(sv, amber_min, green_min, 70.0, 99.0)
    else:
        # Linear interpolation: -100 → 1, approaching amber_min → 69
        score = _interp(max(-100.0, sv), -100.0, amber_min, 1.0, 69.0)

    # q7 review_closing: -10 per overdue incomplete milestone
    if thresholds.get("q7_phase") == "review_closing":
        overdue = sum(
            1 for m in milestones
            if m["status"] != "complete"
            and m.get("due_date") is not None
            and m["due_date"] < today
        )
        score -= overdue * 10.0

    return max(0.0, min(100.0, score))


def _score_budget(workstream_id: str, thresholds: dict, conn) -> float:
    """
    Calculate budget health score in the range [0, 100].

    Computes Budget Variance (BV = (planned_spend_to_date - actual_spend) /
    total_budget * 100) and maps it using the same two-band interpolation as
    schedule health.

    Returns 100 immediately when:
      - q4_budget_exposure is 'informal_none', or
      - planned_budget is NULL or zero (no formal budget to track).
    """
    sql_ws    = (
        "SELECT start_date, end_date, planned_budget "
        "FROM workstreams WHERE id = %s"
    )
    sql_spend = (
        "SELECT COALESCE(SUM(amount), 0) AS total_spend "
        "FROM spend_entries WHERE workstream_id = %s"
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql_ws, (workstream_id,))
        ws = cur.fetchone()

        cur.execute(sql_spend, (workstream_id,))
        spend_row = cur.fetchone()

    planned_budget = ws["planned_budget"] if ws else None

    # Early return: no formal budget to track
    if thresholds.get("q4_budget_exposure") == "informal_none":
        return 100.0
    if not planned_budget or float(planned_budget) == 0:
        return 100.0

    planned_budget = float(planned_budget)
    actual_spend   = float(spend_row["total_spend"]) if spend_row else 0.0

    # Time elapsed percentage (same calculation as schedule)
    today      = date.today()
    start_date = ws["start_date"]
    end_date   = ws["end_date"]
    span_days  = (end_date - start_date).days
    if span_days <= 0:
        time_pct = 100.0
    else:
        time_pct = (today - start_date).days / span_days * 100.0
    time_pct = max(0.0, min(100.0, time_pct))

    planned_to_date = planned_budget * time_pct / 100.0
    bv              = (planned_to_date - actual_spend) / planned_budget * 100.0

    green_min = thresholds["budget_green"]
    amber_min = thresholds["budget_amber"]

    if bv >= green_min:
        score = 100.0
    elif bv >= amber_min:
        score = _interp(bv, amber_min, green_min, 70.0, 99.0)
    else:
        score = _interp(max(-100.0, bv), -100.0, amber_min, 1.0, 69.0)

    return max(0.0, min(100.0, score))


def _score_blockers(workstream_id: str, thresholds: dict, conn) -> float:
    """
    Calculate blocker health score in the range [0, 100].

    Applies the BLOCKER_SCORES lookup table based on open blocker count and the
    age of the oldest open blocker (days since date_raised).  Rule priority:
      1. No open blockers                    → 100
      2. Exactly 1 blocker, age < recent    → 80
      3. Exactly 1 blocker, recent ≤ age ≤ aging → 55
      4. Exactly 1 blocker, age > aging     → 25
      5. 2+ blockers (any age)              → 40 (cap)

    If q5_dependency_level is 'blocked_external', subtracts 10 (floor at 0).
    """
    sql_blockers = (
        "SELECT date_raised FROM blockers "
        "WHERE workstream_id = %s AND status = 'open'"
    )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql_blockers, (workstream_id,))
        blockers = cur.fetchall()

    recent_days = thresholds["blocker_recent_days"]
    aging_days  = thresholds["blocker_aging_days"]

    if not blockers:
        score = float(BLOCKER_SCORES["no_blockers"])
    elif len(blockers) >= 2:
        score = float(BLOCKER_SCORES["multiple_max"])
    else:
        today       = date.today()
        date_raised = blockers[0]["date_raised"]
        age         = (today - date_raised).days

        if age < recent_days:
            score = float(BLOCKER_SCORES["one_recent"])
        elif age <= aging_days:
            score = float(BLOCKER_SCORES["one_aging"])
        else:
            score = float(BLOCKER_SCORES["one_old"])

    # External dependency penalty
    if thresholds.get("q5_dependency_level") == "blocked_external":
        score = max(0.0, score + BLOCKER_SCORES["external_penalty"])

    return score


def _check_staleness(workstream_id: str, staleness_days: float, conn) -> bool:
    """
    Return True if workstream data has not been updated within staleness_days.

    Queries the latest timestamp across milestones.updated_at,
    spend_entries.created_at, and blockers.updated_at.  Returns False if no
    data exists for this workstream (cannot determine staleness) or if the
    latest timestamp is within the allowed window.
    """
    sql = """
        SELECT GREATEST(
            MAX(m.updated_at),
            MAX(s.created_at),
            MAX(b.updated_at)
        ) AS latest
        FROM milestones    m,
             spend_entries s,
             blockers      b
        WHERE m.workstream_id = %s
          AND s.workstream_id = %s
          AND b.workstream_id = %s
    """

    with conn.cursor() as cur:
        cur.execute(sql, (workstream_id, workstream_id, workstream_id))
        row = cur.fetchone()

    if row is None or row[0] is None:
        return False

    latest = row[0]
    now    = datetime.now(timezone.utc)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)

    gap_days = (now - latest).total_seconds() / 86400.0
    return gap_days > staleness_days


# ─── PUBLIC ENTRY POINT ───────────────────────────────────────────────────────

def calculate_rag(workstream_id: str) -> dict:
    """
    Calculate and persist the RAG score for a workstream.

    Opens ONE psycopg2 connection and passes it to all sub-scoring functions.
    Writes the result to the rag_scores table via the Supabase admin client
    (bypassing RLS).

    Returns:
        {
            "schedule_score":  float,
            "budget_score":    float,
            "blocker_score":   float,
            "composite_score": float,
            "rag_status":      "green" | "amber" | "red",
            "is_stale":        bool,
        }

    On any exception: logs the error and returns the last known values from
    rag_scores unchanged.  If no prior record exists, returns a zeroed-out
    red/stale dict rather than raising.
    """
    try:
        config     = _get_wizard_config(workstream_id)
        thresholds = _apply_wizard_modifiers(config)

        conn = get_pg_connection()
        try:
            schedule_score = _score_schedule(workstream_id, thresholds, conn)
            budget_score   = _score_budget(workstream_id, thresholds, conn)
            blocker_score  = _score_blockers(workstream_id, thresholds, conn)
            is_stale       = _check_staleness(
                workstream_id, thresholds["staleness_days"], conn
            )
        finally:
            conn.close()

        composite = (
            schedule_score * thresholds["w_schedule"]
            + budget_score * thresholds["w_budget"]
            + blocker_score * thresholds["w_blocker"]
        )

        if composite >= COMPOSITE_THRESHOLDS["green_min"]:
            rag_status = "green"
        elif composite >= COMPOSITE_THRESHOLDS["amber_min"]:
            rag_status = "amber"
        else:
            rag_status = "red"

        result = {
            "schedule_score":  round(schedule_score, 2),
            "budget_score":    round(budget_score,   2),
            "blocker_score":   round(blocker_score,  2),
            "composite_score": round(composite,      2),
            "rag_status":      rag_status,
            "is_stale":        is_stale,
        }

        # Write result to rag_scores (service-role bypasses RLS)
        admin = get_supabase_admin()
        admin.table("rag_scores").upsert({
            "workstream_id": workstream_id,
            "calculated_at":     datetime.now(timezone.utc).isoformat(),
            **result,
        }).execute()

        return result

    except Exception as exc:
        logger.error(
            "calculate_rag failed for workstream %s: %s",
            workstream_id,
            exc,
            exc_info=True,
        )

        # Return the last known record so the UI does not break
        try:
            admin    = get_supabase_admin()
            response = (
                admin.table("rag_scores")
                .select("*")
                .eq("workstream_id", workstream_id)
                .single()
                .execute()
            )
            if response.data:
                row = response.data
                return {
                    "schedule_score":  row.get("schedule_score",  0.0),
                    "budget_score":    row.get("budget_score",    0.0),
                    "blocker_score":   row.get("blocker_score",   0.0),
                    "composite_score": row.get("composite_score", 0.0),
                    "rag_status":      row.get("rag_status",      "red"),
                    "is_stale":        row.get("is_stale",        True),
                }
        except Exception as fallback_exc:
            logger.error(
                "Fallback rag_scores fetch also failed for %s: %s",
                workstream_id,
                fallback_exc,
            )

        # Absolute last resort — zeroed red result
        return {
            "schedule_score":  0.0,
            "budget_score":    0.0,
            "blocker_score":   0.0,
            "composite_score": 0.0,
            "rag_status":      "red",
            "is_stale":        True,
        }
