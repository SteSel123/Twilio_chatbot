"""Multi-tenant Twilio routing tests."""

from platform.business_profile import BusinessProfile, save_business_profile
from platform.tenant import resolve_tenant


def test_resolve_tenant_from_twilio_to(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.business_profile.BUSINESSES_DIR", tmp_path)
    profile = BusinessProfile(
        tenant_id="salon",
        business_name="Salon Test",
        twilio_whatsapp_from="whatsapp:+31987654321",
    )
    save_business_profile(profile)

    ctx = resolve_tenant(twilio_to="whatsapp:+31987654321")
    assert ctx.tenant_id == "salon"

    default_ctx = resolve_tenant(twilio_to="whatsapp:+10000000000")
    assert default_ctx.tenant_id == "default"
