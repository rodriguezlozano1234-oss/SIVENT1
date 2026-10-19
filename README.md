# SIVENT web v2

> **Novedades de esta versión:** módulo **Catálogo con fotos**, anulación de ventas, panel de inventario con valorización, filtros y exportaciones, y límite de intentos de ingreso. Ver la sección «Novedades» más abajo.

Sistema de inventario, compras y ventas con el modelo de datos de 11 tablas: **Usuarios, Roles, Categorías, Productos, Inventario, Clientes, Compras, Detalle de compras, Ventas, Detalle de ventas y Movimientos de inventario**, más los reportes **Ventas** (diario / semanal / mensual) y **Ventas por empleado**.

## Novedades

- **Catálogo con imágenes** (menú *Almacén → Catálogo*): vitrina de tarjetas con foto, precio y disponibilidad; búsqueda, filtro por categoría, orden por nombre/precio/recientes, «solo con stock» y ficha de detalle. Desde la ficha: *Vender este producto* (abre Ventas con el producto buscado) y *Editar*. Los vendedores no ven precios de compra.
- **Fotos de productos**: se suben en *Productos* (JPG, PNG o WEBP, hasta 5 MB). El sistema corrige la orientación del celular, genera versión grande (900 px) y miniatura (360 px) en WEBP y borra la foto anterior al reemplazarla. Se guardan en `data/uploads/productos/` (junto a la base, así persisten en Docker). Sin foto se muestra un recuadro con las iniciales.
- **Catálogo PDF** para clientes (fotos y precios, sin costos): botón «Descargar catálogo (PDF)»; respeta la categoría elegida.
- **Productos**: miniaturas, margen %, aviso de venta bajo el costo, filtros por categoría / stock / sin foto y exportación a CSV.
- **Inventario**: valor del stock a costo y a venta, conteo de agotados y bajos, filtro por estado, fotos y exportación a CSV.
- **Ventas**: fotos y filtro por categoría en la lista de productos; **anulación de ventas** (solo administrador, con motivo): repone el stock con un movimiento de ENTRADA, marca el comprobante PDF como anulado y excluye la venta de totales y reportes.
- **Panel del administrador**: valor del inventario, productos más vendidos del mes y aviso de productos sin foto.
- **Seguridad**: bloqueo temporal tras 5 intentos fallidos de ingreso, cabeceras de seguridad y tope de subida. Si lo sirves por HTTPS define `SIVENT_HTTPS=1`.
- Las bases existentes se actualizan solas al arrancar (columnas `productos.imagen` y datos de anulación en `ventas`).

## Ejecutar

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
python app.py
```

Abre http://127.0.0.1:5000 y elige el acceso:

| Acceso | Usuario | Contraseña |
|---|---|---|
| Administrador | `admin` | `1234` |
| Vendedor | `vendedor` | `vendedor123` |

**Cambia ambas contraseñas** al empezar (*Cambiar contraseña*; el administrador también puede hacerlo en *Usuarios*) y desactiva el usuario `vendedor` de ejemplo si no lo vas a usar.

## Los dos accesos

La pantalla de ingreso tiene un selector **Administrador / Vendedor**. Cada cuenta solo entra por su acceso (un administrador no puede ingresar como vendedor ni al revés) y cada acceso abre un panel con diseño propio:

- **Administrador** (menú lateral azul): panorama del negocio con ventas de hoy y del mes, gráfico de los últimos 7 días, ranking de vendedores del mes, stock bajo, últimas ventas y compras. Gestiona catálogo, inventario, compras, clientes, reportes, usuarios y roles.
- **Vendedor** (barra superior verde azulado): botón grande de *Nueva venta*, sus ventas de hoy y del mes, consulta rápida de stock y precio, y sus últimas ventas. Solo ve y descarga sus propios comprobantes. Los demás roles que crees (por ejemplo ALMACENERO) ingresan también por el acceso Vendedor y ven en la barra solo los módulos que su rol permite.

## Tus datos actuales

`sivent.db` ya viene migrada con tus productos, stock, ventas y usuario. Si prefieres usar otra base (la de la versión Tkinter o la de la web anterior), reemplaza `sivent.db`: **al primer arranque se migra sola** y antes guarda una copia `sivent_antes_de_migrar_<fecha>.db`.

Qué hace la migración: los productos reciben código `P0001…` y la categoría *General* (reasígnalos en *Productos*); el stock pasa a *Inventario* con un movimiento «Saldo inicial (migración)»; las ventas antiguas se conservan con sus detalles (las facturas de la versión anterior crean su cliente con RUC).

## Roles y permisos

Cada rol tiene permisos por módulo y se edita en *Administración → Roles*; los cambios aplican de inmediato.

| Rol (base) | Acceso |
|---|---|
| ADMIN | Todo, incluidos usuarios y roles |
| VENDEDOR | Ventas y clientes (solo ve sus propias ventas) |
| ALMACENERO | Productos, categorías, inventario y compras |

Para ver los reportes y las ventas de todos hay que tener el permiso *Reportes*.

## Cómo se relacionan los módulos

- **Ventas** descargan el stock del *Inventario* y dejan un movimiento de SALIDA («Venta #N»). Si no alcanza el stock, la venta se rechaza completa.
- **Compras** suben el stock (movimiento de ENTRADA «Compra #N») y actualizan el último precio de compra del producto.
- **Inventario** permite entradas, salidas y ajustes por conteo físico, siempre con motivo, usuario y fecha (*Movimientos* es el historial).
- **Factura** exige un cliente con RUC; la **boleta** puede ir a «Público general».
- **Reporte de ventas** sale de `ventas` + `detalle_ventas`; **Ventas por empleado** de `ventas` + `usuarios` (sin tablas nuevas). Ambos se filtran por fechas y se exportan a CSV y PDF. Las semanas van de lunes a domingo.

## Servir a otros equipos

```bash
pip install waitress
set SIVENT_SECRET_KEY=una-clave-larga-y-propia
waitress-serve --listen=0.0.0.0:5000 app:app
```
Sírvelo detrás de HTTPS si sale de tu red local.

## Estructura

```
app.py          sesión, inicio y registro de módulos
db.py           esquema, migración, transacciones y movimientos de inventario
auth.py         permisos por rol y protección CSRF
catalogo.py     vitrina, productos y categorías   imagenes.py   fotos (validación y miniaturas)
       clientes.py   clientes
inventario.py   stock y movimientos           compras.py    compras
ventas.py       ventas y comprobantes PDF     reportes.py   reportes
admin.py        usuarios y roles              pdf.py        generación de PDF
templates/ static/   interfaz
```

## Límites conocidos

- El PDF es un comprobante de control interno; no es un comprobante electrónico válido ante SUNAT.
- Las ventas se pueden anular, pero las compras no (la corrección de una compra se hace con un ajuste de inventario).
- «Proveedor» se guarda como texto dentro de la compra, porque el modelo no incluye tabla de proveedores.
- SQLite basta para pocos puestos de venta; para varios locales conviene MySQL/PostgreSQL.

## Ejecutar con Docker Desktop (Windows + WSL 2)

Este proyecto incluye `Dockerfile` y `compose.yaml`. No necesitas instalar Python en Windows ni configurar un entorno virtual.

1. Descomprime el proyecto y abre PowerShell en la carpeta `sivent_v2` (donde están `compose.yaml` y `Dockerfile`).
2. Asegúrate de que Docker Desktop esté abierto.
3. Construye e inicia la aplicación:

   ```powershell
   docker compose up -d --build
   ```

4. Abre <http://localhost:5000/login>.
5. Comprueba el estado y los registros:

   ```powershell
   docker compose ps
   docker compose logs -f sivent
   ```

Para detener los contenedores sin eliminar los datos: `docker compose down`. Para iniciarlos de nuevo: `docker compose up -d`.

### Persistencia de datos

La base SQLite está en `data/sivent.db`, montada en el contenedor como `/data/sivent.db`. Los datos permanecen en esa carpeta al reconstruir la imagen o detener el contenedor. Haz copias de seguridad de `data/sivent.db` con la aplicación detenida.

### Seguridad

La variable `SIVENT_SECRET_KEY` se configura en `.env`. No compartas ese archivo ni lo subas a un repositorio público. Cambia las contraseñas iniciales `admin/1234` y `vendedor/vendedor123` al ingresar. Esta configuración está pensada para desarrollo o red local; para publicar el sistema en Internet se necesita HTTPS, copias de seguridad y una configuración de producción revisada.
