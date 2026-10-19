"""Compras a proveedores: cada compra ingresa mercadería al inventario."""
from flask import Blueprint, abort, g, jsonify, render_template, request, url_for

from auth import requiere
from db import aplicar_movimiento, ahora, get_db, transaccion
from util import num, rango_fechas

bp = Blueprint("compras", __name__)


@bp.route("/compras")
@requiere("compras")
def lista():
    desde, hasta = rango_fechas(request.args, dias=90)
    con = get_db()
    filas = con.execute("""
        SELECT c.id, c.fecha, c.proveedor, c.total, u.nombre_completo AS usuario,
               (SELECT COUNT(*) FROM detalle_compras d WHERE d.compra_id=c.id) AS items
        FROM compras c JOIN usuarios u ON u.id=c.usuario_id
        WHERE substr(c.fecha,1,10) BETWEEN ? AND ? ORDER BY c.id DESC LIMIT 300""", (desde, hasta)).fetchall()
    con.close()
    return render_template("compras.html", filas=filas, desde=desde, hasta=hasta,
                           total=sum(f["total"] for f in filas))


@bp.route("/compras/nueva")
@requiere("compras")
def nueva():
    con = get_db()
    filas = con.execute("""SELECT p.id, p.codigo, p.nombre, p.precio_compra, COALESCE(i.cantidad,0) AS stock
                           FROM productos p LEFT JOIN inventario i ON i.producto_id=p.id
                           WHERE p.activo=1 ORDER BY p.nombre""").fetchall()
    con.close()
    return render_template("compra_nueva.html", productos=[dict(r) for r in filas])


@bp.route("/api/compras", methods=["POST"])
@requiere("compras")
def api_crear():
    datos = request.get_json(silent=True) or {}
    proveedor = str(datos.get("proveedor", "")).strip()
    if not proveedor:
        return jsonify(error="Ingrese el proveedor."), 400
    try:
        pedido = {}
        for it in datos.get("items", []):
            pid = num(it.get("id"), "El producto", minimo=1, entero=True)
            cant = num(it.get("cantidad"), "La cantidad", minimo=1, entero=True)
            precio = num(it.get("precio"), "El precio unitario")
            antes = pedido.get(pid, (0, 0))
            # si el mismo producto llega dos veces se suman cantidades y se toma el último precio
            pedido[pid] = (antes[0] + cant, precio)
    except (ValueError, AttributeError, TypeError) as e:
        return jsonify(error=str(e) if isinstance(e, ValueError) else "La compra tiene datos no válidos."), 400
    if not pedido:
        return jsonify(error="Agregue al menos un producto a la compra."), 400

    con = get_db()
    try:
        with transaccion(con):
            total = round(sum(c * p for c, p in pedido.values()), 2)
            cid = con.execute("INSERT INTO compras(fecha,usuario_id,proveedor,total) VALUES (?,?,?,?)",
                              (ahora(), g.user["id"], proveedor, total)).lastrowid
            for pid, (cant, precio) in pedido.items():
                con.execute("""INSERT INTO detalle_compras(compra_id,producto_id,cantidad,precio_unit,subtotal)
                               VALUES (?,?,?,?,?)""", (cid, pid, cant, precio, round(cant * precio, 2)))
                aplicar_movimiento(con, pid, "ENTRADA", cant, f"Compra #{cid} - {proveedor}", g.user["id"])
                con.execute("UPDATE productos SET precio_compra=? WHERE id=?", (precio, pid))  # último costo
        return jsonify(id=cid, total=total, detalle=url_for("compras.detalle", cid=cid))
    except ValueError as e:
        return jsonify(error=str(e)), 409
    finally:
        con.close()


@bp.route("/compras/<int:cid>")
@requiere("compras")
def detalle(cid):
    con = get_db()
    c = con.execute("""SELECT c.*, u.nombre_completo AS usuario FROM compras c JOIN usuarios u ON u.id=c.usuario_id
                       WHERE c.id=?""", (cid,)).fetchone()
    if not c:
        con.close()
        abort(404)
    items = con.execute("""SELECT d.*, p.codigo, p.nombre FROM detalle_compras d JOIN productos p ON p.id=d.producto_id
                           WHERE d.compra_id=? ORDER BY d.id""", (cid,)).fetchall()
    con.close()
    return render_template("compra_detalle.html", c=c, items=items)
