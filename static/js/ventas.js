(function () {
  const $ = (id) => document.getElementById(id);
  const productos = JSON.parse($('productos-data').textContent);
  const carrito = new Map(); // id -> cantidad
  let cliente = null;        // {id, tipo_documento, numero_documento, nombre} o null = público general
  const csrf = document.querySelector('meta[name=csrf]').content;
  const soles = (n) => 'S/ ' + Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const porId = (id) => productos.find((p) => p.id === id);

  function el(tag, props, ...hijos) {
    const e = document.createElement(tag);
    Object.assign(e, props || {});
    hijos.forEach((h) => e.append(h));
    return e;
  }
  function boton(texto, onclick, props) {
    const b = el('button', Object.assign({ type: 'button', textContent: texto }, props));
    b.addEventListener('click', onclick);
    return b;
  }
  function mostrarError(msg) { const e = $('error'); e.textContent = msg; e.hidden = !msg; }

  // ---------------- productos
  function pintarProductos() {
    const q = $('buscar').value.trim().toLowerCase();
    const cat = $('categoria').value;
    const cuerpo = $('lista-productos');
    cuerpo.replaceChildren();
    const lista = productos.filter((p) => (!cat || String(p.cat) === cat)
      && (!q || p.nombre.toLowerCase().includes(q) || p.codigo.toLowerCase().includes(q)));
    if (!lista.length) {
      cuerpo.append(el('tr', {}, el('td', { colSpan: 4, className: 'vacio', textContent: 'No hay productos que coincidan.' })));
      return;
    }
    lista.forEach((p) => {
      const libre = p.stock - (carrito.get(p.id) || 0);
      const tdStock = el('td', { className: 'num', textContent: p.stock });
      if (p.stock <= p.stock_min) tdStock.append(' ', el('span', { className: 'tag bajo', textContent: 'bajo' }));
      const acc = libre > 0
        ? boton('Agregar', () => agregar(p.id), { className: 'btn chico' })
        : el('span', { className: 'sin-stock', textContent: p.stock > 0 ? 'Todo en carrito' : 'Sin stock' });
      cuerpo.append(el('tr', {},
        el('td', { className: 'prod-celda' }, window.fotoMini(p.img, p.nombre),
          el('span', {}, p.nombre, el('br'), el('small', { className: 'muted', textContent: p.codigo }))),
        el('td', { className: 'num', textContent: soles(p.precio) }),
        tdStock,
        el('td', { className: 'acc' }, acc)));
    });
  }

  // ---------------- carrito
  function pintarCarrito() {
    const cuerpo = $('carrito');
    cuerpo.replaceChildren();
    let total = 0;
    carrito.forEach((cant, id) => {
      const p = porId(id);
      const sub = Math.round(p.precio * cant * 100) / 100;
      total += sub;
      cuerpo.append(el('tr', {},
        el('td', { textContent: p.nombre }),
        el('td', { className: 'num' }, el('span', { className: 'cant' },
          boton('−', () => cambiar(id, -1), { ariaLabel: 'Quitar una unidad de ' + p.nombre }),
          el('span', { textContent: cant }),
          boton('+', () => cambiar(id, 1), { ariaLabel: 'Agregar una unidad de ' + p.nombre, disabled: cant >= p.stock }))),
        el('td', { className: 'num', textContent: soles(sub) }),
        el('td', { className: 'acc' }, boton('Quitar', () => { carrito.delete(id); refrescar(); }, { className: 'btn peligro chico' }))));
    });
    $('total').textContent = soles(total);
    $('carrito-vacio').hidden = carrito.size > 0;
    $('confirmar').disabled = carrito.size === 0;
  }
  function refrescar() { pintarProductos(); pintarCarrito(); }
  function agregar(id) {
    if ((carrito.get(id) || 0) >= porId(id).stock) return;
    carrito.set(id, (carrito.get(id) || 0) + 1);
    mostrarError('');
    refrescar();
  }
  function cambiar(id, d) {
    const n = (carrito.get(id) || 0) + d;
    if (n <= 0) carrito.delete(id); else if (n <= porId(id).stock) carrito.set(id, n);
    refrescar();
  }

  // ---------------- cliente
  function pintarCliente() {
    const caja = $('cliente-actual');
    caja.replaceChildren();
    if (cliente) {
      caja.append(el('span', {}, el('strong', { textContent: cliente.nombre }), el('br'),
        el('small', { className: 'muted', textContent: cliente.tipo_documento + ' ' + cliente.numero_documento })),
        boton('Quitar', () => { cliente = null; pintarCliente(); }, { className: 'btn sec chico' }));
    } else {
      caja.append(el('span', { className: 'muted', textContent: 'Público general (sin datos de cliente)' }));
    }
    $('aviso-factura').hidden = $('tipo').value !== 'FACTURA' || (cliente && cliente.tipo_documento === 'RUC');
  }
  function elegirCliente(c) {
    cliente = c;
    $('cliente-buscar').value = '';
    $('cliente-resultados').hidden = true;
    pintarCliente();
  }
  let espera;
  $('cliente-buscar').addEventListener('input', () => {
    clearTimeout(espera);
    const q = $('cliente-buscar').value.trim();
    const caja = $('cliente-resultados');
    if (q.length < 2) { caja.hidden = true; return; }
    espera = setTimeout(async () => {
      try {
        const r = await fetch('/api/clientes?q=' + encodeURIComponent(q));
        const lista = r.ok ? await r.json() : [];
        caja.replaceChildren();
        if (!lista.length) caja.append(el('p', { className: 'vacio', textContent: 'Sin resultados. Puede registrarlo abajo.' }));
        lista.forEach((c) => caja.append(boton(c.nombre + ' — ' + c.tipo_documento + ' ' + c.numero_documento, () => elegirCliente(c))));
        caja.hidden = false;
      } catch (e) { caja.hidden = true; }
    }, 250);
  });
  const ncGuardar = $('nc-guardar');
  if (ncGuardar) ncGuardar.addEventListener('click', async () => {
    mostrarError('');
    const r = await fetch('/api/clientes', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      body: JSON.stringify({ tipo_documento: $('nc-tipo').value, numero_documento: $('nc-num').value, nombre: $('nc-nombre').value }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { mostrarError(d.error || 'No se pudo registrar el cliente.'); return; }
    elegirCliente(d);
    $('nc-num').value = ''; $('nc-nombre').value = '';
    document.querySelector('.nuevo-cliente').open = false;
  });
  $('tipo').addEventListener('change', pintarCliente);
  $('buscar').addEventListener('input', pintarProductos);
  $('categoria').addEventListener('input', pintarProductos);
  const q0 = new URLSearchParams(location.search).get('q');  // viene del botón «Vender» del catálogo
  if (q0) $('buscar').value = q0;

  // ---------------- confirmar
  $('confirmar').addEventListener('click', async () => {
    mostrarError('');
    if ($('tipo').value === 'FACTURA' && !(cliente && cliente.tipo_documento === 'RUC')) {
      mostrarError('Para emitir una factura elija un cliente con RUC.');
      return;
    }
    const btn = $('confirmar');
    btn.disabled = true;
    try {
      const r = await fetch('/api/ventas', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
        body: JSON.stringify({
          items: [...carrito].map(([id, cantidad]) => ({ id, cantidad })),
          tipo: $('tipo').value, cliente_id: cliente ? cliente.id : null,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.status === 401) { location.href = '/login'; return; }
      if (!r.ok) {
        mostrarError(d.error || 'No se pudo registrar la venta.');
        if (r.status === 409) setTimeout(() => location.reload(), 3000); // stock cambió: recargar datos
        btn.disabled = false;
        return;
      }
      carrito.forEach((cant, id) => { porId(id).stock -= cant; });
      carrito.clear();
      cliente = null; pintarCliente();
      const ok = $('resultado');
      ok.replaceChildren('Venta registrada por ' + soles(d.total) + '. ',
        el('a', { href: d.comprobante, target: '_blank', rel: 'noopener', textContent: 'Descargar comprobante (PDF)' }));
      ok.hidden = false;
      window.scrollTo({ top: 0, behavior: 'smooth' });
      refrescar();
    } catch (e) {
      mostrarError('No hay conexión con el servidor. Revise su red e intente de nuevo.');
      btn.disabled = false;
    }
  });

  pintarCliente();
  refrescar();
})();
