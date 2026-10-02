"""Bounded inputs only; the lesson recomputes all derived pictures and results."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Practice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operated: bool


class InputPractice(Practice):
    input: Literal["按键 A", "按键 B"]


class RulePractice(Practice):
    rule: Literal["shape", "color"]


class RobotPractice(Practice):
    route: Literal["correct", "wrong"]


class PixelPractice(Practice):
    size: Literal[4, 8]


class SortPractice(Practice):
    values: list[Annotated[int, Field(ge=0, le=99)]] = Field(min_length=3, max_length=6)


class PacketPractice(Practice):
    order: Literal["2,3,1", "1,2,3"]


class SearchPractice(Practice):
    target: int = Field(ge=0, le=99)


class ContainerPractice(Practice):
    kind: Literal["stack", "queue"]
    items: list[Literal["A", "B", "C"]] = Field(max_length=3)
    removed: list[Literal["A", "B", "C"]] = Field(max_length=100)


class TrainPractice(Practice):
    testIndex: int = Field(ge=0, le=2)


class PathPractice(Practice):
    start: Literal["A", "B", "C", "D", "E", "F"]
    end: Literal["A", "B", "C", "D", "E", "F"]


class GradientPractice(Practice):
    alpha: Literal[0.05, 0.15, 0.6, 1.1]


class MetricsPractice(Practice):
    threshold: float = Field(ge=0.35, le=0.9, allow_inf_nan=False)


PRACTICES = {
    "primary-lower-input-process-output": InputPractice,
    "primary-lower-sorting-by-rule": RulePractice,
    "primary-lower-robot-instructions": RobotPractice,
    "primary-upper-pixels-build-picture": PixelPractice,
    "primary-upper-cards-bubble-sort": SortPractice,
    "primary-upper-message-packets": PacketPractice,
    "junior-linear-search": SearchPractice,
    "junior-stack-and-queue": ContainerPractice,
    "junior-training-and-testing": TrainPractice,
    "senior-shortest-path": PathPractice,
    "senior-gradient-descent": GradientPractice,
    "senior-classification-metrics": MetricsPractice,
}


def validate_state(state: dict, content_key: str) -> None:
    if state == {}:  # Existing sessions have no experiment yet.
        return
    if (
        set(state) != {"state_version", "content_key", "practice"}
        or type(state["state_version"]) is not int
        or state["state_version"] != 1
        or state["content_key"] != content_key
    ):
        raise ValueError("Incompatible experiment state")
    model = PRACTICES.get(content_key.removeprefix("autoplay-"))
    if model is None:
        raise ValueError("Unknown lesson")
    try:
        model.model_validate(state["practice"])
    except ValidationError as caught:
        raise ValueError("Invalid experiment inputs") from caught
