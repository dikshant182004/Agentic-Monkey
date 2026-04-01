"""Schema-level tests for ORM metadata and model registration."""

from backend.db.models import Base


def test_expected_tables_exist() -> None:
    """Ensures the canonical six-model table set is present."""
    table_names = set(Base.metadata.tables.keys())
    assert table_names == {"users", "agents", "steady_states", "runs", "interactions", "afps"}

