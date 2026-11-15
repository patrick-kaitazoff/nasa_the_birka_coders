import L from "leaflet";

/**
 * Acomoda los nombres de estados y condados de EE. UU. sobre el mapa. Cada zona tenía su nombre siempre
 * puesto en el centro: en el noreste los estados se pisaban entre sí y en Texas (254 condados) quedaba una mancha de
 * letras ilegible.
 *
 * La regla es la de cualquier mapa: un nombre se pone solo si entra dentro de su zona tal como se ve en pantalla y no
 * pisa a otro ya puesto; primero las zonas más grandes. Si no entra, se prueba la versión corta (la sigla del
 * estado); si tampoco, no se pone. Al acercarse entran más. La zona elegida y la que está bajo el mouse se nombran
 * siempre, con fondo, así cualquier condado se puede leer apoyando el mouse.
 */
export type Caja = [number, number, number, number];

export interface OpcionesNombres {
  /** las clases de la etiqueta (para medir el texto con su letra) */
  clase: string;
  nombre: (p: any) => string;
  corto?: (p: any) => string | undefined;
  /** se nombra aunque no entre o pise a otra (la elegida, la que está bajo el mouse) */
  forzar?: (p: any) => boolean;
  esconder?: (p: any) => boolean;
  /** cajas ya ocupadas por nombres de más arriba (los estados, para los condados) */
  ocupado?: Caja[];
}

const anchos = new Map<string, number>();
let regla: HTMLElement | null = null;

function medir(mapa: L.Map, clase: string, texto: string): number {
  const clave = clase + "|" + texto;
  const guardado = anchos.get(clave);
  if (guardado != null) return guardado;
  const panel = mapa.getPane("tooltipPane");
  if (!panel) return texto.length * 7;
  if (!regla || regla.parentElement !== panel) {
    regla = document.createElement("div");
    regla.style.cssText = "position:absolute;left:-9999px;top:0;visibility:hidden;white-space:nowrap;animation:none";
    panel.appendChild(regla);
  }
  regla.className = `leaflet-tooltip ${clase}`;
  regla.textContent = texto;
  const ancho = regla.offsetWidth;
  if (ancho > 0) anchos.set(clave, ancho);
  return ancho || texto.length * 7;
}

const ALTO = 16;
const escapar = (s: string) => s.replace(/[<>&]/g, "");

/** Devuelve las cajas que quedaron ocupadas (las recibidas más las nuevas), en píxeles del contenedor del mapa. */
export function acomodarNombres(mapa: L.Map, capa: L.GeoJSON | null, o: OpcionesNombres): Caja[] {
  const ocupado: Caja[] = [...(o.ocupado || [])];
  if (!capa || !mapa.hasLayer(capa)) return ocupado;
  const choca = (c: Caja) => ocupado.some((q) => c[0] < q[2] && c[2] > q[0] && c[1] < q[3] && c[3] > q[1]);
  type Item = { l: any; p: any; tt: L.Tooltip; el: HTMLElement; w: number; h: number; x: number; y: number; forzada: boolean };
  const items: Item[] = [];
  capa.eachLayer((l: any) => {
    const tt = l.getTooltip?.() as L.Tooltip | undefined;
    const el = tt?.getElement();
    if (!tt || !el) return;
    const b = l.getBounds() as L.LatLngBounds;
    const a = mapa.latLngToContainerPoint(b.getNorthWest()), z = mapa.latLngToContainerPoint(b.getSouthEast());
    const c = mapa.latLngToContainerPoint(tt.getLatLng() || b.getCenter());
    const p = l.feature?.properties || {};
    items.push({ l, p, tt, el, w: z.x - a.x, h: z.y - a.y, x: c.x, y: c.y, forzada: !!o.forzar?.(p) });
  });
  items.sort((a, b) => (a.forzada === b.forzada ? b.w * b.h - a.w * a.h : a.forzada ? -1 : 1));
  for (const it of items) {
    let texto: string | null = null;
    if (!o.esconder?.(it.p)) {
      const largo = o.nombre(it.p), corto = o.corto?.(it.p);
      for (const t of [largo, corto]) {
        if (!t) continue;
        const ancho = medir(mapa, o.clase, t);
        const caja: Caja = [it.x - ancho / 2 - 3, it.y - ALTO / 2, it.x + ancho / 2 + 3, it.y + ALTO / 2];
        const entra = ancho <= it.w * 0.9 && ALTO <= it.h * 0.9;
        // la corta (dos letras) se pone aunque la zona sea más chica que el texto, mientras no pise a nadie
        if (it.forzada || ((entra || t === corto) && !choca(caja))) { texto = t; ocupado.push(caja); break; }
      }
    }
    const activa = it.forzada && texto != null;
    // el fondo de la activa cambia el ancho: hay que volver a centrarla
    const cambio = it.el.classList.contains("nombre-activo") !== activa || it.el.classList.contains("nombre-oculto");
    it.el.classList.toggle("nombre-activo", activa);
    if (texto == null) { it.el.classList.add("nombre-oculto"); continue; }
    it.el.classList.remove("nombre-oculto");
    if (it.l.__nombrePuesto !== texto) {
      it.l.__nombrePuesto = texto;
      it.tt.setContent(`<span data-no-traducir>${escapar(texto)}</span>`);
    } else if (cambio) it.tt.update();
  }
  return ocupado;
}
