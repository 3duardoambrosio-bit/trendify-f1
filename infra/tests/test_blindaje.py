# infra/tests/test_blindaje.py
from infra.blindaje import Blindaje, LockType, LockStatus


def test_activate_and_check_lock(tmp_path):
    storage = tmp_path / "locks.jsonl"
    b = Blindaje(storage_path=storage)

    lock = b.activate_lock("TEST_LOCK", LockType.HARD, "testing")

    assert b.is_locked("TEST_LOCK") is True
    assert lock.lock_id == "TEST_LOCK"
    assert lock.lock_type == LockType.HARD
    assert lock.status == LockStatus.ACTIVE
    assert lock.reason == "testing"


def test_release_lock(tmp_path):
    storage = tmp_path / "locks.jsonl"
    b = Blindaje(storage_path=storage)

    b.activate_lock("LOCK_TO_RELEASE", LockType.SOFT, "initial")
    assert b.is_locked("LOCK_TO_RELEASE") is True

    released = b.release_lock("LOCK_TO_RELEASE", reason="done")

    assert released is not None
    assert released.status == LockStatus.RELEASED
    assert b.is_locked("LOCK_TO_RELEASE") is False
    assert released.metadata.get("release_reason") == "done"


def test_persistence_between_instances(tmp_path):
    storage = tmp_path / "locks.jsonl"

    # Primera instancia: crea el lock
    b1 = Blindaje(storage_path=storage)
    b1.activate_lock("PERSISTENT_LOCK", LockType.SOFT, "persist")

    # Segunda instancia: debe cargarlo desde disco
    b2 = Blindaje(storage_path=storage)
    assert b2.is_locked("PERSISTENT_LOCK") is True

    lock = b2.get_lock("PERSISTENT_LOCK")
    assert lock is not None
    assert lock.reason == "persist"
    assert lock.status == LockStatus.ACTIVE
