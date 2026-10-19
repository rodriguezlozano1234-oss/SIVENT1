import math
import re
from datetime import date, datetime, timedelta


def num(valor, campo, minimo=0, entero=False):
    """Convierte a número validando rango. Lanza ValueError con un mensaje listo para mostrar."""
    try:
        s = str(valor if valor is not None else "").strip().replace(",", ".")
        n = int(s) if entero else float(s)
        if not math.isfinite(n):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(f"{campo} debe ser un número válido.")
    if n < minimo:
        raise ValueError(f"{campo} no puede ser menor que {minimo}.")
    return n if entero else round(n, 2)


def rango_fechas(args, dias=30):
    """Lee ?desde=&hasta= (YYYY-MM-DD). Por defecto, los últimos `dias` días."""
    hoy = date.today()

    def leer(clave, defecto):
        try:
            return datetime.strptime(args.get(clave, ""), "%Y-%m-%d").date()
        except ValueError:
            return defecto

    hasta = leer("hasta", hoy)
    desde = leer("desde", hasta - timedelta(days=dias - 1))
    if desde > hasta:
        desde, hasta = hasta, desde
    return desde.isoformat(), hasta.isoformat()


REGLAS_DOC = {
    "DNI": (re.compile(r"^\d{8}$"), "El DNI debe tener 8 dígitos."),
    "RUC": (re.compile(r"^\d{11}$"), "El RUC debe tener 11 dígitos."),
    "CE": (re.compile(r"^[A-Z0-9]{9,12}$"), "El carné de extranjería debe tener entre 9 y 12 caracteres."),
    "OTRO": (re.compile(r"^[A-Z0-9-]{3,20}$"), "El documento debe tener entre 3 y 20 caracteres."),
}
