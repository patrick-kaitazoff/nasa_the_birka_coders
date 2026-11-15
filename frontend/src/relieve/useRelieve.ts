/** Pide el relieve de SRTM (pendiente y erosión por cuadrado) para el campo analizado. Lo usan la pestaña
 * Datos y el visor 3D; se guarda en memoria para no pedirlo dos veces. Los números (R, K, C, P de cada
 * sección) salen del análisis y del plan: el backend solo cambia la pendiente cuadrado por cuadrado.
 *
 * El pedido ya no depende de lo que elige el productor. Antes llevaba el factor C de la rotación
 * elegida y cada elección en el Plan volvía a bajar el relieve entero (~480 KB y el cálculo de SRTM). Ahora el
 * servidor manda la parte de la erosión que no depende de la rotación (R · K · LS · P, «base») y acá se multiplica
 * por el C de lo elegido. */
import { useEffect, useMemo, useState } from "react";
import { useApp } from "../store";
import type { Analisis, Campo, Evaluacion, Plan } from "../tipos";
import { enPalabras } from "../errores";

type ErosionSeccion = { media: number; pct_supera_t: number; ha_supera_t: number };

export interface Relieve {
  fuente: string;
  bordes: { oeste: number; este: number; norte: number; sur: number };
  px_m: number;
  px_m_original: number;
  elev_min: number;
  elev_max: number;
  secciones: Array<{
    id: string; nombre: string; ha: number; pendiente_media: number; pendiente_p90: number; pct_mas_de_4: number;
    elev_min: number; elev_max: number;
    ha_via_agua?: number; ha_bajos?: number;
    erosion_actual?: ErosionSeccion;
    erosion_plan?: ErosionSeccion;
    /** posición de la sección en el pedido (el número que usa grilla.seccion), su tolerancia y la base de la erosión */
    indice?: number; t?: number; base_media?: number; base_cuantiles?: number[];
  }>;
  grilla: {
    filas: number; cols: number;
    elev: number[][]; pendiente: number[][]; dentro: number[][]; seccion: number[][];
    agua?: number[][]; drenaje_ha?: Array<Array<number | null>>;
    erosion_actual: Array<Array<number | null>>; erosion_plan: Array<Array<number | null>>; tolerancia: Array<Array<number | null>>;
    erosion_base?: Array<Array<number | null>>;
  };
  metodo: string;
  limites: string[];
  /** la foto satelital ya guardada en el proyecto (solo los ejemplos): se usa en vez de pedírsela a Esri */
  foto?: string;
}

/** Lo que se le pide al servidor: no depende de la rotación elegida, así elegir no vuelve a pedir el relieve. */
export function pedidoRelieve(campo: Campo, analisis: Analisis) {
  if (!campo.contorno || !analisis.secciones.length) return null;
  let p = 1;
  const secciones = campo.secciones.map((sc) => {
    const s = analisis.secciones.find((x) => x.id === sc.id);
    if (!s) return null;
    if (s.actual?.erosion.p) p = s.actual.erosion.p;
    return {
      id: s.id, nombre: s.nombre, geometria: sc.geometria,
      k: s.suelo?.factor_k, t: s.suelo?.tolerancia_t,
      c_actual: s.actual?.erosion.c ?? null,
    };
  }).filter(Boolean) as Array<{ id: string; nombre: string; geometria: unknown; k?: number; t?: number; c_actual: number | null }>;
  return { contorno: campo.contorno, secciones, r: analisis.factor_r.usado, p, largo_m: campo.largo_pendiente_m || null };
}

/** El factor C de la rotación elegida en cada sección (la de hoy si no eligió nada). */
function cElegido(analisis: Analisis, plan: Plan | null, id: string): number | null {
  const s = analisis.secciones.find((x) => x.id === id);
  if (!s) return null;
  const evs = [s.actual, ...s.alternativas].filter(Boolean) as Evaluacion[];
  const rid = plan?.secciones.find((x) => x.seccion_id === id)?.rotacion_id || (s.actual ? "actual" : s.recomendada_id);
  return evs.find((e) => e.id === rid)?.erosion.c ?? null;
}

/** Parte de los cuadrados de la sección con erosión por encima de la tolerancia, desde los percentiles de la base. */
function pctSupera(cuantiles: number[], c: number, t: number): number {
  if (!cuantiles.length || c <= 0) return 0;
  const limite = t / c;
  let debajo = 0;
  while (debajo < cuantiles.length && cuantiles[debajo] <= limite) debajo++;
  return Math.round((100 * (cuantiles.length - debajo)) / cuantiles.length);
}

/** El relieve con la erosión de lo que eligió el productor, calculada acá con la base que mandó el servidor. */
export function conEleccion(relieve: Relieve, analisis: Analisis, plan: Plan | null, pedido: NonNullable<ReturnType<typeof pedidoRelieve>>): Relieve {
  const base = relieve.grilla.erosion_base;
  if (!base) return relieve; // respuesta de un servidor anterior: trae su propia erosión con el plan
  const cPorIndice = pedido.secciones.map((s) => cElegido(analisis, plan, s.id));
  const secciones = relieve.secciones.map((s) => {
    const c = s.indice != null ? cPorIndice[s.indice] : null;
    if (c == null || s.base_media == null || !s.base_cuantiles || s.t == null) return s;
    const pct = pctSupera(s.base_cuantiles, c, s.t);
    return { ...s, erosion_plan: { media: Math.round(s.base_media * c * 10) / 10, pct_supera_t: pct, ha_supera_t: Math.round((s.ha * pct) / 10) / 10 } };
  });
  const erosion_plan = base.map((fila, i) => fila.map((b, j) => {
    const k = relieve.grilla.seccion[i][j];
    const c = k >= 0 ? cPorIndice[k] : null;
    return b == null || c == null ? null : Math.round(b * c * 10) / 10;
  }));
  return { ...relieve, secciones, grilla: { ...relieve.grilla, erosion_plan } };
}

const cache = new Map<string, Promise<Relieve>>();

/** Las fotos satelitales ya pedidas, por dirección: la misma imagen que se empieza a bajar al abrir un ejemplo es la
 * que después usa el 3D. Antes se pedía dos veces (la segunda salía de la caché del navegador, pero se volvía a
 * decodificar: una foto de 2048 px son 50 a 100 ms). */
const fotos = new Map<string, HTMLImageElement>();
export function pedirFoto(url: string): HTMLImageElement {
  let img = fotos.get(url);
  if (!img) {
    img = new Image();
    img.crossOrigin = "anonymous";
    img.decoding = "async";
    img.src = url;
    fotos.set(url, img);
    img.addEventListener("error", () => fotos.delete(url), { once: true });
  }
  return img;
}

/** Baja ya el código del visor 3D (three.js aparte): al abrir un ejemplo se pide junto con la ficha, en vez de
 * esperar a que React arme el Plan y recién ahí descubra que lo necesita. */
export function adelantarVisor3D() {
  void import("./Vista3D").catch(() => {});
}

/** Deja guardado el relieve ya calculado de un campo de ejemplo (public/ejemplos/relieve_<id>.json, armado con
 * backend/scripts/armar_relieve_ejemplos.py), así el 3D del Plan sale enseguida en vez de esperar 2 a 3 s (o más, si la
 * función de Vercel estaba dormida) a /api/relieve. Si el archivo no es de este ejemplo (se regeneró el
 * ejemplo y no el relieve), no se usa y se le pide al servidor como siempre. */
export function sembrarRelieve(campo: Campo, analisis: Analisis, guardado: { huella?: { secciones?: string[]; r?: number }; relieve?: Relieve } | null, foto?: string) {
  const pedido = pedidoRelieve(campo, analisis);
  if (!pedido || !guardado?.relieve?.grilla || !guardado.huella) return;
  const ids = pedido.secciones.map((s) => s.id);
  const h = guardado.huella;
  if (h.r !== pedido.r || !h.secciones || h.secciones.length !== ids.length || h.secciones.some((id, i) => id !== ids[i])) return;
  // se entrega después de la próxima pintura: así el Plan aparece primero y el 3D (que ocupa la página más de medio
  // segundo al armarse) se dibuja enseguida después, en vez de retener todo detrás de la pantalla de carga
  const relieve: Relieve = foto ? { ...guardado.relieve, foto } : guardado.relieve;
  // la foto se decodifica mientras tanto, fuera del hilo de la página: cuando el 3D la pide ya está lista para subir
  // a la placa y el terreno no se dibuja primero en verde
  const fotoLista = foto ? pedirFoto(foto).decode().catch(() => {}) : Promise.resolve();
  cache.set(JSON.stringify(pedido), new Promise<Relieve>((ok) => {
    // con la página armándose por adelantado no hay pinturas que esperar: el 3D se arma ya, antes del clic
    if (typeof requestAnimationFrame !== "function" || (document as Document & { prerendering?: boolean }).prerendering) return ok(relieve);
    requestAnimationFrame(() => setTimeout(() => {
      // se espera la foto como mucho 0,4 s más: si tarda, el 3D sale igual y la foto entra cuando llegue
      void Promise.race([fotoLista, new Promise((r) => setTimeout(r, 400))]).then(() => ok(relieve));
    }, 0));
  }));
}

const postergar =
  typeof window !== "undefined" && "requestIdleCallback" in window
    ? (fn: () => void) =>
        (window as Window & { requestIdleCallback: (cb: () => void, opt?: { timeout: number }) => number }).requestIdleCallback(fn, { timeout: 2000 })
    : (fn: () => void) => setTimeout(fn, 120);

/** Precarga en segundo plano el código del visor 3D, el relieve de la NASA y la foto satelital sin trabar la pantalla */
export function precargarRelieve(campo: Campo, analisis: Analisis) {
  const pedido = pedidoRelieve(campo, analisis);
  if (!pedido) return;
  const clave = JSON.stringify(pedido);
  if (cache.has(clave)) return;

  postergar(() => {
    // 1. Descarga del chunk de código del visor 3D (mismo import dinámico que React.lazy en App.tsx)
    void import("./Vista3D").catch(() => {});

    // 2. Descarga de datos del relieve (/api/relieve) y textura satelital
    if (!cache.has(clave)) {
      cache.set(
        clave,
        fetch("/api/relieve", { method: "POST", headers: { "Content-Type": "application/json" }, body: clave })
          .then(async (r) => {
            if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
            const res = (await r.json()) as Relieve;
            if (res?.bordes) {
              pedirFoto(urlFotoEsri(res));
            }
            return res;
          })
          .catch((err) => {
            cache.delete(clave);
            throw err;
          })
      );
    }
  });
}

export function useRelieve(): { relieve: Relieve | null; error: string | null; cargando: boolean } {
  const { campo, analisis, plan } = useApp();
  const [estado, setEstado] = useState<{ relieve: Relieve | null; error: string | null; cargando: boolean }>({ relieve: null, error: null, cargando: false });
  const pedido = analisis ? pedidoRelieve(campo, analisis) : null;
  const clave = pedido ? JSON.stringify(pedido) : "";
  useEffect(() => {
    if (!clave) return;
    let vivo = true;
    if (!cache.has(clave)) {
      cache.set(clave, fetch("/api/relieve", { method: "POST", headers: { "Content-Type": "application/json" }, body: clave })
        .then(async (r) => {
          if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `${r.status}`);
          return r.json() as Promise<Relieve>;
        }));
    }
    setEstado((e) => ({ ...e, cargando: true, error: null }));
    cache.get(clave)!
      .then((relieve) => { if (vivo) setEstado({ relieve, error: null, cargando: false }); })
      .catch((e: Error) => { cache.delete(clave); if (vivo) setEstado({ relieve: null, error: enPalabras(e), cargando: false }); });
    return () => { vivo = false; };
  }, [clave]);
  // la erosión de lo elegido se recalcula acá cuando cambia el plan, sin volver a pedir nada
  const relieve = useMemo(
    () => (estado.relieve && analisis && pedido ? conEleccion(estado.relieve, analisis, plan, pedido) : estado.relieve),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [estado.relieve, analisis, plan, clave],
  );
  return { ...estado, relieve };
}

/** La foto satelital de Esri para la maqueta 3D. Hasta 2048 px de lado, pero nunca más fina que 0,5 m por píxel:
 * en un terreno chico (el Lunarejo mide ~800 m) 2048 px daban 0,4 m/px, más de lo que Esri tiene en esa zona, y el
 * servidor contestaba 500. `escala` < 1 pide una más chica (el reintento). */
export function urlFotoEsri(r: Pick<Relieve, "bordes" | "grilla" | "foto">, escala = 1): string {
  // los ejemplos traen su foto en el proyecto (public/ejemplos/foto_<id>.jpg, armar_relieve_ejemplos.py): Esri la arma
  // a pedido y tardaba varios segundos, con el terreno de afuera del campo en verde mientras tanto. Si
  // el archivo falla, el reintento (escala < 1) va a Esri como siempre.
  if (escala === 1 && r.foto) return r.foto;
  const { oeste, este, norte, sur } = r.bordes;
  const anchoM = (este - oeste) * 111320 * Math.cos((((norte + sur) / 2) * Math.PI) / 180);
  const altoM = (norte - sur) * 110540;
  const lado = Math.max(256, Math.min(2048, Math.round(Math.max(anchoM, altoM) / 0.5))) * escala;
  const asp = r.grilla.cols / r.grilla.filas;
  const w = Math.round(asp >= 1 ? lado : lado * asp), h = Math.round(asp >= 1 ? lado / asp : lado);
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export?bbox=${oeste},${sur},${este},${norte}&bboxSR=4326&imageSR=4326&size=${w},${h}&format=jpg&f=image`;
}
