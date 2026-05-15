from sqlalchemy.dialects.postgresql import JSONB

from app.storage.base import Base
from app.storage import models  # noqa: F401


def test_orchestrator_core_tables_registered() -> None:
    expected = {
        "root_tasks",
        "agent_tasks",
        "approvals",
        "artifacts",
        "findings",
        "suggested_actions",
        "events",
        "reports",
    }
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_common_columns_exist() -> None:
    for table_name in [
        "root_tasks",
        "agent_tasks",
        "approvals",
        "artifacts",
        "findings",
        "suggested_actions",
        "events",
        "reports",
    ]:
        table = Base.metadata.tables[table_name]
        assert "id" in table.columns
        assert "created_at" in table.columns
        assert "updated_at" in table.columns


def test_jsonb_columns_use_postgres_jsonb() -> None:
    table = Base.metadata.tables["root_tasks"]
    assert isinstance(table.columns["auth_scope"].type, JSONB)

    table = Base.metadata.tables["agent_tasks"]
    assert isinstance(table.columns["request_payload"].type, JSONB)
    assert isinstance(table.columns["response_payload"].type, JSONB)
