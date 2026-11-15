import type { Catalogo, Campo, Plan, RangoErosion } from "./tipos";

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detalle = `${r.status}`;
    try {
      const j = await r.json();
      detalle = j.detail || detalle;
    } catch {
      /* sin cuerpo */
    }
    throw new Error(detalle);
  }
  return r.json() as Promise<T>;
}

/** Prueba con un asistente externo contestando el chat (modo puente): se abre con ?puente=1 y queda para esta pestaña. */
export function puenteActivo(): boolean {
  try {
    if (new URLSearchParams(location.search).has("puente")) sessionStorage.setItem("fieldshift:puente", "1");
    return sessionStorage.getItem("fieldshift:puente") === "1";
  } catch {
    return false;
  }
}

type Riesgos = { prob_seca: number | null; prob_helada_agro: number | null; prob_calor: number | null };
export interface ResultadoEscenario {
  lluvia_pct: number;
  temp_c: number;
  periodo: string | null;
  lluvia_anual_mm: { hoy: number; escenario: number };
  et0_anual_mm: { hoy: number; escenario: number };
  cultivos: Array<{ cultivo: string; nombre: string; hoy: Riesgos; escenario: Riesgos }>;
  metodo: string;
  limites: string[];
}

export interface ResultadoSmap {
  estado: "listo" | "pendiente" | "sin_cuenta" | "error";
  motivo?: string;
  ok?: boolean;
  fuente?: string;
  desde?: string;
  hasta?: string;
  meses_en_comun?: number;
  correlacion?: number;
  acuerdo?: string;
  ahora?: { hasta: string; percentil: number; texto: string } | null;
  mensual?: Array<{ mes: string; smap_m3m3: number; app_fraccion: number; smap_anomalia: number; app_anomalia: number; gldas_anomalia?: number | null }>;
  gldas?: {
    correlacion?: number | null;
    meses_comunes?: number;
    frase_secas?: string;
    coinciden_secas?: boolean;
    seca_2008?: { gldas_min: number | null; app_min: number | null };
    seca_2022?: { gldas_min: number | null; app_min: number | null };
  } | null;
  gldas_fuente?: string | null;
  limites?: string[];
}

export interface ComparacionDescubierto {
  ok: boolean;
  motivo?: string;
  anios: number;
  meses: number;
  metodos: Array<{ id: string; nombre: string; corte: number | null; meses_por_anio: number | null; aplica?: boolean; separacion?: number; promedio_grupo_bajo?: number }>;
  coincidencia_pct: number | null;
  kappa: number | null;
  distintos: Array<{ anio: number; mes: number; ndvi: number; fijo: boolean; auto: boolean }>;
  lectura: string;
}

export interface TemporadaHistUI {
  temporada: string;
  tipo: "invierno" | "verano";
  anio_agricola: number;
  es_estrella: boolean;
  cultivo_real: {
    codigo: string;
    nombre: string;
    origen: "contado" | "corregido" | "detectado" | "cdl" | "sin_datos";
    eta_etc: number | null;
    dias_estres: number | null;
    modelo_dijo_seca: boolean;
  };
  clima: {
    lluvia_mm: number;
    lluvia_normal_mm: number;
    anomalia_lluvia_pct: number;
    dias_calor: number;
    dias_helada: number;
    r_temporada: number;
    dias_erosivos: number;
  };
  satelite: {
    ndvi_max: number | null;
    ndvi_min: number | null;
    ndvi_integrado: number | null;
    mediana_historica: number | null;
    anomalia_ndvi_pct: number | null;
    estres_satelite: boolean;
    uso_detectado?: string | null;
  };
  propuesta: {
    codigo: string;
    nombre: string;
    eta_etc: number | null;
    dias_estres: number | null;
  };
  relato: string;
}

export interface SeccionHistoriaUI {
  seccion_id: string;
  nombre: string;
  area_ha: number;
  grupo_coneat?: string;
  hay_satelite?: boolean;
  temporadas: TemporadaHistUI[];
  total_temporadas: number;
  validacion: {
    total_evaluadas: number;
    aciertos: number;
    coincidencia_pct: number;
    kappa: number;
    wilson_ic_80: [number, number];
    tabla_contingencia: {
      ambos_estres: number;
      ambos_normal: number;
      modelo_alerta_satelite_bien: number;
      modelo_bien_satelite_bajo: number;
    };
    frase: string;
  };
}

export interface FechaClaveEcostress {
  fecha: string;
  hora_local: string;
  evento: string;
  temperatura_media_c: number;
  temperatura_min_c: number;
  temperatura_max_c: number;
  rango_intralote_c: number;
  desvio_estandar_c: number;
  interpretacion: string;
}

export interface DiagnosticoEcostress {
  fuente: string;
  sensor?: string;
  resolucion_espacial: string;
  diagnostico_campo?: {
    pasadas_totales_orbita: number;
    pasadas_con_dato_valido: number;
    pasadas_con_nube_o_corte: number;
    porcentaje_util: number;
    cobertura_temporal: string;
  };
  fechas_clave_ejemplo: FechaClaveEcostress[];
  conclusion: string;
  estado_productos?: Record<string, string>;
}

export interface ResultadoHistoria {
  campo_id: string;
  nombre: string;
  ubicacion: { lat: number; lon: number };
  periodo_analizado: string;
  /** los cultivos del plan con que se calculó «Con este plan» (null si no se mandó plan) */
  ciclos_plan?: Record<string, Array<[string, string]>> | null;
  estado_satelite?: string;
  mensaje_satelite?: string;
  secciones: SeccionHistoriaUI[];
  caso_estrella?: {
    temporada: string;
    titulo: string;
    subtitulo: string;
    declaratoria_oficial: string;
    declaratoria_rotulo?: string;
    datos_durazno: {
      lluvia_verano_mm: number;
      lluvia_normal_verano_mm: number;
      anomalia_lluvia_pct: number;
      dias_calor_extremo_35c: number;
      caida_ndvi_pct?: number;
      caida_nacional_soja_diea: string;
      caida_nacional_maiz_diea?: string;
      rinde_rotulo?: string;
      rinde_valor?: string;
      rinde_fuente?: string;
      fuente_diea_url?: string;
    };
    impacto_en_tu_campo: string;
    aporte_rotacion_propuesta: string;
  } | null;
  resumen_global: {
    total_secciones: number;
    temporadas_por_seccion: number;
    coincidencia_global_pct: number;
    aciertos_globales: number;
    total_evaluadas: number;
    frase: string;
  };
}

// los departamentos (157 KB) se piden una sola vez y los comparten el mapa y los caminos: antes Caminos.ts los pedía
// de nuevo aparte
let departamentosPedido: Promise<any> | null = null;
let estadosUsPedido: Promise<any> | null = null;
const condadosUsPedidos = new Map<string, Promise<any>>();

export const api = {
  salud: () => fetch(puenteActivo() ? "/api/salud?puente=1" : "/api/salud").then((r) => json<{ ok: boolean; ia: boolean; modelo: string | null }>(r)),
  catalogo: () => fetch("/api/catalogo").then((r) => json<Catalogo>(r)),
  departamentos: () => (departamentosPedido ||= fetch("/api/departamentos").then((r) => json<any>(r)).catch((e) => { departamentosPedido = null; throw e; })),
  // EE. UU. (límites del Census y el lote del Cropland Data Layer)
  estadosUs: () => (estadosUsPedido ||= fetch("/api/estados-us").then((r) => json<any>(r)).catch((e) => { estadosUsPedido = null; throw e; })),
  condadosUs: (fips: string) => {
    if (!condadosUsPedidos.has(fips)) {
      condadosUsPedidos.set(fips, fetch(`/api/condados-us/${fips}`).then((r) => json<any>(r)).catch((e) => { condadosUsPedidos.delete(fips); throw e; }));
    }
    return condadosUsPedidos.get(fips)!;
  },
  loteCdl: (lat: number, lon: number) =>
    fetch("/api/lote-cdl", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lat, lon }) })
      .then((r) => json<{ contorno: any; area_ha: number; anios: Array<{ anio: number; nombre_cdl: string }> }>(r)),
  padron: (departamento: string, numero: number) =>
    fetch(`/api/padron?departamento=${encodeURIComponent(departamento)}&numero=${numero}`).then((r) => json<any>(r)),
  hls: (oeste: number, sur: number, este: number, norte: number) =>
    fetch(`/api/hls?oeste=${oeste}&sur=${sur}&este=${este}&norte=${norte}`).then((r) => json<{ fechas: any[] }>(r)),
  suelosArea: (geometria: unknown) =>
    fetch("/api/suelos-area", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ geometria }) }).then((r) => json<{ partes: Array<{ grupo_coneat: string; fraccion: number; geometria: any }> }>(r)),
  /** Baja de antemano el clima, el suelo y el verdor de cada sección (backend plan.precalentar): se llama al
   * confirmar las secciones y no se espera; así el análisis del final tarda ~1 s en vez de ~17 s. */
  precalentar: (campo: { contorno?: unknown; secciones?: Array<{ id: string; geometria: unknown }> }) =>
    fetch("/api/precalentar", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campo: { contorno: campo.contorno, secciones: (campo.secciones || []).map((s) => ({ id: s.id, geometria: s.geometria })) } }) })
      .then(() => undefined).catch(() => undefined),
  proponerPartes: (geometria: unknown) =>
    fetch("/api/proponer-partes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ geometria }) })
      .then((r) => json<{ ok: boolean; motivo?: string; aviso?: string; fechas?: Array<{ fecha: string; satelite: string }>;
        partes?: Array<{ nombre: string; ha: number; como_se_ve: string; geometria: any }> }>(r)),
  clima: (lat: number, lon: number) =>
    fetch("/api/clima", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lat, lon }) }).then((r) => json<any>(r)),
  escenario: (p: { lat: number; lon: number; agua_util_mm: number; lluvia_pct: number; temp_c: number; cultivos: string[] }) =>
    fetch("/api/escenario", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) }).then((r) => json<ResultadoEscenario>(r)),
  rangoErosion: (erosiones: unknown[], r_alternativas: Array<number | null>) =>
    fetch("/api/rango-erosion", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ erosiones, r_alternativas }) })
      .then((r) => json<{ rangos: Array<RangoErosion | null>; supuestos: string[] }>(r)),
  descubierto: (mensual: Array<{ anio: number; mes: number; ndvi: number }>) =>
    fetch("/api/descubierto", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mensual }) }).then((r) => json<ComparacionDescubierto>(r)),
  smap: (lat: number, lon: number, agua_util_mm: number) =>
    fetch(`/api/smap?lat=${lat}&lon=${lon}&agua_util_mm=${agua_util_mm}`).then((r) => json<ResultadoSmap>(r)),
  ecostress: () => fetch("/api/ecostress").then((r) => json<DiagnosticoEcostress>(r)),
  suelo: (lat: number, lon: number) =>
    fetch("/api/suelo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lat, lon }) }).then((r) => json<any>(r)),
  archivo: (archivo: File, tipo_esperado?: string, punto?: { lat: number; lon: number }) => {
    const fd = new FormData();
    fd.append("archivo", archivo);
    if (tipo_esperado) fd.append("tipo_esperado", tipo_esperado);
    if (punto) {
      fd.append("lat", String(punto.lat));
      fd.append("lon", String(punto.lon));
    }
    return fetch("/api/archivo", { method: "POST", body: fd }).then((r) => json<any>(r));
  },
  plan: (campo: Campo, eleccion?: Record<string, string>, base?: { secciones: unknown[]; temporadas: unknown[] }) =>
    fetch("/api/plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ campo, eleccion, ...(base || {}) }) }).then((r) => json<Plan>(r)),
  historia: (campo: Campo, seccion_id?: string, correcciones?: Record<string, string>, ciclos_plan?: Record<string, Array<[string, string]>>) =>
    fetch("/api/historia", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campo, seccion_id, correcciones, ciclos_plan }),
    }).then((r) => json<ResultadoHistoria>(r)),
};

/** POST que devuelve Server-Sent Events: llama a `alEvento` con cada objeto. */
export async function flujo(ruta: string, cuerpo: unknown, alEvento: (ev: any) => void, señal?: AbortSignal) {
  const r = await fetch(ruta, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
    signal: señal,
  });
  if (!r.ok || !r.body) {
    throw new Error(`El servidor respondió ${r.status}`);
  }
  const lector = r.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await lector.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n\n")) >= 0) {
      const bloque = buffer.slice(0, i);
      buffer = buffer.slice(i + 2);
      for (const linea of bloque.split("\n")) {
        if (linea.startsWith("data: ")) {
          try {
            alEvento(JSON.parse(linea.slice(6)));
          } catch {
            /* línea incompleta */
          }
        }
      }
    }
  }
}
