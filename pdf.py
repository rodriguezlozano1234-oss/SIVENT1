"""Generación de PDF: comprobantes de venta y reportes."""
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

AZUL = colors.HexColor("#1F3C88")
_styles = getSampleStyleSheet()
_celda = ParagraphStyle("celda", parent=_styles["Normal"], fontSize=9, leading=11)
_celda_der = ParagraphStyle("celda_der", parent=_celda, alignment=2)


def serie_numero(v):
    prefijo = "F001" if v["tipo_comprobante"] == "FACTURA" else "B001"
    return f"{prefijo}-{v['id']:08d}"


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def comprobante_pdf(v, items):
    """v: venta con cliente_nombre, tipo_documento, numero_documento y usuario_nombre (pueden ser None)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"{v['tipo_comprobante']} {serie_numero(v)}",
                            leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    fecha = datetime.strptime(v["fecha"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    el = [Paragraph("<b>SIVENT</b>", _styles["Title"]),
          Paragraph(f"<b>{v['tipo_comprobante']} — {serie_numero(v)}</b><br/>Fecha: {fecha}<br/>"
                    f"Atendió: {_esc(v['usuario_nombre'] or '-')}", _styles["Normal"])]
    if v["cliente_nombre"]:
        etiqueta = "Razón social" if v["tipo_documento"] == "RUC" else "Cliente"
        el.append(Paragraph(f"<br/><b>{v['tipo_documento']}:</b> {_esc(v['numero_documento'])}<br/>"
                            f"<b>{etiqueta}:</b> {_esc(v['cliente_nombre'])}", _styles["Normal"]))
    else:
        el.append(Paragraph("<br/><b>Cliente:</b> Público general", _styles["Normal"]))
    if v["estado"] == "ANULADA":
        el.append(Paragraph(f"<br/><font color='#b3261e'><b>COMPROBANTE ANULADO</b></font> — "
                            f"{_esc(v['anulada_motivo'] or 'sin motivo registrado')}", _styles["Normal"]))
    el.append(Spacer(1, 14))

    data = [["Código", "Producto", "Cant.", "P. unit.", "Subtotal"]]
    for it in items:
        data.append([it["codigo"], Paragraph(_esc(it["nombre"]), _celda), str(it["cantidad"]),
                     f"S/ {it['precio_unit']:,.2f}", f"S/ {it['subtotal']:,.2f}"])
    data.append(["", "", "", Paragraph("<b>TOTAL</b>", _celda_der), Paragraph(f"<b>S/ {v['total']:,.2f}</b>", _celda_der)])
    t = Table(data, colWidths=[55, 235, 40, 90, 90], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.lightgrey),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 1), (-1, -2), colors.whitesmoke),
    ]))
    el += [t, Spacer(1, 24),
           Paragraph("<font size=8 color='#777777'>Comprobante de control interno de SIVENT. "
                     "No reemplaza a un comprobante de pago electrónico emitido ante SUNAT.</font>", _styles["Normal"])]
    doc.build(el)
    buf.seek(0)
    return buf


def reporte_pdf(titulo, subtitulo, headers, filas, totales=None):
    """filas y totales ya vienen formateados como texto."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"SIVENT — {titulo}", leftMargin=36, rightMargin=36)
    el = [Paragraph("<b>SIVENT — Reporte</b>", _styles["Title"]),
          Paragraph(f"<b>{_esc(titulo)}</b><br/>{_esc(subtitulo)}<br/>Generado: {datetime.now():%d/%m/%Y %H:%M}",
                    _styles["Normal"]), Spacer(1, 14)]
    cuerpo = [[Paragraph(f"<font color='white'><b>{_esc(h)}</b></font>", _celda) for h in headers]]
    for r in filas:
        cuerpo.append([Paragraph(_esc(c), _celda if i == 0 else _celda_der) for i, c in enumerate(r)])
    if totales:
        cuerpo.append([Paragraph(f"<b>{_esc(c)}</b>", _celda if i == 0 else _celda_der) for i, c in enumerate(totales)])
    t = Table(cuerpo, repeatRows=1)
    estilo = [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke])]
    t.setStyle(TableStyle(estilo))
    el.append(t)
    doc.build(el)
    buf.seek(0)
    return buf


def catalogo_pdf(items, titulo):
    """Catálogo para clientes: tarjetas de 3 columnas con foto, nombre y precio (sin costos ni stock).

    items: dicts con codigo, nombre, categoria, precio, descripcion, agotado y ruta (foto en disco o None).
    """
    from PIL import Image as PILImage

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"SIVENT — {titulo}", leftMargin=30, rightMargin=30,
                            topMargin=34, bottomMargin=34)
    ancho = (A4[0] - 60) / 3
    nombre_st = ParagraphStyle("cat_nombre", parent=_celda, fontName="Helvetica-Bold", fontSize=9.5, leading=11.5)
    pequeno = ParagraphStyle("cat_peq", parent=_celda, fontSize=8, leading=10, textColor=colors.HexColor("#5d6679"))
    precio_st = ParagraphStyle("cat_precio", parent=_celda, fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=AZUL)

    def foto(ruta):
        lado = ancho - 24
        if ruta:
            try:
                with PILImage.open(ruta) as im:
                    jpg = BytesIO()
                    im.convert("RGB").save(jpg, "JPEG", quality=85)
                    jpg.seek(0)
                    w, h = im.size
                img = RLImage(jpg, width=lado, height=lado * h / w)
                if img.drawHeight > lado:  # fotos muy altas: se ajustan a un cuadro
                    img = RLImage(jpg, width=lado * lado / img.drawHeight, height=lado)
                return img
            except Exception:
                pass
        return Paragraph("<font color='#9aa5bd'>Sin foto</font>", ParagraphStyle("sf", parent=_celda, alignment=1))

    def tarjeta(it):
        partes = [foto(it["ruta"]), Spacer(1, 6), Paragraph(_esc(it["nombre"]), nombre_st),
                  Paragraph(f"{_esc(it['codigo'])} · {_esc(it['categoria'])}", pequeno)]
        if it["descripcion"]:
            partes.append(Paragraph(_esc(it["descripcion"][:90]), pequeno))
        partes.append(Paragraph(f"S/ {it['precio']:,.2f}" + (" <font size=8 color='#b3261e'>agotado</font>" if it["agotado"] else ""),
                                precio_st))
        return partes

    el = [Paragraph(f"<b>SIVENT — {_esc(titulo)}</b>", _styles["Title"]),
          Paragraph(f"Precios en soles vigentes al {datetime.now():%d/%m/%Y}. Sujetos a disponibilidad.", pequeno),
          Spacer(1, 10)]
    if not items:
        el.append(Paragraph("No hay productos para mostrar.", _celda))
    else:
        filas = [[tarjeta(it) for it in items[i:i + 3]] for i in range(0, len(items), 3)]
        for fila in filas:
            fila.extend([""] * (3 - len(fila)))
        t = Table(filas, colWidths=[ancho] * 3)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.25, colors.white),
                               ("INNERGRID", (0, 0), (-1, -1), 6, colors.white), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
        for r, fila in enumerate(filas):
            for c, celda in enumerate(fila):
                if celda != "":
                    t.setStyle(TableStyle([("BOX", (c, r), (c, r), 0.6, colors.HexColor("#dde2ec"))]))
        el.append(t)
    doc.build(el)
    buf.seek(0)
    return buf
