"""Tests for SMB business profiles."""

from platform.business_profile import load_business_profile, save_business_profile, BusinessProfile


def test_load_default_profile_has_tools():
    p = load_business_profile("default")
    assert p.business_name
    assert "searchBusinessDocs" in p.enabled_tools


def test_save_and_reload_profile(tmp_path, monkeypatch):
    import platform.business_profile as bp

    monkeypatch.setattr(bp, "BUSINESSES_DIR", tmp_path)
    profile = BusinessProfile(
        tenant_id="testco",
        business_name="Test Co",
        industry="industrial",
    )
    save_business_profile(profile)
    loaded = load_business_profile("testco")
    assert loaded.business_name == "Test Co"
    assert loaded.industry == "industrial"
