"""B6: owner_id columns. Stage 1 added them nullable; stage 2 enforced NOT NULL."""
from bebshax.db.models import Businesses, Personas


def test_businesses_has_owner_id():
    assert hasattr(Businesses, "owner_id")


def test_personas_has_owner_id():
    assert hasattr(Personas, "owner_id")


def test_businesses_owner_id_not_null():
    c = Businesses.__table__.c.get("owner_id")
    assert c is not None and c.nullable is False


def test_personas_owner_id_not_null():
    c = Personas.__table__.c.get("owner_id")
    assert c is not None and c.nullable is False


def test_businesses_owner_id_fk():
    c = Businesses.__table__.c.get("owner_id")
    fks = list(c.foreign_keys)
    assert len(fks) == 1 and "users.id" in str(fks[0].target_fullname)


def test_personas_owner_id_fk():
    c = Personas.__table__.c.get("owner_id")
    fks = list(c.foreign_keys)
    assert len(fks) == 1 and "users.id" in str(fks[0].target_fullname)
