"""Recovery mail content and delivery logs follow the bounded challenge contract."""

import ssl
from unittest.mock import AsyncMock, Mock

import pytest

from bebshax.auth import email as auth_email


async def test_verification_mail_describes_manual_fifteen_minute_code(monkeypatch):
    mail = AsyncMock(return_value=True)
    monkeypatch.setattr(auth_email, "send_email", mail)
    await auth_email.send_verification_email("owner@example.test", "https://app.example.test/verify-email", "123456")
    address, subject, html = mail.call_args.args
    assert "15 minutes" in html
    assert "24 hours" not in html
    assert "automatically" not in html
    assert "?token=" not in html


async def test_delivery_logging_does_not_include_recipient(identity_state, monkeypatch, caplog):
    monkeypatch.setattr(auth_email, "get_settings", lambda: identity_state.settings)
    with caplog.at_level("WARNING"):
        assert await auth_email.send_email("private-address@example.test", "Synthetic subject", "Synthetic body") is False
    assert "private-address" not in caplog.text


async def test_development_without_transport_prints_the_code_but_never_the_recipient(identity_state, monkeypatch, caplog):
    """A local signup must stay completable when no mail transport exists."""
    assert identity_state.settings.environment == "development"
    monkeypatch.setattr(auth_email, "get_settings", lambda: identity_state.settings)
    with caplog.at_level("WARNING"):
        delivered = await auth_email.send_verification_email(
            "private-address@example.test", "http://127.0.0.1:5173/verify-email", otp_code="482913",
        )
        await auth_email.send_password_reset_email("private-address@example.test", "907341")
    assert delivered is False
    assert "DEVELOPMENT ONLY" in caplog.text
    assert "482913" in caplog.text and "907341" in caplog.text
    assert "private-address" not in caplog.text


@pytest.mark.parametrize("environment", ["production", "staging", "local"])
async def test_hosted_environments_never_print_one_time_codes(identity_state, monkeypatch, caplog, environment):
    settings = identity_state.settings.model_copy(update={"environment": environment})
    monkeypatch.setattr(auth_email, "get_settings", lambda: settings)
    with caplog.at_level("WARNING"):
        assert await auth_email.send_verification_email(
            "owner@example.test", "https://app.example.test/verify-email", otp_code="482913",
        ) is False
        assert await auth_email.send_password_reset_email("owner@example.test", "907341") is False
    assert "482913" not in caplog.text and "907341" not in caplog.text
    assert "DEVELOPMENT ONLY" not in caplog.text


@pytest.mark.parametrize("port", [465, 587])
def test_smtp_requires_verified_tls_before_authentication(monkeypatch, port) -> None:
    server = Mock()
    constructor = Mock()
    constructor.return_value.__enter__ = Mock(return_value=server)
    constructor.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(auth_email.smtplib, "SMTP_SSL" if port == 465 else "SMTP", constructor)

    assert auth_email._send_smtp_sync(
        "smtp.example.test", port, "sender@example.test", "synthetic-mail-proof",
        "sender@example.test", "owner@example.test", "Synthetic subject", "Synthetic body",
    ) is True

    tls_call = constructor.call_args if port == 465 else server.starttls.call_args
    context = tls_call.kwargs.get("context")
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    server.login.assert_called_once_with("sender@example.test", "synthetic-mail-proof")