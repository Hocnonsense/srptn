"""Cache garbage collection entry point for server maintenance tasks."""

import argparse
from datetime import timedelta
import math
from pathlib import Path

from srptn.common.data.fs import FSDataStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path("datastore/cache"))
    parser.add_argument("--older-than-days", type=float, default=7)
    args = parser.parse_args()
    if not math.isfinite(args.older_than_days) or args.older_than_days <= 0:
        parser.error("--older-than-days must be finite and positive")
    FSDataStore(base_cache=args.cache_dir).clean_cache(
        timedelta(days=args.older_than_days)
    )


if __name__ == "__main__":
    main()
