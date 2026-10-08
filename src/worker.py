import argparse
import logging
import sqlite3
import time
from datetime import UTC, datetime

import repositories
from database import initialize_database
from environment import load_environment_file
from publishers import PublishFailure
from services import publish_slot

logger = logging.getLogger(__name__)


def process_due_slots(limit: int = 50) -> dict:
    now = datetime.now(UTC).isoformat(timespec="microseconds")
    due_slots = repositories.list_due_slots(now, limit)
    results = {"checked": len(due_slots), "published": 0, "failed": 0, "skipped": 0}
    for slot in due_slots:
        try:
            publish_slot(slot["id"])
            results["published"] += 1
        except ValueError:
            results["skipped"] += 1
        except (LookupError, RuntimeError, PublishFailure, sqlite3.Error) as error:
            logger.warning("Could not publish slot %s: %s", slot["id"], error)
            results["failed"] += 1
    return results


def run_worker(interval: float = 5.0, once: bool = False) -> None:
    load_environment_file()
    initialize_database()
    while True:
        repositories.recover_interrupted_publications()
        results = process_due_slots()
        print(results, flush=True)
        if once:
            return
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish due Social Media Studio slots"
    )
    parser.add_argument(
        "--once", action="store_true", help="process a single due-slot batch"
    )
    parser.add_argument(
        "--interval", type=float, default=5.0, help="seconds between batches"
    )
    options = parser.parse_args()
    run_worker(interval=max(options.interval, 0.1), once=options.once)


if __name__ == "__main__":
    main()
