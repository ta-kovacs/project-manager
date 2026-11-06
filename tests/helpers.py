"""Plain helpers shared by tests and fixtures (fixtures themselves live in tests/fixtures/)."""


def payload(base, overrides, exclude):
    """`base` with `overrides` applied and the `exclude`d fields left out."""
    payload = {**base, **overrides}
    for field in exclude:
        payload.pop(field)
    return payload


class BearerAuth:
    """Sends `Authorization: Bearer <token>`; pass as `auth=` to the test client.

    `username` is the user the token was issued to, when there is one.
    """

    def __init__(self, token, username=None):
        self.token = token
        self.username = username

    def __call__(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request
