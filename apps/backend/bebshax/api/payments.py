"""FastAPI router for Stripe payments, checkout sessions, and subscription webhooks."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bebshax.api.auth import get_current_user
from bebshax.api.studies import get_session
from bebshax.auth.models import Users
from bebshax.payments.service import StripePaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


class CreateCheckoutRequest(BaseModel):
    plan: str = Field(default="pro", description="Subscription tier: 'pro' or 'enterprise'")
    success_url: Optional[str] = Field(default=None, description="Optional custom redirect URL after payment")
    cancel_url: Optional[str] = Field(default=None, description="Optional custom redirect URL if cancelled")


class CreatePortalRequest(BaseModel):
    return_url: Optional[str] = Field(default=None, description="Optional redirect URL when exiting portal")


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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to create Stripe checkout session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment provider error: {e}",
        ) from e


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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to create Stripe billing portal session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment provider error: {e}",
        ) from e


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
    payload = await request.body()
    service = StripePaymentService(session)
    try:
        result = await service.handle_webhook(payload=payload, sig_header=stripe_signature)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error handling Stripe webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failure",
        ) from e
