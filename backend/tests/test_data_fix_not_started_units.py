"""Migration 0032: a Not Started activity's assignments go back to 0 actual /
full budget remaining; every other activity's units are left alone."""

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa

from app.models.activity import ActivityStatus
from app.models.resource import LABOR, Resource
from app.models.resource_assignment import ResourceAssignment
from tests.factories import create_activity, create_project, create_tenant

_MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0032_clear_units_on_not_started.py"


def _fix_sql():
    spec = importlib.util.spec_from_file_location("m0032", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FIX_SQL


def _assign(db, tenant, project, activity, resource, *, target, actual):
    row = ResourceAssignment(
        id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, activity_id=activity.id,
        resource_id=resource.id, target_qty=target, act_reg_qty=actual, remain_qty=target - actual,
    )
    db.add(row)
    db.commit()
    return row


def test_clears_actual_units_only_on_not_started_activities(db_session):
    tenant = create_tenant(db_session, name="Fix", slug="fix-units")
    other_tenant = create_tenant(db_session, name="Other", slug="fix-units-other")
    project = create_project(db_session, tenant)
    other_project = create_project(db_session, other_tenant)
    crew = Resource(id=uuid.uuid4(), tenant_id=tenant.id, project_id=project.id, rsrc_id="R1", name="PMC", rsrc_type=LABOR)
    other_crew = Resource(
        id=uuid.uuid4(), tenant_id=other_tenant.id, project_id=other_project.id, rsrc_id="R1", name="PMC", rsrc_type=LABOR
    )
    db_session.add_all([crew, other_crew])
    db_session.commit()

    not_started = create_activity(db_session, tenant, project, "HER01-DES-MS-1070")
    in_progress = create_activity(db_session, tenant, project, "A2", status=ActivityStatus.in_progress, percent_complete=40)
    other = create_activity(db_session, other_tenant, other_project, "B1")
    bad = _assign(db_session, tenant, project, not_started, crew, target=408, actual=408)
    kept = _assign(db_session, tenant, project, in_progress, crew, target=100, actual=55)  # P6's own, != %
    other_bad = _assign(db_session, other_tenant, other_project, other, other_crew, target=10, actual=10)

    tenant_key = db_session.execute(sa.text("SELECT id FROM tenants WHERE slug = 'fix-units'")).scalar()
    db_session.execute(_fix_sql(), {"tenant_id": tenant_key})
    db_session.commit()
    db_session.expire_all()

    assert (bad.act_reg_qty, bad.remain_qty) == (0, 408)
    assert (kept.act_reg_qty, kept.remain_qty) == (55, 45)
    assert (other_bad.act_reg_qty, other_bad.remain_qty) == (10, 0)  # another tenant's run fixes that one
