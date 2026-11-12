from app.core.security import hash_password, password_needs_rehash, verify_password

PASSWORD = "correct horse battery staple"


def test_hash_does_not_contain_the_password() -> None:
    password_hash = hash_password(PASSWORD)

    assert PASSWORD not in password_hash
    assert password_hash.startswith("$argon2id$")


def test_hashing_the_same_password_twice_gives_different_hashes() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_verify_accepts_the_right_password_and_rejects_others() -> None:
    password_hash = hash_password(PASSWORD)

    assert verify_password(password_hash, PASSWORD)
    assert not verify_password(password_hash, "wrong password entirely")


def test_verify_rejects_a_malformed_hash() -> None:
    assert not verify_password("not-a-real-hash", PASSWORD)


def test_fresh_hash_does_not_need_rehash() -> None:
    assert not password_needs_rehash(hash_password(PASSWORD))
