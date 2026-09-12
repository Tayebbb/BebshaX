"""FastAPI router for Stripe payments, checkout sessions, and subscription webhooks."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user
from bebshax.api.deps import get_session
from bebshax.api.errors import APIError
from bebshax.auth.models import Users
from bebshax.auth.transport import AuthRoute
from bebshax.payments.service import BillingDisabledError, PaymentInputError, StripePaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"], route_class=AuthRoute)


class CreateCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan: str = Field(default="pro", min_length=1, max_length=32, description="Subscription tier: 'pro' or 'enterprise'")
    success_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    cancel_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)


class CreatePortalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    return_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)


@router.post("/create-checkout-session", status_code=status.HTTP_201_CREATED)
async def create_checkout_session_endpoint(
    body: CreateCheckoutRequest,
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a Stripe Checkout Session for initiating subscription purchase."""
    service = StripePaymentService(session)
    try:
        session_info = await service.create_checkout_session(
            user=current_user,
            plan=body.plan,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
        return session_info
    except BillingDisabledError:
        raise APIError(503, "Billing is disabled.", error_code="billing_disabled") from None
    except PaymentInputError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except Exception:
        logger.error("Failed to create Stripe checkout session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment processing error. Please try again.",
        ) from None


@router.post("/create-portal-session")
async def create_portal_session_endpoint(
    body: CreatePortalRequest = CreatePortalRequest(),
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a Stripe Billing Portal session for self-service subscription management."""
    service = StripePaymentService(session)
    try:
        portal_info = await service.create_portal_session(
            user=current_user,
            return_url=body.return_url,
        )
        return portal_info
    except BillingDisabledError:
        raise APIError(503, "Billing is disabled.", error_code="billing_disabled") from None
    except PaymentInputError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except Exception:
        logger.error("Failed to create Stripe billing portal session")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment processing error. Please try again.",
        ) from None


@router.get("/subscription")
async def get_subscription_endpoint(
    current_user: Users = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the current user's subscription tier and billing status."""
    return StripePaymentService.get_subscription_status(current_user)


@router.post("/webhook")
async def stripe_webhook_endpoint(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="stripe-signature"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Handle Stripe asynchronous webhook events."""
    service = StripePaymentService(session)
    try:
        service.require_enabled()
        payload = await request.body()
        result = await service.handle_webhook(payload=payload, sig_header=stripe_signature)
        return result
    except BillingDisabledError:
        raise APIError(503, "Billing is disabled.", error_code="billing_disabled") from None
    except PaymentInputError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from None
    except Exception:
        logger.error("Error handling Stripe webhook")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failure",
        ) from None
