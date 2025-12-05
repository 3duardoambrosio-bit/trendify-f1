from infra.idempotency_manager import IdempotencyManager


def test_generate_key_deterministic():
    manager = IdempotencyManager()
    operation = "test_operation"
    payload = {"key": "value"}

    key1 = manager.generate_key(operation, payload)
    key2 = manager.generate_key(operation, payload)

    assert key1 == key2


def test_generate_key_changes_with_payload():
    manager = IdempotencyManager()
    operation = "test_operation"

    key1 = manager.generate_key(operation, {"key": "value"})
    key2 = manager.generate_key(operation, {"key": "different"})

    assert key1 != key2


def test_store_and_retrieve_result():
    manager = IdempotencyManager()
    key = "test_key"
    result = {"status": "success"}

    manager.store_result(key, result)
    retrieved = manager.get_result(key)

    assert retrieved == result


def test_is_processed():
    manager = IdempotencyManager()
    key = "test_key"

    assert manager.is_processed(key) is False

    manager.store_result(key, {"result": "any"})
    assert manager.is_processed(key) is True
