import random

from app.celery_app import celery_app

# Sec 11.4: sample 10-20% of real conversations for async LLM-as-judge
# scoring — higher than a mature product would use, appropriate given low
# initial volume.
SAMPLE_RATE = 0.15


def should_sample() -> bool:
    return random.random() < SAMPLE_RATE


@celery_app.task(name="tasks.score_conversation_turn")
def score_conversation_turn(conversation_id: str, message_id: str) -> None:
    """Stub: the actual judge prompts/scorers live in the top-level
    `eval/judges/` package (Sec 11.1-11.2), run offline via the pytest
    harness against the golden dataset. Wiring the same judges into this
    async production-sampling task is a follow-up — this task currently
    only reserves the sampling decision and the Celery entry point so the
    call site (bot API route) doesn't need to change later."""
    pass
