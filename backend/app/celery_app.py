import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

REDIS_URL = os.getenv("REDIS_URL")

celery_app = Celery(
    "ik_asistan",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.document_tasks", "app.tasks.rag_tasks", "app.tasks.email_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Istanbul",
    enable_utc=True,
)
