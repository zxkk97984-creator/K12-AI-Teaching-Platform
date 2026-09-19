"""Trusted code-task contracts and catalog import helpers.

Student code is intentionally not executed by this package. T24 owns the
isolated runner boundary; this module only validates task definitions and
grades structured observations returned by a trusted runner.
"""

from app.modules.codelab.contracts import TaskDefinition, load_catalog, public_task_view
from app.modules.codelab.grading import grade_observations

__all__ = ["TaskDefinition", "grade_observations", "load_catalog", "public_task_view"]
