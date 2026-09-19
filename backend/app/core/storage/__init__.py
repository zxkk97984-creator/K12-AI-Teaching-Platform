"""Restricted local file storage for T20 learning resources.

Design rules (fail-closed):

* Keys are project-internal relative POSIX paths. Absolute paths, ``..``,
  backslashes, NUL bytes and hidden path segments are rejected before any
  filesystem call.
* The resolved path must stay inside the configured storage root, and no
  component may be a symlink.
* Uploads are streamed to a temporary file inside the root with a hard byte
  limit, hashed, sniffed, then atomically renamed into place.
* Nothing in this package talks to the network: no arbitrary URL proxy.
"""

from app.core.storage.keys import StorageKeyError, build_storage_key, validate_storage_key
from app.core.storage.local import LocalFileStore, StorageError, StorageWriteResult
from app.core.storage.sniff import SniffResult, detect_mime
from app.core.storage.tickets import TicketError, sign_ticket, verify_ticket
from app.core.storage.uploads import (
    KIND_ALLOWED_FAMILIES,
    UploadRejected,
    ValidatedUpload,
    validate_upload,
)

__all__ = [
    "KIND_ALLOWED_FAMILIES",
    "LocalFileStore",
    "SniffResult",
    "StorageError",
    "StorageKeyError",
    "StorageWriteResult",
    "TicketError",
    "UploadRejected",
    "ValidatedUpload",
    "build_storage_key",
    "detect_mime",
    "sign_ticket",
    "validate_storage_key",
    "validate_upload",
    "verify_ticket",
]
