"""
One-off cleanup: remove departments and DailyReport records created by the xlsx import.

All departments that have DailyReport records are import-created (since no DailyReport
data existed before the import). Safe to delete them along with all DailyReports.
"""

import sys
sys.path.insert(0, '/app')

from app import create_app
from app.extensions import db
from models import Department, DailyReport

app = create_app()
with app.app_context():
    bad_dept_ids = {r.department_id for r in DailyReport.query.all()}
    print(f"DailyReport records: {DailyReport.query.count()}")
    print(f"Import-created departments: {len(bad_dept_ids)}")
    for d in Department.query.filter(Department.id.in_(bad_dept_ids)).order_by(Department.id).all():
        print(f"  [{d.id}] {d.name!r}")

    if not bad_dept_ids:
        print("Nothing to delete.")
    else:
        deleted_dr = DailyReport.query.delete()
        deleted_dept = Department.query.filter(
            Department.id.in_(bad_dept_ids)
        ).delete(synchronize_session=False)
        db.session.commit()
        print(f"\nDeleted: {deleted_dr} DailyReport(s), {deleted_dept} Department(s)")

    print(f"\nRemaining departments: {Department.query.count()}")
    print(f"Remaining DailyReports: {DailyReport.query.count()}")
