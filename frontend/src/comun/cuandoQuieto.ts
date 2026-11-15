/** Llama a `fn` cuando la página terminó de dibujar lo nuevo y quedó quieta: dos cuadros (React ya pintó) y después
 * un momento libre del navegador, con un tope para no quedar esperando de más. Sirve para arrancar un fundido
 * recién cuando no lo va a trabar el armado del Plan o del mapa. Devuelve cómo cancelarlo. */
export function cuandoQuieto(fn: () => void, tope = 1200): () => void {
  let cancelado = false;
  let idle = 0;
  let t = 0;
  const r = requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      if (cancelado) return;
      const listo = () => {
        if (!cancelado) fn();
      };
      if ("requestIdleCallback" in window) idle = window.requestIdleCallback(listo, { timeout: tope });
      else t = globalThis.setTimeout(listo, 300) as unknown as number;
    }),
  );
  return () => {
    cancelado = true;
    cancelAnimationFrame(r);
    if (idle) window.cancelIdleCallback(idle);
    clearTimeout(t);
  };
}
