from __future__ import annotations

from collections.abc import Mapping


NORTH_OWNED_TABLES = frozenset(
    {
        "checkpoint_blobs",
        "checkpoint_migrations",
        "checkpoint_writes",
        "checkpoints",
    }
)


def include_dayboard_schema_name(
    name: str | None,
    object_type: str,
    parent_names: Mapping[str, str | None],
) -> bool:
    """Limit Alembic comparison to schema objects owned by Dayboard."""
    del parent_names
    return object_type != "table" or name not in NORTH_OWNED_TABLES
