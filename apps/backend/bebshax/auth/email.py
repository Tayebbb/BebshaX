"""Email delivery service for BebshaX (SMTP / Gmail & Resend support)."""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from html import escape
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

    tls_context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10, context=tls_context) as server:
            server.login(username, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls(context=tls_context)
            server.login(username, password)
            server.send_message(msg)
    return True


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email using SMTP (Gmail) or Resend API."""
    settings = get_settings()

    # 1. Try SMTP if configured
    smtp_user = settings.smtp_username
    smtp_pass = settings.active_smtp_password
    if smtp_user and smtp_pass:
        try:
            # No literal fallbacks: sender/host come from Settings only. The
            # authenticated account is the sender when no from-address is set.
            from_addr = settings.email_from_address or smtp_user
            smtp_host = settings.smtp_host
            smtp_port = settings.smtp_port
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
            logger.info("Email sent via SMTP")
            return True
        except Exception:
            logger.warning(
                "SMTP email delivery failed. Trying Resend API fallback."
            )

    # 2. Fallback to Resend API
    api_key = settings.resend_api_key
    if api_key:
        from_addr = settings.email_from_address
        if not from_addr:
            logger.warning(
                "BEBSHAX_EMAIL_FROM_ADDRESS is not set; skipping Resend delivery."
            )
        else:
            try:
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
                    logger.info("Email sent via Resend API")
                    return True
                else:
                    logger.error("Resend API failed: %d", resp.status_code)
            except Exception:
                logger.error("Resend API delivery failed")

    logger.warning("No working email credentials configured; delivery skipped.")
    return False


def _console_code_fallback(purpose: str, otp_code: Optional[str]) -> None:
    """Print a one-time code to the log when nothing can deliver it.

    Strictly the local development environment: without this, a fresh signup
    on a machine with no mail transport can never be verified. Codes are
    single-use and expire in 15 minutes; the recipient address is never logged.
    """
    if otp_code and get_settings().environment == "development":
        logger.warning(
            "DEVELOPMENT ONLY (no email transport configured): the %s code just issued is %s",
            purpose, otp_code,
        )


async def send_verification_email(to_email: str, verification_url: str, otp_code: Optional[str] = None) -> bool:
    """Send a six-digit code and a token-free link to its entry page."""
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
        "<p style='margin-top: 20px; font-size: 14px; color: #6b7280;'>Open the verification page and enter your email address and code:</p>"
        f'<p><a href="{escape(verification_url, quote=True)}" style="display:inline-block; padding: 12px 24px; background-color: #4f46e5; color: white; border-radius: 6px; text-decoration: none; font-weight: bold;">Verify Email Address</a></p>'
        "<p style='font-size: 12px; color: #9ca3af;'>This verification code expires in 15 minutes and can be used only once.</p>"
        "</div>"
    )
    delivered = await send_email(to_email, subject, html)
    if not delivered:
        _console_code_fallback("verification", otp_code)
    return delivered


async def send_password_reset_email(to_email: str, otp_code: str) -> bool:
    delivered = await send_email(
        to_email,
        "Reset your BebshaX password",
        "<h2>Reset your BebshaX password</h2>"
        f"<p>Your password reset code is <strong>{otp_code}</strong>.</p>"
        "<p>This code expires in 15 minutes and can be used only once.</p>"
        "<p>If you did not request a password reset, ignore this email.</p>",
    )
    if not delivered:
        _console_code_fallback("password reset", otp_code)
    return delivered
