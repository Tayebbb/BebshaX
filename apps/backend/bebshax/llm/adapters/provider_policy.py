"""Fail-closed selection of remote primary providers from the SDK catalog."""

from __future__ import annotations

import ipaddress
import socket
import tomllib
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from freellmpool import config as fl_config
from freellmpool.models import Provider

_EXCLUDED_SERVICES = ("ollama", "openrouter")
_EXCLUDED_HOSTS = ("ollama.com", "ollama.ai", "openrouter.ai")
_SUPPORTED_TRANSPORTS = ("openai", "gemini", "cloudflare")


def load_primary_catalog(provider_config: Path) -> list[Provider]:
    """Packaged SDK catalog with the application-owned overrides applied by provider id."""
    packaged = fl_config.load_catalog(Path(fl_config.__file__).with_name("providers.toml"))
    overrides = fl_config.load_catalog(provider_config)
    by_id = {provider.id: provider for provider in packaged}
    by_id.update({provider.id: provider for provider in overrides})
    return list(by_id.values())


def configured_json_models(path: Path) -> frozenset[tuple[str, str]]:
    with path.open("rb") as source:
        catalog = tomllib.load(source)
    approved = set()
    for provider in catalog.get("provider", []):
        for model in provider.get("models", []):
            supports_json = model.get("supports_json")
            if supports_json is not None and type(supports_json) is not bool:
                raise ValueError("Configured supports_json must be an explicit boolean")
            if supports_json is True:
                approved.add((provider["id"], model["name"]))
    return frozenset(approved)


def _approved_url(url: str) -> bool:
    if any(character.isspace() or ord(character) < 32 for character in url):
        return False
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return False
        if not host or not host.isascii() or "%" in host or "\\" in host:
            return False
        if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
            return False
        if any(host == excluded or host.endswith("." + excluded) for excluded in _EXCLUDED_HOSTS):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            try:
                address = ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(host)))
            except OSError:
                return "." in host
        return address.is_global
    except ValueError:
        return False


def approved_primary_providers(
    catalog: Iterable[Provider], *, allowed_provider_ids: Iterable[str] | None = None,
) -> list[Provider]:
    allowed = frozenset(allowed_provider_ids) if allowed_provider_ids is not None else None
    approved = []
    for provider in catalog:
        if allowed is not None and provider.id not in allowed:
            continue
        if provider.id.casefold().startswith(_EXCLUDED_SERVICES):
            continue
        if (provider.key_env or "").casefold().startswith(_EXCLUDED_SERVICES):
            continue
        if provider.adapter not in _SUPPORTED_TRANSPORTS or not _approved_url(provider.base_url):
            continue
        models = tuple(
            model for model in provider.models
            if model.enabled and not model.name.casefold().startswith(
                tuple(service + "/" for service in _EXCLUDED_SERVICES)
            )
        )
        if models:
            approved.append(replace(provider, models=models))
    return approved