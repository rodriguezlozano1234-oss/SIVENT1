"""Carga datos de demostración (ficticios) en SIVENT: productos con foto, y opcionalmente clientes y ventas.

Uso (en la carpeta del proyecto):
    python datos_demo.py                          # 100 productos con foto
    python datos_demo.py --clientes 30 --ventas 60  # además clientes y ventas de los últimos 45 días
    python datos_demo.py --sin-fotos              # sin generar imágenes

Con Docker:
    docker compose exec sivent python datos_demo.py --clientes 30 --ventas 60

Es seguro repetirlo: no duplica productos (se reconocen por nombre) ni clientes (por documento).
Los datos son inventados: nombres, DNI, RUC y teléfonos no corresponden a personas ni empresas reales.
"""
import argparse
import colorsys
import random
import re
import textwrap
import unicodedata
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

import db
import imagenes

# (categoría, nombre, descripción, costo en S/, forma de la imagen)
CATALOGO = [
    # ---- Celulares
    ("Celulares", "Samsung Galaxy A15 128GB", "Pantalla AMOLED 6.5\", cámara de 50 MP, 4 GB RAM", 430, "telefono"),
    ("Celulares", "Samsung Galaxy A25 5G 128GB", "5G, pantalla Super AMOLED 120 Hz, 6 GB RAM", 620, "telefono"),
    ("Celulares", "Samsung Galaxy A35 5G 256GB", "Cámara de 50 MP con OIS, resistente al agua IP67", 890, "telefono"),
    ("Celulares", "Samsung Galaxy A55 5G 256GB", "Marco metálico, 8 GB RAM, batería de 5000 mAh", 1250, "telefono"),
    ("Celulares", "Samsung Galaxy S24 256GB", "Gama alta, Galaxy AI, cámara triple", 2900, "telefono"),
    ("Celulares", "Xiaomi Redmi 13C 128GB", "Pantalla 6.74\" 90 Hz, cámara de 50 MP", 340, "telefono"),
    ("Celulares", "Xiaomi Redmi Note 13 256GB", "AMOLED 120 Hz, carga rápida de 33 W", 560, "telefono"),
    ("Celulares", "Xiaomi Redmi Note 13 Pro 256GB", "Cámara de 200 MP, carga de 67 W", 820, "telefono"),
    ("Celulares", "Xiaomi Poco X6 5G 256GB", "Snapdragon 7s Gen 2, pantalla 120 Hz", 940, "telefono"),
    ("Celulares", "Xiaomi Poco M6 128GB", "Económico con pantalla de 90 Hz", 380, "telefono"),
    ("Celulares", "Motorola Moto E14 64GB", "Entrada de gama, Android limpio", 250, "telefono"),
    ("Celulares", "Motorola Moto G24 128GB", "Pantalla 90 Hz, parlantes estéreo", 400, "telefono"),
    ("Celulares", "Motorola Moto G54 5G 256GB", "5G, batería de 6000 mAh", 620, "telefono"),
    ("Celulares", "Motorola Edge 40 Neo 256GB", "pOLED curvo 144 Hz, resistente al agua", 1150, "telefono"),
    ("Celulares", "Honor X6a 128GB", "Pantalla 90 Hz, cámara de 50 MP", 330, "telefono"),
    ("Celulares", "Honor X7b 256GB", "Batería de 6000 mAh, carga de 35 W", 520, "telefono"),
    ("Celulares", "Honor Magic6 Lite 5G 256GB", "Pantalla curva AMOLED, batería de 5300 mAh", 1050, "telefono"),
    ("Celulares", "Realme C53 128GB", "Diseño delgado, cámara de 108 MP", 360, "telefono"),
    ("Celulares", "Realme 12 5G 256GB", "5G, pantalla 120 Hz, carga de 45 W", 780, "telefono"),
    ("Celulares", "ZTE Blade A54 64GB", "Equipo básico para uso diario", 240, "telefono"),
    ("Celulares", "Tecno Spark 20 128GB", "Pantalla 90 Hz, 8 GB RAM extendida", 330, "telefono"),
    ("Celulares", "Infinix Hot 40 Pro 256GB", "Cámara de 108 MP, carga de 33 W", 450, "telefono"),
    ("Celulares", "iPhone 13 128GB", "Chip A15 Bionic, cámara dual", 2300, "telefono"),
    ("Celulares", "iPhone 15 128GB", "Dynamic Island, USB-C, cámara de 48 MP", 3100, "telefono"),
    # ---- Tablets
    ("Tablets", "Samsung Galaxy Tab A9 64GB", "Pantalla de 8.7\", ideal para estudio", 480, "tablet"),
    ("Tablets", "Samsung Galaxy Tab S9 FE 128GB", "10.9\", S Pen incluido, resistente al agua", 1250, "tablet"),
    ("Tablets", "Xiaomi Redmi Pad SE 128GB", "11\" 90 Hz, 4 parlantes", 520, "tablet"),
    ("Tablets", "Lenovo Tab M10 3ra Gen 64GB", "10.1\" HD, modo niños", 360, "tablet"),
    ("Tablets", "Huawei MatePad SE 11\" 128GB", "Pantalla con certificación ocular", 480, "tablet"),
    ("Tablets", "Honor Pad X8a 128GB", "11\" 90 Hz, 4 parlantes", 420, "tablet"),
    # ---- Relojes inteligentes
    ("Relojes inteligentes", "Xiaomi Smart Band 8", "Pulsera con pantalla AMOLED, 16 días de batería", 110, "reloj"),
    ("Relojes inteligentes", "Xiaomi Redmi Watch 4", "AMOLED 1.97\", GPS integrado", 230, "reloj"),
    ("Relojes inteligentes", "Samsung Galaxy Watch6 40mm", "Monitor de sueño y composición corporal", 780, "reloj"),
    ("Relojes inteligentes", "Amazfit Bip 5", "GPS, llamadas Bluetooth, 10 días de batería", 220, "reloj"),
    ("Relojes inteligentes", "Huawei Watch Fit 3", "Diseño delgado, 100 modos deportivos", 420, "reloj"),
    ("Relojes inteligentes", "Haylou Solar Plus", "Reloj deportivo resistente al agua", 130, "reloj"),
    # ---- Audio
    ("Audio", "Audífonos Bluetooth Xiaomi Redmi Buds 5", "Cancelación de ruido, 40 h con estuche", 95, "audio"),
    ("Audio", "Samsung Galaxy Buds FE", "Cancelación activa de ruido, IPX2", 210, "audio"),
    ("Audio", "Audífonos JBL Tune 520BT", "Diadema inalámbrica, 57 h de batería", 140, "audio"),
    ("Audio", "Parlante JBL Go 3", "Bluetooth portátil, resistente al agua", 110, "audio"),
    ("Audio", "Parlante JBL Flip 6", "Sonido potente, IP67, 12 h de batería", 380, "audio"),
    ("Audio", "Audífonos Anker Soundcore Life P2i", "Inalámbricos, 36 h de batería", 130, "audio"),
    ("Audio", "Audífonos in-ear Sony con cable", "Con micrófono, conector de 3.5 mm", 35, "audio"),
    ("Audio", "Audífonos gamer Redragon H510", "Sonido 7.1, micrófono desmontable", 130, "audio"),
    ("Audio", "Audífonos Lenovo LP40 Pro TWS", "Bluetooth 5.1, 24 h con estuche", 70, "audio"),
    ("Audio", "Parlante Bluetooth Xiaomi 16W", "Sonido estéreo, IPX7", 140, "audio"),
    ("Audio", "Audífonos Samsung AKG USB-C", "Con micrófono y control de volumen", 45, "audio"),
    ("Audio", "Audífonos diadema Philips TAH4105", "Bluetooth, graves potentes", 85, "audio"),
    # ---- Cargadores y cables
    ("Cargadores y cables", "Cargador Samsung 25W USB-C", "Carga súper rápida original", 50, "cargador"),
    ("Cargadores y cables", "Cargador Xiaomi 33W", "Carga rápida con cable USB-C", 55, "cargador"),
    ("Cargadores y cables", "Cargador Motorola TurboPower 30W", "Carga rápida USB-C", 60, "cargador"),
    ("Cargadores y cables", "Cargador rápido Anker 20W", "Compacto, compatible con iPhone y Android", 65, "cargador"),
    ("Cargadores y cables", "Cargador inalámbrico 15W", "Base Qi con luz indicadora", 55, "cargador"),
    ("Cargadores y cables", "Cargador de auto doble USB", "Dos puertos con carga rápida", 25, "cargador"),
    ("Cargadores y cables", "Cable USB-C a USB-C 1m", "Soporta carga de hasta 60 W", 15, "cargador"),
    ("Cargadores y cables", "Cable USB-C a Lightning 1m", "Carga rápida para iPhone", 35, "cargador"),
    ("Cargadores y cables", "Cable micro USB 1m", "Cable de datos y carga", 8, "cargador"),
    ("Cargadores y cables", "Cable USB-C reforzado 2m", "Malla de nailon, alta durabilidad", 20, "cargador"),
    ("Cargadores y cables", "Cargador múltiple 4 puertos 65W", "USB-C y USB-A, para varios equipos", 90, "cargador"),
    ("Cargadores y cables", "Adaptador OTG USB-C", "Conecta memorias y teclados al celular", 8, "cargador"),
    ("Cargadores y cables", "Cable HDMI 2m", "Full HD y 4K", 18, "cargador"),
    ("Cargadores y cables", "Base de carga magnética 3 en 1", "Celular, reloj y audífonos", 120, "cargador"),
    # ---- Fundas y protectores
    ("Fundas y protectores", "Funda silicona Samsung A15", "Acabado suave, protege la cámara", 12, "funda"),
    ("Fundas y protectores", "Funda transparente Redmi Note 13", "Antiamarilleo, bordes reforzados", 10, "funda"),
    ("Fundas y protectores", "Funda antigolpes Moto G54", "Doble capa con esquinas reforzadas", 14, "funda"),
    ("Fundas y protectores", "Funda iPhone 15 MagSafe", "Compatible con cargadores magnéticos", 40, "funda"),
    ("Fundas y protectores", "Funda iPhone 13 silicona", "Interior de microfibra", 25, "funda"),
    ("Fundas y protectores", "Funda billetera universal", "Con ranuras para tarjetas", 18, "funda"),
    ("Fundas y protectores", "Mica de vidrio templado Samsung A25", "Dureza 9H, instalación fácil", 8, "funda"),
    ("Fundas y protectores", "Mica de vidrio templado Redmi 13C", "Dureza 9H, borde negro", 7, "funda"),
    ("Fundas y protectores", "Mica de privacidad iPhone 15", "Evita miradas laterales", 20, "funda"),
    ("Fundas y protectores", "Mica cerámica Moto G24", "Flexible, resistente a golpes", 12, "funda"),
    ("Fundas y protectores", "Protector de cámara Samsung A55", "Vidrio templado para lentes", 8, "funda"),
    ("Fundas y protectores", "Funda tablet Samsung Tab A9 giratoria", "Soporte de 360 grados", 30, "funda"),
    ("Fundas y protectores", "Funda Redmi Pad SE con tapa", "Tapa magnética con soporte", 28, "funda"),
    ("Fundas y protectores", "Correa Xiaomi Band 8 silicona", "Varios colores, ajustable", 8, "funda"),
    # ---- Power banks
    ("Power banks", "Power bank Xiaomi 10000mAh 18W", "Doble salida, carga rápida", 65, "powerbank"),
    ("Power banks", "Power bank Xiaomi 20000mAh 50W", "Carga hasta 3 equipos a la vez", 110, "powerbank"),
    ("Power banks", "Power bank Anker PowerCore 10000", "Compacto y liviano", 85, "powerbank"),
    ("Power banks", "Power bank Baseus 20000mAh 65W", "Pantalla digital, carga laptops", 150, "powerbank"),
    ("Power banks", "Power bank Samsung 10000mAh 25W", "Carga súper rápida", 95, "powerbank"),
    ("Power banks", "Power bank solar 20000mAh", "Con panel solar y linterna", 70, "powerbank"),
    # ---- Redes e internet
    ("Redes e internet", "Router TP-Link Archer C6 AC1200", "Doble banda, 4 antenas", 95, "router"),
    ("Redes e internet", "Router TP-Link TL-WR850N", "Wi-Fi N 300 Mbps", 40, "router"),
    ("Redes e internet", "Router Wi-Fi 6 TP-Link AX23", "Wi-Fi 6 AX1800, puertos Gigabit", 160, "router"),
    ("Redes e internet", "Repetidor Wi-Fi TP-Link RE305", "Extiende la señal, doble banda", 80, "router"),
    ("Redes e internet", "Módem 4G LTE Huawei B311", "Acepta chip, hasta 32 usuarios", 150, "router"),
    ("Redes e internet", "Router Xiaomi Mi 4A Gigabit", "Doble banda, 4 antenas", 85, "router"),
    ("Redes e internet", "Switch TP-Link 8 puertos", "Gigabit, instalación sin configuración", 45, "router"),
    ("Redes e internet", "Cable de red UTP Cat6 5m", "Conectores RJ45 listos", 12, "router"),
    # ---- Almacenamiento
    ("Almacenamiento", "Memoria microSD SanDisk 64GB", "Clase 10, con adaptador", 22, "memoria"),
    ("Almacenamiento", "Memoria microSD SanDisk 128GB", "Clase 10, 140 MB/s", 38, "memoria"),
    ("Almacenamiento", "Memoria microSD Kingston 256GB", "A1, ideal para video 4K", 70, "memoria"),
    ("Almacenamiento", "USB Kingston 64GB", "USB 3.2, tapa deslizable", 20, "memoria"),
    ("Almacenamiento", "USB SanDisk 128GB", "USB 3.0, alta velocidad", 35, "memoria"),
    ("Almacenamiento", "Disco SSD externo Kingston XS1000 500GB", "Bolsillo, hasta 1050 MB/s", 190, "memoria"),
    # ---- Accesorios varios
    ("Accesorios", "Soporte de celular para auto", "Fijación con ventosa o rejilla", 18, "soporte"),
    ("Accesorios", "Trípode flexible para celular", "Patas ajustables con control remoto", 25, "soporte"),
    ("Accesorios", "Aro de luz 26 cm con trípode", "Tres tonos de luz, soporte para celular", 40, "soporte"),
    ("Accesorios", "Lector de tarjetas SD USB-C", "SD y microSD, USB 3.0", 15, "soporte"),
]
assert len(CATALOGO) == 100, len(CATALOGO)

DESCRIPCION_CAT = {
    "Tablets": "Tablets Android", "Relojes inteligentes": "Smartwatch y pulseras de actividad",
    "Audio": "Audífonos y parlantes", "Cargadores y cables": "Cargadores, cables y adaptadores",
    "Fundas y protectores": "Fundas, micas y protectores", "Power banks": "Baterías portátiles",
    "Redes e internet": "Routers, módems y redes", "Almacenamiento": "Memorias, USB y discos externos",
}
# (stock mínimo, rango de stock inicial) según el tipo de producto
STOCK = {"telefono": (3, (4, 22)), "tablet": (2, (3, 12)), "reloj": (3, (4, 16)), "audio": (4, (6, 30)),
         "cargador": (8, (20, 80)), "funda": (10, (25, 90)), "powerbank": (5, (8, 30)), "router": (3, (4, 20)),
         "memoria": (6, (10, 45)), "soporte": (5, (8, 30))}
ESTANTE = {"Celulares": "A", "Tablets": "B", "Relojes inteligentes": "B", "Audio": "C", "Cargadores y cables": "D",
           "Fundas y protectores": "E", "Power banks": "D", "Redes e internet": "F", "Almacenamiento": "F", "Accesorios": "E"}

NOMBRES = ["Juan", "Luis", "Carlos", "José", "Miguel", "Rosa", "María", "Ana", "Elena", "Carmen", "Julio", "César",
           "Víctor", "Wilfredo", "Yesenia", "Lucía", "Fiorella", "Milagros", "Jhon", "Edwin", "Sofía", "Pedro", "Marleni",
           "Percy", "Giovanna", "Raúl", "Noemí", "Hugo", "Brenda", "Dante"]
APELLIDOS = ["Quispe", "Huamán", "Flores", "Rojas", "Ccasani", "Condori", "Mendoza", "Gutiérrez", "Vargas", "Pariona",
             "Palomino", "Ramos", "Salcedo", "Cárdenas", "Tello", "Ayala", "Valenzuela", "Chávez", "Aguilar", "Lizarbe",
             "Yupanqui", "Sulca", "Vilcatoma", "Ccahuana", "Cisneros", "Bautista"]
EMPRESAS = ["Comercial", "Inversiones", "Servicios", "Distribuidora", "Corporación", "Importaciones"]
RUBROS = ["Andina", "Wari", "Los Libertadores", "Pampa", "Sierra Sur", "Huamanga", "Tecnored", "Inti", "Qori", "Ayacucho"]
CALLES = ["Jr. 28 de Julio", "Av. Mariscal Cáceres", "Jr. Asamblea", "Av. Independencia", "Jr. Lima", "Jr. Libertad",
          "Av. Ejército", "Jr. Bellido", "Psj. Sucre", "Av. Cusco"]


# ---------------------------------------------------------------- imágenes de demostración
def _hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h / 360, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


_TIENE_TTF = True


def _fuente(tam):
    """Una fuente con tildes (Arial en Windows, DejaVu en Linux); si no hay ninguna, la básica sin tildes."""
    global _TIENE_TTF
    for nombre in ("arial.ttf", "Arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    _TIENE_TTF = False
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow antiguo sin tamaño variable
        return ImageFont.load_default()


def _txt(texto):
    if _TIENE_TTF:
        return texto
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _imagen(nombre, categoria, forma):
    W = 640
    tono = imagenes.tono(categoria)
    img = Image.new("RGB", (W, W))
    d = ImageDraw.Draw(img)
    a, b = _hsl(tono, .45, .94), _hsl(tono, .45, .80)
    for y in range(W):
        t = y / (W - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    oscuro, claro, medio = _hsl(tono, .5, .26), _hsl(tono, .35, .92), _hsl(tono, .45, .45)
    c = W // 2

    if forma == "telefono":
        d.rounded_rectangle((c - 105, 70, c + 105, 440), 38, fill=oscuro)
        d.rounded_rectangle((c - 92, 88, c + 92, 422), 26, fill=claro)
        d.ellipse((c - 7, 98, c + 7, 112), fill=oscuro)
    elif forma == "tablet":
        d.rounded_rectangle((105, 110, 535, 410), 30, fill=oscuro)
        d.rounded_rectangle((122, 126, 518, 394), 14, fill=claro)
        d.ellipse((c - 5, 114, c + 5, 124), fill=medio)
    elif forma == "reloj":
        d.rounded_rectangle((c - 48, 40, c + 48, 220), 18, fill=medio)
        d.rounded_rectangle((c - 48, 330, c + 48, 480), 18, fill=medio)
        d.ellipse((c - 105, 175, c + 105, 385), fill=oscuro)
        d.ellipse((c - 86, 194, c + 86, 366), fill=claro)
        d.line((c, 280, c, 225), fill=oscuro, width=8)
        d.line((c, 280, c + 45, 300), fill=oscuro, width=8)
    elif forma == "audio":
        d.arc((170, 80, 470, 400), 180, 360, fill=oscuro, width=20)
        d.rounded_rectangle((150, 240, 220, 400), 28, fill=oscuro)
        d.rounded_rectangle((420, 240, 490, 400), 28, fill=oscuro)
        d.rounded_rectangle((165, 255, 205, 385), 18, fill=medio)
        d.rounded_rectangle((435, 255, 475, 385), 18, fill=medio)
    elif forma == "cargador":
        d.rounded_rectangle((c - 75, 150, c + 75, 330), 24, fill=oscuro)
        d.rectangle((c - 38, 105, c - 20, 150), fill=medio)
        d.rectangle((c + 20, 105, c + 38, 150), fill=medio)
        d.line([(c, 330), (c, 360), (c - 90, 400), (c - 60, 450), (c + 60, 430), (c + 120, 470)], fill=oscuro, width=12, joint="curve")
    elif forma == "funda":
        d.rounded_rectangle((c - 110, 70, c + 110, 450), 44, fill=medio)
        d.rounded_rectangle((c - 95, 85, c + 95, 435), 32, fill=claro)
        d.rounded_rectangle((c - 82, 98, c - 12, 168), 18, fill=oscuro)
    elif forma == "powerbank":
        d.rounded_rectangle((c - 90, 70, c + 90, 450), 30, fill=oscuro)
        for i in range(4):
            d.rounded_rectangle((c - 50, 130 + i * 55, c + 50, 160 + i * 55), 8, fill=claro if i < 3 else medio)
    elif forma == "router":
        d.line((190, 340, 150, 140), fill=oscuro, width=14)
        d.line((c, 340, c, 120), fill=oscuro, width=14)
        d.line((450, 340, 490, 140), fill=oscuro, width=14)
        d.rounded_rectangle((90, 330, 550, 430), 22, fill=oscuro)
        for i in range(4):
            d.ellipse((150 + i * 40, 372, 166 + i * 40, 388), fill=claro)
    elif forma == "memoria":
        d.polygon([(c - 90, 80), (c + 40, 80), (c + 90, 130), (c + 90, 440), (c - 90, 440)], fill=oscuro)
        for i in range(5):
            d.rectangle((c - 62 + i * 20, 100, c - 52 + i * 20, 150), fill=medio)
        d.rounded_rectangle((c - 60, 250, c + 60, 400), 10, fill=claro)
    else:  # soporte / genérico
        d.rounded_rectangle((c - 90, 220, c + 90, 440), 24, fill=oscuro)
        d.rectangle((c - 12, 120, c + 12, 230), fill=medio)
        d.rounded_rectangle((c - 70, 70, c + 70, 140), 16, fill=oscuro)

    f1, f2 = _fuente(30), _fuente(17)
    y = 498
    for linea in textwrap.wrap(_txt(nombre), 26)[:2]:
        d.text(((W - d.textlength(linea, font=f1)) / 2, y), linea, fill=oscuro, font=f1)
        y += 38
    pie = _txt("Imagen de demostración")
    d.text(((W - d.textlength(pie, font=f2)) / 2, W - 30), pie, fill=medio, font=f2)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


class _Archivo:  # imita el archivo subido desde un formulario
    def __init__(self, datos, nombre):
        self.filename, self._datos = nombre, datos

    def read(self, n=-1):
        return self._datos.read(n)


# ---------------------------------------------------------------- carga
def cargar_productos(con, cantidad, fotos, rnd, admin_id):
    existentes = {r["nombre"].lower() for r in con.execute("SELECT nombre FROM productos")}
    cats = {r["nombre"]: r["id"] for r in con.execute("SELECT id, nombre FROM categorias")}
    maximo = max([int(m.group(1)) for r in con.execute("SELECT codigo FROM productos")
                  if (m := re.fullmatch(r"P(\d+)", r["codigo"]))] or [0])
    nuevos = []
    with db.transaccion(con):
        for cat, nombre, desc, costo, forma in CATALOGO:
            if len(nuevos) >= cantidad:
                break
            if nombre.lower() in existentes:
                continue
            if cat not in cats:
                cats[cat] = con.execute("INSERT INTO categorias(nombre,descripcion) VALUES (?,?)",
                                        (cat, DESCRIPCION_CAT.get(cat, ""))).lastrowid
            maximo += 1
            margen = rnd.uniform(0.18, 0.38)
            venta = max(round(costo * (1 + margen)), costo + 1) - 0.10
            stock_min, (lo, hi) = STOCK[forma]
            azar = rnd.random()
            stock = 0 if azar < 0.07 else rnd.randint(1, stock_min) if azar < 0.20 else rnd.randint(lo, hi)
            pid = con.execute("""INSERT INTO productos(codigo,nombre,descripcion,precio_compra,precio_venta,categoria_id,stock_min)
                                 VALUES (?,?,?,?,?,?,?)""",
                              (f"P{maximo:04d}", nombre, desc, float(costo), round(venta, 2), cats[cat], stock_min)).lastrowid
            con.execute("INSERT INTO inventario(producto_id,cantidad,ubicacion,fecha_actualizacion) VALUES (?,0,?,?)",
                        (pid, f"{ESTANTE.get(cat, 'G')}-{rnd.randint(1, 12):02d}", db.ahora()))
            if stock:
                db.aplicar_movimiento(con, pid, "ENTRADA", stock, "Stock inicial (datos de demostración)", admin_id)
            nuevos.append((pid, cat, nombre, forma))
    if fotos:  # las imágenes se guardan fuera de la transacción y se enlazan al terminar
        for pid, cat, nombre, forma in nuevos:
            token = imagenes.guardar(_Archivo(_imagen(nombre, cat, forma), "demo.png"))
            con.execute("UPDATE productos SET imagen=? WHERE id=?", (token, pid))
    return len(nuevos)


def _documento_libre(con, tipo, rnd):
    while True:
        num = "9" + "".join(rnd.choices("0123456789", k=7)) if tipo == "DNI" else "20" + "".join(rnd.choices("0123456789", k=9))
        if not con.execute("SELECT 1 FROM clientes WHERE tipo_documento=? AND numero_documento=?", (tipo, num)).fetchone():
            return num


def cargar_clientes(con, cantidad, rnd):
    with db.transaccion(con):
        for i in range(cantidad):
            if rnd.random() < 0.2:  # empresa con RUC
                nombre = f"{rnd.choice(EMPRESAS)} {rnd.choice(RUBROS)} S.A.C."
                tipo, mail = "RUC", re.sub(r"[^a-z]", "", nombre.lower().replace("s.a.c.", "")) + "@example.com"
            else:
                n, a1, a2 = rnd.choice(NOMBRES), rnd.choice(APELLIDOS), rnd.choice(APELLIDOS)
                nombre, tipo = f"{n} {a1} {a2}", "DNI"
                mail = re.sub(r"[^a-z]", "", (n + a1).lower().translate(str.maketrans("áéíóúñ", "aeioun"))) + "@example.com"
            con.execute("""INSERT INTO clientes(tipo_documento,numero_documento,nombre,telefono,email,direccion)
                           VALUES (?,?,?,?,?,?)""",
                        (tipo, _documento_libre(con, tipo, rnd), nombre, "9" + "".join(rnd.choices("0123456789", k=8)),
                         mail, f"{rnd.choice(CALLES)} {rnd.randint(100, 1500)}, Huamanga, Ayacucho"))
    return cantidad


def cargar_ventas(con, cantidad, rnd, dias=45):
    usuarios = [r["id"] for r in con.execute("""SELECT u.id FROM usuarios u JOIN roles r ON r.id=u.rol_id
                                              WHERE u.activo=1 AND (r.permisos LIKE '%ventas%')""")]
    clientes = [(r["id"], r["tipo_documento"]) for r in con.execute("SELECT id, tipo_documento FROM clientes WHERE activo=1")]
    productos = con.execute("""SELECT p.id, p.precio_venta, p.categoria_id FROM productos p WHERE p.activo=1""").fetchall()
    if not usuarios or not productos:
        return 0
    ahora = datetime.now()
    fechas = []
    for _ in range(cantidad):
        f = ahora - timedelta(days=rnd.randint(0, dias), hours=rnd.randint(0, 6))
        f = f.replace(hour=rnd.randint(9, 20), minute=rnd.randint(0, 59), second=rnd.randint(0, 59))
        fechas.append(f if f <= ahora else f - timedelta(days=1))
    fechas.sort()
    hechas = 0
    for f in fechas:
        ts = f.strftime("%Y-%m-%d %H:%M:%S")
        with db.transaccion(con):
            stock = {r["producto_id"]: r["cantidad"] for r in con.execute("SELECT producto_id, cantidad FROM inventario")}
            candidatos = [p for p in productos if stock.get(p["id"], 0) > 0]
            if not candidatos:
                continue
            elegidos = rnd.sample(candidatos, min(len(candidatos), rnd.choice([1, 1, 1, 2, 2, 3])))
            lineas = []
            for p in elegidos:
                cant = min(rnd.choice([1, 1, 1, 2, 3]), stock[p["id"]])
                lineas.append((p["id"], cant, p["precio_venta"], round(p["precio_venta"] * cant, 2)))
            cliente = rnd.choice(clientes) if clientes and rnd.random() < 0.6 else None
            tipo = "FACTURA" if cliente and cliente[1] == "RUC" and rnd.random() < 0.7 else "BOLETA"
            uid = rnd.choice(usuarios)
            vid = con.execute("INSERT INTO ventas(fecha,usuario_id,cliente_id,tipo_comprobante,total) VALUES (?,?,?,?,?)",
                              (ts, uid, cliente[0] if cliente else None, tipo, round(sum(l[3] for l in lineas), 2))).lastrowid
            for pid, cant, precio, sub in lineas:
                con.execute("""INSERT INTO detalle_ventas(venta_id,producto_id,cantidad,precio_unit,subtotal)
                               VALUES (?,?,?,?,?)""", (vid, pid, cant, precio, sub))
                db.aplicar_movimiento(con, pid, "SALIDA", cant, f"Venta #{vid}", uid)
                # el movimiento queda con la fecha de la venta, no con la de hoy
                con.execute("UPDATE movimientos_inventario SET fecha=? WHERE id=(SELECT MAX(id) FROM movimientos_inventario)", (ts,))
                con.execute("UPDATE inventario SET fecha_actualizacion=? WHERE producto_id=?", (ts, pid))
        hechas += 1
    return hechas


def main():
    ap = argparse.ArgumentParser(description="Carga datos de demostración en SIVENT.")
    ap.add_argument("--productos", type=int, default=100, help="productos a crear (máx. 100; por defecto 100)")
    ap.add_argument("--clientes", type=int, default=0, help="clientes ficticios a crear")
    ap.add_argument("--ventas", type=int, default=0, help="ventas ficticias de los últimos 45 días")
    ap.add_argument("--sin-fotos", action="store_true", help="no generar imágenes de los productos")
    ap.add_argument("--semilla", type=int, default=2026, help="semilla del generador aleatorio")
    args = ap.parse_args()

    rnd = random.Random(args.semilla)
    db.init_db()
    con = db.get_db()
    try:
        admin = con.execute("SELECT id FROM usuarios WHERE usuario='admin'").fetchone() or con.execute("SELECT id FROM usuarios").fetchone()
        p = cargar_productos(con, args.productos, not args.sin_fotos, rnd, admin["id"]) if args.productos > 0 else 0
        c = cargar_clientes(con, args.clientes, rnd) if args.clientes > 0 else 0
        v = cargar_ventas(con, args.ventas, rnd) if args.ventas > 0 else 0
    finally:
        con.close()
    print(f"Listo: {p} productos nuevos, {c} clientes nuevos, {v} ventas registradas.")
    if args.productos and p < args.productos:
        print(f"(Se omitieron {args.productos - p} productos que ya existían o exceden el catálogo de demostración.)")


if __name__ == "__main__":
    main()
