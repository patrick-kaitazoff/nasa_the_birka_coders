/** Los archivos de los cuatro ejemplos de la portada, bajados de antemano y sin apuro.
 *
 * Hasta ahora un ejemplo empezaba a cargarse recién con el mouse apoyado en su botón (speculationrules de
 * index.html). Quien toca sin apoyarlo, o entra desde el celular, Firefox o Safari (que no arman la página por
 * adelantado), esperaba la bajada después del clic: la ficha y el relieve son poco, pero la foto satelital que va
 * encima del 3D pesa 0,3 a 1 MB y mientras llega el terreno de alrededor se ve verdoso.
 *
 * Se piden con <link rel="prefetch">: el navegador los baja con la prioridad más baja, cuando no tiene otra cosa
 * que hacer, y los deja en su caché; al abrir el ejemplo, /app los pide con la misma dirección y ya están. Son
 * unos 2,7 MB entre los cuatro (casi todo, las fotos). Van en el orden en que se ven en la portada y de a un
 * ejemplo por vez. No se arma ninguna página ni se llama al servidor: eso sigue pasando al apoyar el mouse. */
const EJEMPLOS: Array<[ficha: string, id: string]> = [
  ["campo_demo", "uy"], ["terreno_pucon", "pucon"], ["terreno_mosela", "mosela"], ["terreno_lunarejo", "lunarejo"],
];
/** cuánto después de que la portada terminó de cargar: después del trigo 3D y de la entrada de los videos (2,5 s) */
const ESPERA_MS = 4000;
const ENTRE_EJEMPLOS_MS = 1200;

function pedir(href: string) {
  const l = document.createElement("link");
  l.rel = "prefetch";
  l.href = href;
  document.head.appendChild(l);
}

export function adelantarEjemplos(): () => void {
  const red = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  // con ahorro de datos o una conexión lenta no se baja nada que la persona no pidió
  if (red?.saveData || /(^|-)2g$/.test(red?.effectiveType || "")) return () => {};
  const relojes: number[] = [];
  const empezar = () => {
    EJEMPLOS.forEach(([ficha, id], i) => {
      relojes.push(window.setTimeout(() => {
        pedir(`/ejemplos/${ficha}.fieldshift.json`);
        pedir(`/ejemplos/relieve_${id}.json`);
        pedir(`/ejemplos/foto_${id}.jpg`);
      }, ESPERA_MS + i * ENTRE_EJEMPLOS_MS));
    });
  };
  if (document.readyState === "complete") empezar();
  else addEventListener("load", empezar, { once: true });
  return () => { relojes.forEach(clearTimeout); removeEventListener("load", empezar); };
}
