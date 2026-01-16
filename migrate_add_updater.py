"""
Migration script to add updated_by and updated_at fields to records table.
Run this script inside the Flask app container:
    docker exec flask_app python migrate_add_updater.py
"""
from app import create_app
from models import db

app = create_app()

with app.app_context():
    # Add columns using raw SQL (SQLAlchemy doesn't support ALTER TABLE directly)
    try:
        # Check if columns already exist
        result = db.session.execute(db.text("PRAGMA table_info(records)"))
        columns = [row[1] for row in result]

        if 'updated_by' not in columns:
            print("Adding updated_by column...")
            db.session.execute(db.text("ALTER TABLE records ADD COLUMN updated_by INTEGER"))
            db.session.commit()
            print("✓ updated_by column added")
        else:
            print("⊘ updated_by column already exists")

        if 'updated_at' not in columns:
            print("Adding updated_at column...")
            db.session.execute(db.text("ALTER TABLE records ADD COLUMN updated_at TIMESTAMP"))
            db.session.commit()
            print("✓ updated_at column added")
        else:
            print("⊘ updated_at column already exists")

        # Set initial values for existing records
        print("Setting initial values for existing records...")
        db.session.execute(db.text("""
            UPDATE records
            SET updated_by = created_by,
                updated_at = created_at
            WHERE updated_by IS NULL OR updated_at IS NULL
        """))
        db.session.commit()
        print("✓ Initial values set")

        print("\n✓ Migration completed successfully!")

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        db.session.rollback()
