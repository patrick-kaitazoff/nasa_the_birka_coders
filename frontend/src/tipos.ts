import type { Geometry, Polygon, MultiPolygon } from "geojson";

export type Geo = Polygon | MultiPolygon;

export interface AnioHistorial {
  anio: number;
  invierno?: string | null;
  verano?: string | null;
}

export interface AnalisisSuelo {
  nombre?: string;
  ph?: number;
  materia_organica?: number;
  carbono_organico?: number;
  fosforo_bray?: number;
  potasio?: number;
  arena?: number;
  limo?: number;
  arcilla?: number;
  profundidad?: string;
  agua_util_mm?: number;
}

export interface Seccion {
  id: string;
  nombre: string;
  geometria: Geo;
  area_ha?: number;
  grupo_coneat?: string;
  historial?: AnioHistorial[];
  problemas?: string[];
  notas?: string;
  analisis_suelo?: AnalisisSuelo;
}

export interface Prioridades {
  suelo?: number;
  agua?: number;
  clima?: number;
  ingreso?: number;
  forraje?: number;
  simplicidad?: number;
  diversificacion?: number;
}

export interface Campo {
  id: string;
  nombre?: string;
  ubicacion?: { lat: number; lon: number; departamento?: string; padron?: number; origen?: string; pais?: string; estado?: string; condado?: string };
  contorno?: Geo;
  area_ha?: number;
  secciones: Seccion[];
  sistema?: {
    tipo?: "agricola" | "ganadero" | "mixto";
    ganado?: boolean;
    cabezas?: number;
    vende_forraje?: boolean; // fardos, silo o pastoreo a terceros: el forraje rinde aunque no haya ganado propio
    riego?: boolean;
    maquinaria?: string;
    tenencia?: "propio" | "arrendado";
    anios_contrato?: number;
    renta_kg?: number; // kilos de soja por hectárea y año
    seguro_seca?: boolean | null;
    vende_futuro?: boolean | null;
  };
  experiencia?: { anios?: number; texto?: string; que_funciono?: string; que_fallo?: string };
  objetivos?: { corto_plazo?: string; largo_plazo?: string; pct_agricola?: number; prioridades?: Prioridades };
  restricciones?: { cultivos_excluidos?: string[]; plan_uso_mgap?: boolean; notas?: string };
  margenes?: Record<string, number>;
  detalle_margenes?: Record<string, { rinde?: number; precio?: number; costo?: number }>;
  analisis_suelo_general?: AnalisisSuelo;
  // referencia: una estación pública lejana (la de INUMET del ejemplo), que no cambia los riesgos
  estacion?: { archivo?: string; comparacion?: Record<string, any>; mensual?: any[]; referencia?: { nombre: string; distancia_km: number } };
  pasos_omitidos?: string[];
  rotacion_elegida?: Record<string, string>;
  largo_pendiente_m?: number;
  curvas_de_nivel?: boolean;
  partes_suelo?: Array<{ grupo_coneat: string; geometria: Geo }>;
}

export interface CultivoInfo {
  codigo: string;
  nombre: string;
  temporada: string;
  color: string;
  icono: string;
  siembra: string;
  ciclo_dias: number;
  forraje: number;
  notas: string;
  aportes?: string[];
}

export interface RotacionInfo {
  id: string;
  nombre: string;
  descripcion: string;
  tipo: string;
  anios: [string, string][];
}

export interface Catalogo {
  cultivos: CultivoInfo[];
  rotaciones: RotacionInfo[];
  departamentos: string[];
  aportes?: Record<string, { nombre: string; explicacion: string }>;
}

export interface Explicacion {
  por_que: string[];
  evidencia: string[];
  beneficios: string[];
  huecos: string[];
  riesgos: string[];
}

export interface Evaluacion {
  id: string;
  nombre: string;
  descripcion: string;
  tipo: string;
  anios: [string, string][];
  es_actual?: boolean;
  puntaje_total: number;
  puntajes: Record<string, number>;
  erosion: {
    a_t_ha: number; tolerancia_t: number; ratio: number; cumple: boolean;
    /** false en campo natural: el Plan de Uso no se exige ahí; en análisis viejos no viene */
    exigible?: boolean;
    r: number; k: number; ls: number; c: number; p: number; pendiente_pct: number;
    rango?: RangoErosion | null;
  };
  cobertura_mensual: number[];
  meses_descubierto: string[];
  ventana_peligro: string[];
  riesgo: {
    seca: number; helada: number; calor: number; deficit_medio: number | null;
    /** rinde que se pierde por falta de agua (FAO-33) y cuánto menos rinde un año seco, 1 de cada 5, que uno normal */
    perdida_media?: number | null; perdida_anio_seco?: number | null; caida_anio_seco?: number | null;
    por_cultivo: Array<{ cultivo: string; nombre: string; prob_seca?: number; prob_helada?: number; prob_calor?: number;
      ventana_agua?: string; ventana_helada?: string; ventana_calor?: string }>;
  };
  ingreso: { usa_margenes: boolean; usd_ha_anio: number | null; usd_ha_anio_con_riesgo: number | null; indice_relativo: number | null;
    renta_kg?: number | null; renta_usd_ha?: number | null; precio_soja?: number | null; usd_ha_anio_despues_de_renta?: number | null;
    equilibrios?: Array<{ cultivo: string; nombre: string; kg_ha: number; rinde_esperado?: number | null }>; margenes_estimados?: string[] };
  forraje: number;
  carbono: { indice: number; tendencia: string; meses_raices_vivas: number };
  alertas: string[];
  explicacion?: Explicacion;
}

export interface SeccionAnalizada {
  id: string;
  nombre: string;
  area_ha: number;
  punto: [number, number];
  suelo: Record<string, any>;
  ndvi: {
    fuente?: string;
    metodos?: import("./api").ComparacionDescubierto;
    mensual?: Array<{ anio: number; mes: number; ndvi: number }>;
    temporadas?: Array<{ temporada: string; ndvi_max: number; ndvi_min: number; uso_detectado: string }>;
    descubierto_por_anio?: Array<{ anio: number; meses_descubierto: number; meses: number[] }>;
    umbrales?: { descubierto: number; cultivo: number };
    error?: string;
    hls?: {
      ok: boolean;
      mensual?: Array<{ anio: number; mes: number; ndvi: number }>;
      correlacion?: number | null;
      dif_media?: number | null;
      coincidencia_pct?: number | null;
      meses_comunes?: number;
      fuente?: string;
      error?: string;
      desde_cache?: boolean;
    };
  };
  agua_util_mm: number;
  agua_util_origen: string;
  analisis_suelo: { hay_analisis: boolean; notas: string[]; alertas: string[] };
  problemas: string[];
  actual: Evaluacion | null;
  alternativas: Evaluacion[];
  todas: Array<{ id: string; nombre: string; puntaje_total: number; puntajes: Record<string, number>; erosion: Evaluacion["erosion"]; riesgo?: { seca: number } }>;
  recomendada_id: string | null;
  nota_tolerancia?: string | null;
  /** En cuántos de cada 100 juegos de pesos parecidos a los del productor sale primera cada opción que
   * podía recomendarse (la recomendada es la que más) */
  aceptabilidad?: Record<string, number> | null;
  /** lo peor y lo mejor del lote en cada criterio (escala por lote) */
  escala_lote?: Record<string, [number, number]> | null;
}

export interface Temporada {
  tipo: "verano" | "invierno";
  anio: number;
  etiqueta: string;
}

export interface Plan {
  temporadas: Temporada[];
  secciones: Array<{ seccion_id: string; seccion: string; area_ha: number; rotacion_id: string; rotacion: string; fase: number; cultivos: string[];
    /** en qué temporadas se siembra o se renueva la pastura, y cuándo es la próxima */
    siembras?: Array<"siembra" | "renovación" | null>; proxima_siembra?: string | null;
    /** la sugerida de la sección, aparte de lo elegido: el plan arranca en lo de hoy y elige el productor */
    sugerida_id?: string | null; sugerida?: string | null; elegida?: boolean }>;
  resumen_temporadas: Array<Temporada & { area_por_cultivo: Record<string, number>; pct_cubierto: number; ha_forraje: number }>;
  erosion_media_plan: number;
  erosion_media_actual: number;
  erosion_media_sugerida?: number;
  /** en un campo mixto: cuánto agrícola queda con las sugeridas y, si no llega a la meta, por qué */
  equilibrio?: { meta: number; pct_sugerido: number; nota: string | null } | null;
}

export interface TormentasInfo {
  umbral_mm: number;
  umbral_grande_mm: number;
  por_anio: number;
  por_mes: number[];
  meses_pico: string[];
  anios_sin: number;
  anio_mas: { anio: number; cuantas: number };
  grandes: number;
  cada_anios_grande: number | null;
  maxima: { mm: number; fecha: string };
  periodo: string;
  anios: number;
  fuente: string;
}

export interface Analisis {
  generado: string;
  centro: { lat: number; lon: number };
  clima: any & { tormentas?: TormentasInfo | null };
  factor_r: { usado: number; mgap: any; nasa: number; fuente: string; medido?: { r: number; fuente?: string } | null };
  secciones: SeccionAnalizada[];
  plan: Plan;
  prioridades: Prioridades;
  fuentes: Array<{ nombre: string; url: string; uso: string }>;
}

export type TipoTarjeta =
  | "dibujar_campo" | "secciones" | "datos_sistema" | "historial_seccion" | "problemas"
  | "subir_analisis_suelo" | "subir_estacion" | "subir_historial" | "prioridades" | "margenes";

export interface MensajeUI {
  id: string;
  rol: "productor" | "asesor" | "sistema";
  texto: string;
  /** respuesta: lo que escribió con sus palabras en vez de llenar el formulario */
  tarjeta?: { tipo: TipoTarjeta; mensaje?: string | null; hecha?: boolean; respuesta?: string };
  herramientas?: Array<{ nombre: string; estado: "inicio" | "fin"; error?: boolean }>;
  progreso?: { mensaje: string; avance?: number | null } | null;
  error?: string;
  /** texto a volver a mandar si falló (botón "Probar de nuevo") */
  reintentar?: string;
  cargando?: boolean;
  /** lugares encontrados al escribir un pueblo, una calle o «ruta 5 km 200» en el paso 1 (mapa/BuscarLugar.tsx) */
  lugares?: LugarEncontrado[];
}

export type LugarEncontrado = { nombre: string; departamento: string | null; lat: number; lon: number; tipo: "ruta" | "localidad" | "calle" | "lugar"; zoom: number };

export type Pestania = "mapa" | "analisis" | "comparar" | "vista3d" | "plan";

export type GeometriaCualquiera = Geometry;

/** Rango de la erosión por Monte Carlo (analisis/incertidumbre.py del backend). */
export interface RangoErosion { p10: number; p50: number; p90: number; prob_supera_t: number; simulaciones: number }
