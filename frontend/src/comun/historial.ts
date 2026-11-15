import { useApp } from "../store";
import type { Pestania } from "../tipos";

/**
 * El botón «atrás» del navegador vuelve a la parte anterior de la herramienta. La herramienta es una sola página: antes, ir de Plan a
 * Comparar no quedaba en el historial y «atrás» sacaba a la portada.
 *
 * Cada cambio de parte agrega un paso al historial (la dirección no cambia); «atrás» y «adelante» vuelven a esa
 * parte. Desde la primera parte, «atrás» sigue yendo a la portada. Si la parte ya no existe (por ejemplo, se empezó
 * un campo de cero y no hay plan), se queda donde está.
 */
let porHistorial = false;

function disponible(p: Pestania): boolean {
  const s = useApp.getState();
  if (p === "mapa") return true;
  if (p === "plan" || p === "vista3d") return !!s.plan;
  return !!s.analisis;
}

function conectar() {
  history.replaceState({ ...(history.state || {}), fsPestania: useApp.getState().pestania }, "");
  useApp.subscribe((s, antes) => {
    if (s.pestania === antes.pestania) return;
    if (porHistorial) {
      porHistorial = false;
      return;
    }
    history.pushState({ fsPestania: s.pestania }, "");
  });
  addEventListener("popstate", (e) => {
    const p = (e.state as { fsPestania?: Pestania } | null)?.fsPestania;
    const s = useApp.getState();
    if (!p || p === s.pestania || !disponible(p)) return;
    porHistorial = true;
    s.setPestania(p);
  });
}

/** Se conecta cuando la página se ve: si se está armando por adelantado (la portada la pide antes del clic), el
 * historial todavía no es el de la pestaña. */
export function conectarHistorial() {
  if ((document as Document & { prerendering?: boolean }).prerendering) {
    document.addEventListener("prerenderingchange", conectar, { once: true });
  } else {
    conectar();
  }
}
