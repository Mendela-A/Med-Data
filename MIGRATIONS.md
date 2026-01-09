How to apply the new Alembic migration (remove `status` column)

1) Ensure dependencies are installed in your virtualenv:
   pip install Flask-Migrate alembic

2) If you haven't initialized migrations in this project before, you can either:
   - Use the included `migrations` directory (already provided), and run:
       flask db upgrade
     (If `flask` CLI picks up the app, this will run `migrations/env.py` and apply revisions.)

   - Or initialize afresh (if you prefer):
       flask db init
       flask db migrate -m "Initial"  # only if needed to baseline
       flask db upgrade

3) To apply the specific migration added for removing `status`, run:
       flask db upgrade

Notes:
- The repository contains a migration script `migrations/versions/20260109_remove_status.py` which drops the `status` column from the `records` table.
- The models in `models.py` have been updated to remove the `status` attribute to keep the code consistent with the schema change.
- If your database already has the `status` column absent or the migrations system in a different state, `flask db upgrade` will print a warning or skip accordingly.
