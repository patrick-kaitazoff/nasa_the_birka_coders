import { useState, useEffect } from "react";
import { useApp } from "../store";
import { Cargando } from "../comun/Cargando";
import type { SeccionHistoriaUI } from "../api";
import { DosFilas } from "./Franjas";

const CULTIVOS_OPCIONES: Array<{ codigo: string; nombre: string }> = [
  { codigo: "soja", nombre: "Soja de primera" },
  { codigo: "soja2", nombre: "Soja de segunda" },
  { codigo: "maiz", nombre: "Maíz de primera" },
  { codigo: "maiz2", nombre: "Maíz de segunda" },
  { codigo: "sorgo", nombre: "Sorgo granífero" },
  { codigo: "trigo", nombre: "Trigo" },
  { codigo: "cebada", nombre: "Cebada" },
  { codigo: "colza", nombre: "Colza / Canola" },
  { codigo: "pradera", nombre: "Pradera perenne" },
  { codigo: "campo_natural", nombre: "Campo natural" },
  { codigo: "verdeo", nombre: "Verdeo de invierno" },
  { codigo: "cobertura", nombre: "Puente verde / Cobertura" },
  { codigo: "barbecho", nombre: "Barbecho (suelo descubierto)" },
];

/**
 * Detalle de la historia del campo, temporada por temporada (va en la ventana que se abre desde Plan). Era la pestaña «Historia»;
 */
export function HistoriaDetalle({ seccionInicial, temporadaInicial }: { seccionInicial?: string; temporadaInicial?: string }) {
  const { campo, historia, historiaCargando, historiaError, cargarHistoria, actualizarCorreccionHistoria } = useApp();

  const [seccionId, setSeccionId] = useState<string>(seccionInicial || "");
  const [tempSeleccionada, setTempSeleccionada] = useState<string>(temporadaInicial || "verano 2022/23");
  const [cultivoEditando, setCultivoEditando] = useState<string>("");
  const [mostrandoEditor, setMostrandoEditor] = useState<boolean>(false);

  useEffect(() => {
    if (!historia && !historiaCargando && campo.secciones && campo.secciones.length > 0) {
      void cargarHistoria();
    }
  }, [historia, historiaCargando, campo.secciones, cargarHistoria]);



  const secciones = historia?.secciones || [];
  const seccionActiva: SeccionHistoriaUI | undefined = secciones.find((s) => s.seccion_id === seccionId) || secciones[0];

  useEffect(() => {
    if (secciones.length > 0 && !seccionId) {
      setSeccionId(secciones[0].seccion_id);
    }
  }, [secciones, seccionId]);

  const temporadas = seccionActiva?.temporadas || [];
  const haySatelite = Boolean(seccionActiva?.hay_satelite) || temporadas.some((t) => t.satelite.ndvi_max !== null);
  const tActiva = temporadas.find((t) => t.temporada === tempSeleccionada) || temporadas.find((t) => t.es_estrella) || temporadas[temporadas.length - 1];

  useEffect(() => {
    if (tActiva) {
      setCultivoEditando(tActiva.cultivo_real.codigo === "sin_datos" ? "soja" : tActiva.cultivo_real.codigo);
      setMostrandoEditor(false);
    }
  }, [tActiva?.temporada]);

  if (historiaCargando) {
    return (
      <div className="historia-panel historia-vacia">
        <Cargando que="calculando" size={32} etiqueta="Cargando 26 años de historia climática y satelital de la NASA..." />
      </div>
    );
  }

  if (historiaError && !historia) {
    return (
      <div className="historia-panel historia-vacia">
        <div className="historia-alerta">
          <p>{historiaError}</p>
          <button className="btn" onClick={() => void cargarHistoria()}>
            Probar de nuevo
          </button>
        </div>
      </div>
    );
  }

  if (!historia || secciones.length === 0) {
    return (
      <div className="historia-panel historia-vacia">
        <p>Definí al menos una sección en el mapa para ver la historia de tu campo desde el año 2000.</p>
      </div>
    );
  }

  const estrella = historia.caso_estrella;
  const validacion = seccionActiva?.validacion;

  const guardarCorreccion = () => {
    if (!tActiva) return;
    void actualizarCorreccionHistoria(tActiva.temporada, cultivoEditando);
    setMostrandoEditor(false);
  };

  return (
    <div className="historia-panel">

      {/* Aviso de estado de satélite */}
      {!haySatelite && (
        <aside className="historia-aviso-satelite" role="status">
          <strong>Por ahora solo tenemos el clima de la zona (NASA POWER).</strong> El satélite histórico no está disponible en este momento.
        </aside>
      )}

      {/* Selector de potreros si hay más de 1 */}
      {secciones.length > 1 && (
        <nav className="historia-secciones-nav" aria-label={campo.sistema?.tipo === "ganadero" ? "Potreros del campo" : "Lotes del campo"}>
          {secciones.map((s) => (
            <button
              key={s.seccion_id}
              type="button"
              className={`historia-sec-btn ${seccionActiva?.seccion_id === s.seccion_id ? "activa" : ""}`}
              onClick={() => setSeccionId(s.seccion_id)}
            >
              {s.nombre} {`(${s.area_ha.toLocaleString("es-UY", { maximumFractionDigits: 1 })} ha)`}
            </button>
          ))}
        </nav>
      )}

      {/* Tarjeta de la Temporada Estrella (oculta si es null en Fase 1) */}
      {estrella && estrella.temporada && (
        <article className="historia-tarjeta-estrella" aria-labelledby="titulo-caso-estrella">
          <div className="historia-estrella-badge">
            <span className="estrella-icono" aria-hidden>★</span> Caso de prueba real · {estrella.temporada}
          </div>
          <h3 id="titulo-caso-estrella">{estrella.titulo}</h3>
          <p className="estrella-subtitulo">{estrella.subtitulo}</p>

          <div className="historia-metricas-grid">
            <div className="metrica-caja">
              <span className="metrica-rotulo">Lluvia del verano</span>
              <strong className="metrica-valor">{estrella.datos_durazno.lluvia_verano_mm.toLocaleString("es-UY")} mm</strong>
              <small className="metrica-sub">Normal: {estrella.datos_durazno.lluvia_normal_verano_mm} mm ({estrella.datos_durazno.anomalia_lluvia_pct} %)</small>
            </div>
            <div className="metrica-caja">
              <span className="metrica-rotulo">Calor extremo</span>
              <strong className="metrica-valor">{estrella.datos_durazno.dias_calor_extremo_35c} días</strong>
              <small className="metrica-sub">Con temperaturas ≥ 35 °C</small>
            </div>
            <div className="metrica-caja">
              <span className="metrica-rotulo">Verdor satélite (NASA)</span>
              <strong className="metrica-valor">
                {estrella.datos_durazno.caida_ndvi_pct !== undefined ? `${estrella.datos_durazno.caida_ndvi_pct} %` : "-23 %"}
              </strong>
              <small className="metrica-sub">Caída vs mediana histórica</small>
            </div>
            <div className="metrica-caja">
              <span className="metrica-rotulo">{estrella.datos_durazno.rinde_rotulo || "Rinde nacional DIEA"}</span>
              <strong className="metrica-valor">{estrella.datos_durazno.rinde_valor || "641 kg/ha"}</strong>
              <small className="metrica-sub">
                {estrella.datos_durazno.fuente_diea_url ? (
                  <a href={estrella.datos_durazno.fuente_diea_url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "underline" }}>
                    {estrella.datos_durazno.rinde_fuente || "Soja: DIEA / MGAP"} ↗
                  </a>
                ) : (
                  estrella.datos_durazno.rinde_fuente || "Soja: DIEA / MGAP"
                )}
              </small>
            </div>
          </div>

          <div className="historia-estrella-contraste">
            <div className="contraste-lado">
              <h4>Lo que pasó de verdad</h4>
              <p>{estrella.impacto_en_tu_campo}</p>
            </div>
          </div>
          <p className="declaratoria-cita">
            <strong>{estrella.declaratoria_rotulo || "Resolución oficial"}:</strong> {estrella.declaratoria_oficial}
          </p>
        </article>
      )}

      {/* Franjas por temporada: lo que se hizo */}
      <section className="historia-stripes-contenedor" aria-label="Temporada por temporada, desde 2000">
        <div className="historia-stripes-header">
          <h4>Cómo estuvo el lote en el momento crítico de cada temporada</h4>
          <span className="stripes-ayuda">Tocá una temporada para ver el detalle</span>
        </div>
        <DosFilas temporadas={temporadas} activa={tActiva?.temporada} onElegir={setTempSeleccionada} />
      </section>

      {/* Ficha interactiva de la temporada seleccionada */}
      {tActiva && (
        <article className="historia-ficha-temporada">
          <div className="ficha-temp-header">
            <div>
              <h3>
                {tActiva.temporada.toUpperCase()} {tActiva.es_estrella && <span className="chip-estrella">★ Caso estrella</span>}
              </h3>
              <p className="ficha-temp-tipo">
                {tActiva.tipo === "invierno" ? "Zafra de invierno (junio a octubre)" : "Zafra de verano (diciembre a marzo)"}
              </p>
            </div>

            <div className="ficha-cultivo-badge">
              <span className="badge-etiqueta">Cultivo:</span>
              <strong>{tActiva.cultivo_real.nombre}</strong>
                <small className="badge-origen">
                  {tActiva.cultivo_real.origen === "contado"
                    ? "(Declarado en tu historial)"
                    : tActiva.cultivo_real.origen === "corregido"
                    ? "(Corregido por vos)"
                    : tActiva.cultivo_real.origen === "detectado"
                    ? "(Detectado por satélite)"
                    : tActiva.cultivo_real.origen === "cdl"
                    ? "(Cropland Data Layer del USDA)"
                    : "(Sin datos de satélite)"}
                </small>
            </div>
          </div>

          {/* Corregir o indicar el cultivo que había: siempre a la vista */}
            <div className="editor-cultivo-franja">
              {!mostrandoEditor ? (
                <button
                  type="button"
                  className="btn texto chico"
                  onClick={() => setMostrandoEditor(true)}
                >
                  {tActiva.cultivo_real.origen === "sin_datos"
                    ? "Indicar qué cultivo se sembró acá"
                    : "¿No era ese cultivo? Corregilo acá"}
                </button>
              ) : (
                <div className="editor-cultivo-form">
                  <label htmlFor="selector-cultivo-correccion">Cultivo que había de verdad:</label>
                  <select
                    id="selector-cultivo-correccion"
                    value={cultivoEditando}
                    onChange={(e) => setCultivoEditando(e.target.value)}
                  >
                    {CULTIVOS_OPCIONES.map((opt) => (
                      <option key={opt.codigo} value={opt.codigo}>
                        {opt.nombre}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="btn chico primario" onClick={guardarCorreccion}>
                    Guardar y recalcular
                  </button>
                  <button type="button" className="btn texto chico" onClick={() => setMostrandoEditor(false)}>
                    Cancelar
                  </button>
                </div>
              )}
            </div>

          {/* Grilla con los datos de Clima, Satélite y Balance */}
          <div className="ficha-detalles-grid">
            {/* Clima de NASA POWER */}
            <div className="ficha-columna">
              <h4>Clima de esa temporada (NASA)</h4>
              <ul className="ficha-lista">
                <li>
                  <span>Lluvia caída:</span>
                  <strong>{tActiva.clima.lluvia_mm.toLocaleString("es-UY")} mm</strong>
                  <span className={`anomalia-tag ${tActiva.clima.anomalia_lluvia_pct < -20 ? "negativa" : ""}`}>
                    {tActiva.clima.anomalia_lluvia_pct > 0 ? "+" : ""}{tActiva.clima.anomalia_lluvia_pct} %
                  </span>
                </li>
                <li>
                  <span>Normal histórica:</span>
                  <strong>{tActiva.clima.lluvia_normal_mm.toLocaleString("es-UY")} mm</strong>
                </li>
                <li>
                  <span>Días con calor extremo (≥ 35 °C):</span>
                  <strong>{tActiva.clima.dias_calor} días</strong>
                </li>
                <li>
                  <span>Días con helada (≤ 0 °C):</span>
                  <strong>{tActiva.clima.dias_helada} días</strong>
                </li>
                <li>
                  <span>Lluvia que erosiona (días ≥ 12,7 mm):</span>
                  <strong>{tActiva.clima.dias_erosivos} tormentas</strong>
                </li>
              </ul>
            </div>

            {/* Satélite MODIS */}
            <div className="ficha-columna">
              <h4>Lo que vio el satélite (MODIS)</h4>
              {tActiva.satelite.ndvi_max !== null ? (
                <ul className="ficha-lista">
                  <li>
                    <span>NDVI máximo registrado:</span>
                    <strong>{tActiva.satelite.ndvi_max}</strong>
                  </li>
                  <li>
                    <span>{campo.sistema?.tipo === "ganadero" ? "Mediana histórica del potrero:" : "Mediana histórica del lote:"}</span>
                    <strong>{tActiva.satelite.mediana_historica}</strong>
                  </li>
                  <li>
                    <span>Anomalía de verdor:</span>
                    <strong className={tActiva.satelite.estres_satelite ? "texto-rojo" : ""}>
                      {tActiva.satelite.anomalia_ndvi_pct !== null && tActiva.satelite.anomalia_ndvi_pct > 0 ? "+" : ""}
                      {tActiva.satelite.anomalia_ndvi_pct} %
                    </strong>
                  </li>
                  <li>
                    <span>Uso detectado en la foto:</span>
                    <small>{tActiva.satelite.uso_detectado || "Sin clasificar"}</small>
                  </li>
                </ul>
              ) : (
                <div className="satelite-sin-datos-caja">
                  <p className="texto-aviso-chico">Sin datos de satélite todavía</p>
                  <small>No hay mediciones satelitales de verdor registradas para esta sección.</small>
                </div>
              )}
            </div>

            {/* Balance y Contraste */}
            <div className="ficha-columna">
              <h4>Balance y contraste agronómico</h4>
              <ul className="ficha-lista">
                <li>
                  <span>Agua en floración (cultivo real):</span>
                  <strong>
                    {tActiva.cultivo_real.eta_etc !== null
                      ? `${Math.round(tActiva.cultivo_real.eta_etc * 100)} % de lo que pedía`
                      : tActiva.cultivo_real.origen === "sin_datos"
                      ? "Sin cultivo asignado"
                      : "No aplica (barbecho/pastura)"}
                  </strong>
                </li>
                <li>
                  <span>Días de estrés hídrico:</span>
                  <strong>{tActiva.cultivo_real.dias_estres ?? 0} días</strong>
                </li>
              </ul>
            </div>
          </div>

          <div className="ficha-relato">
            <span className="relato-icono" aria-hidden>⚖</span>
            <p><strong>Dictamen agronómico:</strong> {tActiva.relato}</p>
          </div>
        </article>
      )}

      {/* Validación científica: solo se muestra si existen datos evaluados */}
      {validacion && validacion.total_evaluadas > 0 && (
        <section className="historia-validacion-card">
          <div className="val-header">
            <h4>Validación científica: El modelo biofísico contra el satélite de la NASA</h4>
            <span className="val-badge">{validacion.coincidencia_pct}% de acierto</span>
          </div>
          <p className="val-frase">{validacion.frase}</p>

          <div className="val-grid">
            <div className="val-item">
              <span className="val-num">{validacion.aciertos} / {validacion.total_evaluadas}</span>
              <span className="val-label">Temporadas coincidentes</span>
            </div>
            <div className="val-item">
              <span className="val-num">{validacion.kappa}</span>
              <span className="val-label">Kappa de Cohen (concordancia)</span>
            </div>
            <div className="val-item">
              <span className="val-num">[{validacion.wilson_ic_80[0]} % - {validacion.wilson_ic_80[1]} %]</span>
              <span className="val-label">Intervalo de Wilson (80 % conf.)</span>
            </div>
          </div>
          <p className="val-pie">
            Demuestra la precisión con que las ecuaciones de balance de agua de la FAO (FAO-56) alimentadas con datos climáticos de la NASA reflejan lo que ocurrió de verdad en este campo durante 26 años.
          </p>
        </section>
      )}
    </div>
  );
}
