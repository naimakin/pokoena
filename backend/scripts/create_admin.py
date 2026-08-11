"""One-off CLI to create or promote a POKO Platform Super Admin (POKO staff,
not a tenant user).

Usage (from backend/, with the app's dependencies + DATABASE_URL available):
    python -m scripts.create_admin --email admin@pokoena.com --password 'change-me' --name "Jordan Diaz"

In production this is run once, as a one-shot Docker Swarm service against the
backend image (Swarm secrets are only mountable into scheduled tasks, not `docker run`) —
see infra/README.md.
"""

import argparse
import uuid

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote a POKO Platform Super Admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Admin")
    args = parser.parse_args()

    email = args.email.lower()
    # `users` carries no tenant_id and has no RLS policy — the ordinary poko_app
    # session works here with no tenant context needed, same as any other query
    # against a platform-level (not tenant-scoped) table.
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.hashed_password = hash_password(args.password)
            user.is_platform_admin = True
            user.is_active = True
            print(f"Updated existing user {email} to platform admin.")
        else:
            user = User(
                id=uuid.uuid4(),
                email=email,
                hashed_password=hash_password(args.password),
                full_name=args.name,
                is_platform_admin=True,
                is_active=True,
            )
            db.add(user)
            print(f"Created platform admin user {email}.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
