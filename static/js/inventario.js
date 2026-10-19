(function () {
  const tipo = document.getElementById('m-tipo');
  const etiqueta = document.getElementById('m-cant-label');
  const cant = document.getElementById('m-cant');
  function ajustar() {
    const aj = tipo.value === 'AJUSTE';
    etiqueta.textContent = aj ? 'Stock contado' : 'Cantidad';
    cant.min = aj ? 0 : 1;
  }
  tipo.addEventListener('change', ajustar);
  ajustar();
  document.querySelectorAll('.js-mov').forEach((b) =>
    b.addEventListener('click', () => {
      document.getElementById('m-prod').value = b.dataset.id;
      document.getElementById('form-mov').scrollIntoView({ behavior: 'smooth' });
      cant.focus({ preventScroll: true });
    })
  );
})();

(function () {
  const q = document.getElementById('i-buscar'), estado = document.getElementById('i-estado');
  if (!q) return;
  const filas = Array.from(document.querySelectorAll('#tabla-inv tbody tr'));
  function filtrar() {
    const t = q.value.trim().toLowerCase();
    filas.forEach((tr) => {
      tr.hidden = !((!t || tr.textContent.toLowerCase().includes(t)) && (!estado.value || tr.dataset.estado === estado.value));
    });
  }
  q.addEventListener('input', filtrar);
  estado.addEventListener('input', filtrar);
})();
