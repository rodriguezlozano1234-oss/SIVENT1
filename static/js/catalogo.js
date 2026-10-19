(function () {
  const rejilla = document.getElementById('rejilla');
  if (!rejilla) return;
  const cfg = window.SIVENT_CAT || {};
  const $ = (id) => document.getElementById(id);
  const tarjetas = Array.from(rejilla.children);
  const soles = (n) => 'S/ ' + Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  let categoria = '';

  // ---------- filtros y orden
  function aplicar() {
    const q = $('c-buscar').value.trim().toLowerCase();
    const soloStock = $('c-disp').checked;
    let n = 0;
    tarjetas.forEach((t) => {
      const ok = (!categoria || t.dataset.cat === categoria)
        && (!q || t.dataset.texto.includes(q))
        && (!soloStock || Number(t.dataset.stock) > 0);
      t.hidden = !ok;
      if (ok) n++;
    });
    $('c-cuenta').textContent = n + (n === 1 ? ' producto' : ' productos');
    $('c-vacio').hidden = n > 0;
    // el PDF respeta la categoría y el filtro de stock elegidos
    const p = new URLSearchParams();
    if (categoria) p.set('categoria', categoria);
    if (soloStock) p.set('disponibles', '1');
    $('cat-pdf').href = cfg.pdf + (p.toString() ? '?' + p : '');
  }
  function ordenar() {
    const o = $('c-orden').value;
    const clave = {
      nombre: (a, b) => a.dataset.nombre.localeCompare(b.dataset.nombre, 'es'),
      'precio-asc': (a, b) => a.dataset.precio - b.dataset.precio,
      'precio-desc': (a, b) => b.dataset.precio - a.dataset.precio,
      reciente: (a, b) => b.dataset.id - a.dataset.id,
    }[o];
    tarjetas.sort(clave).forEach((t) => rejilla.append(t));
  }
  document.querySelectorAll('.chip-btn').forEach((b) =>
    b.addEventListener('click', () => {
      categoria = b.dataset.cat;
      document.querySelectorAll('.chip-btn').forEach((x) => x.classList.toggle('on', x === b));
      aplicar();
    }));
  $('c-buscar').addEventListener('input', aplicar);
  $('c-disp').addEventListener('change', aplicar);
  $('c-orden').addEventListener('change', ordenar);

  const inicial = new URLSearchParams(location.search).get('categoria');
  if (inicial) { const b = document.querySelector('.chip-btn[data-cat="' + CSS.escape(inicial) + '"]'); if (b) b.click(); }
  aplicar();

  // ---------- detalle
  const dlg = $('detalle');
  function abrir(t) {
    const p = JSON.parse(t.dataset.json);
    const foto = $('d-foto');
    foto.replaceChildren();
    if (p.img) {
      const img = document.createElement('img');
      img.className = 'foto grande'; img.src = p.img; img.alt = p.nombre;
      foto.append(img);
    } else {
      const ph = document.createElement('span');
      ph.className = 'foto ph grande'; ph.style.setProperty('--h', p.tono); ph.textContent = p.iniciales;
      ph.setAttribute('role', 'img'); ph.setAttribute('aria-label', 'Sin foto: ' + p.nombre);
      foto.append(ph);
    }
    $('d-meta').textContent = p.categoria + ' · ' + p.codigo;
    $('d-nombre').textContent = p.nombre;
    $('d-precio').textContent = soles(p.precio);
    $('d-desc').textContent = p.descripcion || '';
    $('d-desc').hidden = !p.descripcion;
    const st = $('d-stock');
    st.replaceChildren();
    const tag = document.createElement('span');
    tag.className = 'tag ' + (p.stock > p.minimo ? 'okk' : 'bajo');
    tag.textContent = p.stock === 0 ? 'Agotado' : p.stock > p.minimo ? p.stock + ' disponibles' : 'Quedan ' + p.stock;
    st.append(tag);
    $('d-ubic').textContent = p.ubicacion;
    $('d-ubic-fila').hidden = !p.ubicacion;
    const cf = $('d-costo-fila');
    cf.hidden = p.costo === null || p.costo === undefined;
    if (!cf.hidden) {
      const margen = p.precio > 0 ? Math.round((p.precio - p.costo) / p.precio * 100) : 0;
      $('d-costo').textContent = soles(p.costo) + ' · margen ' + margen + '%';
    }
    const v = $('d-vender');
    if (v) { v.href = cfg.ventas + '?q=' + encodeURIComponent(p.codigo); v.hidden = p.stock === 0; }
    const e = $('d-editar');
    if (e) e.href = cfg.editar + '?editar=' + p.id;
    dlg.showModal();
  }
  tarjetas.forEach((t) => {
    t.addEventListener('click', () => abrir(t));
    t.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(t); } });
  });
  $('d-cerrar').addEventListener('click', () => dlg.close());
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });  // clic fuera del cuadro
})();
