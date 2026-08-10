"""One-off CLI to create or promote a POKO admin user.

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
from app.models.user import User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote a POKO admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Admin")
    args = parser.parse_args()

    email = args.email.lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.hashed_password = hash_password(args.password)
            user.role = UserRole.admin
            user.is_active = True
            print(f"Updated existing user {email} to admin.")
        else:
            user = User(
                id=uuid.uuid4(),
                email=email,
                hashed_password=hash_password(args.password),
                full_name=args.name,
                role=UserRole.admin,
                is_active=True,
            )
            db.add(user)
            print(f"Created admin user {email}.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
