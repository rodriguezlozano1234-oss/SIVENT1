"""Reportes: Ventas (diario/semanal/mensual), Ventas por empleado y Top productos."""
import csv
import io
from datetime import date, timedelta

from flask import Blueprint, Response, abort, redirect, render_template, request, send_file, url_for

import pdf
from auth import requiere
from db import get_db
from util import rango_fechas

bp = Blueprint("reportes", __name__)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
TITULOS = {"ventas": "Reporte de ventas", "empleados": "Ventas por empleado", "productos": "Productos más vendidos"}
AGRUPACIONES = {
    "diario": "substr(v.fecha,1,10)",
    "semanal": "date(substr(v.fecha,1,10),'-6 days','weekday 1')",  # lunes de la semana
    "mensual": "substr(v.fecha,1,7)",
}
UNIDADES = ("(SELECT venta_id, SUM(cantidad) AS unidades FROM detalle_ventas GROUP BY venta_id)")


@bp.app_template_filter("celda")
def celda(valor, tipo):
    if valor is None:
        return ""
    if tipo == "s":
        return f"S/ {valor:,.2f}"
    if tipo == "n":
        return f"{int(valor):,}"
    if tipo == "p":
        return f"{valor:.1f}%"
    return str(valor)


def _etiqueta(agrupar, clave):
    if agrupar == "diario":
        return date.fromisoformat(clave).strftime("%d/%m/%Y")
    if agrupar == "semanal":
        d = date.fromisoformat(clave)
        return f"{d:%d/%m} al {d + timedelta(days=6):%d/%m/%Y}"
    anio, mes = clave.split("-")
    return f"{MESES[int(mes) - 1].capitalize()} {anio}"


def construir(clave, args):
    desde, hasta = rango_fechas(args)
    con = get_db()
    r = {"clave": clave, "titulo": TITULOS[clave], "desde": desde, "hasta": hasta, "agrupar": None}

    if clave == "ventas":
        agrupar = args.get("agrupar", "diario")
        if agrupar not in AGRUPACIONES:
            agrupar = "diario"
        r["agrupar"] = agrupar
        filas = con.execute(f"""
            SELECT {AGRUPACIONES[agrupar]} AS periodo, COUNT(*) AS n, COALESCE(SUM(u.unidades),0) AS unidades,
                   ROUND(SUM(v.total),2) AS total
            FROM ventas v LEFT JOIN {UNIDADES} u ON u.venta_id = v.id
            WHERE substr(v.fecha,1,10) BETWEEN ? AND ? AND v.estado='EMITIDA' GROUP BY periodo ORDER BY periodo DESC""", (desde, hasta)).fetchall()
        r["headers"] = ["Período", "N° ventas", "Unidades", "Total", "Ticket promedio"]
        r["tipos"] = ["t", "n", "n", "s", "s"]
        r["filas"] = [(_etiqueta(agrupar, f["periodo"]), f["n"], f["unidades"], f["total"], round(f["total"] / f["n"], 2))
                      for f in filas]
        r["barra"] = 3
    elif clave == "empleados":
        filas = con.execute(f"""
            SELECT u.nombre_completo AS empleado, u.usuario, COUNT(v.id) AS n, COALESCE(SUM(d.unidades),0) AS unidades,
                   COALESCE(ROUND(SUM(v.total),2),0) AS total
            FROM usuarios u
            LEFT JOIN ventas v ON v.usuario_id = u.id AND v.estado='EMITIDA' AND substr(v.fecha,1,10) BETWEEN ? AND ?
            LEFT JOIN {UNIDADES} d ON d.venta_id = v.id
            WHERE u.activo=1 OR v.id IS NOT NULL
            GROUP BY u.id ORDER BY total DESC, empleado""", (desde, hasta)).fetchall()
        gran = sum(f["total"] for f in filas) or 0
        r["headers"] = ["Empleado", "Usuario", "N° ventas", "Unidades", "Total", "Ticket promedio", "% del total"]
        r["tipos"] = ["t", "t", "n", "n", "s", "s", "p"]
        r["filas"] = [(f["empleado"], f["usuario"], f["n"], f["unidades"], f["total"],
                       round(f["total"] / f["n"], 2) if f["n"] else 0, (f["total"] / gran * 100) if gran else 0)
                      for f in filas]
        r["barra"] = 4
    else:  # productos
        filas = con.execute("""
            SELECT p.codigo, p.nombre, SUM(d.cantidad) AS unidades, ROUND(SUM(d.subtotal),2) AS total
            FROM detalle_ventas d JOIN ventas v ON v.id=d.venta_id JOIN productos p ON p.id=d.producto_id
            WHERE substr(v.fecha,1,10) BETWEEN ? AND ? AND v.estado='EMITIDA' GROUP BY p.id ORDER BY unidades DESC, total DESC LIMIT 50""",
                           (desde, hasta)).fetchall()
        r["headers"] = ["Código", "Producto", "Unidades", "Total"]
        r["tipos"] = ["t", "t", "n", "s"]
        r["filas"] = [tuple(f) for f in filas]
        r["barra"] = 3
    con.close()

    # fila de totales y barras proporcionales
    sumables = {"ventas": (1, 2, 3), "empleados": (2, 3, 4), "productos": (2, 3)}[clave]
    if r["filas"]:
        tot = [None] * len(r["headers"])
        tot[0] = "Total"
        for i in sumables:
            tot[i] = sum(f[i] for f in r["filas"])
        if clave == "ventas":
            tot[4] = round(tot[3] / tot[1], 2) if tot[1] else 0
        if clave == "empleados":
            tot[5] = round(tot[4] / tot[2], 2) if tot[2] else 0
            tot[6] = 100.0 if tot[4] else 0
        r["totales"] = tuple(tot)
        mayor = max(f[r["barra"]] for f in r["filas"]) or 1
        r["pct"] = [round(f[r["barra"]] / mayor * 100) for f in r["filas"]]
    else:
        r["totales"], r["pct"] = None, []
    r["subtitulo"] = f"Del {date.fromisoformat(desde):%d/%m/%Y} al {date.fromisoformat(hasta):%d/%m/%Y}" + \
        (f" · agrupado de forma {r['agrupar']}" if r["agrupar"] else "")
    return r


def _validar(clave):
    if clave not in TITULOS:
        abort(404)


@bp.route("/reportes")
@requiere("reportes")
def indice():
    return redirect(url_for("reportes.ver", clave="ventas"))


@bp.route("/reportes/<clave>")
@requiere("reportes")
def ver(clave):
    _validar(clave)
    return render_template("reportes.html", r=construir(clave, request.args), titulos=TITULOS)


@bp.route("/reportes/<clave>/exportar.<formato>")
@requiere("reportes")
def exportar(clave, formato):
    _validar(clave)
    r = construir(clave, request.args)
    if formato == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(r["headers"])
        w.writerows(r["filas"])
        if r["totales"]:
            w.writerow(r["totales"])
        return Response("\ufeff" + out.getvalue(), mimetype="text/csv",  # BOM: Excel respeta las tildes
                        headers={"Content-Disposition": f"attachment; filename=reporte-{clave}.csv"})
    if formato == "pdf":
        fmt = lambda fila: [celda(v, t) for v, t in zip(fila, r["tipos"])]
        buf = pdf.reporte_pdf(r["titulo"], r["subtitulo"], r["headers"], [fmt(f) for f in r["filas"]],
                              fmt(r["totales"]) if r["totales"] else None)
        return send_file(buf, mimetype="application/pdf", download_name=f"reporte-{clave}.pdf")
    abort(404)
