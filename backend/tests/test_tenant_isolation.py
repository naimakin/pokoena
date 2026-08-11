from app.models.user_tenant_role import TenantRole
from tests.factories import add_membership, create_project, create_tenant, create_user


def test_valid_token_from_other_tenant_cannot_access_project(client, db_session):
    tenant_a = create_tenant(db_session, name="Tenant A", slug="tenant-a")
    tenant_b = create_tenant(db_session, name="Tenant B", slug="tenant-b")

    admin_a = create_user(db_session, "admin-a@example.com", "secret123")
    add_membership(db_session, admin_a, tenant_a, TenantRole.company_admin)

    project_b = create_project(db_session, tenant_b, name="Tenant B's Project")

    client.post("/auth/login", json={"email": "admin-a@example.com", "password": "secret123"})

    # A valid, unexpired token for tenant A, reaching for a resource that
    # belongs to tenant B — this must be a 403, not a leak via 200 or a 404
    # that would let someone probe which ids exist in another tenant.
    response = client.get(f"/projects/{project_b.id}")

    assert response.status_code == 403


def test_project_list_never_includes_other_tenants_projects(client, db_session):
    tenant_a = create_tenant(db_session, name="Tenant A", slug="tenant-a2")
    tenant_b = create_tenant(db_session, name="Tenant B", slug="tenant-b2")

    admin_a = create_user(db_session, "admin-a2@example.com", "secret123")
    add_membership(db_session, admin_a, tenant_a, TenantRole.company_admin)

    project_a = create_project(db_session, tenant_a, name="Tenant A's Project")
    create_project(db_session, tenant_b, name="Tenant B's Project")

    client.post("/auth/login", json={"email": "admin-a2@example.com", "password": "secret123"})

    response = client.get("/projects")

    assert response.status_code == 200
    ids = {p["id"] for p in response.json()}
    assert ids == {str(project_a.id)}


def test_cross_tenant_activity_access_is_403(client, db_session):
    from tests.factories import create_project_scope
    from app.models.activity import Activity, ActivityStatus
    import uuid

    tenant_a = create_tenant(db_session, name="Tenant A", slug="tenant-a3")
    tenant_b = create_tenant(db_session, name="Tenant B", slug="tenant-b3")

    admin_a = create_user(db_session, "admin-a3@example.com", "secret123")
    add_membership(db_session, admin_a, tenant_a, TenantRole.company_admin)

    project_b = create_project(db_session, tenant_b, name="Tenant B's Project")
    scope_b = create_project_scope(db_session, tenant_b, project_b)
    activity_b = Activity(
        id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        project_id=project_b.id,
        project_scope_id=scope_b.id,
        external_id="B-001",
        name="Tenant B activity",
        discipline="General",
        percent_complete=0,
        remaining_duration_days=5,
        status=ActivityStatus.not_started,
    )
    db_session.add(activity_b)
    db_session.commit()

    client.post("/auth/login", json={"email": "admin-a3@example.com", "password": "secret123"})

    response = client.patch(f"/activities/{activity_b.id}", json={"percent_complete": 50})

    assert response.status_code == 403
