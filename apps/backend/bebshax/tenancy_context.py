"""Request-local ownership for provenance; this does not authorize data egress."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


_tenant_owner_id: ContextVar[str | None] = ContextVar("bebshax_tenant_owner_id", default=None)


def get_tenant_owner_id() -> str | None:
    """Return the verified owner bound to the current task, or private unknown."""
    return _tenant_owner_id.get()


def _validate_owner(owner_id: str | None) -> None:
    if owner_id is not None and (
        not isinstance(owner_id, str) or not owner_id or len(owner_id) > 64 or owner_id != owner_id.strip()
    ):
        raise ValueError("Invalid tenant owner identity.")


@contextmanager
def tenant_scope(owner_id: str | None) -> Iterator[None]:
    """Bind a trusted identity for this task and restore the previous scope on exit."""
    _validate_owner(owner_id)
    token = _tenant_owner_id.set(owner_id)
    try:
        yield
    finally:
        _tenant_owner_id.reset(token)


def capture_provenance_owner(record: object) -> str | None:
    """Call synchronously at sink submission, not inside a deferred persistence task."""
    explicit_owner = getattr(record, "owner_id", None)
    _validate_owner(explicit_owner)
    request_owner = get_tenant_owner_id()
    if explicit_owner is not None and request_owner is not None and explicit_owner != request_owner:
        raise ValueError("Provenance owner conflicts with the verified request owner.")
    return explicit_owner if explicit_owner is not None else request_owner