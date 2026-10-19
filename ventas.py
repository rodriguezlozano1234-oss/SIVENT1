"""Ventas: carrito, descuento de inventario, historial y comprobante PDF."""
from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

import imagenes
import pdf
from auth import requiere
from db import aplicar_movimiento, ahora, get_db, transaccion
from util import num, rango_fechas

bp = Blueprint("ventas", __name__)

VENTA_SQL = """SELECT v.*, c.nombre AS cliente_nombre, c.tipo_documento, c.numero_documento,
                      u.nombre_completo AS usuario_nombre
               FROM ventas v LEFT JOIN clientes c ON c.id=v.cliente_id JOIN usuarios u ON u.id=v.usuario_id"""


def _puede_ver(v):
    return "reportes" in g.user["permisos"] or v["usuario_id"] == g.user["id"]


@bp.route("/ventas")
@requiere("ventas")
def nueva():
    con = get_db()
    filas = con.execute("""SELECT p.id, p.codigo, p.nombre, p.precio_venta AS precio, p.stock_min, p.imagen,
                                  p.categoria_id AS cat, COALESCE(i.cantidad,0) AS stock
                           FROM productos p LEFT JOIN inventario i ON i.producto_id=p.id
                           WHERE p.activo=1 ORDER BY p.nombre COLLATE NOCASE""").fetchall()
    cats = con.execute("""SELECT id, nombre FROM categorias WHERE activo=1 AND id IN
                          (SELECT categoria_id FROM productos WHERE activo=1) ORDER BY nombre""").fetchall()
    con.close()
    productos = []
    for r in filas:
        d = dict(r)
        d["img"] = imagenes.url(d.pop("imagen"), miniatura=True)  # el JS pinta la foto o las iniciales
        productos.append(d)
    return render_template("ventas.html", productos=productos, categorias=cats)


@bp.route("/api/ventas", methods=["POST"])
@requiere("ventas")
def api_crear():
    datos = request.get_json(silent=True) or {}
    tipo = datos.get("tipo", "BOLETA")
    if tipo not in ("BOLETA", "FACTURA"):
        return jsonify(error="Tipo de comprobante no válido."), 400
    try:
        pedido = {}
        for it in datos.get("items", []):
            pid = num(it.get("id"), "El producto", minimo=1, entero=True)
            pedido[pid] = pedido.get(pid, 0) + num(it.get("cantidad"), "La cantidad", minimo=1, entero=True)
        cliente_id = datos.get("cliente_id")
        cliente_id = num(cliente_id, "El cliente", minimo=1, entero=True) if cliente_id else None
    except (ValueError, AttributeError, TypeError) as e:
        return jsonify(error=str(e) if isinstance(e, ValueError) else "El carrito tiene datos no válidos."), 400
    if not pedido:
        return jsonify(error="El carrito está vacío."), 400

    con = get_db()
    try:
        with transaccion(con):
            if cliente_id:
                cli = con.execute("SELECT tipo_documento FROM clientes WHERE id=? AND activo=1", (cliente_id,)).fetchone()
                if not cli:
                    raise ValueError("El cliente seleccionado ya no existe.")
            if tipo == "FACTURA" and not (cliente_id and cli["tipo_documento"] == "RUC"):
                raise ValueError("Para emitir una factura elija un cliente con RUC.")

            lineas, total = [], 0.0
            for pid, cant in pedido.items():
                p = con.execute("SELECT id, nombre, precio_venta FROM productos WHERE id=? AND activo=1", (pid,)).fetchone()
                if not p:
                    raise ValueError("Un producto del carrito ya no está disponible.")
                sub = round(p["precio_venta"] * cant, 2)  # el precio siempre se toma de la base de datos
                lineas.append((p["id"], cant, p["precio_venta"], sub))
                total += sub
            total = round(total, 2)
            vid = con.execute("INSERT INTO ventas(fecha,usuario_id,cliente_id,tipo_comprobante,total) VALUES (?,?,?,?,?)",
                              (ahora(), g.user["id"], cliente_id, tipo, total)).lastrowid
            for pid, cant, precio, sub in lineas:
                con.execute("""INSERT INTO detalle_ventas(venta_id,producto_id,cantidad,precio_unit,subtotal)
                               VALUES (?,?,?,?,?)""", (vid, pid, cant, precio, sub))
                aplicar_movimiento(con, pid, "SALIDA", cant, f"Venta #{vid}", g.user["id"])  # valida el stock
        return jsonify(id=vid, total=total, comprobante=url_for("ventas.comprobante", vid=vid))
    except ValueError as e:
        return jsonify(error=str(e)), 409
    finally:
        con.close()


@bp.route("/ventas/historial")
@requiere("ventas", "reportes")
def historial():
    desde, hasta = rango_fechas(request.args, dias=30)
    donde, args = ["substr(v.fecha,1,10) BETWEEN ? AND ?"], [desde, hasta]
    todas = "reportes" in g.user["permisos"]
    if not todas:
        donde.append("v.usuario_id=?")
        args.append(g.user["id"])
    con = get_db()
    filas = con.execute(f"{VENTA_SQL} WHERE {' AND '.join(donde)} ORDER BY v.id DESC LIMIT 300", args).fetchall()
    con.close()
    return render_template("ventas_historial.html", filas=filas, desde=desde, hasta=hasta, todas=todas,
                           total=sum(f["total"] for f in filas if f["estado"] == "EMITIDA"),
                           anuladas=sum(1 for f in filas if f["estado"] == "ANULADA"), serie=pdf.serie_numero)


def _cargar(vid):
    con = get_db()
    v = con.execute(f"{VENTA_SQL} WHERE v.id=?", (vid,)).fetchone()
    if not v or not _puede_ver(v):
        con.close()
        abort(404)
    items = con.execute("""SELECT d.*, p.codigo, p.nombre FROM detalle_ventas d JOIN productos p ON p.id=d.producto_id
                           WHERE d.venta_id=? ORDER BY d.id""", (vid,)).fetchall()
    con.close()
    return v, items


@bp.route("/ventas/<int:vid>")
@requiere("ventas", "reportes")
def detalle(vid):
    v, items = _cargar(vid)
    return render_template("venta_detalle.html", v=v, items=items, serie=pdf.serie_numero(v),
                           puede_anular=g.user["rol"] == "ADMIN" and v["estado"] == "EMITIDA")


@bp.route("/ventas/<int:vid>/comprobante.pdf")
@requiere("ventas", "reportes")
def comprobante(vid):
    v, items = _cargar(vid)
    return send_file(pdf.comprobante_pdf(v, items), mimetype="application/pdf",
                     download_name=f"{v['tipo_comprobante'].lower()}-{pdf.serie_numero(v)}.pdf")


@bp.route("/ventas/<int:vid>/anular", methods=["POST"])
@requiere("ventas", "reportes")
def anular(vid):
    """Anula una venta: devuelve el stock al inventario y la excluye de reportes y totales. Solo el administrador."""
    if g.user["rol"] != "ADMIN":
        abort(403)
    motivo = request.form.get("motivo", "").strip()[:200]
    con = get_db()
    try:
        if len(motivo) < 5:
            raise ValueError("Escriba el motivo de la anulación (mínimo 5 caracteres).")
        with transaccion(con):
            v = con.execute("SELECT id, estado FROM ventas WHERE id=?", (vid,)).fetchone()
            if not v:
                raise ValueError("La venta no existe.")
            if v["estado"] == "ANULADA":
                raise ValueError("Esa venta ya estaba anulada.")
            for d in con.execute("SELECT producto_id, cantidad FROM detalle_ventas WHERE venta_id=?", (vid,)).fetchall():
                aplicar_movimiento(con, d["producto_id"], "ENTRADA", d["cantidad"], f"Anulación de venta #{vid}",
                                   g.user["id"], permitir_inactivo=True)
            con.execute("""UPDATE ventas SET estado='ANULADA', anulada_fecha=?, anulada_por=?, anulada_motivo=? WHERE id=?""",
                        (ahora(), g.user["id"], motivo, vid))
        flash(f"Venta #{vid} anulada. El stock volvió al inventario.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    finally:
        con.close()
    return redirect(url_for("ventas.detalle", vid=vid))
