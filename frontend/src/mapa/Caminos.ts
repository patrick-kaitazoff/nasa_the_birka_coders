import L from "leaflet";
import { api } from "../api";

/**
 * Caminos departamentales (tertiary), vecinales (unclassified) y huellas rurales (track)
 * sobre la foto satelital, para ubicarse con precisión al buscar o marcar el campo.
 *
 * Datos de OpenStreetMap (ODbL) guardados por departamento en el backend (/api/caminos/{depto}).
 * Aparecen escalonados según el zoom:
 * - Zoom < 10.5: solo rutas nacionales (Rutas.ts).
 * - Zoom 10.5+: caminos departamentales (tertiary, línea ámbar fina con halo oscuro).
 * - Zoom 11.5+: caminos vecinales (unclassified, línea blanca fina con halo oscuro).
 * - Zoom 13.0+: huellas y callejones (track, línea discontinua verde suave).
 */
export type CaminosDepto = {
  departamento: string;
  slug: string;
  fuente: string;
  tertiary: { type: "MultiLineString"; coordinates: number[][][] };
  unclassified: { type: "MultiLineString"; coordinates: number[][][] };
  track: { type: "MultiLineString"; coordinates: number[][][] };
};

type DeptoBBox = {
  nombre: string;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  anillos: [number, number][][];
};

const cacheCaminos: Record<string, Promise<CaminosDepto | null>> = {};
let indiceDeptos: DeptoBBox[] = [];
let cargandoIndice = false;

function armarIndice(fc: any): DeptoBBox[] {
  if (!fc?.features) return [];
  return fc.features.map((f: any) => {
    const coords = f.geometry?.coordinates || [];
    const anillos: [number, number][][] = coords;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x, y] of anillos[0] || []) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    return {
      nombre: f.properties?.nombre || "",
      minX, minY, maxX, maxY,
      anillos,
    };
  });
}

function puntoEnAnillo(px: number, py: number, anillo: [number, number][]): boolean {
  let dentro = false;
  for (let i = 0, j = anillo.length - 1; i < anillo.length; j = i++) {
    const xi = anillo[i][0], yi = anillo[i][1];
    const xj = anillo[j][0], yj = anillo[j][1];
    const inter = ((yi > py) !== (yj > py)) && (px < ((xj - xi) * (py - yi)) / (yj - yi) + xi);
    if (inter) dentro = !dentro;
  }
  return dentro;
}

function deptoEnPunto(deptos: DeptoBBox[], lat: number, lon: number): string | null {
  for (const d of deptos) {
    if (lon < d.minX || lon > d.maxX || lat < d.minY || lat > d.maxY) continue;
    if (d.anillos[0] && puntoEnAnillo(lon, lat, d.anillos[0])) {
      return d.nombre;
    }
  }
  return null;
}

export function normalizarSlugDepto(depto: string): string {
  return depto
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function bajarCaminos(depto: string): Promise<CaminosDepto | null> {
  const slug = normalizarSlugDepto(depto);
  if (!slug) return Promise.resolve(null);
  cacheCaminos[slug] ||= fetch(`/api/caminos/${slug}`)
    .then((r) => {
      if (!r.ok) return null;
      return r.json() as Promise<CaminosDepto>;
    })
    .catch(() => null);
  return cacheCaminos[slug];
}

const ZOOM_TERTIARY = 10.5;
const ZOOM_UNCLASSIFIED = 11.5;
const ZOOM_TRACK = 13.0;
const HASTA_ZOOM = 16.5;

export function capaCaminos(
  mapa: L.Map,
  { hastaZoom = HASTA_ZOOM, conAutoDepto = true }: { hastaZoom?: number; conAutoDepto?: boolean } = {},
) {
  const renderer = L.svg({ padding: 0.6 });

  // 1. Caminos departamentales (tertiary): ámbar con halo oscuro, más finos que las rutas nacionales
  const bordeTertiary = L.geoJSON(undefined, {
    renderer,
    interactive: false,
    style: { color: "#14261c", weight: 2.8, opacity: 0.45, lineCap: "round", lineJoin: "round" },
  } as any);
  const lineaTertiary = L.geoJSON(undefined, {
    renderer,
    interactive: false,
    style: { color: "#ffb74d", weight: 1.6, opacity: 0.95, lineCap: "round", lineJoin: "round" },
  } as any);

  // 2. Caminos vecinales (unclassified): blanco hueso fino con halo oscuro
  const bordeUnclassified = L.geoJSON(undefined, {
    renderer,
    interactive: false,
    style: { color: "#14261c", weight: 2.2, opacity: 0.4, lineCap: "round", lineJoin: "round" },
  } as any);
  const lineaUnclassified = L.geoJSON(undefined, {
    renderer,
    interactive: false,
    style: { color: "#f5f5f5", weight: 1.2, opacity: 0.9, lineCap: "round", lineJoin: "round" },
  } as any);

  // 3. Huellas y callejones (track): línea punteada verde suave
  const lineaTrack = L.geoJSON(undefined, {
    renderer,
    interactive: false,
    style: { color: "#a5d6a7", weight: 1.0, opacity: 0.85, dashArray: "4 4", lineCap: "round", lineJoin: "round" },
  } as any);

  const grupo = L.layerGroup();
  let deptoActual: string | null = null;
  let activa = false;

  // Cargar índice de departamentos para autodetección al mover el mapa
  if (conAutoDepto && !indiceDeptos.length && !cargandoIndice) {
    cargandoIndice = true;
    api.departamentos()
      .then((fc) => {
        indiceDeptos = armarIndice(fc);
      })
      .catch(() => {});
  }

  const actualizarCapas = (z: number) => {
    grupo.clearLayers();
    if (!activa || z < ZOOM_TERTIARY || z > hastaZoom) return;

    if (z >= ZOOM_TERTIARY) {
      grupo.addLayer(bordeTertiary);
      grupo.addLayer(lineaTertiary);
    }
    if (z >= ZOOM_UNCLASSIFIED) {
      grupo.addLayer(bordeUnclassified);
      grupo.addLayer(lineaUnclassified);
    }
    if (z >= ZOOM_TRACK) {
      grupo.addLayer(lineaTrack);
    }
  };

  const cargar = (depto: string) => {
    const slug = normalizarSlugDepto(depto);
    if (!slug || deptoActual === slug) return;
    deptoActual = slug;
    bajarCaminos(slug).then((d) => {
      if (!d || deptoActual !== slug) return;
      bordeTertiary.clearLayers();
      lineaTertiary.clearLayers();
      bordeUnclassified.clearLayers();
      lineaUnclassified.clearLayers();
      lineaTrack.clearLayers();

      if (d.tertiary?.coordinates?.length) {
        bordeTertiary.addData(d.tertiary as any);
        lineaTertiary.addData(d.tertiary as any);
      }
      if (d.unclassified?.coordinates?.length) {
        bordeUnclassified.addData(d.unclassified as any);
        lineaUnclassified.addData(d.unclassified as any);
      }
      if (d.track?.coordinates?.length) {
        lineaTrack.addData(d.track as any);
      }
      actualizarCapas(mapa.getZoom());
    });
  };

  const alMover = () => {
    const z = mapa.getZoom();
    if (conAutoDepto && z >= ZOOM_TERTIARY && indiceDeptos.length) {
      const c = mapa.getCenter();
      const nom = deptoEnPunto(indiceDeptos, c.lat, c.lng);
      if (nom) cargar(nom);
    }
    actualizarCapas(z);
  };

  mapa.on("zoomend moveend", alMover);

  return {
    mostrar(si: boolean) {
      activa = si;
      if (si) grupo.addTo(mapa);
      else grupo.remove();
      actualizarCapas(mapa.getZoom());
    },
    cargarDepartamento(depto: string) {
      cargar(depto);
    },
    limpiar() {
      deptoActual = null;
      grupo.clearLayers();
    },
    destruir() {
      mapa.off("zoomend moveend", alMover);
      grupo.remove();
    },
  };
}
