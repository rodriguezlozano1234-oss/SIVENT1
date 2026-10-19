(function () {
  const $ = (id) => document.getElementById(id);
  const productos = JSON.parse($('productos-data').textContent);
  const items = new Map(); // id -> {cantidad, precio}
  const csrf = document.querySelector('meta[name=csrf]').content;
  const soles = (n) => 'S/ ' + Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const porId = (id) => productos.find((p) => p.id === id);

  function el(tag, props, ...hijos) {
    const e = document.createElement(tag);
    Object.assign(e, props || {});
    hijos.forEach((h) => e.append(h));
    return e;
  }
  function mostrarError(msg) { const e = $('error'); e.textContent = msg; e.hidden = !msg; }

  function pintarProductos() {
    const q = $('buscar').value.trim().toLowerCase();
    const cuerpo = $('lista-productos');
    cuerpo.replaceChildren();
    const lista = productos.filter((p) => !q || p.nombre.toLowerCase().includes(q) || p.codigo.toLowerCase().includes(q));
    if (!lista.length) {
      cuerpo.append(el('tr', {}, el('td', { colSpan: 4, className: 'vacio', textContent: 'No hay productos que coincidan.' })));
      return;
    }
    lista.forEach((p) => {
      const b = el('button', { type: 'button', className: 'btn chico', textContent: items.has(p.id) ? 'Agregado' : 'Agregar', disabled: items.has(p.id) });
      b.addEventListener('click', () => { items.set(p.id, { cantidad: 1, precio: p.precio_compra }); mostrarError(''); pintarProductos(); pintarCarrito(); });
      cuerpo.append(el('tr', {},
        el('td', {}, p.nombre, el('br'), el('small', { className: 'muted', textContent: p.codigo })),
        el('td', { className: 'num', textContent: soles(p.precio_compra) }),
        el('td', { className: 'num', textContent: p.stock }),
        el('td', { className: 'acc' }, b)));
    });
  }

  const subtotales = new Map(); // id -> celda, para actualizar sin perder el foco al escribir
  function actualizarTotales() {
    let total = 0;
    items.forEach((it, id) => {
      const sub = Math.round(it.cantidad * it.precio * 100) / 100;
      total += sub;
      if (subtotales.has(id)) subtotales.get(id).textContent = soles(sub);
    });
    $('total').textContent = soles(total);
    $('carrito-vacio').hidden = items.size > 0;
    $('confirmar').disabled = items.size === 0;
  }
  function pintarCarrito() {
    const cuerpo = $('carrito');
    cuerpo.replaceChildren();
    subtotales.clear();
    items.forEach((it, id) => {
      const p = porId(id);
      const cant = el('input', { type: 'number', min: 1, step: 1, value: it.cantidad, ariaLabel: 'Cantidad de ' + p.nombre });
      const costo = el('input', { type: 'number', min: 0, step: 0.01, value: it.precio, ariaLabel: 'Costo unitario de ' + p.nombre });
      cant.addEventListener('input', () => { it.cantidad = parseInt(cant.value, 10) || 0; actualizarTotales(); });
      costo.addEventListener('input', () => { it.precio = parseFloat(costo.value) || 0; actualizarTotales(); });
      const sub = el('td', { className: 'num' });
      subtotales.set(id, sub);
      const quitar = el('button', { type: 'button', className: 'btn peligro chico', textContent: 'Quitar' });
      quitar.addEventListener('click', () => { items.delete(id); pintarProductos(); pintarCarrito(); });
      cuerpo.append(el('tr', {}, el('td', { textContent: p.nombre }), el('td', { className: 'num' }, cant),
        el('td', { className: 'num' }, costo), sub, el('td', { className: 'acc' }, quitar)));
    });
    actualizarTotales();
  }

  $('buscar').addEventListener('input', pintarProductos);
  $('confirmar').addEventListener('click', async () => {
    mostrarError('');
    const btn = $('confirmar');
    btn.disabled = true;
    try {
      const r = await fetch('/api/compras', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({ proveedor: $('proveedor').value,
          items: [...items].map(([id, it]) => ({ id, cantidad: it.cantidad, precio: it.precio })) }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.status === 401) { location.href = '/login'; return; }
      if (!r.ok) { mostrarError(d.error || 'No se pudo registrar la compra.'); btn.disabled = false; return; }
      items.forEach((it, id) => { const p = porId(id); p.stock += it.cantidad; p.precio_compra = it.precio; });
      items.clear();
      $('proveedor').value = '';
      const ok = $('resultado');
      ok.replaceChildren('Compra #' + d.id + ' registrada por ' + soles(d.total) + '; el stock ya está actualizado. ',
        el('a', { href: d.detalle, textContent: 'Ver detalle' }));
      ok.hidden = false;
      window.scrollTo({ top: 0, behavior: 'smooth' });
      pintarProductos(); pintarCarrito();
    } catch (e) {
      mostrarError('No hay conexión con el servidor. Revise su red e intente de nuevo.');
      btn.disabled = false;
    }
  });

  pintarProductos();
  pintarCarrito();
})();
