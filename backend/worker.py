# backend/worker.py
import os
import time
import json
import boto3
import hashlib
from fastapi import BackgroundTasks
from lib.ocr_engine import extract_receipt_data
from lib.db import execute_query
from api.index import execute_receipt_ingestion_hash_upgraded

# Initialize system level configuration variables
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
QUEUE_URL = os.getenv("AWS_SQS_QUEUE_URL")
BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "smartbasket-receipts")

sqs = boto3.client("sqs", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)


def poll_queue_loop():
    print("🚀 SmartBasket Asynchronous Parsing Daemon is live and polling...")
    # Initialize a mock background tasks context provider for legacy compatibility
    bg_tasks = BackgroundTasks()

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,  # AWS Long polling optimization saves system credits
            )

            if "Messages" not in response:
                continue

            for message in response["Messages"]:
                print(
                    "📥 Receipt message popped from SQS pipeline. Starting OCR processing..."
                )
                job_data = json.loads(message["Body"])

                s3_key = job_data["s3_key"]
                user_id = job_data["user_id"]
                file_hash = job_data["file_hash"]

                # Fetch raw file payload from S3 infrastructure bucket
                s3_object = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
                file_bytes = s3_object["Body"].read()

                # Call shared library core OCR processing logic
                extracted = extract_receipt_data(file_bytes)

                if extracted and "items" in extracted and extracted["items"]:
                    # Ingest values directly into database parameters
                    receipt_id, processed_count = (
                        execute_receipt_ingestion_hash_upgraded(
                            user_id=user_id,
                            store_name=extracted["store_name"],
                            items=extracted["items"],
                            file_hash=file_hash,
                            background_tasks=bg_tasks,
                            extracted_total=extracted.get("total", 0.0),
                            receipt_date=extracted.get("date"),
                        )
                    )
                    print(
                        f"✅ Ingestion complete. Receipt ID {receipt_id} recorded. Matched {processed_count} items."
                    )
                else:
                    print("⚠️ Image reading execution yielded no parsed text elements.")

                # Drop message upon verified worker consumption cycle completion
                sqs.delete_message(
                    QueueUrl=QUEUE_URL, ReceiptHandle=message["ReceiptHandle"]
                )

        except Exception as e:
            print(f"❌ Worker loop execution encounter error: {str(e)}")
            time.sleep(5)  # Backoff safeguard parameter


if __name__ == "__main__":
    poll_queue_loop()
