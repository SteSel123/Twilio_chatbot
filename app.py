"""Flask webhook server for Twilio WhatsApp."""

from __future__ import annotations

import logging
import os

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

from agent import BusinessAgent
from platform.business_profile import (
    BusinessProfile,
    list_business_profiles,
    load_business_profile,
    save_business_profile,
)
from config import (
    ADMIN_API_KEY,
    BASE_DIR,
    ENFORCE_HTTPS,
    FLASK_SECRET_KEY,
    IS_PRODUCTION,
    LANDING_URL,
    PORT,
    SENTRY_DSN,
    TWILIO_ACCOUNT_SID,
    TWILIO_API_KEY,
    TWILIO_API_SECRET,
)
from platform.auth import ADMIN_API_KEY as _ADMIN_KEY
from platform.auth import is_admin_authenticated, require_admin_api_key, require_admin_browser
from platform.billing import billing_enabled, create_checkout_session, handle_webhook
from platform.events import publish, start_event_worker
from platform.gdpr import erase_user_data, export_user_data
from platform.health import readiness_report
from platform.iot import handle_iot_payload
from platform.observability import log_structured, new_correlation_id
from platform.cors import apply_cors, handle_preflight
from platform.rate_limit import allow_ingress, allow_public
from platform.security_middleware import check_request_security
from platform.tenant import resolve_tenant
from storage import get_data_store
from webhook.handler import process_inbound_async, process_status_callback
from webhook.validator import validate_twilio_request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[FlaskIntegration()], traces_sample_rate=0.1)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = FLASK_SECRET_KEY or ADMIN_API_KEY or "dev-only-change-in-production"
agent = BusinessAgent()
start_event_worker()


@app.before_request
def _platform_context():
    preflight = handle_preflight()
    if preflight is not None:
        return preflight

    if ENFORCE_HTTPS and IS_PRODUCTION:
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        if proto != "https" and request.path not in ("/health", "/health/ready"):
            abort(403, description="HTTPS required")

    tenant = resolve_tenant(
        header_tenant=request.headers.get("X-Tenant-Id"),
        twilio_to=request.form.get("To") if request.path.startswith("/webhook") and request.method == "POST" else None,
    )
    g.tenant_id = tenant.tenant_id
    g.region = tenant.region
    if request.path.startswith("/webhook") and request.method == "POST":
        check_request_security(request)


@app.after_request
def _cors_headers(response):
    return apply_cors(response)


def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "service": "smb-whatsapp-assistant", "tenant": g.tenant_id}


@app.route("/health/ready", methods=["GET"])
def health_ready():
    report = readiness_report()
    status_code = 200 if report["status"] != "fail" else 503
    return jsonify(report), status_code


@app.route("/webhook/status", methods=["POST"])
def webhook_status():
    process_status_callback(request.form.to_dict())
    return "", 204


@app.route("/webhook", methods=["POST"])
def webhook():
    if not validate_twilio_request(request):
        abort(403, description="Invalid Twilio signature")

    form = request.form.to_dict()
    user_id = form.get("From", "")
    if user_id and not allow_ingress(g.tenant_id, user_id):
        log_structured("rate_limit_exceeded", user_id=user_id, tenant_id=g.tenant_id)
        abort(429, description="Rate limit exceeded")

    cid = new_correlation_id()
    publish("message.received", {"correlation_id": cid, "user_id": user_id, "tenant_id": g.tenant_id})
    from platform.business_profile import whatsapp_from_for_tenant
    from config import TWILIO_WHATSAPP_FROM

    whatsapp_from = whatsapp_from_for_tenant(g.tenant_id, TWILIO_WHATSAPP_FROM)
    process_inbound_async(form, agent.handle_message, tenant_id=g.tenant_id, whatsapp_from=whatsapp_from)
    from twilio.twiml.messaging_response import MessagingResponse

    response = MessagingResponse()
    return str(response), 200, {"Content-Type": "application/xml"}


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not _ADMIN_KEY:
        from platform.auth import render_admin_not_configured

        return render_admin_not_configured(), 503

    if is_admin_authenticated():
        return redirect(request.args.get("next") or url_for("admin_dashboard"))

    error = ""
    if request.method == "POST":
        key = request.form.get("admin_key", "")
        if key == _ADMIN_KEY:
            session["admin_authenticated"] = True
            session.permanent = True
            nxt = request.args.get("next") or url_for("admin_dashboard")
            return redirect(nxt)
        error = "Invalid admin key."

    return render_template("admin_login.html", error=error)


@app.route("/admin/logout", methods=["POST", "GET"])
def admin_logout():
    session.pop("admin_authenticated", None)
    return redirect(url_for("admin_login"))


@app.route("/admin/gdpr/export/<path:user_id>", methods=["GET"])
@require_admin_api_key
def gdpr_export(user_id: str):
    data = export_user_data(user_id, g.tenant_id)
    return jsonify(data)


@app.route("/admin/gdpr/erase/<path:user_id>", methods=["DELETE"])
@require_admin_api_key
def gdpr_erase(user_id: str):
    erase_user_data(user_id, g.tenant_id)
    log_structured("gdpr_erase", user_id=user_id, tenant_id=g.tenant_id)
    return jsonify({"status": "erased", "user_id": user_id})


@app.route("/admin/business", methods=["GET"])
@require_admin_api_key
def admin_list_businesses():
    profiles = []
    for tid in list_business_profiles():
        p = load_business_profile(tid)
        profiles.append({"tenant_id": tid, **p.to_dict()})
    return jsonify({"businesses": profiles})


@app.route("/admin/business/<tenant_id>", methods=["GET", "PUT"])
@require_admin_api_key
def admin_business_profile(tenant_id: str):
    if request.method == "GET":
        return jsonify(load_business_profile(tenant_id).to_dict())

    data = request.get_json(silent=True) or {}
    current = load_business_profile(tenant_id)
    updated = BusinessProfile(
        tenant_id=tenant_id,
        business_name=data.get("business_name", current.business_name),
        industry=data.get("industry", current.industry),
        tagline=data.get("tagline", current.tagline),
        welcome_message=data.get("welcome_message", current.welcome_message),
        system_prompt_extra=data.get("system_prompt_extra", current.system_prompt_extra),
        enabled_tools=data.get("enabled_tools", current.enabled_tools),
        docs_subdir=data.get("docs_subdir", current.docs_subdir),
        language_default=data.get("language_default", current.language_default),
        web_search_hint=data.get("web_search_hint", current.web_search_hint),
        external_mcp_servers=data.get("external_mcp_servers", current.external_mcp_servers),
        subscription_tier=data.get("subscription_tier", current.subscription_tier),
        twilio_whatsapp_from=data.get("twilio_whatsapp_from", current.twilio_whatsapp_from),
        google_calendar_id=data.get("google_calendar_id", current.google_calendar_id),
        review_url=data.get("review_url", current.review_url),
        handoff_slack_webhook=data.get("handoff_slack_webhook", current.handoff_slack_webhook),
    )
    save_business_profile(updated)
    agent.reload_docs(tenant_id)
    return jsonify({"status": "saved", "profile": updated.to_dict()})


@app.route("/admin/business", methods=["POST"])
@require_admin_api_key
def admin_create_business():
    data = request.get_json(silent=True) or {}
    tenant_id = (data.get("tenant_id") or "").strip()
    if not tenant_id or not tenant_id.replace("_", "").replace("-", "").isalnum():
        return jsonify({"error": "Valid tenant_id required (alphanumeric, dash, underscore)"}), 400
    if _profile_path_exists(tenant_id):
        return jsonify({"error": "Tenant already exists"}), 409

    profile = BusinessProfile(
        tenant_id=tenant_id,
        business_name=data.get("business_name", tenant_id.title()),
        industry=data.get("industry", "general"),
        docs_subdir=data.get("docs_subdir", tenant_id),
    )
    save_business_profile(profile)
    docs_dir = BASE_DIR / "docs" / profile.docs_subdir
    docs_dir.mkdir(parents=True, exist_ok=True)
    agent.reload_docs(tenant_id)
    return jsonify({"status": "created", "profile": profile.to_dict()}), 201


def _profile_path_exists(tenant_id: str) -> bool:
    from platform.business_profile import _profile_path
    return _profile_path(tenant_id).exists()


@app.route("/admin/business/<tenant_id>", methods=["DELETE"])
@require_admin_api_key
def admin_delete_business(tenant_id: str):
    from platform.business_profile import _profile_path

    path = _profile_path(tenant_id)
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    if tenant_id == "default":
        return jsonify({"error": "Cannot delete default tenant"}), 400
    path.unlink()
    return jsonify({"status": "deleted", "tenant_id": tenant_id})


@app.route("/admin/analytics", methods=["GET"])
@require_admin_api_key
def admin_analytics():
    from platform.analytics import get_dashboard_stats
    from platform.tiers import get_tenant_tier, tier_config

    tenant = request.args.get("tenant_id") or g.tenant_id
    days = int(request.args.get("days", 30))
    stats = get_dashboard_stats(tenant, days=days)
    stats["tier"] = get_tenant_tier(tenant)
    stats["tier_limits"] = tier_config(tenant)
    return jsonify(stats)


@app.route("/admin/outbound", methods=["GET", "POST"])
@require_admin_api_key
def admin_outbound():
    from platform.outbound import list_jobs, schedule_message

    tenant = request.args.get("tenant_id") or g.tenant_id
    if request.method == "GET":
        status = request.args.get("status")
        return jsonify({"jobs": list_jobs(tenant, status=status)})

    data = request.get_json(silent=True) or {}
    job_id = schedule_message(
        tenant,
        data.get("user_id", ""),
        data.get("job_type", "custom"),
        data.get("body", ""),
        metadata=data.get("metadata"),
    )
    return jsonify({"status": "scheduled", "job_id": job_id})


@app.route("/admin/docs/upload", methods=["POST"])
@require_admin_api_key
def admin_upload_docs():
    from config import BASE_DIR

    tenant = request.form.get("tenant_id") or g.tenant_id
    profile = load_business_profile(tenant)
    docs_dir = BASE_DIR / "docs" / profile.docs_subdir
    docs_dir.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for key in request.files:
        f = request.files[key]
        if f.filename:
            safe_name = f.filename.replace("..", "").replace("/", "_")
            dest = docs_dir / safe_name
            f.save(dest)
            uploaded.append(safe_name)
            from platform.document_pipeline import ingest_uploaded_file

            sidecar = ingest_uploaded_file(dest, docs_dir)
            if sidecar and sidecar != dest:
                uploaded.append(sidecar.name)

    if uploaded:
        agent.reload_docs(tenant)
    return jsonify({"status": "ok", "uploaded": uploaded, "docs_dir": str(docs_dir.relative_to(BASE_DIR))})


@app.route("/admin/dashboard", methods=["GET"])
@require_admin_browser
def admin_dashboard():
    from platform.analytics import get_dashboard_stats
    from platform.tiers import get_tenant_tier, tier_config

    store = get_data_store()
    tenant = request.args.get("tenant_id") or g.tenant_id
    profile = load_business_profile(tenant)
    stats = get_dashboard_stats(tenant, days=30)
    stats.update({
        "service": "AppAssist",
        "tenant": tenant,
        "business": profile.business_name,
        "tier": get_tenant_tier(tenant),
        "tier_limits": tier_config(tenant),
        "businesses": list_business_profiles(),
    })
    if hasattr(store, "_connect"):
        try:
            with store._connect() as conn:
                if hasattr(conn, "cursor"):
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM users")
                    stats["active_users"] = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM reply_feedback WHERE rating = 1")
                    stats["positive_feedback"] = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM reply_feedback WHERE rating = 0")
                    stats["negative_feedback"] = cur.fetchone()[0]
        except Exception as exc:
            stats["db_error"] = str(exc)
    return render_template("admin.html", stats=stats, profile=profile.to_dict())


@app.route("/billing/checkout", methods=["POST"])
def billing_checkout():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "")
    tier = data.get("tier", "standard")
    if not user_id or not billing_enabled():
        return jsonify({"error": "billing not configured"}), 400
    url = create_checkout_session(
        user_id,
        tier,
        success_url=data.get("success_url", ""),
        cancel_url=data.get("cancel_url", ""),
        tenant_id=data.get("tenant_id", g.tenant_id),
    )
    return jsonify({"checkout_url": url})


@app.route("/billing/webhook", methods=["POST"])
def billing_webhook():
    sig = request.headers.get("Stripe-Signature", "")
    result = handle_webhook(request.data, sig, get_data_store)
    return jsonify(result)


@app.route("/public/signup", methods=["POST"])
def public_signup():
    """Landing page — create business tenant + setup URL."""
    if not allow_public(_client_ip()):
        return jsonify({"error": "Too many requests. Try again later."}), 429

    from platform.onboarding import create_business_signup

    data = request.get_json(silent=True) or {}
    try:
        result = create_business_signup(
            business_name=data.get("business_name", ""),
            email=data.get("email", ""),
            business_city=data.get("business_city", ""),
            specialization=data.get("specialization", ""),
            industry=data.get("industry", ""),
            tier=data.get("tier", "starter"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    log_structured("public_signup", tenant_id=result["tenant_id"], email=data.get("email", ""))
    return jsonify(result), 201


@app.route("/public/checkout", methods=["POST"])
def public_checkout():
    """Landing page — signup + Stripe checkout in one step."""
    if not allow_public(_client_ip()):
        return jsonify({"error": "Too many requests. Try again later."}), 429

    from platform.onboarding import create_business_signup

    data = request.get_json(silent=True) or {}
    tier = data.get("tier", "starter")
    if tier == "enterprise":
        return jsonify({"error": "Contact us for Enterprise pricing", "contact": True}), 400

    try:
        signup = create_business_signup(
            business_name=data.get("business_name", ""),
            email=data.get("email", ""),
            business_city=data.get("business_city", ""),
            specialization=data.get("specialization", ""),
            industry=data.get("industry", ""),
            tier=tier,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not billing_enabled():
        return jsonify({
            "status": "signup_only",
            "message": "Billing not configured — account created",
            **signup,
        })

    checkout_url = create_checkout_session(
        data.get("email") or signup["tenant_id"],
        tier,
        success_url=data.get("success_url", signup["setup_url"]),
        cancel_url=data.get("cancel_url", ""),
        tenant_id=signup["tenant_id"],
    )
    if not checkout_url:
        return jsonify({"error": "Could not create checkout session", **signup}), 502

    return jsonify({"checkout_url": checkout_url, **signup})


@app.route("/public/demo", methods=["POST"])
def public_demo():
    """Landing page — book a demo / contact sales."""
    if not allow_public(_client_ip()):
        return jsonify({"error": "Too many requests. Try again later."}), 429

    from platform.onboarding import record_demo_request

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400

    req_id = record_demo_request(
        name=name,
        email=email,
        business_name=data.get("business_name", ""),
        message=data.get("message", ""),
    )
    log_structured("demo_request", request_id=req_id, email=email)
    return jsonify({"status": "ok", "message": "We will contact you within 1 business day.", "id": req_id})


@app.route("/demo-site/<industry>")
def demo_site(industry: str):
    """Minimal demo websites for setup preview (same content as standaard menu)."""
    from platform.setup_preview import render_demo_site_html

    return render_demo_site_html(industry)


def _enrich_preview_result(result: dict) -> dict:
    from platform.setup_preview import resolve_static_image_url

    img = result.get("source_image_url") or ""
    if img and not img.startswith("http"):
        result["source_image_url"] = resolve_static_image_url(
            img,
            lambda filename: url_for("static", filename=filename, _external=True),
        )
    return result


@app.route("/setup", methods=["GET"])
def setup_page():
    """Post-signup onboarding — connect Google Calendar."""
    from platform.google_oauth import get_connection_info, oauth_configured
    from platform.onboarding import get_setup_email, verify_setup_token
    from platform.setup_preview import vision_available

    tenant_id = request.args.get("tenant", "")
    token = request.args.get("token", "")
    if not tenant_id or not token or not verify_setup_token(tenant_id, token):
        abort(403, description="Invalid or expired setup link")

    profile = load_business_profile(tenant_id)
    google = get_connection_info(tenant_id)
    return render_template(
        "setup.html",
        tenant_id=tenant_id,
        token=token,
        profile=profile.to_dict(),
        signup_email=get_setup_email(tenant_id),
        google=google,
        oauth_available=oauth_configured(),
        vision_available=vision_available(),
        business_name=profile.business_name,
        business_city=profile.business_city or "",
        specialization=profile.specialization or "",
        landing_url=LANDING_URL,
    )


@app.route("/setup/knowledge-preview", methods=["POST"])
def setup_knowledge_preview():
    """Google lookup from signup data, or temporary photo scan (not stored)."""
    import tempfile
    from pathlib import Path

    from platform.onboarding import get_setup_email, verify_setup_token
    from platform.setup_preview import (
        allowed_image,
        process_business_lookup,
        process_demo_sample,
        process_knowledge_upload,
        vision_available,
    )

    tenant_id = request.form.get("tenant_id", "")
    token = request.form.get("token", "")
    if not tenant_id or not token or not verify_setup_token(tenant_id, token):
        return jsonify({"error": "Invalid or expired setup link"}), 403

    profile = load_business_profile(tenant_id)
    demo_id = (request.form.get("demo_id") or "").strip()
    owner_email = get_setup_email(tenant_id)

    if demo_id:
        try:
            result = process_demo_sample(
                tenant_id=tenant_id,
                demo_id=demo_id,
                business_name=profile.business_name,
                industry=profile.industry,
                owner_email=owner_email,
            )
            agent.reload_docs(tenant_id)
            return jsonify({"status": "ok", **_enrich_preview_result(result)})
        except Exception as exc:
            logger.error("Demo preview failed for %s: %s", tenant_id, exc)
            return jsonify({"error": str(exc)}), 400

    file = request.files.get("photo")
    if file and file.filename:
        if not vision_available():
            return jsonify({
                "error": "Vision niet beschikbaar. Zet OPENAI_API_KEY of Ollama llava in.",
            }), 503
        if not allowed_image(file.filename, file.content_type or ""):
            return jsonify({"error": "Alleen foto's, PDF of screenshots (JPG, PNG, WebP, PDF)."}), 400
        data = file.read()
        if len(data) > 8 * 1024 * 1024:
            return jsonify({"error": "Bestand te groot (max 8 MB)."}), 400
        suffix = Path(file.filename).suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
            suffix = ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            result = process_knowledge_upload(
                tenant_id=tenant_id,
                business_name=profile.business_name,
                industry=profile.industry,
                image_path=tmp_path,
                source_name=file.filename,
                owner_email=owner_email,
                persist=False,
            )
            return jsonify({"status": "ok", **_enrich_preview_result(result)})
        except Exception as exc:
            logger.error("Knowledge preview failed for %s: %s", tenant_id, exc)
            msg = str(exc)
            if "Read timed out" in msg or "timed out" in msg.lower():
                msg = (
                    "Foto-analyse duurde te lang. Probeer een kleinere foto, "
                    "wacht even tot Ollama klaar is, of verhoog OLLAMA_VISION_TIMEOUT in .env."
                )
            return jsonify({"error": msg}), 500
        finally:
            tmp_path.unlink(missing_ok=True)

    business_query = (request.form.get("business_query") or profile.business_name or "").strip()
    business_city = (request.form.get("business_city") or profile.business_city or "").strip()
    if business_query:
        try:
            result = process_business_lookup(
                tenant_id=tenant_id,
                business_name=profile.business_name,
                industry=profile.industry,
                business_query=business_query,
                city=business_city,
                specialization=profile.specialization or "",
                owner_email=owner_email,
            )
            agent.reload_docs(tenant_id)
            return jsonify({"status": "ok", **_enrich_preview_result(result)})
        except Exception as exc:
            logger.error("Business lookup failed for %s: %s", tenant_id, exc)
            return jsonify({"error": str(exc)}), 400

    return jsonify({"error": "Geen bedrijfsgegevens gevonden. Probeer opnieuw aan te melden."}), 400


@app.route("/onboard/google/start", methods=["GET"])
def google_oauth_start():
    from platform.google_oauth import create_authorization_url, oauth_configured
    from platform.onboarding import verify_setup_token

    if not oauth_configured():
        abort(503, description="Google OAuth not configured on server")

    tenant_id = request.args.get("tenant", "")
    token = request.args.get("token", "")
    if not verify_setup_token(tenant_id, token):
        abort(403)

    url = create_authorization_url(tenant_id, token)
    from flask import redirect

    return redirect(url)


@app.route("/onboard/google/callback", methods=["GET"])
def google_oauth_callback():
    from platform.google_oauth import handle_oauth_callback
    from platform.onboarding import setup_url

    code = request.args.get("code", "")
    state = request.args.get("state", "")
    if not code or not state:
        abort(400, description="Missing OAuth parameters")

    try:
        result = handle_oauth_callback(code, state)
    except Exception as exc:
        logger.error("Google OAuth callback failed: %s", exc)
        abort(400, description=str(exc))

    from flask import redirect

    return redirect(setup_url(result["tenant_id"], result["setup_token"]) + "&google=connected")


@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy.html")


@app.route("/terms", methods=["GET"])
def terms():
    return render_template("terms.html")


@app.route("/iot/webhook", methods=["POST"])
def iot_webhook():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    body, status = handle_iot_payload(request.get_json(silent=True) or {}, token)
    return jsonify(body), status


@app.route("/", methods=["GET"])
def index():
    profile = load_business_profile(g.tenant_id)
    return render_template("index.html", profile=profile, tenant_id=g.tenant_id)


if __name__ == "__main__":
    if not TWILIO_ACCOUNT_SID or not TWILIO_API_KEY or not TWILIO_API_SECRET:
        logger.warning(
            "Twilio credentials not set — set TWILIO_ACCOUNT_SID, TWILIO_API_KEY, and TWILIO_API_SECRET in .env"
        )
    app.run(host="0.0.0.0", port=PORT, debug=os.getenv("FLASK_DEBUG", "0") == "1")
