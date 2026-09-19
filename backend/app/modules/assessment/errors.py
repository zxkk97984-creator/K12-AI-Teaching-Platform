"""Stable, leak-free error codes for the Designer quiz-draft pipeline (T15).

Every error carries a short machine code plus a *safe* detail string: field
paths, rule names and counts only. Raw model JSON, stems, options and answers
never travel through an exception, a log line or an HTTP error body.
"""

from __future__ import annotations


class AssessmentError(Exception):
    """Base class: code is a stable machine identifier, detail is leak-free."""

    code = "ASSESSMENT_ERROR"

    def __init__(self, detail: str, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if code is not None:
            self.code = code


class DesignerRequestInvalid(AssessmentError):
    """The trusted request could not be built (no material, bad chapter)."""

    code = "DESIGNER_REQUEST_INVALID"


class DesignerUnavailable(AssessmentError):
    """The gateway could not produce a draft (mode disabled/error/insufficient)."""

    code = "DESIGNER_UNAVAILABLE"


class QuizDraftRejected(AssessmentError):
    """The designer output failed strict validation and must not be auto-used."""

    code = "QUIZ_DRAFT_REJECTED"


class HumanApprovalNotAllowed(AssessmentError):
    """HUMAN_APPROVED requires a real human reviewer and a valid draft."""

    code = "HUMAN_APPROVAL_NOT_ALLOWED"
