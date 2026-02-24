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


# ─────────────────────────────────────────────────────────────────────────────
# SCORING ENGINE — TO BE IMPLEMENTED
# Implementation order:
#   1. _apply_wizard_modifiers(config) → adjusted thresholds + weights
#   2. _score_schedule(workstream_id, thresholds) → float 0-100
#   3. _score_budget(workstream_id, thresholds) → float 0-100
#   4. _score_blockers(workstream_id, thresholds) → float 0-100
#   5. _composite_rag(s_score, b_score, bl_score, weights) → (float, str)
#   6. _check_staleness(workstream_id, q8_value) → bool
#   7. calculate_rag(workstream_id) → dict  ← public entry point
# ─────────────────────────────────────────────────────────────────────────────

def calculate_rag(workstream_id: str) -> dict:
    """
    Main entry point. Called by the application after any data write.
    Reads all inputs, applies wizard modifiers, calculates scores,
    writes result to rag_scores, and returns the scores dict.

    Returns:
        {
            "schedule_score":  float,
            "budget_score":    float,
            "blocker_score":   float,
            "composite_score": float,
            "rag_status":      "green" | "amber" | "red",
            "is_stale":        bool,
        }
    """
    # TODO: implement in build phase
    raise NotImplementedError("Scoring engine not yet implemented — build phase pending.")
