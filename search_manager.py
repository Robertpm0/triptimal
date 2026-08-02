import redis
import time
import uuid

from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    MAX_ACTIVE_SEARCHES
)

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

SLOTS_KEY = "active_search_slots"

def initialize_slots():
    """Initialize slot count if not already set."""
    if not redis_client.exists(SLOTS_KEY):
        redis_client.set(SLOTS_KEY, MAX_ACTIVE_SEARCHES)

def acquire_search_slot(timeout=1800):
    """
    Wait for an available search slot.
    Returns a token that must be released later.
    """
    token = str(uuid.uuid4())
    start = time.time()

    while True:
        with redis_client.pipeline() as pipe:
            try:
                pipe.watch(SLOTS_KEY)
                current = int(pipe.get(SLOTS_KEY) or 0)

                if current > 0:
                    pipe.multi()
                    pipe.set(SLOTS_KEY, current - 1)
                    pipe.execute()

                    # lease expires automatically if process crashes
                    redis_client.set(
                        f"search:{token}",
                        "active",
                        ex=timeout
                    )

                    print(f"SEARCH SLOT ACQUIRED {token}")
                    return token

            except redis.WatchError:
                # another worker changed the value, retry
                pass

        if time.time() - start > timeout:
            raise TimeoutError("Timed out waiting for search slot")

        time.sleep(2)

def release_search_slot(token):
    """Release a previously acquired search slot."""
    lease_key = f"search:{token}"

    if redis_client.exists(lease_key):
        redis_client.delete(lease_key)

        with redis_client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(SLOTS_KEY)
                    current = int(pipe.get(SLOTS_KEY) or 0)
                    new_value = min(current + 1, MAX_ACTIVE_SEARCHES)

                    pipe.multi()
                    pipe.set(SLOTS_KEY, new_value)
                    pipe.execute()
                    break

                except redis.WatchError:
                    continue

        print(f"SEARCH SLOT RELEASED {token}")