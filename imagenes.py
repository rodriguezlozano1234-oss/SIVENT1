"""Fotos de productos: validación, redimensionado, miniaturas y marcador de posición."""
import os
import re
import secrets
from io import BytesIO

from flask import url_for
from markupsafe import Markup, escape
from PIL import Image, ImageOps, UnidentifiedImageError

from db import UPLOADS_DIR

MAX_BYTES = 5 * 1024 * 1024
LADO_GRANDE, LADO_MINIATURA = 900, 360
TOKEN = re.compile(r"^[0-9a-f]{32}$")
ARCHIVO = re.compile(r"^[0-9a-f]{32}(_t)?\.webp$")
Image.MAX_IMAGE_PIXELS = 40_000_000  # evita "bombas de descompresión"


def _ruta(token, miniatura=False):
    return os.path.join(UPLOADS_DIR, f"{token}{'_t' if miniatura else ''}.webp")


def _version(img, lado):
    """Copia de la imagen con el lado mayor limitado, sobre fondo blanco si trae transparencia."""
    img = img.copy()
    img.thumbnail((lado, lado), Image.LANCZOS)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        fondo.paste(img, mask=img.getchannel("A"))
        return fondo
    return img.convert("RGB")


def guardar(archivo):
    """Valida y guarda la foto subida (FileStorage). Devuelve el token, o None si no se subió nada.

    Lanza ValueError con un mensaje listo para mostrar si el archivo no es una imagen válida.
    """
    if archivo is None or not archivo.filename:
        return None
    datos = archivo.read(MAX_BYTES + 1)
    if not datos:
        return None
    if len(datos) > MAX_BYTES:
        raise ValueError("La imagen supera los 5 MB. Elija una más liviana.")
    try:
        img = Image.open(BytesIO(datos))
        if img.format not in ("JPEG", "PNG", "WEBP", "GIF"):
            raise ValueError("Formato no admitido. Use JPG, PNG o WEBP.")
        img.load()
        img = ImageOps.exif_transpose(img)  # respeta la orientación de fotos tomadas con el celular
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("El archivo no es una imagen válida. Use JPG, PNG o WEBP.")
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    token = secrets.token_hex(16)
    _version(img, LADO_GRANDE).save(_ruta(token), "WEBP", quality=82, method=4)
    _version(img, LADO_MINIATURA).save(_ruta(token, True), "WEBP", quality=78, method=4)
    return token


def borrar(token):
    if not token or not TOKEN.match(token):
        return
    for mini in (False, True):
        try:
            os.remove(_ruta(token, mini))
        except OSError:
            pass


def ruta_archivo(token, miniatura=False):
    """Ruta en disco de la foto (o None si no existe), para el PDF del catálogo."""
    if token and TOKEN.match(token):
        ruta = _ruta(token, miniatura)
        if os.path.exists(ruta):
            return ruta
    return None


def url(token, miniatura=False):
    if not token or not TOKEN.match(token):
        return ""
    return url_for("catalogo.media", archivo=f"{token}{'_t' if miniatura else ''}.webp")


def iniciales(nombre):
    palabras = [p for p in re.split(r"[\s\-_/]+", (nombre or "").strip()) if p]
    return "".join(p[0] for p in palabras[:2]).upper() or "?"


def tono(texto):
    """Color estable (0-359) para el marcador de posición, según el nombre."""
    return sum(ord(c) * (i + 1) for i, c in enumerate(texto or "")) % 360


def foto(token, nombre, miniatura=True, clase="", alt=""):
    """HTML de la foto del producto, o un recuadro con sus iniciales si todavía no tiene foto."""
    clase = ("foto " + clase).strip()
    if token and TOKEN.match(token):
        return Markup('<img class="{}" src="{}" alt="{}" loading="lazy" decoding="async">').format(
            clase, url(token, miniatura), alt)
    return Markup('<span class="{} ph" style="--h:{}" aria-hidden="true">{}</span>').format(
        clase, tono(nombre), escape(iniciales(nombre)))


def init_app(app):
    app.jinja_env.globals["foto"] = foto
    app.jinja_env.globals["foto_url"] = url
    app.jinja_env.globals["tono"] = tono
    app.jinja_env.globals["iniciales"] = iniciales
