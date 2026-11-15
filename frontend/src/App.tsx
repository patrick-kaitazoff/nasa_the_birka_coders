import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useApp, flujoTerminado, esAnalisisDesactualizado, ejemploQueSeAbre } from "./store";
import { Chat } from "./chat/Chat";
import { MapaCampo, bajarDepartamentos } from "./mapa/MapaCampo";
import { PanelAnalisis } from "./analisis/PanelAnalisis";
import { Comparar } from "./comparar/Comparar";
import { Plan } from "./plan/Plan";
import { MarcaFieldShift, definicionesTramas } from "./comun/Cultivo";
import { ModalConfirmar } from "./comun/ModalConfirmar";
import { ModalBorrarContorno } from "./comun/ModalBorrarContorno";
import { ModalResultados } from "./comun/ModalResultados";
import { EntradaHerramienta } from "./inicio/EntradaHerramienta";
import { RevisarDatos } from "./plan/RevisarDatos";
import { Cargando } from "./comun/Cargando";
import { VentanaHistoria } from "./historia/VentanaHistoria";
import { precargarRelieve } from "./relieve/useRelieve";
import type { Pestania } from "./tipos";
import { SelectorIdioma } from "./i18n/SelectorIdioma";
import { SelectorPais } from "./mapa/SelectorPais";
import { cuandoQuieto } from "./comun/cuandoQuieto";
import { fotoDePortada } from "./inicio/llegada";
import fotoTrigo from "./landing/portada-trigo.webp";


/** Con ?demo, hasta que el campo de ejemplo está armado: una pantalla quieta con la marca y «Abriendo el campo de
 * ejemplo», que se funde cuando ya se dibujó la parte pedida. Antes se veía medio segundo lo que había guardado (u
 * otra parte) y después saltaba.
 * De fondo, el trigo de la portada oscurecido: la foto del último cuadro si se llegó desde ahí, si no la foto fija
 * del trigo. Antes era una pantalla crema con un ícono chico, y el fundido desde el atardecer cortaba la escena. */
function AbriendoEjemplo() {
  const cargando = useApp((s) => s.cargandoEjemplo);
  const [visible, setVisible] = useState(cargando);
  const [fondo] = useState(() => fotoDePortada() ?? fotoTrigo);
  const [saliendo, setSaliendo] = useState(false);
  // los suelos según el país del ejemplo
  const [sub] = useState(() => {
    const id = ejemploQueSeAbre();
    if (id === "us") return "Con el clima y el satélite de la NASA y los suelos del USDA (SSURGO)";
    if (id === "pucon" || id === "mosela") return "Con el clima y el satélite de la NASA y el mapa mundial de suelos SoilGrids";
    return "Con el clima y el satélite de la NASA y los suelos del MGAP";
  });
  useEffect(() => {
    if (cargando || !visible) return;
    // si el ejemplo se armó por adelantado (mouse apoyado en el botón de la portada), nadie llegó a ver esta pantalla:
    // se saca sin fundido y la portada se funde directo con el Plan
    if ((document as Document & { prerendering?: boolean }).prerendering) { setVisible(false); return; }
    // se funde cuando el ejemplo ya está dibujado y la página quedó quieta, así el fundido no se traba
    let t = 0;
    const cancelar = cuandoQuieto(() => {
      setSaliendo(true);
      t = window.setTimeout(() => setVisible(false), 450);
    });
    return () => { cancelar(); clearTimeout(t); };
  }, [cargando, visible]);
  if (!visible) return null;
  return (
    <div className={`abriendo-ejemplo ${saliendo ? "saliendo" : ""}`} role="status" aria-live="polite" style={{ backgroundImage: `url(${fondo})` }}>
      <div className="abriendo-ejemplo-caja">
        <MarcaFieldShift size={48} />
        <p className="abriendo-ejemplo-titulo">Abriendo el campo de ejemplo</p>
        <p className="abriendo-ejemplo-sub">{sub}</p>
        <span className="abriendo-ejemplo-barra" aria-hidden />
      </div>
    </div>
  );
}

/** Lo que falla fuera del chat (plan, ejemplo) se avisa abajo, en castellano, y se va solo. */
function AvisoFlotante() {
  const { aviso, setAviso } = useApp();
  useEffect(() => {
    if (!aviso) return;
    const t = setTimeout(() => setAviso(null), 9000);
    return () => clearTimeout(t);
  }, [aviso, setAviso]);
  if (!aviso) return null;
  return (
    <div className="aviso-flotante" role="alert">
      <span className="msg-error-icono" aria-hidden>!</span>
      <p>{aviso}</p>
      <button className="btn texto chico" aria-label="Cerrar" onClick={() => setAviso(null)}>×</button>
    </div>
  );
}

// orden de lectura de la solución: qué hago (Plan), por qué esto y no otra cosa (Comparar), en qué se basa (Datos). La Vista 3D no es una parte: es el botón 2D / 3D del
// mapa del Plan (store.setPestania lleva «vista3d» ahí).
const PESTANIAS: Array<{ id: Pestania; t: string }> = [
  { id: "mapa", t: "Mapa del campo" },
  { id: "plan", t: "Plan" },
  { id: "comparar", t: "Comparar" },
  { id: "analisis", t: "Datos" },
];

/**
 * Las partes de la solución en un notch que cuelga del centro del encabezado. Reemplaza a la cápsula flotante de abajo; el chat quedó
 * aparte, abajo a la derecha. La parte elegida es una píldora clara que se desliza a la otra. Solo en la compu.
 */
/** Lo que cuelga del notch por debajo de la barra. Las esquinas de abajo son concéntricas con la píldora
 * (radio: media píldora más el margen) y, como el notch cuelga menos que la unión más la esquina, la esquina empieza
 * dentro de la barra: cada unión curva es un círculo tangente al borde de la barra y a la esquina. Coordenadas con
 * y = 0 en el borde de la barra. */
function NotchForma({ ancho }: { ancho: number }) {
  const css = getComputedStyle(document.documentElement);
  const v = (k: string, d: number) => parseFloat(css.getPropertyValue(k)) || d;
  const pr = v("--notch-pildora-alto", 42) / 2;
  const m = v("--notch-margen", 7);
  const r = v("--notch-curva", 12);
  const h = v("--notch-baja", 26);
  const R = pr + m;
  const xc = m + pr;
  const yc = h - m - pr; // centro de la esquina (el del extremo de la píldora)
  const fx = xc - Math.sqrt(Math.max(0, (R + r) ** 2 - (r - yc) ** 2)); // centro de la unión: (fx, r)
  const tx = fx + ((xc - fx) * r) / (R + r);
  const ty = r + ((yc - r) * r) / (R + r);
  const W = ancho;
  const n = (x: number) => x.toFixed(2);
  const d = `M${n(fx)},-2 L${n(fx)},0 A${r},${r} 0 0 1 ${n(tx)},${n(ty)} A${R},${R} 0 0 0 ${n(xc)},${n(h)} `
    + `L${n(W - xc)},${n(h)} A${R},${R} 0 0 0 ${n(W - tx)},${n(ty)} A${r},${r} 0 0 1 ${n(W - fx)},0 L${n(W - fx)},-2 Z`;
  return (
    <svg className="notch-forma" aria-hidden width={W - 2 * fx} height={h + 2} viewBox={`${n(fx)} -2 ${n(W - 2 * fx)} ${h + 2}`}
      style={{ left: fx, top: `calc(100% - ${h + 2}px)` }}>
      <path d={d} />
    </svg>
  );
}

function NotchPartes({ partes, activa, onElegir }: {
  partes: Array<{ id: Pestania; t: string }>;
  activa: Pestania;
  onElegir: (p: Pestania) => void;
}) {
  const navRef = useRef<HTMLDivElement>(null);
  const notchRef = useRef<HTMLElement>(null);
  const botones = useRef<Partial<Record<Pestania, HTMLButtonElement | null>>>({});
  const [pildora, setPildora] = useState<{ x: number; w: number } | null>(null);
  const [ancho, setAncho] = useState(0);
  const ids = partes.map((p) => p.id).join(",");

  useLayoutEffect(() => {
    const medir = () => {
      const b = botones.current[activa];
      if (b) setPildora((v) => (v && v.x === b.offsetLeft && v.w === b.offsetWidth ? v : { x: b.offsetLeft, w: b.offsetWidth }));
      if (notchRef.current) setAncho(notchRef.current.offsetWidth);
    };
    medir();
    // el ancho cambia con el idioma y cuando termina de cargar la tipografía
    const ro = new ResizeObserver(medir);
    if (navRef.current) ro.observe(navRef.current);
    return () => ro.disconnect();
  }, [activa, ids]);

  return (
    <nav className="notch no-imprimir" aria-label="Partes de la solución" ref={notchRef}>
      {ancho > 0 && <NotchForma ancho={ancho} />}
      <div className="notch-partes" ref={navRef}>
        {pildora && <span className="notch-pildora" style={{ transform: `translateX(${pildora.x}px)`, width: pildora.w }} aria-hidden />}
        {partes.map((p) => (
          <button
            key={p.id}
            type="button"
            ref={(el) => { botones.current[p.id] = el; }}
            className={`notch-btn ${activa === p.id ? "activa" : ""}`}
            aria-current={activa === p.id ? "page" : undefined}
            onClick={() => onElegir(p.id)}
          >
            {p.t}
          </button>
        ))}
      </div>
    </nav>
  );
}

function MenuCampo() {
  const s = useApp();
  const { campo } = s;
  const [abierto, setAbierto] = useState(false);
  const [editando, setEditando] = useState(false);
  const [nombreTemp, setNombreTemp] = useState(campo.nombre || "");
  const contenedorRef = useRef<HTMLDivElement>(null);
  const entradaArchivo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setNombreTemp(campo.nombre || "");
  }, [campo.nombre]);

  useEffect(() => {
    if (!abierto) return;
    const alClicFuera = (e: MouseEvent) => {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
        setEditando(false);
      }
    };
    const alTecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAbierto(false);
        setEditando(false);
      }
    };
    window.addEventListener("mousedown", alClicFuera);
    window.addEventListener("keydown", alTecla);
    return () => {
      window.removeEventListener("mousedown", alClicFuera);
      window.removeEventListener("keydown", alTecla);
    };
  }, [abierto]);

  function exportar() {
    const datos = {
      version: 1,
      campo: s.campo,
      mensajes: s.mensajes,
      historialApi: s.historialApi,
      analisis: s.analisis,
      plan: s.plan,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(datos)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `ficha-${(campo.nombre || "campo").replace(/\s+/g, "-").toLowerCase()}.fieldshift.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function importar(f: File) {
    try {
      s.importarFicha(JSON.parse(await f.text()));
    } catch {
      /* archivo inválido */
    }
  }

  function guardarNombre() {
    s.actualizarCampo({ nombre: nombreTemp.trim() });
    setEditando(false);
  }

  const nSec = campo.secciones.length;
  const texto = `${campo.nombre || "Tu campo"}${nSec ? ` · ${nSec} ${nSec === 1 ? "sección" : "secciones"}` : ""}`;

  return (
    <div className="campo-menu-contenedor" ref={contenedorRef}>
      <button
        type="button"
        className="campo-nombre-btn"
        onClick={() => setAbierto(!abierto)}
        aria-expanded={abierto}
        aria-haspopup="menu"
        title="Opciones del campo: cambiar nombre, exportar, importar o empezar de cero"
      >
        <span>{texto}</span>
        <span className="campo-nombre-flecha" aria-hidden>▾</span>
      </button>

      {abierto && (
        <div className="menu-campo-dropdown" role="menu">
          {editando ? (
            <div className="menu-campo-item editando">
              <input
                className="entrada chica"
                value={nombreTemp}
                placeholder="ej. La Esperanza"
                onChange={(e) => setNombreTemp(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") guardarNombre();
                  if (e.key === "Escape") setEditando(false);
                }}
                autoFocus
              />
              <button className="btn chico primario" onClick={guardarNombre} title="Guardar">✓</button>
            </div>
          ) : (
            <button className="menu-campo-item" onClick={() => setEditando(true)}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
              <span>Cambiar nombre</span>
            </button>
          )}

          <button className="menu-campo-item" onClick={() => { exportar(); setAbierto(false); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" /></svg>
            <span>Exportar ficha</span>
          </button>

          <button className="menu-campo-item" onClick={() => { entradaArchivo.current?.click(); setAbierto(false); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" /></svg>
            <span>Importar ficha</span>
          </button>

          <div className="menu-campo-separador" />

          <button className="menu-campo-item peligro" onClick={() => { s.setConfirmarNuevo(true); setAbierto(false); }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
            <span>Empezar de cero</span>
          </button>
        </div>
      )}
      <input
        ref={entradaArchivo}
        type="file"
        hidden
        accept=".json"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void importar(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function App() {
  const {
    iniciar,
    pestania,
    setPestania,
    campo,
    mensajes,
    analisis,
    plan,
    catalogo,
    vistaMovil,
    setVistaMovil,
    cargarZona,
    chatPlegado,
    chatMensajeNuevo,
    modalEditarCampo,
    setModalEditarCampo,
    editandoCampo,
    copiaEdicionCampo,
    cancelarEdicionCampo,
    confirmarEdicionCampo,
    recalculandoAnalisis,
    rehacerAnalisis,
    esEjemplo,
  } = useApp();

  const analisisDesactualizado = esAnalisisDesactualizado(campo, analisis);

  useEffect(() => {
    void iniciar();
    // precarga inmediata de departamentos para que al entrar al mapa estén disponibles al instante
    void bajarDepartamentos();
  }, [iniciar]);

  // apenas se conoce el lugar, se traen el clima y el suelo de la zona en segundo plano: ya no se muestran,
  // pero así el análisis los encuentra guardados y tarda menos
  const punto = campo.ubicacion?.lat ? `${campo.ubicacion.lat.toFixed(3)},${campo.ubicacion.lon?.toFixed(3)}` : "";
  useEffect(() => {
    if (punto) cargarZona();
  }, [punto, cargarZona]);

  // precarga de relieve 3D en segundo plano para abrir al instante
  useEffect(() => {
    if (analisis && campo.contorno) precargarRelieve(campo, analisis);
  }, [analisis, campo]);

  const terminado = flujoTerminado(analisis, plan, mensajes, campo.contorno);
  // en los resultados, las partes de la solución van en un notch que cuelga del encabezado y «Preguntar» queda
  // sola abajo a la derecha, desde donde se abre el chat como una isla redondeada.
  // En la computadora: en el celular sigue la barra de abajo.
  const enResultados = terminado && !editandoCampo && pestania !== "mapa";

  // si el campo ya tiene análisis y plan sin pasos pendientes, no se queda en mapa (salvo que esté editando)
  useEffect(() => {
    if (terminado && pestania === "mapa" && !editandoCampo) {
      setPestania(plan ? "plan" : "comparar");
    }
  }, [terminado, pestania, editandoCampo, plan, setPestania]);

  // las pestañas aparecen recién cuando tienen algo; así tampoco hay botones apagados con el cursor de "prohibido".
  // Al terminar el flujo guiado, Mapa del campo desaparece de los resultados.
  const habilitada = (p: Pestania) =>
    p === "mapa"
      ? !terminado
      : p === "analisis" || p === "comparar"
      ? !!analisis
      : p === "plan"
      ? !!plan
      : true;

  const seccionesConfirmadas =
    pestania === "mapa" &&
    campo.secciones.length > 0 &&
    mensajes.some((m) => m.tarjeta?.tipo === "secciones" && m.tarjeta.hecha);
  // desde el paso 4 (ya contó cómo trabaja el campo) lo que importa es la charla: el chat ocupa ~65 % del ancho
  const chatAncho = seccionesConfirmadas && mensajes.some((m) => m.tarjeta?.tipo === "datos_sistema" && m.tarjeta.hecha);

  return (
    <div className="app">
      <AvisoFlotante />
      <ModalConfirmar />
      <ModalBorrarContorno />
      <ModalResultados />
      <VentanaHistoria />
      <EntradaHerramienta />
      <AbriendoEjemplo />
      {modalEditarCampo && <RevisarDatos onCerrar={() => setModalEditarCampo(false)} />}
      {/* tramas de cultivos, compartidas por todos los mapas y planos */}
      <svg id="tramas-globales" width="0" height="0" style={{ position: "absolute" }} aria-hidden>
        <defs>{definicionesTramas(catalogo?.cultivos || [])}</defs>
      </svg>
      <header className={`barra ${enResultados ? "con-notch" : ""}`}>
        {/* el logo lleva a la portada, como en casi todas las webs. Antes abría «¿Empezar de nuevo?», que
            borra el campo: eso queda solo en el menú «Tu campo» → «Empezar de cero». El campo queda guardado. */}
        <a className="marca interactiva" href="/" title="Ir a la portada (tu campo queda guardado)" aria-label="Seasons Ahead, ir a la portada">
          <MarcaFieldShift size={26} /> Seasons Ahead <small>para planificar tu campo con datos</small>
        </a>
        <div className="espacio" />
        {enResultados && (
          <NotchPartes partes={PESTANIAS.filter((p) => habilitada(p.id))} activa={pestania} onElegir={setPestania} />
        )}
        <div className="barra-derecha">
          {/* Sin el botón «Empezar mi campo» en el ejemplo. Para empezar uno propio: el logo lleva a la portada y «Planificar mi campo»
              arranca de cero. */}
          {terminado && !esEjemplo && (
            <button
              type="button"
              className="barra-btn-editar"
              onClick={() => setModalEditarCampo(true)}
              title="Revisar o cambiar los datos del campo"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
              </svg>
              <span>Editar mi campo</span>
            </button>
          )}
          <MenuCampo />
          <SelectorPais />
          <SelectorIdioma />
        </div>
      </header>
      <main className={`principal ${enResultados ? "en-resultados" : ""} ${chatPlegado[pestania] || pestania !== "mapa" || editandoCampo ? "chat-plegado" : ""} ${seccionesConfirmadas && !editandoCampo ? "chat-expandido" : ""} ${chatAncho && !editandoCampo ? "chat-ancho" : ""}`} data-vista={vistaMovil}>
        <section className="area-trabajo">
          {editandoCampo ? (
            <div className="barra-edicion-campo" role="region" aria-label="Modo de edición del campo">
              <div className="edicion-campo-info">
                <span className="edicion-campo-punto" aria-hidden />
                <strong>Estás editando el campo</strong>
                <span className="edicion-campo-sub">Cambiá las divisiones o el contorno en el mapa.</span>
              </div>
              <div className="edicion-campo-acciones">
                <button type="button" className="btn chico fantasma" onClick={cancelarEdicionCampo}>
                  Cancelar
                </button>
                <button
                  type="button"
                  className="btn chico primario"
                  onClick={confirmarEdicionCampo}
                >
                  {copiaEdicionCampo && (JSON.stringify(campo.contorno) !== JSON.stringify(copiaEdicionCampo.contorno) || JSON.stringify(campo.secciones) !== JSON.stringify(copiaEdicionCampo.secciones))
                    ? "Listo, rehacer el análisis"
                    : "Listo"}
                </button>
              </div>
            </div>
          ) : (
            <nav className={`pestanias ${enResultados ? "en-resultados" : ""}`} aria-label="Secciones de trabajo">
              {PESTANIAS.filter((p) => habilitada(p.id)).map((p) => (
                <button key={p.id} className={`pestania ${pestania === p.id ? "activa" : ""}`} onClick={() => setPestania(p.id)}>
                  {p.t}
                </button>
              ))}
            </nav>
          )}
          {analisisDesactualizado && !recalculandoAnalisis && !editandoCampo && (pestania === "analisis" || pestania === "comparar" || pestania === "plan") && (
            <div className="alerta-analisis-desactualizado" role="alert">
              <div className="alerta-desactualizado-texto">
                <span className="alerta-desactualizado-icono" aria-hidden>!</span>
                <span>Estos números son de una versión anterior de tu campo</span>
              </div>
              <button
                type="button"
                className="btn chico primario"
                onClick={() => void rehacerAnalisis()}
              >
                Rehacer el análisis
              </button>
            </div>
          )}
          <div key={enResultados ? pestania : "flujo"} className={`contenido ${pestania === "mapa" ? "lleno" : ""}`}>
            {pestania === "mapa" && <MapaCampo />}
            {recalculandoAnalisis && (pestania === "analisis" || pestania === "comparar" || pestania === "plan") ? (
              <div className="recalculando-pantalla">
                <Cargando que="calculando" size={32} etiqueta="Actualizando el análisis y el plan…" />
                <p className="recalculando-titulo">Actualizando el análisis y el plan con los datos de tu campo…</p>
                <small className="recalculando-sub">Analizando con datos de la NASA y el MGAP</small>
              </div>
            ) : (
              <>
                {pestania === "analisis" && <PanelAnalisis />}
                {pestania === "comparar" && <Comparar />}
                {pestania === "plan" && <Plan />}
              </>
            )}
          </div>
        </section>
        <Chat />
      </main>
      <nav className="movil-nav">
        <button className={vistaMovil === "chat" ? "activa" : ""} onClick={() => setVistaMovil("chat")}>
          Chat{chatMensajeNuevo ? <span className="movil-punto-nuevo" aria-label="Mensaje nuevo" /> : null}
        </button>
        {!terminado && (
          <button className={vistaMovil === "trabajo" && pestania === "mapa" ? "activa" : ""} onClick={() => { setVistaMovil("trabajo"); setPestania("mapa"); }}>Mapa</button>
        )}
        {plan && <button className={vistaMovil === "trabajo" && pestania === "plan" ? "activa" : ""} onClick={() => { setVistaMovil("trabajo"); setPestania("plan"); }}>Plan</button>}
        {analisis && <button className={vistaMovil === "trabajo" && pestania === "comparar" ? "activa" : ""} onClick={() => { setVistaMovil("trabajo"); setPestania("comparar"); }}>Comparar</button>}
      </nav>
    </div>
  );
}
