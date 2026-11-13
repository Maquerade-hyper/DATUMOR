import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.app.auth.user_model import User
from apps.api.app.database import Base


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_user(**overrides):
    values = {
        "email": "Customer@Example.com",
        "email_normalized": "customer@example.com",
        "password_hash": "$argon2id$test-hash",
        "role": "customer",
    }
    values.update(overrides)
    return User(**values)


def test_user_persists_with_expected_defaults(db_engine):
    with Session(db_engine) as session:
        user = make_user()
        session.add(user)
        session.commit()

        stored = session.scalar(
            select(User).where(User.email_normalized == "customer@example.com")
        )

        assert stored is not None
        assert isinstance(stored.user_id, uuid.UUID)
        assert stored.role == "customer"
        assert stored.is_active is True
        assert stored.is_email_verified is False
        assert stored.password_hash.startswith("$argon2id$")
        assert stored.created_at is not None
        assert stored.updated_at is not None


def test_normalized_email_must_be_unique(db_engine):
    with Session(db_engine) as session:
        session.add(make_user())
        session.commit()

        session.add(make_user(email="CUSTOMER@example.com"))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("role", ["owner", "root", ""])
def test_invalid_role_is_rejected_by_database(db_engine, role):
    with Session(db_engine) as session:
        session.add(make_user(role=role))
        with pytest.raises(IntegrityError):
            session.commit()


def test_normalized_email_must_be_lowercase_and_trimmed(db_engine):
    with Session(db_engine) as session:
        session.add(
            make_user(email_normalized=" Customer@Example.com ")
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_email_length_constraint(db_engine):
    with Session(db_engine) as session:
        session.add(make_user(email="x"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_user_can_be_deactivated(db_engine):
    with Session(db_engine) as session:
        user = make_user()
        session.add(user)
        session.commit()

        user.is_active = False
        session.commit()

        stored = session.get(User, user.user_id)
        assert stored.is_active is False
