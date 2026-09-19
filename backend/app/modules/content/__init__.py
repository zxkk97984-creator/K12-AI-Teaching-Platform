"""Versioned curriculum content.

Public surface for other modules: package loading/validation, the idempotent
importer, review/publication transitions and student visibility rules.
"""

from app.modules.content.importer import (
    ContentImportError,
    ContentNotPublishable,
    ImportResult,
    build_plan,
    import_package,
    materialize_published,
    mirror_revision,
)
from app.modules.content.package import LoadedPackage, PackageValidationError, load_package
from app.modules.content.schemas import ChapterDetailDTO, ChapterSummaryDTO, ViewerScope
from app.modules.content.service import (
    ContentReviewError,
    content_profile_for,
    publish_revision,
    record_review,
    viewer_scope_from_profile,
    visible_chapter_detail,
    visible_chapters,
    withdraw_revision,
)

__all__ = [
    "ChapterDetailDTO",
    "ChapterSummaryDTO",
    "ContentImportError",
    "ContentNotPublishable",
    "ContentReviewError",
    "ImportResult",
    "LoadedPackage",
    "PackageValidationError",
    "ViewerScope",
    "build_plan",
    "content_profile_for",
    "import_package",
    "load_package",
    "materialize_published",
    "mirror_revision",
    "publish_revision",
    "record_review",
    "viewer_scope_from_profile",
    "visible_chapter_detail",
    "visible_chapters",
    "withdraw_revision",
]
