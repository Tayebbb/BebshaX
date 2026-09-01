"""Email delivery service for BebshaX (SMTP / Gmail & Resend support)."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional
import httpx

from bebshax.config import get_settings

logger = logging.getLogger(__name__)
RESEND_API_URL = "https://api.resend.com/emails"


def _send_smtp_sync(
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    from_addr: str,
    to_email: str,
    subject: str,
    html_body: str,
) -> bool:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email
    msg.set_content("Please enable HTML to view this email.")
    msg.add_alternative(html_body, subtype="html")

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as server:
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
    return True


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email using SMTP (Gmail) or Resend API."""
    settings = get_settings()

    # 1. Try SMTP if configured
    smtp_user = getattr(settings, "smtp_username", None)
    smtp_pass = getattr(settings, "active_smtp_password", None)
    if smtp_user and smtp_pass:
        try:
            from_addr = getattr(settings, "email_from_address", smtp_user)
            smtp_host = getattr(settings, "smtp_host", "smtp.gmail.com")
            smtp_port = getattr(settings, "smtp_port", 587)
            await asyncio.to_thread(
                _send_smtp_sync,
                smtp_host,
                smtp_port,
                smtp_user,
                smtp_pass,
                from_addr,
                to_email,
                subject,
                html_body,
            )
            logger.info("Sent email to %s via SMTP (%s)", to_email, smtp_host)
            return True
        except Exception as exc:
            logger.warning(
                "SMTP email delivery to %s failed (%s). Trying Resend API fallback.",
                to_email,
                exc,
            )

    # 2. Fallback to Resend API
    api_key = getattr(settings, "resend_api_key", None)
    if api_key:
        try:
            from_addr = getattr(settings, "email_from_address", "bebshax.official@gmail.com")
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    RESEND_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "from": from_addr,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_body,
                    },
                )
            if resp.status_code < 400:
                logger.info("Sent email to %s via Resend API", to_email)
                return True
            else:
                logger.error("Resend API failed: %d %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.error("Resend API exception: %s", exc)

    logger.warning("No working email credentials configured. Email to %s skipped.", to_email)
    return False


async def send_verification_email(to_email: str, verification_url: str, otp_code: Optional[str] = None) -> bool:
    """Send verification email with both 6-digit OTP code and direct link."""
    subject = f"Your BebshaX Verification Code: {otp_code}" if otp_code else "Verify your BebshaX account"

    otp_html = ""
    if otp_code:
        otp_html = (
            "<p style='font-size: 15px; color: #374151;'>Use this 6-digit verification code to complete your signup:</p>"
            f"<div style='font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #4f46e5; background-color: #f3f4f6; padding: 16px 28px; border-radius: 8px; text-align: center; margin: 16px 0; display: inline-block;'>{otp_code}</div>"
        )

    html = (
        "<div style='font-family: Arial, sans-serif; max-width: 500px; padding: 24px; border: 1px solid #e5e7eb; border-radius: 10px;'>"
        "<h2 style='color: #111827; margin-top: 0;'>Welcome to BebshaX</h2>"
        f"{otp_html}"
        "<p style='margin-top: 20px; font-size: 14px; color: #6b7280;'>Or click the button below to verify automatically:</p>"
        f'<p><a href="{verification_url}" style="display:inline-block; padding: 12px 24px; background-color: #4f46e5; color: white; border-radius: 6px; text-decoration: none; font-weight: bold;">Verify Email Address</a></p>'
        "<p style='font-size: 12px; color: #9ca3af;'>This verification code expires in 24 hours.</p>"
        "</div>"
    )
    return await send_email(to_email, subject, html)
