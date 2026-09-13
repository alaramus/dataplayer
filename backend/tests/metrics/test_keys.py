from app.metrics import keys


def test_an_issued_key_is_long_and_different_every_time() -> None:
    issued = {keys.issue() for _ in range(50)}

    assert len(issued) == 50
    assert all(len(key) >= 32 for key in issued)


def test_the_fingerprint_is_stable_and_is_not_the_key() -> None:
    key = keys.issue()

    assert keys.fingerprint(key) == keys.fingerprint(key)
    assert key not in keys.fingerprint(key)


def test_a_sealed_key_opens_and_does_not_hold_it_in_the_clear() -> None:
    key = keys.issue()
    sealed = keys.seal(key)

    assert key.encode() not in sealed
    assert keys.unseal(sealed) == key
