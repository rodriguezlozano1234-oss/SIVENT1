"""Clientes (personas o empresas)."""
import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from auth import requiere
from db import get_db, transaccion
from util import REGLAS_DOC

bp = Blueprint("clientes", __name__)


def validar(d):
    tipo = (d.get("tipo_documento") or "DNI").strip().upper()
    if tipo not in REGLAS_DOC:
        raise ValueError("Tipo de documento no válido.")
    numero = re.sub(r"\s", "", d.get("numero_documento") or "").upper()
    regla, mensaje = REGLAS_DOC[tipo]
    if not regla.match(numero):
        raise ValueError(mensaje)
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("Ingrese el nombre o la razón social.")
    email = (d.get("email") or "").strip()
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("El correo electrónico no es válido.")
    return {"tipo": tipo, "numero": numero, "nombre": nombre, "telefono": (d.get("telefono") or "").strip()[:30],
            "email": email, "direccion": (d.get("direccion") or "").strip()}


def guardar_cliente(con, datos, cid=None):
    """Crea o actualiza un cliente (dentro de una transacción). Devuelve su id."""
    previo = con.execute("SELECT id, activo FROM clientes WHERE tipo_documento=? AND numero_documento=?",
                         (datos["tipo"], datos["numero"])).fetchone()
    campos = (datos["tipo"], datos["numero"], datos["nombre"], datos["telefono"], datos["email"], datos["direccion"])
    if cid:
        if previo and previo["id"] != int(cid):
            raise ValueError("Ya existe otro cliente con ese documento.")
        con.execute("""UPDATE clientes SET tipo_documento=?, numero_documento=?, nombre=?, telefono=?, email=?, direccion=?
                       WHERE id=? AND activo=1""", campos + (cid,))
        return int(cid)
    if previo:
        if previo["activo"]:
            raise ValueError("Ya existe un cliente con ese documento.")
        con.execute("""UPDATE clientes SET nombre=?, telefono=?, email=?, direccion=?, activo=1 WHERE id=?""",
                    campos[2:] + (previo["id"],))
        return previo["id"]
    cur = con.execute("""INSERT INTO clientes(tipo_documento,numero_documento,nombre,telefono,email,direccion)
                         VALUES (?,?,?,?,?,?)""", campos)
    return cur.lastrowid


@bp.route("/clientes")
@requiere("clientes")
def lista():
    con = get_db()
    filas = con.execute("""SELECT id, tipo_documento, numero_documento, nombre, telefono, email, direccion
                           FROM clientes WHERE activo=1 ORDER BY nombre""").fetchall()
    con.close()
    return render_template("clientes.html", clientes=filas)


@bp.route("/clientes/guardar", methods=["POST"])
@requiere("clientes")
def guardar():
    con = get_db()
    try:
        datos = validar(request.form)
        with transaccion(con):
            guardar_cliente(con, datos, request.form.get("id", "").strip() or None)
        flash("Cliente guardado.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    finally:
        con.close()
    return redirect(url_for("clientes.lista"))


@bp.route("/clientes/<int:cid>/eliminar", methods=["POST"])
@requiere("clientes")
def eliminar(cid):
    con = get_db()
    con.execute("UPDATE clientes SET activo=0 WHERE id=?", (cid,))
    con.close()
    flash("Cliente eliminado.", "ok")
    return redirect(url_for("clientes.lista"))


# --- API usada por la pantalla de ventas
@bp.route("/api/clientes")
@requiere("ventas", "clientes")
def api_buscar():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    con = get_db()
    filas = con.execute("""SELECT id, tipo_documento, numero_documento, nombre FROM clientes
                           WHERE activo=1 AND (nombre LIKE ? OR numero_documento LIKE ?) ORDER BY nombre LIMIT 12""",
                        (f"%{q}%", f"%{q}%")).fetchall()
    con.close()
    return jsonify([dict(r) for r in filas])


@bp.route("/api/clientes", methods=["POST"])
@requiere("ventas", "clientes")
def api_crear():
    con = get_db()
    try:
        datos = validar(request.get_json(silent=True) or {})
        with transaccion(con):
            cid = guardar_cliente(con, datos)
        return jsonify(id=cid, tipo_documento=datos["tipo"], numero_documento=datos["numero"], nombre=datos["nombre"])
    except ValueError as e:
        return jsonify(error=str(e)), 400
    finally:
        con.close()
