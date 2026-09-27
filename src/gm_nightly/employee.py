from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler

from .config import Config
from .models import digest


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_server_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Use the company origin without credentials, path or query")
    if not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("Company URL must be HTTPS (HTTP is allowed only on loopback)")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Non-local company servers require HTTPS")
    return url.rstrip("/")


def load_credentials(config: Config):
    if config.credentials_file:
        path = Path(config.credentials_file)
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("Credentials file must be readable only by its owner (chmod 600)")
        credentials = json.loads(path.read_text())
        for name in ("RIVER_API_KEY", "GBRAIN_REMOTE_CLIENT_SECRET"):
            if credentials.get(name):
                os.environ.setdefault(name, credentials[name])


def relay(config: Config, local, company, store) -> dict:
    """Read compiled personal Gbrain pages and write through official scoped company OAuth.

    Only these constructed Markdown pages cross the network. No trace journal, timeline,
    raw_data, local path, full get_page object, or source export is transmitted.
    """
    from .gbrain import note_markdown, shared_memory

    if not config.employee_id or not config.company_home:
        raise ValueError("Pair with the company Gbrain using employee install first")
    previous = store.get("relay_pages") or {}
    approved = {}
    for page in local.pages(config.share_tag, config.max_memories):
        memory = shared_memory(page, config.tenant, config.employee_id)
        if memory and len(memory.content) <= config.max_source_chars:
            slug = f"employees/{config.employee_id}/{digest(memory.id)[:24]}"
            approved[slug] = note_markdown(
                memory.title,
                memory.content,
                True,
                config.share_tag,
                {"gm_origin": digest(memory.id), "gm_employee": config.employee_id},
            )
    sent = withdrawn = 0
    for slug, markdown in approved.items():
        old = previous.get(slug, {})
        fingerprint = digest(markdown)
        if old.get("fingerprint") == fingerprint:
            continue
        intent = store.get("relay_pending:" + slug)
        if intent and (intent["content"] != markdown or intent["operation"] != "put"):
            raise RuntimeError(
                "An earlier relay write is unresolved; retry it before changing this page"
            )
        intent = intent or {
            "operation": "put",
            "content": markdown,
            "revision": old.get("revision"),
            "request_id": str(uuid.uuid4()),
        }
        store.put("relay_pending:" + slug, intent)
        result = company.put(slug, markdown, intent["revision"], intent["request_id"])
        previous[slug] = {"fingerprint": fingerprint, "revision": result["revision"]}
        store.put("relay_pages", previous)
        store.put("relay_pending:" + slug, None)
        sent += 1
    for slug in set(previous) - set(approved):
        intent = store.get("relay_pending:" + slug) or {
            "operation": "delete",
            "revision": previous[slug]["revision"],
            "request_id": str(uuid.uuid4()),
        }
        if intent["operation"] != "delete":
            raise RuntimeError("A relay write needs recovery before withdrawal")
        store.put("relay_pending:" + slug, intent)
        result = company.delete(slug, intent["revision"], intent["request_id"])
        if result.get("state") != "committed":
            raise RuntimeError("Gbrain has not committed the withdrawal")
        del previous[slug]
        store.put("relay_pages", previous)
        store.put("relay_pending:" + slug, None)
        withdrawn += 1
    result = {"shared_pages": len(approved), "sent": sent, "withdrawn": withdrawn}
    store.put("last_delivery", result)
    return result
