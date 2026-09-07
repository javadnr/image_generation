import asyncio
from bot.config import settings

TIER_QUEUES: dict[str, asyncio.Semaphore | None] = {}


def init_queues():
    global TIER_QUEUES
    TIER_QUEUES = {
        "free": asyncio.Semaphore(settings.FREE_QUEUE_SIZE) if settings.FREE_QUEUE_SIZE > 0 else None,
        "bronze": asyncio.Semaphore(settings.BRONZE_QUEUE_SIZE) if settings.BRONZE_QUEUE_SIZE > 0 else None,
        "silver": asyncio.Semaphore(settings.SILVER_QUEUE_SIZE) if settings.SILVER_QUEUE_SIZE > 0 else None,
        "gold": None,
    }


USER_GENERATING: set[int] = set()


async def acquire_queue(tier: str, user_id: int) -> bool:
    if user_id in USER_GENERATING:
        return False
    sem = TIER_QUEUES.get(tier)
    if sem is not None:
        await sem.acquire()
    USER_GENERATING.add(user_id)
    return True


def release_queue(tier: str, user_id: int) -> None:
    USER_GENERATING.discard(user_id)
    sem = TIER_QUEUES.get(tier)
    if sem is not None:
        sem.release()
