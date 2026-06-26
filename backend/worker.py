# worker.py
import os
import time
import json
import boto3
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks
from lib.ocr_engine import extract_receipt_data
from lib.db import execute_query
from api.index import execute_receipt_ingestion_hash_upgraded

# Initialize robust logging for the EC2 daemon
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("worker_daemon")

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
QUEUE_URL = os.getenv("AWS_SQS_QUEUE_URL")
BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "smartbasket-receipts")

sqs = boto3.client("sqs", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)


def poll_queue_loop():
    logger.info("🚀 SmartBasket Asynchronous Parsing Daemon is live and polling...")
    bg_tasks = BackgroundTasks()

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,
            )

            if "Messages" not in response:
                continue

            for message in response["Messages"]:
                job_data = json.loads(message["Body"])

                s3_key = job_data["s3_key"]
                user_id = job_data["user_id"]
                file_hash = job_data["file_hash"]

                logger.info(
                    f"📥 [Trace: {file_hash}] Receipt message popped from SQS pipeline. Validating..."
                )

                # 🛡️ CATCH DUPLICATES BEFORE RUNNING OCR 🛡️
                existing_receipt = execute_query(
                    "SELECT id FROM receipts WHERE image_hash = %s LIMIT 1;",
                    (file_hash,),
                )
                if existing_receipt:
                    logger.warning(
                        f"♻️ [Trace: {file_hash}] Duplicate hash detected in queue: {file_hash}. Skipping OCR extraction."
                    )

                    execute_query(
                        "DELETE FROM active_queue_locks WHERE image_hash = %s;",
                        (file_hash,),
                        commit=True,
                    )
                    sqs.delete_message(
                        QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"]
                    )
                    continue

                # Proceed with regular processing if it's unique
                s3_object = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
                file_bytes = s3_object["Body"].read()

                logger.info(
                    f"⚡ [Trace: {file_hash}] Running heavy EasyOCR sequence..."
                )
                start_time = time.time()

                try:
                    extracted = extract_receipt_data(file_bytes)
                    elapsed_time = time.time() - start_time
                    logger.info(
                        f"⏱️ [Trace: {file_hash}] OCR & Engine parsing completed in {elapsed_time:.2f}s"
                    )

                    if extracted and "store_name" in extracted:
                        receipt_id, processed_count = (
                            execute_receipt_ingestion_hash_upgraded(
                                user_id=user_id,
                                store_name=extracted["store_name"],
                                items=extracted.get("items", []),
                                file_hash=file_hash,
                                background_tasks=bg_tasks,
                                extracted_total=extracted.get("total", 0.0),
                                receipt_date=extracted.get("date"),
                            )
                        )

                        if extracted["store_name"] == "REJECTED":
                            logger.warning(
                                f"🛑 [Trace: {file_hash}] Ingestion aborted. Receipt marked as REJECTED."
                            )
                        else:
                            logger.info(
                                f"✅ [Trace: {file_hash}] Ingestion complete. Receipt ID {receipt_id} recorded. Matched {processed_count} items."
                            )
                    else:
                        logger.warning(
                            f"⚠️ [Trace: {file_hash}] OCR execution yielded no payload. Marking as REJECTED to unblock UI."
                        )
                        execute_receipt_ingestion_hash_upgraded(
                            user_id=user_id,
                            store_name="REJECTED",
                            items=[],
                            file_hash=file_hash,
                            background_tasks=bg_tasks,
                            extracted_total=0.0,
                        )
                except Exception as engine_err:
                    logger.error(
                        f"💥 [Trace: {file_hash}] FATAL INNER PARSING CYCLE CRASH: {str(engine_err)}",
                        exc_info=True,
                    )

                execute_query(
                    "DELETE FROM active_queue_locks WHERE image_hash = %s;",
                    (file_hash,),
                    commit=True,
                )

                sqs.delete_message(
                    QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"]
                )

        except Exception as e:
            logger.error(
                f"❌ Worker loop execution encounter error: {str(e)}", exc_info=True
            )
            time.sleep(5)


if __name__ == "__main__":
    poll_queue_loop()
