"""Email delivery service for BebshaX (Resend integration)."""

import logging
from typing import Optional
import httpx

from bebshax.config import get_settings

logger = logging.getLogger(__name__)
RESEND_API_URL = "https://api.resend.com/emails"


async def send_verification_email(to_email: str, verification_url: str) -> bool:
    """Send email verification link via Resend API.
    
    Fail-soft: Email delivery errors log warning/error but do not crash the caller.
    """
    settings = get_settings()
    api_key = getattr(settings, "resend_api_key", None)
    if not api_key:
        logger.warning(
            "Resend API key not configured (BEBSHAX_RESEND_API_KEY). "
            "Skipping real email dispatch to %s (verification URL: %s).",
            to_email,
            verification_url,
        )
        return False

    try:
        from_addr = getattr(settings, "email_from_address", "noreply@bebshax.ai")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "from": from_addr,
                    "to": [to_email],
                    "subject": "Verify your BebshaX account",
                    "html": (
                        "<p>Click the link below to verify your email address:</p>"
                        f'<p><a href="{verification_url}">{verification_url}</a></p>'
                        "<p>This link expires in 24 hours.</p>"
                    ),
                },
            )
        if resp.status_code >= 400:
            logger.error(
                "Failed to send verification email to %s: HTTP %d %s",
                to_email,
                resp.status_code,
                resp.text,
            )
            return False
        return True
    except Exception as exc:
        logger.error(
            "Exception sending verification email to %s: %s",
            to_email,
            exc,
        )
        return False
