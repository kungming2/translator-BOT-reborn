# scheduler/runner.py
"""APScheduler-based runner that launches bot scripts as subprocesses on a fixed schedule."""

import logging
import subprocess
import sys
from pathlib import Path

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.schedulers.blocking import BlockingScheduler

from config import SCHEDULER_SETTINGS
from scheduler.lock import AlreadyRunningError, script_lock

BOT_DIR = Path(SCHEDULER_SETTINGS["main_bot_directory"])
LOG_DIR = Path(SCHEDULER_SETTINGS["main_log_directory"])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scheduler.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("scheduler")


def run_script(
    script: str, args: list[str] | None = None, lock_name: str | None = None
) -> None:
    """Run a bot script as a subprocess, with optional exclusive lock."""
    args = args or []
    name = lock_name or Path(script).stem
    log_file = LOG_DIR / f"{name}.log"

    try:
        with script_lock(name):
            log.info(f"Starting {name} {' '.join(args)}")
            with open(log_file, "a") as lf:
                result = subprocess.run(
                    [sys.executable, str(BOT_DIR / script)] + args,
                    stdout=lf,
                    stderr=lf,
                )
            if result.returncode != 0:
                log.error(f"{name} exited with code {result.returncode}")
            else:
                log.info(f"Finished {name}")
    except AlreadyRunningError:
        log.warning(f"Skipping {name} — previous instance still running")


def on_scheduler_event(event: JobExecutionEvent) -> None:
    """Log an error if a scheduled job raised an exception or was missed."""
    if event.exception:
        log.error(f"Job {event.job_id} raised an exception: {event.exception}")


scheduler = BlockingScheduler(timezone="UTC")
scheduler.add_listener(on_scheduler_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED)

# --- Ziwen: every 3 minutes ---
scheduler.add_job(
    run_script,
    "interval",
    minutes=3,
    id="ziwen",
    kwargs={"script": "main_ziwen.py", "lock_name": "ziwen"},
    max_instances=1,  # belt-and-suspenders alongside flock
    coalesce=True,  # if missed runs pile up, only run once on recovery
    misfire_grace_time=60,
)

# --- Chinese Reference: every 5 minutes ---
scheduler.add_job(
    run_script,
    "interval",
    minutes=5,
    id="chinese_reference",
    kwargs={"script": "main_chinese_reference.py", "lock_name": "chinese_reference"},
    max_instances=1,
    coalesce=True,
    misfire_grace_time=60,
)

# --- Hermes: every 30 minutes ---
scheduler.add_job(
    run_script,
    "interval",
    minutes=30,
    id="hermes",
    kwargs={"script": "main_hermes.py", "lock_name": "hermes"},
    max_instances=1,
    coalesce=True,
    misfire_grace_time=120,
)

# --- Wenju: hourly at :01 UTC ---
scheduler.add_job(
    run_script,
    "cron",
    minute=1,
    id="wenju_hourly",
    kwargs={
        "script": "main_wenju.py",
        "args": ["hourly"],
        "lock_name": "wenju_hourly",
    },
    max_instances=1,
    coalesce=True,
    misfire_grace_time=300,
)

# --- Wenju: daily at 23:57 UTC ---
scheduler.add_job(
    run_script,
    "cron",
    hour=23,
    minute=57,
    id="wenju_daily",
    kwargs={"script": "main_wenju.py", "args": ["daily"], "lock_name": "wenju_daily"},
    max_instances=1,
    coalesce=True,
    misfire_grace_time=600,
)

# --- Wenju: weekly Wednesday 00:01 UTC ---
scheduler.add_job(
    run_script,
    "cron",
    day_of_week="wed",
    hour=0,
    minute=1,
    id="wenju_weekly",
    kwargs={
        "script": "main_wenju.py",
        "args": ["weekly"],
        "lock_name": "wenju_weekly",
    },
    max_instances=1,
    coalesce=True,
    misfire_grace_time=3600,
)

# --- Wenju: monthly on the 10th at 00:01 UTC ---
scheduler.add_job(
    run_script,
    "cron",
    day=10,
    hour=0,
    minute=1,
    id="wenju_monthly",
    kwargs={
        "script": "main_wenju.py",
        "args": ["monthly"],
        "lock_name": "wenju_monthly",
    },
    max_instances=1,
    coalesce=True,
    misfire_grace_time=3600,
)

if __name__ == "__main__":
    log.info("Bot scheduler starting...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot scheduler stopped.")
