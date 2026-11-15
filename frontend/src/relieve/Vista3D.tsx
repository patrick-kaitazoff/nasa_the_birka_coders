/** Visor 3D del campo: el relieve real (NASA SRTM, 30 m) como una maqueta, con capas de lo que calcula la
 * app encima: el plan de cultivos temporada por temporada, la erosión cuadrado por cuadrado (hoy y con el
 * plan) contra la tolerancia del suelo, la pendiente y la foto satelital (Esri o NASA HLS). Al pasar el
 * mouse muestra los números de ese punto. La altura va exagerada (se puede cambiar) para que se lea el
 * relieve: un campo uruguayo tiene decenas de metros de desnivel en kilómetros.
 *
 * Todo sale de /api/relieve (analisis/relieve.py) y del análisis: acá solo se dibuja. */
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { api } from "../api";
import { nombreCultivo, useApp } from "../store";
import type { Geo } from "../tipos";
import { pedirFoto, urlFotoEsri, useRelieve, type Relieve } from "./useRelieve";
import { Cargando } from "../comun/Cargando";
import { FilaSugerencias } from "../chat/FilaSugerencias";

type Capa = "satelite" | "nasa" | "plan" | "erosion_actual" | "erosion_plan" | "agua" | "pendiente";
const CAPAS: Array<{ id: Capa; t: string }> = [
  { id: "plan", t: "Plan de cultivos" },
  { id: "erosion_actual", t: "Erosión hoy" },
  { id: "erosion_plan", t: "Erosión con el plan" },
  { id: "agua", t: "Agua" },
  { id: "pendiente", t: "Pendiente" },
  { id: "satelite", t: "Foto satelital" },
  { id: "nasa", t: "Imagen NASA (HLS)" },
];
// el mapa 2D del Plan ya es la foto satelital: en el recuadro chico el 3D muestra solo lo que explica el plan
const ES_FOTO = (c: Capa) => c === "satelite" || c === "nasa";

// ---------------------------------------------------------------- colores
type RGB = [number, number, number];
const hex = (h: string): RGB => { const n = parseInt(h.replace("#", ""), 16); return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]; };
const mezclar = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
function rampa(paradas: Array<[number, string]>, v: number): RGB {
  if (v <= paradas[0][0]) return hex(paradas[0][1]);
  for (let i = 1; i < paradas.length; i++) {
    if (v <= paradas[i][0]) {
      const [a, ca] = paradas[i - 1], [b, cb] = paradas[i];
      return mezclar(hex(ca), hex(cb), (v - a) / (b - a));
    }
  }
  return hex(paradas[paradas.length - 1][1]);
}
// erosión / tolerancia: verde (aguanta) → amarillo (en el límite) → rojo (se lava)
const RAMPA_EROSION: Array<[number, string]> = [[0, "#2f7d4f"], [0.6, "#8fbf6a"], [1, "#f2c14e"], [2, "#e07b39"], [4, "#a8321f"]];
const RAMPA_PENDIENTE: Array<[number, string]> = [[0, "#f4efe1"], [2, "#d7e3b5"], [4, "#a9c97e"], [7, "#e3a857"], [12, "#b0541f"], [20, "#6b2410"]];
const FUERA_BAJO = hex("#9aa58a"), FUERA_ALTO = hex("#d8cfb9");

// ---------------------------------------------------------------- geometría
interface Malla {
  W: number; D: number; px: number; filas: number; cols: number;
  aXZ: (lon: number, lat: number) => [number, number];
  alturaEn: (x: number, z: number) => number;
}

function prepararMalla(r: Relieve, exag: number): Malla {
  const { filas, cols, elev } = r.grilla;
  const px = r.px_m, W = (cols - 1) * px, D = (filas - 1) * px;
  const { oeste, este, norte, sur } = r.bordes;
  const aXZ = (lon: number, lat: number): [number, number] => [((lon - oeste) / (este - oeste)) * W - W / 2, ((norte - lat) / (norte - sur)) * D - D / 2];
  const alturaEn = (x: number, z: number) => {
    const j = Math.max(0, Math.min(cols - 1.001, (x + W / 2) / px)), i = Math.max(0, Math.min(filas - 1.001, (z + D / 2) / px));
    const j0 = Math.floor(j), i0 = Math.floor(i), fj = j - j0, fi = i - i0;
    const e = (a: number, b: number) => (elev[a][b] - r.elev_min) * exag;
    return e(i0, j0) * (1 - fi) * (1 - fj) + e(i0, j0 + 1) * (1 - fi) * fj + e(i0 + 1, j0) * fi * (1 - fj) + e(i0 + 1, j0 + 1) * fi * fj;
  };
  return { W, D, px, filas, cols, aXZ, alturaEn };
}

function anillos(g: Geo | undefined): number[][][] {
  if (!g) return [];
  const geo = g as { type: string; coordinates: unknown };
  if (geo.type === "Polygon") return [(geo.coordinates as number[][][])[0]];
  if (geo.type === "MultiPolygon") return (geo.coordinates as number[][][][]).map((p) => p[0]);
  return [];
}

/** Celda de la sección k más lejos de cualquier celda que no sea de k (distancia por pasos, BFS). */
function puntoInterior(seccion: number[][], k: number): [number, number] {
  const filas = seccion.length, cols = seccion[0]?.length || 0;
  const dist = new Int32Array(filas * cols).fill(-1);
  const cola: number[] = [];
  for (let i = 0; i < filas; i++) for (let j = 0; j < cols; j++) {
    if (seccion[i][j] !== k || i === 0 || j === 0 || i === filas - 1 || j === cols - 1) { dist[i * cols + j] = 0; cola.push(i * cols + j); }
  }
  let mejor = -1, valor = 0;
  for (let q = 0; q < cola.length; q++) {
    const c = cola[q], i = Math.floor(c / cols), j = c % cols;
    for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const a = i + di, b = j + dj;
      if (a < 0 || b < 0 || a >= filas || b >= cols || dist[a * cols + b] >= 0) continue;
      dist[a * cols + b] = dist[c] + 1;
      if (dist[c] + 1 > valor) { valor = dist[c] + 1; mejor = a * cols + b; }
      cola.push(a * cols + b);
    }
  }
  return mejor < 0 ? [-1, -1] : [Math.floor(mejor / cols), mejor % cols];
}

// ---------------------------------------------------------------- componente
interface Punto { seccion: string | null; elev: number; pendiente: number; ea: number | null; ep: number | null; t: number | null; cultivo: string | null }

function ajustarEncuadre(
  el: HTMLElement,
  camara: THREE.PerspectiveCamera,
  controles: OrbitControls,
  relieve: Relieve,
  exag: number,
  moverCamara: boolean,
  interactuo = false
) {
  const w = el.clientWidth;
  const h = el.clientHeight;
  if (!w || !h) return;

  const panel = el.parentElement?.querySelector(".vista3d-panel") as HTMLElement | null;
  const esMovil = window.innerWidth <= 768 || w <= 640;

  let dx = 0;
  let dy = 0;
  let wVis = w;
  let hVis = h;

  if (esMovil) {
    const panelH = panel ? Math.min(h * 0.5, panel.offsetHeight + 14) : 180;
    wVis = Math.max(100, w - 24);
    hVis = Math.max(100, h - panelH - 24);
    const cy = (h - panelH) / 2;
    dy = cy - h / 2;
  } else {
    const panelW = panel ? Math.min(w * 0.45, panel.offsetWidth + 28) : 328;
    wVis = Math.max(100, w - panelW - 24);
    hVis = Math.max(100, h - 24);
    const cx = panelW + wVis / 2;
    dx = cx - w / 2;
  }

  camara.aspect = w / h;
  camara.setViewOffset(w, h, -dx, -dy, w, h);
  camara.updateProjectionMatrix();

  const { filas, cols } = relieve.grilla;
  const W = (cols - 1) * relieve.px_m;
  const D = (filas - 1) * relieve.px_m;

  // Alturas del bloque para encuadre
  const exagFraming = Math.max(exag, 3);
  const elevH = (relieve.elev_max - relieve.elev_min) * exagFraming;
  const yTop = elevH + 35 * Math.sqrt(exagFraming);
  const yBase = -Math.max(25, (relieve.elev_max - relieve.elev_min) * 0.5) * exagFraming;

  // Se encuadra el campo, no el bloque entero de terreno, que trae un margen alrededor y dejaba los
  // lotes chicos en el medio. La cámara gira alrededor del centro del campo; los bordes del bloque pueden quedar fuera.
  // Puntos del borde del campo: en cada fila de la grilla, la primera y la última celda de adentro.
  const { dentro, elev } = relieve.grilla;
  const borde: Array<[number, number]> = [];
  const paso = Math.max(1, Math.floor(filas / 60));
  for (let i = 0; i < filas; i += paso) {
    const fila = dentro[i] || [];
    const j0 = fila.findIndex(Boolean);
    if (j0 < 0) continue;
    let j1 = fila.length - 1;
    while (j1 > j0 && !fila[j1]) j1--;
    borde.push([i, j0], [i, j1]);
  }
  let pts: THREE.Vector3[];
  const centro = new THREE.Vector3(0, 0, 0);
  if (borde.length >= 4) {
    const xs = borde.map(([, j]) => j * relieve.px_m - W / 2), zs = borde.map(([i]) => i * relieve.px_m - D / 2);
    const altos = borde.map(([i, j]) => (elev[i][j] - relieve.elev_min) * exag);
    centro.set((Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...altos) + Math.max(...altos)) / 2, (Math.min(...zs) + Math.max(...zs)) / 2);
    pts = borde.flatMap((_, k) => [new THREE.Vector3(xs[k], altos[k] + 8, zs[k]), new THREE.Vector3(xs[k], altos[k] - 8, zs[k])]);
  } else {
    pts = [
      new THREE.Vector3(-W / 2, yBase, -D / 2), new THREE.Vector3(W / 2, yBase, -D / 2),
      new THREE.Vector3(W / 2, yBase, D / 2), new THREE.Vector3(-W / 2, yBase, D / 2),
      new THREE.Vector3(-W / 2, yTop, -D / 2), new THREE.Vector3(W / 2, yTop, -D / 2),
      new THREE.Vector3(W / 2, yTop, D / 2), new THREE.Vector3(-W / 2, yTop, D / 2),
    ];
  }

  // Dirección inicial de la cámara: elevación ~32°
  const dir = new THREE.Vector3(0.2, 0.78, 1.22).normalize();
  const sinPhi = dir.y;
  const cosPhi = Math.hypot(dir.x, dir.z);

  // Muestrear ángulos de giro cada 15° para que nunca se corte al rotar 360°
  const angulos: number[] = [];
  for (let a = 0; a < 360; a += 15) {
    angulos.push((a * Math.PI) / 180);
  }

  // Búsqueda binaria para que el campo llene el lado que más aprieta en el ángulo de giro más ancho. Era 85 %: como
  // se toma el peor ángulo de la vuelta entera, en los demás quedaba bastante más chico. El espacio visible ya descuenta 24 px de margen.
  const OBJETIVO_OCUPACION = 1;

  function calcularOcupacion(dist: number): number {
    let maxOcupacion = 0;
    for (const theta of angulos) {
      camara.position.set(
        centro.x + dist * cosPhi * Math.sin(theta),
        centro.y + dist * sinPhi,
        centro.z + dist * cosPhi * Math.cos(theta)
      );
      camara.lookAt(centro);
      camara.updateMatrixWorld();

      let minX = Infinity, maxX = -Infinity;
      let minY = Infinity, maxY = -Infinity;

      for (let i = 0; i < pts.length; i++) {
        const p = pts[i].clone().project(camara);
        const sx = ((p.x + 1) / 2) * w;
        const sy = ((1 - p.y) / 2) * h;
        if (sx < minX) minX = sx;
        if (sx > maxX) maxX = sx;
        if (sy < minY) minY = sy;
        if (sy > maxY) maxY = sy;
      }

      const boxW = maxX - minX;
      const boxH = maxY - minY;
      const frac = Math.max(boxW / wVis, boxH / hVis);
      if (frac > maxOcupacion) maxOcupacion = frac;
    }
    return maxOcupacion;
  }

  // la búsqueda mueve la cámara para probar cada ángulo: se guarda dónde estaba y se la devuelve. Sin esto, si la
  // persona ya la había movido, cualquier cambio de tamaño del recuadro la dejaba mirando desde otro lado
  const posAntes = camara.position.clone(), giroAntes = camara.quaternion.clone();
  let dMin = 50;
  let dMax = 50000;
  for (let iter = 0; iter < 24; iter++) {
    const dMid = (dMin + dMax) / 2;
    const ocupacion = calcularOcupacion(dMid);
    if (ocupacion > OBJETIVO_OCUPACION) {
      dMin = dMid;
    } else {
      dMax = dMid;
    }
  }

  const distancia = (dMin + dMax) / 2;
  camara.position.copy(posAntes);
  camara.quaternion.copy(giroAntes);
  camara.updateMatrixWorld();

  controles.minDistance = Math.max(10, distancia * 0.15);
  controles.maxDistance = distancia * 3.5;

  if (moverCamara) {
    camara.position.copy(dir.multiplyScalar(distancia).add(centro));
    controles.target.copy(centro);
    controles.update();
  } else if (!interactuo) {
    const dirActual = camara.position.clone().sub(controles.target).normalize();
    if (dirActual.lengthSq() > 0.001) {
      camara.position.copy(dirActual.multiplyScalar(distancia).add(controles.target));
      controles.update();
    }
  }
}

/** Vive dentro del mapa del Plan (botón 2D / 3D), no como parte aparte. La temporada la manda la
 * línea de temporadas del Plan, así que acá no hay barrita ni ▶. Chica (en el recuadro del mapa): solo las capas y su leyenda. Grande (pantalla completa): todo.
 */
export function Vista3D({ grande = true }: { grande?: boolean }) {
  const { relieve, error, cargando } = useRelieve();
  const { plan, catalogo, temporada, campo } = useApp();
  const [capa, setCapa] = useState<Capa>("plan");
  const [exag, setExag] = useState(3);
  const [giro, setGiro] = useState(true);
  const [punto, setPunto] = useState<Punto | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const caja = useRef<HTMLDivElement>(null);
  const usuarioInteractuo = useRef(false);
  const motor = useRef<{
    renderer: THREE.WebGLRenderer; etiquetas: CSS2DRenderer; escena: THREE.Scene; camara: THREE.PerspectiveCamera;
    controles: OrbitControls; terreno: THREE.Mesh; faldon: THREE.Mesh; bordes: THREE.Group; rotulos: CSS2DObject[];
    /** algo cambió (textura, altura, tamaño) y hay que dibujar aunque la cámara esté quieta */
    sucio: boolean;
  } | null>(null);

  // cultivo de cada sección en la temporada elegida (para la capa del plan y los rótulos)
  const cultivoSeccion = useMemo(() => {
    const m = new Map<string, string>();
    plan?.secciones.forEach((s) => { const c = s.cultivos[temporada]; if (c) m.set(s.seccion_id, c); });
    return m;
  }, [plan, temporada]);

  // ------------------------------------------------ armar la escena (una vez por relieve)
  useEffect(() => {
    const el = caja.current;
    if (!el || !relieve) return;
    const ancho = el.clientWidth, alto = el.clientHeight;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(ancho, alto);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // el sol y el terreno no se mueven: la sombra se calcula cuando cambia la altura, no en cada cuadro
    renderer.shadowMap.autoUpdate = false;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const etiquetas = new CSS2DRenderer();
    etiquetas.setSize(ancho, alto);
    etiquetas.domElement.className = "vista3d-rotulos";
    el.appendChild(etiquetas.domElement);

    const escena = new THREE.Scene();
    const { filas, cols } = relieve.grilla;
    const W = (cols - 1) * relieve.px_m, D = (filas - 1) * relieve.px_m;
    const L = Math.max(W, D);
    const camara = new THREE.PerspectiveCamera(38, ancho / alto, L / 200, L * 20);
    const controles = new OrbitControls(camara, renderer.domElement);
    controles.enableDamping = true;
    controles.maxPolarAngle = Math.PI * 0.47;
    controles.autoRotateSpeed = 0.35;
    controles.addEventListener("start", () => { usuarioInteractuo.current = true; });
    ajustarEncuadre(el, camara, controles, relieve, exag, true);

    escena.add(new THREE.HemisphereLight(0xfdf8ec, 0x5b6b4a, 1.5));
    const sol = new THREE.DirectionalLight(0xfff2d6, 2.4);
    sol.position.set(-L * 0.6, L * 0.8, -L * 0.35);
    sol.castShadow = true;
    sol.shadow.mapSize.set(2048, 2048);
    Object.assign(sol.shadow.camera, { left: -L, right: L, top: L, bottom: -L, near: 1, far: L * 4 });
    sol.shadow.bias = -0.0005;
    escena.add(sol);

    // terreno: una grilla con un vértice por cuadrado
    const pos = new Float32Array(filas * cols * 3), uv = new Float32Array(filas * cols * 2);
    for (let i = 0; i < filas; i++) for (let j = 0; j < cols; j++) {
      const k = i * cols + j;
      pos[k * 3] = j * relieve.px_m - W / 2; pos[k * 3 + 2] = i * relieve.px_m - D / 2;
      uv[k * 2] = j / (cols - 1); uv[k * 2 + 1] = 1 - i / (filas - 1);
    }
    const idx: number[] = [];
    for (let i = 0; i < filas - 1; i++) for (let j = 0; j < cols - 1; j++) {
      const a = i * cols + j, b = a + 1, c = a + cols, d = c + 1;
      idx.push(a, c, b, b, c, d);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
    geo.setIndex(idx);
    const terreno = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ roughness: 0.92, metalness: 0 }));
    terreno.castShadow = true;
    terreno.receiveShadow = true;
    // escondido hasta tener su primera textura: sin ella se vería blanco un cuadro
    terreno.visible = false;
    escena.add(terreno);

    // faldón: los costados de la maqueta, como un corte del suelo
    const borde: Array<[number, number]> = [];
    for (let j = 0; j < cols; j++) borde.push([0, j]);
    for (let i = 1; i < filas; i++) borde.push([i, cols - 1]);
    for (let j = cols - 2; j >= 0; j--) borde.push([filas - 1, j]);
    for (let i = filas - 2; i > 0; i--) borde.push([i, 0]);
    borde.push([0, 0]);
    const fPos = new Float32Array(borde.length * 2 * 3), fCol = new Float32Array(borde.length * 2 * 3);
    const arriba = hex("#6e4b2f"), abajo = hex("#2f2118");
    borde.forEach(([i, j], n) => {
      const x = j * relieve.px_m - W / 2, z = i * relieve.px_m - D / 2;
      fPos.set([x, 0, z, x, 0, z], n * 6);
      fCol.set([...arriba, ...abajo], n * 6);
    });
    const fIdx: number[] = [];
    for (let n = 0; n < borde.length - 1; n++) { const a = n * 2; fIdx.push(a, a + 1, a + 2, a + 2, a + 1, a + 3); }
    const fGeo = new THREE.BufferGeometry();
    fGeo.setAttribute("position", new THREE.BufferAttribute(fPos, 3));
    fGeo.setAttribute("color", new THREE.BufferAttribute(fCol, 3));
    fGeo.setIndex(fIdx);
    const faldon = new THREE.Mesh(fGeo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, side: THREE.DoubleSide }));
    escena.add(faldon);

    const bordes = new THREE.Group();
    escena.add(bordes);
    motor.current = { renderer, etiquetas, escena, camara, controles, terreno, faldon, bordes, rotulos: [], sucio: true };
    if (import.meta.env.DEV) (window as any).__motor3d = motor.current;

    const ro = new ResizeObserver(() => {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h); etiquetas.setSize(w, h);
      ajustarEncuadre(el, camara, controles, relieve, exag, false, usuarioInteractuo.current);
      if (motor.current) motor.current.sucio = true;
    });
    ro.observe(el);
    let vivo = true;
    // Antes se dibujaba 60 veces por segundo siempre, también con la maqueta quieta o fuera de la
    // pantalla (al bajar por el Plan). Ahora solo se dibuja si la cámara se movió (gira sola o la mueve la persona) o
    // si algo cambió, y nada mientras no se ve.
    let aLaVista = true;
    const io = new IntersectionObserver((es) => { aLaVista = es[es.length - 1].isIntersecting; if (aLaVista && motor.current) motor.current.sucio = true; });
    io.observe(el);
    // Con la maqueta chica los seis rótulos quedaban uno encima del
    // otro, ilegibles. Cada pocos cuadros se esconde el que choca con uno ya puesto; primero van las secciones grandes,
    // así el orden no cambia al girar y no titilan.
    const ha = new Map(relieve.secciones.map((s) => [s.id, s.ha]));
    let n = 0;
    const despejarRotulos = () => {
      const els = (motor.current?.rotulos || []).map((r) => r.element).filter((e) => e.style.display !== "none");
      els.sort((a, b) => (ha.get(b.dataset.seccion || "") || 0) - (ha.get(a.dataset.seccion || "") || 0));
      const puestos: DOMRect[] = [];
      for (const e of els) {
        const r = e.getBoundingClientRect();
        const choca = puestos.some((p) => r.left < p.right + 4 && r.right > p.left - 4 && r.top < p.bottom + 2 && r.bottom > p.top - 2);
        e.classList.toggle("tapado", choca);
        if (!choca) puestos.push(r);
      }
    };
    const cuadro = () => {
      if (!vivo) return;
      requestAnimationFrame(cuadro);
      if (!aLaVista) return;
      const m = motor.current;
      const seMovio = controles.update();
      const cambio = !!m?.sucio;
      if (!seMovio && !cambio) return;
      if (m) m.sucio = false;
      renderer.render(escena, camara);
      etiquetas.render(escena, camara);
      if (cambio || n++ % 6 === 0) despejarRotulos();
    };
    cuadro();
    return () => {
      vivo = false; ro.disconnect(); io.disconnect(); controles.dispose(); renderer.dispose();
      geo.dispose(); fGeo.dispose(); ((terreno.material as THREE.MeshStandardMaterial).map)?.dispose();
      el.removeChild(renderer.domElement); el.removeChild(etiquetas.domElement);
      motor.current = null;
    };
  }, [relieve]);

  // ------------------------------------------------ altura (exageración), bordes y rótulos
  useEffect(() => {
    const m = motor.current;
    if (!m || !relieve) return;
    const malla = prepararMalla(relieve, exag);
    const { filas, cols, elev } = relieve.grilla;
    const pos = m.terreno.geometry.getAttribute("position") as THREE.BufferAttribute;
    for (let i = 0; i < filas; i++) for (let j = 0; j < cols; j++) pos.setY(i * cols + j, (elev[i][j] - relieve.elev_min) * exag);
    pos.needsUpdate = true;
    m.terreno.geometry.computeVertexNormals();
    m.terreno.geometry.computeBoundingSphere();
    m.renderer.shadowMap.needsUpdate = true;
    m.sucio = true;
    // faldón: de la superficie hasta la base
    const base = -Math.max(25, (relieve.elev_max - relieve.elev_min) * 0.5) * exag;
    const fp = m.faldon.geometry.getAttribute("position") as THREE.BufferAttribute;
    for (let n = 0; n < fp.count; n += 2) {
      const x = fp.getX(n), z = fp.getZ(n);
      fp.setY(n, malla.alturaEn(x, z)); fp.setY(n + 1, base);
    }
    fp.needsUpdate = true;
    m.faldon.geometry.computeVertexNormals();

    // bordes del campo y de las secciones, apoyados sobre el terreno
    m.bordes.children.forEach((c) => (c as THREE.Line).geometry.dispose());
    m.bordes.clear();
    const linea = (g: Geo | undefined, color: number, ancho: number) => {
      for (const anillo of anillos(g)) {
        const pts: THREE.Vector3[] = [];
        for (let n = 0; n < anillo.length - 1; n++) {
          const [x0, z0] = malla.aXZ(anillo[n][0], anillo[n][1]), [x1, z1] = malla.aXZ(anillo[n + 1][0], anillo[n + 1][1]);
          const pasos = Math.max(1, Math.ceil(Math.hypot(x1 - x0, z1 - z0) / (malla.px / 2)));
          for (let s = 0; s < pasos; s++) {
            const x = x0 + ((x1 - x0) * s) / pasos, z = z0 + ((z1 - z0) * s) / pasos;
            pts.push(new THREE.Vector3(x, malla.alturaEn(x, z) + 3 + ancho, z));
          }
        }
        if (pts.length) pts.push(pts[0].clone());
        const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.95 }));
        m.bordes.add(l);
      }
    };
    campo.secciones.forEach((s) => linea(s.geometria, 0xfffbef, 0));
    linea(campo.contorno, 0xffffff, 2);

    // rótulos: uno por sección, en el punto más adentro de ella (el más lejos de sus bordes)
    m.rotulos.forEach((r) => { r.removeFromParent(); r.element.remove(); });
    m.rotulos = [];
    relieve.secciones.forEach((s, k) => {
      const [i0, j0] = puntoInterior(relieve.grilla.seccion, k);
      if (i0 < 0) return;
      const x = j0 * malla.px - malla.W / 2, z = i0 * malla.px - malla.D / 2;
      const div = document.createElement("div");
      div.className = "rotulo3d";
      div.dataset.seccion = s.id;
      const o = new CSS2DObject(div);
      o.position.set(x, malla.alturaEn(x, z) + 30 * Math.sqrt(exag), z);
      m.escena.add(o);
      m.rotulos.push(o);
    });
  }, [relieve, exag, campo.secciones, campo.contorno]);

  // ------------------------------------------------ imágenes satelitales: Esri de fondo siempre, HLS al elegirla
  const [imagenes, setImagenes] = useState<Partial<Record<"satelite" | "nasa", HTMLImageElement>>>({});
  // en los ejemplos la foto está en el proyecto y llega enseguida: el terreno se pinta recién con ella, en vez de
  // pintarse primero en verde y volver a armar la textura unos cuadros después. Si falla o tarda más de
  // 1,2 s, se pinta sin ella como siempre.
  const [sinFoto, setSinFoto] = useState(false);
  useEffect(() => {
    // También en un campo nuevo. En el de Iowa el terreno salió beige y la foto entró unos segundos
    // después; ahora se la espera un poco más (1,8 s: la pide a Esri en el momento) antes de pintar sin ella
    if (!relieve || imagenes.satelite) return;
    const r = setTimeout(() => setSinFoto(true), relieve.foto ? 1200 : 1800);
    return () => clearTimeout(r);
  }, [relieve, imagenes.satelite]);
  const pedidas = useRef(new Set<string>());
  useEffect(() => {
    if (!relieve) return;
    const { oeste, este, norte, sur } = relieve.bordes;
    const asp = relieve.grilla.cols / relieve.grilla.filas;
    const w = asp >= 1 ? 2048 : Math.round(2048 * asp), h = asp >= 1 ? Math.round(2048 / asp) : 2048; // HLS (GIBS)
    const cargar = (url: string, clave: "satelite" | "nasa", reintento?: string) => {
      // la misma imagen que se pidió al abrir el ejemplo o al precargar el relieve: si ya llegó, se usa en el acto
      const img = pedirFoto(url);
      const lista = () => setImagenes((x) => ({ ...x, [clave]: img }));
      // si Esri no tiene esa resolución en la zona contesta 500: se prueba una vez con la mitad
      const fallo = () => {
        if (clave === "satelite") setSinFoto(true);
        if (reintento) cargar(reintento, clave);
        else setAviso(clave === "nasa" ? "No pude traer la imagen de la NASA (HLS)." : "No pude traer la foto satelital.");
      };
      if (img.complete) { if (img.naturalWidth) lista(); else fallo(); return; }
      img.addEventListener("load", lista, { once: true });
      img.addEventListener("error", fallo, { once: true });
    };
    if (!pedidas.current.has("satelite")) {
      pedidas.current.add("satelite");
      cargar(urlFotoEsri(relieve), "satelite", urlFotoEsri(relieve, 0.5));
    }
    if (capa === "nasa" && !pedidas.current.has("nasa")) {
      pedidas.current.add("nasa");
      api.hls(oeste, sur, este, norte).then((r) => {
        const p = r.fechas?.[0];
        if (!p) { setAviso("No encontré una fecha sin nubes de HLS para este campo."); return; }
        cargar(`https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=${p.capa}&STYLES=&FORMAT=image/jpeg&CRS=EPSG:4326&BBOX=${sur},${oeste},${norte},${este}&WIDTH=${w}&HEIGHT=${h}&TIME=${p.fecha}`, "nasa");
      }).catch(() => setAviso("No pude consultar las fechas de HLS."));
    }
  }, [relieve, capa]);

  // ------------------------------------------------ pintar la capa: foto de fondo y los datos encima, dentro del campo
  useEffect(() => {
    const m = motor.current;
    if (!m || !relieve) return;
    if (!imagenes.satelite && !sinFoto) return; // la foto está por llegar
    const mat = m.terreno.material as THREE.MeshStandardMaterial;
    const g = relieve.grilla;
    const esFoto = capa === "satelite" || capa === "nasa";
    const base = capa === "nasa" ? imagenes.nasa || imagenes.satelite : imagenes.satelite;
    const colorCultivo = (cod: string | undefined) => hex(catalogo?.cultivos.find((c) => c.codigo === cod)?.color || "#cfc6b0");
    // los datos, un píxel por cuadrado de la grilla
    const chico = document.createElement("canvas");
    chico.width = g.cols; chico.height = g.filas;
    const cx = chico.getContext("2d")!;
    const img = cx.createImageData(g.cols, g.filas);
    for (let i = 0; i < g.filas; i++) for (let j = 0; j < g.cols; j++) {
      const k = (i * g.cols + j) * 4;
      const fuera = !g.dentro[i][j] || g.seccion[i][j] < 0;
      let c: RGB | null = null;
      if (fuera || esFoto) {
        if (!base) c = mezclar(FUERA_BAJO, FUERA_ALTO, (g.elev[i][j] - relieve.elev_min) / Math.max(1, relieve.elev_max - relieve.elev_min));
      } else if (capa === "plan") c = colorCultivo(cultivoSeccion.get(relieve.secciones[g.seccion[i][j]]?.id));
      else if (capa === "pendiente") c = rampa(RAMPA_PENDIENTE, g.pendiente[i][j]);
      else if (capa === "agua") {
        const cl = g.agua ? g.agua[i][j] : 0;
        c = cl === 2 ? hex("#08519c") : cl === 1 ? hex("#6baed6") : hex("#eae4d3");
      } else {
        const a = capa === "erosion_actual" ? g.erosion_actual[i][j] : g.erosion_plan[i][j];
        const tol = g.tolerancia[i][j];
        c = a == null || !tol ? hex("#cfc6b0") : rampa(RAMPA_EROSION, a / tol);
      }
      if (c) img.data.set([c[0] * 255, c[1] * 255, c[2] * 255, fuera || esFoto ? 255 : 236], k);
    }
    cx.putImageData(img, 0, 0);
    const W = base ? base.naturalWidth : g.cols * 8, H = base ? base.naturalHeight : g.filas * 8;
    const lienzo = document.createElement("canvas");
    lienzo.width = W; lienzo.height = H;
    const ctx = lienzo.getContext("2d")!;
    if (base) ctx.drawImage(base, 0, 0, W, H);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(chico, 0, 0, W, H);
    const tex = new THREE.CanvasTexture(lienzo);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = m.renderer.capabilities.getMaxAnisotropy();
    const vieja = mat.map;
    mat.map = tex;
    mat.vertexColors = false;
    mat.needsUpdate = true;
    vieja?.dispose();
    m.terreno.visible = true;
    m.sucio = true;
    // si la portada está armando la página por adelantado, se dibuja un cuadro ya: compilar los shaders y subir la
    // textura a la placa lleva ~0,5 s, y si quedaba para el primer cuadro al mostrarse, el clic parecía no responder
    if ((document as Document & { prerendering?: boolean }).prerendering) m.renderer.render(m.escena, m.camara);
    // rótulos
    m.rotulos.forEach((r) => {
      const s = relieve.secciones.find((x) => x.id === r.element.dataset.seccion);
      if (!s) return;
      let sub = "";
      if (capa === "plan") sub = nombreCultivo(catalogo, cultivoSeccion.get(s.id) || "", true);
      else if (capa === "erosion_actual" && s.erosion_actual) sub = `${s.erosion_actual.pct_supera_t} % supera la tolerancia`;
      else if (capa === "erosion_plan" && s.erosion_plan) sub = `${s.erosion_plan.pct_supera_t} % supera la tolerancia`;
      else if (capa === "pendiente") sub = `pendiente media ${s.pendiente_media.toLocaleString("es-UY")} %`;
      else if (capa === "agua") {
        const v = s.ha_via_agua ?? 0;
        const b = s.ha_bajos ?? 0;
        sub = v > 0
          ? `${v.toLocaleString("es-UY", { maximumFractionDigits: 1 })} ha en vías de agua`
          : b > 0
          ? `${b.toLocaleString("es-UY", { maximumFractionDigits: 1 })} ha en bajos`
          : "sin vías de agua";
      }
      r.element.innerHTML = "";
      const b = document.createElement("b"); b.textContent = s.nombre; r.element.appendChild(b);
      if (sub) { const sm = document.createElement("small"); sm.textContent = sub; r.element.appendChild(sm); }
    });
  }, [relieve, capa, cultivoSeccion, catalogo, exag, imagenes, sinFoto]);

  useEffect(() => { if (motor.current) motor.current.controles.autoRotate = giro; }, [giro, relieve]);
  // en el recuadro chico no están las capas de fotos: si se achica con una de ellas, vuelve a los cultivos
  useEffect(() => { if (!grande && ES_FOTO(capa)) setCapa("plan"); }, [grande, capa]);

  // ------------------------------------------------ qué hay bajo el mouse
  const onMover = (e: React.PointerEvent) => {
    const m = motor.current;
    if (!m || !relieve) return;
    const r = m.renderer.domElement.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), m.camara);
    const hit = ray.intersectObject(m.terreno)[0];
    if (!hit) { setPunto(null); return; }
    const g = relieve.grilla;
    const W = (g.cols - 1) * relieve.px_m, D = (g.filas - 1) * relieve.px_m;
    const j = Math.round((hit.point.x + W / 2) / relieve.px_m), i = Math.round((hit.point.z + D / 2) / relieve.px_m);
    if (i < 0 || j < 0 || i >= g.filas || j >= g.cols) { setPunto(null); return; }
    const k = g.seccion[i][j];
    const s = k >= 0 && g.dentro[i][j] ? relieve.secciones[k] : null;
    setPunto({
      seccion: s?.nombre || null, elev: g.elev[i][j], pendiente: g.pendiente[i][j],
      ea: s ? g.erosion_actual[i][j] : null, ep: s ? g.erosion_plan[i][j] : null, t: s ? g.tolerancia[i][j] : null,
      cultivo: s ? cultivoSeccion.get(s.id) || null : null,
    });
  };

  if (error) return <div className="vacio"><div className="caja"><h3>No pude armar la vista 3D</h3><div className="alerta ambar">{error}</div></div></div>;
  const f1 = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("es-UY", { maximumFractionDigits: 1 }));

  return (
    <div className={`vista3d ${grande ? "" : "compacto"}`}>
      <div className="vista3d-lienzo" ref={caja} onPointerMove={onMover} onPointerLeave={() => setPunto(null)} onPointerDown={() => { setGiro(false); usuarioInteractuo.current = true; }} />
      {!relieve && (
        <div className="vista3d-cargando" role="status">
          <Cargando que="calculando" size={32} etiqueta="Cargando relieve 3D" />
          <span>{cargando ? "Trayendo el relieve de la NASA (SRTM)…" : "Preparando maqueta 3D…"}</span>
        </div>
      )}

      <div className="vista3d-panel">
        {grande && <h3>Tu campo en 3D</h3>}
        {grande && <p className="bajada">Relieve real de la NASA (SRTM, 30 m), con la altura exagerada para que se lea. Arrastrá para girar, rueda para acercar.</p>}
        {/* En el recuadro chico las capas van en una fila que se desliza de costado: envueltas en dos o
            tres renglones, con la leyenda abajo, tapaban media maqueta en una pantalla de ~1100 × 550. */}
        {(() => {
          const chips = CAPAS.filter((c) => grande || !ES_FOTO(c.id)).map((c) => (
            <button key={c.id} role="radio" aria-checked={capa === c.id} className={`chip ${capa === c.id ? "on" : ""}`} onClick={() => setCapa(c.id)}>{c.t}</button>
          ));
          return grande
            ? <div className="vista3d-capas" role="radiogroup" aria-label="Capa">{chips}</div>
            : <FilaSugerencias className="vista3d-capas" role="radiogroup" aria-label="Capa">{chips}</FilaSugerencias>;
        })()}
        <Leyenda capa={capa} />
        {grande && <>
        <label className="campo vista3d-exag">
          <span>{exag === 1 ? "Relieve: tamaño real" : `Relieve: ×${exag} (más marcado que el real)`}</span>
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            value={exag}
            onChange={(e) => setExag(+e.target.value)}
            aria-label={exag === 1 ? "Relieve: tamaño real" : `Relieve: ×${exag} (más marcado que el real)`}
          />
        </label>
        <label className="vista3d-giro"><input type="checkbox" checked={giro} onChange={(e) => setGiro(e.target.checked)} /> Girar solo</label>
        {aviso && <div className="alerta ambar" style={{ marginTop: 8 }}>{aviso}</div>}
        {relieve && <p className="fuente" style={{ marginTop: 8 }}>{relieve.fuente}</p>}
        </>}
      </div>

      {grande && punto && (
        <div className="vista3d-punto">
          {punto.seccion ? <b>{punto.seccion}</b> : <b>Fuera del campo</b>}
          <dl>
            <dt>Altura</dt><dd>{f1(punto.elev)} m</dd>
            <dt>Pendiente</dt><dd>{f1(punto.pendiente)} %</dd>
            {punto.cultivo && <><dt>{plan?.temporadas[temporada]?.etiqueta}</dt><dd>{nombreCultivo(catalogo, punto.cultivo, true)}</dd></>}
            {punto.ea != null && <><dt>Erosión hoy</dt><dd>{f1(punto.ea)} t/ha/año</dd></>}
            {punto.ep != null && <><dt>Con el plan</dt><dd>{f1(punto.ep)} t/ha/año</dd></>}
            {punto.t != null && <><dt>Tolerancia</dt><dd>{f1(punto.t)} t/ha/año</dd></>}
          </dl>
        </div>
      )}
    </div>
  );
}

function Leyenda({ capa }: { capa: Capa }) {
  const { catalogo, plan, temporada } = useApp();
  if (capa === "plan") {
    const cods = [...new Set((plan?.secciones || []).map((s) => s.cultivos[temporada]).filter(Boolean))];
    return (
      <div className="vista3d-leyenda">
        {cods.map((c) => <span key={c}><i style={{ background: catalogo?.cultivos.find((x) => x.codigo === c)?.color }} />{nombreCultivo(catalogo, c, true)}</span>)}
      </div>
    );
  }
  if (capa === "erosion_actual" || capa === "erosion_plan") {
    return (
      <div className="vista3d-rampa">
        <div style={{ background: "linear-gradient(90deg, #2f7d4f, #8fbf6a 15%, #f2c14e 25%, #e07b39 50%, #a8321f)" }} />
        <span><small>aguanta</small><small>en el límite</small><small>el doble</small><small>4 veces la tolerancia</small></span>
      </div>
    );
  }
  if (capa === "pendiente") {
    return (
      <div className="vista3d-rampa">
        <div style={{ background: "linear-gradient(90deg, #f4efe1, #d7e3b5 10%, #a9c97e 20%, #e3a857 35%, #b0541f 60%, #6b2410)" }} />
        <span><small>0 %</small><small>4 %</small><small>7 %</small><small>12 %</small><small>20 %</small></span>
      </div>
    );
  }
  if (capa === "agua") {
    return (
      <div className="vista3d-leyenda">
        <span><i style={{ background: "#08519c" }} />Vía de agua (cañada, más de 5 ha)</span>
        <span><i style={{ background: "#6baed6" }} />Acá se junta el agua (bajo)</span>
        <span><i style={{ background: "#eae4d3" }} />Ladera normal</span>
      </div>
    );
  }
  return <p className="fuente" style={{ margin: "4px 0 0" }}>{capa === "nasa" ? "Landsat y Sentinel-2 procesados por la NASA (HLS), 30 m, de la fecha más limpia del último año." : "Imágenes © Esri, Maxar, Earthstar Geographics."}</p>;
}
