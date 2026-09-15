from sqlalchemy.engine import URL

from app.db.session import connection_args_for_database, normalized_database_url


def test_local_database_does_not_force_tls() -> None:
    url = "postgresql+asyncpg://postgres:postgres@localhost:5432/zhibian"
    assert connection_args_for_database(url) == {}


def test_postgresql_driver_is_normalized_to_asyncpg() -> None:
    normalized = normalized_database_url("postgresql://user:pass@db.example/db")

    assert isinstance(normalized, URL)
    assert normalized.drivername == "postgresql+asyncpg"


def test_sslmode_is_removed_from_asyncpg_url() -> None:
    url = "postgresql://user:pass@ep.example.neon.tech/db?sslmode=require"
    normalized = normalized_database_url(url)

    assert "sslmode" not in normalized.query
    assert "ssl" in connection_args_for_database(url)


def test_channel_binding_is_removed_from_asyncpg_url() -> None:
    normalized = normalized_database_url(
        "postgresql://user:pass@ep.example.neon.tech/db"
        "?sslmode=require&channel_binding=require"
    )

    assert "channel_binding" not in normalized.query


def test_password_is_not_replaced_with_masked_rendering() -> None:
    normalized = normalized_database_url(
        "postgresql://user:secret@db.example/db"
    )

    assert normalized.password == "secret"
    assert "***" not in normalized.render_as_string(hide_password=False)


def test_special_characters_in_password_are_preserved() -> None:
    normalized = normalized_database_url(
        "postgresql://user:p%40ss%3Aword%2F%E5%AF%86@db.example/db"
    )

    assert normalized.password == "p@ss:word/密"
