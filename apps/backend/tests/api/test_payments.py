"""Unit and regression tests for Stripe payments API & service."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.db.models import Base
from bebshax.main import app

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="module", autouse=True)
def _setup_app_db():
    import asyncio

    async def init():
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(init())
    sm = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    app.state.db_sessionmaker = sm
    app.state.sessionmaker = sm


client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_user():
    import asyncio

    user_id = "usr_stripe_test_01"
    async def init_user():
        sm = app.state.db_sessionmaker
        async with sm() as session:
            existing = await session.get(Users, user_id)
            if not existing:
                u = Users(
                    id=user_id,
                    email="stripe_test@example.com",
                    full_name="Stripe Test User",
                    auth_provider="email",
                    is_active=True,
                    is_verified=True,
                    subscription_plan="free",
                    subscription_status="active",
                )
                session.add(u)
                await session.commit()
    asyncio.run(init_user())
    return user_id


def test_payment_endpoints_require_auth():
    """Unauthenticated requests to payment management endpoints must return 401."""
    res_checkout = client.post("/api/payments/create-checkout-session", json={"plan": "pro"})
    assert res_checkout.status_code == 401

    res_portal = client.post("/api/payments/create-portal-session", json={})
    assert res_portal.status_code == 401

    res_sub = client.get("/api/payments/subscription")
    assert res_sub.status_code == 401


def test_get_subscription_status(seeded_user):
    """Authenticated user retrieves their subscription status (free by default)."""
    token = create_access_token(seeded_user)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/payments/subscription", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["plan"] == "free"
    assert data["status"] == "active"
    assert data["is_paid"] is False


def test_create_checkout_session_invalid_plan(seeded_user):
    """Reject invalid tier names with 400 Bad Request."""
    token = create_access_token(seeded_user)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/payments/create-checkout-session",
        json={"plan": "diamond_infinite"},
        headers=headers,
    )
    assert res.status_code == 400
    assert "Invalid plan" in res.json()["detail"]


@patch("stripe.Customer.create")
@patch("stripe.checkout.Session.create")
def test_create_checkout_session_success(mock_session_create, mock_customer_create, seeded_user):
    """Successfully generate a Stripe Checkout session for Pro plan."""
    mock_customer = MagicMock()
    mock_customer.id = "cus_mock_12345"
    mock_customer_create.return_value = mock_customer

    mock_checkout = MagicMock()
    mock_checkout.id = "cs_test_mock_session_id"
    mock_checkout.url = "https://checkout.stripe.com/c/pay/cs_test_mock"
    mock_session_create.return_value = mock_checkout

    token = create_access_token(seeded_user)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/payments/create-checkout-session",
        json={"plan": "pro"},
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["session_id"] == "cs_test_mock_session_id"
    assert data["url"] == "https://checkout.stripe.com/c/pay/cs_test_mock"
    assert data["plan"] == "pro"


@patch("stripe.Customer.create")
@patch("stripe.billing_portal.Session.create")
def test_create_portal_session_success(mock_portal_create, mock_customer_create, seeded_user):
    """Successfully generate a Stripe Billing Portal session."""
    mock_customer = MagicMock()
    mock_customer.id = "cus_mock_12345"
    mock_customer_create.return_value = mock_customer

    mock_portal = MagicMock()
    mock_portal.url = "https://billing.stripe.com/p/session/test_portal"
    mock_portal_create.return_value = mock_portal

    token = create_access_token(seeded_user)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/payments/create-portal-session",
        json={},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["url"] == "https://billing.stripe.com/p/session/test_portal"


def test_webhook_checkout_session_completed_upgrades_user(seeded_user):
    """Webhook event checkout.session.completed upgrades the user's plan to pro."""
    webhook_event = {
        "id": "evt_test_checkout_01",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_completed",
                "client_reference_id": seeded_user,
                "customer": "cus_test_9999",
                "metadata": {
                    "user_id": seeded_user,
                    "plan": "pro",
                },
            }
        },
    }

    res = client.post(
        "/api/payments/webhook",
        content=json.dumps(webhook_event).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["received"] is True

    # Verify user state was updated
    token = create_access_token(seeded_user)
    headers = {"Authorization": f"Bearer {token}"}
    sub_res = client.get("/api/payments/subscription", headers=headers)
    assert sub_res.status_code == 200
    assert sub_res.json()["plan"] == "pro"
    assert sub_res.json()["is_paid"] is True


def test_webhook_subscription_deleted_reverts_user(seeded_user):
    """Webhook event customer.subscription.deleted reverts user to free tier."""
    webhook_event = {
        "id": "evt_test_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_test_deleted",
                "customer": "cus_test_9999",
                "status": "canceled",
            }
        },
    }

    res = client.post(
        "/api/payments/webhook",
        content=json.dumps(webhook_event).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200

    # Verify user state is reverted
    token = create_access_token(seeded_user)
    headers = {"Authorization": f"Bearer {token}"}
    sub_res = client.get("/api/payments/subscription", headers=headers)
    assert sub_res.status_code == 200
    assert sub_res.json()["plan"] == "free"
    assert sub_res.json()["status"] == "canceled"
    assert sub_res.json()["is_paid"] is False
