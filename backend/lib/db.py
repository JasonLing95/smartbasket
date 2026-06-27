# lib/db.py
import os
import psycopg2
from psycopg2 import pool
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

_connection_pool = None


def get_db_pool():
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool

    # --- 1. DISCRETE VARIABLES (Recommended: No URL encoding needed) ---
    db_host = os.environ.get("DB_HOST")
    db_user = os.environ.get("DB_USER", "postgres")
    db_pass = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME", "postgres")
    db_port = os.environ.get("DB_PORT", "5432")

    try:
        # If the explicit host and password exist, use the raw connection method
        if db_host and db_pass:
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_pass,
                database=db_name,
                sslmode="require" if "amazonaws.com" in db_host else "prefer",
            )
            return _connection_pool

        # --- 2. FALLBACK: URL PARSING ---
        database_url = os.environ.get("DATABASE_URL")

        if not database_url:
            raise ValueError(
                "[-] CRITICAL: Database credentials missing. Provide DB_HOST/DB_PASSWORD or DATABASE_URL."
            )

        parsed_url = urlparse(database_url)
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=parsed_url.hostname,
            port=parsed_url.port or 5432,
            user=parsed_url.username,
            password=parsed_url.password,
            database=parsed_url.path.lstrip("/"),
            sslmode=(
                "require"
                if parsed_url.hostname and "amazonaws.com" in parsed_url.hostname
                else "prefer"
            ),
        )
        return _connection_pool

    except Exception as e:
        logger.error(
            f"❌ Connection pool initialization engine failed: {e}", exc_info=True
        )
        raise e


def execute_query(query, params=None, commit=False, fetch_res=False):
    pool_instance = get_db_pool()
    conn = pool_instance.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if commit:
                res = cursor.fetchall() if fetch_res else True
                conn.commit()
                return res
            return cursor.fetchall()
    except Exception as e:
        logger.error(f"❌ Database query execution failed: {e}", exc_info=True)
        if commit:
            conn.rollback()
        raise e
    finally:
        pool_instance.putconn(conn)
