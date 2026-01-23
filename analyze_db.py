#!/usr/bin/env python
"""
Database ANALYZE script for optimizing query planner statistics.

This script should be run periodically (e.g., daily via cron) to keep
the database query planner statistics up-to-date.

Usage:
    python analyze_db.py

Docker usage:
    docker exec flask_app python analyze_db.py

Cron example (run daily at 3 AM):
    0 3 * * * cd /path/to/app && python analyze_db.py >> logs/analyze.log 2>&1
"""

import sys
from datetime import datetime


def analyze_database():
    """Run ANALYZE on the database to update query planner statistics."""
    try:
        from app import create_app
        from models import db

        app = create_app()
        with app.app_context():
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting ANALYZE...")

            # Run ANALYZE to update statistics
            db.session.execute(db.text("ANALYZE"))
            db.session.commit()

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ANALYZE completed successfully")
            return 0

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    exit_code = analyze_database()
    sys.exit(exit_code)
