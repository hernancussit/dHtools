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

# Active Sessions Tracking & Auditing
ACTIVE_SESSIONS = {}
ACTIVE_SESSIONS_LOCK = threading.RLock()

# Telegram Bot Hub State
TELEGRAM_LINK_TOKENS = {}
TELEGRAM_LINK_LOCK = threading.RLock()
TELEGRAM_ACTIVE_MESSAGES = {}
TELEGRAM_ACTIVE_MESSAGES_LOCK = threading.RLock()
TELEGRAM_MEDIA_CACHE = {}
TELEGRAM_MEDIA_CACHE_LOCK = threading.RLock()

import time
START_TIME = time.time()

