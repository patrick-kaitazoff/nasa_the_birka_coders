import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { booleanIntersects, feature } from "@turf/turf";
import { crearSeccion, useApp } from "../store";
import { api } from "../api";
import {
  areaHa,
  bbox,
  puntoInterior,
  circuloGeo,
  calcularZonaLibre,
  lineasZonaLibre,
  limitarALibre,
  recortarAZonaLibre,
} from "./geo";
import { UbicarCampo, IconoUbicacion } from "./UbicarCampo";
import { dondeEstoy } from "./ubicacion";
import { Cargando } from "../comun/Cargando";
import { desencimar, etiquetaHTML, type Etiqueta } from "./etiquetas";
import { PanelSecciones, COLORES_SECCION } from "./PanelSecciones";
import { Lupa, AUMENTO, ZOOM_MAX_LUPA } from "./Lupa";
import { capaLugares } from "./Lugares";
import { capaRutas } from "./Rutas";
import { capaMar } from "./Mar";
import { capaCaminos } from "./Caminos";
import { acomodarNombres } from "./etiquetasZona";
import type { Geo } from "../tipos";

export type Fondo = "satelite" | "nasa" | "calles";

/** Un día con imagen limpia de HLS sobre el campo (lo elige el servidor con el catálogo CMR). */
export type PasadaHLS = { fecha: string; nubes: number; sensor: "L30" | "S30"; satelite: string; capa: string };

export function fechaCorta(iso: string) {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(a, m - 1, d).toLocaleDateString("es-UY", { day: "numeric", month: "short", year: "numeric" });
}

export function capaFondo(f: Fondo, pasada?: PasadaHLS | null): L.TileLayer {
  if (f === "calles") {
    return L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxNativeZoom: 19,
      maxZoom: 20,
      attribution: "© OpenStreetMap",
    });
  }
  if (f === "nasa" && pasada) {
    // HLS (Landsat + Sentinel-2 de la NASA, 30 m). GIBS lo sirve hasta el nivel 12; más cerca se agranda.
    return L.tileLayer(
      `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${pasada.capa}/default/${pasada.fecha}/GoogleMapsCompatible_Level12/{z}/{y}/{x}.png`,
      { maxNativeZoom: 12, maxZoom: 20, attribution: `NASA GIBS · HLS ${pasada.satelite}, 30 m (${fechaCorta(pasada.fecha)}) · caminos y nombres © colaboradores de OpenStreetMap (ODbL)` },
    );
  }
  // Esri World Imagery en el campo uruguayo tiene fotos nativas de alta resolución hasta nivel 18 (~0,6 m/px).
  // A nivel 19 no existen teselas en zonas rurales y el servidor devuelve la imagen gris "Map data not yet available".
  // Con maxNativeZoom: 18 y maxZoom: 20, Leaflet escala automáticamente las teselas del nivel 18
  // cuando el usuario se acerca a dibujar potreros, alambrados y esquinas, sin perder nunca la foto satelital.
  return L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxNativeZoom: 18,
    maxZoom: 20,
    attribution: "Imágenes © Esri, Maxar, Earthstar Geographics · caminos y nombres © colaboradores de OpenStreetMap (ODbL)",
  });
}

let deptosCache: Promise<any> | null = null;
export function bajarDepartamentos(): Promise<any> {
  deptosCache ||= api.departamentos().catch((e) => { deptosCache = null; throw e; });
  return deptosCache;
}

export function encuadrar(mapa: L.Map, g: Geo, conPanel = true, volar = false) {
  const [x0, y0, x1, y1] = bbox(g);
  encuadrarCaja(mapa, L.latLngBounds([y0, x0], [y1, x1]), conPanel, volar);
}

export type OpcionesAreaVisible = {
  padMin?: number;
  margenExtra?: number;
  /** no contar lo que tapa arriba o abajo (los botones chicos de las esquinas): para ver el país entero, que queda
   * en el medio y no llega a esas esquinas */
  soloLados?: boolean;
};

/**
 * Calcula con precisión matemática el área visible real del mapa descontando lo que tapan los paneles
 * flotantes marcados con [data-tapa-mapa], para que al encuadrar cualquier departamento o volver
 * a Uruguay la geometría quede perfectamente centrada en el espacio libre disponible.
 */
export function calcularAreaVisible(mapa: L.Map, _conPanel = true, opciones?: OpcionesAreaVisible) {
  const contenedor = mapa.getContainer();
  const cajaMapa = contenedor.getBoundingClientRect();
  const ancho = cajaMapa.width || mapa.getSize().x;
  const alto = cajaMapa.height || mapa.getSize().y;

  const padMin = opciones?.padMin ?? 24;
  const margenExtra = opciones?.margenExtra ?? 20;

  let padIzq = padMin;
  let padArriba = padMin;
  let padDer = padMin;
  let padAbajo = padMin;

  // Buscar todos los elementos del DOM con atributo data-tapa-mapa
  const elementos = document.querySelectorAll<HTMLElement>("[data-tapa-mapa]");

  for (const el of Array.from(elementos)) {
    // Si el elemento no está visible, se ignora
    if (el.offsetParent === null) continue;
    const estilo = window.getComputedStyle(el);
    if (estilo.display === "none" || estilo.visibility === "hidden" || parseFloat(estilo.opacity || "1") === 0) {
      continue;
    }

    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;

    // Calcular intersección del elemento con el contenedor del mapa
    const interIzq = Math.max(cajaMapa.left, r.left);
    const interDer = Math.min(cajaMapa.right, r.right);
    const interArriba = Math.max(cajaMapa.top, r.top);
    const interAbajo = Math.min(cajaMapa.bottom, r.bottom);

    // Si no intersecta el mapa, no ocluye
    if (interIzq >= interDer || interArriba >= interAbajo) continue;

    const dir = (el.dataset.tapaMapa || "auto").toLowerCase();
    if (opciones?.soloLados && /^(arriba|top|abajo|bottom)$/.test(dir)) continue;

    // Si tiene dirección declarada explícitamente
    if (dir === "izq" || dir === "izquierda") {
      padIzq = Math.max(padIzq, Math.round(interDer - cajaMapa.left + margenExtra));
    } else if (dir === "der" || dir === "derecha") {
      padDer = Math.max(padDer, Math.round(cajaMapa.right - interIzq + margenExtra));
    } else if (dir === "arriba" || dir === "top") {
      padArriba = Math.max(padArriba, Math.round(interAbajo - cajaMapa.top + margenExtra));
    } else if (dir === "abajo" || dir === "bottom") {
      padAbajo = Math.max(padAbajo, Math.round(cajaMapa.bottom - interArriba + margenExtra));
    } else {
      // Detección automática por cercanía a los bordes del mapa
      const distIzq = Math.abs(r.left - cajaMapa.left);
      const distDer = Math.abs(cajaMapa.right - r.right);
      const distArriba = Math.abs(r.top - cajaMapa.top);
      const distAbajo = Math.abs(cajaMapa.bottom - r.bottom);

      // Si ocupa casi todo el ancho, tapa arriba o abajo
      if (r.width >= ancho * 0.6) {
        if (distArriba < distAbajo) {
          padArriba = Math.max(padArriba, Math.round(interAbajo - cajaMapa.top + margenExtra));
        } else {
          padAbajo = Math.max(padAbajo, Math.round(cajaMapa.bottom - interArriba + margenExtra));
        }
      } else {
        // Tapa a los lados
        if (distIzq <= distDer) {
          padIzq = Math.max(padIzq, Math.round(interDer - cajaMapa.left + margenExtra));
        } else {
          padDer = Math.max(padDer, Math.round(cajaMapa.right - interIzq + margenExtra));
        }
      }
    }
  }

  // Salvaguardas para no exceder las dimensiones útiles del mapa
  const maxPadH = Math.max(0, ancho - 80);
  if (padIzq + padDer > maxPadH) {
    const factor = maxPadH / (padIzq + padDer);
    padIzq = Math.round(padIzq * factor);
    padDer = Math.round(padDer * factor);
  }
  const maxPadV = Math.max(0, alto - 60);
  if (padArriba + padAbajo > maxPadV) {
    const factor = maxPadV / (padArriba + padAbajo);
    padArriba = Math.round(padArriba * factor);
    padAbajo = Math.round(padAbajo * factor);
  }

  return {
    paddingTopLeft: [padIzq, padArriba] as L.PointTuple,
    paddingBottomRight: [padDer, padAbajo] as L.PointTuple,
  };
}

/** Muestra la caja en la parte del mapa que se ve: en el centro exacto del espacio libre no tapado. */
export function encuadrarCaja(mapa: L.Map, caja: L.LatLngBounds, conPanel = true, volar = false) {
  (mapa as any)._stop?.();
  mapa.invalidateSize({ pan: false });
  const { paddingTopLeft, paddingBottomRight } = calcularAreaVisible(mapa, conPanel);
  const opciones = { paddingTopLeft, paddingBottomRight, maxZoom: 16 };
  if (volar) { mapa.flyToBounds(caja, { ...opciones, duration: VUELO_S }); return; }
  // Si la caja ya se ve entera en la parte libre y no queda chiquita, no se mueve nada: al terminar el contorno
  // el mapa daba un salto rápido para reencuadrar algo que ya estaba a la vista.
  const t = mapa.getSize();
  const libre = L.latLngBounds(
    mapa.containerPointToLatLng(L.point(paddingTopLeft[0], t.y - paddingBottomRight[1])),
    mapa.containerPointToLatLng(L.point(t.x - paddingBottomRight[0], paddingTopLeft[1])),
  );
  const zIdeal = mapa.getBoundsZoom(caja, false, L.point(paddingTopLeft[0] + paddingBottomRight[0], paddingTopLeft[1] + paddingBottomRight[1]));
  if (libre.contains(caja) && mapa.getZoom() >= Math.min(zIdeal, 16) - 1.5) return;
  mapa.fitBounds(caja, { ...opciones, animate: true, duration: 0.6 });
}

/** Vuelos del mapa. El mapa llegaba volando desde lo alto (y antes, desde un globo); ahora abre
 * ya encuadrado. LLEGADA_* quedan para el vuelo que todavía puede pedir el encuadre (`vueloLlegada`, hoy apagado). */
const VUELO_S = 1.1;
export const LLEGADA_DESDE: [number, number] = [-32.5, -55.8];
export const LLEGADA_ZOOM = 4.6;
/** Lo que dura el vuelo del mapa hasta Uruguay al llegar (el globo empalma con su velocidad inicial). */
export const LLEGADA_VUELO_S = 1.7;

/** Más cerca que esto, el departamento bajo el mouse ya no se aclara (ocupa toda la vista). */
const ZOOM_REALCE = 9;

/** El borde de Uruguay (Artigas al norte, Punta del Este al sur, Nueva Palmira al oeste, la laguna Merín al este). */
const URUGUAY: L.LatLngBoundsExpression = [[-34.98, -58.44], [-30.08, -53.07]];
/** Los 48 estados contiguos. */
const EEUU: L.LatLngBoundsExpression = [[24.5, -124.8], [49.4, -66.9]];

/** Todo Uruguay, dejando libre el panel y el chat si está adelante a la derecha. Los botones de las esquinas
 * («Satélite») no cuentan: antes se tomaban como si taparan todo el ancho de arriba y el país quedaba chico y bajo. */
function verUruguay(m: L.Map, volar = false, seco = false) {
  m.invalidateSize({ pan: false });
  const { paddingTopLeft, paddingBottomRight } = calcularAreaVisible(m, true, { soloLados: true, padMin: 28 });
  // con «Estados Unidos» elegido en el paso 1, el país es EE. UU.
  const caja = useApp.getState().paisMapa === "US" ? EEUU : URUGUAY;
  if (volar) {
    // más largo que los otros vuelos y con una curva suave, para que llegue sin frenar de golpe
    m.flyToBounds(caja, { paddingTopLeft, paddingBottomRight, duration: LLEGADA_VUELO_S, easeLinearity: 0.12 });
    return;
  }
  m.fitBounds(caja, { paddingTopLeft, paddingBottomRight, ...(seco ? { animate: false } : {}) });
}

export function MapaCampo() {
  const div = useRef<HTMLDivElement>(null);
  const mapa = useRef<L.Map | null>(null);
  const capas = useRef<L.LayerGroup | null>(null);
  const fondoRef = useRef<L.TileLayer | null>(null);
  const [fondo, setFondo] = useState<Fondo>("satelite");
  const fondoActual = useRef<Fondo>(fondo);
  fondoActual.current = fondo;
  const [pasadas, setPasadas] = useState<PasadaHLS[]>([]);
  const [iPasada, setIPasada] = useState(0);
  const deptos = useRef<L.GeoJSON | null>(null);
  // EE. UU.: estados y condados del estado elegido, para tocar y acercarse como con los departamentos
  const estadosUs = useRef<L.GeoJSON | null>(null);
  const condadosUs = useRef<L.GeoJSON | null>(null);
  const estadoUsElegido = useRef<string | null>(null);
  const condadoUsElegido = useRef<string | null>(null);
  const condadoBajoMouse = useRef<string | null>(null);
  // lo elegido, para el camino «Todos los estados › Texas › Schleicher» de arriba del mapa
  const [zonaUs, setZonaUs] = useState<{ estado?: { fips: string; nombre: string }; condado?: { fips: string; nombre: string } }>({});
  const rutasUs = useRef<L.TileLayer | null>(null);
  const paisAnterior = useRef<string | null>(null);
  const { paisMapa, tocandoLote } = useApp();
  const { campo, modoMapa, setModoMapa, setContorno, setSecciones, centrar, seccionSel, setSeccionSel, enviar, explorando, setConfirmarBorrarContorno, setAviso, mensajes } = useApp();
  const capaEditandoRef = useRef<L.Polygon | null>(null);
  const [panelLotesForzado, setPanelLotesForzado] = useState<boolean | null>(null);
  const { editandoCampo } = useApp();
  const seccionesConfirmadas = campo.secciones.length > 0 && mensajes.some((m) => m.tarjeta?.tipo === "secciones" && m.tarjeta.hecha);
  const panelLotesOculto = !editandoCampo && seccionesConfirmadas && (panelLotesForzado === false || panelLotesForzado === null);
  const [mapaListo, setMapaListo] = useState<L.Map | null>(null);
  const conMouse = typeof window !== "undefined" && window.matchMedia?.("(pointer: fine)").matches;
  const lupaActiva = !!conMouse && explorando && !campo.contorno && modoMapa === "ver";
  const ultimoContorno = useRef<string>("");
  // lo último que se pidió mirar sin campo todavía (un departamento, la ubicación): se vuelve a encuadrar si cambia el tamaño
  const objetivo = useRef<L.LatLngBounds | null>(null);
  const deptoElegido = useRef<string | null>(null);
  const lugares = useRef<ReturnType<typeof capaLugares> | null>(null);
  const rutas = useRef<ReturnType<typeof capaRutas> | null>(null);
  const mar = useRef<ReturnType<typeof capaMar> | null>(null);
  const caminos = useRef<ReturnType<typeof capaCaminos> | null>(null);
  const [buscandoGPS, setBuscandoGPS] = useState(false);
  const alIrADondeEstoy = async () => {
    if (buscandoGPS) return;
    setBuscandoGPS(true);
    try {
      const d = await dondeEstoy();
      const m = mapa.current;
      useApp.getState().setExplorando(true);
      useApp.getState().setCentrar(d.lat, d.lon, d.zoom || 14);
      if (m) {
        m.flyTo([d.lat, d.lon], Math.max(m.getZoom(), d.zoom || 14), { duration: 1.2 });
      }
      if (d.aviso) useApp.getState().setAviso(d.aviso);
    } catch (e: any) {
      useApp.getState().setAviso(e?.message || "No pudimos obtener tu ubicación.");
    } finally {
      setBuscandoGPS(false);
    }
  };

  // encuadre pendiente: se aplica cuando el tamaño del mapa lleva un rato quieto
  // esperarTamanio: el pedido llegó con el chat todavía adelante; el mapa va a cambiar de tamaño cuando el
  // chat pase al costado y recién ahí se puede encuadrar (en esta PC React tarda más de 160 ms en eso)
  const pedido = useRef<{ volar: boolean; esperarTamanio: boolean; desde: number } | null>(null);
  const tEncuadre = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const volandoHasta = useRef(0);
  // el primer encuadre se hace volando (una sola vez): al tocar «Comenzar» en la bienvenida, o al llegar desde la
  // portada con un campo guardado (sin bienvenida). Mientras se ve la bienvenida, el mapa espera lejos.
  // Sin vuelo de llegada: el mapa abre ya encuadrado, con la
  // foto que bajó la portada, y la entrada la hace el fundido entre páginas (inicio/EntradaHerramienta.tsx)
  const vueloLlegada = useRef(false);
  const { bienvenida } = useApp();
  const programarEncuadre = (volar: boolean, espera = 160) => {
    clearTimeout(tEncuadre.current);
    tEncuadre.current = setTimeout(() => {
      const m = mapa.current;
      if (!m || m.getSize().x < 60) return;
      const p = pedido.current;
      if (p?.esperarTamanio && performance.now() - p.desde < 1500) { programarEncuadre(volar, 100); return; }
      pedido.current = null;
      const c = useApp.getState().campo.contorno;
      // si cambia el tamaño en pleno vuelo, se vuelve a volar (de golpe se vería un salto)
      const enVuelo = performance.now() < volandoHasta.current;
      if (vueloLlegada.current && useApp.getState().bienvenida) return;
      const llegando = vueloLlegada.current;
      vueloLlegada.current = false;
      if (llegando) volandoHasta.current = performance.now() + VUELO_S * 1000 + 50;
      if (c) encuadrar(m, c, true, llegando);
      else if (objetivo.current) {
        if (volar || enVuelo) volandoHasta.current = performance.now() + 1150;
        encuadrarCaja(m, objetivo.current, true, volar || enVuelo);
      } else {
        const st = useApp.getState();
        // solo volver a Uruguay en carga inicial limpia, nunca si la persona ya está explorando o dibujando
        if (!st.explorando && st.modoMapa === "ver" && !st.campo.contorno) {
          verUruguay(m, llegando);
        }
      }
    }, espera);
  };
  // al cerrarse la bienvenida («Comenzar»), el mapa baja volando desde el sur de Sudamérica
  useEffect(() => {
    if (!bienvenida && vueloLlegada.current) programarEncuadre(true, 40);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bienvenida]);

  /** Mirar una caja (un departamento, la ubicación): espera a que el mapa tenga su tamaño final y vuela ahí. */
  const pedirEncuadre = (caja: L.LatLngBounds) => {
    objetivo.current = caja;
    pedido.current = { volar: true, esperarTamanio: false, desde: performance.now() };
    programarEncuadre(true);
  };

  // crear el mapa una vez
  useEffect(() => {
    if (!div.current || mapa.current) return;
    const m = L.map(div.current, { zoomControl: false, attributionControl: true, doubleClickZoom: false, minZoom: 2, zoomSnap: 0.1, zoomDelta: 0.5, wheelPxPerZoomLevel: 110, wheelDebounceTime: 20, maxZoom: 20 }).setView(vueloLlegada.current ? LLEGADA_DESDE : [-32.8, -56.0], vueloLlegada.current ? LLEGADA_ZOOM : 7);
    m.doubleClickZoom.disable();
    L.control.zoom({ position: "bottomright" }).addTo(m);
    // los textos de la librería de dibujo, en castellano del Uruguay (traía "Presiona el primer marcador para finalizar")
    m.pm.setLang("es_uy" as any, {
      tooltips: {
        placeMarker: "Tocá para poner un punto",
        firstVertex: "Tocá la primera esquina",
        continueLine: "Tocá la siguiente esquina",
        finishLine: "Tocá el último punto para terminar",
        finishPoly: "Tocá la primera esquina para cerrar",
        finishRect: "Tocá para terminar",
        startCircle: "Tocá para poner el centro",
        finishCircle: "Tocá para terminar el círculo",
        placeCircleMarker: "Tocá para poner el punto",
        placeText: "Tocá para poner el texto",
      },
    } as any, "es");
    m.pm.setGlobalOptions({ snappable: true, snapDistance: 20, snapSegment: true, snapMiddlePoints: true, allowSelfIntersection: false, pathOptions: { color: "#f2c80f", weight: 3 } } as any);
    capas.current = L.layerGroup().addTo(m);
    const referencia = m.createPane("referencia");
    referencia.style.zIndex = "250";
    referencia.style.pointerEvents = "none";
    mapa.current = m;
    setMapaListo(m);
    if (import.meta.env.DEV) (window as any).__mapa = m; // para las pruebas en el navegador
    lugares.current = capaLugares(m);
    lugares.current.mostrar(true);
    rutas.current = capaRutas(m);
    rutas.current.mostrar(true);
    mar.current = capaMar(m);
    mar.current.mostrar(true);
    caminos.current = capaCaminos(m);
    caminos.current.mostrar(true);
    const alElegirDepto = (e: any) => {
      if (e.detail) caminos.current?.cargarDepartamento(e.detail);
    };
    window.addEventListener("fieldshift:departamento", alElegirDepto);
    // Clic en cualquier punto del mapa mientras se explora: acerca suavemente ("acercar acá")
    const alClicMapa = (ev: L.LeafletMouseEvent) => {
      const st = useApp.getState();
      if (st.tocandoLote && st.modoMapa === "ver") {
        // EE. UU.: el contorno del lote sale del Cropland Data Layer en ese punto (UbicarCampo lo pide)
        window.dispatchEvent(new CustomEvent("fieldshift:toque-lote", { detail: { lat: ev.latlng.lat, lon: ev.latlng.lng } }));
        return;
      }
      if (st.modoMapa !== "ver" || st.campo.contorno) return;
      if (st.explorando && m.getZoom() <= ZOOM_MAX_LUPA && m.getZoom() >= 8.0) {
        m.flyTo(ev.latlng, Math.min(16, m.getZoom() + AUMENTO), { duration: 0.8 });
        objetivo.current = null;
      }
    };
    m.on("click", alClicMapa);
    // El contenedor puede montarse sin tamaño todavía, y cambia de tamaño cuando el chat pasa al costado.
    // Regla: nunca se encuadra mientras el tamaño
    // se está moviendo. Cada cambio de tamaño reinicia la espera; cuando queda quieto, se encuadra una sola vez
    // (volando si lo pidió un clic, de golpe si solo cambió el tamaño).
    let tamAnterior = "";
    const obs = new ResizeObserver(() => {
      m.invalidateSize({ pan: false });
      const { x, y } = m.getSize();
      if (x < 60 || y < 60) return; // escondido (otra pestaña en el celular)
      const tam = `${x}x${y}`;
      if (tam === tamAnterior) return;
      tamAnterior = tam;
      if (pedido.current) pedido.current.esperarTamanio = false;
      programarEncuadre(pedido.current?.volar ?? false);
    });
    const alPedirEncuadre = () => setTimeout(() => { const c = useApp.getState().campo.contorno; if (c) encuadrar(m, c); }, 60);
    window.addEventListener("fieldshift:encuadrar", alPedirEncuadre);
    obs.observe(div.current);
    const t = setTimeout(() => {
      const c = useApp.getState().campo.contorno;
      if (c) encuadrar(m, c);
    }, 80);
    return () => {
      clearTimeout(t);
      clearTimeout(tEncuadre.current);
      window.removeEventListener("fieldshift:encuadrar", alPedirEncuadre);
      m.off("click", alClicMapa);
      caminos.current?.destruir();
      window.removeEventListener("fieldshift:departamento", alElegirDepto);
      obs.disconnect();
      m.remove();
      mapa.current = null;
    };
  }, []);

  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    fondoRef.current?.remove();
    fondoRef.current = capaFondo(fondo, pasadas[iPasada]).addTo(m);
    fondoRef.current.bringToBack();
  }, [fondo, pasadas, iPasada]);

  // con el contorno puesto, en segundo plano se buscan los días con imagen limpia de la NASA (30 m)
  const cajaContorno = campo.contorno ? bbox(campo.contorno).map((v) => v.toFixed(3)).join(",") : "";
  useEffect(() => {
    setPasadas([]);
    setIPasada(0);
    if (!cajaContorno) { setFondo((f) => (f === "nasa" ? "satelite" : f)); return; }
    let vivo = true;
    const [o, s, e, n] = cajaContorno.split(",").map(Number);
    api.hls(o, s, e, n).then((r) => { if (vivo) setPasadas(r.fechas || []); }).catch(() => { /* sin catálogo: queda el satélite común */ });
    // los suelos que hay dentro del contorno (MGAP), si no vinieron con el padrón: para avisar si una sección mezcla suelos
    const st = useApp.getState();
    if (st.campo.contorno && !st.campo.partes_suelo?.length) {
      api.suelosArea(st.campo.contorno).then((r) => {
        if (vivo && r.partes?.length) useApp.getState().actualizarCampo({ partes_suelo: r.partes.map((p) => ({ grupo_coneat: p.grupo_coneat, geometria: p.geometria })) });
      }).catch(() => { /* sin MGAP: no se revisan los suelos */ });
    }
    return () => { vivo = false; };
  }, [cajaContorno]);

  useEffect(() => {
    const m = mapa.current;
    if (!m || deptos.current) return;
    let vivo = true;
    bajarDepartamentos().then((fc) => {
      if (!vivo || !mapa.current) return;
      const dibujo = L.svg({ padding: 1 });
      const capa = L.geoJSON(fc, {
        // se dibuja bastante más allá de lo que se ve: al arrastrar rápido las líneas ya están (con el 10 % de
        // siempre, se cortaban en el borde hasta soltar el mouse)
        renderer: dibujo,
        style: () => ({ color: "#ffffff", weight: 1.5, opacity: fondoActual.current === "satelite" ? 0.9 : 0, fillColor: "#ffffff", fillOpacity: 0.04 }),
        onEachFeature: (f, l) => {
          const nombre = titulo(f.properties.nombre);
          // nombre propio: no pasa por el traductor
          l.bindTooltip(`<span data-no-traducir>${nombre.replace(/[<>&]/g, "")}</span>`, { permanent: true, direction: "center", className: "etiqueta-depto" });
          // el realce sirve para elegir departamento desde lejos; de cerca el departamento llena la pantalla y
          // se veía como un velo blanco sobre toda la foto al cruzar el límite
          l.on("mouseover", () => {
            const m = mapa.current;
            if (m && m.getZoom() < ZOOM_REALCE && useApp.getState().modoMapa === "ver") (l as L.Path).setStyle({ fillOpacity: 0.16 });
          });
          l.on("mouseout", () => (l as L.Path).setStyle({ fillOpacity: 0.04 }));
          l.on("click", (ev: L.LeafletMouseEvent) => {
            const st = useApp.getState();
            if (st.modoMapa !== "ver" || st.paisMapa === "US") return; // mientras se dibuja, el clic es un vértice
            if (st.campo.contorno) return; // con campo definido, el clic sobre el mapa nunca reencuadra el departamento
            const m = mapa.current;
            // ya elegido el departamento o con zoom suficiente para explorar, el clic es "acercar acá" (lo que mostraba la lupa)
            if (m && (st.explorando || m.getZoom() >= 8.5)) {
              if (deptoElegido.current === f.properties.nombre || m.getZoom() >= 8.5) {
                if (m.getZoom() <= 16) {
                  m.flyTo(ev.latlng, Math.min(17, m.getZoom() + AUMENTO), { duration: 0.8 });
                  objetivo.current = null; // desde acá manda lo que la persona mira
                }
                return; // ya estamos en este departamento o con zoom alto: NUNCA hacer zoom out
              }
            }
            deptoElegido.current = f.properties.nombre;
            // el chat deja de estar adelante (si no, tapa medio departamento) y el departamento se encuadra en lo que se ve
            st.setExplorando(true);
            st.setPestania("mapa");
            pedirEncuadre((l as L.Polygon).getBounds());
            window.dispatchEvent(new CustomEvent("fieldshift:departamento", { detail: f.properties.nombre }));
          });
        },
      } as L.GeoJSONOptions);
      deptos.current = capa;
      if (import.meta.env.DEV) (window as any).__deptos = capa;
      if (useApp.getState().paisMapa !== "US") {
        capa.addTo(mapa.current).bringToBack();
        (dibujo as any)._container?.classList.add("capa-entra"); // aparecen fundiéndose, no de golpe
      }
      fondoRef.current?.bringToBack();
    }).catch(() => { /* sin servidor del MGAP: el mapa anda igual */ });
    return () => { vivo = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // EE. UU.: con «Estados Unidos» elegido en el paso 1,
  // los departamentos se van y aparecen los estados; al tocar uno (o elegirlo en la lista) se encuadra y aparecen sus
  // condados, que se tocan igual. Lo elegido en el mapa se refleja en las listas de UbicarCampo y al revés.
  /** Los nombres de estados y condados que entran sin pisarse (etiquetasZona.ts), y después los pueblos. */
  const acomodarUs = () => {
    const m = mapa.current;
    if (!m || useApp.getState().paisMapa !== "US") return;
    const ocupado = acomodarNombres(m, estadosUs.current, {
      clase: "etiqueta-depto etiqueta-estado",
      nombre: (p) => String(p.nombre), corto: (p) => p.sigla,
      // adentro del estado elegido mandan sus condados: su nombre ya está arriba, en el camino
      esconder: (p) => p.fips === estadoUsElegido.current && !!condadosUs.current,
    });
    acomodarNombres(m, condadosUs.current, {
      clase: "etiqueta-depto etiqueta-condado",
      nombre: (p) => String(p.base),
      esconder: (p) => p.fips === condadoUsElegido.current && m.getZoom() >= 8.5,
      // el elegido se nombra mientras se ve el estado; ya adentro del condado su nombre está arriba, en el camino
      forzar: (p) => (p.fips === condadoUsElegido.current ? m.getZoom() < 8.5 : p.fips === condadoBajoMouse.current),
      ocupado,
    });
    lugares.current?.redibujar();
  };
  /** El estado elegido queda despejado y el resto se oscurece un poco, así se ve dónde se está trabajando. */
  const estiloEstado = (fips: string, encima = false): L.PathOptions => {
    const elegido = estadoUsElegido.current;
    if (!elegido) return { color: "#ffffff", weight: 1.5, opacity: 0.9, fillColor: "#ffffff", fillOpacity: encima ? 0.16 : 0.04 };
    if (fips === elegido) return { color: "#ffffff", weight: 2.4, opacity: 1, fillColor: "#ffffff", fillOpacity: 0 };
    return { color: "#ffffff", weight: 1, opacity: 0.55, fillColor: "#0b1410", fillOpacity: encima ? 0.12 : 0.34 };
  };
  const pintarEstados = () => estadosUs.current?.eachLayer((l: any) => l.setStyle(estiloEstado(l.feature?.properties?.fips)));
  const estiloCondado = (fips: string, encima = false): L.PathOptions => (fips === condadoUsElegido.current
    ? { color: "#f2c80f", weight: 2.5, opacity: 1, fillColor: "#ffffff", fillOpacity: 0 }
    : { color: "#ffffff", weight: 1, opacity: 0.75, fillColor: "#ffffff", fillOpacity: encima ? 0.16 : 0.03 });
  /** Aviso para la lupa: qué zona hay bajo el mouse (el condado, o el estado si todavía no se eligió uno). */
  const avisarZona = (nombre: string | null) => window.dispatchEvent(new CustomEvent("fieldshift:zona-mouse", { detail: nombre }));

  /** EE. UU.: rutas y calles con su número encima de la foto. En Uruguay van las nuestras (Rutas.ts, Caminos.ts); para todo EE. UU. se usa la capa de referencia de
   * Esri, hecha para ir sobre su foto. Aparece al mirar un estado; en el mapa de calles no va, ya las trae. */
  const ponerRutasUs = () => {
    const m = mapa.current;
    if (!m) return;
    const quiere = useApp.getState().paisMapa === "US" && fondoActual.current !== "calles";
    if (!quiere) { rutasUs.current?.remove(); return; }
    rutasUs.current ||= L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}", {
      // minZoom en la capa y también en el mapa (L.map, más arriba): sin el del mapa, Leaflet subía solo el zoom a 6
      // cada vez que se cambiaba la foto de fondo y esta capa quedaba un instante como la única con límite
      pane: "referencia", minZoom: 5, maxNativeZoom: 17, maxZoom: 20, opacity: 0.9, attribution: "rutas © Esri",
    });
    if (!m.hasLayer(rutasUs.current)) rutasUs.current.addTo(m);
  };

  /** Vuelve a todo el país: sin estado elegido, sin condados. */
  const soltarEstadoUs = () => {
    const m = mapa.current;
    estadoUsElegido.current = null;
    condadoUsElegido.current = null;
    condadoBajoMouse.current = null;
    condadosUs.current?.remove();
    condadosUs.current = null;
    setZonaUs({});
    pintarEstados();
    acomodarUs();
    if (m) { objetivo.current = null; useApp.getState().setExplorando(false); verUruguay(m, true); }
  };

  const elegirEstadoUs = (fips: string, encuadrar = true): Promise<void> => {
    const m = mapa.current;
    if (!m || !estadosUs.current) return Promise.resolve();
    if (!fips) { soltarEstadoUs(); return Promise.resolve(); }
    const capaEstado = estadosUs.current.getLayers().find((l: any) => l.feature?.properties?.fips === fips) as L.Polygon | undefined;
    if (encuadrar && capaEstado) pedirEncuadre(capaEstado.getBounds());
    const nombreEstado = String((capaEstado as any)?.feature?.properties?.nombre || "");
    if (encuadrar && condadoUsElegido.current) {
      // se volvió del condado al estado entero
      condadoUsElegido.current = null;
      condadosUs.current?.eachLayer((l: any) => l.setStyle(estiloCondado(l.feature?.properties?.fips)));
      setZonaUs({ estado: { fips, nombre: nombreEstado } });
      acomodarUs();
    }
    if (estadoUsElegido.current === fips && condadosUs.current) return Promise.resolve();
    estadoUsElegido.current = fips;
    condadoUsElegido.current = null;
    condadosUs.current?.remove();
    condadosUs.current = null;
    setZonaUs({ estado: { fips, nombre: nombreEstado } });
    pintarEstados();
    acomodarUs();
    return api.condadosUs(fips).then((fc) => {
      if (!mapa.current || useApp.getState().paisMapa !== "US" || estadoUsElegido.current !== fips) return;
      condadosUs.current?.remove();
      const dibujo = L.svg({ padding: 1 });
      condadosUs.current = L.geoJSON(fc, {
        renderer: dibujo,
        style: (f) => estiloCondado(f?.properties.fips),
        onEachFeature: (f, l) => {
          l.bindTooltip(`<span data-no-traducir>${String(f.properties.base).replace(/[<>&]/g, "")}</span>`,
            { permanent: true, direction: "center", className: "etiqueta-depto etiqueta-condado nombre-oculto" });
          l.on("mouseover", () => {
            const mm = mapa.current;
            if (!mm || useApp.getState().modoMapa !== "ver") return;
            // adentro del condado ya elegido no hace falta repetir su nombre en la lupa
            avisarZona(condadoUsElegido.current === f.properties.fips && mm.getZoom() >= 8.5 ? null : String(f.properties.nombre));
            if (mm.getZoom() >= 11) return; // de cerca el condado llena la pantalla
            if (condadoUsElegido.current !== f.properties.fips) (l as L.Path).setStyle(estiloCondado(f.properties.fips, true));
            condadoBajoMouse.current = f.properties.fips;
            acomodarUs();
          });
          l.on("mouseout", () => {
            (l as L.Path).setStyle(estiloCondado(f.properties.fips));
            avisarZona(null);
            if (condadoBajoMouse.current === f.properties.fips) { condadoBajoMouse.current = null; acomodarUs(); }
          });
          l.on("click", (ev: L.LeafletMouseEvent) => {
            const st = useApp.getState();
            if (st.tocandoLote || st.modoMapa !== "ver" || st.campo.contorno) return; // el mapa se encarga
            if (condadoUsElegido.current === f.properties.fips) return; // ya elegido: el clic es «acercar acá»
            L.DomEvent.stopPropagation(ev as any);
            elegirCondadoUs(f.properties.fips);
            window.dispatchEvent(new CustomEvent("fieldshift:condado-us", { detail: f.properties.fips }));
          });
        },
      } as L.GeoJSONOptions).addTo(mapa.current);
      // los condados entran fundiéndose, y sus nombres se acomodan cuando ya están en la página
      (dibujo as any)._container?.classList.add("capa-entra");
      acomodarUs();
    }).catch(() => { /* sin condados: se puede marcar igual */ });
  };
  const elegirCondadoUs = (fips: string) => {
    const capa = condadosUs.current?.getLayers().find((l: any) => l.feature?.properties?.fips === fips) as L.Polygon | undefined;
    if (!capa) return;
    condadoUsElegido.current = fips;
    condadosUs.current?.eachLayer((l: any) => l.setStyle(estiloCondado(l.feature?.properties?.fips)));
    (capa as any).bringToFront?.();
    setZonaUs((z) => ({ estado: z.estado, condado: { fips, nombre: String((capa as any).feature?.properties?.nombre || "") } }));
    acomodarUs();
    const st = useApp.getState();
    st.setExplorando(true);
    st.setPestania("mapa");
    pedirEncuadre(capa.getBounds());
  };

  useEffect(() => {
    const m = mapaListo;
    if (!m) return;
    const us = paisMapa === "US";
    const cambiarCapas = () => {
    if (deptos.current) {
      if (us) deptos.current.remove();
      else if (!m.hasLayer(deptos.current)) { deptos.current.addTo(m).bringToBack(); fondoRef.current?.bringToBack(); }
    }
    if (!us) {
      estadosUs.current?.remove();
      condadosUs.current?.remove();
    } else if (estadosUs.current) {
      if (!m.hasLayer(estadosUs.current)) { estadosUs.current.addTo(m); ((estadosUs.current.options as any).renderer?._container as HTMLElement | undefined)?.classList.add("capa-entra"); }
      if (condadosUs.current && !m.hasLayer(condadosUs.current)) condadosUs.current.addTo(m);
    } else {
      api.estadosUs().then((fc) => {
        if (!mapa.current || estadosUs.current) return;
        const dibujo = L.svg({ padding: 1 });
        estadosUs.current = L.geoJSON(fc, {
          renderer: dibujo,
          style: (f) => estiloEstado(f?.properties.fips),
          onEachFeature: (f, l) => {
            l.bindTooltip(`<span data-no-traducir>${String(f.properties.nombre).replace(/[<>&]/g, "")}</span>`,
              { permanent: true, direction: "center", className: "etiqueta-depto etiqueta-estado nombre-oculto" });
            l.on("mouseover", () => {
              const mm = mapa.current;
              if (!mm || useApp.getState().modoMapa !== "ver" || estadoUsElegido.current === f.properties.fips) return;
              if (!estadoUsElegido.current) avisarZona(String(f.properties.nombre));
              if (mm.getZoom() < 8) (l as L.Path).setStyle(estiloEstado(f.properties.fips, true));
            });
            l.on("mouseout", () => { (l as L.Path).setStyle(estiloEstado(f.properties.fips)); if (!estadoUsElegido.current) avisarZona(null); });
            l.on("click", (ev: L.LeafletMouseEvent) => {
              const st = useApp.getState();
              if (st.tocandoLote || st.modoMapa !== "ver" || st.campo.contorno) return;
              if (estadoUsElegido.current === f.properties.fips) return; // adentro del estado mandan los condados
              L.DomEvent.stopPropagation(ev as any);
              st.setExplorando(true);
              st.setPestania("mapa");
              void elegirEstadoUs(f.properties.fips);
              window.dispatchEvent(new CustomEvent("fieldshift:estado-us", { detail: f.properties.fips }));
            });
          },
        } as L.GeoJSONOptions);
        if (useApp.getState().paisMapa === "US") {
          estadosUs.current.addTo(mapa.current);
          (dibujo as any)._container?.classList.add("capa-entra");
          acomodarUs();
        }
      }).catch(() => { /* sin estados: se puede buscar o marcar igual */ });
    }
    // los nombres de pueblos son los del país; en EE. UU., además, las rutas con su número (Esri) sobre la foto
    lugares.current?.pais(us ? "US" : "UY");
    ponerRutasUs();
    if (us) setTimeout(acomodarUs, 0);
    };
    const cambio = paisAnterior.current !== null && paisAnterior.current !== paisMapa;
    paisAnterior.current = paisMapa;
    const st = useApp.getState();
    if (!cambio || st.campo.contorno || st.modoMapa !== "ver" || m.getSize().x <= 60) { cambiarCapas(); return; }
    // Al cambiar de país (no al abrir) y sin campo todavía, el mapa pasa al otro país con un fundido.
    // Antes volaba de Uruguay a EE. UU. en 1,7 s: 8.000 km alejándose hasta ver medio mundo, con la foto llegando a
    // pedazos, y los límites de un país se cambiaban por los del otro de golpe al empezar. Ahora el mapa se apaga
    // 0,2 s, se cambia todo a oscuras (encuadre, límites, nombres) y vuelve cuando la foto del país nuevo ya bajó.
    objetivo.current = null;
    const cont = m.getContainer();
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { cambiarCapas(); verUruguay(m, false, true); return; }
    cont.classList.add("cambiando-pais");
    let tTope = 0;
    const tApagado = window.setTimeout(() => {
      cambiarCapas();
      verUruguay(m, false, true);
      const mostrar = () => { clearTimeout(tTope); fondoRef.current?.off("load", mostrar); cont.classList.remove("cambiando-pais"); acomodarUs(); };
      fondoRef.current?.once("load", mostrar);
      tTope = window.setTimeout(mostrar, 1100); // con internet lento no se espera más que esto
    }, 230);
    return () => { clearTimeout(tApagado); clearTimeout(tTope); cont.classList.remove("cambiando-pais"); };
  }, [mapaListo, paisMapa]); // eslint-disable-line react-hooks/exhaustive-deps

  // los nombres se vuelven a acomodar en cada zoom: de más cerca entran más
  const acomodarRef = useRef(acomodarUs);
  acomodarRef.current = acomodarUs;
  useEffect(() => {
    const m = mapaListo;
    if (!m) return;
    const alZoom = () => {
      acomodarRef.current();
      // ya adentro del condado elegido, la lupa deja de repetir su nombre
      if (condadoUsElegido.current && m.getZoom() >= 8.5) window.dispatchEvent(new CustomEvent("fieldshift:zona-mouse", { detail: null }));
    };
    m.on("zoomend", alZoom);
    return () => { m.off("zoomend", alZoom); };
  }, [mapaListo]);

  // las listas de estado y condado de UbicarCampo mueven el mapa
  useEffect(() => {
    const alEstado = (e: Event) => { void elegirEstadoUs(String((e as CustomEvent).detail)); };
    const alCondado = (e: Event) => {
      const fips = String((e as CustomEvent).detail);
      void elegirEstadoUs(fips.slice(0, 2), false).then(() => elegirCondadoUs(fips));
    };
    window.addEventListener("fieldshift:ir-estado", alEstado);
    window.addEventListener("fieldshift:ir-condado", alCondado);
    return () => { window.removeEventListener("fieldshift:ir-estado", alEstado); window.removeEventListener("fieldshift:ir-condado", alCondado); };
  }, [mapaListo]); // eslint-disable-line react-hooks/exhaustive-deps

  // con «Tocar el lote» activo, el cursor es una cruz
  useEffect(() => {
    mapaListo?.getContainer().classList.toggle("tocando-lote", tocandoLote);
  }, [mapaListo, tocandoLote]);

  // Los límites de departamento van siempre sobre el satélite, sin botón.
  // El mapa de calles ya trae sus propios límites y nombres, y sobre la imagen de la NASA por fecha lo que
  // importa es el campo: ahí los nuestros se esconden, pero siguen sirviendo para tocar y acercarse.
  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    const calles = fondo === "calles";
    m.getContainer().classList.toggle("fondo-calles", calles);
    m.getContainer().classList.toggle("sin-deptos", fondo !== "satelite");
    lugares.current?.mostrar(!calles); // el mapa de calles ya trae los nombres
    rutas.current?.mostrar(!calles); // y las rutas
    mar.current?.mostrar(fondo === "satelite"); // el agua en cuadrados es de la foto de Esri
    caminos.current?.mostrar(fondo === "satelite");
    deptos.current?.setStyle({ opacity: fondo === "satelite" ? 0.9 : 0 });
    ponerRutasUs();
    setTimeout(() => acomodarRef.current(), 0);
  }, [fondo]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (campo.ubicacion?.departamento) {
      caminos.current?.cargarDepartamento(campo.ubicacion.departamento);
    }
  }, [campo.ubicacion?.departamento]);

  // con el campo ya ubicado y de cerca, los nombres de departamento estorban
  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    const ajustar = () => m.getContainer().classList.toggle("deptos-sin-nombre", m.getZoom() >= 11);
    ajustar();
    m.on("zoomend", ajustar);
    return () => { m.off("zoomend", ajustar); };
  }, []);

  useEffect(() => {
    const m = mapa.current;
    if (!m || campo.contorno || modoMapa !== "ver" || useApp.getState().explorando) return;
    // mientras se ve la bienvenida, el mapa espera alto para la llegada (antes esto lo encuadraba de una y el vuelo
    // de llegada salía de Uruguay hacia Uruguay, sin moverse)
    if (vueloLlegada.current && useApp.getState().bienvenida) return;
    objetivo.current = null;
    if (m.getSize().x > 60) verUruguay(m);
  }, [campo.contorno, modoMapa]);

  // el lugar que se buscó en el paso 1 (mapa/BuscarLugar.tsx): un alfiler con su nombre, hasta marcar el contorno
  const pinLugar = useRef<L.Marker | null>(null);
  useEffect(() => {
    const m = mapaListo;
    if (!m) return;
    const alPunto = (e: Event) => {
      const r = (e as CustomEvent).detail as { lat: number; lon: number; nombre: string; tipo: string };
      pinLugar.current?.remove();
      // un pueblo ya tiene su nombre en el mapa: ahí va solo el punto (si no, se leía dos veces)
      const nombre = r.tipo === "localidad" ? "" : `<span class="pin-lugar-nombre">${r.nombre.replace(/[<>&]/g, "")}</span>`;
      pinLugar.current = L.marker([r.lat, r.lon], {
        interactive: false, keyboard: false, zIndexOffset: 900,
        icon: L.divIcon({ className: "pin-lugar", html: `<span class="pin-lugar-punto"></span>${nombre}`, iconSize: undefined as any }),
      }).addTo(m);
    };
    window.addEventListener("fieldshift:punto", alPunto);
    return () => { window.removeEventListener("fieldshift:punto", alPunto); pinLugar.current?.remove(); };
  }, [mapaListo]);
  useEffect(() => {
    if (campo.contorno) { pinLugar.current?.remove(); pinLugar.current = null; }
  }, [campo.contorno]);

  useEffect(() => {
    if (!centrar || !mapa.current) return;
    // una caja de unos dos "cuadros" del zoom pedido alrededor del punto, encuadrada en lo que se ve
    const lado = (40075000 / 2 ** (centrar.zoom || 14)) * 1.2;
    pedirEncuadre(L.latLng(centrar.lat, centrar.lon).toBounds(lado));
  }, [centrar]); // eslint-disable-line react-hooks/exhaustive-deps

  const alGuardarEsquinas = () => {
    if (capaEditandoRef.current) {
      try {
        const geoJSON = (capaEditandoRef.current as any).toGeoJSON();
        const nuevaGeo = (geoJSON?.geometry || geoJSON) as Geo;
        if (nuevaGeo && areaHa(nuevaGeo) > 0.05) {
          setContorno(nuevaGeo);
          if (campo.secciones.length > 0) {
            const nuevasSecs = campo.secciones
              .map((s) => ({ ...s, geometria: recortarAZonaLibre(s.geometria, nuevaGeo, []) }))
              .filter((s): s is typeof campo.secciones[0] => !!s.geometria);
            setSecciones(nuevasSecs);
          }
          setAviso("Esquinas del campo actualizadas.");
        }
      } catch {}
    }
    setModoMapa("ver");
  };

  // dibujar contorno y secciones
  useEffect(() => {
    const m = mapa.current, g = capas.current;
    if (!m || !g) return;
    g.clearLayers();
    const etiquetas: Etiqueta[] = [];
    if (campo.contorno) {
      if (modoMapa === "editar_contorno") {
        const geoLayer = L.geoJSON(campo.contorno as any, {
          style: { color: "#f2c80f", weight: 3, fill: true, fillColor: "#f2c80f", fillOpacity: 0.15 },
          pmIgnore: false,
        }).addTo(g);
        const subLayers = geoLayer.getLayers();
        const poly = subLayers[0] as L.Polygon;
        if (poly && (poly as any).pm) {
          capaEditandoRef.current = poly;
          (poly as any).pm.enable({
            allowSelfIntersection: false,
            snappable: true,
            snapDistance: 20,
          });
        }
      } else {
        capaEditandoRef.current = null;
        L.geoJSON(campo.contorno as any, { style: { color: "#ffffff", weight: 3, fill: false, dashArray: campo.secciones.length ? "6 6" : undefined }, interactive: false, pmIgnore: false } as any).addTo(g);
        const firma = JSON.stringify(campo.contorno).slice(0, 200);
        if (firma !== ultimoContorno.current) {
          ultimoContorno.current = firma;
          encuadrar(m, campo.contorno);
        }
      }
    }
    // mientras se dibuja un lote nuevo, los que ya están no responden al mouse: sin la etiqueta que seguía al cursor
    // ni el resaltado
    const dibujando = modoMapa === "secciones" || modoMapa === "circulo";
    campo.secciones.forEach((s, i) => {
      const color = COLORES_SECCION[i % COLORES_SECCION.length];
      const capa = L.geoJSON(s.geometria as any, {
        // sobre la imagen de la NASA por fecha, solo el borde: lo que importa es ver qué había adentro
        style: { color: seccionSel === s.id ? "#fff" : color, weight: seccionSel === s.id ? 3 : fondo === "nasa" ? 2.5 : 2, fillColor: color, fillOpacity: fondo === "nasa" ? 0.04 : dibujando ? 0.5 : 0.38 },
        interactive: !dibujando,
        pmIgnore: false,
      } as L.GeoJSONOptions);
      capa.on("click", (e: L.LeafletMouseEvent) => {
        if (useApp.getState().modoMapa !== "ver") return;
        L.DomEvent.stopPropagation(e);
        setSeccionSel(s.id);
      });
      const html = etiquetaHTML(escapar(s.nombre), `${Math.round(s.area_ha || 0)} ha`);
      const [la, lo] = puntoInterior(s.geometria);
      // la etiqueta no es un imán para el dibujo (snapIgnore): si no, el punto se pegaba al centro del lote
      const marcador = L.marker([la, lo], { icon: L.divIcon({ html, className: "etiqueta-div", iconSize: undefined as any }), interactive: false, snapIgnore: true, pmIgnore: true } as L.MarkerOptions).addTo(g);
      etiquetas.push({ marcador, peso: s.area_ha || 0 });
      if (!dibujando) capa.bindTooltip(html, { direction: "top", className: "etiqueta-limpia", sticky: true });
      capa.addTo(g);
    });
    const ordenar = () => desencimar(etiquetas);
    requestAnimationFrame(ordenar);
    m.on("zoomend moveend", ordenar);
    return () => {
      m.off("zoomend moveend", ordenar);
      if (capaEditandoRef.current && (capaEditandoRef.current as any).pm) {
        try { (capaEditandoRef.current as any).pm.disable(); } catch {}
      }
    };
  }, [campo.contorno, campo.secciones, seccionSel, setSeccionSel, fondo, modoMapa]);

  // modos de dibujo con geoman
  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    m.pm.disableDraw();

    // calcular zona libre del campo (contorno menos lotes existentes)
    const zonaLibre =
      campo.contorno && (modoMapa === "secciones" || modoMapa === "circulo")
        ? calcularZonaLibre(campo.contorno, campo.secciones)
        : null;
    const lineasLibre = zonaLibre ? lineasZonaLibre(zonaLibre) : null;

    if ((modoMapa === "secciones" || modoMapa === "circulo") && campo.contorno) {
      if (!zonaLibre || areaHa(zonaLibre) < 0.1) {
        setModoMapa("ver");
        setAviso("El campo ya está completamente cubierto por los lotes.");
        return;
      }
    }

    // sombrear la zona libre disponible para dibujar
    let capaZonaLibre: L.GeoJSON | null = null;
    if ((modoMapa === "secciones" || modoMapa === "circulo") && zonaLibre) {
      capaZonaLibre = L.geoJSON(zonaLibre as any, {
        style: {
          color: "#2e7d32",
          weight: 2,
          dashArray: "6 6",
          fillColor: "#4caf50",
          fillOpacity: 0.16,
        },
        interactive: false,
        pmIgnore: false,
      }).addTo(m);
    }

    // interceptar el marcador y los vértices de Geoman para limitarlos a la zona libre
    const polyDraw = (m.pm.Draw as any).Polygon;
    const circleDraw = (m.pm.Draw as any).Circle;

    let origPolySync: any = null;
    let origPolyVertex: any = null;
    let origCircleSync: any = null;
    let origCircleCenter: any = null;

    const debeLimitar = Boolean(
      (modoMapa === "secciones" || modoMapa === "circulo") && zonaLibre && lineasLibre,
    );

    // el imán de Geoman (bordes, caminos) corre después de limitar: se vuelve a limitar el punto que dejó
    let origPolySnap: any = null;
    let origCircleSnap: any = null;
    const reLimitar = (dibujo: any) => {
      const hint = dibujo?._hintMarker as L.Marker | undefined;
      if (!hint) return;
      const ll = hint.getLatLng();
      const c = limitarALibre(ll, zonaLibre!, lineasLibre!);
      if (!c.equals(ll)) hint.setLatLng(c);
    };
    if (polyDraw && debeLimitar) {
      origPolySnap = polyDraw._handleSnapping;
      polyDraw._handleSnapping = function (e: any) {
        const r = origPolySnap.call(this, e);
        reLimitar(this);
        return r;
      };
    }
    if (circleDraw && debeLimitar) {
      origCircleSnap = circleDraw._handleSnapping;
      circleDraw._handleSnapping = function (e: any) {
        const r = origCircleSnap.call(this, e);
        reLimitar(this);
        return r;
      };
    }

    if (polyDraw && debeLimitar) {
      origPolySync = polyDraw._syncHintMarker;
      origPolyVertex = polyDraw._createVertex;
      polyDraw._syncHintMarker = function (e: any) {
        if (e?.latlng) {
          e = { ...e, latlng: limitarALibre(e.latlng, zonaLibre!, lineasLibre!) };
        }
        return origPolySync.call(this, e);
      };
      polyDraw._createVertex = function (e: any) {
        if (e?.latlng) {
          e = { ...e, latlng: limitarALibre(e.latlng, zonaLibre!, lineasLibre!) };
        }
        return origPolyVertex.call(this, e);
      };
    }

    if (circleDraw && debeLimitar) {
      origCircleSync = circleDraw._syncHintMarker;
      origCircleCenter = circleDraw._placeCenterMarker;
      circleDraw._syncHintMarker = function (e: any) {
        if (e?.latlng) {
          e = { ...e, latlng: limitarALibre(e.latlng, zonaLibre!, lineasLibre!) };
        }
        return origCircleSync.call(this, e);
      };
      circleDraw._placeCenterMarker = function (e: any) {
        if (e?.latlng) {
          e = { ...e, latlng: limitarALibre(e.latlng, zonaLibre!, lineasLibre!) };
        }
        return origCircleCenter.call(this, e);
      };
    }

    m.pm.setGlobalOptions({ snappable: true, snapDistance: 20 });

    const alCrear = (e: any) => {
      let geo: Geo | null = null;
      if (e.shape === "Circle" || typeof e.layer?.getRadius === "function") {
        const c = e.layer.getLatLng();
        const r = e.layer.getRadius();
        geo = circuloGeo(c.lat, c.lng, r);
      } else {
        geo = e.layer.toGeoJSON().geometry as Geo;
      }
      e.layer.remove();
      if (!geo) return;

      if (modoMapa === "contorno") {
        setContorno(geo, { ubicacion: { origen: "dibujo" } } as any);
        setModoMapa("ver");
        void enviar(`Listo, dibujé el contorno del campo en el mapa (${Math.round(areaHa(geo))} ha).`, { accion: true });
      } else if ((modoMapa === "secciones" || modoMapa === "circulo") && campo.contorno) {
        const r = recortarAZonaLibre(geo, campo.contorno, campo.secciones);
        if (r && areaHa(r) > 0.05) {
          const n = campo.secciones.length + 1;
          const prefijo = campo.sistema?.tipo === "ganadero" ? "Potrero" : "Lote";
          const nuevoLote = crearSeccion(r, `${prefijo} ${n}`);
          const nuevasSecciones = [...campo.secciones, nuevoLote];
          setSecciones(nuevasSecciones);

          const origHa = areaHa(geo);
          const finalHa = areaHa(r);
          if (origHa - finalHa > 0.1) {
            let chocabaLotes = false;
            let loteChocado = "";
            for (const s of campo.secciones) {
              try {
                if (booleanIntersects(feature(geo), feature(s.geometria))) {
                  chocabaLotes = true;
                  loteChocado = s.nombre;
                  break;
                }
              } catch {}
            }
            if (chocabaLotes && campo.secciones.length === 1) {
              setAviso(`Lo ajusté al borde del campo y del ${loteChocado || campo.secciones[0].nombre}.`);
            } else if (chocabaLotes) {
              setAviso("Lo ajusté al borde del campo y de los otros lotes.");
            } else {
              setAviso("Lo ajusté al borde del campo.");
            }
          }

          const libre = calcularZonaLibre(campo.contorno, nuevasSecciones);
          const libreHa = libre ? areaHa(libre) : 0;
          if (libreHa < 0.1) {
            m.pm.disableDraw();
            setModoMapa("ver");
            setAviso("El campo quedó completo. Ya podés continuar con los lotes.");
            return;
          }
        } else {
          setAviso("Esa parte ya está ocupada por otro lote o está fuera del campo.");
        }

        const estiloLineas = {
          finishOn: null,
          snappable: true,
          snapDistance: 20,
          templineStyle: { color: "#f2c80f" },
          hintlineStyle: { color: "#f2c80f", dashArray: "5 5" },
        };
        if (modoMapa === "circulo") {
          m.pm.enableDraw("Circle", estiloLineas as any);
        } else {
          m.pm.enableDraw("Polygon", estiloLineas as any);
        }
      }
    };

    // superficie en vivo mientras se marca (para compararla con lo que la persona sabe de su campo)
    const { setMarcando } = useApp.getState();
    let capaTrabajo: any = null;
    const medir = () => {
      if (modoMapa === "circulo") {
        const r = (capaTrabajo as L.Circle)?.getRadius?.() || 0;
        const ha = (Math.PI * r * r) / 10000;
        setMarcando(r > 0 ? { puntos: 2, ha } : { puntos: 1, ha: 0 });
      } else {
        const ll = (capaTrabajo?.getLatLngs?.() || []) as L.LatLng[];
        const pts = ll.map((p) => [p.lng, p.lat]);
        const ha = pts.length >= 3 ? areaHa({ type: "Polygon", coordinates: [[...pts, pts[0]]] } as Geo) : 0;
        setMarcando({ puntos: pts.length, ha });
      }
    };
    const alEmpezar = (e: any) => {
      capaTrabajo = e.workingLayer;
      capaTrabajo?.on("pm:vertexadded pm:vertexremoved", medir);
      if (modoMapa === "circulo") {
        m.on("mousemove", medir);
      }
      setMarcando({ puntos: 0, ha: 0 });
    };
    const borrarUltimo = () => {
      try { (m.pm.Draw as any).Polygon._removeLastVertex(); } catch { /* sin puntos */ }
      medir();
    };

    const alCancelar = () => {
      setModoMapa("ver");
    };

    const alTeclado = (ev: KeyboardEvent) => {
      const tag = (ev.target as HTMLElement)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;

      if (ev.key === "Escape") {
        ev.preventDefault();
        if (modoMapa === "editar_contorno") {
          setModoMapa("ver");
        } else if (modoMapa === "contorno" && !campo.contorno) {
          borrarUltimo();
        } else {
          setModoMapa("ver");
        }
      } else if (ev.key === "Backspace" || (ev.key === "z" && (ev.ctrlKey || ev.metaKey))) {
        ev.preventDefault();
        borrarUltimo();
      }
    };

    if (modoMapa === "contorno" || modoMapa === "secciones" || modoMapa === "circulo" || modoMapa === "editar_contorno") {
      window.addEventListener("keydown", alTeclado);
      window.addEventListener("fieldshift:cancelar-dibujo", alCancelar);
    }

    if (modoMapa === "contorno" || modoMapa === "secciones" || modoMapa === "circulo") {
      m.on("pm:drawstart", alEmpezar);
      m.on("pm:create", alCrear);
      window.addEventListener("fieldshift:borrar-punto", borrarUltimo);

      const estiloLineas = {
        finishOn: null,
        snappable: true,
        snapDistance: 20,
        templineStyle: { color: "#f2c80f" },
        hintlineStyle: { color: "#f2c80f", dashArray: "5 5" },
      };

      if (modoMapa === "circulo") {
        m.pm.enableDraw("Circle", estiloLineas as any);
      } else {
        m.pm.enableDraw("Polygon", estiloLineas as any);
      }
    }

    return () => {
      m.off("pm:create", alCrear);
      m.off("pm:drawstart", alEmpezar);
      if (modoMapa === "circulo") {
        m.off("mousemove", medir);
      }
      capaTrabajo?.off("pm:vertexadded pm:vertexremoved", medir);
      window.removeEventListener("fieldshift:borrar-punto", borrarUltimo);
      window.removeEventListener("fieldshift:cancelar-dibujo", alCancelar);
      window.removeEventListener("keydown", alTeclado);
      setMarcando(null);
      m.pm.disableDraw();
      if (capaZonaLibre) {
        capaZonaLibre.remove();
      }
      if (polyDraw) {
        if (origPolySync) polyDraw._syncHintMarker = origPolySync;
        if (origPolyVertex) polyDraw._createVertex = origPolyVertex;
        if (origPolySnap) polyDraw._handleSnapping = origPolySnap;
      }
      if (circleDraw) {
        if (origCircleSync) circleDraw._syncHintMarker = origCircleSync;
        if (origCircleCenter) circleDraw._placeCenterMarker = origCircleCenter;
        if (origCircleSnap) circleDraw._handleSnapping = origCircleSnap;
      }
    };
  }, [modoMapa, campo.contorno, campo.secciones, campo.sistema?.tipo, setContorno, setSecciones, setModoMapa, enviar]);

  const mostrarUbicar = !campo.contorno || modoMapa === "contorno";

  return (
    <div className="mapa-contenedor">
      <div ref={div} className="mapa" />
      <Lupa mapa={mapaListo} activa={lupaActiva} fondo={fondo} />
      {!campo.contorno && (
        <button
          className="btn chico mapa-btn-gps"
          onClick={alIrADondeEstoy}
          title="Centrar en mi ubicación actual"
          aria-label="Ir a donde estoy"
          disabled={buscandoGPS}
        >
          {buscandoGPS ? (
            <Cargando que="buscando" claro={false} etiqueta="Buscando dónde estás" />
          ) : (
            <>
              <IconoUbicacion />
              <span>Ir a donde estoy</span>
            </>
          )}
        </button>
      )}
      {paisMapa === "US" && !campo.contorno && modoMapa === "ver" && zonaUs.estado && (
        <nav className="mapa-camino" aria-label="Zona elegida">
          <button type="button" onClick={() => { soltarEstadoUs(); window.dispatchEvent(new CustomEvent("fieldshift:estado-us", { detail: "" })); }}>
            <span aria-hidden>←</span> Todos los estados
          </button>
          <span className="mapa-camino-sep" aria-hidden>›</span>
          {zonaUs.condado ? (
            <button type="button" data-no-traducir title="Ver el estado entero"
              onClick={() => { const f = zonaUs.estado!.fips; void elegirEstadoUs(f); window.dispatchEvent(new CustomEvent("fieldshift:estado-us", { detail: f })); }}>
              {zonaUs.estado.nombre}
            </button>
          ) : <b data-no-traducir>{zonaUs.estado.nombre}</b>}
          {zonaUs.condado && <><span className="mapa-camino-sep" aria-hidden>›</span><b data-no-traducir>{zonaUs.condado.nombre}</b></>}
        </nav>
      )}
      {modoMapa === "editar_contorno" && (
        <div
          className="mapa-alerta-edicion"
          style={{
            position: "absolute",
            top: 16,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 1000,
            background: "rgba(23, 27, 33, 0.94)",
            backdropFilter: "blur(8px)",
            color: "#fff",
            padding: "10px 18px",
            borderRadius: "10px",
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontSize: 13,
            border: "1px solid rgba(255,255,255,0.18)",
          }}
        >
          <span>Mové las esquinas del campo arrastrándolas.</span>
          <button className="btn primario chico" onClick={alGuardarEsquinas}>Guardar esquinas</button>
          <button className="btn secundario chico" onClick={() => setModoMapa("ver")}>Cancelar</button>
        </div>
      )}
      {panelLotesOculto && (
        <button
          className="btn chico mapa-btn-ver-lotes"
          onClick={() => setPanelLotesForzado(true)}
          title="Ver lotes y divisiones del campo"
        >
          {`Ver lotes (${campo.secciones.length})`}
        </button>
      )}
      <div className={`mapa-panel ${mostrarUbicar ? "solo-movil" : ""} ${panelLotesOculto ? "escondido" : ""}`} data-tapa-mapa="auto">
        {mostrarUbicar ? (
          <>
            <h3>{modoMapa === "contorno" ? "Dibujá el contorno" : "Ubicá tu campo"}</h3>
            <UbicarCampo alListo={(t) => void enviar(t, { accion: true })} />
            {campo.contorno && <button className="btn texto chico" onClick={() => setModoMapa("ver")}>Cancelar</button>}
          </>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
              <div>
                <h3 style={{ margin: 0 }}>{campo.nombre || "Tu campo"}</h3>
                <small style={{ color: "var(--texto-3)" }}>{`${campo.area_ha?.toLocaleString("es-UY")} ha`}</small>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                {seccionesConfirmadas && (
                  <button
                    className="btn texto chico"
                    onClick={() => setPanelLotesForzado(false)}
                    title="Ocultar panel de lotes"
                  >
                    Ocultar
                  </button>
                )}
                <button
                  className={`btn texto chico ${modoMapa === "editar_contorno" ? "activo" : ""}`}
                  onClick={() => setModoMapa(modoMapa === "editar_contorno" ? "ver" : "editar_contorno")}
                  title="Ajustar esquinas del campo en el mapa"
                >
                  {modoMapa === "editar_contorno" ? "Dejar de ajustar" : "Ajustar esquinas"}
                </button>
                <button
                  className="btn texto chico peligro"
                  onClick={() => setConfirmarBorrarContorno(true)}
                  title="Borrar contorno y empezar de nuevo"
                >
                  Borrar contorno
                </button>
              </div>
            </div>
            <PanelSecciones />
            {/* Fuera «El clima y el suelo de tu zona». El clima y el suelo se siguen pidiendo callados (App.tsx) para que el
                análisis los encuentre ya guardados. */}
            <div className="fila" style={{ marginTop: 8 }}>
              <button
                className="btn texto chico peligro"
                style={{ flex: "0 0 auto" }}
                onClick={() => setConfirmarBorrarContorno(true)}
              >
                Borrar contorno y marcar de nuevo
              </button>
            </div>
          </>
        )}
      </div>
      <SelectorFondo fondo={fondo} conNasa={pasadas.length > 0} alElegir={setFondo} />
      {fondo === "nasa" && pasadas[iPasada] && (
        <div className="mapa-fecha" data-tapa-mapa="der">
          <div className="fila-fecha">
            <button className="btn texto chico" aria-label="Fecha anterior" disabled={iPasada >= pasadas.length - 1} onClick={() => setIPasada(iPasada + 1)}>‹</button>
            <strong>{fechaCorta(pasadas[iPasada].fecha)}</strong>
            <button className="btn texto chico" aria-label="Fecha siguiente" disabled={iPasada === 0} onClick={() => setIPasada(iPasada - 1)}>›</button>
          </div>
          <small>{pasadas[iPasada].satelite} · 30 m por punto. Mové las fechas para ver qué había en cada potrero.</small>
        </div>
      )}
    </div>
  );
}

const NOMBRE_FONDO: Record<Fondo, string> = { satelite: "Satélite", nasa: "NASA, por fecha", calles: "Calles" };

/** El fondo del mapa: un solo botón con el actual y una flecha que abre las otras opciones. Está
 * marcado con data-tapa-mapa: al encuadrar el campo, queda debajo y no le tapa una esquina. */
function SelectorFondo({ fondo, conNasa, alElegir }: { fondo: Fondo; conNasa: boolean; alElegir: (f: Fondo) => void }) {
  const [abierto, setAbierto] = useState(false);
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: PointerEvent) => { if (!caja.current?.contains(e.target as Node)) setAbierto(false); };
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") setAbierto(false); };
    document.addEventListener("pointerdown", fuera);
    document.addEventListener("keydown", tecla);
    return () => { document.removeEventListener("pointerdown", fuera); document.removeEventListener("keydown", tecla); };
  }, [abierto]);
  const opciones = (["satelite", "nasa", "calles"] as Fondo[]).filter((f) => f !== fondo && (f !== "nasa" || conNasa));
  return (
    <div ref={caja} className={`mapa-capas ${abierto ? "abierto" : ""}`} data-tapa-mapa="arriba">
      <button className="chip on selector-fondo" aria-haspopup="menu" aria-expanded={abierto} onClick={() => setAbierto(!abierto)}>
        {NOMBRE_FONDO[fondo]}
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {abierto && (
        <div className="selector-fondo-menu" role="menu">
          {opciones.map((f) => (
            <button key={f} role="menuitem" className="chip" onClick={() => { alElegir(f); setAbierto(false); }}
              title={f === "nasa" ? "Imagen de los satélites Landsat y Sentinel-2 procesada por la NASA (HLS), 30 m, de un día sin nubes" : undefined}>
              {NOMBRE_FONDO[f]}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function titulo(s: string) {
  return s.toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase()).replace(/ Y /g, " y ");
}

export function escapar(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
}
