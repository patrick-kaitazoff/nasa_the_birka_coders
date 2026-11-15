import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { capaFondo, bajarDepartamentos, titulo, type Fondo } from "./MapaCampo";
import { capaRutas, bajarRutas, type Numero } from "./Rutas";
import { bajarLugares, type Lugar } from "./Lugares";
import { capaCaminos } from "./Caminos";
import { useApp } from "../store";

/**
 * Lupa para encontrar el campo:
 * Muestra la foto satelital con +3 niveles de zoom, trazado de rutas con sus números
 * identificadores (sin recalcular marcadores pesados) y nombres de departamento y localidades.
 */
export const AUMENTO = 3; // niveles de zoom de más dentro de la lupa
export const ZOOM_MAX_LUPA = 13.5; // más cerca que esto, la lupa ya no ayuda

/** El mapa de adentro es 3 veces el círculo y se mueve con CSS: antes cada movimiento del mouse hacía un setView, y Leaflet volvía a dibujar todos los caminos del
 * departamento (miles de líneas en SVG) y a pedir teselas. Ahora solo se recentra cuando el cursor se acerca al borde
 * de lo ya cargado, y alrededor ya están las teselas. */
const LADO = 200; // el círculo
const LIENZO = LADO * 3; // el mapa de adentro
const MARGEN = LIENZO / 2 - LADO / 2 - 30; // cuánto se puede correr el cursor antes de recentrar

type DeptoIndex = {
  nombre: string;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  anillos: [number, number][][];
};

function armarIndiceDeptos(fc: any): DeptoIndex[] {
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
      nombre: titulo(f.properties?.nombre || ""),
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

function buscarDepto(deptos: DeptoIndex[], lat: number, lon: number): string | null {
  for (const d of deptos) {
    if (lon < d.minX || lon > d.maxX || lat < d.minY || lat > d.maxY) continue;
    if (d.anillos[0] && puntoEnAnillo(lon, lat, d.anillos[0])) {
      let enHueco = false;
      for (let i = 1; i < d.anillos.length; i++) {
        if (puntoEnAnillo(lon, lat, d.anillos[i])) {
          enHueco = true;
          break;
        }
      }
      if (!enHueco) return d.nombre;
    }
  }
  return null;
}

export function Lupa({ mapa, activa, fondo = "satelite" }: { mapa: L.Map | null; activa: boolean; fondo?: Fondo }) {
  const caja = useRef<HTMLDivElement>(null);
  const interior = useRef<HTMLDivElement>(null);
  const lente = useRef<L.Map | null>(null);
  const capaBase = useRef<L.TileLayer | null>(null);
  const extras = useRef<{ rutas: ReturnType<typeof capaRutas>; caminos: ReturnType<typeof capaCaminos> } | null>(null);
  const lenteDetalle = useRef<L.LayerGroup | null>(null);
  // la posición va directo al estilo (sin render de React en cada movimiento); el estado solo para mostrar y esconder
  const [visible, setVisible] = useState(false);
  const visibleRef = useRef(false);
  const fondoRef = useRef(fondo);
  fondoRef.current = fondo;

  const rutasRef = useRef<Numero[]>([]);
  const lugaresRef = useRef<Lugar[]>([]);
  const deptosRef = useRef<DeptoIndex[]>([]);
  const deptoRef = useRef<string | null>(null);

  useEffect(() => {
    bajarRutas().then((d) => { rutasRef.current = d.numeros || []; }).catch(() => {});
    bajarDepartamentos().then((fc) => { deptosRef.current = armarIndiceDeptos(fc); }).catch(() => {});
  }, []);
  // los pueblos son los del país elegido
  const pais = useApp((s) => s.paisMapa);
  useEffect(() => {
    lugaresRef.current = [];
    bajarLugares(pais).then((d) => { lugaresRef.current = d || []; }).catch(() => {});
  }, [pais]);
  // el estado o el condado que hay bajo el mouse (lo avisa MapaCampo): se lee dentro de la lupa aunque en el mapa su
  // nombre no entre
  const [zona, setZona] = useState<string | null>(null);
  useEffect(() => {
    const alZona = (e: Event) => setZona(((e as CustomEvent).detail as string | null) || null);
    window.addEventListener("fieldshift:zona-mouse", alZona);
    return () => window.removeEventListener("fieldshift:zona-mouse", alZona);
  }, []);
  const rutasUs = useRef<L.TileLayer | null>(null);

  useEffect(() => {
    if (!interior.current || lente.current) return;
    const l = L.map(interior.current, {
      zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false, doubleClickZoom: false,
      boxZoom: false, keyboard: false, touchZoom: false, zoomSnap: 0, fadeAnimation: false, zoomAnimation: false,
      maxZoom: 20,
    }).setView([-32.8, -56], 10);
    const rutas = capaRutas(l, { hastaZoom: 99, conNumeros: false }); // las rutas trazadas adentro de la lupa
    const caminos = capaCaminos(l, { hastaZoom: 99, conAutoDepto: false });
    extras.current = { rutas, caminos };
    lenteDetalle.current = L.layerGroup().addTo(l);
    lente.current = l;
    return () => {
      caminos.destruir();
      l.remove();
      lente.current = null;
      lenteDetalle.current = null;
      capaBase.current = null;
      extras.current = null;
    };
  }, []);

  // el mismo fondo que el mapa: con «Calles», la lupa también muestra calles (antes quedaba siempre en satélite)
  useEffect(() => {
    const l = lente.current;
    if (!l) return;
    capaBase.current?.remove();
    const calles = fondo === "calles";
    const base = capaFondo(calles ? "calles" : "satelite");
    base.options.keepBuffer = 4;
    base.addTo(l).bringToBack();
    capaBase.current = base;
    extras.current?.rutas.mostrar(!calles); // el mapa de calles ya trae sus rutas y caminos
    extras.current?.caminos.mostrar(!calles);
    // en EE. UU., las rutas de Esri encima de la foto, como en el mapa
    rutasUs.current?.remove();
    rutasUs.current = null;
    if (pais === "US" && !calles) {
      rutasUs.current = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
        { maxNativeZoom: 17, maxZoom: 20, keepBuffer: 4 }).addTo(l);
    }
  }, [fondo, pais]);

  useEffect(() => {
    if (!mapa || !activa) {
      visibleRef.current = false;
      setVisible(false);
      return;
    }
    const contenedor = mapa.getContainer();
    let cuadro = 0;
    let centro: L.LatLng | null = null;
    let zoomLente = -1;

    const mostrar = (si: boolean) => {
      if (visibleRef.current === si) return;
      visibleRef.current = si;
      setVisible(si);
    };

    /** Recentra el mapa de adentro (lo único que le cuesta a Leaflet) y pone los nombres de esa zona. */
    const recentrar = (ll: L.LatLng, z: number) => {
      const l = lente.current;
      if (!l) return;
      l.setView(ll, z, { animate: false });
      centro = ll;
      zoomLente = z;
      const radLat = ((LIENZO / 2) * 360) / (256 * 2 ** z);
      const radLon = radLat / (Math.cos((ll.lat * Math.PI) / 180) || 1);
      const cerca = (x: { lat: number; lon: number }) => Math.abs(x.lat - ll.lat) < radLat && Math.abs(x.lon - ll.lng) < radLon;
      const det = lenteDetalle.current;
      if (det) {
        det.clearLayers();
        for (const x of lugaresRef.current.filter(cerca).slice(0, 12)) {
          L.marker([x.lat, x.lon], {
            interactive: false, keyboard: false,
            icon: L.divIcon({ className: `lugar lugar-${x.t}`, html: `<span data-no-traducir>${x.n.replace(/[<>&]/g, "")}</span>`, iconSize: undefined as any }),
          }).addTo(det);
        }
        if (fondoRef.current !== "calles") {
          for (const r of rutasRef.current.filter(cerca).slice(0, 6)) {
            L.marker([r.lat, r.lon], {
              interactive: false, keyboard: false,
              icon: L.divIcon({ className: `ruta-num ruta-${r.clase}`, html: `<span>${r.ruta}</span>`, iconSize: undefined as any }),
            }).addTo(det);
          }
        }
      }
      const depto = buscarDepto(deptosRef.current, ll.lat, ll.lng);
      if (depto && depto !== deptoRef.current) {
        deptoRef.current = depto;
        extras.current?.caminos.cargarDepartamento(depto);
      }
    };

    const mover = (e: L.LeafletMouseEvent) => {
      // sobre un control (zoom, alfiler, etiquetas), la lupa no tiene sentido
      const sobreControl = (e.originalEvent?.target as Element | null)?.closest?.(".leaflet-control");
      if (mapa.getZoom() > ZOOM_MAX_LUPA || sobreControl) {
        mostrar(false);
        return;
      }
      cancelAnimationFrame(cuadro);
      cuadro = requestAnimationFrame(() => {
        const l = lente.current;
        const c = caja.current;
        const adentro = interior.current;
        if (!l || !c || !adentro) return;
        c.style.left = `${e.containerPoint.x}px`;
        c.style.top = `${e.containerPoint.y}px`;
        const z = Math.min(17, mapa.getZoom() + AUMENTO);
        if (!centro || Math.abs(z - zoomLente) > 0.01) recentrar(e.latlng, z);
        let p = l.latLngToContainerPoint(e.latlng);
        if (Math.abs(p.x - LIENZO / 2) > MARGEN || Math.abs(p.y - LIENZO / 2) > MARGEN) {
          recentrar(e.latlng, z);
          p = l.latLngToContainerPoint(e.latlng);
        }
        adentro.style.transform = `translate(${LADO / 2 - p.x}px, ${LADO / 2 - p.y}px)`;
        mostrar(true);
      });
    };
    const salir = () => {
      cancelAnimationFrame(cuadro);
      mostrar(false);
    };
    mapa.on("mousemove", mover);
    mapa.on("mouseout zoomstart movestart", salir);
    // el «mouseout» de Leaflet a veces no llega si el mouse sale rápido hacia el panel o el chat: el del contenedor sí
    contenedor.addEventListener("mouseleave", salir);
    window.addEventListener("blur", salir);
    return () => {
      cancelAnimationFrame(cuadro);
      mapa.off("mousemove", mover);
      mapa.off("mouseout zoomstart movestart", salir);
      contenedor.removeEventListener("mouseleave", salir);
      window.removeEventListener("blur", salir);
    };
  }, [mapa, activa]);

  return (
    <div ref={caja} className={`lupa ${visible ? "visible" : ""}`} aria-hidden>
      <div ref={interior} className="lupa-mapa" style={{ width: LIENZO, height: LIENZO }} />
      {zona && pais === "US" && <span className="lupa-zona" data-no-traducir>{zona}</span>}
      <span className="lupa-texto">Clic para acercar</span>
    </div>
  );
}
