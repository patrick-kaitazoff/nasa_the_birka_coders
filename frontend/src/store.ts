import { regionDe, useRegion, type Region } from "./i18n/region";
import { create } from "zustand";
import CATALOGO_INICIAL from "./catalogo_inicial.json";
import { useIdioma } from "./i18n/idioma";
import type { Analisis, Campo, Catalogo, MensajeUI, Pestania, Plan, Seccion, TipoTarjeta } from "./tipos";
import { flujo, api, puenteActivo, type ResultadoHistoria } from "./api";
import { areaHa, puntoInterior } from "./mapa/geo";
import { enPalabras } from "./errores";
import { armandoPorAdelantado, finDelFundido } from "./inicio/llegada";
import { adelantarVisor3D, pedirFoto, sembrarRelieve } from "./relieve/useRelieve";
import { sinOpcionesFueraDeTolerancia } from "./plan/eleccion";
import { corregirPorIP, paisInicial } from "./mapa/paisInicial";

const CLAVE = "fieldshift:v1";

function nuevoId() {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
}

function campoVacio(): Campo {
  return { id: nuevoId(), secciones: [] };
}

interface Estado {
  campo: Campo;
  mensajes: MensajeUI[];
  historialApi: any[];
  analisis: Analisis | null;
  plan: Plan | null;
  historia: ResultadoHistoria | null;
  historiaCargando: boolean;
  historiaError: string | null;
  correccionesHistoria: Record<string, string>;
  catalogo: Catalogo | null;
  ia: boolean;
  modo: "ia" | "guiado";
  pestania: Pestania;
  temporada: number;
  ocupado: boolean;
  modoMapa: "ver" | "contorno" | "secciones" | "circulo" | "editar_contorno";
  seccionSel: string | null;
  /** el lote marcado lo puso la app (el más grande, al abrir el Plan) y no la persona: Comparar arranca entonces en el
   * primero de la izquierda */
  seccionAuto: boolean;
  vistaMovil: "chat" | "trabajo";
  centrar: { lat: number; lon: number; zoom?: number; t: number } | null;
  zona: { estado: "nada" | "cargando" | "listo" | "error"; punto?: string; clima?: any; suelo?: any };
  /** aviso chico abajo de la pantalla para lo que falla fuera del chat */
  aviso: string | null;
  setAviso: (a: string | null) => void;
  /** tocó un departamento o fue a su ubicación: el chat deja de estar adelante y el mapa queda a la vista */
  explorando: boolean;
  setExplorando: (v: boolean) => void;
  /** En qué país se busca el campo en el mapa: Uruguay (departamentos, padrón) o EE. UU. (estados,
   * condados, lote del Cropland Data Layer). */
  paisMapa: "UY" | "US";
  setPaisMapa: (p: "UY" | "US") => void;
  /** Esperando que se toque un lote en el mapa para sacar su contorno del CDL (EE. UU.). */
  tocandoLote: boolean;
  setTocandoLote: (v: boolean) => void;
  /** mientras se marca un contorno o una sección: cuántas esquinas lleva y qué superficie encierra */
  marcando: { puntos: number; ha: number } | null;
  setMarcando: (v: { puntos: number; ha: number } | null) => void;
  /** en pantalla grande, el chat se achica a una franja según la pestaña (en el mapa abierto; en los resultados, chico) */
  chatPlegado: Record<Pestania, boolean>;
  setChatPlegado: (p: Pestania, v: boolean) => void;
  chatMensajeNuevo: boolean;
  setChatMensajeNuevo: (v: boolean) => void;
  /** pantalla de bienvenida inicial a pantalla completa */
  bienvenida: boolean;
  /** con ?demo, mientras se baja y arma el campo de ejemplo: se tapa con «Abriendo el campo de ejemplo…» en vez de
   * mostrar lo que había guardado */
  cargandoEjemplo: boolean;
  /** se está mirando el campo de ejemplo: no se guarda en el navegador, así no pisa el campo propio */
  esEjemplo: boolean;
  setBienvenida: (v: boolean) => void;
  /** modal para confirmar si se borra el campo actual al tocar el logo o nuevo campo */
  confirmarNuevo: boolean;
  confirmarBorrarContorno: boolean;
  setConfirmarBorrarContorno: (v: boolean) => void;
  modalEditarCampo: boolean;
  setModalEditarCampo: (v: boolean) => void;
  editandoCampo: boolean;
  copiaEdicionCampo: { contorno?: any; secciones: any[]; area_ha?: number } | null;
  pestaniaPreviaEdicion: Pestania;
  recalculandoAnalisis: boolean;
  setRecalculandoAnalisis: (v: boolean) => void;
  iniciarEdicionCampo: (submodo?: "ver" | "secciones") => void;
  cancelarEdicionCampo: () => void;
  confirmarEdicionCampo: () => void;
  rehacerAnalisis: () => Promise<void>;
  borrarContorno: () => void;
  setConfirmarNuevo: (v: boolean) => void;
  mostrarGuiaResultados: boolean;
  setMostrarGuiaResultados: (v: boolean) => void;
  cargarZona: () => void;
  setVistaMovil: (v: "chat" | "trabajo") => void;
  setCentrar: (lat: number, lon: number, zoom?: number) => void;
  cargarHistoria: () => Promise<void>;
  /** pestaña Datos: sección elegida y si «Para el agrónomo» está abierto (se mantienen al cambiar de pestaña) */
  datosSeccion: string | null;
  setDatosSeccion: (id: string | null) => void;
  datosAgronomo: boolean;
  setDatosAgronomo: (v: boolean) => void;
  /** ventana «temporada por temporada» encima de Plan (antes era la pestaña Historia) */
  historiaAbierta: { seccion?: string; temporada?: string } | null;
  abrirHistoria: (op?: { seccion?: string; temporada?: string }) => void;
  cerrarHistoria: () => void;
  actualizarCorreccionHistoria: (temporada: string, cultivo: string) => Promise<void>;

  iniciar: () => Promise<void>;
  setPestania: (p: Pestania) => void;
  /** el mapa del Plan en 3D (la maqueta con relieve) en vez del mapa satelital plano */
  mapaPlan3D: boolean;
  setMapaPlan3D: (v: boolean) => void;
  setTemporada: (i: number) => void;
  setModoMapa: (m: Estado["modoMapa"]) => void;
  setSeccionSel: (id: string | null) => void;
  /** marca un lote sin que lo haya elegido la persona */
  setSeccionAuto: (id: string | null) => void;
  setModo: (m: "ia" | "guiado") => void;
  actualizarCampo: (cambios: Partial<Campo>) => void;
  fusionarCampo: (cambios: any) => void;
  setContorno: (g: Campo["contorno"], extra?: Partial<Campo>) => void;
  setSecciones: (s: Seccion[]) => void;
  actualizarSeccion: (id: string, cambios: Partial<Seccion>) => void;
  omitirPaso: (tipo: TipoTarjeta) => void;
  marcarTarjetaHecha: (tipo: TipoTarjeta) => void;
  reabrirPaso: (tipo: TipoTarjeta) => void;
  /** paso: la tarjeta que se contestó con palabras; el servidor saca de ahí los datos para la ficha */
  /** accion: el texto lo armó la app (una tarjeta terminada, el contorno dibujado): el servidor no llama a la IA */
  enviar: (texto: string, opciones?: { oculto?: boolean; paso?: TipoTarjeta; accion?: boolean }) => Promise<void>;
  /** contesta una tarjeta escribiendo, en vez del formulario o el archivo */
  responderConPalabras: (tipo: TipoTarjeta, texto: string) => Promise<void>;
  /** Pregunta con respuesta ya hecha (las precargadas en los ejemplos): se ve «escribiendo» un segundo y la respuesta */
  responderLocal: (pregunta: string, respuesta: string) => Promise<void>;
  elegirRotacion: (seccionId: string, rotacionId: string) => Promise<void>;
  /** reemplaza todas las elecciones de una vez («Lo de hoy» = {}, la sugerida en cada lote, la de menos erosión) */
  elegirVarias: (eleccion: Record<string, string>) => Promise<void>;
  nuevoCampo: () => void;
  importarFicha: (datos: any, opciones?: { ejemplo?: boolean }) => void;
  /** «Empezar mi campo» desde el ejemplo: vuelve al campo propio guardado, o a la bienvenida si no hay */
  salirDelEjemplo: () => void;
  cargarDemo: (cual?: string) => Promise<void>;
}

function fusion(base: any, cambios: any): any {
  if (base && typeof base === "object" && !Array.isArray(base) && cambios && typeof cambios === "object" && !Array.isArray(cambios)) {
    const out: any = { ...base };
    for (const [k, v] of Object.entries(cambios)) {
      if (k === "secciones" && Array.isArray(v) && Array.isArray(base[k])) {
        const lista: any[] = base[k].map((s: any) => ({ ...s }));
        for (const c of v as any[]) {
          const i = lista.findIndex((s) => s.id === c.id);
          if (i >= 0) lista[i] = fusion(lista[i], c);
          else lista.push(c);
        }
        out[k] = lista;
      } else out[k] = fusion(base[k], v);
    }
    return out;
  }
  return cambios;
}

export function tieneDatosCampo(campo?: Campo | null, mensajes?: MensajeUI[] | null, analisis?: any, plan?: any): boolean {
  if (!campo) return false;
  return !!(
    campo.contorno ||
    (campo.area_ha && campo.area_ha > 0) ||
    (campo.secciones && campo.secciones.length > 0) ||
    analisis ||
    plan ||
    (mensajes && mensajes.some((m) => m.rol === "productor"))
  );
}

export function hayPasoPendiente(mensajes: MensajeUI[], contorno?: any): boolean {
  return mensajes.some(
    (m) => m.tarjeta && !m.tarjeta.hecha && (m.tarjeta.tipo !== "dibujar_campo" || !contorno)
  );
}

export function flujoTerminado(analisis: Analisis | null, plan: Plan | null, mensajes: MensajeUI[], contorno?: any): boolean {
  return Boolean(analisis && plan && !hayPasoPendiente(mensajes, contorno));
}

export function crearSnapshotAnalisis(campo: Campo) {
  return {
    contornoStr: JSON.stringify(campo.contorno),
    seccionesStr: JSON.stringify(campo.secciones),
    sistemaStr: JSON.stringify(campo.sistema),
    prioridadesStr: JSON.stringify(campo.objetivos?.prioridades),
    margenesStr: JSON.stringify(campo.margenes),
    curvasDeNivel: Boolean(campo.curvas_de_nivel),
    largoPendiente: campo.largo_pendiente_m || 0,
    analisisSueloGeneralStr: JSON.stringify(campo.analisis_suelo_general),
    estacionStr: JSON.stringify(campo.estacion),
  };
}

export function esAnalisisDesactualizado(campo: Campo, analisis: Analisis | null): boolean {
  if (!analisis) return false;
  const snap = (analisis as any)._snapshot;
  if (snap) {
    if (snap.contornoStr !== JSON.stringify(campo.contorno)) return true;
    if (snap.seccionesStr !== JSON.stringify(campo.secciones)) return true;
    if (snap.sistemaStr !== JSON.stringify(campo.sistema)) return true;
    if (snap.prioridadesStr !== JSON.stringify(campo.objetivos?.prioridades)) return true;
    if (snap.margenesStr !== JSON.stringify(campo.margenes)) return true;
    if (Boolean(snap.curvasDeNivel) !== Boolean(campo.curvas_de_nivel)) return true;
    if ((snap.largoPendiente || 0) !== (campo.largo_pendiente_m || 0)) return true;
    if (snap.analisisSueloGeneralStr !== JSON.stringify(campo.analisis_suelo_general)) return true;
    if (snap.estacionStr !== JSON.stringify(campo.estacion)) return true;
    return false;
  }
  const secsCampo = campo.secciones || [];
  const secsAnalisis = analisis.secciones || [];
  if (secsCampo.length !== secsAnalisis.length) return true;
  for (const sc of secsCampo) {
    const sa = secsAnalisis.find((x) => x.id === sc.id);
    if (!sa) return true;
    if (sc.nombre !== sa.nombre) return true;
    if (Math.abs((sc.area_ha || 0) - (sa.area_ha || 0)) > 0.1) return true;
  }
  if (analisis.prioridades && campo.objetivos?.prioridades) {
    for (const [k, v] of Object.entries(analisis.prioridades)) {
      if ((campo.objetivos.prioridades as any)[k] !== v) return true;
    }
  }
  return false;
}

/** `/app?vacio` (el botón PRUEBA de la portada): borra el campo guardado y arranca de cero. Se saca el parámetro
 * de la dirección para que recargar a mitad de la prueba no vuelva a borrar. */
/** La portada pidió arrancar de cero: se tocó «Planificar mi campo» o «Abrir la herramienta». Se lee una sola vez; mientras la portada arma la página por adelantado no se lee (se mira al mostrarse, en
 * main.tsx). Lo guardado de antes se pisa con el campo nuevo en cuanto se guarda algo. */
export function pidioDeCero(): boolean {
  if ((document as Document & { prerendering?: boolean }).prerendering) return false;
  try {
    const t = Number(sessionStorage.getItem("fs:deCero") || 0);
    sessionStorage.removeItem("fs:deCero");
    return t > 0 && Date.now() - t < 15000;
  } catch {
    return false;
  }
}

function pidioVacio(): boolean {
  const q = new URLSearchParams(location.search);
  if (!q.has("vacio")) return false;
  q.delete("vacio");
  const resto = q.toString();
  history.replaceState(null, "", location.pathname + (resto ? "?" + resto : "") + location.hash);
  try {
    localStorage.removeItem(CLAVE);
  } catch {
    /* almacenamiento bloqueado: igual arranca vacío */
  }
  return true;
}

/** Los terrenos de ejemplo de la portada, con su solución armada (scripts/armar_terrenos.py). */
export const TERRENOS_EJEMPLO = ["pucon", "mosela", "lunarejo"];

/** La parte que pide un link al ejemplo (?demo&pestania=…), como la deja cargarDemo. */
function pestaniaDelEjemplo(): Pestania {
  const q = new URLSearchParams(location.search).get("pestania");
  if (!q || q === "ficha" || q === "historia" || q === "vista3d") return "plan";
  return q as Pestania;
}

// El ejemplo que se estaba mirando en esta pestaña. Recargar (F5) dejaba la herramienta vacía, porque el
// ?demo se saca de la dirección apenas carga. sessionStorage es de la pestaña: se borra
// al cerrarla, al salir del ejemplo y al entrar desde la portada para empezar de cero.
const CLAVE_EJEMPLO = "fs:ejemplo";
let ejemploAlAbrir: string | null = (() => {
  try {
    return sessionStorage.getItem(CLAVE_EJEMPLO);
  } catch {
    return null;
  }
})();
let ejemploAReabrir: string | null = null;
/** Qué ejemplo se está abriendo (?demo= o el que se reabre con F5), para la pantalla de carga. */
export function ejemploQueSeAbre(): string | null {
  return new URLSearchParams(location.search).get("demo") ?? ejemploAReabrir;
}
function recordarEjemplo(id: string | null) {
  try {
    if (id) sessionStorage.setItem(CLAVE_EJEMPLO, id);
    else sessionStorage.removeItem(CLAVE_EJEMPLO);
  } catch {
    /* sin almacenamiento */
  }
}

function cargar(): Partial<Estado> {
  if (pidioVacio() || pidioDeCero()) {
    ejemploAlAbrir = null;
    recordarEjemplo(null);
    return { bienvenida: true };
  }
  // se mira una sola vez, al abrir la página (salirDelEjemplo también llama a cargar)
  ejemploAReabrir = new URLSearchParams(location.search).has("demo") ? null : ejemploAlAbrir;
  ejemploAlAbrir = null;
  if (ejemploAReabrir) return { bienvenida: false, cargandoEjemplo: true, esEjemplo: true, pestania: "plan" };
  // Con ?demo no se lee lo guardado. El ejemplo lo reemplaza igual, y leerlo y dibujarlo congelaba la
  // página casi un segundo y mostraba medio segundo la parte vieja
  if (new URLSearchParams(location.search).has("demo")) {
    return { bienvenida: false, cargandoEjemplo: true, esEjemplo: true, pestania: pestaniaDelEjemplo() };
  }
  try {
    const t = localStorage.getItem(CLAVE);
    if (!t) return { bienvenida: true };
    const d = JSON.parse(t);
    const tiene = tieneDatosCampo(d.campo, d.mensajes, d.analisis, d.plan);
    let pestania: Pestania | undefined = d.pestania;
    if ((pestania as string) === "ficha") {
      pestania = (d.analisis || d.plan) ? "plan" : "mapa";
    }
    // la pestaña Historia pasó a una ventana encima de Plan
    const veniaDeHistoria = (pestania as string) === "historia";
    if (veniaDeHistoria) pestania = d.plan ? "plan" : d.analisis ? "comparar" : "mapa";
    const yaTerminado = flujoTerminado(d.analisis, d.plan, d.mensajes || [], d.campo?.contorno);
    if (yaTerminado && pestania === "mapa") {
      pestania = d.plan ? "plan" : "comparar";
    }
    const veniaDe3D = pestania === "vista3d";
    if (veniaDe3D) pestania = d.plan ? "plan" : "comparar";
    return {
      campo: d.campo,
      mensajes: (d.mensajes || []).map((m: MensajeUI) => ({ ...m, cargando: false, progreso: null })),
      historialApi: d.historialApi || [],
      analisis: d.analisis ? sinOpcionesFueraDeTolerancia(d.analisis, d.plan || d.analisis?.plan || null) : null,
      plan: d.plan || null,
      ...(pestania ? { pestania } : {}),
      ...(veniaDeHistoria ? { historiaAbierta: {} } : {}),
      ...(veniaDe3D ? { mapaPlan3D: true } : {}),
      bienvenida: !tiene,
    };
  } catch {
    return { bienvenida: true };
  }
}

/** Los cultivos del plan por sección, temporada por temporada, para que la historia calcule «Con este plan»
 * con el plan de verdad: {id: [["verano", "soja"], ["invierno", "trigo"], …]}. */
/** La historia ya calculada de cada campo de ejemplo (public/ejemplos), por el id del campo. */
const HISTORIA_EJEMPLO: Record<string, string> = {
  "demo-durazno-1000": "historia_demo",
  "demo-iowa-madison": "historia_us",
  "ejemplo-pucon": "historia_pucon",
  "ejemplo-mosela": "historia_mosela",
  "ejemplo-lunarejo": "historia_lunarejo",
};

export function ciclosDelPlan(plan: Plan | null): Record<string, Array<[string, string]>> | undefined {
  if (!plan?.secciones?.length || !plan.temporadas?.length) return undefined;
  const r: Record<string, Array<[string, string]>> = {};
  for (const sec of plan.secciones) {
    r[sec.seccion_id] = sec.cultivos.map((c, i) => [plan.temporadas[i]?.tipo || "verano", c] as [string, string]);
  }
  return r;
}

export function firmaCiclos(c: Record<string, Array<[string, string]>> | null | undefined): string {
  if (!c) return "";
  return Object.keys(c).sort().map((k) => `${k}:${c[k].map((x) => x.join("-")).join(",")}`).join("|");
}

function guardar(s: Estado) {
  // el ejemplo no se guarda: lo guardado sigue siendo el campo de la persona
  if (s.esEjemplo) return;
  try {
    localStorage.setItem(CLAVE, JSON.stringify({ campo: s.campo, mensajes: s.mensajes.slice(-200), historialApi: s.historialApi,
      analisis: s.analisis, plan: s.plan }));
  } catch {
    try {
      localStorage.setItem(CLAVE, JSON.stringify({ campo: s.campo, mensajes: s.mensajes.slice(-100), historialApi: s.historialApi }));
    } catch {
      /* almacenamiento lleno o bloqueado: la app sigue igual */
    }
  }
}

export const useApp = create<Estado>((set, get) => ({
  campo: campoVacio(),
  mensajes: [],
  historialApi: [],
  analisis: null,
  plan: null,
  historia: null,
  historiaCargando: false,
  historiaError: null,
  correccionesHistoria: {},
  historiaAbierta: null,
  datosSeccion: null,
  datosAgronomo: false,
  // Arranca con el catálogo que viene en la app, así el plano y las leyendas salen con colores sin
  // esperar a /api/catalogo (con el servidor dormido tardaba segundos); después se reemplaza por el del servidor
  catalogo: CATALOGO_INICIAL as unknown as Catalogo,
  ia: false,
  modo: "guiado",
  pestania: "mapa",
  mapaPlan3D: false,
  temporada: 0,
  ocupado: false,
  modoMapa: "ver",
  seccionSel: null,
  seccionAuto: false,
  vistaMovil: "chat",
  centrar: null,
  zona: { estado: "nada" },
  aviso: null,
  explorando: false,
  marcando: null,
  // ?pais=us: la herramienta abre con el mapa en EE. UU. (el link de la portada); sin link, lo elegido
  // antes, la IP o la zona horaria (mapa/paisInicial.ts)
  paisMapa: paisInicial(),
  tocandoLote: false,
  chatPlegado: { mapa: false, analisis: true, comparar: true, vista3d: true, plan: true },
  chatMensajeNuevo: false,
  bienvenida: true,
  cargandoEjemplo: false,
  esEjemplo: false,
  confirmarNuevo: false,
  confirmarBorrarContorno: false,
  modalEditarCampo: false,
  editandoCampo: false,
  copiaEdicionCampo: null,
  pestaniaPreviaEdicion: "plan",
  recalculandoAnalisis: false,
  mostrarGuiaResultados: false,
  ...cargar(),
  setAviso: (a) => set({ aviso: a }),
  setExplorando: (v) => set({ explorando: v }),
  setPaisMapa: (p) => set({ paisMapa: p, tocandoLote: false }),
  setTocandoLote: (v) => set({ tocandoLote: v }),
  setMarcando: (v) => set({ marcando: v }),
  setChatPlegado: (p, v) => set((s) => ({ chatPlegado: { ...s.chatPlegado, [p]: v }, chatMensajeNuevo: v ? s.chatMensajeNuevo : false })),
  setChatMensajeNuevo: (v) => set({ chatMensajeNuevo: v }),
  setBienvenida: (v) => set({ bienvenida: v }),
  setConfirmarNuevo: (v) => set({ confirmarNuevo: v }),
  setConfirmarBorrarContorno: (v) => set({ confirmarBorrarContorno: v }),
  setModalEditarCampo: (v) => set({ modalEditarCampo: v }),
  setRecalculandoAnalisis: (v) => set({ recalculandoAnalisis: v }),
  setMostrarGuiaResultados: (v) => set({ mostrarGuiaResultados: v }),
  iniciarEdicionCampo: (submodo) => {
    const act = get();
    const copia = {
      contorno: act.campo.contorno ? JSON.parse(JSON.stringify(act.campo.contorno)) : undefined,
      secciones: JSON.parse(JSON.stringify(act.campo.secciones || [])),
      area_ha: act.campo.area_ha,
    };
    const pestaniaPrevia = act.pestania === "mapa" ? (act.plan ? "plan" : "comparar") : act.pestania;
    set({
      editandoCampo: true,
      copiaEdicionCampo: copia,
      pestaniaPreviaEdicion: pestaniaPrevia,
      pestania: "mapa",
      modoMapa: submodo === "secciones" ? "secciones" : "ver",
      modalEditarCampo: false,
      chatPlegado: { ...act.chatPlegado, mapa: true },
      vistaMovil: "trabajo",
    });
  },
  cancelarEdicionCampo: () => {
    const { copiaEdicionCampo, pestaniaPreviaEdicion } = get();
    if (copiaEdicionCampo) {
      set((s) => ({
        campo: {
          ...s.campo,
          contorno: copiaEdicionCampo.contorno,
          secciones: copiaEdicionCampo.secciones,
          area_ha: copiaEdicionCampo.area_ha,
        },
      }));
    }
    set({
      editandoCampo: false,
      copiaEdicionCampo: null,
      pestania: pestaniaPreviaEdicion || "plan",
      modoMapa: "ver",
    });
    guardar(get());
  },
  confirmarEdicionCampo: () => {
    const { campo, copiaEdicionCampo, pestaniaPreviaEdicion, enviar } = get();
    const contornoCambio = JSON.stringify(campo.contorno) !== JSON.stringify(copiaEdicionCampo?.contorno);
    const seccionesCambio = JSON.stringify(campo.secciones) !== JSON.stringify(copiaEdicionCampo?.secciones);
    const huboCambios = contornoCambio || seccionesCambio;

    set({
      editandoCampo: false,
      copiaEdicionCampo: null,
      pestania: pestaniaPreviaEdicion || "plan",
      modoMapa: "ver",
    });
    guardar(get());

    if (huboCambios) {
      set({ recalculandoAnalisis: true });
      void enviar("analizar de nuevo", { accion: true });
    }
  },
  rehacerAnalisis: async () => {
    const { plan, pestania, enviar } = get();
    const destino = pestania === "mapa" ? (plan ? "plan" : "comparar") : pestania;
    set({
      modalEditarCampo: false,
      recalculandoAnalisis: true,
      pestania: destino,
    });
    await enviar("analizar de nuevo", { accion: true });
  },
  setVistaMovil: (v) => set({ vistaMovil: v }),
  setCentrar: (lat, lon, zoom) => set({ centrar: { lat, lon, zoom, t: Date.now() } }),

  iniciar: async () => {
    const act = get();
    if ((act.pestania as string) === "ficha") {
      set({ pestania: act.analisis || act.plan ? "plan" : "mapa" });
    }
    // con ?demo el ejemplo se baja a la vez que se pregunta al servidor, no después
    const demo = new URLSearchParams(location.search).has("demo") ? get().cargarDemo()
      : ejemploAReabrir ? get().cargarDemo(ejemploAReabrir) : null;
    try {
      const [s, c] = await Promise.all([api.salud(), api.catalogo()]);
      set({ ia: s.ia, modo: s.ia ? "ia" : "guiado", catalogo: c });
    } catch {
      set({ ia: false, modo: "guiado" });
    }
    if (demo) {
      await demo;
      return;
    }
    if (get().mensajes.length === 0) await get().enviar("__inicio", { oculto: true });
  },
  // la Vista 3D dejó de ser una parte: es el botón 2D / 3D del mapa del Plan. Lo que todavía pide
  // «vista3d» (el cartel de «Plan listo», la portada, links viejos) va al Plan con el 3D prendido.
  setPestania: (p) => set((s) => p === "vista3d"
    ? { pestania: "plan", mapaPlan3D: true, chatMensajeNuevo: !s.chatPlegado.plan ? false : s.chatMensajeNuevo }
    : { pestania: p, chatMensajeNuevo: !s.chatPlegado[p] ? false : s.chatMensajeNuevo }),
  setMapaPlan3D: (v) => set({ mapaPlan3D: v }),
  setTemporada: (i) => set({ temporada: i }),
  setModoMapa: (m) => set({ modoMapa: m }),
  setSeccionSel: (id) => set({ seccionSel: id, seccionAuto: false }),
  setSeccionAuto: (id) => set({ seccionSel: id, seccionAuto: true }),
  setModo: (m) => set({ modo: m }),
  cargarZona: () => {
    // clima y suelo del lugar en paralelo, sin frenar el chat; una vez por punto
    const u = get().campo.ubicacion;
    if (!u?.lat || !u?.lon) return;
    const punto = `${u.lat.toFixed(3)},${u.lon.toFixed(3)}`;
    if (get().zona.punto === punto && get().zona.estado !== "error") return;
    set({ zona: { estado: "cargando", punto } });
    const mismo = () => get().zona.punto === punto;
    const clima = api.clima(u.lat, u.lon).then((c) => { if (mismo()) set((s) => ({ zona: { ...s.zona, clima: c } })); });
    const suelo = api.suelo(u.lat, u.lon).then((x) => { if (mismo()) set((s) => ({ zona: { ...s.zona, suelo: x } })); });
    Promise.allSettled([clima, suelo]).then((r) => {
      if (mismo()) set((s) => ({ zona: { ...s.zona, estado: r.every((x) => x.status === "rejected") ? "error" : "listo" } }));
    });
  },
  actualizarCampo: (cambios) => {
    set((s) => ({ campo: { ...s.campo, ...cambios } }));
    guardar(get());
  },
  fusionarCampo: (cambios) => {
    set((s) => ({ campo: fusion(s.campo, cambios) }));
    guardar(get());
  },
  setContorno: (g, extra) => {
    if (!g) return;
    const [lat, lon] = puntoInterior(g);
    set((s) => ({
      campo: { ...s.campo, ...extra, contorno: g, area_ha: Math.round(areaHa(g) * 10) / 10,
        ubicacion: { ...(s.campo.ubicacion || {}), ...(extra?.ubicacion || {}), lat, lon } },
    }));
    guardar(get());
  },
  setSecciones: (secs) => {
    set((s) => {
      const campoArea = s.campo.area_ha ?? (s.campo.contorno ? Math.round(areaHa(s.campo.contorno) * 10) / 10 : undefined);
      let lista = secs.map((x) => ({ ...x, area_ha: Math.round(areaHa(x.geometria) * 10) / 10 }));
      if (campoArea && lista.length > 0) {
        const suma = lista.reduce((acc, curr) => acc + (curr.area_ha || 0), 0);
        if (suma > campoArea) {
          const exceso = Math.round((suma - campoArea) * 10) / 10;
          const ult = lista[lista.length - 1];
          const nuevoAreaUlt = Math.max(0.1, Math.round(((ult.area_ha || 0) - exceso) * 10) / 10);
          lista = [...lista.slice(0, -1), { ...ult, area_ha: nuevoAreaUlt }];
        }
      }
      return { campo: { ...s.campo, secciones: lista } };
    });
    guardar(get());
    if (secs.length > 0) void get().cargarHistoria();
  },
  actualizarSeccion: (id, cambios) => {
    set((s) => ({ campo: { ...s.campo, secciones: s.campo.secciones.map((x) => (x.id === id ? { ...x, ...cambios } : x)) } }));
    guardar(get());
  },
  omitirPaso: (tipo) => {
    set((s) => ({ campo: { ...s.campo, pasos_omitidos: Array.from(new Set([...(s.campo.pasos_omitidos || []), tipo])) } }));
    get().marcarTarjetaHecha(tipo);
  },
  marcarTarjetaHecha: (tipo) => {
    set((s) => ({ mensajes: s.mensajes.map((m) => (m.tarjeta?.tipo === tipo && !m.tarjeta.hecha ? { ...m, tarjeta: { ...m.tarjeta, hecha: true } } : m)) }));
    guardar(get());
  },
  responderLocal: async (pregunta, respuesta) => {
    if (get().ocupado) return;
    const idAsesor = nuevoId();
    set((s) => ({
      ocupado: true,
      mensajes: [...s.mensajes, { id: nuevoId(), rol: "productor", texto: pregunta }, { id: idAsesor, rol: "asesor", texto: "", cargando: true }],
    }));
    // un segundo «escribiendo», como si la pensara: al instante parecía que no había leído la pregunta
    await new Promise((r) => setTimeout(r, 1000));
    set((s) => ({
      ocupado: false,
      mensajes: s.mensajes.map((m) => (m.id === idAsesor ? { ...m, texto: respuesta, cargando: false } : m)),
      chatMensajeNuevo: s.chatPlegado[s.pestania] ? true : s.chatMensajeNuevo,
    }));
    guardar(get());
  },
  responderConPalabras: async (tipo, texto) => {
    set((s) => ({ mensajes: s.mensajes.map((m) => (m.tarjeta?.tipo === tipo && !m.tarjeta.hecha ? { ...m, tarjeta: { ...m.tarjeta, hecha: true, respuesta: texto } } : m)) }));
    await get().enviar(texto, { paso: tipo });
  },
  reabrirPaso: (tipo) => {
    const id = nuevoId();
    const msg: MensajeUI = {
      id,
      rol: "asesor",
      texto: "Podés revisar o cambiar estos datos:",
      tarjeta: { tipo, hecha: false },
    };
    set((s) => {
      const tieneRes = Boolean(s.analisis || s.plan);
      const pestaniaDestino = tieneRes ? (s.pestania === "mapa" ? (s.plan ? "plan" : "comparar") : s.pestania) : "mapa";
      return {
        mensajes: [...s.mensajes, msg],
        pestania: pestaniaDestino,
        chatPlegado: { ...s.chatPlegado, [pestaniaDestino]: false },
        vistaMovil: "chat",
        modoMapa: tipo === "secciones" ? "secciones" : s.modoMapa,
      };
    });
    guardar(get());
  },

  enviar: async (texto, opciones) => {
    if (get().ocupado) return;
    const idAsesor = nuevoId();
    const nuevos: MensajeUI[] = [];
    if (!opciones?.oculto) nuevos.push({ id: nuevoId(), rol: "productor", texto });
    nuevos.push({ id: idAsesor, rol: "asesor", texto: "", cargando: true, herramientas: [] });
    set((s) => ({ mensajes: [...s.mensajes, ...nuevos], ocupado: true }));

    const editar = (f: (m: MensajeUI) => MensajeUI) =>
      set((s) => ({ mensajes: s.mensajes.map((m) => (m.id === idAsesor ? f(m) : m)) }));
    const { campo, historialApi, modo, analisis } = get();
    try {
      // con IA viaja también el último análisis, para que el asesor pueda justificar sin recalcular
      // (el servidor puede no tenerlo: campo de ejemplo, otra instancia de Vercel)
      await flujo("/api/chat", { campo, historial: historialApi, texto, modo, idioma: useIdioma.getState().idioma, puente: puenteActivo(), analisis: modo === "ia" ? analisis : null, paso: opciones?.paso ?? null, con_analisis: !!analisis, accion: !!opciones?.accion }, (ev) => {
        switch (ev.tipo) {
          case "texto":
            editar((m) => ({ ...m, texto: m.texto + ev.delta }));
            // si el chat está plegado, avisar con el punto de mensaje nuevo sin abrirlo solo
            if (get().chatPlegado[get().pestania]) set({ chatMensajeNuevo: true });
            break;
          case "herramienta":
            editar((m) => {
              const hs = [...(m.herramientas || [])];
              const i = hs.findIndex((h) => h.nombre === ev.nombre && h.estado === "inicio");
              if (ev.estado === "fin" && i >= 0) hs[i] = { nombre: ev.nombre, estado: "fin", error: ev.error };
              else hs.push({ nombre: ev.nombre, estado: ev.estado, error: ev.error });
              return { ...m, herramientas: hs, progreso: ev.estado === "fin" ? null : m.progreso };
            });
            break;
          case "progreso":
            editar((m) => ({ ...m, progreso: { mensaje: ev.mensaje, avance: ev.avance ?? null } }));
            break;
          case "tarjeta":
            // la tarjeta va en un mensaje propio, debajo del texto del asesor
            set((s) => ({ mensajes: [...s.mensajes, { id: nuevoId(), rol: "asesor", texto: ev.mensaje || "", tarjeta: { tipo: ev.tarjeta, mensaje: ev.mensaje } }] }));
            if (ev.tarjeta === "dibujar_campo") set({ pestania: "mapa", modoMapa: "ver" });
            // el paso 2 arranca con «Dibujar un lote» (forma libre, líneas rectas) ya elegido, si todavía no hay lotes
            if (ev.tarjeta === "secciones") set({ pestania: "mapa", modoMapa: get().campo.contorno && !get().campo.secciones.length ? "secciones" : "ver" });
            break;
          case "campo_patch":
            get().fusionarCampo(ev.cambios);
            break;
          // La ventana «Análisis listo» sale con el primer análisis, no cada vez que el asesor recalcula a mitad de una
          // charla: Preguntando en el ejemplo de Iowa, se abría encima del chat mientras llegaba la
          // respuesta y la tapaba.
          case "analisis":
            set({
              // también en un campo nuevo se sacan las opciones que pierden más suelo del que aguanta
              analisis: { ...sinOpcionesFueraDeTolerancia(ev.resultado, ev.resultado.plan || null), _snapshot: crearSnapshotAnalisis(get().campo) },
              plan: ev.resultado.plan,
              temporada: 0,
              mostrarGuiaResultados: !get().analisis || get().mostrarGuiaResultados,
              recalculandoAnalisis: false,
            });
            break;
          case "plan":
            // Al recalcular desde el chat se pasa al Plan, pero el chat queda como estaba: cada pestaña
            // guarda si lo tiene abierto, y preguntando desde Datos la ventana se cerraba con la respuesta a medio llegar
            set((s) => ({ plan: ev.plan, pestania: "plan", temporada: 0, mostrarGuiaResultados: !s.plan || s.mostrarGuiaResultados,
              chatPlegado: { ...s.chatPlegado, plan: s.chatPlegado[s.pestania] } }));
            break;
          case "mensajes":
            set((s) => ({ historialApi: [...s.historialApi, ...ev.nuevos] }));
            break;
          case "error":
            editar((m) => {
              const hs = (m.herramientas || []).map((h) => (h.estado === "inicio" ? { ...h, estado: "fin" as const, error: true } : h));
              return { ...m, herramientas: hs, cargando: false, progreso: null, error: enPalabras({ message: ev.mensaje }), reintentar: opciones?.oculto ? undefined : texto };
            });
            break;
        }
      });
    } catch (e: any) {
      editar((m) => {
        const hs = (m.herramientas || []).map((h) => (h.estado === "inicio" ? { ...h, estado: "fin" as const, error: true } : h));
        return { ...m, herramientas: hs, cargando: false, progreso: null, error: enPalabras(e), reintentar: opciones?.oculto ? undefined : texto };
      });
    } finally {
      // si el asesor no escribió nada y solo mostró una tarjeta, se saca la burbuja vacía
      set((s) => ({
        ocupado: false,
        recalculandoAnalisis: false,
        mensajes: s.mensajes
          .map((m) =>
            m.id === idAsesor
              ? {
                  ...m,
                  cargando: false,
                  progreso: null,
                  herramientas: (m.herramientas || []).map((h) => (m.error && h.estado === "inicio" ? { ...h, estado: "fin" as const, error: true } : h)),
                }
              : m
          )
          .filter((m) => !(m.id === idAsesor && !m.texto && !m.error && !(m.herramientas || []).length)),
      }));
      guardar(get());
    }
  },

  elegirRotacion: async (seccionId, rotacionId) => {
    const campo = { ...get().campo, rotacion_elegida: { ...(get().campo.rotacion_elegida || {}), [seccionId]: rotacionId } };
    set({ campo });
    try {
      const a = get().analisis;
      const plan = await api.plan(campo, undefined, a ? { secciones: a.secciones, temporadas: a.plan.temporadas } : undefined);
      set((s) => ({ plan, analisis: s.analisis ? { ...s.analisis, plan } : s.analisis }));
    } catch (e: any) {
      alertaSuave(enPalabras(e, "No se pudo rearmar el plan"));
    }
    guardar(get());
  },

  elegirVarias: async (eleccion) => {
    const campo = { ...get().campo, rotacion_elegida: { ...eleccion } };
    set({ campo });
    try {
      const a = get().analisis;
      const plan = await api.plan(campo, undefined, a ? { secciones: a.secciones, temporadas: a.plan.temporadas } : undefined);
      set((s) => ({ plan, analisis: s.analisis ? { ...s.analisis, plan } : s.analisis }));
    } catch (e: any) {
      alertaSuave(enPalabras(e, "No se pudo rearmar el plan"));
    }
    guardar(get());
  },

  borrarContorno: () => {
    const c = get().campo;
    const campoLimpio: Campo = {
      id: c.id,
      nombre: c.nombre,
      ubicacion: c.ubicacion ? { ...c.ubicacion, padron: undefined, origen: undefined } : undefined,
      secciones: [],
    };
    const msgId = nuevoId();
    const nuevosMensajes: MensajeUI[] = [
      {
        id: msgId,
        rol: "asesor",
        texto: "Borré el contorno del campo. Podés volver a marcarlo en el mapa, buscar por padrón o subir un archivo.",
        tarjeta: { tipo: "dibujar_campo" },
      },
    ];
    set({
      campo: campoLimpio,
      mensajes: nuevosMensajes,
      historialApi: [],
      analisis: null,
      plan: null,
      historia: null,
      historiaCargando: false,
      historiaError: null,
      correccionesHistoria: {},
      pestania: "mapa",
      temporada: 0,
      modoMapa: "contorno",
      seccionSel: null,
      marcando: null,
      confirmarBorrarContorno: false,
      editandoCampo: false,
      copiaEdicionCampo: null,
      chatPlegado: { ...get().chatPlegado, mapa: false },
    });
    guardar(get());
  },

  nuevoCampo: () => {
    set({
      campo: campoVacio(),
      mensajes: [],
      historialApi: [],
      analisis: null,
      plan: null,
      historia: null,
      historiaCargando: false,
      historiaError: null,
      correccionesHistoria: {},
      pestania: "mapa",
      temporada: 0,
      seccionSel: null,
      explorando: false,
      bienvenida: true,
      esEjemplo: false,
      confirmarNuevo: false,
  confirmarBorrarContorno: false,
  mostrarGuiaResultados: false,
    });
    guardar(get());
    void get().enviar("__inicio", { oculto: true });
  },
  setDatosSeccion: (id) => set({ datosSeccion: id }),
  setDatosAgronomo: (v) => set({ datosAgronomo: v }),
  abrirHistoria: (op) => set({ historiaAbierta: op || {} }),
  cerrarHistoria: () => set({ historiaAbierta: null }),
  cargarHistoria: async () => {
    const { campo, historiaCargando, correccionesHistoria } = get();
    if (historiaCargando || !campo.secciones || campo.secciones.length === 0) return;
    set({ historiaCargando: true, historiaError: null });

    const ciclos = ciclosDelPlan(get().plan);
    // Para los campos de ejemplo sin correcciones usamos el JSON real precalculado para respuesta instantánea,
    // siempre que se haya calculado con el mismo plan que se está mirando. También los otros cuatro
    // ejemplos (antes solo Durazno; los demás esperaban 1 a 4,5 s al servidor cada vez que se abrían). Los archivos
    // son lo que contesta /api/historia para cada ejemplo: si cambia el plan de un ejemplo hay que volver a guardarlos
    // (si no coinciden, se le pide al servidor como siempre).
    const guardada = HISTORIA_EJEMPLO[campo.id];
    if (guardada && (!correccionesHistoria || Object.keys(correccionesHistoria).length === 0)) {
      try {
        const r = await fetch(`/ejemplos/${guardada}.json`);
        if (r.ok) {
          const js = await r.json();
          if (firmaCiclos(js.ciclos_plan) === firmaCiclos(ciclos)) {
            set({ historia: js, historiaCargando: false });
            return;
          }
        }
      } catch {
        // Fallback a la API normal
      }
    }

    try {
      const res = await api.historia(campo, undefined, correccionesHistoria, ciclos);
      set({ historia: res, historiaCargando: false });
    } catch (e: any) {
      set({ historiaError: enPalabras(e, "No se pudo cargar la historia del campo"), historiaCargando: false });
    }
  },
  actualizarCorreccionHistoria: async (temporada: string, cultivo: string) => {
    const { campo, correccionesHistoria } = get();
    const nuevas = { ...(correccionesHistoria || {}), [temporada]: cultivo };
    set({ correccionesHistoria: nuevas, historiaCargando: true });
    try {
      const res = await api.historia(campo, undefined, nuevas, ciclosDelPlan(get().plan));
      set({ historia: res, historiaCargando: false });
    } catch (e: any) {
      alertaSuave(enPalabras(e, "No se pudo recalcular con la corrección"));
      set({ historiaCargando: false });
    }
  },
  cargarDemo: async (cual) => {
    try {
      // ?demo=pucon|mosela|lunarejo: los terrenos de ejemplo de la portada; ?demo=us: el campo de Iowa; ?demo solo, el de Durazno
      const qDemo = new URLSearchParams(location.search).get("demo");
      const pedido = cual || (["us", "eeuu", "iowa"].includes(qDemo || "") ? "us"
        : qDemo && TERRENOS_EJEMPLO.includes(qDemo) ? qDemo : "uy");
      const r = await fetch(pedido === "us" ? "/ejemplos/campo_demo_eeuu.fieldshift.json"
        : TERRENOS_EJEMPLO.includes(pedido) ? `/ejemplos/terreno_${pedido}.fieldshift.json` : "/ejemplos/campo_demo.fieldshift.json");
      // el relieve 3D ya calculado del ejemplo, a la vez que el ejemplo; si no está o falla, lo calcula el servidor
      const relieveListo = fetch(`/ejemplos/relieve_${pedido}.json`).then((x) => (x.ok ? x.json() : null)).catch(() => null);
      // y la foto satelital que va encima del relieve, que también está en el proyecto: se empieza a bajar ya
      const fotoRelieve = `/ejemplos/foto_${pedido}.jpg`;
      pedirFoto(fotoRelieve);
      // y el código del visor 3D: los ejemplos abren en el Plan con el relieve girando
      adelantarVisor3D();
      const ficha = await r.json();
      // se baja ya, pero se dibuja cuando terminó el fundido desde la portada: si no, el fundido se traba
      // Si la portada está armando esta página por adelantado (el mouse apoyado en el botón del ejemplo),
      // todavía no hay fundido que cuidar ni nadie mirando: se arma todo ya, y al tocar aparece el Plan hecho
      const adelantado = armandoPorAdelantado();
      if (!adelantado) await finDelFundido();
      // se le da hasta 0,4 s más al relieve: si llega, el 3D abre ya dibujado; si no, se pide como siempre
      const relieveGuardado = await Promise.race([relieveListo, new Promise<null>((ok) => setTimeout(() => ok(null), armandoPorAdelantado() ? 4000 : 400))]);
      get().importarFicha(ficha, { ejemplo: true });
      { const st = get(); if (relieveGuardado && st.analisis) sembrarRelieve(st.campo, st.analisis, relieveGuardado, fotoRelieve); }
      // qué ejemplo se está mirando (para F5) se anota recién cuando la página se muestra: apoyar el mouse no deja rastro
      if (armandoPorAdelantado()) document.addEventListener("prerenderingchange", () => { if (get().esEjemplo) recordarEjemplo(pedido); }, { once: true });
      else recordarEjemplo(pedido);
      set((s) => ({
        analisis: s.analisis ? { ...s.analisis, _snapshot: crearSnapshotAnalisis(s.campo) } : null,
      }));
      void get().cargarHistoria();
      const q = new URLSearchParams(location.search).get("pestania");
      // ?pestania=historia (links viejos): Plan con la ventana de la historia abierta
      const p = q === "ficha" || q === "historia" ? (get().analisis ? "plan" : "mapa") : (q as Pestania | null);
      // los ejemplos abren en el Plan con el relieve 3D girando; con ?pestania= se respeta la parte pedida
      set({ pestania: p === "vista3d" ? "plan" : p || "plan", mapaPlan3D: !p || p === "vista3d" || p === "plan", temporada: 0, seccionSel: null, vistaMovil: "trabajo", bienvenida: false, confirmarNuevo: false,
        ...(q === "historia" ? { historiaAbierta: {} } : {}), cargandoEjemplo: false });
      // ya está cargado: se saca ?demo (y ?pestania) de la dirección. Si quedaba, «Empezar de nuevo»
      // dejaba la bienvenida escondida y el mapa esperando lejos, y recargar o ir atrás y adelante volvía a cargar
      // el ejemplo encima de lo que la persona estaba haciendo.
      const resto = new URLSearchParams(location.search);
      resto.delete("demo");
      resto.delete("pestania");
      const r2 = resto.toString();
      history.replaceState(history.state, "", location.pathname + (r2 ? "?" + r2 : "") + location.hash);
    } catch (e: any) {
      set({ cargandoEjemplo: false });
      alertaSuave(enPalabras(e, "No se pudo cargar el ejemplo"));
    }
  },
  importarFicha: (d, opciones) => {
    if (!d || !d.campo) return;
    // una ficha importada es el campo de la persona y se guarda; el ejemplo no (ver guardar)
    set({ esEjemplo: !!opciones?.ejemplo });
    const yaTerminado = flujoTerminado(d.analisis, d.plan || d.analisis?.plan, d.mensajes || [], d.campo?.contorno);
    const snap = d.analisis?._snapshot || (d.campo ? crearSnapshotAnalisis(d.campo) : undefined);
    set((s) => ({
      campo: d.campo,
      mensajes: d.mensajes || [],
      historialApi: d.historialApi || [],
      analisis: d.analisis ? { ...sinOpcionesFueraDeTolerancia(d.analisis, d.plan || d.analisis?.plan || null), _snapshot: snap } : null,
      plan: d.plan || d.analisis?.plan || null,
      pestania: yaTerminado && s.pestania === "mapa" ? (d.plan ? "plan" : "comparar") : s.pestania,
    }));
    guardar(get());
  },
  salirDelEjemplo: () => {
    // lo guardado es el campo propio (el ejemplo nunca se guardó): se vuelve a leer, y si no hay, bienvenida
    const guardado = cargar();
    set({
      campo: campoVacio(),
      mensajes: [],
      historialApi: [],
      analisis: null,
      plan: null,
      historia: null,
      historiaCargando: false,
      historiaError: null,
      historiaAbierta: null,
      correccionesHistoria: {},
      pestania: "mapa",
      mapaPlan3D: false,
      temporada: 0,
      seccionSel: null,
      explorando: false,
      confirmarNuevo: false,
      mostrarGuiaResultados: false,
      ...guardado,
      esEjemplo: false,
    });
    if (get().mensajes.length === 0) void get().enviar("__inicio", { oculto: true });
  },
}));

function alertaSuave(msg: string) {
  useApp.setState({ aviso: msg });
}

export function crearSeccion(geometria: any, nombre: string, extra?: Partial<Seccion>): Seccion {
  return { id: "s" + nuevoId().slice(0, 6), nombre, geometria, ...extra };
}

export function colorCultivo(cat: Catalogo | null, cod: string): string {
  return cat?.cultivos.find((c) => c.codigo === cod)?.color || "#999";
}

const CORTOS: Record<string, string> = {
  soja: "Soja 1ª", soja2: "Soja 2ª", maiz: "Maíz 1ª", maiz2: "Maíz 2ª", sorgo: "Sorgo", sorgo_forrajero: "Sorgo forrajero",
  girasol: "Girasol", trigo: "Trigo", cebada: "Cebada", colza: "Colza", cobertura: "Cobertura", verdeo: "Verdeo",
  pradera: "Pradera", alfalfa: "Alfalfa", campo_natural: "Campo natural", barbecho: "Barbecho",
};

export function nombreCorto(cod: string): string {
  return CORTOS[cod] || cod;
}

export function nombreCultivo(cat: Catalogo | null, cod: string, corto = false): string {
  const n = cat?.cultivos.find((c) => c.codigo === cod)?.nombre || cod;
  if (!corto) return n;
  return n.split(" (")[0].replace("Cultivo de cobertura", "Cobertura").replace("Verdeo de invierno", "Verdeo");
}

if (import.meta.env.DEV) (window as any).__app = useApp; // para las pruebas en el navegador

// El país del campo abierto, para los textos que cambian entre Uruguay y EE. UU. (i18n/region.ts)
function regionDelCampo(c: Estado["campo"]): Region {
  if (c?.ubicacion) return regionDe(c.ubicacion.lat, c.ubicacion.lon);
  const anillo = (c?.contorno as any)?.coordinates?.[0];
  const p = Array.isArray(anillo?.[0]?.[0]) ? anillo[0][0] : anillo?.[0];
  return Array.isArray(p) ? regionDe(p[1], p[0]) : "";
}
useRegion.getState().setRegion(regionDelCampo(useApp.getState().campo));
// la IP corrige lo adivinado por la zona horaria, solo mientras no hay campo (con campo, manda el campo)
void corregirPorIP((p) => {
  const s = useApp.getState();
  if (!s.campo.contorno && !s.esEjemplo && s.paisMapa !== p) s.setPaisMapa(p);
});
useApp.subscribe((s, antes) => {
  // se dejó el ejemplo (Empezar mi campo, empezar de cero, importar una ficha): recargar ya no lo vuelve a abrir
  if (antes.esEjemplo && !s.esEjemplo) recordarEjemplo(null);
  if (s.campo !== antes.campo) {
    const r = regionDelCampo(s.campo);
    if (r !== useRegion.getState().region) useRegion.getState().setRegion(r);
    // un campo de EE. UU. (el ejemplo de Iowa, uno cargado) deja el mapa en EE. UU.; uno de Uruguay, en Uruguay
    if ((r === "US" || r === "UY") && r !== s.paisMapa) useApp.setState({ paisMapa: r });
  }
});
