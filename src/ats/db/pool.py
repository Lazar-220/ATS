from psycopg_pool import ConnectionPool


def create_pool(database_url: str, max_size: int) -> ConnectionPool:
    """Build a pool without connecting, so a process can start while Postgres is still down.

    The caller opens it; `/health` then reports the outage instead of the API failing to boot.
    """
    return ConnectionPool(database_url, min_size=1, max_size=max_size, open=False)
