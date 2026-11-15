import type { Geo, Seccion } from "../tipos";
import { bbox, puntoInterior } from "../mapa/geo";
import { IconoCultivo } from "../comun/Cultivo";

export interface Proyeccion {
  x: (lon: number) => number;
  y: (lat: number) => number;
  metrosPorUnidad: number;
}

export function proyectar(g: Geo, W: number, H: number, margen = 10): Proyeccion {
  const [x0, y0, x1, y1] = bbox(g);
  const latMed = (y0 + y1) / 2;
  const k = Math.cos((latMed * Math.PI) / 180);
  const anchoGeo = (x1 - x0) * k, altoGeo = y1 - y0;
  const esc = Math.min((W - 2 * margen) / anchoGeo, (H - 2 * margen) / altoGeo);
  const offX = (W - anchoGeo * esc) / 2, offY = (H - altoGeo * esc) / 2;
  return {
    x: (lon) => offX + (lon - x0) * k * esc,
    y: (lat) => offY + (y1 - lat) * esc,
    metrosPorUnidad: 111320 / esc,
  };
}

export function caminoSVG(g: Geo, p: Proyeccion): string {
  const anillos = g.type === "Polygon" ? g.coordinates : g.coordinates.flat();
  return anillos.map((r) => r.map(([lon, lat], i) => `${i ? "L" : "M"}${p.x(lon).toFixed(1)},${p.y(lat).toFixed(1)}`).join("") + "Z").join(" ");
}

interface Props {
  contorno: Geo;
  secciones: Seccion[];
  cultivoDe: (seccionId: string) => string | undefined;
  info: (cod: string) => { color: string; icono: string; nombre: string };
  W?: number;
  H?: number;
  etiquetas?: boolean;
  seleccion?: string | null;
  onSeccion?: (id: string) => void;
  /** el norte abajo a la derecha (arriba lo tapa la píldora «Plano / Relieve 3D» del Plan) */
  norteAbajo?: boolean;
}

const ALTO_ROTULO = 38;

let lienzoMedir: CanvasRenderingContext2D | null | undefined;
/** Ancho real de un texto con la letra de los rótulos (la cuenta aproximada quedaba corta y se pisaban). */
function anchoTexto(texto: string, fuente: string, aprox: number): number {
  if (lienzoMedir === undefined) lienzoMedir = typeof document !== "undefined" ? document.createElement("canvas").getContext("2d") : null;
  if (!lienzoMedir) return texto.length * aprox;
  lienzoMedir.font = fuente;
  return lienzoMedir.measureText(texto).width;
}

type Caja = { x: number; y: number; w: number; h: number };

/** Dónde va el rótulo de cada lote: centrado en el lote y, si se pisa con otro (pasa en el recuadro angosto del
 * Plan), en el lugar libre más cercano; siempre dentro del dibujo. */
function rotulos(secciones: Seccion[], cultivoDe: (id: string) => string | undefined, info: Props["info"], p: Proyeccion, W: number, H: number, libre?: Caja) {
  const items = secciones.flatMap((s) => {
    const cod = cultivoDe(s.id);
    if (!cod) return [];
    const [lat, lon] = puntoInterior(s.geometria);
    const i = info(cod);
    const nombre = i.nombre.split(" (")[0].replace("Cultivo de cobertura", "Cobertura");
    const letra = getComputedStyle?.(document.body)?.fontFamily || "Inter, sans-serif";
    const ancho = Math.ceil(Math.max(anchoTexto(nombre, `700 12px ${letra}`, 7.4), anchoTexto(s.nombre, `10.5px ${letra}`, 6.2))) + 31 + 10;
    const x = Math.max(4, Math.min(W - ancho - 4, p.x(lon) - ancho / 2));
    return [{ s, i, nombre, ancho, x, y: p.y(lat) - ALTO_ROTULO / 2 }];
  }).sort((a, b) => a.y - b.y);
  // Para cada rótulo se prueban lugares cerca del lote (arriba, abajo y un poco al costado, del más cercano
  // al más lejano) y queda el primero libre; si no hay ninguno, el que menos se pisa
  const puestos: typeof items = [];
  // la flecha del norte también cuenta como ocupada: antes un rótulo podía quedar debajo
  const enLibre = (x: number, y: number, w: number) => {
    if (!libre) return 0;
    const dx = Math.min(x + w, libre.x + libre.w) - Math.max(x, libre.x);
    const dy = Math.min(y + ALTO_ROTULO, libre.y + libre.h) - Math.max(y, libre.y);
    return dx > 0 && dy > 0 ? dx * dy * 4 : 0;
  };
  const pisa = (x: number, y: number, w: number) => puestos.reduce((acc, b) => {
    const dx = Math.min(x + w + 6, b.x + b.ancho + 6) - Math.max(x, b.x);
    const dy = Math.min(y + ALTO_ROTULO + 5, b.y + ALTO_ROTULO + 5) - Math.max(y, b.y);
    return acc + (dx > 0 && dy > 0 ? dx * dy : 0);
  }, enLibre(x, y, w));
  const paso = ALTO_ROTULO + 6;
  for (const it of items) {
    const candidatos: Array<[number, number]> = [];
    for (const dy of [0, paso, -paso, 2 * paso, -2 * paso, 3 * paso, -3 * paso])
      for (const dx of [0, -it.ancho * 0.55, it.ancho * 0.55]) candidatos.push([dx, dy]);
    candidatos.sort((a, b) => Math.hypot(a[0], a[1] * 1.3) - Math.hypot(b[0], b[1] * 1.3));
    let mejor = { x: it.x, y: Math.max(4, Math.min(H - ALTO_ROTULO - 4, it.y)), costo: Infinity };
    for (const [dx, dy] of candidatos) {
      const x = Math.max(4, Math.min(W - it.ancho - 4, it.x + dx));
      const y = Math.max(4, Math.min(H - ALTO_ROTULO - 4, it.y + dy));
      const costo = pisa(x, y, it.ancho);
      if (costo < mejor.costo) mejor = { x, y, costo };
      if (costo === 0) break;
    }
    puestos.push({ ...it, x: mejor.x, y: mejor.y });
  }
  return puestos;
}

/** Plano del campo en SVG con cada sección pintada con la trama de su cultivo. */
export function PlanoSVG({ contorno, secciones, cultivoDe, info, W = 600, H = 420, etiquetas = true, seleccion, onSeccion, norteAbajo = false }: Props) {
  // Sin la escala
  // gráfica, que además se pisaba con el rótulo del lote de abajo a la izquierda, y con 10 px de margen en vez de 24
  // el campo llena más su recuadro. La escala sigue en el plano que se descarga
  const p = proyectar(contorno, W, H, etiquetas ? 10 : 6);
  // dónde va la flecha del norte, y el lugar que ocupa (con un margen) para que los rótulos no la tapen
  const norte = norteAbajo ? { x: W - 26, y: H - 34 } : { x: W - 34, y: 40 };
  const lugarNorte: Caja = { x: norte.x - 14, y: norte.y - 28, w: 28, h: 54 };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Plano del campo con los cultivos por sección" style={{ display: "block" }}>
      {secciones.map((s) => {
        const cod = cultivoDe(s.id);
        return (
          <path key={s.id} d={caminoSVG(s.geometria, p)} fill={cod ? `url(#trama-${cod})` : "#eee"} stroke={seleccion === s.id ? "#12352a" : "#fff"}
            strokeWidth={seleccion === s.id ? 3 : etiquetas ? 2 : 1} fillRule="evenodd" style={{ cursor: onSeccion ? "pointer" : undefined }}
            onClick={() => onSeccion?.(s.id)}>
            <title>{`${s.nombre}: ${cod ? info(cod).nombre : "sin dato"}`}</title>
          </path>
        );
      })}
      <path d={caminoSVG(contorno, p)} fill="none" stroke="#12352a" strokeWidth={etiquetas ? 2 : 1.2} />
      {etiquetas && rotulos(secciones, cultivoDe, info, p, W, H, lugarNorte).map(({ s, i, nombre, ancho, x, y }) => {
        return (
          <g key={s.id} transform={`translate(${x},${y})`} pointerEvents="none">
            <rect width={ancho} height="38" rx="8" fill="#fffdf8" opacity="0.95" stroke="rgba(0,0,0,.15)" />
            <g transform="translate(6,9)"><IconoCultivo icono={i.icono} color={i.color} size={20} /></g>
            <text x="31" y="16" fontSize="12" fontWeight="700" fill="#1f2a24">{nombre}</text>
            <text x="31" y="30" fontSize="10.5" fill="#56615a">{s.nombre}</text>
          </g>
        );
      })}
      {etiquetas && (
        <g transform={`translate(${norte.x},${norte.y})`} pointerEvents="none">
          {/* con un borde claro, para que se lea sobre las tramas de los cultivos */}
          <path d="M0 -22 L8 6 L0 0 L-8 6 Z" fill="#12352a" stroke="#fffdf8" strokeWidth="2.5" strokeLinejoin="round" paintOrder="stroke" />
          <text y="20" fontSize="12" textAnchor="middle" fontWeight="700" fill="#12352a" stroke="#fffdf8" strokeWidth="3" strokeLinejoin="round" paintOrder="stroke">N</text>
        </g>
      )}
    </svg>
  );
}
