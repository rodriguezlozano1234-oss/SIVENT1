"""Usuarios y roles (administrar el sistema)."""
import sqlite3

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth import requiere
from db import MODULOS, get_db, transaccion

bp = Blueprint("admin", __name__)


def _admins_activos(con, excluir_id=None):
    sql = """SELECT COUNT(*) FROM usuarios u JOIN roles r ON r.id=u.rol_id WHERE r.nombre='ADMIN' AND u.activo=1"""
    if excluir_id:
        return con.execute(sql + " AND u.id<>?", (excluir_id,)).fetchone()[0]
    return con.execute(sql).fetchone()[0]


# ---------------------------------------------------------------- usuarios
@bp.route("/usuarios")
@requiere("usuarios")
def usuarios():
    con = get_db()
    filas = con.execute("""SELECT u.id, u.nombre_completo, u.usuario, u.rol_id, u.activo, r.nombre AS rol
                           FROM usuarios u JOIN roles r ON r.id=u.rol_id ORDER BY u.activo DESC, u.nombre_completo""").fetchall()
    roles = con.execute("SELECT id, nombre FROM roles ORDER BY nombre").fetchall()
    con.close()
    return render_template("usuarios.html", usuarios=filas, roles=roles)


@bp.route("/usuarios/guardar", methods=["POST"])
@requiere("usuarios")
def usuario_guardar():
    f = request.form
    uid = f.get("id", "").strip()
    nombre = f.get("nombre_completo", "").strip()
    usuario = f.get("usuario", "").strip().lower()
    password = f.get("password", "")
    activo = 1 if f.get("activo") else 0
    con = get_db()
    try:
        if not nombre or not usuario:
            raise ValueError("Ingrese el nombre completo y el usuario.")
        if not usuario.replace("_", "").replace(".", "").isalnum():
            raise ValueError("El usuario solo puede tener letras, números, punto y guion bajo.")
        if (not uid or password) and len(password) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        with transaccion(con):
            rol = con.execute("SELECT id, nombre FROM roles WHERE id=?", (f.get("rol_id"),)).fetchone()
            if not rol:
                raise ValueError("Elija un rol válido.")
            if uid:
                uid = int(uid)
                if uid == g.user["id"] and (not activo or rol["nombre"] != "ADMIN"):
                    raise ValueError("No puede desactivarse ni quitarse el rol ADMIN a sí mismo.")
                if (not activo or rol["nombre"] != "ADMIN") and _admins_activos(con, uid) == 0:
                    raise ValueError("Debe quedar al menos un administrador activo.")
                con.execute("UPDATE usuarios SET nombre_completo=?, usuario=?, rol_id=?, activo=? WHERE id=?",
                            (nombre, usuario, rol["id"], activo, uid))
                if password:
                    con.execute("UPDATE usuarios SET password=? WHERE id=?", (generate_password_hash(password), uid))
                flash("Usuario actualizado.", "ok")
            else:
                con.execute("INSERT INTO usuarios(nombre_completo,usuario,password,rol_id,activo) VALUES (?,?,?,?,?)",
                            (nombre, usuario, generate_password_hash(password), rol["id"], activo))
                flash("Usuario creado.", "ok")
    except sqlite3.IntegrityError:
        flash("Ya existe un usuario con ese nombre de acceso.", "error")
    except ValueError as e:
        flash(str(e), "error")
    finally:
        con.close()
    return redirect(url_for("admin.usuarios"))


# ---------------------------------------------------------------- roles
@bp.route("/roles")
@requiere("usuarios")
def roles():
    con = get_db()
    filas = con.execute("""SELECT r.id, r.nombre, r.descripcion, r.permisos,
                           (SELECT COUNT(*) FROM usuarios u WHERE u.rol_id=r.id) AS usuarios
                           FROM roles r ORDER BY r.nombre""").fetchall()
    con.close()
    lista = [dict(r, lista=[p for p in r["permisos"].split(",") if p in MODULOS]) for r in filas]
    return render_template("roles.html", roles=lista, modulos=MODULOS)


@bp.route("/roles/guardar", methods=["POST"])
@requiere("usuarios")
def rol_guardar():
    f = request.form
    rid = f.get("id", "").strip()
    nombre = f.get("nombre", "").strip().upper()
    desc = f.get("descripcion", "").strip()
    permisos = [m for m in MODULOS if m in f.getlist("permisos")]
    con = get_db()
    try:
        if not nombre:
            raise ValueError("Ingrese el nombre del rol.")
        with transaccion(con):
            if rid:
                actual = con.execute("SELECT nombre FROM roles WHERE id=?", (rid,)).fetchone()
                if not actual:
                    raise ValueError("El rol ya no existe.")
                if actual["nombre"] == "ADMIN":
                    nombre, permisos = "ADMIN", list(MODULOS)  # el rol ADMIN no se puede recortar
                con.execute("UPDATE roles SET nombre=?, descripcion=?, permisos=? WHERE id=?",
                            (nombre, desc, ",".join(permisos), rid))
                flash("Rol actualizado. Los cambios aplican de inmediato a sus usuarios.", "ok")
            else:
                con.execute("INSERT INTO roles(nombre,descripcion,permisos) VALUES (?,?,?)", (nombre, desc, ",".join(permisos)))
                flash("Rol creado.", "ok")
    except sqlite3.IntegrityError:
        flash("Ya existe un rol con ese nombre.", "error")
    except ValueError as e:
        flash(str(e), "error")
    finally:
        con.close()
    return redirect(url_for("admin.roles"))


@bp.route("/roles/<int:rid>/eliminar", methods=["POST"])
@requiere("usuarios")
def rol_eliminar(rid):
    con = get_db()
    r = con.execute("SELECT nombre, (SELECT COUNT(*) FROM usuarios WHERE rol_id=roles.id) AS n FROM roles WHERE id=?", (rid,)).fetchone()
    if not r:
        flash("El rol ya no existe.", "error")
    elif r["nombre"] == "ADMIN":
        flash("El rol ADMIN no se puede eliminar.", "error")
    elif r["n"]:
        flash(f"No se puede eliminar: {r['n']} usuario(s) tienen este rol.", "error")
    else:
        con.execute("DELETE FROM roles WHERE id=?", (rid,))
        flash("Rol eliminado.", "ok")
    con.close()
    return redirect(url_for("admin.roles"))
