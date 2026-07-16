from __future__ import annotations

import os
import secrets
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort, jsonify, redirect, request

from app.db import get_db_connection

bp = Blueprint("shortener", __name__)

API_KEY = os.environ.get("SHORTENER_API_KEY", "acortador_ifop_2026").strip()

ALLOWED_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("SHORTENER_ALLOWED_HOSTS", "giscc.ifop.cl").split(",")
    if h.strip()
}


def _conn():
    # Reutiliza la configuración central del sistema (app/db.py)
    return get_db_connection()


def _require_api_key():
    if not API_KEY:
        abort(500, description="SHORTENER_API_KEY no configurada")
    if request.headers.get("X-API-Key", "") != API_KEY:
        abort(401)


def _validate_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        abort(400, description="url requerida")

    p = urlparse(u)
    if p.scheme not in {"http", "https"}:
        abort(400, description="scheme inválido")

    host = (p.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        abort(400, description=f"host no permitido: {host}")

    return u


def _new_slug(nbytes: int = 6) -> str:
    return secrets.token_urlsafe(nbytes).rstrip("=")


@bp.post("/api/shorten")
def api_shorten():
    _require_api_key()

    data = request.get_json(silent=True) or {}
    long_url = _validate_url(data.get("url"))

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Deduplicación opcional
            cur.execute(
                "SELECT slug FROM short_links WHERE long_url = %s LIMIT 1",
                (long_url,),
            )
            row = cur.fetchone()
            if row:
                slug = row["slug"]
                short_url = f"{request.url_root.rstrip('/')}/short/{slug}"
                return jsonify({"slug": slug, "short_url": short_url, "long_url": long_url})

            for _ in range(10):
                slug = _new_slug()
                try:
                    cur.execute(
                        "INSERT INTO short_links (slug, long_url) VALUES (%s, %s)",
                        (slug, long_url),
                    )
                    short_url = f"{request.url_root.rstrip('/')}/short/{slug}"
                    return jsonify({"slug": slug, "short_url": short_url, "long_url": long_url})
                except psycopg2.errors.UniqueViolation:
                    conn.rollback()
                    continue

    abort(500, description="no se pudo generar slug")


@bp.get("/short/<slug>")
def go(slug: str):
    slug = (slug or "").strip()
    if not slug:
        abort(404)

    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT long_url FROM short_links WHERE slug = %s LIMIT 1",
                (slug,),
            )
            row = cur.fetchone()
            if not row:
                abort(404)

            cur.execute(
                "UPDATE short_links SET hits = hits + 1, last_hit_at = NOW() WHERE slug = %s",
                (slug,),
            )

            return redirect(row["long_url"], code=302)