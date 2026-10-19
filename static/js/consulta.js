(function () {
  const datos = JSON.parse(document.getElementById('productos-data').textContent);
  const entrada = document.getElementById('consulta');
  const salida = document.getElementById('consulta-res');
  const soles = (n) => 'S/ ' + Number(n).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  entrada.addEventListener('input', () => {
    const q = entrada.value.trim().toLowerCase();
    salida.replaceChildren();
    if (!q) {
      const p = document.createElement('p');
      p.className = 'vacio';
      p.textContent = 'Escriba para ver precio y disponibilidad.';
      salida.append(p);
      return;
    }
    const hallados = datos.filter((p) => p.nombre.toLowerCase().includes(q) || p.codigo.toLowerCase().includes(q)).slice(0, 6);
    if (!hallados.length) {
      const p = document.createElement('p');
      p.className = 'vacio';
      p.textContent = 'No hay productos que coincidan.';
      salida.append(p);
      return;
    }
    hallados.forEach((p) => {
      const fila = document.createElement('div');
      fila.className = 'consulta-fila';
      const izq = document.createElement('span');
      izq.className = 'prod-celda';
      const txt = document.createElement('span');
      txt.append(p.nombre, document.createElement('br'));
      const cod = document.createElement('small');
      cod.className = 'muted';
      cod.textContent = p.codigo + ' · ' + soles(p.precio);
      txt.append(cod);
      izq.append(window.fotoMini(p.img, p.nombre), txt);
      const der = document.createElement('span');
      der.className = 'tag ' + (p.stock > 0 ? 'okk' : 'bajo');
      der.textContent = p.stock > 0 ? p.stock + ' disponibles' : 'Sin stock';
      fila.append(izq, der);
      salida.append(fila);
    });
  });
})();
