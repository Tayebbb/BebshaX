"""Stripe payment and subscription service logic."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.auth.models import Users
from bebshax.config import get_settings

logger = logging.getLogger(__name__)

class BillingDisabledError(RuntimeError):
    """Billing has not been explicitly enabled by verified server configuration."""


class PaymentInputError(ValueError):
    """An application-authored payment validation message safe for public output."""


# Plan tier definitions & default pricing (USD cents / month)
PLAN_CONFIGS: dict[str, dict[str, Any]] = {
    "pro": {
        "name": "BebshaX Pro",
        "unit_amount": 2900,  # $29.00 / month
        "currency": "usd",
        "interval": "month",
        "description": "Unlimited studies, 50 personas/study, full evidence grounding and priority models",
    },
    "enterprise": {
        "name": "BebshaX Enterprise",
        "unit_amount": 9900,  # $99.00 / month
        "currency": "usd",
        "interval": "month",
        "description": "Everything in Pro + priority LLM routing pools, dedicated capacity, and team collaboration",
    },
}


def _assert_internal_redirect(url: Optional[str], base_url: str) -> None:
    """Reject client-supplied redirects that point away from our own frontend.

    Stripe sends the user's browser to these URLs after checkout, so an
    unvalidated value is a ready-made phishing hop. Compare parsed origins:
    a prefix test also accepts ``https://<base_url>.attacker.com/x``.
    """
    if not url:
        return
    try:
        target = urlparse(url)
        allowed = urlparse(base_url)
    except ValueError:
        raise PaymentInputError("Redirect URL must stay within the application origin.") from None
    if (target.scheme, target.netloc) != (allowed.scheme, allowed.netloc):
        raise PaymentInputError("Redirect URL must stay within the application origin.")


class StripePaymentService:
    """Encapsulates Stripe Checkout, Billing Portal, and Webhook lifecycle."""
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        if getattr(self.settings, "payments_enabled", False) is True and self.settings.stripe_secret_key:
            stripe.api_key = self.settings.stripe_secret_key

    def require_enabled(self) -> None:
        if getattr(self.settings, "payments_enabled", False) is not True:
            raise BillingDisabledError("Billing is disabled.")

    async def get_or_create_customer(self, user: Users) -> str:
        """Ensure the user has an associated Stripe customer ID."""
        self.require_enabled()
        db_user = await self.session.get(Users, user.id) or user
        if db_user.stripe_customer_id:
            return db_user.stripe_customer_id

        if not self.settings.stripe_secret_key:
            raise PaymentInputError("Payment processing is not configured.")

        customer = stripe.Customer.create(
            email=db_user.email,
            name=db_user.full_name,
            metadata={"user_id": db_user.id},
        )
        db_user.stripe_customer_id = customer.id
        await self.session.commit()
        return customer.id

    async def create_checkout_session(
        self,
        user: Users,
        plan: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a Stripe Checkout Session for subscription purchase."""
        self.require_enabled()
        plan_lower = plan.lower().strip()
        if plan_lower not in PLAN_CONFIGS:
            raise PaymentInputError("Invalid plan. Allowed plans: " + ", ".join(PLAN_CONFIGS))

        if not self.settings.stripe_secret_key:
            raise PaymentInputError("Payment processing is not configured.")

        plan_info = PLAN_CONFIGS[plan_lower]

        base_url = self.settings.frontend_base_url.rstrip("/")
        default_success = f"{base_url}/app?checkout=success&plan={plan_lower}"
        default_cancel = f"{base_url}/app?checkout=cancelled"
        _assert_internal_redirect(success_url, base_url)
        _assert_internal_redirect(cancel_url, base_url)
        customer_id = await self.get_or_create_customer(user)

        # Prefer a Stripe Dashboard price id when configured; the inline
        # price_data path below is the unchanged default.
        configured_price_id = {
            "pro": self.settings.stripe_price_id_pro,
            "enterprise": self.settings.stripe_price_id_enterprise,
        }.get(plan_lower)
        if configured_price_id:
            line_items = [{"price": configured_price_id, "quantity": 1}]
        else:
            line_items = [
                {
                    "price_data": {
                        "currency": plan_info["currency"],
                        "product_data": {
                            "name": plan_info["name"],
                            "description": plan_info["description"],
                        },
                        "unit_amount": plan_info["unit_amount"],
                        "recurring": {
                            "interval": plan_info["interval"],
                        },
                    },
                    "quantity": 1,
                }
            ]

        checkout_session = stripe.checkout.Session.create(
            customer=customer_id,
            client_reference_id=user.id,
            mode="subscription",
            payment_method_types=["card"],
            line_items=line_items,
            success_url=success_url or default_success,
            cancel_url=cancel_url or default_cancel,
            metadata={
                "user_id": user.id,
                "plan": plan_lower,
            },
        )

        return {
            "session_id": checkout_session.id,
            "url": checkout_session.url,
            "plan": plan_lower,
        }

    async def create_portal_session(
        self,
        user: Users,
        return_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a Stripe Customer Billing Portal session for subscription management."""
        self.require_enabled()
        if not self.settings.stripe_secret_key:
            raise PaymentInputError("Payment processing is not configured.")

        base_url = self.settings.frontend_base_url.rstrip("/")
        default_return = f"{base_url}/app"
        _assert_internal_redirect(return_url, base_url)
        customer_id = await self.get_or_create_customer(user)

        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url or default_return,
        )

        return {
            "url": portal_session.url,
        }

    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: Optional[str] = None,
    ) -> dict[str, Any]:
        """Process incoming Stripe webhook events."""
        self.require_enabled()
        event: dict[str, Any]

        if not self.settings.stripe_webhook_secret or not sig_header:
            # Without signature verification anyone could POST a forged
            # checkout.session.completed and upgrade an arbitrary account.
            logger.error("Stripe webhook rejected: signature verification is not configured")
            raise PaymentInputError("Webhook signature verification is not configured")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self.settings.stripe_webhook_secret
            )
        except Exception:
            logger.error("Stripe webhook signature verification failed")
            raise PaymentInputError("Invalid webhook signature") from None

        event_type = event.get("type", "")
        data_object = event.get("data", {}).get("object", {})

        logger.info(f"Received Stripe webhook event: {event_type}")

        if event_type == "checkout.session.completed":
            await self._on_checkout_completed(data_object)
        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            await self._on_subscription_updated(data_object)

        return {"received": True, "event": event_type}

    async def _on_checkout_completed(self, session_obj: dict[str, Any]) -> None:
        user_id = session_obj.get("client_reference_id") or session_obj.get("metadata", {}).get("user_id")
        plan = session_obj.get("metadata", {}).get("plan", "pro")
        customer_id = session_obj.get("customer")

        if not user_id and customer_id:
            # Look up user by stripe_customer_id
            from sqlalchemy import select
            stmt = select(Users).where(Users.stripe_customer_id == customer_id)
            user = (await self.session.execute(stmt)).scalar_one_or_none()
        elif user_id:
            user = await self.session.get(Users, user_id)
        else:
            user = None

        if user:
            user.subscription_plan = plan
            user.subscription_status = "active"
            if customer_id:
                user.stripe_customer_id = customer_id
            await self.session.commit()
            logger.info(f"User {user.id} upgraded to plan {plan}")

    async def _on_subscription_updated(self, sub_obj: dict[str, Any]) -> None:
        customer_id = sub_obj.get("customer")
        user_id = sub_obj.get("metadata", {}).get("user_id")
        status = sub_obj.get("status", "active")
        current_period_end = sub_obj.get("current_period_end")

        from sqlalchemy import select
        user = None
        if user_id:
            user = await self.session.get(Users, user_id)
        if not user and customer_id:
            stmt = select(Users).where(Users.stripe_customer_id == customer_id)
            user = (await self.session.execute(stmt)).scalar_one_or_none()

        if user:
            user.subscription_status = status
            if status in ("canceled", "unpaid", "incomplete_expired"):
                user.subscription_plan = "free"
            if current_period_end:
                user.subscription_expires_at = datetime.fromtimestamp(current_period_end, tz=timezone.utc)
            await self.session.commit()
            logger.info(f"User {user.id} subscription status updated to {status}")

    @staticmethod
    def get_subscription_status(user: Users) -> dict[str, Any]:
        """Return formatted subscription status for a user."""
        if getattr(get_settings(), "payments_enabled", False) is not True:
            return {
                "plan": "free", "status": "disabled", "is_paid": False,
                "expires_at": None, "has_billing_account": False, "billing_enabled": False,
            }
        expiry = user.subscription_expires_at
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        is_paid = (
            user.subscription_status == "active"
            and user.subscription_plan in ("pro", "enterprise")
            and (expiry is None or expiry > datetime.now(timezone.utc))
        )
        return {
            "plan": user.subscription_plan,
            "status": user.subscription_status,
            "is_paid": is_paid,
            "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            "has_billing_account": user.stripe_customer_id is not None,
            "billing_enabled": True,
        }
