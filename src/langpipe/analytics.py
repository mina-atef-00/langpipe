"""Analytics: retention, lapse, forecast, and per-stage progress.

All numbers here are computed from the review log and the card schedule in the
database. Nothing is estimated from averages or heuristics. The definitions:

* retention rate: reviews graded 3 or above divided by all reviews
* lapse rate: reviews graded below 3 divided by all reviews (so the two
  together always sum to 1.0)
* review load forecast: the number of cards whose next due date falls inside
  the next N days. Cards never introduced do not appear, so the forecast is a
  floor, not a prediction of new material.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from langpipe.curriculum import StageProgress, progress_for_stage
from langpipe.db import Database
from langpipe.models import utcnow

PASS_THRESHOLD = 3


@dataclass(frozen=True)
class StatsReport:
    total_reviews: int
    passed_reviews: int
    lapsed_reviews: int
    retention_rate: float | None
    lapse_rate: float | None
    total_cards: int
    backlog: int
    forecast_7d: int
    forecast_30d: int
    stages: list[StageProgress]


def compute_report(db: Database, now: datetime | None = None) -> StatsReport:
    reviews = db.list_reviews()
    total = len(reviews)
    passed = sum(1 for r in reviews if r.grade >= PASS_THRESHOLD)
    lapsed = total - passed

    retention = round(passed / total, 4) if total else None
    lapse = round(lapsed / total, 4) if total else None

    today = utcnow() if now is None else now
    backlog = db.count_due_before(today)
    forecast_7 = len(db.cards_due_between(today, today + timedelta(days=7)))
    forecast_30 = len(db.cards_due_between(today, today + timedelta(days=30)))

    stages = [progress_for_stage(db, s) for s in db.list_stages()]

    return StatsReport(
        total_reviews=total,
        passed_reviews=passed,
        lapsed_reviews=lapsed,
        retention_rate=retention,
        lapse_rate=lapse,
        total_cards=len(db.list_cards()),
        backlog=backlog,
        forecast_7d=forecast_7,
        forecast_30d=forecast_30,
        stages=stages,
    )


def render_report(report: StatsReport) -> str:
    lines: list[str] = []
    lines.append("Retention")
    if report.retention_rate is None or report.lapse_rate is None:
        lines.append("  no reviews recorded yet")
    else:
        lines.append(f"  retention rate:  {report.retention_rate * 100:.1f}%")
        lines.append(f"  lapse rate:      {report.lapse_rate * 100:.1f}%")
        lines.append(
            f"  passed/lapsed:   {report.passed_reviews}/{report.lapsed_reviews} "
            f"of {report.total_reviews} reviews"
        )
    lines.append("Review load forecast")
    lines.append(f"  overdue now:          {report.backlog}")
    lines.append(f"  due in next 7 days:   {report.forecast_7d}")
    lines.append(f"  due in next 30 days:  {report.forecast_30d}")
    lines.append(f"  cards total:          {report.total_cards}")
    lines.append("Per-stage progress")
    for s in report.stages:
        lines.append(
            f"  stage {s.stage.order} ({s.stage.name}): "
            f"vocab {s.vocab_learned}/{s.stage.target_vocab} ({s.vocab_pct}%), "
            f"grammar {s.grammar_learned}/{s.stage.target_grammar} ({s.grammar_pct}%)"
        )
    return "\n".join(lines)
