import os
import multiprocessing

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = 0

# CPU budgeting
TOTAL_CPUS = multiprocessing.cpu_count()
RESERVED_CPUS = 4  # Flask + Gunicorn + Nginx + OS

SEARCH_CPU_BUDGET = TOTAL_CPUS - RESERVED_CPUS

# Max simultaneous searches
MAX_ACTIVE_SEARCHES = 3

# Workers per search
SEARCH_WORKERS = max(1, SEARCH_CPU_BUDGET // MAX_ACTIVE_SEARCHES)