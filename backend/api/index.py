# api/index.py
from dotenv import load_dotenv

load_dotenv()

import os
import math
import hashlib
import secrets
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks, File, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from lib.db import execute_query, get_db_pool
from lib.matcher import find_canonical_item
from lib.llm_matcher import resolve_unmatched_entity
import asyncio
from fastapi.responses import StreamingResponse

APP_ENV = os.getenv("APP_ENV", "development")

app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Cryptographic Helper Functions ---


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
    )
    return f"{salt}:{key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hex_key = stored_hash.split(":")
        key = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
        )
        return secrets.compare_digest(key.hex(), hex_key)
    except Exception:
        return False


def get_user_from_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Authorization credentials missing."
        )
    token = authorization.replace("Bearer ", "").strip()
    res = execute_query(
        "SELECT username FROM user_sessions WHERE token = %s;", (token,)
    )
    if not res:
        raise HTTPException(status_code=401, detail="Session expired or token invalid.")
    return res[0][0]


def get_optional_user(authorization: Optional[str]) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "").strip()
    res = execute_query(
        "SELECT username FROM user_sessions WHERE token = %s;", (token,)
    )
    return res[0][0] if res else None


# --- Data Validation Schemas ---


class UserAuthPayload(BaseModel):
    username: str
    email: Optional[str] = None
    password: str


class ReceiptItem(BaseModel):
    raw_string: str
    price: float


class ReceiptPayload(BaseModel):
    store_name: str
    items: List[ReceiptItem]


class AddBasketItemPayload(BaseModel):
    master_item_id: str
    preferred_store: str = "Tesco"
    quantity: int = 1


class UpdateQuantityPayload(BaseModel):
    master_item_id: str
    action: str


# --- Real-Time SSE Infrastructure ---
active_connections = {}


async def notify_user(username: str, message: str):
    """Pushes a message to a specific user's active SSE stream."""
    if username in active_connections:
        await active_connections[username].put(message)


@app.get("/api/stream/alerts")
async def sse_alerts(username: str):
    """Maintains a persistent connection to the frontend to push live alerts."""
    if username not in active_connections:
        active_connections[username] = asyncio.Queue()

    async def event_generator():
        try:
            while True:
                # Wait asynchronously until a new message is pushed to this user's queue
                msg = await active_connections[username].get()
                yield f"data: {msg}\n\n"
        except asyncio.CancelledError:
            # Clean up the connection if the user closes the browser
            active_connections.pop(username, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Core Processing Engines ---


async def process_alerts_background(
    item_ids: List[str], store_name: str, new_prices: List[float]
):
    pool = get_db_pool()
    conn = pool.getconn()
    import sys  # Used to force-flush background terminal logs

    try:
        with conn.cursor() as cursor:
            for item_id, price in zip(item_ids, new_prices):
                # ✅ FIXED: Removed 'preferred_store != %s' so same-store price drops trigger alerts too!
                basket_query = "SELECT DISTINCT user_id, preferred_store, last_known_price FROM user_baskets WHERE master_item_id = %s::uuid AND last_known_price > %s;"
                cursor.execute(basket_query, (item_id, price))

                matches = cursor.fetchall()
                if not matches:
                    print(
                        f"🔍 No users found tracking item {item_id} at a price higher than £{price:.2f}."
                    )
                    sys.stdout.flush()

                for user in matches:
                    username = user[0]
                    print(
                        f"📢 ALERT: SQL Trigger matched! Pushing live notification to {username}..."
                    )
                    sys.stdout.flush()

                    # ⚡ Fire the message down the persistent HTTP stream!
                    live_message = f"🔥 Live Price Drop: {store_name} just scanned an item on your list for £{price:.2f}!"
                    await notify_user(username, live_message)

    except Exception as e:
        print(f"Background alert failure: {e}")
        sys.stdout.flush()
    finally:
        pool.putconn(conn)


def execute_receipt_ingestion_hash_upgraded(
    user_id: Optional[str],
    store_name: str,
    items: list,
    file_hash: str,
    background_tasks: BackgroundTasks,
    extracted_total: float,
    receipt_date: Optional[str] = None,
):
    # Trust the safeguarded total directly from the OCR dictionary
    total_spent = extracted_total

    store_name_clean = store_name.strip()

    if store_name_clean.lower() == "lidl":
        store_name_clean = "Lidl"
    elif store_name_clean.lower() in ["tesco", "tesco extra"]:
        store_name_clean = "Tesco"
    elif store_name_clean.lower() == "aldi":
        store_name_clean = "Aldi"

    if receipt_date:
        # Normalize messy/UK dates to clean ISO YYYY-MM-DD before SQL binding
        normalized_date = None
        for date_format in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y"):
            try:
                normalized_date = datetime.strptime(
                    receipt_date.strip(), date_format
                ).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

        if normalized_date:
            receipt_insert = """
                INSERT INTO receipts (user_id, store_name, total_spent, image_hash, date)
                VALUES (%s, %s, %s, %s, %s::timestamp) RETURNING id;
            """
            receipt_rows = execute_query(
                receipt_insert,
                (
                    user_id,
                    store_name_clean,
                    total_spent,
                    file_hash,
                    f"{normalized_date} 12:00:00",
                ),
                commit=True,
                fetch_res=True,
            )
        else:
            receipt_insert = """
                INSERT INTO receipts (user_id, store_name, total_spent, image_hash)
                VALUES (%s, %s, %s, %s) RETURNING id;
            """
            receipt_rows = execute_query(
                receipt_insert,
                (user_id, store_name_clean, total_spent, file_hash),
                commit=True,
                fetch_res=True,
            )
    else:
        receipt_insert = """
            INSERT INTO receipts (user_id, store_name, total_spent, image_hash)
            VALUES (%s, %s, %s, %s) RETURNING id;
        """
        receipt_rows = execute_query(
            receipt_insert,
            (user_id, store_name_clean, total_spent, file_hash),
            commit=True,
            fetch_res=True,
        )

    receipt_id = receipt_rows[0][0]
    inserted_item_ids = []
    new_prices = []

    for item in items:
        raw_string = item.get("raw_string", "")

        if not raw_string:
            print("⚠️ Ingestion blocked an empty string stub. Skipping this row.")
            continue

        # ✅ FIXED: Extract the new loyalty-aware properties from the OCR engine
        unit_price = float(item.get("unit_price", 0))
        base_price = float(item.get("base_price", unit_price))
        loyalty_price = item.get("loyalty_price")
        if loyalty_price is not None:
            loyalty_price = float(loyalty_price)
        discount_type = item.get("discount_type")
        quantity = int(item.get("quantity", 1))

        matched_item = find_canonical_item(raw_string)
        master_item_id = None

        if matched_item:
            master_item_id = matched_item["master_item_id"]
        else:
            ai_resolution = resolve_unmatched_entity(raw_string)
            ai_action = ai_resolution.get("action")

            if ai_action == "skip":
                print(f"⚠️ AI Matcher skipped '{raw_string}'. Dropping from ingestion.")
                continue

            ai_match_id = ai_resolution.get("matched_item_id")
            if ai_action == "match" and ai_match_id:
                master_item_id = ai_match_id
            elif ai_action == "create" or (ai_action == "match" and not ai_match_id):
                clean_name = ai_resolution.get("cleaned_name", raw_string)
                category = ai_resolution.get("category", "Groceries")

                # ✅ Optional: Also grab the size metrics if your LLM successfully parsed them
                size_value = ai_resolution.get("size_value")
                size_unit = ai_resolution.get("size_unit")

                import uuid

                new_uuid = str(uuid.uuid4())

                # Update this if you added size_value and size_unit to master_items insert
                execute_query(
                    "INSERT INTO master_items (id, canonical_name, category, is_verified) VALUES (%s::uuid, %s, %s, FALSE);",
                    (new_uuid, clean_name, category),
                    commit=True,
                )
                master_item_id = new_uuid

        if not master_item_id:
            continue

        inserted_item_ids.append(master_item_id)
        new_prices.append(unit_price)

        line_total_cost = unit_price * quantity
        execute_query(
            "INSERT INTO receipt_items (receipt_id, master_item_id, price) VALUES (%s, %s::uuid, %s);",
            (receipt_id, master_item_id, line_total_cost),
            commit=True,
        )

        # ✅ FIXED: Insert into price_history using the correct column names (removed ON CONFLICT)
        execute_query(
            """
            INSERT INTO price_history (master_item_id, store_name, base_price, loyalty_price, discount_type, raw_name, scanned_at) 
            VALUES (%s::uuid, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
            """,
            (
                master_item_id,
                store_name_clean,
                base_price,
                loyalty_price,
                discount_type,
                raw_string,
            ),
            commit=True,
        )

        # Automatically add item quantities into user baskets if logged in
        if user_id:
            execute_query(
                """
                INSERT INTO user_baskets (user_id, master_item_id, preferred_store, last_known_price, quantity) 
                VALUES (%s, %s::uuid, %s, %s, %s) 
                ON CONFLICT (user_id, master_item_id) DO UPDATE SET quantity = user_baskets.quantity + EXCLUDED.quantity;
                """,
                (user_id, master_item_id, store_name_clean, unit_price, quantity),
                commit=True,
            )

    if inserted_item_ids:
        background_tasks.add_task(
            process_alerts_background, inserted_item_ids, store_name_clean, new_prices
        )

    return receipt_id, len(inserted_item_ids)


# --- Authentication Routers ---


@app.post("/api/auth/register")
def register_account(payload: UserAuthPayload):
    if not payload.username or not payload.email or not payload.password:
        raise HTTPException(
            status_code=400, detail="All enrollment validation terms must be filled."
        )
    if execute_query(
        "SELECT username FROM users WHERE username = %s OR email = %s;",
        (payload.username, payload.email),
    ):
        raise HTTPException(
            status_code=400,
            detail="Username identifier or email string already registered.",
        )

    hashed = hash_password(payload.password)
    execute_query(
        "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s);",
        (payload.username, payload.email, hashed),
        commit=True,
    )

    session_token = secrets.token_urlsafe(48)
    execute_query(
        "INSERT INTO user_sessions (token, username) VALUES (%s, %s);",
        (session_token, payload.username),
        commit=True,
    )

    return {
        "status": "success",
        "token": session_token,
        "username": payload.username,
        "message": "Profile created cleanly.",
    }


@app.post("/api/auth/login")
def login_authenticate(payload: UserAuthPayload):
    user_record = execute_query(
        "SELECT password_hash FROM users WHERE username = %s;", (payload.username,)
    )

    # ◄── FIX: Separate specific "Not Found" logic to trigger frontend auto-switch
    if not user_record:
        raise HTTPException(status_code=404, detail="User not found.")

    if not verify_password(payload.password, user_record[0][0]):
        raise HTTPException(status_code=401, detail="Invalid password.")

    session_token = secrets.token_urlsafe(48)
    execute_query(
        "INSERT INTO user_sessions (token, username) VALUES (%s, %s);",
        (session_token, payload.username),
        commit=True,
    )
    return {"status": "success", "token": session_token, "username": payload.username}


@app.post("/api/auth/logout")
def logout_session(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        execute_query(
            "DELETE FROM user_sessions WHERE token = %s;",
            (authorization.replace("Bearer ", "").strip(),),
            commit=True,
        )
    return {"status": "success"}


# --- Secured Application Routers ---


@app.post("/api/receipts/upload")
async def upload_real_receipt(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    user_id = get_optional_user(authorization)
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # 1. ENVIRONMENT AWARE PATTERN - LOCAL DEV RUNS INLINE
    if APP_ENV == "development":
        print("┌────────────────────────────────────────────────────────┐")
        print("│ 💻 LOCAL TESTING DETECTED: Running Synchronous OCR     │")
        print("└────────────────────────────────────────────────────────┘")

        from lib.ocr_engine import extract_receipt_data

        extracted = extract_receipt_data(file_bytes)
        receipt_id, processed_count = execute_receipt_ingestion_hash_upgraded(
            user_id=user_id,
            store_name=extracted["store_name"],
            items=extracted["items"],
            file_hash=file_hash,
            background_tasks=background_tasks,
            extracted_total=extracted.get("total", 0.0),
            receipt_date=extracted.get("date"),
        )
        return {
            "status": "success",
            "mode": "local_synchronous",
            "store_detected": extracted["store_name"],
            "receipt_id": str(receipt_id),
            "cached": False,
        }

    # 2. ASYNCHRONOUS DECOUPLED INFRASTRUCTURE - PRODUCTION RUNS QUEUED
    else:
        try:
            # Short-circuit on duplicate files directly inside database records
            existing_receipt = execute_query(
                "SELECT id, store_name FROM receipts WHERE image_hash = %s;",
                (file_hash,),
            )
            if existing_receipt:
                return {
                    "status": "success",
                    "message": "Duplicate receipt cached instantly.",
                    "store_detected": existing_receipt[0][1],
                    "receipt_id": str(existing_receipt[0][0]),
                    "cached": True,
                }

            # Connect to AWS ecosystem natively using system-level environment vars
            import boto3
            import json

            s3 = boto3.client("s3")
            sqs = boto3.client("sqs", region_name=os.getenv("AWS_REGION", "eu-west-2"))

            bucket_name = os.getenv("AWS_STORAGE_BUCKET_NAME", "smartbasket-receipts")
            queue_url = os.getenv("AWS_SQS_QUEUE_URL")
            s3_key = f"receipts/{file_hash}.jpg"

            # Offload file stream straight to S3 bucket storage parameters
            s3.put_object(Bucket=bucket_name, Key=s3_key, Body=file_bytes)

            # Package lightweight tracking metadata payload
            job_payload = {"s3_key": s3_key, "user_id": user_id, "file_hash": file_hash}

            # Enqueue execution job into SQS cluster instances
            sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(job_payload))

            return {
                "status": "success",
                "mode": "production_async_queue",
                "message": "Receipt uploaded successfully. Processing has been queued.",
                "cached": False,
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Async queue fail: {str(e)}")


@app.get("/api/receipts/{receipt_id}")
def get_receipt_details(receipt_id: str, authorization: Optional[str] = Header(None)):
    try:
        meta_query = "SELECT store_name, total_spent, TO_CHAR(date, 'DD Mon YYYY HH24:MI') FROM receipts WHERE id = %s;"
        meta = execute_query(meta_query, (receipt_id,))
        if not meta:
            raise HTTPException(status_code=404, detail="Receipt not found.")

        items_query = """
            SELECT m.canonical_name, m.category, ri.price
            FROM receipt_items ri
            JOIN master_items m ON ri.master_item_id = m.id
            WHERE ri.receipt_id = %s;
        """
        items = execute_query(items_query, (receipt_id,))

        return {
            "store_name": meta[0][0],
            "total_spent": float(meta[0][1]),
            "date": meta[0][2],
            "items": [
                {"name": i[0], "category": i[1], "price": float(i[2])} for i in items
            ],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch receipt details: {e}"
        )


@app.get("/api/basket/compare")
async def compare_basket(
    friction_penalty: float = 0.0, authorization: Optional[str] = Header(None)
):
    user_id = get_user_from_token(authorization)
    query = """
        SELECT 
        ub.master_item_id, 
        m.canonical_name, 
        m.category, 
        m.size_value,   
        m.size_unit,    
        ub.quantity, 
        ph.store_name, 
        ph.base_price,  
        ph.loyalty_price,
        COALESCE(ph.loyalty_price, ph.base_price) AS effective_price,
        ph.discount_type
    FROM user_baskets ub 
    JOIN master_items m ON ub.master_item_id = m.id 
    LEFT JOIN (
        SELECT DISTINCT ON (master_item_id, store_name) *
        FROM price_history
        ORDER BY master_item_id, store_name, scanned_at DESC
    ) ph ON ub.master_item_id = ph.master_item_id 
    WHERE ub.user_id = %s;
    """
    try:
        rows = execute_query(query, (user_id,))
        if not rows:
            return {"user_id": user_id, "basket_options": [], "optimized_split": None}

        items_matrix = {}
        for row in rows:
            m_item_id = row[0]
            name = row[1]
            category = row[2]
            # Indexes 3 and 4 are size_value and size_unit
            quantity = row[5]
            store = row[6]
            # Indexes 7 and 8 are base_price and loyalty_price
            price = row[9]  # The COALESCE effective_price

            if m_item_id not in items_matrix:
                items_matrix[m_item_id] = {
                    "id": str(m_item_id),
                    "name": name,
                    "category": category,
                    "quantity": quantity,
                    "prices": {},
                }
            if store and price is not None:
                items_matrix[m_item_id]["prices"][store] = float(price)

        all_stores = {row[6] for row in rows if row[6]}  # Updated index for store_name
        single_store_options = []

        for store in all_stores:
            total_cost, items_matched, matched_items_detailed = 0.0, 0, []
            for item_id, item in items_matrix.items():
                if store in item["prices"]:
                    total_cost += item["prices"][store] * item["quantity"]
                    items_matched += 1
                    matched_items_detailed.append(
                        {
                            "id": str(item_id),
                            "name": item["name"],
                            "quantity": item["quantity"],
                        }
                    )
                else:
                    pass
            single_store_options.append(
                {
                    "store_name": store,
                    "total_cost": round(total_cost, 2),
                    "items_counted": items_matched,
                    "items_detailed": matched_items_detailed,
                }
            )

        single_store_options.sort(key=lambda x: (-x["items_counted"], x["total_cost"]))
        cheapest_single_cost = (
            single_store_options[0]["total_cost"] if single_store_options else 0.0
        )

        allocated_items, visited_stores, raw_items_subtotal = [], set(), 0.0
        for item_id, item in items_matrix.items():
            if not item["prices"]:
                continue
            best_store = min(item["prices"], key=item["prices"].get)
            line_total = item["prices"][best_store] * item["quantity"]
            raw_items_subtotal += line_total
            visited_stores.add(best_store)
            allocated_items.append(
                {
                    "item_name": item["name"],
                    "allocated_store": best_store,
                    "total_cost": round(line_total, 2),
                }
            )

        applied_penalty = max(0, len(visited_stores) - 1) * friction_penalty
        effective_split_cost = raw_items_subtotal + applied_penalty

        if effective_split_cost >= cheapest_single_cost:
            best = single_store_options[0]
            optimized_split = {
                "strategy_meta": f"Consolidated ({best['store_name']})",
                "items_subtotal": best["total_cost"],
                "penalty_applied": 0.0,
                "total_effective_cost": best["total_cost"],
                "stores_visited": [best["store_name"]],
                "net_savings": 0.0,
                "allocations": [
                    {
                        "item_name": i["name"],
                        "allocated_store": best["store_name"],
                        "total_cost": round(
                            i["prices"].get(best["store_name"], 0.0) * i["quantity"], 2
                        ),
                    }
                    for i in items_matrix.values()
                ],
            }
        else:
            optimized_split = {
                "strategy_meta": "Smart Multi-Store Split",
                "items_subtotal": round(raw_items_subtotal, 2),
                "penalty_applied": round(applied_penalty, 2),
                "total_effective_cost": round(effective_split_cost, 2),
                "stores_visited": list(visited_stores),
                "net_savings": round(cheapest_single_cost - effective_split_cost, 2),
                "allocations": allocated_items,
            }
        return {
            "user_id": user_id,
            "basket_options": single_store_options,
            "optimized_split": optimized_split,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Optimization matrix logic fault: {str(e)}"
        )


@app.get("/api/alerts")
async def get_active_alerts(authorization: Optional[str] = Header(None)):
    user_id = get_optional_user(authorization)
    try:
        if not user_id:
            query = """
                WITH LatestPrices AS (
                    SELECT DISTINCT ON (master_item_id, store_name) 
                           master_item_id, store_name, COALESCE(loyalty_price, base_price) AS price
                    FROM price_history ORDER BY master_item_id, store_name, scanned_at DESC
                ),
                GlobalGaps AS (
                    SELECT DISTINCT ON (m.canonical_name)
                        m.canonical_name, p1.store_name AS current_store, p2.store_name AS cheaper_store, 
                        p1.price AS old_price, p2.price AS new_price, (p1.price - p2.price) AS savings
                    FROM LatestPrices p1 
                    JOIN LatestPrices p2 ON p1.master_item_id = p2.master_item_id AND p1.price > p2.price AND p1.store_name != p2.store_name
                    JOIN master_items m ON p1.master_item_id = m.id 
                    ORDER BY m.canonical_name, (p1.price - p2.price) DESC
                )
                SELECT * FROM GlobalGaps ORDER BY savings DESC LIMIT 6;
            """
            results = execute_query(query)
        else:
            query = """
                WITH LatestPrices AS (
                    SELECT DISTINCT ON (master_item_id, store_name) 
                           master_item_id, store_name, COALESCE(loyalty_price, base_price) AS price
                    FROM price_history ORDER BY master_item_id, store_name, scanned_at DESC
                ),
                ItemGaps AS (
                    SELECT DISTINCT ON (m.canonical_name)
                        m.canonical_name, p1.store_name AS current_store, p2.store_name AS cheaper_store, 
                        p1.price AS old_price, p2.price AS new_price, (p1.price - p2.price) * ub.quantity AS savings
                    FROM user_baskets ub 
                    JOIN master_items m ON ub.master_item_id = m.id 
                    JOIN LatestPrices p1 ON m.id = p1.master_item_id
                    JOIN LatestPrices p2 ON m.id = p2.master_item_id AND p1.price > p2.price AND p1.store_name != p2.store_name
                    WHERE ub.user_id = %s 
                    ORDER BY m.canonical_name, ((p1.price - p2.price) * ub.quantity) DESC
                )
                SELECT * FROM ItemGaps ORDER BY savings DESC LIMIT 6;
            """
            results = execute_query(query, (user_id,))

        return {
            "active_alerts": [
                {
                    "item_name": r[0],
                    "current_store": r[1],
                    "cheaper_store": r[2],
                    "old_price": float(r[3]),
                    "new_price": float(r[4]),
                    "potential_savings": float(r[5]),
                }
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Alert compilation error: {str(e)}"
        )


# api/index.py
@app.get("/api/catalog/search")
def search_catalog(q: str = ""):
    if not q:
        return {"results": []}
    try:
        query = """
            SELECT m.id, m.canonical_name, m.category, COUNT(DISTINCT ph.store_name) AS variant_count, similarity(m.canonical_name, %s) as score
            FROM master_items m
            LEFT JOIN price_history ph ON m.id = ph.master_item_id
            WHERE m.canonical_name ILIKE %s
            GROUP BY m.id, m.canonical_name, m.category
            ORDER BY score DESC, variant_count DESC, m.canonical_name ASC LIMIT 12;
        """
        rows = execute_query(query, (q, f"%{q}%"))
        return {
            "results": [
                {
                    "id": str(r[0]),
                    "canonical_name": r[1],
                    "category": r[2],
                    "variant_count": int(r[3]),
                }
                for r in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Catalog filter failure: {e}")


@app.get("/api/catalog/all")
def get_all_catalog(page: int = 1, limit: int = 10):
    try:
        offset = (page - 1) * limit
        count_row = execute_query("SELECT COUNT(*) FROM master_items;")
        total_count = count_row[0][0] if count_row else 0
        query = """
            SELECT m.id, m.canonical_name, m.category, COUNT(DISTINCT ph.store_name) AS variant_count
            FROM master_items m
            LEFT JOIN price_history ph ON m.id = ph.master_item_id
            GROUP BY m.id, m.canonical_name, m.category
            ORDER BY variant_count DESC, m.canonical_name ASC LIMIT %s OFFSET %s;
        """
        rows = execute_query(query, (limit, offset))
        return {
            "results": [
                {
                    "id": str(r[0]),
                    "canonical_name": r[1],
                    "category": r[2],
                    "variant_count": int(r[3]),
                }
                for r in rows
            ],
            "total_count": total_count,
            "page": page,
            "total_pages": math.ceil(total_count / limit) if total_count > 0 else 1,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Catalog fetch failure: {e}")


@app.get("/api/catalog/item/{item_id}/variants")
def get_item_store_variants(item_id: str):
    try:
        query = """
            SELECT store_name, COALESCE(loyalty_price, base_price), raw_name, TO_CHAR(scanned_at, 'DD Mon YYYY')
            FROM (
                SELECT DISTINCT ON (store_name) * FROM price_history
                WHERE master_item_id = %s::uuid ORDER BY store_name, scanned_at DESC
            ) latest
            ORDER BY COALESCE(loyalty_price, base_price) ASC;
        """
        rows = execute_query(query, (item_id,))
        return {
            "variants": [
                {
                    "store_name": r[0],
                    "price": float(r[1]),
                    "raw_name": r[2] or "Standard",
                    "updated_at": r[3],
                }
                for r in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch variants: {e}")


@app.post("/api/basket/add")
def add_to_basket(
    payload: AddBasketItemPayload, authorization: Optional[str] = Header(None)
):
    user_id = get_user_from_token(authorization)
    try:
        query = """
            INSERT INTO user_baskets (user_id, master_item_id, preferred_store, last_known_price, quantity) 
            VALUES (
                %s, 
                %s::uuid, 
                %s, 
                (SELECT COALESCE(MIN(COALESCE(loyalty_price, base_price)), 1.50) FROM price_history WHERE master_item_id = %s::uuid), 
                %s
            ) 
            ON CONFLICT (user_id, master_item_id) DO UPDATE SET quantity = user_baskets.quantity + EXCLUDED.quantity;
        """
        execute_query(
            query,
            (
                user_id,
                payload.master_item_id,
                payload.preferred_store,
                payload.master_item_id,
                payload.quantity,
            ),
            commit=True,
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Basket mutation failure: {e}")


@app.get("/api/basket/items")
async def get_basket_items(authorization: Optional[str] = Header(None)):
    user_id = get_user_from_token(authorization)
    query = """
        SELECT m.id, m.canonical_name, m.category, ub.quantity, ph.store_name, COALESCE(ph.loyalty_price, ph.base_price), ph.scanned_at 
        FROM user_baskets ub 
        JOIN master_items m ON ub.master_item_id = m.id 
        LEFT JOIN (
            SELECT DISTINCT ON (master_item_id, store_name) *
            FROM price_history
            ORDER BY master_item_id, store_name, scanned_at DESC
        ) ph ON ub.master_item_id = ph.master_item_id 
        WHERE ub.user_id = %s;
    """
    try:
        rows = execute_query(query, (user_id,))
        items_map, stores = {}, set()
        now = datetime.now()

        def calc_conf(lu):
            if not lu:
                return 0
            if isinstance(lu, str):
                try:
                    lu = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                except:
                    return 0
            if hasattr(lu, "tzinfo") and lu.tzinfo:
                lu = lu.replace(tzinfo=None)
            return int(max(10, 100 - ((now - lu).days * 3)))

        for row in rows:
            row_id, name, cat, qty, store_name, price, updated_at = row
            item_id_str = str(row_id)
            if item_id_str not in items_map:
                items_map[item_id_str] = {
                    "id": item_id_str,
                    "name": name,
                    "category": cat,
                    "quantity": qty,
                    "prices": {},
                }
            if store_name and price is not None:
                stores.add(store_name)
                items_map[item_id_str]["prices"][store_name] = {
                    "price": float(price),
                    "confidence": calc_conf(updated_at),
                }

        return {
            "stores": sorted(list(stores)) if stores else ["Aldi", "Tesco"],
            "items": list(items_map.values()),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Matrix compute logic fault: {str(e)}"
        )


@app.post("/api/basket/update")
def update_basket_quantity(
    payload: UpdateQuantityPayload, authorization: Optional[str] = Header(None)
):
    user_id = get_user_from_token(authorization)
    try:
        if payload.action == "increment":
            execute_query(
                "UPDATE user_baskets SET quantity = quantity + 1 WHERE user_id = %s AND master_item_id = %s::uuid;",
                (user_id, payload.master_item_id),
                commit=True,
            )
        elif payload.action == "decrement":
            execute_query(
                "UPDATE user_baskets SET quantity = quantity - 1 WHERE user_id = %s AND master_item_id = %s::uuid AND quantity > 1;",
                (user_id, payload.master_item_id),
                commit=True,
            )
        elif payload.action == "delete":
            execute_query(
                "DELETE FROM user_baskets WHERE user_id = %s AND master_item_id = %s::uuid;",
                (user_id, payload.master_item_id),
                commit=True,
            )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed transaction context: {e}")


@app.get("/api/receipts")
def get_receipt_history(authorization: Optional[str] = Header(None)):
    user_id = get_user_from_token(authorization)
    try:
        # ◄── FIX: Added a JOIN to count the items dynamically per receipt
        query = """
            SELECT r.id, r.store_name, r.total_spent, TO_CHAR(r.date, 'DD Mon YYYY HH24:MI'), COUNT(ri.id)
            FROM receipts r
            LEFT JOIN receipt_items ri ON r.id = ri.receipt_id
            WHERE r.user_id = %s
            GROUP BY r.id, r.store_name, r.total_spent, r.date
            ORDER BY r.date DESC;
        """
        rows = execute_query(query, (user_id,))
        return {
            "receipts": [
                {
                    "id": str(r[0]),
                    "store_name": r[1],
                    "total_spent": float(r[2]),
                    "date": r[3],
                    "items_count": int(r[4]),
                }
                for r in rows
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ledger compile crash: {e}")


@app.get("/api/analytics/spend")
async def get_spend_analytics(authorization: Optional[str] = Header(None)):
    user_id = get_user_from_token(authorization)
    try:
        # Fetch strictly the real aggregated data for this specific user
        query = """
            SELECT TO_CHAR(date, 'Mon'), SUM(total_spent), COUNT(id) 
            FROM receipts 
            WHERE user_id = %s 
            GROUP BY TO_CHAR(date, 'Mon'), DATE_TRUNC('month', date) 
            ORDER BY DATE_TRUNC('month', date) ASC;
        """
        rows = execute_query(query, (user_id,))

        # Build the dynamic timeseries directly from the database rows
        time_series = [
            {"month": row[0], "Spend": float(row[1]), "Receipts": int(row[2])}
            for row in rows
        ]

        return {"time_series": time_series}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Analytics compute fault: {str(e)}"
        )
