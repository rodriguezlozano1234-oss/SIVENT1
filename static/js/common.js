(function () {
  // Formularios con edición en la misma pantalla: <form data-crud="producto"> + filas con data-json.
  function llenar(form, datos) {
    Array.from(form.elements).forEach((el) => {
      if (!el.name || el.name === 'csrf') return;
      const v = datos[el.name];
      if (el.type === 'checkbox') el.checked = Array.isArray(v) ? v.includes(el.value) : !!v;
      else if (v !== undefined) el.value = v === null ? '' : v;
    });
  }

  document.querySelectorAll('form[data-crud]').forEach((form) => {
    const nombre = form.dataset.crud;
    const titulo = form.querySelector('.crud-titulo');
    const enviar = form.querySelector('.crud-enviar');
    const cancelar = form.querySelector('.crud-cancelar');
    const textoNuevo = enviar.textContent;
    const tituloNuevo = titulo.textContent;

    function modoNuevo() {
      form.reset();
      if (form.elements.id) form.elements.id.value = '';
      form.classList.remove('editando');
      titulo.textContent = tituloNuevo;
      enviar.textContent = textoNuevo;
      cancelar.hidden = true;
      form.dispatchEvent(new CustomEvent('crud:nuevo'));
    }
    cancelar.addEventListener('click', modoNuevo);

    document.querySelectorAll('.js-editar').forEach((b) =>
      b.addEventListener('click', () => {
        const fila = b.closest('[data-json]');
        modoNuevo();
        const datos = JSON.parse(fila.dataset.json);
        llenar(form, datos);
        form.dispatchEvent(new CustomEvent('crud:editar', { detail: datos }));
        form.classList.add('editando');
        titulo.textContent = 'Editar ' + nombre;
        enviar.textContent = 'Guardar cambios';
        cancelar.hidden = false;
        form.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const primero = form.querySelector('input:not([type=hidden]):not([type=checkbox])');
        if (primero) primero.focus({ preventScroll: true });
      })
    );
  });

  document.querySelectorAll('form.js-confirm').forEach((f) =>
    f.addEventListener('submit', (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); })
  );

  document.querySelectorAll('input[data-filtro]').forEach((inp) =>
    inp.addEventListener('input', () => {
      const q = inp.value.trim().toLowerCase();
      document.querySelectorAll(inp.dataset.filtro + ' tbody tr').forEach((tr) => {
        tr.hidden = q && !tr.textContent.toLowerCase().includes(q);
      });
    })
  );
})();

// Miniatura de producto (foto o recuadro con iniciales), igual que la que dibuja el servidor.
window.fotoMini = function (img, nombre) {
  const palabras = (nombre || '').trim().split(/[\s\-_/]+/).filter(Boolean);
  let e;
  if (img) {
    e = document.createElement('img');
    e.src = img; e.alt = ''; e.loading = 'lazy'; e.className = 'foto';
  } else {
    e = document.createElement('span');
    e.className = 'foto ph';
    e.setAttribute('aria-hidden', 'true');
    e.style.setProperty('--h', [...(nombre || '')].reduce((a, c, i) => a + c.codePointAt(0) * (i + 1), 0) % 360);
    e.textContent = (palabras.slice(0, 2).map((p) => p[0]).join('') || '?').toUpperCase();
  }
  return e;
};
