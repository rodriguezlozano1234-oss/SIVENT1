"""Base de datos de SIVENT (SQLite): esquema, migración desde la versión anterior y operaciones de inventario."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SIVENT_DB", os.path.join(BASE_DIR, "sivent.db"))
# Las fotos de productos viven junto a la base de datos (en Docker: la carpeta montada ./data).
UPLOADS_DIR = os.environ.get("SIVENT_UPLOADS", os.path.join(os.path.dirname(DB_PATH), "uploads", "productos"))

# Módulos del sistema; cada rol recibe un subconjunto de ellos.
MODULOS = {
    "catalogo": "Catálogo, productos y categorías",
    "inventario": "Inventario y movimientos",
    "clientes": "Clientes",
    "compras": "Compras a proveedores",
    "ventas": "Ventas",
    "reportes": "Reportes",
    "usuarios": "Usuarios y roles (administrar el sistema)",
}
ROLES_BASE = [
    ("ADMIN", "Administra todo el sistema: usuarios, roles, catálogo, compras, ventas y reportes.", list(MODULOS)),
    ("VENDEDOR", "Registra ventas y atiende a los clientes.", ["ventas", "clientes"]),
    ("ALMACENERO", "Gestiona productos, inventario y compras a proveedores.", ["catalogo", "inventario", "compras"]),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS roles(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    descripcion TEXT NOT NULL DEFAULT '',
    permisos TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS usuarios(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_completo TEXT NOT NULL,
    usuario TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    rol_id INTEGER NOT NULL REFERENCES roles(id),
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS categorias(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    descripcion TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS productos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    precio_compra REAL NOT NULL DEFAULT 0 CHECK(precio_compra >= 0),
    precio_venta REAL NOT NULL CHECK(precio_venta >= 0),
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    stock_min INTEGER NOT NULL DEFAULT 0 CHECK(stock_min >= 0),
    activo INTEGER NOT NULL DEFAULT 1,
    imagen TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS inventario(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL UNIQUE REFERENCES productos(id),
    cantidad INTEGER NOT NULL DEFAULT 0 CHECK(cantidad >= 0),
    ubicacion TEXT NOT NULL DEFAULT '',
    fecha_actualizacion TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clientes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_documento TEXT NOT NULL DEFAULT 'DNI' CHECK(tipo_documento IN ('DNI','RUC','CE','OTRO')),
    numero_documento TEXT NOT NULL,
    nombre TEXT NOT NULL,
    telefono TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    direccion TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    UNIQUE(tipo_documento, numero_documento)
);
CREATE TABLE IF NOT EXISTS compras(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    proveedor TEXT NOT NULL,
    total REAL NOT NULL CHECK(total >= 0)
);
CREATE TABLE IF NOT EXISTS detalle_compras(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER NOT NULL REFERENCES compras(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    precio_unit REAL NOT NULL CHECK(precio_unit >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0)
);
CREATE TABLE IF NOT EXISTS ventas(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    cliente_id INTEGER REFERENCES clientes(id),
    tipo_comprobante TEXT NOT NULL DEFAULT 'BOLETA' CHECK(tipo_comprobante IN ('BOLETA','FACTURA')),
    total REAL NOT NULL CHECK(total >= 0),
    estado TEXT NOT NULL DEFAULT 'EMITIDA',
    anulada_fecha TEXT,
    anulada_por INTEGER REFERENCES usuarios(id),
    anulada_motivo TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS detalle_ventas(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    precio_unit REAL NOT NULL CHECK(precio_unit >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0)
);
CREATE TABLE IF NOT EXISTS movimientos_inventario(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    tipo TEXT NOT NULL CHECK(tipo IN ('ENTRADA','SALIDA','AJUSTE')),
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    stock_anterior INTEGER NOT NULL,
    stock_resultante INTEGER NOT NULL,
    motivo TEXT NOT NULL,
    fecha TEXT NOT NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id)
);
CREATE INDEX IF NOT EXISTS ix_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS ix_ventas_usuario ON ventas(usuario_id);
CREATE INDEX IF NOT EXISTS ix_detalle_ventas_venta ON detalle_ventas(venta_id);
CREATE INDEX IF NOT EXISTS ix_detalle_compras_compra ON detalle_compras(compra_id);
CREATE INDEX IF NOT EXISTS ix_mov_producto ON movimientos_inventario(producto_id, fecha);
"""

# Columnas añadidas después de la v2: se agregan solas a las bases existentes al arrancar.
COLUMNAS_NUEVAS = [
    ("productos", "imagen", "TEXT NOT NULL DEFAULT ''"),
    ("ventas", "estado", "TEXT NOT NULL DEFAULT 'EMITIDA'"),
    ("ventas", "anulada_fecha", "TEXT"),
    ("ventas", "anulada_por", "INTEGER REFERENCES usuarios(id)"),
    ("ventas", "anulada_motivo", "TEXT NOT NULL DEFAULT ''"),
]


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    """Conexión con filas accesibles por nombre. Las transacciones se manejan con `transaccion`."""
    con = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    con.execute("PRAGMA journal_mode = WAL;")
    return con


@contextmanager
def transaccion(con):
    """BEGIN IMMEDIATE ... COMMIT; hace ROLLBACK ante cualquier excepción."""
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")


def aplicar_movimiento(con, producto_id, tipo, cantidad, motivo, usuario_id, permitir_inactivo=False):
    """Cambia el stock de un producto y deja el movimiento registrado. Debe llamarse dentro de `transaccion`.

    ENTRADA / SALIDA: `cantidad` es la cantidad que entra o sale.
    AJUSTE: `cantidad` es el stock contado (el sistema calcula la diferencia).
    `permitir_inactivo` solo se usa al anular una venta de un producto que ya fue dado de baja.
    """
    p = con.execute("SELECT nombre FROM productos WHERE id=?" + ("" if permitir_inactivo else " AND activo=1"),
                    (producto_id,)).fetchone()
    if not p:
        raise ValueError("El producto no existe o está inactivo.")
    fila = con.execute("SELECT cantidad FROM inventario WHERE producto_id=?", (producto_id,)).fetchone()
    anterior = fila["cantidad"] if fila else 0

    if tipo in ("ENTRADA", "SALIDA") and cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    if tipo == "ENTRADA":
        nuevo = anterior + cantidad
    elif tipo == "SALIDA":
        nuevo = anterior - cantidad
        if nuevo < 0:
            raise ValueError(f"Stock insuficiente: {p['nombre']} (quedan {anterior}).")
    elif tipo == "AJUSTE":
        if cantidad < 0:
            raise ValueError("El stock contado no puede ser negativo.")
        nuevo = cantidad
        if nuevo == anterior:
            raise ValueError("El stock contado es igual al actual: no hay nada que ajustar.")
        cantidad = abs(nuevo - anterior)
    else:
        raise ValueError("Tipo de movimiento no válido.")

    ts = ahora()
    if fila:
        con.execute("UPDATE inventario SET cantidad=?, fecha_actualizacion=? WHERE producto_id=?",
                    (nuevo, ts, producto_id))
    else:
        con.execute("INSERT INTO inventario(producto_id,cantidad,ubicacion,fecha_actualizacion) VALUES (?,?,'',?)",
                    (producto_id, nuevo, ts))
    con.execute("""INSERT INTO movimientos_inventario
                   (producto_id,tipo,cantidad,stock_anterior,stock_resultante,motivo,fecha,usuario_id)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (producto_id, tipo, cantidad, anterior, nuevo, motivo, ts, usuario_id))
    return anterior, nuevo


# ---------------------------------------------------------------- arranque y migración
def _columnas(con, tabla):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({tabla})")}


def _asegurar_columnas(con):
    for tabla, columna, ddl in COLUMNAS_NUEVAS:
        if columna not in _columnas(con, tabla):
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {ddl}")


def _es_legado(con):
    """True si la base es la de la versión anterior (productos con columna `precio`)."""
    cols = _columnas(con, "productos")
    return bool(cols) and "precio_venta" not in cols


def _sql_semillas_roles():
    filas = ", ".join(f"('{n}','{d}','{','.join(p)}')" for n, d, p in ROLES_BASE)
    return f"INSERT INTO roles(nombre,descripcion,permisos) VALUES {filas};"


def _migrar_legado(con):
    """Convierte la base de la versión anterior al modelo nuevo conservando usuarios, productos, stock y ventas."""
    destino = os.path.splitext(DB_PATH)[0] + f"_antes_de_migrar_{datetime.now():%Y%m%d_%H%M%S}.db"
    copia = sqlite3.connect(destino)
    con.backup(copia)
    copia.close()

    vcols = _columnas(con, "ventas")
    admin = "(SELECT MIN(id) FROM usuarios)"
    tipo = "COALESCE(v.tipo,'BOLETA')" if "tipo" in vcols else "'BOLETA'"
    usuario = f"COALESCE(v.usuario_id,{admin})" if "usuario_id" in vcols else admin
    if "ruc" in vcols:
        clientes_sql = """INSERT INTO clientes(tipo_documento,numero_documento,nombre)
            SELECT 'RUC', ruc, COALESCE(MAX(razon_social), ruc) FROM ventas_old
            WHERE ruc GLOB '[0-9]*' AND LENGTH(ruc)=11 GROUP BY ruc;"""
        cliente = "(SELECT c.id FROM clientes c WHERE c.tipo_documento='RUC' AND c.numero_documento=v.ruc)"
    else:
        clientes_sql, cliente = "", "NULL"

    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.executescript(f"""
        BEGIN;
        ALTER TABLE usuarios RENAME TO usuarios_old;
        ALTER TABLE productos RENAME TO productos_old;
        ALTER TABLE ventas RENAME TO ventas_old;
        ALTER TABLE detalle_venta RENAME TO detalle_venta_old;
        {SCHEMA}
        {_sql_semillas_roles()}
        INSERT INTO categorias(nombre,descripcion) VALUES ('General','Categoría por defecto');
        INSERT INTO usuarios(id,nombre_completo,usuario,password,rol_id,activo)
            SELECT id, usuario, usuario, password,
                   (SELECT id FROM roles WHERE nombre = CASE WHEN UPPER(rol)='ADMIN' THEN 'ADMIN' ELSE 'VENDEDOR' END),
                   activo FROM usuarios_old;
        INSERT INTO productos(id,codigo,nombre,descripcion,precio_compra,precio_venta,categoria_id,stock_min,activo)
            SELECT id, 'P'||printf('%04d',id), nombre, '', 0, precio,
                   (SELECT id FROM categorias WHERE nombre='General'), stock_min, activo FROM productos_old;
        INSERT INTO inventario(producto_id,cantidad,ubicacion,fecha_actualizacion)
            SELECT id, stock, 'Almacén principal', datetime('now','localtime') FROM productos_old;
        INSERT INTO movimientos_inventario(producto_id,tipo,cantidad,stock_anterior,stock_resultante,motivo,fecha,usuario_id)
            SELECT id,'ENTRADA',stock,0,stock,'Saldo inicial (migración)',datetime('now','localtime'),{admin}
            FROM productos_old WHERE stock > 0;
        {clientes_sql}
        INSERT INTO ventas(id,fecha,usuario_id,cliente_id,tipo_comprobante,total)
            SELECT v.id, v.fecha, {usuario}, {cliente}, {tipo}, v.total FROM ventas_old v;
        INSERT INTO detalle_ventas(id,venta_id,producto_id,cantidad,precio_unit,subtotal)
            SELECT id, venta_id, producto_id, cantidad, precio_unit, subtotal FROM detalle_venta_old;
        DROP TABLE detalle_venta_old;
        DROP TABLE ventas_old;
        DROP TABLE productos_old;
        DROP TABLE usuarios_old;
        COMMIT;
        """)
    except Exception:
        try:
            con.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")


def _sembrar(con):
    if con.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 0:
        con.executescript(_sql_semillas_roles())
    # El rol ADMIN siempre tiene todos los módulos.
    con.execute("UPDATE roles SET permisos=? WHERE nombre='ADMIN'", (",".join(MODULOS),))
    if con.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0:
        con.executemany("INSERT INTO categorias(nombre,descripcion) VALUES (?,?)", [
            ("General", "Categoría por defecto"),
            ("Celulares", "Equipos móviles"),
            ("Accesorios", "Cargadores, fundas, audífonos y similares"),
        ])
    if con.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        con.execute("""INSERT INTO usuarios(nombre_completo,usuario,password,rol_id)
                       VALUES ('Administrador','admin',?,(SELECT id FROM roles WHERE nombre='ADMIN'))""",
                    (generate_password_hash("1234"),))


def _hashear_passwords(con):
    for u in con.execute("SELECT id, password FROM usuarios").fetchall():
        if not u["password"].startswith(("scrypt:", "pbkdf2:")):
            con.execute("UPDATE usuarios SET password=? WHERE id=?", (generate_password_hash(u["password"]), u["id"]))


def init_db():
    con = get_db()
    try:
        if _es_legado(con):
            _migrar_legado(con)
        con.executescript(SCHEMA)
        _asegurar_columnas(con)
        _sembrar(con)
        _hashear_passwords(con)
    finally:
        con.close()
