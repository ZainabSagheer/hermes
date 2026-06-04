"""LinkedIn UGC API client — text posts, image posts, and OAuth helpers."""

import time
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

_REDIRECT_PORT = 8765
_REDIRECT_URI = f"http://localhost:{_REDIRECT_PORT}/callback"
_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_SCOPES = "openid profile w_member_social w_organization_social"


def get_access_token(client_id: str, client_secret: str) -> str:
    """Full OAuth 2.0 PKCE-less flow — opens browser, captures callback, returns token."""
    auth_url = (
        _AUTH_URL + "?" + urllib.parse.urlencode({
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": _REDIRECT_URI,
            "scope": _SCOPES,
            "state": "hermas",
        })
    )

    code_holder: dict[str, str] = {}
    server_error: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                code_holder["code"] = params["code"][0]
                self._respond("<h2>Authorised. You can close this tab.</h2>")
            elif "error" in params:
                server_error.append(params.get("error_description", ["Unknown error"])[0])
                self._respond("<h2>Authorization failed. Check the terminal.</h2>")
            else:
                self._respond("<h2>Unexpected request.</h2>")

        def _respond(self, body: str):
            html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f0f4f8}}
.box{{background:white;padding:40px;border-radius:12px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.1)}}
h2{{color:#0a66c2}}p{{color:#555}}</style>
<script>setTimeout(()=>window.close(),3000);</script></head>
<body><div class="box"><h2>✅ Authorised!</h2><p>{body}</p>
<p style="margin-top:20px;font-size:13px;color:#999">This tab will close automatically.</p></div></body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            self.wfile.flush()

        def log_message(self, *_):
            pass  # silence access log

    server = HTTPServer(("localhost", _REDIRECT_PORT), Handler)
    server.timeout = 2  # short so the loop can check code_holder regularly

    webbrowser.open(auth_url)

    # Keep handling requests until the auth code arrives or we time out.
    # Browsers fire extra requests (favicon, prefetch) before the real callback —
    # consuming only one request would silently swallow those and miss the code.
    deadline = time.monotonic() + 120
    while not code_holder and not server_error:
        if time.monotonic() > deadline:
            break
        server.handle_request()

    # Stay alive a few extra seconds so browser follow-up requests
    # (favicon, etc.) don't hit ERR_CONNECTION_REFUSED.
    drain_until = time.monotonic() + 5
    while time.monotonic() < drain_until:
        server.handle_request()
    server.server_close()

    if server_error:
        raise RuntimeError(f"LinkedIn denied access: {server_error[0]}")
    if "code" not in code_holder:
        raise RuntimeError("No auth code received. Did you complete the browser flow?")

    # Exchange code for token
    r = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code_holder["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


class LinkedInClient:
    BASE = "https://api.linkedin.com/v2"

    def __init__(self, access_token: str, org_id: str | None = None) -> None:
        self._http = httpx.Client(
            base_url=self.BASE,
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        self._urn: str | None = None
        self._org_urn: str | None = f"urn:li:organization:{org_id}" if org_id else None

    # --- profile ---

    def person_urn(self) -> str:
        if not self._urn:
            # OpenID Connect apps use /v2/userinfo; sub == member ID
            r = self._http.get("/userinfo")
            r.raise_for_status()
            self._urn = f"urn:li:person:{r.json()['sub']}"
        return self._urn

    def author_urn(self) -> str:
        """Return org URN when posting as a page, else personal URN."""
        return self._org_urn if self._org_urn else self.person_urn()

    # --- image upload ---

    def upload_image(self, image_path: Path) -> str:
        """Upload an image file and return its LinkedIn asset URN."""
        urn = self.author_urn()

        # Step 1 — register upload
        reg = self._http.post(
            "/assets?action=registerUpload",
            json={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": urn,
                    "serviceRelationships": [
                        {
                            "relationshipType": "OWNER",
                            "identifier": "urn:li:userGeneratedContent",
                        }
                    ],
                }
            },
        )
        reg.raise_for_status()
        payload = reg.json()["value"]
        upload_url = payload["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = payload["asset"]

        # Step 2 — upload binary
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        up = httpx.put(
            upload_url,
            content=image_path.read_bytes(),
            headers={"Content-Type": mime},
            timeout=60,
        )
        up.raise_for_status()
        return asset_urn

    # --- posts ---

    def post_text(self, text: str, visibility: str = "PUBLIC") -> str:
        """Publish a text-only post. Returns the post URN."""
        r = self._http.post(
            "/ugcPosts",
            json=self._build_payload(text, visibility),
        )
        r.raise_for_status()
        return r.headers.get("x-restli-id", r.json().get("id", ""))

    def post_with_image(
        self,
        text: str,
        image_path: Path,
        alt_text: str = "",
        visibility: str = "PUBLIC",
    ) -> str:
        """Upload image then publish post. Returns the post URN."""
        asset_urn = self.upload_image(image_path)
        payload = self._build_payload(text, visibility)
        content = payload["specificContent"]["com.linkedin.ugc.ShareContent"]
        content["shareMediaCategory"] = "IMAGE"
        content["media"] = [
            {
                "status": "READY",
                "description": {"text": alt_text},
                "media": asset_urn,
                "title": {"text": ""},
            }
        ]
        r = self._http.post("/ugcPosts", json=payload)
        r.raise_for_status()
        return r.headers.get("x-restli-id", r.json().get("id", ""))

    # --- helpers ---

    def _build_payload(self, text: str, visibility: str) -> dict:
        return {
            "author": self.author_urn(),
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            },
        }
