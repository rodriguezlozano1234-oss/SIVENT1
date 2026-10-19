"""Catálogo: vitrina con fotos, productos (con imagen) y categorías."""
import csv
import io
import secrets
import sqlite3

from flask import (Blueprint, Response, abort, flash, g, redirect, render_template, request, send_file,
                   send_from_directory, url_for)

import imagenes
import pdf
from auth import requiere
from db import UPLOADS_DIR, aplicar_movimiento, ahora, get_db, transaccion
from util import num

bp = Blueprint("catalogo", __name__)


def _codigo_libre(con, pid):
    base = f"P{pid:04d}"
    codigo, n = base, 1
    while con.execute("SELECT 1 FROM productos WHERE codigo=?", (codigo,)).fetchone():
        n += 1
        codigo = f"{base}-{n}"
    return codigo


# ---------------------------------------------------------------- fotos y vitrina
@bp.route("/media/productos/<archivo>")
@requiere()
def media(archivo):
    """Sirve las fotos subidas. Solo se aceptan nombres generados por el sistema."""
    if not imagenes.ARCHIVO.match(archivo):
        abort(404)
    resp = send_from_directory(UPLOADS_DIR, archivo, mimetype="image/webp", max_age=60 * 60 * 24 * 30)
    resp.headers["Cache-Control"] = "private, max-age=2592000, immutable"  # el nombre cambia si cambia la foto
    return resp


def _vitrina_filas(con, categoria=None, solo_disponibles=False):
    filas = con.execute("""
        SELECT p.id, p.codigo, p.nombre, p.descripcion, p.precio_compra, p.precio_venta, p.stock_min, p.imagen,
               p.categoria_id, c.nombre AS categoria, COALESCE(i.cantidad,0) AS stock, COALESCE(i.ubicacion,'') AS ubicacion
        FROM productos p JOIN categorias c ON c.id = p.categoria_id
        LEFT JOIN inventario i ON i.producto_id = p.id
        WHERE p.activo=1 ORDER BY p.nombre COLLATE NOCASE""").fetchall()
    if categoria:
        filas = [f for f in filas if f["categoria_id"] == categoria]
    if solo_disponibles:
        filas = [f for f in filas if f["stock"] > 0]
    return filas


@bp.route("/catalogo")
@requiere("catalogo", "ventas", "inventario")
def vitrina():
    con = get_db()
    filas = _vitrina_filas(con)
    cats = con.execute("""SELECT c.id, c.nombre, COUNT(p.id) AS n FROM categorias c
                          JOIN productos p ON p.categoria_id=c.id AND p.activo=1
                          WHERE c.activo=1 GROUP BY c.id ORDER BY c.nombre""").fetchall()
    con.close()
    return render_template("catalogo.html", productos=filas, categorias=cats,
                           ver_costo="catalogo" in g.user["permisos"],
                           sin_foto=sum(1 for f in filas if not f["imagen"]))


@bp.route("/catalogo/catalogo.pdf")
@requiere("catalogo", "ventas", "inventario")
def vitrina_pdf():
    """Catálogo imprimible para compartir con clientes: fotos y precios, sin costos ni stock."""
    cat = request.args.get("categoria", "")
    con = get_db()
    filas = _vitrina_filas(con, int(cat) if cat.isdigit() else None, request.args.get("disponibles") == "1")
    nombre_cat = None
    if cat.isdigit():
        r = con.execute("SELECT nombre FROM categorias WHERE id=?", (int(cat),)).fetchone()
        nombre_cat = r["nombre"] if r else None
    con.close()
    items = [{"codigo": f["codigo"], "nombre": f["nombre"], "categoria": f["categoria"], "precio": f["precio_venta"],
              "descripcion": f["descripcion"], "agotado": f["stock"] <= 0,
              "ruta": imagenes.ruta_archivo(f["imagen"], miniatura=True)} for f in filas]
    buf = pdf.catalogo_pdf(items, "Catálogo de productos" + (f" — {nombre_cat}" if nombre_cat else ""))
    return send_file(buf, mimetype="application/pdf", download_name="catalogo-sivent.pdf")


# ---------------------------------------------------------------- productos
@bp.route("/productos")
@requiere("catalogo")
def productos():
    con = get_db()
    filas = con.execute("""
        SELECT p.id, p.codigo, p.nombre, p.descripcion, p.precio_compra, p.precio_venta, p.categoria_id, p.imagen,
               p.stock_min, c.nombre AS categoria, COALESCE(i.cantidad,0) AS stock, COALESCE(i.ubicacion,'') AS ubicacion
        FROM productos p JOIN categorias c ON c.id = p.categoria_id
        LEFT JOIN inventario i ON i.producto_id = p.id
        WHERE p.activo=1 ORDER BY p.id DESC""").fetchall()
    cats = con.execute("SELECT id, nombre FROM categorias WHERE activo=1 ORDER BY nombre").fetchall()
    con.close()
    return render_template("productos.html", productos=filas, categorias=cats)


@bp.route("/productos/exportar.csv")
@requiere("catalogo")
def productos_csv():
    con = get_db()
    filas = con.execute("""
        SELECT p.codigo, p.nombre, c.nombre AS categoria, p.descripcion, p.precio_compra, p.precio_venta,
               COALESCE(i.cantidad,0) AS stock, p.stock_min, COALESCE(i.ubicacion,'') AS ubicacion
        FROM productos p JOIN categorias c ON c.id = p.categoria_id LEFT JOIN inventario i ON i.producto_id = p.id
        WHERE p.activo=1 ORDER BY p.nombre COLLATE NOCASE""").fetchall()
    con.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Código", "Producto", "Categoría", "Descripción", "P. compra", "P. venta", "Stock", "Stock mínimo", "Ubicación"])
    w.writerows([tuple(f) for f in filas])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=productos.csv"})


@bp.route("/productos/guardar", methods=["POST"])
@requiere("catalogo")
def producto_guardar():
    f = request.form
    pid = f.get("id", "").strip()
    try:
        nombre = f.get("nombre", "").strip()
        if not nombre:
            raise ValueError("Ingrese el nombre del producto.")
        codigo = f.get("codigo", "").strip().upper()
        descripcion = f.get("descripcion", "").strip()
        pv = num(f.get("precio_venta"), "El precio de venta")
        pc = num(f.get("precio_compra") or 0, "El precio de compra")
        smin = num(f.get("stock_min") or 0, "El stock mínimo", entero=True)
        cat = num(f.get("categoria_id"), "La categoría", entero=True)
        stock = 0 if pid else num(f.get("stock") or 0, "El stock inicial", entero=True)
        ubic = f.get("ubicacion", "").strip()
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("catalogo.productos"))

    # La foto se valida y se guarda aparte: si falla, el producto se guarda igual y se avisa.
    error_imagen, nueva = None, None
    try:
        nueva = imagenes.guardar(request.files.get("imagen"))
    except ValueError as e:
        error_imagen = str(e)
    quitar = bool(f.get("quitar_imagen")) and not nueva

    previa, guardado = "", False
    con = get_db()
    try:
        with transaccion(con):
            if not con.execute("SELECT 1 FROM categorias WHERE id=? AND activo=1", (cat,)).fetchone():
                raise ValueError("Elija una categoría válida.")
            if pid:
                fila = con.execute("SELECT imagen FROM productos WHERE id=? AND activo=1", (pid,)).fetchone()
                if not fila:
                    raise ValueError("El producto ya no existe.")
                previa = fila["imagen"]
                imagen = nueva or ("" if quitar else previa)
                con.execute("""UPDATE productos SET codigo=COALESCE(NULLIF(?,''),codigo), nombre=?, descripcion=?,
                               precio_compra=?, precio_venta=?, categoria_id=?, stock_min=?, imagen=? WHERE id=?""",
                            (codigo, nombre, descripcion, pc, pv, cat, smin, imagen, pid))
                mensaje = "Producto actualizado."
            else:
                cur = con.execute("""INSERT INTO productos(codigo,nombre,descripcion,precio_compra,precio_venta,categoria_id,stock_min,imagen)
                                     VALUES (?,?,?,?,?,?,?,?)""",
                                  (codigo or "TMP-" + secrets.token_hex(4), nombre, descripcion, pc, pv, cat, smin, nueva or ""))
                nuevo = cur.lastrowid
                if not codigo:
                    con.execute("UPDATE productos SET codigo=? WHERE id=?", (_codigo_libre(con, nuevo), nuevo))
                con.execute("INSERT INTO inventario(producto_id,cantidad,ubicacion,fecha_actualizacion) VALUES (?,0,?,?)",
                            (nuevo, ubic, ahora()))
                if stock > 0:
                    aplicar_movimiento(con, nuevo, "ENTRADA", stock, "Stock inicial", g.user["id"])
                mensaje = "Producto registrado."
        guardado = True
        flash(mensaje, "ok")
    except sqlite3.IntegrityError:
        flash("Ya existe un producto con ese código.", "error")
    except ValueError as e:
        flash(str(e), "error")
    finally:
        con.close()

    if guardado:
        if previa and (nueva or quitar):
            imagenes.borrar(previa)  # la foto anterior ya no se usa
    else:
        imagenes.borrar(nueva)  # no se guardó el producto: no dejar la foto huérfana
    if guardado and error_imagen:
        flash(f"El producto se guardó, pero la foto no: {error_imagen}", "error")
    return redirect(url_for("catalogo.productos"))


@bp.route("/productos/<int:pid>/eliminar", methods=["POST"])
@requiere("catalogo")
def producto_eliminar(pid):
    con = get_db()
    con.execute("UPDATE productos SET activo=0 WHERE id=?", (pid,))  # baja lógica: conserva el historial
    con.close()
    flash("Producto eliminado.", "ok")
    return redirect(url_for("catalogo.productos"))


# ---------------------------------------------------------------- categorías
@bp.route("/categorias")
@requiere("catalogo")
def categorias():
    con = get_db()
    filas = con.execute("""SELECT c.id, c.nombre, c.descripcion,
                           (SELECT COUNT(*) FROM productos p WHERE p.categoria_id=c.id AND p.activo=1) AS productos
                           FROM categorias c WHERE c.activo=1 ORDER BY c.nombre""").fetchall()
    con.close()
    return render_template("categorias.html", categorias=filas)


@bp.route("/categorias/guardar", methods=["POST"])
@requiere("catalogo")
def categoria_guardar():
    cid = request.form.get("id", "").strip()
    nombre = request.form.get("nombre", "").strip()
    desc = request.form.get("descripcion", "").strip()
    if not nombre:
        flash("Ingrese el nombre de la categoría.", "error")
        return redirect(url_for("catalogo.categorias"))
    con = get_db()
    try:
        with transaccion(con):
            if cid:
                con.execute("UPDATE categorias SET nombre=?, descripcion=? WHERE id=? AND activo=1", (nombre, desc, cid))
                flash("Categoría actualizada.", "ok")
            else:
                previa = con.execute("SELECT id, activo FROM categorias WHERE nombre=?", (nombre,)).fetchone()
                if previa and previa["activo"]:
                    raise ValueError("Ya existe una categoría con ese nombre.")
                if previa:  # estaba eliminada: se reactiva
                    con.execute("UPDATE categorias SET descripcion=?, activo=1 WHERE id=?", (desc, previa["id"]))
                else:
                    con.execute("INSERT INTO categorias(nombre,descripcion) VALUES (?,?)", (nombre, desc))
                flash("Categoría registrada.", "ok")
    except sqlite3.IntegrityError:
        flash("Ya existe una categoría con ese nombre.", "error")
    except ValueError as e:
        flash(str(e), "error")
    finally:
        con.close()
    return redirect(url_for("catalogo.categorias"))


@bp.route("/categorias/<int:cid>/eliminar", methods=["POST"])
@requiere("catalogo")
def categoria_eliminar(cid):
    con = get_db()
    n = con.execute("SELECT COUNT(*) FROM productos WHERE categoria_id=? AND activo=1", (cid,)).fetchone()[0]
    if n:
        flash(f"No se puede eliminar: la categoría tiene {n} producto(s). Muévalos a otra categoría primero.", "error")
    else:
        con.execute("UPDATE categorias SET activo=0 WHERE id=?", (cid,))
        flash("Categoría eliminada.", "ok")
    con.close()
    return redirect(url_for("catalogo.categorias"))
