"""
Training notification wrapper — forwards to shared/notify.py

Kept for backward compatibility with train_yearly.sh which calls:
  python3 notify.py --type train_start --year 2020 --details "..."
"""
import os
import sys

# Add shared/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from notify import send_notification, TYPES  # noqa: F401

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=list(TYPES.keys()))
    parser.add_argument("--year", default="")
    parser.add_argument("--details", default="")
    args = parser.parse_args()
    send_notification(args.type, args.details, source="training", year=args.year)
