# lib/db.py
import os
import boto3
import psycopg2
from psycopg2 import pool

_connection_pool = None


def get_db_pool():
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool

    host = os.environ.get("PGHOST")
    port = int(os.environ.get("PGPORT", 5432))
    user = os.environ.get("PGUSER")
    dbname = os.environ.get("PGDATABASE", "postgres")
    region = os.environ.get("AWS_REGION")

    # Check if we are running in production on Vercel with an active AWS configuration
    is_production = os.environ.get("AWS_ROLE_ARN") is not None

    if not all([host, user]):
        raise ValueError(
            "Missing critical database environment configurations (PGHOST or PGUSER)."
        )

    # 1. Resolve Password / Authentication Token
    if is_production:
        # High-security IAM passwordless token generation for AWS Aurora
        print(
            "☁️ AWS Environment detected. Generating short-lived IAM database token..."
        )
        rds_client = boto3.client("rds", region_name=region)
        password_or_token = rds_client.generate_db_auth_token(
            DBHostname=host, Port=port, DBUsername=user, Region=region
        )
    else:
        # Local development fallback (Using standard PGPASSWORD environment variable)
        print("💻 Local environment detected. Swapping to local credential string...")
        password_or_token = os.environ.get("PGPASSWORD", "secret")

    # 2. Instantiate the connection pool
    try:
        _connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=host,
            port=port,
            user=user,
            password=password_or_token,
            database=dbname,
            sslmode=(
                "require" if is_production else "prefer"
            ),  # Require SSL in production, accept plain local tcp
        )
        return _connection_pool
    except Exception as e:
        print(f"❌ Connection pool initialization engine failed: {e}")
        raise e


def execute_query(query, params=None, commit=False, fetch_res=False):
    pool = get_db_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if commit:
                # If we need to fetch a returning ID during a commit transaction
                res = cursor.fetchall() if fetch_res else True
                conn.commit()
                return res
            return cursor.fetchall()
    except Exception as e:
        if commit:
            conn.rollback()
        raise e
    finally:
        pool.putconn(conn)
