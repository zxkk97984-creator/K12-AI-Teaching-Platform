from __future__ import annotations

import copy

import pytest

from evals import review_tools


def _completed_review() -> dict:
    review = copy.deepcopy(review_tools.build_template())
    review["review_status"] = "COMPLETE"
    review["reviewer"] = {"name": "真实审校者", "role_or_org": "合成评测审校组"}
    review["reviewed_at"] = "2026-09-20T15:00:00+08:00"
    review["attestation"] = review_tools.ATTESTATION
    for item in review["case_reviews"]:
        item["scores"] = {dimension: 2 for dimension in review_tools._dimensions()}
        item["disposition"] = "PASS"
        item["rationale"] = "已逐项核对合成输出与来源。"
    review["overall"] = {
        "accept_failed_cases_for_demo": False,
        "four_stage_age_fit": True,
        "source_support_sufficient": True,
        "code_feedback_boundary_preserved": True,
        "conclusion": "NEEDS_REVISION",
        "rationale": "三个失败案例不能直接进入演示，需要保留失败说明并完成修订。",
        "traceable_signature": "review-record-001",
    }
    return review


def test_template_is_unsigned_and_matches_live_cases() -> None:
    template = review_tools.build_template()

    assert template["review_status"] == "NOT_RUN"
    assert len(template["case_reviews"]) == 16
    assert all(
        value is None for value in template["case_reviews"][0]["scores"].values()
    )


def test_completed_review_requires_all_human_fields() -> None:
    result = review_tools.validate_completed(_completed_review())

    assert result["human_review"] == "COMPLETE"
    assert result["case_dispositions"] == {"PASS": 16}
    assert result["overall_conclusion"] == "NEEDS_REVISION"


def test_agent_cannot_pass_an_unsigned_or_sparse_review() -> None:
    with pytest.raises(review_tools.ReviewValidationError, match="review_status"):
        review_tools.validate_completed(review_tools.build_template())

    sparse = _completed_review()
    sparse["case_reviews"][0]["scores"]["factuality"] = None
    with pytest.raises(review_tools.ReviewValidationError, match="factuality"):
        review_tools.validate_completed(sparse)
