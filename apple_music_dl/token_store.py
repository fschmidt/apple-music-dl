import keyring

SERVICE = "apple-music-dl"
ACCOUNT = "media-user-token"


def load() -> str | None:
    return keyring.get_password(SERVICE, ACCOUNT)


def save(token: str) -> None:
    keyring.set_password(SERVICE, ACCOUNT, token)


def clear() -> None:
    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass
