"""Verify Cloudflare's signature, issuer, audience, and owner identity."""

import hmac
import secrets
from urllib.parse import urlsplit

from flask import current_app, g, request, session
import jwt

from .errors import Problem


def configure(app):
    issuer = app.config["ACCESS_ISSUER"].rstrip("/")
    if urlsplit(issuer).scheme != "https":
        raise RuntimeError("NEWS_ACCESS_ISSUER must use HTTPS.")
    app.extensions["access_keys"] = jwt.PyJWKClient(
        issuer + "/cdn-cgi/access/certs", timeout=5, lifespan=300
    )


def require(role):
    token = request.headers.get("Cf-Access-Jwt-Assertion", "")
    if not token or len(token) > 16_384:
        raise Problem(
            "Sign in through Cloudflare Access to continue.",
            401,
            "authentication_required",
        )
    try:
        key = current_app.extensions["access_keys"].get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=current_app.config["ACCESS_ISSUER"].rstrip("/"),
            audience=current_app.config["OWNER_AUD"]
            if role == "owner"
            else current_app.config["WORKER_AUD"],
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except jwt.InvalidAudienceError:
        raise Problem(
            "This credential cannot access this area.", 403, "forbidden"
        ) from None
    except (jwt.PyJWTError, ValueError, OSError):
        raise Problem(
            "Access credentials are invalid or expired.", 401, "invalid_credentials"
        ) from None
    if role == "owner":
        if (
            not isinstance(claims.get("email"), str)
            or claims["email"].casefold()
            != current_app.config["OWNER_EMAIL"].casefold()
        ):
            raise Problem("Only the owner can use the newsroom.", 403, "forbidden")
        g.owner = claims["email"]
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.form.get("csrf_token", "")
            if not hmac.compare_digest(supplied, session["csrf_token"]):
                raise Problem(
                    "This form expired. Reload the page and try again.",
                    403,
                    "csrf_failed",
                )
            origin = request.headers.get("Origin")
            if origin and origin != current_app.config["BASE_URL"].rstrip("/"):
                raise Problem("This form came from another site.", 403, "csrf_failed")
    else:
        if not isinstance(claims.get("common_name"), str) or not claims["common_name"]:
            raise Problem("Use the dedicated worker service token.", 403, "forbidden")
        g.worker = current_app.config["WORKER_ID"]
