import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { create } from "zustand";
import { respuestaEjemplo, sugerenciasEjemplo } from "./respuestasEjemplo";
import { useApp, esAnalisisDesactualizado } from "../store";
import { Tarjeta } from "./Tarjetas";
import { FilaSugerencias } from "./FilaSugerencias";
import type { MensajeUI } from "../tipos";
import { AvatarBrote } from "./Presentacion";
import { Cargando } from "../comun/Cargando";
import { BotonLeer } from "./LeerEnVozAlta";
import { buscarLugares, irALugar, ListaLugares, pareceLugar } from "../mapa/BuscarLugar";
import { useIdioma } from "../i18n/idioma";
import { useRegion } from "../i18n/region";

/** En el paso 1, si lo que se escribe parece un lugar («Blanquillo», «sarandí 300 durazno», «ruta 5 km 200»), se
 * busca y se muestra con su departamento; con un solo resultado, el mapa va directo ahí.
 * Si no se encuentra nada, el texto sigue al asesor como cualquier mensaje. */
async function buscarEnElChat(texto: string, enviar: (t: string) => Promise<void>) {
  const id = () => Math.random().toString(36).slice(2, 10);
  const idYo = id(), idAsesor = id();
  useApp.setState((s) => ({ mensajes: [...s.mensajes, { id: idYo, rol: "productor", texto }, { id: idAsesor, rol: "asesor", texto: "", cargando: true }] }));
  let lugares: Awaited<ReturnType<typeof buscarLugares>> = [];
  try {
    lugares = await buscarLugares(texto);
  } catch {
    lugares = [];
  }
  if (!lugares.length) {
    useApp.setState((s) => ({ mensajes: s.mensajes.filter((m) => m.id !== idYo && m.id !== idAsesor) }));
    await enviar(texto);
    return;
  }
  const uno = lugares.length === 1 ? lugares[0] : null;
  const respuesta = uno
    ? `Te llevé a ${uno.nombre}${uno.departamento && uno.departamento !== uno.nombre ? ` (${uno.departamento})` : ""} en el mapa.`
    : "Encontré estos lugares. Tocá el tuyo:";
  useApp.setState((s) => ({ mensajes: s.mensajes.map((m) => (m.id === idAsesor ? { ...m, texto: respuesta, cargando: false, lugares: uno ? undefined : lugares } : m)) }));
  if (uno) irALugar(uno);
}

/** Desliza la lista hasta `top` en ~0,7 s con una curva suave. Si la persona mueve la rueda, se corta. */
function deslizar(contenedor: HTMLElement, top: number) {
  const desde = contenedor.scrollTop;
  const hasta = Math.max(0, Math.min(top, contenedor.scrollHeight - contenedor.clientHeight));
  const delta = hasta - desde;
  if (Math.abs(delta) < 2) return () => {};
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    contenedor.scrollTop = hasta;
    return () => {};
  }
  const ms = Math.min(810, 405 + Math.abs(delta) * 0.54);
  const t0 = performance.now();
  let cuadro = 0;
  let cortado = false;
  const cortar = () => { cortado = true; };
  contenedor.addEventListener("wheel", cortar, { once: true, passive: true });
  contenedor.addEventListener("touchstart", cortar, { once: true, passive: true });
  const paso = () => {
    if (cortado) return;
    const x = Math.min((performance.now() - t0) / ms, 1);
    const e = x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
    contenedor.scrollTop = desde + delta * e;
    if (x < 1) cuadro = requestAnimationFrame(paso);
  };
  cuadro = requestAnimationFrame(paso);
  return () => {
    cancelAnimationFrame(cuadro);
    contenedor.removeEventListener("wheel", cortar);
    contenedor.removeEventListener("touchstart", cortar);
  };
}

function LugaresDelChat({ m }: { m: MensajeUI }) {
  const [elegido, setElegido] = useState<number | null>(null);
  return <ListaLugares lugares={m.lugares!} elegido={elegido} alElegir={(r, i) => { setElegido(i); irALugar(r); }} />;
}

const SACAR_CULTIVO = "Sacar un cultivo de las opciones";

/** Las preguntas ya hechas en cada lote de un ejemplo («campo|lote» → preguntas, en orden): con eso se sabe cuáles
 * sacar de las sugerencias y cuáles de seguimiento mostrar. Fuera del componente, que se desmonta al
 * cerrar el chat. */
const useHechas = create<{ por: Record<string, string[]>; sumar: (clave: string, pregunta: string) => void }>((set) => ({
  por: {},
  sumar: (clave, pregunta) => set((s) => ({ por: { ...s.por, [clave]: [...(s.por[clave] || []).filter((x) => x !== pregunta), pregunta] } })),
}));

/** Dónde arrancó la charla nueva la última vez que se abrió el chat (y el id del mensaje de justo antes, para saber si
 * sigue siendo la misma conversación). Fuera del componente: sobrevive a que el chat se desmonte al cerrarlo. */
let islaAnterior: { desde: number; idAntes: string | null } | null = null;

const NOMBRE_HERR: Record<string, string> = {
  actualizar_campo: "Guardando en la ficha",
  pedir_al_productor: "Preparando formulario",
  analizar_campo: "Analizando con datos de la NASA y el MGAP",
  consultar_analisis: "Revisando el análisis",
  proponer_plan: "Armando el plan",
};

/** Markdown mínimo y seguro: **negrita**, listas con guion y párrafos. */
function Texto({ t }: { t: string }) {
  const bloques = t.split(/\n{2,}/);
  return (
    <>
      {bloques.map((b, i) => {
        const lineas = b.split("\n");
        if (lineas.every((l) => /^\s*[-•*]\s/.test(l))) {
          return (
            <ul key={i} style={{ margin: "4px 0", paddingLeft: 18 }}>
              {lineas.map((l, j) => <li key={j}>{enLinea(l.replace(/^\s*[-•*]\s/, ""))}</li>)}
            </ul>
          );
        }
        return <p key={i} style={{ margin: i ? "8px 0 0" : 0 }}>{lineas.map((l, j) => <span key={j}>{j > 0 && <br />}{enLinea(l)}</span>)}</p>;
      })}
    </>
  );
}

function enLinea(s: string) {
  const partes = s.split(/(\*\*[^*]+\*\*)/g);
  return partes.map((p, i) => (p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p.replace(/^#+\s/, "")}</span>));
}

/** Saca la respuesta que falló (y la pregunta que la originó) y la vuelve a mandar. */
async function reintentar(m: MensajeUI) {
  const s = useApp.getState();
  if (s.ocupado) return;
  const textoReintento = m.reintentar || (s.analisis ? "Analizar de nuevo" : "Analizar ahora con lo que hay");
  const i = s.mensajes.findIndex((x) => x.id === m.id);
  const antes = s.mensajes[i - 1];
  const sacar = new Set([m.id, ...(antes?.rol === "productor" && antes.texto === textoReintento ? [antes.id] : [])]);
  useApp.setState({ mensajes: s.mensajes.filter((x) => !sacar.has(x.id)) });
  await s.enviar(textoReintento);
}

function BarraProgreso({ progreso }: { progreso: { mensaje: string; avance?: number | null } }) {
  const tieneAvance = typeof progreso.avance === "number" && !Number.isNaN(progreso.avance);
  const objetivo = tieneAvance ? Math.round(progreso.avance! * 100) : 0;
  const [visual, setVisual] = useState(() => objetivo);
  const lento = useRef(0);

  useEffect(() => {
    if (!tieneAvance) return;
    const timer = setInterval(() => {
      setVisual((v) => {
        if (v < objetivo) {
          const paso = Math.max(1, Math.ceil((objetivo - v) / 3));
          return Math.min(objetivo, v + paso);
        }
        // Mientras el backend procesa consultas externas (MGAP, MODIS) y no llegan nuevos eventos,
        // avanzamos sutilmente 1% cada tanto (hasta un tope de +12%) para que la barra nunca
        // parezca congelada en un porcentaje fijo
        if (v >= objetivo && v < 94 && v < objetivo + 12) {
          return v + 1;
        }
        // Pasado ese tope seguía quieta. Con un solo lote el servidor no avisa nada entre el 30 % y el
        // 85 % (unos 20 s esperando al MGAP) y la barra quedaba clavada en 42 %. Ahora sigue de a 1 % cada ~2 s,
        // hasta 25 puntos por encima del último aviso.
        lento.current += 1;
        if (v >= objetivo && v < 94 && v < objetivo + 25 && lento.current % 14 === 0) return v + 1;
        return v;
      });
    }, 140);
    return () => clearInterval(timer);
  }, [objetivo, tieneAvance]);

  if (!tieneAvance) {
    return (
      <div className="progreso progreso-indeterminado">
        <div className="progreso-texto">
          <span className="progreso-etiqueta">
            <Cargando que="calculando" etiqueta={progreso.mensaje} />
            <span>{progreso.mensaje}</span>
          </span>
        </div>
        <div className="barra-progreso barra-indeterminada">
          <div />
        </div>
      </div>
    );
  }

  const pct = Math.min(100, Math.max(visual, objetivo));

  return (
    <div className="progreso">
      <div className="progreso-texto">
        <span>{progreso.mensaje}</span>
        <span className="progreso-pct">{pct}%</span>
      </div>
      <div className="barra-progreso">
        <div style={{ width: `${pct}%`, transition: "width 0.25s ease-out" }} />
      </div>
    </div>
  );
}

function Mensaje({ m, nuevo }: { m: MensajeUI; nuevo: boolean }) {
  // los mensajes que llegan mientras se usa la página entran suaves; los que ya estaban al abrirla, quietos
  const entra = nuevo ? "msg-entra" : "";
  const burbuja = useRef<HTMLDivElement>(null);
  if (m.tarjeta) {
    return (
      <div className={`msg asesor ${entra}`} style={{ maxWidth: "100%", width: "100%" }}>
        <Tarjeta m={m} />
      </div>
    );
  }
  const herr = (m.herramientas || []).filter((h) => h.nombre !== "pedir_al_productor");
  return (
    <div className={`msg ${m.rol} ${entra}`}>
      {herr.length > 0 && (
        <div className="herramientas">
          {herr.map((h, i) => {
            const enCurso = h.estado === "inicio" && !m.error;
            const conError = h.error || (h.estado === "inicio" && !!m.error);
            return (
              <span key={i} className={`herr ${conError ? "error" : h.estado === "fin" ? "fin" : ""}`}>
                {enCurso ? (
                  <Cargando que={h.nombre === "analizar_campo" ? "calculando" : h.nombre === "proponer_plan" ? "escribiendo" : "guardando"} color="#2f6fae" etiqueta={NOMBRE_HERR[h.nombre]} />
                ) : conError ? "!" : "✓"} {NOMBRE_HERR[h.nombre] || h.nombre}
              </span>
            );
          })}
        </div>
      )}
      {m.progreso && !m.error && (
        <BarraProgreso progreso={m.progreso} />
      )}
      {(m.texto || (m.cargando && !m.progreso && !m.error)) && (
        <div className="burbuja" ref={burbuja}>
          {m.texto ? <Texto t={m.texto} /> : <span className="escribiendo"><Cargando que="escribiendo" etiqueta="Escribiendo" /></span>}
        </div>
      )}
      {m.lugares && m.lugares.length > 0 && <LugaresDelChat m={m} />}
      {m.rol === "asesor" && m.texto && !m.cargando && (
        <div className="msg-acciones">
          <BotonLeer id={m.id} origen={burbuja} />
        </div>
      )}
      {m.error && (
        <div className="msg-error" role="alert">
          <span className="msg-error-icono" aria-hidden>!</span>
          <div>
            <p>{m.error}</p>
            <button className="btn chico" onClick={() => void reintentar(m)}>Probar de nuevo</button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Chat() {
  const {
    mensajes, enviar, ocupado, ia, modo, setModo, analisis, campo, cargarDemo, paisMapa,
    pestania, chatPlegado, setChatPlegado, chatMensajeNuevo, setVistaMovil,
    recalculandoAnalisis, rehacerAnalisis, esEjemplo, seccionSel, responderLocal,
  } = useApp();
  const region = useRegion((r) => r.region);
  const analisisDesactualizado = esAnalisisDesactualizado(campo, analisis);
  const plegado = chatPlegado[pestania];
  const esSuperpuesto = pestania !== "mapa";
  // al cerrarse, la isla se encoge hacia la cápsula antes de desaparecer
  const [cerrando, setCerrando] = useState(false);
  // tamaño de la píldora «Preguntar»: la isla nace recortada a ese tamaño y vuelve a él al cerrarse
  const pildora = useRef({ w: 150, h: 48 });
  const cerrar = () => {
    const isla = esSuperpuesto && window.matchMedia("(min-width: 961px)").matches && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!isla) {
      setChatPlegado(pestania, true);
      return;
    }
    setCerrando(true);
    window.setTimeout(() => {
      setCerrando(false);
      setChatPlegado(pestania, true);
    }, 300);
  };

  useEffect(() => {
    if (!esSuperpuesto || plegado) return;
    const alTecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cerrar();
      }
    };
    window.addEventListener("keydown", alTecla);
    return () => window.removeEventListener("keydown", alTecla);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [esSuperpuesto, plegado, pestania, setChatPlegado]);
  const [texto, setTexto] = useState("");
  const fin = useRef<HTMLDivElement>(null);
  const area = useRef<HTMLTextAreaElement>(null);

  const lista = useRef<HTMLDivElement>(null);
  const alAbrir = useRef<Set<string>>(new Set(mensajes.map((m) => m.id)));

  // Al abrir el chat desde la solución («Preguntar»), arranca como vacío: abajo, un «¿Qué querés saber?» con lugar
  // para la charla nueva, y la conversación anterior queda arriba, a un scroll.
  const [desdeIsla, setDesdeIsla] = useState<number | null>(null);
  const [altoLista, setAltoLista] = useState(0);
  // Antes se iba al fondo dos cuadros
  // después de pintar, y en esos cuadros se veía el principio de la charla vieja y después el salto. Ahora todo pasa
  // antes del primer cuadro (useLayoutEffect) y, mientras la isla termina de abrir, se mantiene abajo aunque algo de
  // la charla vieja cambie de alto, salvo que la persona mueva la rueda.
  // Al volver a abrirlo, la charla nueva arranca donde arrancó la vez anterior, así se
  // ve la última pregunta con su respuesta. Antes cada vez quedaba vacío y había que subir para leerla. La primera vez
  // después del análisis sigue arrancando vacío.
  useLayoutEffect(() => {
    if (!esSuperpuesto || plegado || !analisis) {
      setDesdeIsla(null);
      return;
    }
    const ms = useApp.getState().mensajes;
    const antes = islaAnterior;
    const sigue = antes && antes.desde <= ms.length && (ms[antes.desde - 1]?.id ?? null) === antes.idAntes;
    const desde = sigue ? antes!.desde : ms.length;
    islaAnterior = { desde, idAntes: ms[desde - 1]?.id ?? null };
    setDesdeIsla(desde);
    setAltoLista(lista.current?.clientHeight || 0);
  }, [esSuperpuesto, plegado, analisis]);
  useLayoutEffect(() => {
    const l = lista.current;
    if (desdeIsla == null || !l) return;
    // con una charla de la vez anterior, arriba queda la última pregunta (si la respuesta es larga se lee desde el
    // principio); si no, al fondo
    const alFondo = () => {
      const pregunta = [...l.querySelectorAll<HTMLElement>(".chat-nueva-charla > .msg.productor")].pop();
      const top = pregunta ? pregunta.getBoundingClientRect().top - l.getBoundingClientRect().top + l.scrollTop - 12 : l.scrollHeight;
      l.scrollTo({ top, behavior: "instant" });
    };
    alFondo();
    let tocado = false;
    const tocar = () => { tocado = true; };
    l.addEventListener("wheel", tocar, { passive: true });
    l.addEventListener("touchstart", tocar, { passive: true });
    const hasta = performance.now() + 700;
    let c = 0;
    const fijar = () => {
      if (tocado) return;
      alFondo();
      if (performance.now() < hasta) c = requestAnimationFrame(fijar);
    };
    c = requestAnimationFrame(fijar);
    return () => {
      cancelAnimationFrame(c);
      l.removeEventListener("wheel", tocar);
      l.removeEventListener("touchstart", tocar);
    };
  }, [desdeIsla, altoLista]);
  useEffect(() => {

    // Al empezar se lee la presentación desde arriba
    if (!campo.contorno && mensajes.length <= 2) {
      lista.current?.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const contenedor = lista.current;
    if (!contenedor) return;

    // Se mide después de pintar: la tarjeta recién agregada todavía no tiene su alto final en este efecto
    const cuadro = requestAnimationFrame(() => {
      // los mensajes son .msg (con «.mensaje» nunca encontraba ninguno). Con el chat abierto desde la solución, los
      // nuevos van dentro de «¿Qué querés saber?» (.chat-nueva-charla): sin mirarlos, el «último» era uno viejo de la
      // charla de antes y el chat subía hasta él al tocar una pregunta
      const msgs = contenedor.querySelectorAll<HTMLElement>(":scope > .msg, :scope > .chat-nueva-charla > .msg");
      const ultimo = msgs[msgs.length - 1];
      if (!ultimo) { fin.current?.scrollIntoView({ block: "end", behavior: "smooth" }); return; }
      // Con una tarjeta (secciones, sistema, historia…), su comienzo queda arriba: se ve el título, se llena desde el
      // primer campo y el botón entra en la pantalla. El texto del mensaje queda justo arriba, a un toque de scroll.
      const tarjeta = ultimo.querySelector<HTMLElement>(".tarjeta");
      let objetivoEl = tarjeta || (ultimo.offsetHeight > contenedor.clientHeight * 0.6 ? ultimo : null);
      const arribaDe = (el: HTMLElement) => el.getBoundingClientRect().top - contenedor.getBoundingClientRect().top + contenedor.scrollTop;
      // Si la pregunta del asesor que va justo antes de la tarjeta entra junto con la tarjeta, se baja
      // hasta la pregunta (antes quedaba cortada arriba, como «¿Qué sembraste…» al pasar al paso 4)
      if (tarjeta) {
        const previo = msgs[msgs.length - 2];
        if (previo?.classList.contains("asesor") && !previo.querySelector(".tarjeta")) {
          const alto = ultimo.getBoundingClientRect().bottom - previo.getBoundingClientRect().top;
          if (alto <= contenedor.clientHeight - 24) objetivoEl = previo;
        }
      }
      parar = objetivoEl
        ? deslizar(contenedor, arribaDe(objetivoEl) - 12)
        : deslizar(contenedor, contenedor.scrollHeight);
    });
    let parar = () => {};
    return () => { cancelAnimationFrame(cuadro); parar(); };
    // también al cambiar los lotes: la tarjeta de secciones crece y suma «Listo, continuar…» abajo
  }, [mensajes, campo.contorno, campo.secciones.length]);

  function mandar(e?: React.FormEvent) {
    e?.preventDefault();
    const t = texto.trim();
    if (!t || ocupado) return;
    setTexto("");
    if (!campo.contorno && pareceLugar(t)) {
      void buscarEnElChat(t, enviar);
      return;
    }
    void enviar(t);
  }

  // en un ejemplo, la pregunta ya hecha se va y entran las que siguen de su respuesta; se lleva por lote, porque
  // cada respuesta es del lote que se está mirando
  const claveHechas = `${campo.id}|${seccionSel || analisis?.secciones[0]?.id || ""}`;
  const hechas = useHechas((h) => h.por[claveHechas]) || [];
  const sugerencias = analisis
    ? analisisDesactualizado
      ? ["Rehacer el análisis", ...(modo === "ia" ? ["¿Por qué sale mejor esta opción?"] : [])]
      // en los ejemplos las preguntas tienen la respuesta ya hecha (chat/respuestasEjemplo.ts): van aunque no haya IA
      : esEjemplo
      ? sugerenciasEjemplo(hechas, analisis, seccionSel, [SACAR_CULTIVO])
      : modo === "ia"
      // preguntas sobre las decisiones: el asesor las justifica con el análisis y, si le contás algo nuevo,
      // lo guarda, recalcula y dice qué cambió (agente/prompt.py)
      ? ["¿Por qué sale mejor esta opción?", "¿Por qué no otra rotación?", SACAR_CULTIVO, "Te cuento algo que puede cambiar el análisis", "Quiero más ingreso este año"]
      : [SACAR_CULTIVO, "Analizar de nuevo"]
    : [];
  // «Sacar un cultivo» no se manda: deja escrito «No quiero » para que complete cuál
  const elegirSugerencia = (s: string) => {
    const hecha = esEjemplo && analisis ? respuestaEjemplo(s, analisis, seccionSel) : null;
    if (hecha) {
      useHechas.getState().sumar(claveHechas, s);
      void responderLocal(s, hecha);
      return;
    }
    if (s !== SACAR_CULTIVO) {
      void enviar(s);
      return;
    }
    setTexto(useIdioma.getState().idioma === "en" ? "I don't want " : "No quiero ");
    requestAnimationFrame(() => {
      const a = area.current;
      if (!a) return;
      a.focus();
      a.setSelectionRange(a.value.length, a.value.length);
    });
  };  // «Analizar ahora con lo que hay» se sacó

  if (plegado) {
    return (
      <button
        className="chat-flotante-btn no-imprimir"
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          pildora.current = { w: Math.round(r.width), h: Math.round(r.height) };
          setChatPlegado(pestania, false);
          setVistaMovil("chat");
        }}
        aria-label="Abrir el chat"
        title="Abrir el chat"
      >
        <span className="chat-flotante-icono">
          <AvatarBrote size={28} />
          {chatMensajeNuevo && <span className="chat-punto-nuevo" aria-label="Mensaje nuevo" />}
        </span>
        <span className="chat-flotante-txt">Preguntar</span>
      </button>
    );
  }

  return (
    <>
      {esSuperpuesto && (
        <div
          className={`chat-telon ${cerrando ? "cerrando" : ""}`}
          onClick={cerrar}
          aria-hidden="true"
        />
      )}
      <div className={`columna-chat ${esSuperpuesto ? "chat-superpuesto" : ""} ${cerrando ? "cerrando" : ""}`}
        style={esSuperpuesto ? ({ "--pildora-w": `${pildora.current.w}px`, "--pildora-h": `${pildora.current.h}px` } as React.CSSProperties) : undefined}>
        <div className="chat-cabecera">
          <AvatarBrote size={22} />
          <p>{(campo.contorno ? region === "US" : paisMapa === "US")
            ? (modo === "ia" ? "Conversación con IA, con datos de la NASA y del USDA" : "Con datos de la NASA y del USDA")
            : (modo === "ia" ? "Conversación con IA, con datos de la NASA y del MGAP" : "Con datos de la NASA y del MGAP")}</p>
          <button
            className="btn texto chico chat-achicar"
            onClick={cerrar}
            aria-label="Cerrar el chat"
            title="Cerrar el chat"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      <div className="mensajes" aria-live="polite" ref={lista}>
        {analisisDesactualizado && !recalculandoAnalisis && (
          <div className="chat-alerta-desactualizado">
            <span>Cambiaste datos del campo.</span>
            <button
              type="button"
              className="btn chico primario"
              onClick={() => void rehacerAnalisis()}
            >
              Rehacer el análisis
            </button>
          </div>
        )}
        {desdeIsla == null ? (
          mensajes.map((m) => <Mensaje key={m.id} m={m} nuevo={!alAbrir.current.has(m.id)} />)
        ) : (
          <>
            {mensajes.slice(0, desdeIsla).map((m) => <Mensaje key={m.id} m={m} nuevo={false} />)}
            <div className="chat-nueva-charla" style={{ minHeight: Math.max(0, altoLista - 32) }}>
              <div className="chat-nueva-charla-saludo">
                <AvatarBrote size={40} />
                <b>¿Qué querés saber de tu plan?</b>
                <span>Preguntame por cualquier lote, cultivo o número. La charla de antes está más arriba.</span>
              </div>
              {mensajes.slice(desdeIsla).map((m) => <Mensaje key={m.id} m={m} nuevo={!alAbrir.current.has(m.id)} />)}
            </div>
          </>
        )}
        <div ref={fin} />
      </div>
      <div className="compositor">
        {!campo.contorno && !ocupado && (
          <div className="sugerencias">
            {/* Eran cuatro («Ir a donde estoy»,
                que ya está sobre el mapa, el ejemplo de Durazno, el de Iowa y «Mi campo está en EE. UU.») y tapaban la
                tarjeta del paso 1. El país se elige en la barra de arriba y el ejemplo es el de ese país. */}
            <button className="chip" onClick={() => void cargarDemo(paisMapa === "US" ? "us" : "uy")}>
              {paisMapa === "US" ? "Ver el ejemplo de Iowa" : "Ver un campo de ejemplo"}
            </button>
          </div>
        )}
        {sugerencias.length > 0 && !ocupado && (
          <FilaSugerencias>
            {sugerencias.map((s) => <button key={s} className="chip" onClick={() => elegirSugerencia(s)}>{s}</button>)}
          </FilaSugerencias>
        )}
        <form onSubmit={mandar}>
          {/* mientras contesta: «Un momento…». Decía «Calculando…» también al saludar o al contestar una pregunta, donde
              no se calcula nada; el progreso del análisis ya se ve en la burbuja */}
          <textarea
            ref={area}
            rows={1}
            value={texto}
            placeholder={ocupado ? "Un momento…" : "Escribí tu respuesta o una pregunta…"}
            onChange={(e) => {
              setTexto(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(140, e.target.scrollHeight) + "px";
              e.target.style.overflowY = e.target.scrollHeight > 140 ? "auto" : "hidden"; // sin barra mientras entra
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) mandar(e);
            }}
          />
          <button className="btn primario" type="submit" disabled={ocupado || !texto.trim()} aria-label="Enviar">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>
        </form>
        {/* con el análisis hecho ya no hay entrevista que seguir: el link solo confundía */}
        {ia && !(modo === "ia" && analisis) && (
          <div className="aviso-modo">
            <span />
            <button className="btn texto chico" style={{ padding: "0 4px" }} onClick={() => setModo(modo === "ia" ? "guiado" : "ia")}>{modo === "ia" ? "Pasar a la entrevista guiada" : "Pasar a la conversación libre"}</button>
          </div>
        )}
      </div>
    </div>
    </>
  );
}
