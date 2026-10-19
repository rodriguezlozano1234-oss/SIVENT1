"""Stock por producto y movimientos (entradas, salidas y ajustes)."""
import csv
import io

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from auth import requiere
from db import aplicar_movimiento, get_db, transaccion
from util import num, rango_fechas

bp = Blueprint("inventario", __name__)


@bp.route("/inventario")
@requiere("inventario")
def lista():
    con = get_db()
    filas = con.execute("""
        SELECT p.id, p.codigo, p.nombre, p.imagen, c.nombre AS categoria, p.stock_min, p.precio_compra, p.precio_venta,
               COALESCE(i.cantidad,0) AS cantidad, COALESCE(i.ubicacion,'') AS ubicacion, i.fecha_actualizacion
        FROM productos p JOIN categorias c ON c.id = p.categoria_id
        LEFT JOIN inventario i ON i.producto_id = p.id
        WHERE p.activo=1 ORDER BY p.nombre COLLATE NOCASE""").fetchall()
    con.close()
    kpi = {"unidades": sum(f["cantidad"] for f in filas),
           "costo": sum(f["cantidad"] * f["precio_compra"] for f in filas),
           "venta": sum(f["cantidad"] * f["precio_venta"] for f in filas),
           "agotados": sum(1 for f in filas if f["cantidad"] == 0),
           "bajos": sum(1 for f in filas if 0 < f["cantidad"] <= f["stock_min"])}
    return render_template("inventario.html", filas=filas, kpi=kpi)


@bp.route("/inventario/exportar.csv")
@requiere("inventario")
def exportar():
    con = get_db()
    filas = con.execute("""
        SELECT p.codigo, p.nombre, c.nombre AS categoria, COALESCE(i.cantidad,0) AS cantidad, p.stock_min,
               COALESCE(i.ubicacion,'') AS ubicacion, COALESCE(i.fecha_actualizacion,'') AS actualizado
        FROM productos p JOIN categorias c ON c.id = p.categoria_id LEFT JOIN inventario i ON i.producto_id = p.id
        WHERE p.activo=1 ORDER BY p.nombre COLLATE NOCASE""").fetchall()
    con.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Código", "Producto", "Categoría", "Stock", "Stock mínimo", "Estado", "Ubicación", "Actualizado"])
    for f in filas:
        estado = "Sin stock" if f["cantidad"] == 0 else "Stock bajo" if f["cantidad"] <= f["stock_min"] else "Normal"
        w.writerow([f["codigo"], f["nombre"], f["categoria"], f["cantidad"], f["stock_min"], estado, f["ubicacion"], f["actualizado"]])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=inventario.csv"})


@bp.route("/inventario/movimiento", methods=["POST"])
@requiere("inventario")
def movimiento():
    f = request.form
    tipo = f.get("tipo", "")
    con = get_db()
    try:
        pid = num(f.get("producto_id"), "El producto", entero=True)
        cantidad = num(f.get("cantidad"), "La cantidad" if tipo != "AJUSTE" else "El stock contado", entero=True)
        motivo = f.get("motivo", "").strip()
        if not motivo:
            raise ValueError("Indique el motivo del movimiento.")
        with transaccion(con):
            anterior, nuevo = aplicar_movimiento(con, pid, tipo, cantidad, motivo, g.user["id"])
        flash(f"Movimiento registrado: el stock pasó de {anterior} a {nuevo}.", "ok")
    except ValueError as e:
        flash(str(e), "error")
    finally:
        con.close()
    return redirect(url_for("inventario.lista"))


@bp.route("/inventario/<int:pid>/ubicacion", methods=["POST"])
@requiere("inventario")
def ubicacion(pid):
    ubic = request.form.get("ubicacion", "").strip()[:60]
    con = get_db()
    try:
        with transaccion(con):
            if not con.execute("SELECT 1 FROM inventario WHERE producto_id=?", (pid,)).fetchone():
                con.execute("INSERT INTO inventario(producto_id,cantidad,ubicacion,fecha_actualizacion) VALUES (?,0,?,datetime('now','localtime'))", (pid, ubic))
            else:
                con.execute("UPDATE inventario SET ubicacion=?, fecha_actualizacion=datetime('now','localtime') WHERE producto_id=?", (ubic, pid))
        flash("Ubicación actualizada.", "ok")
    finally:
        con.close()
    return redirect(url_for("inventario.lista"))


@bp.route("/inventario/movimientos")
@requiere("inventario")
def movimientos():
    desde, hasta = rango_fechas(request.args, dias=30)
    tipo = request.args.get("tipo", "")
    pid = request.args.get("producto_id", "")
    donde, args = ["substr(m.fecha,1,10) BETWEEN ? AND ?"], [desde, hasta]
    if tipo in ("ENTRADA", "SALIDA", "AJUSTE"):
        donde.append("m.tipo=?"); args.append(tipo)
    if pid.isdigit():
        donde.append("m.producto_id=?"); args.append(int(pid))
    con = get_db()
    filas = con.execute(f"""
        SELECT m.*, p.codigo, p.nombre AS producto, u.nombre_completo AS usuario
        FROM movimientos_inventario m JOIN productos p ON p.id=m.producto_id JOIN usuarios u ON u.id=m.usuario_id
        WHERE {' AND '.join(donde)} ORDER BY m.id DESC LIMIT 500""", args).fetchall()
    productos = con.execute("SELECT id, codigo, nombre FROM productos WHERE activo=1 ORDER BY nombre").fetchall()
    con.close()
    return render_template("movimientos.html", filas=filas, productos=productos, desde=desde, hasta=hasta,
                           tipo=tipo, pid=pid)
