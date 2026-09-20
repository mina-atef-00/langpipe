"""Curriculum engine: a phased plan and progress against it.

The default plan follows the bridge pattern used in self-directed language
study: a vocabulary front-load phase, then input, expansion, and fluency. The
targets are data, so a learner can override them. Progress is computed from the
review log, not from counts of generated cards: a word only counts toward the
vocabulary target once it has been reviewed and recalled at least once
(grade >= 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from lesan_pipe.db import Database
from lesan_pipe.models import CurriculumStage

DEFAULT_STAGES: list[CurriculumStage] = [
    CurriculumStage(
        order=1,
        name="bridge",
        target_vocab=300,
        target_grammar=20,
        description=(
            "Vocabulary front-load. Nothing is comprehensible yet, so the "
            "schedule is SRS-heavy. Custom texts use only words already studied."
        ),
    ),
    CurriculumStage(
        order=2,
        name="input",
        target_vocab=800,
        target_grammar=40,
        description="Graded readers and slow audio become usable. Sentence mining starts.",
    ),
    CurriculumStage(
        order=3,
        name="expansion",
        target_vocab=1500,
        target_grammar=60,
        description="Native-adjacent content opens up. Production (writing, speaking) begins.",
    ),
    CurriculumStage(
        order=4,
        name="fluency",
        target_vocab=2500,
        target_grammar=80,
        description="Review-only SRS; most time on native content and production.",
    ),
]


@dataclass(frozen=True)
class StageProgress:
    """Measured progress for one curriculum stage."""

    stage: CurriculumStage
    vocab_learned: int
    grammar_learned: int
    vocab_in_pack: int
    grammar_in_pack: int

    @property
    def vocab_pct(self) -> float:
        return self._pct(self.vocab_learned, self.stage.target_vocab)

    @property
    def grammar_pct(self) -> float:
        return self._pct(self.grammar_learned, self.stage.target_grammar)

    @staticmethod
    def _pct(learned: int, target: int) -> float:
        if target <= 0:
            return 100.0
        return min(100.0, round(100.0 * learned / target, 1))


def progress_for_stage(db: Database, stage: CurriculumStage) -> StageProgress:
    """Compute progress for one stage from the review log and the pack contents."""
    vocab_reviewed = db.vocab_reviewed_by_stage().get(stage.order, 0)
    grammar_reviewed = db.grammar_reviewed_by_stage().get(stage.order, 0)
    vocab_in_pack = db.count_notes_by_kind_stage("vocab").get(stage.order, 0)
    grammar_in_pack = db.count_notes_by_kind_stage("grammar").get(stage.order, 0)
    return StageProgress(
        stage=stage,
        vocab_learned=vocab_reviewed,
        grammar_learned=grammar_reviewed,
        vocab_in_pack=vocab_in_pack,
        grammar_in_pack=grammar_in_pack,
    )
