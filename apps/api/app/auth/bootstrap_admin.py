import os

from sqlalchemy import select

from apps.api.app.auth.service import hash_password, normalize_email
from apps.api.app.auth.user_model import User
from apps.api.app.database import SessionLocal


def main():
    email = os.getenv("DATUMOR_BOOTSTRAP_ADMIN_EMAIL", "").strip()
    password = os.getenv("DATUMOR_BOOTSTRAP_ADMIN_PASSWORD", "")
    full_name = os.getenv("DATUMOR_BOOTSTRAP_ADMIN_NAME", "DATUMOR Administrator")

    if not email or len(password) < 16:
        raise SystemExit(
            "Set DATUMOR_BOOTSTRAP_ADMIN_EMAIL and "
            "DATUMOR_BOOTSTRAP_ADMIN_PASSWORD (minimum 16 characters)."
        )

    with SessionLocal() as db:
        existing_admin = db.scalar(
            select(User).where(User.role == "superadmin").limit(1)
        )
        if existing_admin:
            raise SystemExit("A superadmin already exists. Bootstrap refused.")

        normalized = normalize_email(email)
        existing_user = db.scalar(
            select(User).where(User.email_normalized == normalized)
        )
        if existing_user:
            raise SystemExit("That email already belongs to an account.")

        user = User(
            email=email,
            email_normalized=normalized,
            password_hash=hash_password(password),
            full_name=full_name,
            role="superadmin",
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        db.commit()
        print(f"Superadmin created: {user.user_id} ({user.email})")


if __name__ == "__main__":
    main()
