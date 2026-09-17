"""
Celery application entry-point (docs.celeryq.dev/en/stable/getting-started
/first-steps-with-celery.html). Broker = CloudAMQP (RabbitMQ), result
backend = Upstash Redis — both hosted, so no local broker container is
needed (Technical PRD Sec 2, Sec 12.3).
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "recipe_bot",
    broker=settings.celery_broker_url,
    backend=settings.upstash_redis_url,
    include=[
        "app.tasks.tts_tasks",
        "app.tasks.media_tasks",
        "app.tasks.memory_tasks",
        "app.tasks.eval_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
