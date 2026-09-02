import threading

# Security: Brute Force & Rate Limiting Storage
LOGIN_ATTEMPTS = {}
LOGIN_ATTEMPTS_LOCK = threading.RLock()

# Job Processing State
JOBS = {}
JOBS_LOCK = threading.RLock()
BATCH_JOBS = {}
BATCH_LOCK = threading.RLock()
QUEUE_LIST = []
QUEUE_LOCK = threading.RLock()
ACTIVE_WORKER_JOB = None

import time
START_TIME = time.time()
