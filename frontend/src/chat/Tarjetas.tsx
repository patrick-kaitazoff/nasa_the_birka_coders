import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { nombreCultivo, useApp } from "../store";
import { UbicarCampo } from "../mapa/UbicarCampo";
import { PanelSecciones } from "../mapa/PanelSecciones";
import { revisarDivisiones } from "../mapa/revision";
import type { AnalisisSuelo, AnioHistorial, MensajeUI, Prioridades, TipoTarjeta } from "../tipos";
import { enPalabras } from "../errores";
import { Cargando } from "../comun/Cargando";
import { useRegion } from "../i18n/region";
import { buAcAKgHa, HA_A_AC, kgHaABuAc, usdBuAUsdT, usdTAUsdBu } from "../i18n/unidades";

const TITULOS: Record<TipoTarjeta, string> = {
  dibujar_campo: "Ubicación y contorno del campo",
  secciones: "Secciones del campo",
  datos_sistema: "Cómo trabajás el campo",
  historial_seccion: "Qué se sembró en cada sección",
  problemas: "Tu experiencia en el campo",
  subir_analisis_suelo: "Análisis de suelo",
  subir_estacion: "Estación meteorológica",
  subir_historial: "Archivo de historial",
  prioridades: "Prioridades y planes",
  margenes: "Márgenes por cultivo",
};

const ICONOS: Record<TipoTarjeta, string> = {
  dibujar_campo: "M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z M9 3v15 M15 6v15",
  secciones: "M4 4h16v16H4z M4 12h16 M12 4v16",
  datos_sistema: "M3 21h18 M5 21V9l7-5 7 5v12 M9 21v-6h6v6",
  historial_seccion: "M4 5h16 M4 12h16 M4 19h16 M8 3v4 M16 10v4 M10 17v4",
  problemas: "M12 3l9 16H3z M12 10v4 M12 17h.01",
  subir_analisis_suelo: "M5 20h14 M7 20c0-6 2-9 5-12 3 3 5 6 5 12 M12 8v12",
  subir_estacion: "M12 3v10 M8 7h8 M6 21h12 M12 13a4 4 0 1 0 0.01 0",
  subir_historial: "M4 4h12l4 4v12H4z M8 12h8 M8 16h6",
  prioridades: "M4 7h10 M18 7h2 M4 17h4 M12 17h8 M14 5v4 M8 15v4",
  margenes: "M12 3v18 M16 7c0-2-2-3-4-3s-4 1-4 3 2 3 4 3 4 1 4 3-2 3-4 3-4-1-4-3",
};

function Icono({ d }: { d: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function norm(s: string) {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/** Busca la sección que corresponde a un nombre de un archivo ("Potrero 2", "P2", "Lote 2"). */
export function emparejarSeccion(nombre: string | undefined, secciones: Array<{ id: string; nombre: string }>) {
  if (!nombre) return null;
  const n = norm(nombre);
  const exacta = secciones.find((s) => norm(s.nombre) === n);
  if (exacta) return exacta;
  const num = n.match(/\d+/)?.[0];
  if (num) {
    const porNum = secciones.filter((s) => norm(s.nombre).match(/\d+/)?.[0] === num);
    if (porNum.length === 1) return porNum[0];
  }
  return secciones.find((s) => n.includes(norm(s.nombre)) || norm(s.nombre).includes(n)) || null;
}

/** El orden de la entrevista guiada (backend, guiado.PASOS). "Paso N de M" chico arriba de cada tarjeta
 * (GOV.UK: un indicador simple alcanza) y "si lo tenés" en lo que no es imprescindible. */
// sin «subir_estacion»: no es un paso de la entrevista, se abre si la persona dice que mide la lluvia
const ORDEN_PASOS: string[] = ["dibujar_campo", "secciones", "datos_sistema", "historial_seccion", "problemas", "subir_analisis_suelo", "prioridades", "margenes"];
const SI_LO_TENES = new Set(["subir_analisis_suelo", "subir_estacion", "margenes"]);
// las que se pueden contestar escribiendo. Ubicar el
// campo y dividirlo en secciones van en el mapa: ahí escribir el lugar ya funciona en el chat.
const CON_PALABRAS = new Set<TipoTarjeta>(["datos_sistema", "historial_seccion", "problemas", "subir_analisis_suelo", "subir_estacion", "subir_historial", "prioridades", "margenes"]);
const EJEMPLO_PALABRAS: Partial<Record<TipoTarjeta, string>> = {
  datos_sistema: "Por ejemplo: «es mixto, unas 80 vacas, el campo es arrendado por 3 años más»",
  historial_seccion: "Por ejemplo: «en La Loma hice trigo y soja de segunda los últimos 3 años»",
  problemas: "Por ejemplo: «El Bajo se anega cuando llueve mucho y la soja ahí siempre rinde poco»",
  subir_analisis_suelo: "Por ejemplo: «pH 6,1, materia orgánica 3,4 %, fósforo 12 ppm»",
  subir_estacion: "Por ejemplo: «este año llovieron unos 1.100 mm y tuve tres heladas fuertes en julio»",
  subir_historial: "Por ejemplo: «2023 trigo y soja, 2024 maíz, 2025 cobertura y soja»",
  prioridades: "Por ejemplo: «me importa cuidar el suelo y que sea simple; no quiero soja»",
  margenes: "Por ejemplo: «soja 280, maíz 220, trigo 90 dólares por hectárea»",
};

/** «O contámelo con tus palabras»: un cuadro para escribir la respuesta en vez del formulario. Lo que escriba va al
 * asistente, que saca de ahí los datos para la ficha; sin la IA, se toma lo que se entiende y lo demás queda anotado. */
function ConPalabras({ tipo }: { tipo: TipoTarjeta }) {
  const { responderConPalabras, ocupado } = useApp();
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);
  const id = `con-palabras-${tipo}`;
  useEffect(() => {
    if (abierto) area.current?.focus();
  }, [abierto]);
  if (!abierto) {
    return (
      <button type="button" className="btn texto chico con-palabras-abrir" onClick={() => setAbierto(true)}>
        O contámelo con tus palabras
      </button>
    );
  }
  const mandar = () => {
    const t = texto.trim();
    if (!t || ocupado) return;
    void responderConPalabras(tipo, t);
  };
  return (
    <div className="con-palabras">
      <label htmlFor={id}>Contámelo como me lo dirías a mí</label>
      <textarea
        id={id}
        ref={area}
        rows={3}
        value={texto}
        placeholder={EJEMPLO_PALABRAS[tipo]}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            mandar();
          }
        }}
      />
      <div className="con-palabras-acciones">
        <button type="button" className="btn texto chico" onClick={() => { setAbierto(false); setTexto(""); }}>Volver al formulario</button>
        <button type="button" className="btn primario chico" disabled={!texto.trim() || ocupado} onClick={mandar}>Enviar</button>
      </div>
    </div>
  );
}

export function Tarjeta({ m }: { m: MensajeUI }) {
  const t = m.tarjeta!;
  const { campo, marcarTarjetaHecha, omitirPaso, enviar, ocupado, setModoMapa, setConfirmarBorrarContorno } = useApp();
  const hechaCalculada = t.tipo === "dibujar_campo" ? !!campo.contorno : !!t.hecha;
  const terminar = (texto: string) => {
    marcarTarjetaHecha(t.tipo);
    void enviar(texto, { accion: true });
  };
  const omitir = (texto: string) => {
    omitirPaso(t.tipo);
    void enviar(texto, { accion: true });
  };
  const props = { terminar, omitir, ocupado };
  const panelALaVista = usePanelDelMapaALaVista();

  return (
    <div className={`tarjeta ${hechaCalculada ? "hecha" : ""}`}>
      <div className="tarjeta-titulo">
        <span className="icono"><Icono d={ICONOS[t.tipo]} /></span>
        {TITULOS[t.tipo]}
        {!hechaCalculada && SI_LO_TENES.has(t.tipo) && <span className="etq-suave">si lo tenés</span>}
        {hechaCalculada ? <span className="etq bien" style={{ marginLeft: "auto" }}>Hecho</span>
          : ORDEN_PASOS.includes(t.tipo) && <span className="paso-n">Paso {ORDEN_PASOS.indexOf(t.tipo) + 1} de {ORDEN_PASOS.length}</span>}
      </div>
      {t.mensaje && <div className="tarjeta-sub">{t.mensaje}</div>}
      {hechaCalculada ? (
        t.respuesta ? <div className="con-palabras-hecha"><span>Lo contaste con tus palabras:</span> <q>{t.respuesta}</q></div> : <ResumenHecho tipo={t.tipo} />
      ) : (
        <>
          {t.tipo === "dibujar_campo" && <UbicarCampo compacto alListo={(x) => terminar(x)} />}
          {t.tipo === "secciones" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {panelALaVista ? (
                <div className="tarjeta-sub" style={{ marginTop: 0 }}>
                  Se arman en el panel del mapa, a la izquierda: dibujándolas o con el campo entero como una sola.
                </div>
              ) : (
                <>
                  <div className="tarjeta-sub" style={{ marginTop: 0 }}>
                    Las secciones se ven en el mapa; podés dibujarlas ahí.
                  </div>
                  <PanelSecciones />
                </>
              )}
              {campo.secciones.length > 0 && (
                <button
                  className="btn primario grande"
                  style={{ width: "100%", padding: "10px 14px", fontWeight: 600 }}
                  onClick={() => {
                    setModoMapa("ver");
                    // mientras sigue la entrevista, el servidor ya baja el suelo y el verdor de cada lote
                    void api.precalentar(campo);
                    terminar(`Listo, dividí el campo en ${campo.secciones.length} secciones: ${campo.secciones.map((s) => `${s.nombre} (${Math.round(s.area_ha || 0)} ha)`).join(", ")}.`);
                  }}
                >
                  {campo.secciones.length === 1
                    ? "Listo, continuar con 1 sección →"
                    : `Listo, continuar con las ${campo.secciones.length} secciones →`}
                </button>
              )}
              <button
                className="btn texto chico"
                style={{ color: "var(--texto-3)", fontSize: "12px", alignSelf: "flex-start", marginTop: 4 }}
                onClick={() => setConfirmarBorrarContorno(true)}
              >
                ¿Te equivocaste en el contorno? Borrar y marcar de nuevo
              </button>
            </div>
          )}
          {t.tipo === "datos_sistema" && <FormSistema {...props} />}
          {t.tipo === "historial_seccion" && <FormHistorial {...props} />}
          {t.tipo === "problemas" && <FormProblemas {...props} />}
          {t.tipo === "subir_analisis_suelo" && <FormSuelo {...props} />}
          {t.tipo === "subir_estacion" && <FormEstacion {...props} />}
          {t.tipo === "subir_historial" && <FormArchivoHistorial {...props} />}
          {t.tipo === "prioridades" && <FormPrioridades {...props} />}
          {t.tipo === "margenes" && <FormMargenes {...props} />}
          {CON_PALABRAS.has(t.tipo) && <ConPalabras tipo={t.tipo} />}
        </>
      )}
    </div>
  );
}

/** El panel del mapa (ubicar el campo, armar las secciones) se ve al lado del chat: pantalla grande, pestaña
 * Mapa y el chat ya al costado. Ahí la tarjeta del chat no repite sus botones. En el celular o con el chat adelante, la tarjeta sigue teniendo todo. */
function usePanelDelMapaALaVista() {
  const { pestania, campo, modoMapa, explorando } = useApp();
  const [grande, setGrande] = useState(() => window.matchMedia("(min-width: 961px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 961px)");
    const f = () => setGrande(mq.matches);
    mq.addEventListener("change", f);
    return () => mq.removeEventListener("change", f);
  }, []);
  const inicio = !campo.contorno && modoMapa === "ver" && !explorando;
  return grande && pestania === "mapa" && !inicio;
}

function ResumenHecho({ tipo }: { tipo: TipoTarjeta }) {
  const { campo, setConfirmarBorrarContorno } = useApp();
  if (tipo === "dibujar_campo") {
    return (
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div className="hecho-ok">{`✓ Campo de ${campo.area_ha?.toLocaleString("es-UY")} ha cargado`}</div>
        <button
          className="btn texto chico"
          style={{ color: "var(--rojo, #b3412e)", fontSize: "12px", padding: "2px 6px" }}
          onClick={() => setConfirmarBorrarContorno(true)}
        >
          Borrar contorno y marcar de nuevo
        </button>
      </div>
    );
  }
  if (tipo === "secciones") {
    const avisos = campo.secciones.length ? revisarDivisiones(campo) : [];
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {/* cada nombre en su propio nodo, para que el traductor reconozca «Campo entero» o «Lote 2» */}
        <div className="hecho-ok"><span>
          {campo.secciones.length === 1 ? "✓ 1 sección:" : `✓ ${campo.secciones.length} secciones:`}
          {campo.secciones.map((s, i) => <span key={s.id}>{i ? ", " : " "}<span>{s.nombre}</span>{` (${Math.round(s.area_ha || 0)} ha)`}</span>)}
        </span></div>
        {avisos.length > 0 && (
          <div className="revision" style={{ marginTop: 4, background: "rgba(0,0,0,0.02)", padding: "8px 10px", borderRadius: 8 }}>
            <b style={{ fontSize: 12 }}>Mirando tus divisiones:</b>
            <ul style={{ margin: "4px 0 0", paddingLeft: 16, fontSize: 12 }}>
              {avisos.map((x, i) => (
                <li key={i} className={`rev-${x.tipo}`}>
                  {x.seccion ? <><b>{x.seccion}</b> {x.texto}</> : x.texto}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }
  return <div className="hecho-ok">✓ Guardado en la ficha del campo</div>;
}

interface PropsForm {
  terminar: (t: string) => void;
  omitir: (t: string) => void;
  ocupado: boolean;
}

// ----------------------------------------------------------------- sistema
function FormSistema({ terminar }: PropsForm) {
  const { campo, actualizarCampo } = useApp();
  const [tipo, setTipo] = useState<"agricola" | "ganadero" | "mixto">(campo.sistema?.tipo || "agricola");
  const [cabezas, setCabezas] = useState(String(campo.sistema?.cabezas || ""));
  const [tenencia, setTenencia] = useState<"propio" | "arrendado">(campo.sistema?.tenencia || "propio");
  const [anios, setAnios] = useState(String(campo.sistema?.anios_contrato || ""));
  // En EE. UU. la renta se carga en bushels de soja por acre; el campo la sigue guardando en kg por ha
  const us = useRegion((r) => r.region === "US");
  const [renta, setRenta] = useState(campo.sistema?.renta_kg ? String(us ? Math.round(kgHaABuAc(campo.sistema.renta_kg, "soja")) : campo.sistema.renta_kg) : "");
  const rentaKg = renta ? (us ? Math.round(buAcAKgHa(+renta, "soja")) : +renta) : undefined;
  const [riego, setRiego] = useState(campo.sistema?.riego ?? false);
  const [vende, setVende] = useState(campo.sistema?.vende_forraje ?? false);
  const tri = (v: boolean | null | undefined) => (v === true ? "si" : v === false ? "no" : "");
  const [seguro, setSeguro] = useState(tri(campo.sistema?.seguro_seca));
  const [futuro, setFuturo] = useState(tri(campo.sistema?.vende_futuro));
  const deTri = (v: string) => (v === "si" ? true : v === "no" ? false : null);
  const [pct, setPct] = useState(campo.objetivos?.pct_agricola ?? 50);
  const [curvas, setCurvas] = useState(!!campo.curvas_de_nivel);
  // «Largo típico de la pendiente» se sacó. Desde el
  // La erosión saca el largo de ladera de cada lote del relieve de la NASA (SRTM); si no puede, usa 100 m

  function guardar() {
    const sistema = { tipo, ganado: tipo !== "agricola", cabezas: tipo !== "agricola" && cabezas ? +cabezas : undefined, tenencia,
      anios_contrato: tenencia === "arrendado" && anios ? +anios : undefined,
      renta_kg: tenencia === "arrendado" ? rentaKg : undefined, riego, vende_forraje: vende,
      seguro_seca: deTri(seguro), vende_futuro: deTri(futuro) };
    actualizarCampo({
      sistema,
      curvas_de_nivel: curvas,
      objetivos: { ...(campo.objetivos || {}), pct_agricola: tipo === "mixto" ? pct : tipo === "agricola" ? 100 : 0 }
    });
    const partes = [
      // cada pedazo, sin comas adentro: el traductor parte la frase en las comas y busca cada pedazo en el diccionario
      tipo === "agricola" ? "Es un campo agrícola" : tipo === "ganadero" ? "Es un campo ganadero" : `Es un campo mixto (más o menos ${pct} % agrícola)`,
      sistema.ganado ? `con ganado${cabezas ? ` (${cabezas} cabezas)` : ""}` : "sin ganado",
      ...(vende ? ["vendo forraje"] : []),
      tenencia === "propio" ? "propio" : "arrendado",
      ...(tenencia !== "propio" && anios ? [anios === "1" ? "por 1 año más" : `por ${anios} años más`] : []),
      // en kg aunque se haya cargado en bushels: la pantalla lo vuelve a pasar a bushels (i18n/unidades.ts)
      ...(tenencia !== "propio" && rentaKg ? [`con renta de ${rentaKg} kg de soja`] : []),
      riego ? "con riego" : "sin riego",
      ...(curvas ? ["siembro en curvas de nivel o terrazas"] : []),
      ...(seguro === "si" ? ["con seguro de seca"] : seguro === "no" ? ["sin seguro de seca"] : []),
      ...(futuro === "si" ? ["vendo parte a futuro"] : []),
    ];
    terminar(partes.join(", ") + ".");
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="chips">
        {(["agricola", "mixto", "ganadero"] as const).map((x) => (
          <button key={x} className={`chip ${tipo === x ? "on" : ""}`} onClick={() => setTipo(x)}>
            {x === "agricola" ? "Agrícola" : x === "mixto" ? "Mixto (agrícola-ganadero)" : "Ganadero"}
          </button>
        ))}
      </div>
      {tipo === "mixto" && (
        <label className="campo">Parte agrícola del campo: {pct} %
          <input type="range" min={10} max={90} step={5} value={pct} onChange={(e) => setPct(+e.target.value)} style={{ accentColor: "var(--verde-700)" }} />
        </label>
      )}
      <div className="grilla2">
        {tipo !== "agricola" && <label className="campo">Cabezas (aprox.)<input className="entrada" inputMode="numeric" value={cabezas} onChange={(e) => setCabezas(e.target.value.replace(/\D/g, ""))} /></label>}
        <label className="campo">¿Vendés forraje? (fardos, silo, pastoreo)
          <select className="entrada" value={vende ? "si" : "no"} onChange={(e) => setVende(e.target.value === "si")}>
            <option value="no">No</option><option value="si">Sí</option>
          </select>
        </label>
        <label className="campo">El campo es
          <select className="entrada" value={tenencia} onChange={(e) => setTenencia(e.target.value as any)}>
            <option value="propio">Propio</option><option value="arrendado">Arrendado</option>
          </select>
        </label>
        {tenencia === "arrendado" && <label className="campo">Años que quedan<input className="entrada" inputMode="numeric" value={anios} onChange={(e) => setAnios(e.target.value.replace(/\D/g, ""))} /></label>}
        {tenencia === "arrendado" && <label className="campo">{us ? "Renta (bushels de soja por acre)" : "Renta (kg de soja por ha)"}<input className="entrada" inputMode="numeric" placeholder={us ? "ej. 23" : "ej. 800"} value={renta} onChange={(e) => setRenta(e.target.value.replace(/\D/g, ""))} /></label>}
        <label className="campo">¿Tenés seguro de seca?
          <select className="entrada" value={seguro} onChange={(e) => setSeguro(e.target.value)}>
            <option value="">No sé / no aplica</option><option value="si">Sí</option><option value="no">No</option>
          </select>
        </label>
        <label className="campo">¿Vendés a futuro antes de cosechar?
          <select className="entrada" value={futuro} onChange={(e) => setFuturo(e.target.value)}>
            <option value="">No sé / no aplica</option><option value="si">Sí</option><option value="no">No</option>
          </select>
        </label>
        <label className="campo">¿Riego?
          <select className="entrada" value={riego ? "si" : "no"} onChange={(e) => setRiego(e.target.value === "si")}>
            <option value="no">No</option><option value="si">Sí</option>
          </select>
        </label>
      </div>
      <div style={{ marginTop: 4, display: "flex", flexDirection: "column", gap: 10 }}>
        <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
          <input type="checkbox" checked={curvas} onChange={(e) => setCurvas(e.target.checked)} />
          Siembro en curvas de nivel o tengo terrazas (baja la erosión)
        </label>
      </div>
      <div className="tarjeta-pie"><span /><button className="btn primario" onClick={guardar}>Guardar y seguir</button></div>
    </div>
  );
}

// ----------------------------------------------------------------- historial
const ANIOS_HIST = (() => {
  const y = new Date().getFullYear();
  const ultimo = new Date().getMonth() >= 6 ? y - 1 : y - 2; // último verano ya cosechado
  return [ultimo - 3, ultimo - 2, ultimo - 1, ultimo];
})();

function opcionesCultivo(temporada: "invierno" | "verano") {
  const cat = useApp.getState().catalogo;
  return (cat?.cultivos || []).filter((c) => c.temporada === temporada || c.temporada === "perenne" || c.temporada === "barbecho");
}

function FormHistorial({ terminar, omitir }: PropsForm) {
  const { campo, actualizarSeccion, catalogo } = useApp();
  const [datos, setDatos] = useState<Record<string, AnioHistorial[]>>(() =>
    Object.fromEntries(campo.secciones.map((s) => [s.id, ANIOS_HIST.map((a) => s.historial?.find((h) => h.anio === a) || { anio: a, invierno: "", verano: "" })])),
  );
  const [sec, setSec] = useState(campo.secciones[0]?.id);
  // «Guardar y seguir» primero va de lote en lote y recién en el último pasa al paso siguiente;
  // el ✓ de un lote sale cuando está completo o cuando se pasó al siguiente, no con el primer dato
  const [pasados, setPasados] = useState<Set<string>>(() => new Set());
  const inv = opcionesCultivo("invierno"), ver = opcionesCultivo("verano");
  const completo = (sid: string) => (datos[sid] || []).every((h) => h.invierno && h.verano);
  const listo = (sid: string) => pasados.has(sid) || completo(sid);
  const siguiente = (() => {
    const ids = campo.secciones.map((s) => s.id);
    const i = ids.indexOf(sec || "");
    const orden = [...ids.slice(i + 1), ...ids.slice(0, Math.max(i, 0))];
    return campo.secciones.find((s) => s.id === orden.find((id) => !listo(id))) || null;
  })();

  function avanzar() {
    if (sec) setPasados((p) => new Set(p).add(sec));
    if (siguiente) setSec(siguiente.id);
    else guardar();
  }

  function cambiar(sid: string, anio: number, campoT: "invierno" | "verano", v: string) {
    setDatos((d) => {
      const filas = d[sid].map((h) => {
        if (h.anio !== anio) return h;
        const nuevo = { ...h, [campoT]: v };
        const c = catalogo?.cultivos.find((x) => x.codigo === v);
        if (c?.temporada === "perenne") return { ...nuevo, invierno: v, verano: v };
        return nuevo;
      });
      return { ...d, [sid]: filas };
    });
  }

  function copiarATodas() {
    if (!sec) return;
    setDatos((d) => Object.fromEntries(Object.keys(d).map((k) => [k, d[sec].map((h) => ({ ...h }))])));
  }

  function guardar() {
    const partes: string[] = [];
    for (const s of campo.secciones) {
      const filas = (datos[s.id] || []).filter((h) => h.invierno || h.verano);
      if (!filas.length) continue;
      actualizarSeccion(s.id, { historial: filas.map((h) => ({ anio: h.anio, invierno: h.invierno || "barbecho", verano: h.verano || "barbecho" })) });
      const txt = filas.map((h) => `${h.anio}: ${nombreCultivo(catalogo, h.invierno || "barbecho", true).toLowerCase()} / ${nombreCultivo(catalogo, h.verano || "barbecho", true).toLowerCase()}`).join("; ");
      partes.push(`${s.nombre}: ${txt}`);
    }
    // se pasó por todos los lotes sin cargar nada: es lo mismo que «No me acuerdo»
    if (!partes.length) return omitir("No me acuerdo bien de lo que sembré; usá lo que vio el satélite.");
    terminar(`Cargué el historial. ${partes.join(". ")}.`);
  }

  if (!campo.secciones.length) return <div className="alerta ambar">Primero hay que definir las secciones del campo.</div>;
  const filas = sec ? datos[sec] : [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {campo.secciones.length > 1 && (
        <div className="chips">
          {campo.secciones.map((s) => (
            <button key={s.id} className={`chip ${sec === s.id ? "on" : ""}`} onClick={() => setSec(s.id)}>
              {s.nombre}{listo(s.id) ? " ✓" : ""}
            </button>
          ))}
        </div>
      )}
      <table className="tabla-mini">
        <thead><tr><th>Año</th><th>Invierno</th><th>Verano</th></tr></thead>
        <tbody>
          {filas.map((h) => (
            <tr key={h.anio}>
              <td><b>{h.anio}</b>{" "}<small style={{ color: "var(--texto-3)" }}>/{String(h.anio + 1).slice(2)}</small></td>
              <td><select value={h.invierno || ""} onChange={(e) => cambiar(sec!, h.anio, "invierno", e.target.value)}>
                <option value="">—</option>{inv.map((c) => <option key={c.codigo} value={c.codigo}>{nombreCultivo(catalogo, c.codigo, true)}</option>)}
              </select></td>
              <td><select value={h.verano || ""} onChange={(e) => cambiar(sec!, h.anio, "verano", e.target.value)}>
                <option value="">—</option>{ver.map((c) => <option key={c.codigo} value={c.codigo}>{nombreCultivo(catalogo, c.codigo, true)}</option>)}
              </select></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="tarjeta-pie">
        <div style={{ display: "flex", gap: 6 }}>
          <button className="btn texto chico" onClick={() => omitir("No me acuerdo bien de lo que sembré; usá lo que vio el satélite.")}>No me acuerdo</button>
          {campo.secciones.length > 1 && <button className="btn texto chico" onClick={copiarATodas}>Copiar a todas</button>}
        </div>
        <button className="btn primario" onClick={avanzar}>
          {siguiente ? `Guardar y seguir con ${siguiente.nombre} →` : "Guardar y seguir"}
        </button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- problemas y experiencia
const PROBLEMAS = [
  { id: "anegamiento", t: "Se anega" },
  { id: "helada", t: "Hiela fuerte" },
  { id: "erosion", t: "Se lava / cárcavas" },
  { id: "suelo_superficial", t: "Suelo superficial o con piedra" },
  { id: "sequia", t: "Se seca rápido" },
  { id: "malezas", t: "Malezas resistentes" },
  { id: "compactacion", t: "Compactación" },
];

function FormProblemas({ terminar }: PropsForm) {
  const { campo, actualizarSeccion, actualizarCampo } = useApp();
  const [marcas, setMarcas] = useState<Record<string, string[]>>(() => Object.fromEntries(campo.secciones.map((s) => [s.id, s.problemas || []])));
  const [anios, setAnios] = useState(String(campo.experiencia?.anios || ""));
  const [bien, setBien] = useState(campo.experiencia?.que_funciono || "");
  const [mal, setMal] = useState(campo.experiencia?.que_fallo || "");

  function toggle(sid: string, p: string) {
    setMarcas((m) => ({ ...m, [sid]: m[sid].includes(p) ? m[sid].filter((x) => x !== p) : [...m[sid], p] }));
  }

  function guardar() {
    const partes: string[] = [];
    for (const s of campo.secciones) {
      actualizarSeccion(s.id, { problemas: marcas[s.id] });
      if (marcas[s.id]?.length) partes.push(`${s.nombre}: ${marcas[s.id].map((p) => PROBLEMAS.find((x) => x.id === p)?.t.toLowerCase()).join(", ")}`);
    }
    actualizarCampo({ experiencia: { anios: anios ? +anios : undefined, que_funciono: bien || undefined, que_fallo: mal || undefined, texto: [bien, mal].filter(Boolean).join(" | ") || "sin comentarios" } });
    const txt = [
      partes.length ? `Problemas por sección: ${partes.join("; ")}.` : "No marqué problemas especiales.",
      anios ? `Trabajo el campo hace ${anios} años.` : "",
      // sin el punto que ya trae lo escrito: salía «…yields well..»
      bien ? `Lo que me anduvo bien: ${bien.trim().replace(/[.\s]+$/, "")}.` : "",
      mal ? `Lo que me falló: ${mal.trim().replace(/[.\s]+$/, "")}.` : "",
    ].filter(Boolean).join(" ");
    terminar(txt);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {campo.secciones.map((s) => (
        <div key={s.id}>
          <div style={{ fontSize: 12.5, fontWeight: 650, marginBottom: 4 }}>{s.nombre}</div>
          <div className="chips">
            {PROBLEMAS.map((p) => (
              <button key={p.id} className={`chip ${marcas[s.id]?.includes(p.id) ? "on" : ""}`} onClick={() => toggle(s.id, p.id)}>{p.t}</button>
            ))}
          </div>
        </div>
      ))}
      <label className="campo">¿Hace cuántos años trabajás este campo?<input className="entrada" inputMode="numeric" value={anios} onChange={(e) => setAnios(e.target.value.replace(/\D/g, ""))} /></label>
      <label className="campo">Qué te anduvo bien<textarea className="entrada" rows={2} value={bien} onChange={(e) => setBien(e.target.value)} placeholder="ej. el maíz temprano en el lote del bajo" /></label>
      <label className="campo">Qué te falló<textarea className="entrada" rows={2} value={mal} onChange={(e) => setMal(e.target.value)} placeholder="ej. la soja de segunda se secó en 2023" /></label>
      <div className="tarjeta-pie"><span /><button className="btn primario" onClick={guardar}>Guardar y seguir</button></div>
    </div>
  );
}

// ----------------------------------------------------------------- archivos
/** Baja uno de los archivos de ejemplo de /ejemplos y lo pasa como si lo hubiera elegido el productor. */
function BotonEjemplo({ archivo, alArchivo }: { archivo: string; alArchivo: (f: File) => void }) {
  return (
    <button className="btn texto chico" onClick={async () => {
      const r = await fetch(`/ejemplos/${archivo}`);
      alArchivo(new File([await r.blob()], archivo, { type: "text/csv" }));
    }}>Probar con un archivo de ejemplo</button>
  );
}

function ZonaArchivo({ acepta, alArchivo, cargando, texto }: { acepta: string; alArchivo: (f: File) => void; cargando: boolean; texto: React.ReactNode }) {
  const ref = useRef<HTMLInputElement>(null);
  const [sobre, setSobre] = useState(false);
  return (
    <div className={`zona-archivo ${sobre ? "sobre" : ""}`} onClick={() => ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setSobre(true); }} onDragLeave={() => setSobre(false)}
      onDrop={(e) => { e.preventDefault(); setSobre(false); const f = e.dataTransfer.files[0]; if (f) alArchivo(f); }}>
      {cargando ? <Cargando que="calculando" etiqueta="Leyendo el archivo" /> : texto}
      <input ref={ref} type="file" hidden accept={acepta} onChange={(e) => { const f = e.target.files?.[0]; if (f) alArchivo(f); e.target.value = ""; }} />
    </div>
  );
}

const TEXTURAS = ["arenoso", "arenoso franco", "franco arenoso", "franco", "franco limoso", "franco arcillo arenoso", "franco arcilloso", "franco arcillo limoso", "arcillo arenoso", "arcillo limoso", "arcilloso"];

function FormSuelo({ terminar, omitir }: PropsForm) {
  const { campo, actualizarSeccion, actualizarCampo } = useApp();
  const [filas, setFilas] = useState<Array<AnalisisSuelo & { seccion?: string }>>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metodo, setMetodo] = useState<string>("");
  const [manual, setManual] = useState<AnalisisSuelo & { textura?: string }>({});

  async function subir(f: File) {
    setError(null);
    setCargando(true);
    try {
      const r = await api.archivo(f, "analisis_suelo");
      if (r.tipo !== "analisis_suelo" || !r.filas?.length) throw new Error(r.motivo || "No encontré valores de análisis de suelo en el archivo.");
      setMetodo(r.metodo || "tabla");
      setFilas(r.filas.map((x: AnalisisSuelo) => ({ ...x, seccion: emparejarSeccion(x.nombre, campo.secciones)?.id || (r.filas.length === 1 ? "__general" : "") })));
    } catch (e: any) {
      setError(enPalabras(e));
    } finally {
      setCargando(false);
    }
  }

  // Los valores van separados con « · » y no con comas: el traductor no reconocía «pH 5,8, MO 3,1 %, …»
  // como lista y dejaba «MO» y «arcilla» en castellano. «Todo el campo» con mayúscula: empieza una oración.
  // Varias muestras para el mismo lote se promedian. Antes cada una pisaba a la
  // anterior y quedaba solo la última.
  function guardar(lista: Array<AnalisisSuelo & { seccion?: string; textura?: string }>) {
    const grupos = new Map<string, Array<AnalisisSuelo & { textura?: string }>>();
    for (const { seccion, ...a } of lista) grupos.set(seccion || "__general", [...(grupos.get(seccion || "__general") || []), a]);
    const partes: string[] = [];
    const promedios: string[] = [];
    for (const [seccion, muestras] of grupos) {
      const a: AnalisisSuelo & { textura?: string } = { ...muestras[0] };
      if (muestras.length > 1) {
        for (const k of ["ph", "materia_organica", "carbono_organico", "fosforo_bray", "potasio", "arena", "limo", "arcilla", "agua_util_mm"] as const) {
          const vs = muestras.map((m) => m[k]).filter((v): v is number => typeof v === "number");
          a[k] = vs.length ? Math.round((vs.reduce((x, y) => x + y, 0) / vs.length) * 100) / 100 : undefined;
        }
        a.nombre = muestras.map((m) => m.nombre).filter(Boolean).join(", ") || undefined;
        a.textura = muestras.find((m) => m.textura)?.textura;
      }
      const n = (x: number) => x.toLocaleString("es-UY", { maximumFractionDigits: 2 });
      const desc = [a.ph != null && `pH ${n(a.ph)}`, a.materia_organica != null && `MO ${n(a.materia_organica)} %`, a.fosforo_bray != null && `P Bray ${n(a.fosforo_bray)} ppm`,
        a.potasio != null && `K ${n(a.potasio)} meq/100 g`, a.arcilla != null && `arcilla ${n(a.arcilla)} %`, (a as any).textura && `textura ${(a as any).textura}`].filter(Boolean).join(" · ");
      if (seccion !== "__general") {
        actualizarSeccion(seccion, { analisis_suelo: a });
        const nombre = campo.secciones.find((s) => s.id === seccion)?.nombre || "";
        partes.push(`${nombre}: ${desc}`);
        if (muestras.length > 1) promedios.push(`Promedié las ${muestras.length} muestras de ${nombre}.`);
      } else {
        actualizarCampo({ analisis_suelo_general: a });
        partes.push(`Todo el campo: ${desc}`);
        if (muestras.length > 1) promedios.push(`Promedié las ${muestras.length} muestras de todo el campo.`);
      }
    }
    terminar(`Cargué el análisis de suelo${metodo ? ` (${metodo})` : ""}. ${partes.join(". ")}.${promedios.length ? " " + promedios.join(" ") : ""}`);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ZonaArchivo acepta=".csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg,.webp" alArchivo={subir} cargando={cargando}
        texto={<>Arrastrá el análisis acá o <b>elegilo</b><br /><small>CSV, Excel, PDF o foto del informe del laboratorio</small></>} />
      {error && <div className="alerta ambar">{error} Podés cargarlo a mano abajo.</div>}
      {filas.length > 0 && (
        <>
          <table className="tabla-mini">
            <thead><tr><th>Muestra</th><th>pH</th><th>MO %</th><th>P</th><th>K</th><th>Sección</th></tr></thead>
            <tbody>
              {filas.map((f, i) => (
                <tr key={i}>
                  <td>{f.nombre || `#${i + 1}`}</td>{[f.ph, f.materia_organica, f.fosforo_bray, f.potasio].map((v, k) => <td key={k}>{v != null ? v.toLocaleString("es-UY") : "—"}</td>)}
                  <td><select value={f.seccion || ""} onChange={(e) => setFilas(filas.map((x, j) => (j === i ? { ...x, seccion: e.target.value } : x)))}>
                    <option value="">(no usar)</option><option value="__general">Todo el campo</option>
                    {campo.secciones.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
                  </select></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="tarjeta-pie"><span /><button className="btn primario" onClick={() => guardar(filas.filter((f) => f.seccion))}>Usar estos valores</button></div>
        </>
      )}
      <details>
        <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "var(--texto-2)" }}>Cargar a mano (para todo el campo)</summary>
        <div className="grilla2" style={{ marginTop: 8 }}>
          {([["ph", "pH"], ["materia_organica", "Materia orgánica %"], ["fosforo_bray", "Fósforo Bray I (ppm)"], ["potasio", "Potasio (meq/100 g)"]] as const).map(([k, t]) => (
            <label key={k} className="campo">{t}<input className="entrada" inputMode="decimal" value={(manual as any)[k] ?? ""} onChange={(e) => setManual({ ...manual, [k]: e.target.value === "" ? undefined : parseFloat(e.target.value.replace(",", ".")) })} /></label>
          ))}
          <label className="campo" style={{ gridColumn: "1 / -1" }}>Textura
            <select className="entrada" value={manual.textura || ""} onChange={(e) => setManual({ ...manual, textura: e.target.value || undefined })}>
              <option value="">No sé</option>{TEXTURAS.map((x) => <option key={x}>{x}</option>)}
            </select>
          </label>
        </div>
        <div className="tarjeta-pie" style={{ marginTop: 8 }}><span /><button className="btn secundario chico" onClick={() => guardar([{ ...manual, seccion: "__general" }])}>Guardar</button></div>
      </details>
      <div className="tarjeta-pie">
        <button className="btn texto chico" onClick={() => omitir("No tengo análisis de suelo.")}>No tengo análisis</button>
        <BotonEjemplo archivo="analisis_suelo_ejemplo.csv" alArchivo={subir} />
      </div>
    </div>
  );
}

function FormEstacion({ terminar, omitir }: PropsForm) {
  const { campo, actualizarCampo } = useApp();
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function subir(f: File) {
    setError(null);
    setCargando(true);
    try {
      const p = campo.ubicacion ? { lat: campo.ubicacion.lat, lon: campo.ubicacion.lon } : undefined;
      const r = await api.archivo(f, "estacion", p);
      if (r.tipo !== "estacion") throw new Error(r.motivo || "No reconocí el archivo como datos de una estación.");
      actualizarCampo({ estacion: { archivo: f.name, comparacion: r.comparacion, mensual: r.mensual } });
      terminar(`Subí los datos de mi estación (${f.name}, ${r.dias} días, del ${r.desde} al ${r.hasta}). ${r.comparacion?.conclusion || ""}`);
    } catch (e: any) {
      setError(enPalabras(e));
    } finally {
      setCargando(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ZonaArchivo acepta=".csv,.txt,.xlsx,.xls" alArchivo={subir} cargando={cargando}
        texto={<>Arrastrá el archivo de la estación o <b>elegilo</b><br /><small>CSV o Excel con fecha y lluvia o temperaturas (diario, horario o cada 10 minutos)</small></>} />
      {error && <div className="alerta ambar" role="alert">{error}</div>}
      <div className="tarjeta-pie">
        <button className="btn texto chico" onClick={() => omitir("No tengo estación meteorológica.")}>No tengo estación</button>
        {/* Datos reales de INUMET (Paso de los Toros) en vez de los sintéticos */}
        <BotonEjemplo archivo="estacion_inumet_paso_de_los_toros.csv" alArchivo={subir} />
      </div>
    </div>
  );
}

function FormArchivoHistorial({ terminar, omitir }: PropsForm) {
  const { campo, actualizarSeccion } = useApp();
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function subir(f: File) {
    setError(null);
    setCargando(true);
    try {
      const r = await api.archivo(f, "historial");
      if (r.tipo !== "historial" || !r.filas?.length) throw new Error("No encontré columnas de año, lote o potrero, y cultivo.");
      const porSec: Record<string, AnioHistorial[]> = {};
      let sinPar = 0;
      for (const h of r.filas) {
        const s = emparejarSeccion(h.seccion, campo.secciones) || (campo.secciones.length === 1 ? campo.secciones[0] : null);
        if (!s) { sinPar++; continue; }
        (porSec[s.id] ||= []).push({ anio: h.anio, invierno: h.invierno || "barbecho", verano: h.verano || "barbecho" });
      }
      Object.entries(porSec).forEach(([id, hs]) => actualizarSeccion(id, { historial: hs }));
      terminar(`Subí el historial de cultivos (${f.name}): ${Object.keys(porSec).length} secciones con datos${sinPar ? `, ${sinPar} filas sin sección que coincida` : ""}.`);
    } catch (e: any) {
      setError(enPalabras(e));
    } finally {
      setCargando(false);
    }
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <ZonaArchivo acepta=".csv,.xlsx,.xls" alArchivo={subir} cargando={cargando} texto={<>Arrastrá el archivo o <b>elegilo</b><br /><small>Columnas: año, lote o potrero, invierno, verano</small></>} />
      {error && <div className="alerta ambar" role="alert">{error}</div>}
      <div className="tarjeta-pie">
        <button className="btn texto chico" onClick={() => omitir("No tengo un archivo de historial.")}>No tengo</button>
        <BotonEjemplo archivo="historial_ejemplo.csv" alArchivo={subir} />
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- prioridades
export const DIMENSIONES: Array<{ id: keyof Prioridades; t: string; d: string }> = [
  { id: "ingreso", t: "Ingreso", d: "plata por hectárea y por año" },
  { id: "suelo", t: "Cuidar el suelo", d: "erosión y carbono" },
  { id: "agua", t: "Bajar el riesgo de seca", d: "que el cultivo no se seque en floración" },
  { id: "clima", t: "Heladas y calor", d: "evitar cultivos que sufren el clima del lugar" },
  { id: "forraje", t: "Forraje para el ganado", d: "pasto todo el año" },
  { id: "simplicidad", t: "Simplicidad", d: "rotación simple y manejo operativo ágil" },
  { id: "diversificacion", t: "Diversificar", d: "repartir el riesgo de precio y cortar malezas" },
];
const NIVELES = ["Nada", "Poco", "Algo", "Importante", "Muy importante", "Lo principal"];

function FormPrioridades({ terminar }: PropsForm) {
  const { campo, actualizarCampo, catalogo } = useApp();
  const base: Prioridades = { ingreso: 3, suelo: 3, agua: 3, clima: 2, forraje: campo.sistema?.ganado ? 3 : 0, simplicidad: 1, diversificacion: 1, ...(campo.objetivos?.prioridades || {}) };
  const [p, setP] = useState<Prioridades>(base);
  const [corto, setCorto] = useState(campo.objetivos?.corto_plazo || "");
  const [largo, setLargo] = useState(campo.objetivos?.largo_plazo || "");
  const [excl, setExcl] = useState<string[]>(campo.restricciones?.cultivos_excluidos || []);
  const cultivosEx = useMemo(() => (catalogo?.cultivos || []).filter((c) => !["barbecho", "campo_natural", "cobertura"].includes(c.codigo)), [catalogo]);

  function guardar() {
    actualizarCampo({ objetivos: { ...(campo.objetivos || {}), prioridades: p, corto_plazo: corto || undefined, largo_plazo: largo || undefined },
      restricciones: { ...(campo.restricciones || {}), cultivos_excluidos: excl } });
    const orden = [...DIMENSIONES].sort((a, b) => (p[b.id] || 0) - (p[a.id] || 0)).filter((d) => (p[d.id] || 0) >= 3).map((d) => d.t.toLowerCase());
    terminar([
      `Mis prioridades: ${orden.join(", ") || "nada en especial"}.`,
      // sin el punto que ya trae lo escrito (salía «…this year..»)
      corto && `A corto plazo: ${corto.trim().replace(/[.\s]+$/, "")}.`,
      largo && `A largo plazo: ${largo.trim().replace(/[.\s]+$/, "")}.`,
      excl.length && `No quiero hacer: ${excl.map((c) => nombreCultivo(catalogo, c, true).toLowerCase()).join(", ")}.`,
    ].filter(Boolean).join(" "));
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {DIMENSIONES.map((d) => (
        <div key={d.id} className="deslizador" title={d.d}>
          <span><b style={{ color: "var(--texto)", fontWeight: 600 }}>{d.t}</b><br /><small style={{ color: "var(--texto-3)" }}>{d.d}</small></span>
          <input type="range" min={0} max={5} value={p[d.id] ?? 0} onChange={(e) => setP({ ...p, [d.id]: +e.target.value })} aria-label={d.t} />
          <b title={NIVELES[p[d.id] ?? 0]}>{p[d.id] ?? 0}</b>
        </div>
      ))}
      <label className="campo">Planes para esta zafra<textarea className="entrada" rows={2} value={corto} onChange={(e) => setCorto(e.target.value)} placeholder="ej. necesito caja este año; ya compré semilla de soja" /></label>
      <label className="campo">Planes a 5-10 años<textarea className="entrada" rows={2} value={largo} onChange={(e) => setLargo(e.target.value)} placeholder="ej. recuperar el suelo del lote de la loma, dejarle el campo a mis hijos" /></label>
      <div>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--texto-2)", marginBottom: 4 }}>Cultivos que no querés hacer</div>
        <div className="chips">
          {cultivosEx.map((c) => (
            <button key={c.codigo} className={`chip ${excl.includes(c.codigo) ? "on" : ""}`} onClick={() => setExcl(excl.includes(c.codigo) ? excl.filter((x) => x !== c.codigo) : [...excl, c.codigo])}>
              {nombreCultivo(catalogo, c.codigo, true)}
            </button>
          ))}
        </div>
      </div>
      <div className="tarjeta-pie"><span /><button className="btn primario" onClick={guardar}>Guardar y seguir</button></div>
    </div>
  );
}

const REFERENCIAS_URUGUAY: Record<string, { rinde: number; precio: number; costo: number; margen: number }> = {
  soja: { rinde: 2600, precio: 400, costo: 680, margen: 360 },
  soja2: { rinde: 1900, precio: 400, costo: 580, margen: 180 },
  maiz: { rinde: 6800, precio: 200, costo: 950, margen: 410 },
  maiz2: { rinde: 5200, precio: 195, costo: 820, margen: 194 },
  trigo: { rinde: 3800, precio: 215, costo: 720, margen: 97 },
  cebada: { rinde: 3900, precio: 210, costo: 700, margen: 119 },
  colza: { rinde: 1750, precio: 450, costo: 690, margen: 98 },
  sorgo: { rinde: 5000, precio: 180, costo: 680, margen: 220 },
  girasol: { rinde: 2000, precio: 390, costo: 620, margen: 160 },
  pradera: { rinde: 0, precio: 0, costo: 0, margen: 120 },
  alfalfa: { rinde: 0, precio: 0, costo: 0, margen: 180 },
  verdeo: { rinde: 0, precio: 0, costo: 0, margen: 90 },
  cobertura: { rinde: 0, precio: 0, costo: 0, margen: -70 },
};

// Ejemplos de EE. UU., ya en bu/ac, USD/bu y USD/ac: rinde y costo sin la tierra de Iowa State
// University, «Estimated Costs of Crop Production in Iowa–2026» (A1-20: maíz después de soja, 211 bu y 911,98 USD/ac
// menos 274 de renta; soja después de maíz, 61 bu y 679,11 menos 274); precio medio de la campaña 2026/27 del USDA. El trigo no está en esa publicación: va sin ejemplo.
const REFERENCIAS_EEUU: Record<string, { rinde: number; precio: number; costo: number }> = {
  maiz: { rinde: 211, precio: 4.6, costo: 638 },
  soja: { rinde: 61, precio: 12.1, costo: 405 },
};

function FormMargenes({ terminar, omitir }: PropsForm) {
  const { campo, actualizarCampo, catalogo } = useApp();
  // Cultivos estratégicos principales que maneja el productor agrícola promedio en Uruguay
  const granosPrincipales = ["soja", "maiz", "trigo"];
  const otrosGranos = ["soja2", "maiz2", "cebada", "colza", "sorgo", "girasol"];
  const directos = ["pradera", "alfalfa", "verdeo", "cobertura"];
  const [verMas, setVerMas] = useState(false);
  const region = useRegion((r) => r.region);

  // En EE. UU. la tarjeta se llena en bushels por acre, dólares por bushel y dólares por acre. El campo
  // sigue guardando todo en métrico (kg/ha, USD/t, USD/ha): se convierte al abrir y al guardar.
  const us = region === "US";
  const U = us ? { rinde: "bu/ac", precio: "USD/bu", sup: "USD/ac" } : { rinde: "kg/ha", precio: "USD/t", sup: "USD/ha" };
  const r1 = (x: number, dec: number) => Math.round(x * 10 ** dec) / 10 ** dec;
  const ver = {
    rinde: (v: number, c: string) => (us ? r1(kgHaABuAc(v, c), 0) : v),
    precio: (v: number, c: string) => (us ? r1(usdTAUsdBu(v, c), 2) : v),
    sup: (v: number) => (us ? Math.round(v / HA_A_AC) : v),
  };
  const guardarComo = {
    rinde: (v: number, c: string) => (us ? Math.round(buAcAKgHa(v, c)) : v),
    precio: (v: number, c: string) => (us ? r1(usdBuAUsdT(v, c), 1) : v),
    sup: (v: number) => (us ? Math.round(v * HA_A_AC) : v),
  };
  const det0 = campo.detalle_margenes || {};
  const [modo, setModo] = useState<"detalle" | "margen">(Object.keys(det0).length || !campo.margenes ? "detalle" : "margen");
  const txt = (x: number | undefined) => (x != null ? String(x) : "");

  const [d, setD] = useState<Record<string, { rinde: string; precio: string; costo: string }>>(() =>
    Object.fromEntries([...granosPrincipales, ...otrosGranos].map((c) => [c, {
      rinde: txt(det0[c]?.rinde != null ? ver.rinde(det0[c].rinde, c) : undefined),
      precio: txt(det0[c]?.precio != null ? ver.precio(det0[c].precio, c) : undefined),
      costo: txt(det0[c]?.costo != null ? ver.sup(det0[c].costo) : undefined),
    }])));
  const [m, setM] = useState<Record<string, string>>(() =>
    Object.fromEntries([...granosPrincipales, ...otrosGranos, ...directos].map((c) => [c, txt(campo.margenes?.[c] != null ? ver.sup(campo.margenes[c]) : undefined)])));

  const num = (s: string) => (s.trim() !== "" && !Number.isNaN(+s) ? +s : null);
  const margenDe = (c: string) => {
    const r = num(d[c]?.rinde || ""), p = num(d[c]?.precio || ""), k = num(d[c]?.costo || "");
    // en EE. UU. el precio ya es por bushel: rinde (bu/ac) × precio (USD/bu) − costo (USD/ac)
    return r != null && p != null && k != null ? Math.round((us ? r * p : (r * p) / 1000) - k) : null;
  };

  const aplicarReferencias = () => {
    const nuevoD: Record<string, { rinde: string; precio: string; costo: string }> = {};
    const nuevoM: Record<string, string> = {};
    for (const [c, ref] of Object.entries(REFERENCIAS_URUGUAY)) {
      if (ref.rinde > 0) {
        nuevoD[c] = { rinde: String(ref.rinde), precio: String(ref.precio), costo: String(ref.costo) };
      }
      nuevoM[c] = String(ref.margen);
    }
    setD((prev) => ({ ...prev, ...nuevoD }));
    setM((prev) => ({ ...prev, ...nuevoM }));
  };

  function guardar() {
    const margenes: Record<string, number> = {};
    const detalle: Record<string, { rinde: number; precio: number; costo: number }> = {};
    const todosGranos = [...granosPrincipales, ...otrosGranos];
    for (const c of todosGranos) {
      if (modo === "detalle") {
        const mg = margenDe(c);
        if (mg != null) {
          margenes[c] = guardarComo.sup(mg);
          detalle[c] = { rinde: guardarComo.rinde(+d[c].rinde, c), precio: guardarComo.precio(+d[c].precio, c), costo: guardarComo.sup(+d[c].costo) };
        }
      } else if (num(m[c]) != null) margenes[c] = guardarComo.sup(num(m[c])!);
    }
    for (const c of directos) if (num(m[c]) != null) margenes[c] = guardarComo.sup(num(m[c])!);
    // sin ningún número cargado, «Guardar y seguir» sigue igual que «No los sé, seguir con referencias». Antes no
    // hacía nada y no avisaba: quien venía tocando «Guardar y seguir» en cada paso se quedaba trabado en el último,
    // justo antes del análisis
    if (!Object.keys(margenes).length) { omitir("Usá el índice relativo."); return; }
    actualizarCampo({ margenes, detalle_margenes: detalle });
    terminar(`Mis márgenes (${U.sup}): ${Object.entries(margenes).map(([k, v]) => `${nombreCultivo(catalogo, k, true).toLowerCase()} ${ver.sup(v)}`).join(", ")}.`);
  }

  const limpio = (s: string) => s.replace(/[^\d.-]/g, "");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        {/* las referencias son de Uruguay (FUCREA / OPYPA): fuera de Uruguay no se ofrecen */}
        {region === "UY" || region === "" ? (
          <button type="button" className="btn chico fantasma" onClick={aplicarReferencias} style={{ fontWeight: 600 }}>
            Usar referencias de la zafra (FUCREA / OPYPA)
          </button>
        ) : <span />}
        <div className="chips" style={{ margin: 0 }}>
          <button type="button" className={`chip ${modo === "detalle" ? "on" : ""}`} onClick={() => setModo("detalle")}>Precio de venta y rinde</button>
          <button type="button" className={`chip ${modo === "margen" ? "on" : ""}`} onClick={() => setModo("margen")}>Solo el margen</button>
        </div>
      </div>

      <p style={{ margin: 0, fontSize: 12.5, color: "var(--texto-2)", lineHeight: 1.4 }}>
        Con definir o confirmar tus números de <b>1 o 2 cultivos principales</b> (como Soja o Maíz), el sistema proyecta los demás automáticamente con los coeficientes técnicos de la zona.
      </p>
      {us && (
        <p style={{ margin: 0, fontSize: 12, color: "var(--texto-3)", lineHeight: 1.4 }}>
          Los ejemplos de maíz y soja son de Iowa: rinde y costo sin la tierra de Iowa State University (2026) y precio medio de la campaña 2026/27 del USDA (noviembre de 2026).
        </p>
      )}

      {modo === "detalle" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div className="margen-encabezado">
            <span>{`Rinde esperado (${U.rinde})`}</span>
            <span>{`Precio venta (${U.precio})`}</span>
            <span>{`Costo compra/insumos (${U.sup})`}</span>
          </div>
          {granosPrincipales.map((c) => (
            <div key={c} className="fila-margen">
              <span className="fila-margen-nombre">{nombreCultivo(catalogo, c, true)}</span>
              <input className="entrada" inputMode="decimal" aria-label={us ? "Rinde en bushels por acre" : "Rinde en kg por hectárea"} placeholder={us ? (REFERENCIAS_EEUU[c] ? `ej. ${REFERENCIAS_EEUU[c].rinde}` : U.rinde) : `ej. ${REFERENCIAS_URUGUAY[c]?.rinde || 2600}`} value={d[c]?.rinde || ""} onChange={(e) => setD({ ...d, [c]: { ...d[c], rinde: limpio(e.target.value) } })} />
              <input className="entrada" inputMode="decimal" aria-label={us ? "Precio venta en dólares por bushel" : "Precio venta en dólares por tonelada"} placeholder={us ? (REFERENCIAS_EEUU[c] ? `ej. ${REFERENCIAS_EEUU[c].precio.toFixed(2)}` : U.precio) : `ej. ${REFERENCIAS_URUGUAY[c]?.precio || 400}`} value={d[c]?.precio || ""} onChange={(e) => setD({ ...d, [c]: { ...d[c], precio: limpio(e.target.value) } })} />
              <input className="entrada" inputMode="decimal" aria-label={us ? "Costo en dólares por acre, sin renta" : "Costo en dólares por hectárea, sin renta"} placeholder={us ? (REFERENCIAS_EEUU[c] ? `ej. ${REFERENCIAS_EEUU[c].costo}` : U.sup) : `ej. ${REFERENCIAS_URUGUAY[c]?.costo || 680}`} value={d[c]?.costo || ""} onChange={(e) => setD({ ...d, [c]: { ...d[c], costo: limpio(e.target.value) } })} />
              <span className="fila-margen-resultado">{margenDe(c) != null ? `Margen: ${margenDe(c)} ${U.sup}` : ""}</span>
            </div>
          ))}
          {verMas && otrosGranos.map((c) => (
            <div key={c} className="fila-margen">
              <span className="fila-margen-nombre">{nombreCultivo(catalogo, c, true)}</span>
              <input className="entrada" inputMode="decimal" aria-label={us ? "Rinde en bushels por acre" : "Rinde en kg por hectárea"} placeholder={U.rinde} value={d[c]?.rinde || ""} onChange={(e) => setD({ ...d, [c]: { ...d[c], rinde: limpio(e.target.value) } })} />
              <input className="entrada" inputMode="decimal" aria-label={us ? "Precio venta en dólares por bushel" : "Precio venta en dólares por tonelada"} placeholder={U.precio} value={d[c]?.precio || ""} onChange={(e) => setD({ ...d, [c]: { ...d[c], precio: limpio(e.target.value) } })} />
              <input className="entrada" inputMode="decimal" aria-label={us ? "Costo en dólares por acre, sin renta" : "Costo en dólares por hectárea, sin renta"} placeholder={U.sup} value={d[c]?.costo || ""} onChange={(e) => setD({ ...d, [c]: { ...d[c], costo: limpio(e.target.value) } })} />
              <span className="fila-margen-resultado">{margenDe(c) != null ? `Margen: ${margenDe(c)} ${U.sup}` : ""}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="grilla2">
          {granosPrincipales.map((c) => (
            <label key={c} className="campo">{nombreCultivo(catalogo, c, true)}
              <input className="entrada" inputMode="numeric" placeholder={U.sup} value={m[c] || ""} onChange={(e) => setM({ ...m, [c]: limpio(e.target.value) })} />
            </label>
          ))}
          {verMas && otrosGranos.map((c) => (
            <label key={c} className="campo">{nombreCultivo(catalogo, c, true)}
              <input className="entrada" inputMode="numeric" placeholder={U.sup} value={m[c] || ""} onChange={(e) => setM({ ...m, [c]: limpio(e.target.value) })} />
            </label>
          ))}
        </div>
      )}

      <div>
        <button type="button" className="btn texto chico" onClick={() => setVerMas(!verMas)} style={{ padding: "3px 0", color: "var(--verde-700)", fontWeight: 600 }}>
          {verMas ? "Ver solo cultivos principales" : "Ajustar más cultivos (soja 2da, cebada, colza, pasturas)"}
        </button>
      </div>

      {verMas && (
        <div className="grilla2" style={{ borderTop: "1px dashed var(--linea)", paddingTop: 8 }}>
          {directos.map((c) => (
            <label key={c} className="campo">{nombreCultivo(catalogo, c, true)} (margen neto)
              <input className="entrada" inputMode="numeric" placeholder={U.sup} value={m[c] || ""} onChange={(e) => setM({ ...m, [c]: limpio(e.target.value) })} />
            </label>
          ))}
        </div>
      )}

      <small style={{ color: "var(--texto-3)" }}>
        Costos directos de implantación y protección (sin incluir la renta del campo, que se deduce por separado si es arrendado).
      </small>

      <div className="tarjeta-pie">
        <button className="btn texto chico" onClick={() => omitir("Usá el índice relativo.")}>No los sé, seguir con referencias</button>
        <button className="btn primario" onClick={guardar}>Guardar y seguir</button>
      </div>
    </div>
  );
}
