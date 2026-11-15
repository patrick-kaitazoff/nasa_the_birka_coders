import L from "leaflet";

/**
 * Nombres de ciudades, villas, pueblos y parajes sobre el mapa satelital, para guiarse al buscar el campo. Datos de OpenStreetMap (ODbL) guardados en el backend.
 * Cada tipo aparece desde cierto zoom y solo se dibujan los que están a la vista.
 */
export type Lugar = { n: string; t: "city" | "town" | "village" | "hamlet" | "locality"; lat: number; lon: number };
// Con el departamento entero a la vista (zoom ~8,5 a
// 9,5) ya salen las ciudades y los pueblos (town); las villas un poco más cerca. Si se enciman, gana el más grande.
const DESDE_ZOOM: Record<Lugar["t"], number> = { city: 7.4, town: 8.3, village: 9.6, hamlet: 11.5, locality: 12 };
// EE. UU.: el tipo sale de la población (scripts/actualizar_lugares_us.py). Con un estado entero a la
// vista (zoom 6 a 7) salen las ciudades de más de 100.000; con un condado (9 a 10), los pueblos de la zona.
const DESDE_ZOOM_US: Record<Lugar["t"], number> = { city: 5, town: 7.4, village: 8.8, hamlet: 10.2, locality: 12 };
const MAX_A_LA_VISTA = 160;

export type PaisLugares = "UY" | "US";
const datosLugares: Partial<Record<PaisLugares, Promise<Lugar[]>>> = {};
export function bajarLugares(pais: PaisLugares = "UY"): Promise<Lugar[]> {
  datosLugares[pais] ||= fetch(pais === "US" ? "/api/lugares-us" : "/api/lugares")
    .then((r) => r.json())
    .then((d) => d.lugares || [])
    .catch(() => { delete datosLugares[pais]; return []; });
  return datosLugares[pais]!;
}

export function capaLugares(mapa: L.Map) {
  const grupo = L.layerGroup();
  let lugares: Lugar[] = [];
  let activa = false;
  let pais: PaisLugares = "UY";
  // La lista de lugares llega después; si para entonces el mapa ya se desarmó (se salió de la página o
  // React lo volvió a montar), getBounds tiraba «Cannot read properties of undefined (reading '_leaflet_pos')»
  let desarmado = false;
  mapa.once("unload", () => { desarmado = true; });
  const dibujar = () => {
    if (desarmado) return;
    grupo.clearLayers();
    if (!activa || !lugares.length) return;
    const z = mapa.getZoom();
    const desde = pais === "US" ? DESDE_ZOOM_US : DESDE_ZOOM;
    const vista = mapa.getBounds().pad(0.1);
    // lugares ocupados en pantalla: los nombres de departamento visibles y los que ya se pusieron
    const caja0 = mapa.getContainer().getBoundingClientRect();
    const ocupado: Array<[number, number, number, number]> = [...mapa.getContainer().querySelectorAll(".etiqueta-depto")]
      .map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0)
      .map((r) => [r.left - caja0.left - 4, r.top - caja0.top - 4, r.right - caja0.left + 4, r.bottom - caja0.top + 4]);
    const choca = (c: [number, number, number, number]) => ocupado.some((o) => c[0] < o[2] && c[2] > o[0] && c[1] < o[3] && c[3] > o[1]);
    let n = 0;
    for (const l of lugares) { // vienen ordenados de ciudad a paraje: los importantes primero
      if (z < desde[l.t]) { if (pais === "US") break; continue; } // en EE. UU. vienen de más a menos habitantes: el resto tampoco entra
      if (!vista.contains([l.lat, l.lon])) continue;
      const p = mapa.latLngToContainerPoint([l.lat, l.lon]);
      const ancho = l.n.length * (l.t === "city" ? 9.2 : l.t === "town" ? 8.2 : 7.2) + 16, alto = l.t === "city" ? 22 : 18;
      const c: [number, number, number, number] = [p.x - ancho / 2, p.y - alto / 2, p.x + ancho / 2, p.y + alto / 2];
      if (choca(c)) continue; // si se encima con otro nombre, gana el más importante (el que ya está)
      ocupado.push(c);
      L.marker([l.lat, l.lon], {
        interactive: false, keyboard: false,
        icon: L.divIcon({ className: `lugar lugar-${l.t}`, html: `<span data-no-traducir>${l.n.replace(/[<>&]/g, "")}</span>`, iconSize: undefined as any }),
      }).addTo(grupo);
      if (++n >= MAX_A_LA_VISTA) break;
    }
  };
  bajarLugares(pais).then((d) => { if (pais === "UY") { lugares = d; dibujar(); } });
  // un instante después del movimiento: los nombres de estados y condados se acomodan en ese mismo aviso
  // (etiquetasZona.ts) y estos no tienen que pisarlos
  const alMover = () => setTimeout(dibujar, 0);
  mapa.on("zoomend moveend", alMover);
  return {
    /** De qué país son los nombres: los de Uruguay salen de OpenStreetMap, los de EE. UU. de GeoNames. */
    pais(p: PaisLugares) {
      if (p === pais) return;
      pais = p;
      lugares = [];
      dibujar();
      bajarLugares(p).then((d) => { if (pais === p) { lugares = d; dibujar(); } });
    },
    redibujar: dibujar,
    mostrar(si: boolean) {
      activa = si;
      if (si) grupo.addTo(mapa); else grupo.remove();
      dibujar();
    },
  };
}
