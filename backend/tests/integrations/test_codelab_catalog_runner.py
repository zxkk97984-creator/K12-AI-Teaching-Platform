from __future__ import annotations

import os
import shutil
import subprocess
from textwrap import dedent

import pytest
from runner.host.runner import DEFAULT_IMAGE, DockerRunner, RunRequest

from app.modules.codelab.grading import grade_observations
from app.modules.codelab.trusted import expected_output, trusted_cases

_CORRECT = {
    "temperature-converter": dedent(
        """\
        def celsius_to_fahrenheit(celsius):
            return celsius * 9 / 5 + 32
        """
    ),
    "list-summary": dedent(
        """\
        def summarize(numbers):
            if not numbers:
                return {'count': 0, 'sum': 0, 'max': None, 'min': None, 'mean': None}
            return {
                'count': len(numbers), 'sum': sum(numbers), 'max': max(numbers),
                'min': min(numbers), 'mean': sum(numbers) / len(numbers),
            }
        """
    ),
    "binary-search": dedent(
        """\
        def binary_search(items, target):
            low, high = 0, len(items) - 1
            while low <= high:
                middle = (low + high) // 2
                if items[middle] == target:
                    return middle
                if items[middle] < target:
                    low = middle + 1
                else:
                    high = middle - 1
            return -1
        """
    ),
    "odd-even": "def is_even(number):\n    return number % 2 == 0\n",
    "even-sum": dedent(
        """\
        def sum_even(numbers):
            return sum(number for number in numbers if number % 2 == 0)
        """
    ),
    "palindrome-check": dedent(
        """\
        def is_palindrome(text):
            return text == text[::-1]
        """
    ),
    "word-frequency": dedent(
        """\
        def word_frequency(words):
            counts = {}
            for word in words:
                counts[word] = counts.get(word, 0) + 1
            return counts
        """
    ),
    "prediction-accuracy": dedent(
        """\
        def accuracy(y_true, y_pred):
            return sum(a == b for a, b in zip(y_true, y_pred)) / len(y_true)
        """
    ),
    "sort-unique": dedent(
        """\
        def sort_unique(numbers):
            return sorted(set(numbers))
        """
    ),
    "balanced-brackets": dedent(
        """\
        def balanced_brackets(text):
            pairs = {')': '(', ']': '[', '}': '{'}
            stack = []
            for char in text:
                if char in '([{':
                    stack.append(char)
                elif not stack or stack.pop() != pairs[char]:
                    return False
            return not stack
        """
    ),
    "range-sum": dedent(
        """\
        def range_sums(numbers, queries):
            return [sum(numbers[left:right + 1]) for left, right in queries]
        """
    ),
    "climbing-stairs": dedent(
        """\
        def climb_stairs(n):
            a, b = 1, 1
            for _ in range(2, n + 1):
                a, b = b, a + b
            return b
        """
    ),
}

_WRONG = {
    "temperature-converter": "def celsius_to_fahrenheit(celsius):\n    return celsius\n",
    "list-summary": "def summarize(numbers):\n    return {}\n",
    "binary-search": "def binary_search(items, target):\n    return -1\n",
    "odd-even": "def is_even(number):\n    return False\n",
    "even-sum": "def sum_even(numbers):\n    return 0\n",
    "palindrome-check": "def is_palindrome(text):\n    return False\n",
    "word-frequency": "def word_frequency(words):\n    return {}\n",
    "prediction-accuracy": "def accuracy(y_true, y_pred):\n    return 0.0\n",
    "sort-unique": "def sort_unique(numbers):\n    return numbers\n",
    "balanced-brackets": "def balanced_brackets(text):\n    return False\n",
    "range-sum": "def range_sums(numbers, queries):\n    return []\n",
    "climbing-stairs": "def climb_stairs(n):\n    return 0\n",
}


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"], check=False
        ).returncode
        == 0
        and subprocess.run(
            ["docker", "image", "inspect", os.getenv("RUNNER_IMAGE", DEFAULT_IMAGE)], check=False
        ).returncode
        == 0
    )


if os.getenv("RUNNER_DOCKER_TESTS") != "1" or not _docker_available():
    pytest.skip(
        "catalogue runner checks require RUNNER_DOCKER_TESTS=1 and the fixed Docker image",
        allow_module_level=True,
    )


@pytest.mark.parametrize("task_id", sorted(_CORRECT))
def test_each_catalogue_task_runs_all_trusted_cases_and_rejects_a_wrong_answer(
    task_id: str,
) -> None:
    cases = trusted_cases(task_id)
    correct: list[dict] = []
    wrong: list[dict] = []
    runner = DockerRunner(image=os.getenv("RUNNER_IMAGE", DEFAULT_IMAGE))
    for case in cases:
        base = {
            "case_id": case.case_id,
            "task_id": task_id,
            "task_revision": 1,
            "entrypoint": {
                "temperature-converter": "celsius_to_fahrenheit",
                "list-summary": "summarize",
                "binary-search": "binary_search",
                "odd-even": "is_even",
                "even-sum": "sum_even",
                "palindrome-check": "is_palindrome",
                "word-frequency": "word_frequency",
                "prediction-accuracy": "accuracy",
                "sort-unique": "sort_unique",
                "balanced-brackets": "balanced_brackets",
                "range-sum": "range_sums",
                "climbing-stairs": "climb_stairs",
            }[task_id],
            "input": case.input,
            "owner_id": "catalog-runner-test",
        }
        for label, code, observations in (
            ("correct", _CORRECT[task_id], correct),
            ("wrong", _WRONG[task_id], wrong),
        ):
            request = RunRequest.from_payload(
                base | {"student_code": code, "lease_id": f"{task_id}-{case.case_id}-{label}"}
            )
            result = runner.run_case(request).as_observation()
            observations.append(result)
            if label == "correct":
                assert result["execution_status"] == "COMPLETED"
                assert result.get("actual_output") == expected_output(task_id, case.input)

    assert grade_observations(task_id, 1, correct).status == "PASSED"
    assert grade_observations(task_id, 1, correct).deterministic_score == 70
    wrong_grade = grade_observations(task_id, 1, wrong)
    assert wrong_grade.status != "PASSED"
    assert wrong_grade.deterministic_score != 70
