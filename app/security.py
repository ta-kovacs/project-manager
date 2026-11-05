from pwdlib import PasswordHash

# Argon2id with pwdlib's recommended parameters.
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


# Verified against when the username doesn't exist, so a failed login takes
# the same time whether or not the user is registered.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def verify_dummy_password(password: str) -> None:
    _password_hash.verify(password, _DUMMY_HASH)
