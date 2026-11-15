/** Campo de trigo al atardecer para la página de presentación: decenas de miles de espigas con viento y una
 * «caricia» que sigue al mouse (o al dedo). Todo el movimiento va en la GPU: cada espiga es una instancia de
 * la misma tira de triángulos y el vertex shader la dobla como un arco (el largo no cambia, como un tallo de
 * verdad). La caricia es un rastro de los últimos puntos por donde pasó el cursor sobre el campo: cada punto
 * empuja las espigas cercanas hacia donde iba el cursor y se apaga con un pequeño rebote, como un resorte.
 *
 * Al bajar en la página, la cámara sube y el campo pasa a los colores de un índice de vegetación por potrero
 * (`setEscena`): es una ilustración de cómo lo ve un satélite, no datos reales.
 *
 * No depende de React: la página crea uno, le pasa el canvas y lo destruye al irse. */
import * as THREE from "three";

const RASTRO = 28; // puntos del rastro del cursor (uniforms del shader)

const COMUN = /* glsl */ `
uniform vec3 uSol;
uniform float uSat;
uniform float uTiempo;
uniform float uDia;    // 0 atardecer, 1 mediodía (con nubes)
uniform vec3 uZenit;
uniform vec3 uMedio;
uniform vec3 uHoriz;
uniform vec3 uBajo;
uniform vec3 uHalo;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float ruido(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) { return 0.55 * ruido(p) + 0.28 * ruido(p * 2.1 + 3.7) + 0.17 * ruido(p * 4.3 + 9.1); }
vec3 cielo(vec3 d) {
  float e = d.y;
  vec3 c = mix(uHoriz, uMedio, smoothstep(0.0, 0.16, e));
  c = mix(c, uZenit, smoothstep(0.12, 0.62, e));
  c = mix(c, uBajo, smoothstep(0.0, -0.2, e));
  float s = max(dot(d, uSol), 0.0);
  c += uHalo * pow(s, 6.0) * 0.45;
  c += mix(vec3(1.0, 0.80, 0.55), vec3(1.0), uDia) * pow(s, 70.0) * 0.8;
  c += vec3(1.0, 0.96, 0.86) * smoothstep(0.9990, 0.9996, s) * 1.6;
  if (uDia > 0.0 && e > 0.0) {
    vec2 q = d.xz / (e + 0.06) * 0.9 + vec2(uTiempo * 0.012, uTiempo * 0.004);
    float n = fbm(q);
    float nube = smoothstep(0.52, 0.8, n) * smoothstep(0.0, 0.08, e);
    c = mix(c, mix(vec3(0.86, 0.9, 0.95), vec3(1.0), smoothstep(0.55, 0.9, n)), nube * 0.9 * uDia);
  }
  return c;
}
// potreros vistos desde arriba (ilustración): filas de distinto ancho, cortadas en cuadros
float potrero(vec2 p) {
  vec2 q = p + vec2(3.0, 40.0);
  float fila = floor(q.y / 11.0);
  float largo = 9.0 + hash(vec2(fila, 3.0)) * 12.0;
  float c = floor((q.x + hash(vec2(fila, 7.0)) * 13.0) / largo);
  return hash(vec2(c, fila));
}
vec3 colorNdvi(float v) {
  vec3 a = vec3(0.52, 0.33, 0.18), b = vec3(0.88, 0.78, 0.34), c = vec3(0.13, 0.50, 0.24);
  return v < 0.5 ? mix(a, b, v * 2.0) : mix(b, c, (v - 0.5) * 2.0);
}
float niebla(float d) { return 1.0 - exp(-pow(d * 0.017, 1.6)); }
`;

const ESPIGA_VS = /* glsl */ `
${COMUN}
attribute vec3 aBase;  // x, z, alto
attribute vec4 aAzar;  // fase, tono, ancho, inclinación propia
uniform float uViento;
uniform vec4 uRastro[${RASTRO}];    // x, z, nacimiento, radio
uniform vec2 uRastroDir[${RASTRO}]; // hacia dónde iba el cursor
varying float vY;
varying float vX;
varying float vEspiga;
varying float vBrillo;
varying float vTono;
varying float vPotrero;
varying vec3 vMundo;

void main() {
  vec2 wp = aBase.xy;
  float h = aBase.z;
  float y = position.y;
  vec3 raiz = vec3(wp.x, 0.0, wp.y);

  // la tira siempre de frente a la cámara (girando solo en el eje vertical)
  vec3 aCam = cameraPosition - raiz;
  aCam.y = 0.0;
  vec3 der = normalize(vec3(-aCam.z, 0.0, aCam.x) + 1e-5);

  // viento: ráfagas que viajan por el campo + un temblor propio de cada espiga
  float rafaga = smoothstep(0.25, 0.95, ruido(wp * 0.06 + vec2(uTiempo * 0.30, uTiempo * 0.10)));
  float ola = sin(dot(wp, vec2(0.42, 0.18)) - uTiempo * 1.7 + aAzar.x * 0.6) * 0.5 + 0.5;
  vec2 dirViento = normalize(vec2(0.9, -0.45));
  vec2 flexion = dirViento * (0.08 + 0.55 * rafaga * (0.55 + 0.45 * ola)) * uViento;
  flexion += vec2(sin(uTiempo * 2.1 + aAzar.x * 6.28), cos(uTiempo * 1.7 + aAzar.x * 5.1)) * 0.035 * uViento;
  flexion += (vec2(hash(wp * 3.1), hash(wp * 5.7)) - 0.5) * aAzar.w;

  // la caricia del cursor
  vec2 caricia = vec2(0.0);
  for (int i = 0; i < ${RASTRO}; i++) {
    vec4 r = uRastro[i];
    float edad = uTiempo - r.z;
    if (edad < 0.0 || edad > 4.5) continue;
    vec2 d = wp - r.xy;
    float dist = length(d);
    float alcance = 1.0 - smoothstep(r.w * 0.3, r.w, dist);
    if (alcance <= 0.0) continue;
    float vida = smoothstep(0.0, 0.10, edad) * exp(-edad * 1.35) * cos(edad * 2.6);
    vec2 lejos = dist > 1e-3 ? d / dist : vec2(0.0);
    caricia += (lejos * 0.55 + uRastroDir[i] * 0.85) * alcance * vida;
  }
  float c = length(caricia);
  if (c > 1e-4) caricia *= 1.3 * tanh(c / 1.3) / c;
  flexion += caricia;

  // doblar como un arco de largo fijo
  float tita = min(length(flexion), 1.45);
  vec2 dirF = tita > 1e-4 ? flexion / length(flexion) : vec2(0.0);
  float a = tita * y;
  float avance = tita > 1e-3 ? (1.0 - cos(a)) / tita : 0.0;
  float alto = tita > 1e-3 ? sin(a) / tita : y;

  // tallo fino, espiga en huso y la punta de las barbas
  float espiga = smoothstep(0.78, 0.82, y);
  float huso = pow(sin(clamp((y - 0.79) / 0.19, 0.0, 1.0) * 3.14159), 0.55);
  float ancho = mix(0.0055 * (1.0 - 0.3 * y), 0.021, huso) * aAzar.z;
  ancho = mix(ancho, 0.0018, smoothstep(0.96, 1.0, y));
  ancho *= 1.0 + length(cameraPosition - raiz) * 0.035; // lejos, más anchas: sin parpadeo

  vec3 p = raiz + vec3(dirF.x, 0.0, dirF.y) * avance * h + vec3(0.0, alto * h, 0.0) + der * position.x * ancho;

  vY = y;
  vX = position.x;
  vEspiga = espiga * (1.0 - smoothstep(0.97, 1.0, y));
  vBrillo = smoothstep(0.12, 0.95, tita) + smoothstep(0.05, 0.6, c) * 0.6;
  vTono = aAzar.y;
  vPotrero = potrero(wp);
  vMundo = p;
  gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
}
`;

const ESPIGA_FS = /* glsl */ `
${COMUN}
varying float vY;
varying float vX;
varying float vEspiga;
varying float vBrillo;
varying float vTono;
varying float vPotrero;
varying vec3 vMundo;

void main() {
  vec3 tallo = vec3(0.46, 0.33, 0.13);
  vec3 dorado = vec3(0.86, 0.63, 0.27);
  vec3 punta = vec3(1.0, 0.85, 0.50);
  vec3 col = mix(tallo * 0.35, tallo, smoothstep(0.0, 0.5, vY));
  col = mix(col, dorado * 0.9, smoothstep(0.45, 0.8, vY));
  col = mix(col, mix(dorado, punta, 0.5), vEspiga);
  col *= 0.72 + 0.28 * cos(vX * 3.14159); // redondez del tallo y de la espiga
  col *= 0.76 + 0.42 * vTono;
  col *= 0.86 + 0.42 * vBrillo;
  vec3 v = normalize(vMundo - cameraPosition);
  float contraluz = pow(max(dot(v, uSol), 0.0), 5.0);
  col += vec3(1.0, 0.66, 0.32) * contraluz * (0.25 + 0.9 * vEspiga) * vY * (1.0 - 0.7 * uDia);
  col *= 1.0 + 0.4 * uDia; // a pleno sol, más claro
  col = mix(col, colorNdvi(vPotrero) * (0.65 + 0.5 * vY), uSat);
  col = mix(col, cielo(v), niebla(length(vMundo - cameraPosition)));
  gl_FragColor = vec4(col, 1.0);
}
`;

const SUELO_VS = /* glsl */ `
varying vec3 vMundo;
void main() {
  vec4 m = modelMatrix * vec4(position, 1.0);
  vMundo = m.xyz;
  gl_Position = projectionMatrix * viewMatrix * m;
}
`;

const SUELO_FS = /* glsl */ `
${COMUN}
varying vec3 vMundo;
void main() {
  vec2 wp = vMundo.xz;
  vec3 col = vec3(0.30, 0.20, 0.09) * (0.75 + 0.4 * ruido(wp * 0.7)) + vec3(0.25, 0.17, 0.06) * ruido(wp * 0.08);
  col *= 1.0 + 0.55 * uDia;
  col = mix(col, colorNdvi(potrero(wp)) * 0.62, uSat);
  vec3 v = normalize(vMundo - cameraPosition);
  col = mix(col, cielo(v), niebla(length(vMundo - cameraPosition)));
  gl_FragColor = vec4(col, 1.0);
}
`;

const CIELO_VS = SUELO_VS;
const CIELO_FS = /* glsl */ `
${COMUN}
varying vec3 vMundo;
void main() { gl_FragColor = vec4(cielo(normalize(vMundo - cameraPosition)), 1.0); }
`;

const POLEN_VS = /* glsl */ `
attribute float aBrillo;
varying float vBrillo;
uniform float uPx;
void main() {
  vec4 mv = viewMatrix * vec4(position, 1.0);
  vBrillo = aBrillo;
  gl_PointSize = uPx * (0.6 + aBrillo) * 26.0 / -mv.z;
  gl_Position = projectionMatrix * mv;
}
`;
const POLEN_FS = /* glsl */ `
varying float vBrillo;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d);
  gl_FragColor = vec4(vec3(1.0, 0.82, 0.5) * a * (0.35 + vBrillo), 1.0);
}
`;

type Paleta = "atardecer" | "dia";
type Opciones = {
  alAcariciar?: () => void;
  /** "atardecer" (portada A) o "dia": cielo celeste con nubes (portada B) */
  paleta?: Paleta;
  /** cuántas partículas de polen (0 = sin polen) */
  polen?: number;
  /** false: se arma pero no se dibuja hasta llamar a arrancar (la bienvenida espera a que termine el fundido) */
  arrancar?: boolean;
};

const v3 = (r: number, g: number, b: number) => new THREE.Vector3(r, g, b);
const PALETAS: Record<Paleta, { dia: number; sol: THREE.Vector3; zenit: THREE.Vector3; medio: THREE.Vector3; horiz: THREE.Vector3; bajo: THREE.Vector3; halo: THREE.Vector3 }> = {
  atardecer: { dia: 0, sol: v3(0.35, 0.07, -1), zenit: v3(0.10, 0.12, 0.27), medio: v3(0.52, 0.36, 0.46), horiz: v3(1.0, 0.64, 0.38), bajo: v3(0.62, 0.42, 0.28), halo: v3(1.0, 0.55, 0.25) },
  dia: { dia: 1, sol: v3(0.75, 0.55, -0.55), zenit: v3(0.20, 0.47, 0.82), medio: v3(0.47, 0.70, 0.93), horiz: v3(0.84, 0.90, 0.94), bajo: v3(0.78, 0.72, 0.56), halo: v3(1.0, 0.95, 0.85) },
};

const azar = (a: number, b: number) => a + Math.random() * (b - a);

/** Números al azar con semilla fija (mulberry32): la portada y la bienvenida plantan el mismo trigo, espiga por
 * espiga, así el fundido entre las dos páginas no mezcla dos campos distintos. */
function azarConSemilla(semilla: number) {
  let a = semilla >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Cómo quedó la escena en un momento, para seguirla igual en otra página. */
export type EstadoTrigo = { vista: number; meta: number; px: number; py: number; t: number };

/** Niveles de calidad del trigo. En una compu con placa de video integrada el nivel
 * más alto no pasaba de ~45 cuadros por segundo, con tirones, y el recorte de antes recién saltaba debajo de 40 y a
 * los ~4 s: nunca. Ahora se mide desde el segundo y medio (~3 s para decidir) y se baja de a un nivel hasta que vaya
 * parejo; lo elegido queda guardado, así la bienvenida (y la próxima visita) arranca ya en ese nivel y planta
 * exactamente el mismo campo. En esa compu el nivel 1 da 60 parejos en la portada y en la bienvenida; con el 70 %
 * de las espigas el campo se veía ralo (por eso 85 %), y la menor resolución casi no se nota.
 * espigas: parte de las espigas que se dibujan; px: parte de la resolución de la pantalla (piso en 1 en el nivel 1). */
// Los niveles bajos perdían demasiado. Ahora ninguno dibuja con menos de
// un punto por píxel de la pantalla (el nivel 2 bajaba a 0,6 y en una pantalla común el trigo se veía borroso), y
// cada uno deja más espigas: 92 % y 75 % (antes 85 % y 55 %, que se veía ralo).
const NIVELES = [
  { espigas: 1, px: 1 },
  { espigas: 0.92, px: 0.85 },
  { espigas: 0.75, px: 0.72 },
];
const CLAVE_NIVEL = "fs:trigoNivel";

/** ?calidad=0, 1 o 2 para probar un nivel fijo (sin medir ni guardar). */
function nivelPedido(): number | null {
  const q = new URLSearchParams(location.search).get("calidad");
  const n = q === null || q === "" ? NaN : Number(q);
  return Number.isInteger(n) && n >= 0 && n < NIVELES.length ? n : null;
}

function nivelGuardado(): number {
  const pedido = nivelPedido();
  if (pedido !== null) return pedido;
  try {
    const n = Number(localStorage.getItem(CLAVE_NIVEL));
    // el nivel más bajo no se guarda para siempre: una medición mala (la página cargando algo pesado al lado) dejaba
    // el trigo en lo peor en todas las visitas. Se arranca a lo sumo en el 1 y, si de verdad no da, vuelve a bajar.
    return Number.isInteger(n) && n >= 0 && n < NIVELES.length ? Math.min(n, 1) : 0;
  } catch {
    return 0;
  }
}

export class CampoTrigo {
  private renderer: THREE.WebGLRenderer;
  private escena = new THREE.Scene();
  private camara = new THREE.PerspectiveCamera(50, 1, 0.05, 900);
  private antes = performance.now();
  private uniforms = {
    uTiempo: { value: 0 },
    uViento: { value: 1 },
    uSol: { value: new THREE.Vector3() },
    uDia: { value: 0 },
    uZenit: { value: new THREE.Vector3() },
    uMedio: { value: new THREE.Vector3() },
    uHoriz: { value: new THREE.Vector3() },
    uBajo: { value: new THREE.Vector3() },
    uHalo: { value: new THREE.Vector3() },
    uSat: { value: 0 },
    uRastro: { value: Array.from({ length: RASTRO }, () => new THREE.Vector4(0, 0, -100, 1)) },
    uRastroDir: { value: Array.from({ length: RASTRO }, () => new THREE.Vector2()) },
  };
  private espigas: THREE.InstancedBufferGeometry;
  private total: number;
  private polen: THREE.Points;
  private polenVel: Float32Array;
  private uPx = { value: 1 };
  private raf = 0;
  private ndc = new THREE.Vector2();
  private hayPuntero = false;
  private ultimo: THREE.Vector3 | null = null;
  private cursorMundo: THREE.Vector3 | null = null;
  private indice = 0;
  private plano = new THREE.Plane(new THREE.Vector3(0, 1, 0), -0.72);
  private rayo = new THREE.Raycaster();
  private parallax = new THREE.Vector2();
  private vista = { actual: 0, meta: 0, sat: 0, satMeta: 0 };
  /** multiplica la velocidad con que la cámara llega a su vista: 1 al bajar la página, más al despegar */
  private rapidez = 1;
  private tiempos: number[] = [];
  private nivel = nivelGuardado();
  /** con ?calidad=N se prueba un nivel fijo, sin medir */
  private nivelFijo = nivelPedido() !== null;
  /** cuadros que faltan para volver a medir (al arrancar y después de cambiar de nivel, los primeros vienen lentos) */
  private saltear = 90;
  private malas = 0;
  private avisado = false;
  private lienzo: HTMLCanvasElement;
  private alto = 1;
  private visible = true;
  private enMarcha: boolean;
  private alPrimerCuadro: (() => void) | null = null;
  private observadores: Array<ResizeObserver | IntersectionObserver> = [];

  constructor(lienzo: HTMLCanvasElement, private opciones: Opciones = {}) {
    this.lienzo = lienzo;
    this.enMarcha = opciones.arrancar !== false;
    const pal = PALETAS[opciones.paleta ?? "atardecer"];
    const u = this.uniforms;
    u.uDia.value = pal.dia;
    u.uSol.value.copy(pal.sol).normalize();
    u.uZenit.value.copy(pal.zenit);
    u.uMedio.value.copy(pal.medio);
    u.uHoriz.value.copy(pal.horiz);
    u.uBajo.value.copy(pal.bajo);
    u.uHalo.value.copy(pal.halo);
    this.renderer = new THREE.WebGLRenderer({ canvas: lienzo, antialias: true, powerPreference: "high-performance" });
    const chico = Math.min(innerWidth, innerHeight) < 700 || matchMedia("(pointer: coarse)").matches;
    // ?espigas=N para probar en compus lentas (o en un navegador sin GPU)
    const pedidas = Number(new URLSearchParams(location.search).get("espigas"));
    this.total = pedidas > 0 ? Math.min(pedidas, 200000) : chico ? 40000 : 110000;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) this.uniforms.uViento.value = 0.35;

    this.espigas = this.crearEspigas();
    const malla = new THREE.Mesh(
      this.espigas,
      new THREE.ShaderMaterial({ uniforms: this.uniforms, vertexShader: ESPIGA_VS, fragmentShader: ESPIGA_FS, side: THREE.DoubleSide }),
    );
    malla.frustumCulled = false;
    this.escena.add(malla);

    const suelo = new THREE.Mesh(
      new THREE.PlaneGeometry(700, 700).rotateX(-Math.PI / 2).translate(0, 0, -250),
      new THREE.ShaderMaterial({ uniforms: this.uniforms, vertexShader: SUELO_VS, fragmentShader: SUELO_FS }),
    );
    this.escena.add(suelo);

    const cielo = new THREE.Mesh(
      new THREE.SphereGeometry(800, 32, 16),
      new THREE.ShaderMaterial({ uniforms: this.uniforms, vertexShader: CIELO_VS, fragmentShader: CIELO_FS, side: THREE.BackSide, depthWrite: false }),
    );
    cielo.onBeforeRender = () => cielo.position.copy(this.camara.position);
    this.escena.add(cielo);

    ({ puntos: this.polen, vel: this.polenVel } = this.crearPolen(opciones.polen ?? (chico ? 160 : 360)));
    this.escena.add(this.polen);

    this.redimensionar();
    // el lienzo puede ser la pantalla entera (portada A) o una caja dentro de la página (portada B)
    const ro = new ResizeObserver(this.redimensionar);
    ro.observe(lienzo);
    // fuera de la vista no se dibuja: no gasta batería mientras se lee el resto de la página
    const io = new IntersectionObserver(([e]) => {
      this.visible = e.isIntersecting;
      cancelAnimationFrame(this.raf);
      if (this.visible && this.enMarcha) {
        this.antes = performance.now();
        this.raf = requestAnimationFrame(this.cuadro);
      }
    });
    io.observe(lienzo);
    this.observadores = [ro, io];
    addEventListener("pointermove", this.mover, { passive: true });
    document.addEventListener("pointerleave", this.salir);
    addEventListener("blur", this.salir);
    if (this.enMarcha) this.raf = requestAnimationFrame(this.cuadro);
  }

  /** Compila los shaders sin frenar la página (donde el navegador lo permite). Si no, se compilarían en el primer
   * cuadro: en la bienvenida eso dejaba la pantalla quieta ~0,3 a 0,5 s justo en el fundido. */
  async preparar(): Promise<void> {
    this.camaraSegunVista();
    try {
      await this.renderer.compileAsync(this.escena, this.camara);
    } catch {
      /* se compila en el primer cuadro, como antes */
    }
  }

  /** Empieza a dibujar (si se armó con arrancar: false). alPrimerCuadro avisa cuando ya hay algo dibujado. */
  arrancar(alPrimerCuadro?: () => void) {
    this.alPrimerCuadro = alPrimerCuadro ?? null;
    if (this.enMarcha) {
      this.alPrimerCuadro?.();
      this.alPrimerCuadro = null;
      return;
    }
    this.enMarcha = true;
    this.antes = performance.now();
    if (this.visible) this.raf = requestAnimationFrame(this.cuadro);
  }

  /** Una foto del último cuadro, en JPEG.
   * Se copia el cuadro que ya está en pantalla: dibujar uno nuevo y leerlo obligaba a esperar a la placa de video y
   * congelaba la portada ~140 ms justo antes del fundido. Solo si la copia sale vacía (hay navegadores que borran el
   * lienzo de WebGL después de mostrarlo) se dibuja y se lee en la misma tarea. A 800 px de ancho pasar a JPEG cuesta
   * ~14 ms; a 1280, 80 a 220 ms. Alcanza: dura menos de un segundo, debajo del velo oscuro de la bienvenida, y el
   * trigo 3D la tapa enseguida. */
  foto(anchoMax = 800): string | null {
    try {
      const { width, height } = this.lienzo;
      const k = Math.min(1, anchoMax / width);
      const c = document.createElement("canvas");
      c.width = Math.round(width * k);
      c.height = Math.round(height * k);
      const ctx = c.getContext("2d", { willReadFrequently: true });
      if (!ctx) return null;
      ctx.drawImage(this.lienzo, 0, 0, c.width, c.height);
      // el cielo nunca es negro ni transparente: si el centro salió así, la copia vino vacía
      const p = ctx.getImageData(c.width >> 1, c.height >> 2, 1, 1).data;
      if (p[3] === 0 || p[0] + p[1] + p[2] === 0) {
        this.camaraSegunVista();
        this.renderer.render(this.escena, this.camara);
        ctx.drawImage(this.lienzo, 0, 0, c.width, c.height);
      }
      return c.toDataURL("image/jpeg", 0.82);
    } catch {
      return null;
    }
  }

  /** vista: 0 a ras del trigo, 1 desde arriba. sat: 0 trigo, 1 colores de vegetación por potrero. */
  /** Al tocar «Comenzar» en la bienvenida de la herramienta: la cámara sube rápido desde el trigo hasta verlo
   * desde arriba, sin cambiarle los colores. En ~0,6 s ya está arriba, mientras se funde con la foto del mapa. */
  despegar() {
    this.rapidez = 3;
    this.vista.meta = 1;
    this.vista.satMeta = 0;
  }

  /** Pone la cámara en una vista sin transición (la bienvenida arranca donde la dejó la portada). */
  fijarVista(vista: number) {
    this.vista.actual = vista;
    this.vista.meta = vista;
  }

  /** La vista, el movimiento del mouse y la hora del viento, para que otra página siga desde acá. */
  estado(): EstadoTrigo {
    return { vista: this.vista.actual, meta: this.vista.meta, px: this.parallax.x, py: this.parallax.y, t: this.uniforms.uTiempo.value };
  }

  /** Sigue la escena que dejó otra página: misma cámara, mismo viento, y sigue yendo hacia la misma vista. */
  continuar(e: EstadoTrigo) {
    this.vista.actual = e.vista;
    this.vista.meta = e.meta;
    this.parallax.set(e.px, e.py);
    this.ndc.set(e.px, e.py);
    this.uniforms.uTiempo.value = e.t;
    this.antes = performance.now();
  }

  setEscena(vista: number, sat: number) {
    this.vista.meta = vista;
    this.vista.satMeta = sat;
  }

  destruir() {
    cancelAnimationFrame(this.raf);
    this.observadores.forEach((o) => o.disconnect());
    removeEventListener("pointermove", this.mover);
    document.removeEventListener("pointerleave", this.salir);
    removeEventListener("blur", this.salir);
    this.escena.traverse((o) => {
      const m = o as THREE.Mesh;
      m.geometry?.dispose();
      (m.material as THREE.Material | undefined)?.dispose();
    });
    this.renderer.dispose();
  }

  private crearEspigas() {
    const pos: number[] = [];
    const idx: number[] = [];
    // más cortes arriba, donde va la espiga
    const niveles = [0, 0.25, 0.5, 0.7, 0.79, 0.83, 0.87, 0.91, 0.945, 0.97, 1];
    const SEG = niveles.length - 1;
    niveles.forEach((y, i) => {
      pos.push(-0.5, y, 0, 0.5, y, 0);
      if (i < SEG) {
        const a = i * 2;
        idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
      }
    });
    const g = new THREE.InstancedBufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    const base = new Float32Array(this.total * 3);
    const azarA = new Float32Array(this.total * 4);
    const zCerca = 7.5;
    const zLejos = -115;
    const rnd = azarConSemilla(20261115);
    const entre = (a: number, b: number) => a + rnd() * (b - a);
    for (let i = 0; i < this.total; i++) {
      // más densas cerca de la cámara, donde se ven grandes; el orden es al azar, así que cortar la lista
      // (si la compu no da) deja una muestra pareja
      const z = zCerca - (zCerca - zLejos) * rnd() ** 2;
      const d = Math.max(7.5 - z, 2.5);
      const x = (rnd() - 0.5) * (2.3 * d + 7);
      const lote = Math.sin(x * 0.11) * Math.cos(z * 0.09) * 0.07;
      base.set([x, z, 0.82 + lote + entre(-0.1, 0.12)], i * 3);
      azarA.set([rnd() * 100, rnd(), entre(0.75, 1.25), entre(0.05, 0.22)], i * 4);
    }
    g.setAttribute("aBase", new THREE.InstancedBufferAttribute(base, 3));
    g.setAttribute("aAzar", new THREE.InstancedBufferAttribute(azarA, 4));
    g.instanceCount = Math.round(this.total * NIVELES[this.nivel].espigas);
    return g;
  }

  private crearPolen(n: number) {
    const pos = new Float32Array(n * 3);
    const brillo = new Float32Array(n);
    const vel = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos.set([azar(-9, 9), azar(0.5, 3.2), azar(-16, 5)], i * 3);
      brillo[i] = Math.random() ** 3;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aBrillo", new THREE.BufferAttribute(brillo, 1));
    const puntos = new THREE.Points(
      g,
      new THREE.ShaderMaterial({
        uniforms: { uPx: this.uPx },
        vertexShader: POLEN_VS,
        fragmentShader: POLEN_FS,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    );
    puntos.frustumCulled = false;
    return { puntos, vel };
  }

  private redimensionar = () => {
    const base = Math.min(devicePixelRatio || 1, 2);
    const f = NIVELES[this.nivel].px;
    const px = this.nivel === 0 ? base : Math.max(Math.min(base, 1), base * f);
    this.renderer.setPixelRatio(px);
    const ancho = this.lienzo.clientWidth || innerWidth;
    this.alto = this.lienzo.clientHeight || innerHeight;
    this.uPx.value = px * (this.alto / 800);
    this.renderer.setSize(ancho, this.alto, false);
    this.camara.aspect = ancho / this.alto;
    this.camara.fov = this.camara.aspect < 0.8 ? 62 : 50;
    this.camara.updateProjectionMatrix();
  };

  private mover = (e: PointerEvent) => {
    const r = this.lienzo.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width;
    const y = (e.clientY - r.top) / r.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return this.salir();
    this.ndc.set(x * 2 - 1, -y * 2 + 1);
    this.hayPuntero = true;
  };

  private salir = () => {
    this.hayPuntero = false;
    this.ultimo = null;
    this.cursorMundo = null;
  };

  private acariciar(t: number) {
    if (!this.hayPuntero) return;
    this.rayo.setFromCamera(this.ndc, this.camara);
    const p = new THREE.Vector3();
    if (!this.rayo.ray.intersectPlane(this.plano, p) || p.distanceTo(this.camara.position) > 70) {
      this.ultimo = null;
      this.cursorMundo = null;
      return;
    }
    this.cursorMundo = p;
    const d = p.distanceTo(this.camara.position);
    if (this.ultimo && this.ultimo.distanceTo(p) < 0.07 + 0.012 * d) return;
    const dir = new THREE.Vector2();
    if (this.ultimo) dir.set(p.x - this.ultimo.x, p.z - this.ultimo.z).normalize();
    const i = this.indice++ % RASTRO;
    this.uniforms.uRastro.value[i].set(p.x, p.z, t, 0.55 + 0.04 * d);
    this.uniforms.uRastroDir.value[i].copy(dir);
    if (this.ultimo && !this.avisado) {
      this.avisado = true;
      this.opciones.alAcariciar?.();
    }
    this.ultimo = p.clone();
  }

  private moverPolen(dt: number, t: number) {
    const pos = this.polen.geometry.getAttribute("position") as THREE.BufferAttribute;
    const a = pos.array as Float32Array;
    const v = this.polenVel;
    const c = this.cursorMundo;
    for (let i = 0; i < a.length; i += 3) {
      v[i] += (Math.sin(t * 0.3 + i) * 0.05 + 0.04) * dt;
      v[i + 1] += Math.cos(t * 0.4 + i * 0.7) * 0.03 * dt;
      v[i + 2] += Math.sin(t * 0.25 + i * 1.3) * 0.04 * dt;
      if (c) {
        const dx = a[i] - c.x, dy = a[i + 1] - c.y, dz = a[i + 2] - c.z;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < 2.2) {
          const f = (1 - d2 / 2.2) * 2.4 * dt;
          v[i] += dx * f;
          v[i + 1] += (Math.abs(dy) + 0.5) * f;
          v[i + 2] += dz * f;
        }
      }
      const roce = Math.exp(-dt * 1.4);
      for (let k = 0; k < 3; k++) {
        v[i + k] *= roce;
        a[i + k] += v[i + k] * dt;
      }
      if (a[i] > 9) a[i] -= 18;
      if (a[i] < -9) a[i] += 18;
      if (a[i + 1] > 3.6 || a[i + 1] < 0.4) { a[i + 1] = azar(0.6, 1.4); v[i + 1] = 0; }
      if (a[i + 2] > 5) a[i + 2] -= 21;
      if (a[i + 2] < -16) a[i + 2] += 21;
    }
    pos.needsUpdate = true;
  }

  private camaraSegunVista() {
    const v = this.vista.actual;
    const s = v * v * (3 - 2 * v);
    const px = this.parallax.x;
    const py = this.parallax.y;
    // a ras del trigo se mira apenas hacia arriba: el horizonte queda bajo y el cielo deja lugar al texto
    this.camara.position.set(px * 0.45, 1.55 + s * 7.5 + py * 0.12, 6 + s * 1.5);
    this.camara.lookAt(px * 0.15, 2.6 * (1 - s) + py * 0.25, -10 + s * 4);
  }

  /** Si la compu no llega a ~52 cuadros por segundo con la cámara quieta, se baja un nivel (menos espigas y menos
   * píxeles) y se vuelve a medir. Nunca se sube: subir y bajar se vería como un parpadeo. Cada medición son 60
   * cuadros sin el 10 % más lento (un tirón suelto, de cuando se carga algo, no cuenta). */
  private medir(dt: number) {
    if (this.nivelFijo || this.nivel >= NIVELES.length - 1) return;
    // mientras la cámara se mueve (al bajar la página o al despegar) no se mide: no es el trabajo de siempre
    if (Math.abs(this.vista.meta - this.vista.actual) > 0.02 || dt >= 0.1) {
      this.tiempos.length = 0;
      return;
    }
    if (this.saltear > 0) {
      this.saltear--;
      return;
    }
    this.tiempos.push(dt);
    if (this.tiempos.length < 60) return;
    const todos = this.tiempos.sort((a, b) => a - b);
    const orden = todos.slice(0, 54);
    const medio = orden.reduce((s, x) => s + x, 0) / orden.length;
    // y cuadros salteados: lo normal (el cuarto más rápido) es lo que tarda la pantalla en refrescar; uno que tarda
    // casi el doble es un cuadro que no llegó. Más de 3 de 60 (5 %) se ven como tirones aunque el promedio dé bien.
    const normal = todos[15];
    const salteados = todos.filter((x) => x > normal * 1.7).length;
    this.tiempos.length = 0;
    const mala = medio > 1 / 52 || salteados > 3;
    // dos mediciones malas seguidas (~2 s): una sola puede ser la página cargando algo
    this.malas = mala ? this.malas + 1 : 0;
    if (this.malas < 2) return;
    this.malas = 0;
    this.nivel++;
    this.saltear = 30;
    this.espigas.instanceCount = Math.round(this.total * NIVELES[this.nivel].espigas);
    this.redimensionar();
    try {
      localStorage.setItem(CLAVE_NIVEL, String(this.nivel));
    } catch {
      /* sin almacenamiento: la próxima vez vuelve a medir */
    }
  }

  private cuadro = () => {
    if (!this.visible) return;
    this.raf = requestAnimationFrame(this.cuadro);
    const ahora = performance.now();
    const dt = Math.min((ahora - this.antes) / 1000, 0.1);
    this.antes = ahora;
    const t = (this.uniforms.uTiempo.value += dt);
    this.medir(dt);
    const k = 1 - Math.exp(-dt * 2.2 * this.rapidez);
    this.vista.actual += (this.vista.meta - this.vista.actual) * k;
    this.vista.sat += (this.vista.satMeta - this.vista.sat) * k;
    this.uniforms.uSat.value = this.vista.sat;
    if (this.hayPuntero) this.parallax.lerp(this.ndc, 1 - Math.exp(-dt * 1.5));
    this.camaraSegunVista();
    this.acariciar(t);
    this.moverPolen(dt, t);
    this.renderer.render(this.escena, this.camara);
    if (this.alPrimerCuadro) {
      const aviso = this.alPrimerCuadro;
      this.alPrimerCuadro = null;
      aviso();
    }
  };
}
