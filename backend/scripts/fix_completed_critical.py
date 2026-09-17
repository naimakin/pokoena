"""One-off backfill: clears `is_critical` on already-completed activities.

Before this fix, `services/xer_import.py::_is_critical` (and the CPM scheduler's
`total_float_hr_cnt = 0.0` display convention for TK_Complete tasks it read
from) flagged every finished activity as critical regardless of actual float.
That bug is fixed for imports going forward, but projects imported *before*
the fix still carry the bad value in the `activities` table until their next
schedule import — this script corrects them in place, without requiring a
re-upload.

Usage (from backend/, with DATABASE_URL available):
    python -m scripts.fix_completed_critical            # apply
    python -m scripts.fix_completed_critical --dry-run   # report only

Idempotent: re-running finds nothing left to fix.
"""

import argparse

from sqlalchemy import func

from app.db.session import SessionLocal, set_rls_context
from app.models.activity import Activity, ActivityStatus
from app.models.tenant import Tenant


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear is_critical on completed activities")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without writing")
    args = parser.parse_args()

    db = SessionLocal()
    total = 0
    try:
        # `tenants` carries no tenant_id itself and has no RLS policy — safe to
        # list with the ordinary poko_app session, same as scripts/seed_demo.py.
        for (tenant_id,) in db.query(Tenant.id).all():
            set_rls_context(db, tenant_id)
            count = (
                db.query(func.count(Activity.id))
                .filter(
                    Activity.tenant_id == tenant_id,
                    Activity.status == ActivityStatus.complete,
                    Activity.is_critical.is_(True),
                )
                .scalar()
            )
            if not count:
                continue
            total += count
            print(f"tenant {tenant_id}: {count} completed activities marked critical")
            if not args.dry_run:
                db.query(Activity).filter(
                    Activity.tenant_id == tenant_id,
                    Activity.status == ActivityStatus.complete,
                    Activity.is_critical.is_(True),
                ).update({Activity.is_critical: False}, synchronize_session=False)
                db.commit()
    finally:
        db.close()

    verb = "Would fix" if args.dry_run else "Fixed"
    print(f"{verb} {total} activities total.")


if __name__ == "__main__":
    main()
