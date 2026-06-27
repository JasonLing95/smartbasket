# lib/db.py
import os
import psycopg2
from psycopg2 import pool
from urllib.parse import urlparse, quote, unquote
import re
import logging

logger = logging.getLogger(__name__)

_connection_pool = None


def get_db_pool():
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool

    # --- 1. DISCRETE VARIABLES ---
    db_host = os.environ.get("DB_HOST")
    db_user = os.environ.get("DB_USER", "postgres")
    db_pass = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME", "postgres")
    db_port = os.environ.get("DB_PORT", "5432")

    try:
        if db_host and db_pass:
            logger.info(
                f"🔧 DB Init [Discrete]: Host={db_host} | User={db_user} | DB={db_name} | PassLength={len(db_pass)}"
            )
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

        # 🛡️ AUTOMATIC ENCODING SHIELD 🛡️
        match = re.match(
            r"(postgresql://)([^:]+):(.*)@([^@/]+:[0-9]+/[^@?]+)", database_url
        )
        if match:
            protocol, username, raw_password, trailing_uri = match.groups()
            if (
                any(char in raw_password for char in ["@", "#", ":", "/", "?", "="])
                and "%" not in raw_password
            ):
                logger.info(
                    "⚙️ Unencoded special characters detected in DATABASE_URL. Auto-healing..."
                )
                encoded_password = quote(raw_password)
                database_url = f"{protocol}{username}:{encoded_password}@{trailing_uri}"

        parsed_url = urlparse(database_url)

        # 🔑 THE CRITICAL FIX: Decode the password back to raw text before giving it to PostgreSQL
        final_password = unquote(parsed_url.password) if parsed_url.password else None
        final_host = parsed_url.hostname
        final_user = parsed_url.username
        final_db = parsed_url.path.lstrip("/")

        # 🔍 ENHANCED VISIBILITY LOGGING
        # This will tell you exactly what Vercel is seeing without leaking the password
        logger.info(
            f"🔧 DB Init [URL]: Host={final_host} | User={final_user} | DB={final_db} | PassLength={len(final_password) if final_password else 0} | Contains '%': {'%' in final_password if final_password else False}"
        )

        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=final_host,
            port=parsed_url.port or 5432,
            user=final_user,
            password=final_password,
            database=final_db,
            sslmode=(
                "require" if final_host and "amazonaws.com" in final_host else "prefer"
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
