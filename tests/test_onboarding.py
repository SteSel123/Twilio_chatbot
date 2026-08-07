"""Public signup and setup token tests."""

from pathlib import Path

from platform.onboarding import (
    create_business_signup,
    get_setup_email,
    record_demo_request,
    setup_url,
    verify_setup_token,
)


def test_create_signup_and_token():
    result = create_business_signup(
        business_name="Test Cafe OAuth",
        business_city="Utrecht",
        specialization="Italian restaurant",
        tier="starter",
    )
    assert result["tenant_id"]
    assert result["setup_token"]
    assert "setup?tenant=" in result["setup_url"]
    assert verify_setup_token(result["tenant_id"], result["setup_token"])
    assert get_setup_email(result["tenant_id"]).endswith("@pending.local")
    seed = Path("docs") / result["tenant_id"] / "branche-info.md"
    if seed.is_file():
        assert "Veelgestelde vragen" in seed.read_text(encoding="utf-8")


def test_create_signup_with_email():
    result = create_business_signup(
        business_name="Test With Email",
        business_city="Amsterdam",
        specialization="Hair salon",
        email="test@example.com",
    )
    assert get_setup_email(result["tenant_id"]) == "test@example.com"


def test_invalid_setup_token():
    assert not verify_setup_token("nonexistent-tenant", "bad-token")


def test_demo_request():
    req_id = record_demo_request(name="Jane", email="jane@example.com", business_name="Salon")
    assert req_id > 0


def test_setup_url_format():
    url = setup_url("salon-abc", "tok123")
    assert "tenant=salon-abc" in url
    assert "token=tok123" in url
