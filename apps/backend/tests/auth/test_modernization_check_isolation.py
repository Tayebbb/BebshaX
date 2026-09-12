"""The auth test launcher must not use workstation settings or real transports."""

import os
import asyncio
from pathlib import Path
import runpy
import smtplib
from unittest.mock import AsyncMock, patch

import dotenv
import httpx
import pytest


def test_owned_launcher_disables_dotenv_and_payment_configuration(monkeypatch) -> None:
    import sys

    monkeypatch.setattr(sys, "argv", ["security-checks"])
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: True)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *args: None)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", AsyncMock(return_value=None))
    monkeypatch.setattr(smtplib.SMTP, "connect", lambda *args: None)
    monkeypatch.setenv("BEBSHAX_STRIPE_SECRET_KEY", "private-workstation-placeholder")
    monkeypatch.setenv("BEBSHAX_STRIPE_WEBHOOK_SECRET", "private-workstation-placeholder")
    monkeypatch.setenv("BEBSHAX_PAYMENTS_ENABLED", "true")
    monkeypatch.setenv("COVERAGE_CORE", "ctrace")
    called = []

    def verify_isolation(args: list[str]) -> int:
        called.append(args)
        assert dotenv.load_dotenv("must-not-be-read.env") is False
        assert os.environ["BEBSHAX_STRIPE_SECRET_KEY"] == ""
        assert os.environ["BEBSHAX_STRIPE_WEBHOOK_SECRET"] == ""
        assert os.environ["BEBSHAX_PAYMENTS_ENABLED"] == "false"
        assert os.environ["COVERAGE_CORE"] == "sysmon"
        with pytest.raises(AssertionError, match="External"):
            httpx.HTTPTransport.handle_request(None, None)
        with pytest.raises(AssertionError, match="External"):
            asyncio.run(httpx.AsyncHTTPTransport.handle_async_request(None, None))
        with pytest.raises(AssertionError, match="External"):
            smtplib.SMTP.connect(None)
        return 0

    monkeypatch.setattr(pytest, "main", verify_isolation)
    launcher = runpy.run_path(str(Path(__file__).with_name("run_modernization_checks.py")))
    with patch.dict(os.environ):
        assert launcher["main"]() == 0
    assert len(called) == 1