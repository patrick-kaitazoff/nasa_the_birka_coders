import {
  area,
  bbox as turfBbox,
  bboxPolygon,
  booleanPointInPolygon,
  buffer as turfBuffer,
  centroid,
  destination,
  difference as turfDifference,
  feature,
  featureCollection,
  intersect,
  nearestPointOnLine,
  point,
  pointOnFeature,
  polygonToLine,
  transformRotate,
  truncate,
  union,
} from "@turf/turf";
import type { Feature, FeatureCollection, Polygon, MultiPolygon, Geometry } from "geojson";
import L from "leaflet";
import type { Geo } from "../tipos";

/** Crea un polígono circular (64 lados) a partir de centro [lat, lon] y radio en metros. Para pivots de riego. */
export function circuloGeo(lat: number, lon: number, radioM: number): Polygon {
  const centro = point([lon, lat]);
  const buf = turfBuffer(centro, radioM / 1000, { units: "kilometers", steps: 64 });
  return buf!.geometry as Polygon;
}

export function areaHa(g: Geo): number {
  try {
    return area(feature(g)) / 10000;
  } catch {
    return 0;
  }
}

/** [lat, lon] de un punto que cae dentro del polígono. */
export function puntoInterior(g: Geo): [number, number] {
  const p = pointOnFeature(feature(g));
  const [lon, lat] = p.geometry.coordinates;
  return [lat, lon];
}

/** Rectángulo de ancho × largo metros centrado en (lat, lon), girado `angulo` grados desde el norte. */
export function rectangulo(lat: number, lon: number, anchoM: number, largoM: number, angulo = 0): Polygon {
  const c = point([lon, lat]);
  const medioDiag = Math.hypot(anchoM, largoM) / 2 / 1000;
  const base = (Math.atan2(anchoM, largoM) * 180) / Math.PI;
  const esquinas = [angulo + base, angulo + 180 - base, angulo + 180 + base, angulo + 360 - base].map(
    (b) => destination(c, medioDiag, b, { units: "kilometers" }).geometry.coordinates,
  );
  return { type: "Polygon", coordinates: [[...esquinas, esquinas[0]]] };
}

export function recortar(a: Geo, contorno: Geo): Geo | null {
  try {
    const r = intersect(featureCollection([feature(a), feature(contorno)]) as FeatureCollection<Polygon | MultiPolygon>);
    return r ? (r.geometry as Geo) : null;
  } catch {
    return null;
  }
}

/**
 * Elimina partes insignificantes (slivers o restos numéricos de cortes) menores a `minHa`.
 * Si el polígono completo queda por debajo de `minHa`, devuelve null.
 */
export function limpiarSlivers(g: Geo, minHa = 0.01): Geo | null {
  if (g.type === "Polygon") {
    return areaHa(g) >= minHa ? g : null;
  }
  if (g.type === "MultiPolygon") {
    const partes = g.coordinates
      .map((coords) => ({ type: "Polygon" as const, coordinates: coords }))
      .filter((poly) => areaHa(poly) >= minHa);
    if (!partes.length) return null;
    if (partes.length === 1) return partes[0];
    return {
      type: "MultiPolygon",
      coordinates: partes.map((p) => p.coordinates),
    };
  }
  return null;
}

/**
 * Calcula la superficie libre del campo (contorno menos todas las secciones ya creadas).
 * Si no hay secciones, devuelve el contorno. Si el campo ya está todo cubierto, devuelve null.
 */
export function calcularZonaLibre(
  contorno: Geo,
  secciones: Array<{ geometria: Geo }>,
): Geo | null {
  if (!secciones || !secciones.length) return contorno;
  let libre: Geo = contorno;
  for (const s of secciones) {
    if (!s?.geometria) continue;
    try {
      const diff = turfDifference(
        featureCollection([feature(libre), feature(s.geometria)]) as FeatureCollection<Polygon | MultiPolygon>,
      );
      if (!diff) return null;
      libre = diff.geometry as Geo;
    } catch {
      // si falla una diferencia geométrica puntual, seguimos con lo que tenemos
    }
  }
  return limpiarSlivers(libre, 0.05);
}

/**
 * Convierte el polígono o multipolígono de la zona libre a líneas perimetrales
 * para calcular proyecciones y distancias de imantación.
 */
export function lineasZonaLibre(zonaLibre: Geo): any {
  return polygonToLine(feature(zonaLibre) as any);
}

/**
 * Limita una coordenada [lat, lon] al interior de la zona libre.
 * Si cae adentro, la devuelve intacta. Si cae afuera, la proyecta al borde más cercano de la zona libre.
 */
export function limitarALibre(
  latlng: L.LatLng,
  zonaLibre: Geo,
  lineasLibre: any,
): L.LatLng {
  try {
    const pt = point([latlng.lng, latlng.lat]);
    if (booleanPointInPolygon(pt, zonaLibre as any)) {
      return latlng;
    }
    const snapped = nearestPointOnLine(lineasLibre, pt);
    const [lon, lat] = snapped.geometry.coordinates;
    return L.latLng(lat, lon);
  } catch {
    return latlng;
  }
}

/**
 * Recorta una geometría (polígono o círculo) a la zona libre del campo:
 * primero la intersecta con el contorno exterior, y luego resta cualquier solapamiento
 * con las secciones ya existentes.
 */
export function recortarAZonaLibre(
  geometria: Geo,
  contorno: Geo,
  secciones: Array<{ geometria: Geo }>,
): Geo | null {
  try {
    let r = recortar(geometria, contorno);
    if (!r) return null;
    for (const s of secciones) {
      if (!s?.geometria) continue;
      const diff = turfDifference(
        featureCollection([feature(r), feature(s.geometria)]) as FeatureCollection<Polygon | MultiPolygon>,
      );
      if (!diff) return null;
      r = diff.geometry as Geo;
    }
    const limpio = limpiarSlivers(r, 0.05);
    return limpio && areaHa(limpio) > 0.05 ? limpio : null;
  } catch {
    return null;
  }
}

/** Ángulo (grados) que deja el lado largo del campo en sentido norte-sur: el del rectángulo más chico que lo encierra. */
export function anguloLargo(contorno: Geo): number {
  const f = feature(contorno);
  const centro = centroid(f);
  let mejor = 0, menor = Infinity;
  for (let a = 0; a < 180; a += 3) {
    const [x0, y0, x1, y1] = turfBbox(transformRotate(f, -a, { pivot: centro }));
    const areaCuadro = (x1 - x0) * (y1 - y0);
    if (areaCuadro < menor) { menor = areaCuadro; mejor = (y1 - y0) >= (x1 - x0) ? a : a + 90; }
  }
  return mejor;
}

/**
 * Parte el contorno en `n` partes de la misma superficie con cortes paralelos.
 * "largo": franjas que siguen el lado largo del campo; "ancho": cortes a través del lado largo.
 */
export function partesIguales(contorno: Geo, n: number, sentido: "largo" | "ancho" = "largo"): Geo[] {
  const angulo = anguloLargo(contorno) + (sentido === "ancho" ? 90 : 0);
  const f = feature(contorno);
  const centro = centroid(f);
  const girado = transformRotate(f, -angulo, { pivot: centro });
  const [minX, minY, maxX, maxY] = turfBbox(girado);
  const caja = (a: number, b: number) =>
    transformRotate(bboxPolygon([a, minY - 0.01, b, maxY + 0.01]), angulo, { pivot: centro }).geometry as Geo;
  const areaHasta = (x: number) => { const r = recortar(caja(minX - 0.01, x), contorno); return r ? areaHa(r) : 0; };
  const total = areaHa(contorno);
  const cortes = [minX - 0.01];
  for (let i = 1; i < n; i++) {
    let lo = cortes[cortes.length - 1], hi = maxX;
    for (let k = 0; k < 22; k++) { const m = (lo + hi) / 2; if (areaHasta(m) < (total * i) / n) lo = m; else hi = m; }
    cortes.push((lo + hi) / 2);
  }
  cortes.push(maxX + 0.01);
  const out: Geo[] = [];
  for (let i = 0; i < n; i++) {
    const r = recortar(caja(cortes[i], cortes[i + 1]), contorno);
    if (r && areaHa(r) > 0.05) out.push(r);
  }
  return out;
}

function poligonos(geoms: Geometry[]): Geo[] {
  const out: Geo[] = [];
  for (const g of geoms) {
    if (!g) continue;
    if (g.type === "Polygon" || g.type === "MultiPolygon") out.push(g);
    else if (g.type === "GeometryCollection") out.push(...poligonos(g.geometries));
    else if (g.type === "LineString" && g.coordinates.length >= 4) {
      const c = [...g.coordinates];
      const [a, b] = [c[0], c[c.length - 1]];
      if (a[0] !== b[0] || a[1] !== b[1]) c.push(a);
      out.push({ type: "Polygon", coordinates: [c] });
    }
  }
  // sin la tercera coordenada (altura) que traen los KML
  return out.map((g) => truncate(feature(g), { precision: 7, coordinates: 2 }).geometry as Geo);
}

export interface Importado {
  poligonos: Array<{ geometria: Geo; nombre?: string }>;
  formato: string;
}

export async function importarArchivo(file: File): Promise<Importado> {
  const nombre = file.name.toLowerCase();
  const ext = nombre.split(".").pop() || "";
  const conNombre = (fc: FeatureCollection): Importado["poligonos"] =>
    fc.features.flatMap((f: Feature) => poligonos([f.geometry as Geometry]).map((g) => ({ geometria: g, nombre: (f.properties as any)?.name || (f.properties as any)?.Name })));

  if (ext === "geojson" || ext === "json") {
    const js = JSON.parse(await file.text());
    const fc: FeatureCollection = js.type === "FeatureCollection" ? js : js.type === "Feature" ? { type: "FeatureCollection", features: [js] } : { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: js }] };
    return { poligonos: conNombre(fc), formato: "GeoJSON" };
  }
  if (ext === "kml" || ext === "gpx") {
    const tg = await import("@tmcw/togeojson");
    const xml = new DOMParser().parseFromString(await file.text(), "text/xml");
    const fc = (ext === "kml" ? tg.kml(xml) : tg.gpx(xml)) as FeatureCollection;
    return { poligonos: conNombre(fc), formato: ext.toUpperCase() };
  }
  if (ext === "kmz") {
    const [{ default: JSZip }, tg] = await Promise.all([import("jszip"), import("@tmcw/togeojson")]);
    const zip = await JSZip.loadAsync(await file.arrayBuffer());
    const kmlFile = Object.values(zip.files).find((f) => f.name.toLowerCase().endsWith(".kml"));
    if (!kmlFile) throw new Error("El KMZ no tiene un KML adentro.");
    const xml = new DOMParser().parseFromString(await kmlFile.async("text"), "text/xml");
    return { poligonos: conNombre(tg.kml(xml) as FeatureCollection), formato: "KMZ" };
  }
  if (ext === "zip") {
    const { default: shp } = await import("shpjs");
    const r: any = await shp(await file.arrayBuffer());
    const colecciones: FeatureCollection[] = Array.isArray(r) ? r : [r];
    return { poligonos: colecciones.flatMap(conNombre), formato: "Shapefile" };
  }
  throw new Error(`No sé leer archivos .${ext}. Probá con KML, KMZ, GeoJSON, GPX o un shapefile en .zip.`);
}

/** Lista de vértices "lat, lon" (uno por línea) → polígono. */
export function poligonoDesdeTexto(t: string): Polygon | null {
  const pts = t
    .split(/\n|;/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => l.replace(/,(?=\d)/g, ".").split(/[\s,]+/).map(Number))
    .filter((p) => p.length >= 2 && p.every((x) => !Number.isNaN(x)))
    .map(([a, b]) => (Math.abs(a) <= 90 && Math.abs(b) > 40 ? [b, a] : [a, b]));
  if (pts.length < 3) return null;
  const c = [...pts, pts[0]];
  return { type: "Polygon", coordinates: [c] };
}

export function unir(geoms: Geo[]): Geo | null {
  if (!geoms.length) return null;
  if (geoms.length === 1) return geoms[0];
  try {
    const u = union(featureCollection(geoms.map((g) => feature(g))) as FeatureCollection<Polygon | MultiPolygon>);
    return u ? (u.geometry as Geo) : geoms[0];
  } catch {
    return geoms[0];
  }
}

export function bbox(g: Geo): [number, number, number, number] {
  return turfBbox(feature(g)) as [number, number, number, number];
}
