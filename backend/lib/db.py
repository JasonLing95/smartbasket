# lib/db.py
import os
import psycopg2
from psycopg2 import pool
from urllib.parse import urlparse, quote
import re
import logging

logger = logging.getLogger(__name__)

_connection_pool = None


def get_db_pool():
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise ValueError("[-] CRITICAL: DATABASE_URL environment variable is missing.")

    try:
        # 🛡️ AUTOMATIC ENCODING SHIELD 🛡️
        # If the password has special characters and isn't encoded, let's catch it here.
        # This matches standard connection string anatomy: postgresql://user:pass@host:port/db
        match = re.match(
            r"(postgresql://)([^:]+):(.*)@([^@/]+:[0-9]+/[^@?]+)", database_url
        )

        if match:
            protocol, username, raw_password, trailing_uri = match.groups()

            # Check if the password contains unencoded symbols that break urlparse
            if (
                any(char in raw_password for char in ["@", "#", ":", "/", "?", "="])
                and "%" not in raw_password
            ):
                logger.info(
                    "⚙️ Unencoded special characters detected in DATABASE_URL password. Auto-healing string configurations..."
                )
                encoded_password = quote(raw_password)
                database_url = f"{protocol}{username}:{encoded_password}@{trailing_uri}"

        # Proceed to parse the safely prepared/healed connection string
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
