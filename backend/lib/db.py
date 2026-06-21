# lib/db.py
import os
import psycopg2
from urllib.parse import urlparse

_connection_pool = None


def get_db_pool():
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise ValueError("[-] CRITICAL: DATABASE_URL environment variable is missing.")

    # Parse the URL string into the components psycopg2 needs
    parsed_url = urlparse(database_url)

    # 2. Instantiate the connection pool
    try:
        _connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=parsed_url.hostname,
            port=parsed_url.port or 5432,
            user=parsed_url.username,
            password=parsed_url.password,
            database=parsed_url.path.lstrip("/"),
            sslmode="require" if "amazonaws.com" in parsed_url.hostname else "prefer",
        )
        return _connection_pool
    except Exception as e:
        print(f"❌ Connection pool initialization engine failed: {e}")
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
        if commit:
            conn.rollback()
        raise e
    finally:
        pool_instance.putconn(conn)
