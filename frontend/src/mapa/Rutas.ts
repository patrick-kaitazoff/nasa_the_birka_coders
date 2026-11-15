import L from "leaflet";

/**
 * Rutas nacionales con su número sobre la foto satelital. Datos de OpenStreetMap (ODbL) guardados en el backend
 * (scripts/actualizar_rutas.py). Aparecen al mirar un departamento (zoom 7,8 o más) y se van de muy cerca,
 * donde la línea simplificada ya no calza justo con la foto. En el mapa de calles no van: ya las trae.
 */
const DESDE_ZOOM = 7.8;
const HASTA_ZOOM = 14.5;
const MAX_NUMEROS = 60;

export type Numero = { ruta: string; clase: "principal" | "secundaria"; lat: number; lon: number };

// una sola descarga para el mapa y la lupa
let datos: Promise<{ lineas: any; numeros: Numero[] }> | null = null;
export function bajarRutas() {
  datos ||= fetch("/api/rutas").then((r) => r.json()).catch((e) => { datos = null; throw e; });
  return datos;
}

/** `hastaZoom`: la lupa las muestra siempre, porque mira de cerca a propósito;
 * `conNumeros`: en la lupa no, se recalcularían en cada movimiento del mouse. */
export function capaRutas(mapa: L.Map, { hastaZoom = HASTA_ZOOM, conNumeros = true }: { hastaZoom?: number; conNumeros?: boolean } = {}) {
  const renderer = L.svg({ padding: 1 }); // dibujadas más allá de lo que se ve: no se cortan al arrastrar
  const borde = L.geoJSON(undefined, {
    renderer, interactive: false,
    style: (f) => ({ color: "#14261c", weight: f?.properties.clase === "principal" ? 5 : 3.6, opacity: 0.45, lineCap: "round", lineJoin: "round" }),
  } as L.GeoJSONOptions);
  const linea = L.geoJSON(undefined, {
    renderer, interactive: false,
    style: (f) => ({ color: "#ffe17a", weight: f?.properties.clase === "principal" ? 2.4 : 1.4, opacity: 0.95, lineCap: "round", lineJoin: "round" }),
  } as L.GeoJSONOptions);
  const carteles = L.layerGroup();
  let numeros: Numero[] = [];
  let pedida = false;
  let activa = false;

  const cargar = () => {
    if (pedida) return;
    pedida = true;
    bajarRutas().then((d) => {
      borde.addData(d.lineas);
      linea.addData(d.lineas);
      // las principales primero: si dos números se pisan, queda el de la ruta principal
      numeros = (d.numeros || []).sort((a: Numero, b: Numero) => (a.clase === b.clase ? 0 : a.clase === "principal" ? -1 : 1));
      actualizar();
    }).catch(() => { pedida = false; /* sin rutas: el mapa anda igual */ });
  };

  const ponerNumeros = () => {
    carteles.clearLayers();
    const vista = mapa.getBounds().pad(0.05);
    const caja0 = mapa.getContainer().getBoundingClientRect();
    // no encima de los nombres de departamento ni de los pueblos que ya están
    const ocupado: Array<[number, number, number, number]> = [...mapa.getContainer().querySelectorAll(".etiqueta-depto, .lugar span")]
      .map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0)
      .map((r) => [r.left - caja0.left - 3, r.top - caja0.top - 3, r.right - caja0.left + 3, r.bottom - caja0.top + 3]);
    const choca = (c: [number, number, number, number]) => ocupado.some((o) => c[0] < o[2] && c[2] > o[0] && c[1] < o[3] && c[3] > o[1]);
    const ultimoDeRuta: Record<string, L.Point[]> = {};
    let n = 0;
    for (const x of numeros) {
      if (!vista.contains([x.lat, x.lon])) continue;
      const p = mapa.latLngToContainerPoint([x.lat, x.lon]);
      // el mismo número, no más seguido que cada ~170 px
      if ((ultimoDeRuta[x.ruta] || []).some((q) => q.distanceTo(p) < 170)) continue;
      const ancho = x.ruta.length * 7 + 12, alto = 17;
      const c: [number, number, number, number] = [p.x - ancho / 2, p.y - alto / 2, p.x + ancho / 2, p.y + alto / 2];
      if (choca(c)) continue;
      ocupado.push([c[0] - 6, c[1] - 6, c[2] + 6, c[3] + 6]);
      (ultimoDeRuta[x.ruta] ||= []).push(p);
      L.marker([x.lat, x.lon], {
        interactive: false, keyboard: false,
        icon: L.divIcon({ className: `ruta-num ruta-${x.clase}`, html: `<span title="Ruta ${x.ruta}">${x.ruta}</span>`, iconSize: undefined as any }),
      }).addTo(carteles);
      if (++n >= MAX_NUMEROS) break;
    }
  };

  const actualizar = () => {
    const z = mapa.getZoom();
    const ver = activa && z >= DESDE_ZOOM && z <= hastaZoom;
    if (ver) {
      cargar();
      if (!mapa.hasLayer(linea)) { borde.addTo(mapa); linea.addTo(mapa); if (conNumeros) carteles.addTo(mapa); }
      if (conNumeros) ponerNumeros();
    } else if (mapa.hasLayer(linea)) {
      borde.remove(); linea.remove(); carteles.remove();
    }
  };
  // después de los nombres de pueblos (que se ponen en el mismo evento), para no taparlos
  const alMover = () => setTimeout(actualizar, 0);
  mapa.on("zoomend moveend", alMover);
  return {
    mostrar(si: boolean) { activa = si; actualizar(); },
  };
}
