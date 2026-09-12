"""Private processing scope for verified persona workflow owners."""

from collections.abc import Iterator
from contextlib import contextmanager

from bebshax.llm.governance import LLMRequestContext, get_llm_request_context, llm_request_context
from bebshax.tenancy import PUBLIC_OWNER_IDS
from bebshax.tenancy_context import get_tenant_owner_id, tenant_scope


@contextmanager
def private_persona_context(owner_id: str, study_id: str | None = None) -> Iterator[None]:
    if (not isinstance(owner_id, str) or not owner_id or owner_id != owner_id.strip()
            or len(owner_id) > 64 or owner_id in PUBLIC_OWNER_IDS):
        raise ValueError("Private persona processing requires a verified owner.")
    inherited = get_llm_request_context()
    owners = (get_tenant_owner_id(), inherited.owner_user_id if inherited is not None else None)
    if any(owner is not None and owner != owner_id for owner in owners):
        raise ValueError("Persona processing ownership conflicts with the verified caller.")
    if inherited is not None and inherited.study_id is not None and study_id is not None:
        if inherited.study_id != study_id:
            raise ValueError("Persona processing study conflicts with the verified scope.")
    with tenant_scope(owner_id), llm_request_context(LLMRequestContext(
        owner_user_id=owner_id, study_id=study_id, data_classification="private",
    )):
        yield