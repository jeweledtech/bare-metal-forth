"""Deterministic extractor for Windows MUI (Multilingual User Interface) files.

NOT IMPLEMENTED — no real .mui fixture available for validation.
See schema/mui.schema.json for the expected output shape.

When a real .mui fixture (e.g. i8042prt.sys.mui from an en-US directory)
becomes available, implement the extraction logic here:
  - Parse MUI signature resource (language_id, fallback, checksums)
  - Inventory resource types (RT_STRING, RT_DIALOG, RT_MESSAGETABLE, etc.)
  - Extract string and message tables
  - Derive parent_binary from filename (strip .mui extension + language dir)
"""

from pathlib import Path


def extract_mui(path: Path) -> dict:
    """Extract MUI resource metadata from a .mui PE file.

    NOT IMPLEMENTED — no real .mui fixture available for validation.
    The router's dispatch path will hit this and get a clear error
    indicating the gap.  Schema documents the expected output shape.

    Re-implement when i8042prt.sys.mui or equivalent becomes available
    for ground-truth validation.
    """
    raise NotImplementedError(
        "MUI extractor deferred: no real .mui fixture available for "
        "validation. See schema/mui.schema.json for expected output shape."
    )
