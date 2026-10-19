"""Sesión, permisos por rol y protección CSRF."""
import secrets
from functools import wraps

from flask import abort, g, jsonify, redirect, request, session, url_for

from db import MODULOS, get_db


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def init_auth(app):
    @app.before_request
    def cargar_usuario():
        g.user = None
        uid = session.get("uid")
        if not uid:
            return
        con = get_db()
        r = con.execute("""SELECT u.id, u.usuario, u.nombre_completo, r.nombre AS rol, r.permisos
                           FROM usuarios u JOIN roles r ON r.id = u.rol_id
                           WHERE u.id=? AND u.activo=1""", (uid,)).fetchone()
        con.close()
        if not r:
            session.clear()
            return
        permisos = set(MODULOS) if r["rol"] == "ADMIN" else {p for p in r["permisos"].split(",") if p in MODULOS}
        g.user = {"id": r["id"], "usuario": r["usuario"], "nombre": r["nombre_completo"],
                  "rol": r["rol"], "permisos": permisos}

    @app.before_request
    def proteger_csrf():
        if request.method == "POST" and request.endpoint != "static":
            enviado = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
            if not enviado or not secrets.compare_digest(enviado, session.get("csrf", "")):
                abort(400, "Sesión expirada. Recargue la página e intente de nuevo.")

    @app.context_processor
    def contexto():
        usuario = g.get("user")
        return {"user": usuario,
                "panel": None if not usuario else ("admin" if usuario["rol"] == "ADMIN" else "vendedor"),
                "puede": lambda *mods: bool(g.get("user")) and any(m in g.user["permisos"] for m in mods)}

    app.jinja_env.globals["csrf_token"] = csrf_token


def requiere(*modulos):
    """Exige sesión iniciada y, si se indican módulos, que el rol tenga al menos uno de ellos."""
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if g.user is None:
                if request.path.startswith("/api/"):
                    return jsonify(error="Sesión expirada. Inicie sesión de nuevo."), 401
                return redirect(url_for("login", next=request.path))
            if modulos and not any(m in g.user["permisos"] for m in modulos):
                abort(403)
            return f(*a, **k)
        return w
    return deco
