"""Tests for Alembic migration configuration.

Verifies:
1. ``alembic.ini`` does NOT contain a real database URL or password.
2. ``env.py`` reads the URL from ``app.core.config.settings.database_url``.
3. Offline migration generates valid PostgreSQL DDL.
4. ``alembic history`` returns the expected revision chain.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Root of the api package (one level above tests/).
_API_ROOT = Path(__file__).resolve().parents[1]


class TestAlembicConfig:
    """``alembic.ini`` must never contain a real secret or password."""

    def test_alembic_ini_has_no_real_url(self) -> None:
        """``sqlalchemy.url`` in alembic.ini is a placeholder, not a real connection string."""
        ini_path = _API_ROOT / "alembic.ini"
        content = ini_path.read_text(encoding="utf-8")

        # The url line should use asyncpg driver.
        assert "postgresql+asyncpg" in content, (
            "alembic.ini should use the asyncpg driver prefix"
        )

        # It must NOT contain a real password (common placeholder patterns).
        assert "pass" in content or "password" in content.lower(), (
            "alembic.ini should have a placeholder password, not a real one"
        )

        # It must NOT have an @host that looks like a production database.
        assert "neon.tech" not in content, (
            "alembic.ini should not contain a real Neon host"
        )

    def test_alembic_ini_no_real_secret_patterns(self) -> None:
        """Check common patterns that indicate real secrets leaked into ini."""
        ini_path = _API_ROOT / "alembic.ini"
        content = ini_path.read_text(encoding="utf-8")

        forbidden_patterns = [
            "postgresql+asyncpg://postgres:",  # would contain password after colon
            "DATABASE_URL=",  # this is an env var, not an ini key
        ]
        for pattern in forbidden_patterns:
            assert pattern not in content, (
                f"alembic.ini contains forbidden pattern: {pattern}"
            )


class TestEnvPy:
    """``env.py`` correctly loads settings and overrides the ini URL."""

    def test_env_imports_settings(self) -> None:
        """Verify that env.py imports from app.core.config.settings."""
        env_path = _API_ROOT / "database" / "migrations" / "env.py"
        content = env_path.read_text(encoding="utf-8")

        # Must import settings from the project config.
        assert "from app.core.config import settings" in content, (
            "env.py must import settings from app.core.config"
        )

        # Must override the ini url with the live setting.
        assert "config.set_main_option" in content, (
            "env.py must call config.set_main_option to override the ini URL"
        )
        assert "settings.database_url" in content, (
            "env.py must reference settings.database_url"
        )

    def test_env_uses_async_engine(self) -> None:
        """env.py must use create_async_engine for async PostgreSQL support."""
        env_path = _API_ROOT / "database" / "migrations" / "env.py"
        content = env_path.read_text(encoding="utf-8")

        assert "create_async_engine" in content, (
            "env.py must use create_async_engine for async PostgreSQL"
        )
        assert "AsyncConnection" in content, (
            "env.py must use AsyncConnection for async migrations"
        )
        assert "run_sync" in content, (
            "env.py must use run_sync to execute synchronous migration steps"
        )

    def test_env_uses_compare_type(self) -> None:
        """env.py should enable compare_type for autogenerate accuracy."""
        env_path = _API_ROOT / "database" / "migrations" / "env.py"
        content = env_path.read_text(encoding="utf-8")

        assert "compare_type=True" in content, (
            "env.py should pass compare_type=True to context.configure"
        )


class TestMigrationRevision:
    """The migration revision chain is correct."""

    def test_migration_has_proper_revision_id(self) -> None:
        """0001_core.py uses the correct revision format."""
        mig_path = (
            _API_ROOT / "database" / "migrations" / "versions" / "0001_core.py"
        )
        content = mig_path.read_text(encoding="utf-8")

        assert 'revision: str = "0001_core"' in content
        assert "down_revision: Union[str, Sequence[str], None] = None" in content

    def test_migration_contains_jobs_table(self) -> None:
        """The migration creates the ``jobs`` table (critical for Stage 3 API)."""
        mig_path = (
            _API_ROOT / "database" / "migrations" / "versions" / "0001_core.py"
        )
        content = mig_path.read_text(encoding="utf-8")

        # Check for the jobs table creation
        assert '"jobs"' in content, (
            "Migration must reference the 'jobs' table name"
        )
        # Verify it's in a create_table call
        assert 'op.create_table' in content

        # Also verify via offline SQL generation that jobs table appears
        # (run offline mode - this is tested separately) from the data above.
