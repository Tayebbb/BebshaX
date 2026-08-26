"""B6 Stage 1: owner_id columns. Must FAIL before fix, PASS after."""
from bebshax.db.models import Businesses, Personas


def test_businesses_has_owner_id():
    assert hasattr(Businesses, "owner_id")


def test_personas_has_owner_id():
    assert hasattr(Personas, "owner_id")


def test_businesses_owner_id_nullable():
    c = Businesses.__table__.c.get("owner_id")
    assert c is not None and c.nullable is True


def test_personas_owner_id_nullable():
    c = Personas.__table__.c.get("owner_id")
    assert c is not None and c.nullable is True


def test_businesses_owner_id_fk():
    c = Businesses.__table__.c.get("owner_id")
    fks = list(c.foreign_keys)
    assert len(fks) == 1 and "users.id" in str(fks[0].target_fullname)


def test_personas_owner_id_fk():
    c = Personas.__table__.c.get("owner_id")
    fks = list(c.foreign_keys)
    assert len(fks) == 1 and "users.id" in str(fks[0].target_fullname)
