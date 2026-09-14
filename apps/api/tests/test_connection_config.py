from app.db.session import connection_args_for_database, normalized_database_url


def test_local_database_does_not_force_tls() -> None:
    url = "postgresql+asyncpg://postgres:postgres@localhost:5432/zhibian"
    assert connection_args_for_database(url) == {}


def test_neon_sslmode_is_translated_for_asyncpg() -> None:
    url = "postgresql+asyncpg://user:pass@ep.example.neon.tech/db?sslmode=require"
    assert "sslmode" not in normalized_database_url(url)
    assert "ssl" in connection_args_for_database(url)
