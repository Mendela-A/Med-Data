#!/usr/bin/env python
"""
Test runner for Blueprint-based application

Usage:
    python run_blueprint.py

This script runs the new blueprint-based application for testing.
The old app.py remains unchanged during migration.
"""

from app import create_app

if __name__ == '__main__':
    app = create_app()

    # Print registered routes for debugging
    print("\n=== Registered Routes ===")
    for rule in app.url_map.iter_rules():
        print(f"{rule.rule:40s} -> {rule.endpoint}")
    print("=" * 70)

    app.run(host='0.0.0.0', port=5001, debug=True)
