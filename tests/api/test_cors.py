"""Cross-origin requests: the frontend (served from its own origin) may call the API, other sites may not."""

FRONTEND = "http://localhost:8080"  # the default CORS_ORIGINS


def preflight(client, origin, method="POST", headers="authorization,content-type"):
    return client.options(
        "/projects",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def test_preflight_from_the_frontend_is_allowed(client):
    response = preflight(client, FRONTEND)

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == FRONTEND
    allowed = response.headers["Access-Control-Allow-Headers"].lower()
    assert "authorization" in allowed
    assert "content-type" in allowed


def test_responses_to_the_frontend_carry_the_allow_origin_header(client):
    response = client.get("/health", headers={"Origin": FRONTEND})

    assert response.headers["Access-Control-Allow-Origin"] == FRONTEND
    # The frontend sends a bearer token, never cookies.
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_other_origins_are_not_allowed(client):
    response = preflight(client, "https://evil.example")

    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers
    assert (
        "Access-Control-Allow-Origin" not in client.get("/health", headers={"Origin": "https://evil.example"}).headers
    )


def test_unlisted_methods_are_not_allowed(client):
    assert preflight(client, FRONTEND, method="PATCH").status_code == 400
