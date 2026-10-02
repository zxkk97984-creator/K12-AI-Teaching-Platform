from app.modules.ai.service import BACKEND_HANDLERS, register_backend_handler
from app.modules.lookup.schemas import (
    CourseSearchInput,
    LearningProgressInput,
    LookupResult,
    WrongQuestionsInput,
)
from app.modules.lookup.service import LABELS, course_search, learning_progress, wrong_questions

HANDLERS = {
    "COURSE_SEARCH": course_search,
    "WRONG_QUESTIONS": wrong_questions,
    "LEARNING_PROGRESS": learning_progress,
}
INPUTS = {
    "COURSE_SEARCH": CourseSearchInput,
    "WRONG_QUESTIONS": WrongQuestionsInput,
    "LEARNING_PROGRESS": LearningProgressInput,
}


def installed_capability(identifier: str):
    if identifier not in HANDLERS:
        return None
    name = f"lookup.{identifier}"
    if name not in BACKEND_HANDLERS:
        register_backend_handler(
            name,
            HANDLERS[identifier],
            input_model=INPUTS[identifier],
            output_model=LookupResult,
            requires_runtime=True,
        )
    return {
        "id": identifier,
        "name": LABELS[identifier],
        "executor": "BACKEND",
        "handler": name,
        "allowed_context": [],
        "enabled": True,
    }
