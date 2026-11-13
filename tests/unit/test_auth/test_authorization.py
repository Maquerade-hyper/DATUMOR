import uuid

import pytest
from fastapi import HTTPException

from apps.api.app.auth.dependencies import ensure_resource_owner
from apps.api.app.auth.user_model import User


def test_customer_can_access_own_resource():
    user_id = uuid.uuid4()
    user = User(user_id=user_id, role="customer")
    ensure_resource_owner(user_id, user)


def test_customer_cannot_access_another_customer_resource():
    user = User(user_id=uuid.uuid4(), role="customer")
    with pytest.raises(HTTPException) as error:
        ensure_resource_owner(uuid.uuid4(), user)
    assert error.value.status_code == 404


@pytest.mark.parametrize("role", ["admin", "superadmin"])
def test_admin_roles_can_access_customer_resource(role):
    user = User(user_id=uuid.uuid4(), role=role)
    ensure_resource_owner(uuid.uuid4(), user)
