import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import auth
import imagenes
import pdf
from auth import requiere
from db import BASE_DIR, get_db, init_db

app = Flask(__name__)


def _clave_secreta():
    """Clave de sesión: variable de entorno o archivo local que se crea la primera vez."""
    if os.environ.get("SIVENT_SECRET_KEY"):
        return os.environ["SIVENT_SECRET_KEY"]
    ruta = os.path.join(BASE_DIR, ".secret_key")
    if not os.path.exists(ruta):
        with open(ruta, "w") as f:
            f.write(secrets.token_hex(32))
    with open(ruta) as f:
        return f.read().strip()


app.secret_key = _clave_secreta()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("SIVENT_HTTPS") == "1",  # activar si se sirve por HTTPS
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                  MAX_CONTENT_LENGTH=6 * 1024 * 1024)  # tope de subida: foto de hasta 5 MB
auth.init_auth(app)
imagenes.init_app(app)
init_db()

import admin, catalogo, clientes, compras, inventario, reportes, ventas  # noqa: E402

for modulo in (catalogo, clientes, inventario, compras, ventas, reportes, admin):
    app.register_blueprint(modulo.bp)


@app.template_filter("soles")
def soles(v):
    return f"S/ {float(v or 0):,.2f}"


@app.template_filter("fh")
def fecha_hora(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return s or ""


@app.after_request
def cabeceras(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def error(e):
    mensajes = {400: e.description, 403: "Su rol no tiene acceso a esta sección.", 404: "No encontramos esa página.",
                413: "El archivo es demasiado grande. Las fotos pueden pesar hasta 5 MB."}
    if request.path.startswith("/api/"):
        return jsonify(error=mensajes[e.code]), e.code
    return render_template("error.html", codigo=e.code, mensaje=mensajes[e.code]), e.code


# ---------------------------------------------------------------- sesión
ACCESOS = {"admin": "Administrador", "vendedor": "Vendedor"}
INTENTOS_MAX, VENTANA_SEG = 5, 10 * 60
_fallos = defaultdict(list)  # (usuario, ip) -> instantes de los intentos fallidos recientes


def _bloqueado(clave):
    ahora_ = time.time()
    _fallos[clave] = [t for t in _fallos[clave] if ahora_ - t < VENTANA_SEG]
    return len(_fallos[clave]) >= INTENTOS_MAX


@app.route("/login", methods=["GET", "POST"])
def login():
    acceso = request.values.get("acceso", "admin")
    if acceso not in ACCESOS:
        acceso = "admin"
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip().lower()
        clave = (usuario, request.remote_addr)
        con = get_db()
        u = con.execute("""SELECT u.id, u.password, r.nombre AS rol FROM usuarios u JOIN roles r ON r.id=u.rol_id
                           WHERE u.usuario=? AND u.activo=1""", (usuario,)).fetchone()
        con.close()
        if _bloqueado(clave):
            flash("Demasiados intentos fallidos. Espere unos minutos e intente de nuevo.", "error")
        elif not (u and check_password_hash(u["password"], request.form.get("password", ""))):
            _fallos[clave].append(time.time())
            flash("Usuario o contraseña incorrectos.", "error")
        elif acceso == "admin" and u["rol"] != "ADMIN":
            flash("Esta cuenta no es de administrador. Ingrese por el acceso Vendedor.", "error")
        elif acceso == "vendedor" and u["rol"] == "ADMIN":
            flash("Las cuentas de administrador ingresan por el acceso Administrador.", "error")
        else:
            _fallos.pop(clave, None)
            session.clear()
            session.permanent = True
            session["uid"] = u["id"]
            destino = request.args.get("next", "")
            return redirect(destino if destino.startswith("/") and not destino.startswith("//") else url_for("inicio"))
    return render_template("login.html", acceso=acceso)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/cuenta", methods=["GET", "POST"])
@requiere()
def cuenta():
    if request.method == "POST":
        con = get_db()
        u = con.execute("SELECT password FROM usuarios WHERE id=?", (g.user["id"],)).fetchone()
        nueva, repetir = request.form.get("nueva", ""), request.form.get("repetir", "")
        if not check_password_hash(u["password"], request.form.get("actual", "")):
            flash("La contraseña actual no es correcta.", "error")
        elif len(nueva) < 8:
            flash("La nueva contraseña debe tener al menos 8 caracteres.", "error")
        elif nueva != repetir:
            flash("Las contraseñas nuevas no coinciden.", "error")
        else:
            con.execute("UPDATE usuarios SET password=? WHERE id=?", (generate_password_hash(nueva), g.user["id"]))
            con.close()
            flash("Contraseña actualizada.", "ok")
            return redirect(url_for("cuenta"))
        con.close()
    return render_template("cuenta.html")


# ---------------------------------------------------------------- inicio
def _resumen_ventas(con, hoy, usuario_id=None):
    filtro, extra = (" AND usuario_id=?", (usuario_id,)) if usuario_id else ("", ())
    return (con.execute(f"SELECT COUNT(*) n, COALESCE(SUM(total),0) t FROM ventas WHERE estado='EMITIDA' AND substr(fecha,1,10)=?{filtro}",
                        (hoy,) + extra).fetchone(),
            con.execute(f"SELECT COUNT(*) n, COALESCE(SUM(total),0) t FROM ventas WHERE estado='EMITIDA' AND substr(fecha,1,7)=?{filtro}",
                        (hoy[:7],) + extra).fetchone())


def _ultimas(con, usuario_id=None, limite=8):
    filtro, extra = (" AND v.usuario_id=?", (usuario_id,)) if usuario_id else ("", ())
    return con.execute(f"""SELECT v.id, v.fecha, v.total, v.tipo_comprobante, v.estado, c.nombre AS cliente, u.nombre_completo AS usuario
                           FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id JOIN usuarios u ON u.id=v.usuario_id
                           WHERE 1=1{filtro} ORDER BY v.id DESC LIMIT {limite}""", extra).fetchall()


def _stock_bajo(con):
    return con.execute("""SELECT p.codigo, p.nombre, p.imagen, COALESCE(i.cantidad,0) AS cantidad, p.stock_min
                          FROM productos p LEFT JOIN inventario i ON i.producto_id=p.id
                          WHERE p.activo=1 AND COALESCE(i.cantidad,0) <= p.stock_min
                          ORDER BY cantidad, p.nombre""").fetchall()


@app.route("/")
@requiere()
def inicio():
    p = g.user["permisos"]
    es_admin = g.user["rol"] == "ADMIN"
    hoy_dt = datetime.now()
    hoy = hoy_dt.strftime("%Y-%m-%d")
    d = {}
    con = get_db()
    if es_admin:
        d["hoy"], d["mes"] = _resumen_ventas(con, hoy)
        d["ultimas"] = _ultimas(con)
        d["bajos"] = _stock_bajo(con)
        d["compras"] = con.execute("SELECT id, fecha, proveedor, total FROM compras ORDER BY id DESC LIMIT 5").fetchall()
        d["empleados"] = con.execute("""
            SELECT u.nombre_completo AS nombre, COUNT(v.id) AS n, COALESCE(SUM(v.total),0) AS total
            FROM usuarios u JOIN ventas v ON v.usuario_id=u.id AND v.estado='EMITIDA' AND substr(v.fecha,1,7)=?
            GROUP BY u.id ORDER BY total DESC LIMIT 5""", (hoy[:7],)).fetchall()
        por_dia = {r["dia"]: r["t"] for r in con.execute(
            "SELECT substr(fecha,1,10) AS dia, SUM(total) AS t FROM ventas WHERE estado='EMITIDA' AND substr(fecha,1,10)>=? GROUP BY dia",
            ((hoy_dt - timedelta(days=6)).strftime("%Y-%m-%d"),))}
        dias = [(hoy_dt - timedelta(days=i)) for i in range(6, -1, -1)]
        mayor = max([por_dia.get(x.strftime("%Y-%m-%d"), 0) for x in dias] + [1])
        d["semana"] = [{"dia": x.strftime("%d/%m"),
                        "total": por_dia.get(x.strftime("%Y-%m-%d"), 0),
                        "pct": round(por_dia.get(x.strftime("%Y-%m-%d"), 0) / mayor * 100)} for x in dias]
        d["inv"] = con.execute("""SELECT COUNT(*) AS productos, COALESCE(SUM(COALESCE(i.cantidad,0)),0) AS unidades,
                                         COALESCE(SUM(COALESCE(i.cantidad,0)*p.precio_compra),0) AS costo,
                                         COALESCE(SUM(COALESCE(i.cantidad,0)*p.precio_venta),0) AS venta,
                                         COALESCE(SUM(CASE WHEN COALESCE(i.cantidad,0)=0 THEN 1 ELSE 0 END),0) AS agotados,
                                         COALESCE(SUM(CASE WHEN p.imagen='' THEN 1 ELSE 0 END),0) AS sin_foto
                                  FROM productos p LEFT JOIN inventario i ON i.producto_id=p.id WHERE p.activo=1""").fetchone()
        d["top"] = con.execute("""SELECT p.nombre, p.imagen, SUM(dv.cantidad) AS unidades, ROUND(SUM(dv.subtotal),2) AS total
                                  FROM detalle_ventas dv JOIN ventas v ON v.id=dv.venta_id AND v.estado='EMITIDA'
                                  JOIN productos p ON p.id=dv.producto_id WHERE substr(v.fecha,1,7)=?
                                  GROUP BY p.id ORDER BY unidades DESC, total DESC LIMIT 5""", (hoy[:7],)).fetchall()
        plantilla = "inicio_admin.html"
    else:
        if "ventas" in p:
            d["hoy"], d["mes"] = _resumen_ventas(con, hoy, g.user["id"])  # el vendedor ve solo lo suyo
            d["ultimas"] = _ultimas(con, g.user["id"], 6)
            d["productos"] = [dict(r) for r in con.execute(
                """SELECT p.codigo, p.nombre, p.precio_venta AS precio, COALESCE(i.cantidad,0) AS stock,
                          p.imagen AS img
                   FROM productos p LEFT JOIN inventario i ON i.producto_id=p.id WHERE p.activo=1 ORDER BY p.nombre""")]
            for p_ in d["productos"]:
                p_["img"] = imagenes.url(p_["img"], miniatura=True)
        if p & {"inventario", "catalogo", "compras"}:
            d["bajos"] = _stock_bajo(con)
        plantilla = "inicio_vendedor.html"
    con.close()
    return render_template(plantilla, d=d, serie=pdf.serie_numero)


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
