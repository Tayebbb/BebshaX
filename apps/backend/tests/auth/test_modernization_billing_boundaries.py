"""Billing is inert until explicitly enabled; SDK boundaries remain hermetic."""

from datetime import timedelta
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bebshax.api import payments as payments_api
from bebshax.api.errors import register_exception_handlers
from bebshax.auth.models import Users
from bebshax.auth.security import create_access_token
from bebshax.auth.sessions import utc_now
from bebshax.payments import service as payment_service


@pytest.fixture
def payment_state(identity_state, monkeypatch) -> SimpleNamespace:
    settings = SimpleNamespace(
        payments_enabled=False, stripe_secret_key="unit-only-payment-key",
        stripe_webhook_secret="unit-only-webhook-key", stripe_price_id_pro=None,
        stripe_price_id_enterprise=None, frontend_base_url="https://app.example.test",
    )
    monkeypatch.setattr(payment_service, "get_settings", lambda: settings)
    sdk = SimpleNamespace(
        customer=Mock(return_value=SimpleNamespace(id="cus_unit_owner")),
        checkout=Mock(return_value=SimpleNamespace(id="cs_unit_checkout", url="https://checkout.stripe.com/unit")),
        portal=Mock(return_value=SimpleNamespace(url="https://billing.stripe.com/unit")),
        webhook=Mock(return_value={"id": "evt_unit", "type": "unit.ignored", "data": {}}),
    )
    monkeypatch.setattr(payment_service.stripe.Customer, "create", sdk.customer)
    monkeypatch.setattr(payment_service.stripe.checkout.Session, "create", sdk.checkout)
    monkeypatch.setattr(payment_service.stripe.billing_portal.Session, "create", sdk.portal)
    monkeypatch.setattr(payment_service.stripe.Webhook, "construct_event", sdk.webhook)
    identity_state.app.include_router(payments_api.router, prefix="/api")
    register_exception_handlers(identity_state.app)
    return SimpleNamespace(
        client=identity_state.client, sessions=identity_state.sessions, settings=settings, sdk=sdk,
        headers={"Authorization": f"Bearer {create_access_token('usr_identity')}", "stripe-signature": "unit-signature"},
    )


@pytest.mark.parametrize("enabled", [None, False, "true", 1])
@pytest.mark.parametrize("path", ["create-checkout-session", "create-portal-session", "webhook"])
async def test_billing_requires_explicit_boolean_enablement_even_with_keys(payment_state, enabled, path) -> None:
    if enabled is None:
        del payment_state.settings.payments_enabled
    else:
        payment_state.settings.payments_enabled = enabled
    response = await payment_state.client.post(
        f"/api/payments/{path}", json={}, headers=payment_state.headers,
    )

    assert response.status_code == 503
    assert response.json()["error_code"] == "billing_disabled"
    for operation in vars(payment_state.sdk).values():
        operation.assert_not_called()


async def test_disabled_billing_does_not_report_stale_paid_entitlement(payment_state) -> None:
    async with payment_state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.subscription_plan = "enterprise"
        user.subscription_status = "active"
        user.stripe_customer_id = "cus_stale"
        await session.commit()

    response = await payment_state.client.get("/api/payments/subscription", headers=payment_state.headers)

    assert response.status_code == 200
    assert response.json() == {
        "plan": "free", "status": "disabled", "is_paid": False,
        "expires_at": None, "has_billing_account": False, "billing_enabled": False,
    }
    async with payment_state.sessions() as session:
        assert (await session.get(Users, "usr_identity")).subscription_plan == "enterprise"


@pytest.mark.parametrize("path,field", [
    ("create-checkout-session", "success_url"), ("create-portal-session", "return_url"),
])
async def test_redirect_is_validated_before_any_payment_side_effect(payment_state, path, field) -> None:
    payment_state.settings.payments_enabled = True
    response = await payment_state.client.post(
        f"/api/payments/{path}", json={field: "https://foreign.example.test"}, headers=payment_state.headers,
    )

    assert response.status_code == 400
    for operation in vars(payment_state.sdk).values():
        operation.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("subscription_plan", "enterprise"), ("is_paid", True), ("user_id", "usr_other"),
])
async def test_checkout_rejects_client_entitlement_and_identity_fields(payment_state, field, value) -> None:
    payment_state.settings.payments_enabled = True
    response = await payment_state.client.post(
        "/api/payments/create-checkout-session", json={"plan": "pro", field: value}, headers=payment_state.headers,
    )

    assert response.status_code == 422
    payment_state.sdk.checkout.assert_not_called()
    async with payment_state.sessions() as session:
        assert (await session.get(Users, "usr_identity")).subscription_plan == "free"
        assert (await session.get(Users, "usr_other")).subscription_plan == "free"


async def test_expired_subscription_never_reports_paid_entitlement(payment_state) -> None:
    payment_state.settings.payments_enabled = True
    async with payment_state.sessions() as session:
        user = await session.get(Users, "usr_identity")
        user.subscription_plan = "pro"
        user.subscription_status = "active"
        user.subscription_expires_at = utc_now() - timedelta(seconds=1)
        await session.commit()

    response = await payment_state.client.get("/api/payments/subscription", headers=payment_state.headers)

    assert response.status_code == 200
    assert response.json()["is_paid"] is False


@pytest.mark.parametrize("exception_type", [ValueError, RuntimeError])
@pytest.mark.parametrize("path,operation", [
    ("create-checkout-session", "checkout"), ("create-portal-session", "portal"), ("webhook", "webhook"),
])
async def test_payment_sdk_exception_values_are_never_public_or_logged(
    payment_state, caplog, exception_type, path, operation,
) -> None:
    payment_state.settings.payments_enabled = True
    sentinel = "private-payment-sdk-value"
    getattr(payment_state.sdk, operation).side_effect = exception_type(sentinel)
    with caplog.at_level(logging.ERROR):
        response = await payment_state.client.post(
            f"/api/payments/{path}", json={}, headers=payment_state.headers,
        )

    assert response.status_code == (400 if path == "webhook" else 500)
    assert sentinel not in response.text
    assert sentinel not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_invalid_plan_is_not_echoed_in_payment_errors(payment_state) -> None:
    payment_state.settings.payments_enabled = True
    sentinel = "private-invalid-plan"
    response = await payment_state.client.post(
        "/api/payments/create-checkout-session", json={"plan": sentinel}, headers=payment_state.headers,
    )

    assert response.status_code == 400
    assert "Invalid plan" in response.json()["detail"]
    assert sentinel not in response.text