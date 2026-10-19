(function () {
  const form = document.querySelector('form[data-crud="producto"]');
  if (!form) return;
  const $ = (id) => document.getElementById(id);
  const MAX = 5 * 1024 * 1024;

  // ---------- foto: vista previa y validación antes de enviar
  const entrada = $('f-imagen'), prev = $('foto-prev'), nota = $('foto-nota'), quitar = $('foto-quitar');
  const notaInicial = nota.textContent;
  let urlTemporal = null;

  function ponerFoto(src) {
    prev.replaceChildren();
    if (src) {
      const img = document.createElement('img');
      img.className = 'foto'; img.src = src; img.alt = 'Vista previa de la foto';
      prev.append(img);
    } else {
      const ph = document.createElement('span');
      ph.className = 'foto ph'; ph.style.setProperty('--h', 215); ph.setAttribute('aria-hidden', 'true'); ph.textContent = '+';
      prev.append(ph);
    }
  }
  function limpiarTemporal() { if (urlTemporal) { URL.revokeObjectURL(urlTemporal); urlTemporal = null; } }

  entrada.addEventListener('change', () => {
    limpiarTemporal();
    const f = entrada.files[0];
    nota.classList.remove('neg');
    if (!f) { ponerFoto(form.dataset.fotoActual || ''); nota.textContent = notaInicial; return; }
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) {
      entrada.value = ''; nota.textContent = 'Formato no admitido. Use JPG, PNG o WEBP.'; nota.classList.add('neg'); return;
    }
    if (f.size > MAX) {
      entrada.value = ''; nota.textContent = 'La imagen supera los 5 MB. Elija una más liviana.'; nota.classList.add('neg'); return;
    }
    urlTemporal = URL.createObjectURL(f);
    ponerFoto(urlTemporal);
    nota.textContent = f.name;
    if (quitar) quitar.querySelector('input').checked = false;
  });

  form.addEventListener('crud:nuevo', () => {
    limpiarTemporal();
    delete form.dataset.fotoActual;
    ponerFoto('');
    quitar.hidden = true;
    nota.textContent = notaInicial; nota.classList.remove('neg');
    avisarMargen();
  });
  form.addEventListener('crud:editar', (e) => {
    const img = e.detail.img || '';
    form.dataset.fotoActual = img;
    ponerFoto(img);
    quitar.hidden = !img;
    avisarMargen();
  });
  quitar.querySelector('input').addEventListener('change', (e) => {
    if (e.target.checked) { entrada.value = ''; limpiarTemporal(); ponerFoto(''); }
    else ponerFoto(form.dataset.fotoActual || '');
  });

  // ---------- aviso de margen negativo
  function avisarMargen() {
    const pc = parseFloat(form.elements.precio_compra.value) || 0;
    const pv = parseFloat(form.elements.precio_venta.value);
    $('aviso-margen').hidden = !(pc > 0 && pv >= 0 && pv < pc);
  }
  ['precio_compra', 'precio_venta'].forEach((n) => form.elements[n].addEventListener('input', avisarMargen));

  // ---------- filtros de la tabla
  const filas = Array.from(document.querySelectorAll('#tabla-productos tbody tr'));
  const q = $('p-buscar'), cat = $('p-cat'), estado = $('p-estado');
  function filtrar() {
    const t = q.value.trim().toLowerCase();
    let n = 0;
    filas.forEach((tr) => {
      const ok = (!t || tr.textContent.toLowerCase().includes(t))
        && (!cat.value || tr.dataset.cat === cat.value)
        && (!estado.value || (estado.value === 'sinfoto' ? tr.dataset.foto === '0'
          : estado.value === 'bajo' ? ['bajo', 'agotado'].includes(tr.dataset.estado) : tr.dataset.estado === estado.value));
      tr.hidden = !ok;
      if (ok) n++;
    });
    $('cuenta-prod').textContent = n;
    const vacio = $('p-vacio');
    if (vacio) vacio.hidden = n > 0;
  }
  [q, cat, estado].forEach((el) => el.addEventListener('input', filtrar));

  // ---------- ?editar=ID desde el catálogo
  const id = new URLSearchParams(location.search).get('editar');
  if (id) {
    const fila = filas.find((tr) => tr.dataset.id === id);
    const b = fila && fila.querySelector('.js-editar');
    if (b) b.click();
  }
})();
