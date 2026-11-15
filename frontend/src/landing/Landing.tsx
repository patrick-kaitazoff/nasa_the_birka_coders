import { useEffect, useRef, useState } from "react";
import type { CampoTrigo } from "./CampoTrigo";
import { MarcaFieldShift } from "../comun/Cultivo";
import { SelectorIdioma } from "../i18n/SelectorIdioma";
import { Terrenos } from "./Terrenos";
import { adelantarEjemplos } from "./adelantarEjemplos";

const DATOS = [
  { sigla: "GPM", t: "GPM IMERG · 10 km", d: "Lluvia diaria de satélite desde el 2000: cuántos años hay seca en la floración de cada cultivo y cuándo cae la lluvia que erosiona." },
  { sigla: "POWER", t: "NASA POWER", d: "Temperatura, radiación y viento diarios desde 1981: calor, heladas y cuánta agua pide cada cultivo." },
  { sigla: "MODIS", t: "MODIS NDVI · 250 m", d: "El verdor de cada sección cada 16 días: qué rotación se hizo de verdad y cuánto tiempo quedó el suelo descubierto." },
  { sigla: "HLS", t: "HLS · Landsat + Sentinel-2 · 30 m", d: "La foto del campo sin nubes, mes a mes, de fondo en el mapa." },
  { sigla: "SMAP", t: "SMAP L4 · humedad en las raíces", d: "Qué tan húmedo estuvo el suelo donde toman agua los cultivos, comparado con lo normal de la zona." },
  { sigla: "SRTM", t: "SRTM · relieve · 30 m", d: "La pendiente de cada cuadrado del campo: dónde se lava más el suelo, en un visor 3D." },
  { sigla: "MGAP", t: "Suelos del MGAP", d: "Erodabilidad y tolerancia de cada suelo, con la misma ecuación del Plan de Uso y Manejo." },
];

/** Cuánto se espera para armar el trigo 3D desde que aparece el texto: lo que tarda la entrada (landing.css). */
const ESPERA_3D_MS = 800;

/** Cómo se ve el campo de fondo mientras se recorre la página: cada sección dice su vista (0 a ras del trigo,
 * 1 desde arriba), si el campo se pinta como lo vería un satélite y cuánto se oscurece para leer. */
function useEscena(campo: React.RefObject<CampoTrigo | null>, velo: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const actualizar = () => {
      const secs = [...document.querySelectorAll<HTMLElement>("[data-vista]")];
      if (!secs.length) return;
      const medio = scrollY + innerHeight / 2;
      const centros = secs.map((s) => s.offsetTop + s.offsetHeight / 2);
      const val = (s: HTMLElement, k: string) => Number(s.dataset[k] || 0);
      let i = 0;
      while (i < secs.length - 1 && centros[i + 1] < medio) i++;
      const j = Math.min(i + 1, secs.length - 1);
      let f = j === i ? 0 : Math.min(Math.max((medio - centros[i]) / (centros[j] - centros[i]), 0), 1);
      f = f * f * (3 - 2 * f);
      const mezcla = (k: string) => val(secs[i], k) + (val(secs[j], k) - val(secs[i], k)) * f;
      campo.current?.setEscena(mezcla("vista"), mezcla("sat"));
      if (velo.current) velo.current.style.opacity = String(mezcla("velo"));
    };
    actualizar();
    addEventListener("scroll", actualizar, { passive: true });
    addEventListener("resize", actualizar);
    return () => {
      removeEventListener("scroll", actualizar);
      removeEventListener("resize", actualizar);
    };
  }, [campo, velo]);
}

export function Landing() {
  const lienzo = useRef<HTMLCanvasElement>(null);
  const velo = useRef<HTMLDivElement>(null);
  const campo = useRef<CampoTrigo | null>(null);
  const [sinWebgl, setSinWebgl] = useState(false);
  const [listo, setListo] = useState(false);
  const [acariciado, setAcariciado] = useState(false);
  const [despegando, setDespegando] = useState(false);
  // «bajá para ver los ejemplos» se va apenas se baja un poco la página
  const [bajo, setBajo] = useState(false);
  const sombra = useRef<HTMLDivElement>(null);
  // los archivos de los cuatro ejemplos se bajan solos, sin apuro, cuando la portada ya cargó
  useEffect(() => adelantarEjemplos(), []);
  useEffect(() => {
    const alBajar = () => {
      setBajo(scrollY > 80);
      // la sombra del texto de la portada se va a medida que se baja
      if (sombra.current) sombra.current.style.opacity = String(Math.max(0, 1 - scrollY / (innerHeight * 0.8)));
    };
    alBajar();
    addEventListener("scroll", alBajar, { passive: true });
    return () => removeEventListener("scroll", alBajar);
  }, []);
  const tactil = typeof matchMedia !== "undefined" && matchMedia("(pointer: coarse)").matches;

  // El trigo 3D (three.js, ~130 KB) se baja aparte: el texto se muestra enseguida sobre la foto del trigo, y el 3D
  // aparece fundiéndose cuando ya compiló sus shaders y dibujó un cuadro.
  // Crear el 3D deja la página sin responder de 0,3 a 0,5 s. Antes pasaba apenas aparecía el texto. Ahora el código se baja
  // igual desde el principio, pero se arma cuando el texto ya terminó de entrar y la página está quieta: mientras
  // tanto se ve la foto del trigo, que es el mismo cuadro.
  useEffect(() => {
    let cancelado = false;
    const paginaQuieta = new Promise<void>((ok) => {
      setTimeout(() => {
        if (typeof requestIdleCallback === "function") requestIdleCallback(() => ok(), { timeout: 500 });
        else ok();
      }, ESPERA_3D_MS);
    });
    Promise.all([import("./CampoTrigo"), paginaQuieta])
      .then(async ([{ CampoTrigo }]) => {
        if (cancelado || !lienzo.current) return;
        const c = new CampoTrigo(lienzo.current, { arrancar: false, alAcariciar: () => setTimeout(() => setAcariciado(true), 1800) });
        campo.current = c;
        dispatchEvent(new Event("scroll")); // la vista según dónde quedó la página
        await c.preparar();
        if (cancelado) return;
        c.arrancar(() => setListo(true));
      })
      .catch(() => {
        if (!cancelado) setSinWebgl(true);
      });
    return () => {
      cancelado = true;
      campo.current?.destruir();
      campo.current = null;
    };
  }, []);
  useEscena(campo, velo);

  // la foto satelital de Uruguay con que abre la herramienta se baja acá, sin apuro, cuando el trigo ya está: al llegar
  // a /app sale de la caché del navegador y el mapa no queda oscuro esperándola. Son las teselas de Esri
  // de los niveles 6 y 7 que cubren el país con margen (42 teselas, menos de 1 MB).
  useEffect(() => {
    if (!listo) return;
    const t = window.setTimeout(() => {
      const url = (z: number, y: number, x: number) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
      const grilla: Array<[number, number, number, number, number]> = [[6, 37, 39, 20, 23], [7, 74, 78, 41, 46]];
      for (const [z, y0, y1, x0, x1] of grilla) {
        for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
          const img = new Image();
          img.decoding = "async";
          img.src = url(z, y, x);
        }
      }
    }, 1500);
    return () => clearTimeout(t);
  }, [listo]);

  // al volver con el botón atrás, el navegador puede mostrar la portada tal como quedó al despegar
  useEffect(() => {
    const alMostrar = (e: PageTransitionEvent) => {
      if (!e.persisted) return;
      setDespegando(false);
    };
    addEventListener("pageshow", alMostrar);
    return () => removeEventListener("pageshow", alMostrar);
  }, []);

  /** Al tocar un link a la herramienta. Se navega
   * enseguida y el navegador funde la portada con la herramienta, que pinta su esqueleto al instante (app.html). Antes
   * la cámara subía 0,56 s, se sacaba una foto del trigo (otros 0,1 a 0,2 s trabando la página) y recién ahí se
   * navegaba. Queda anotado que se llegó desde la portada y, salvo el ejemplo, que se arranca de cero. */
  function alTocar(e: React.MouseEvent) {
    const a = (e.target as HTMLElement).closest("a");
    const href = a?.getAttribute("href") || "";
    if (!a || !href.startsWith("/app")) return;
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target === "_blank") return;
    try {
      const ahora = String(Date.now());
      sessionStorage.setItem("fs:desdePortada", ahora);
      if (/[?&]demo\b/.test(href)) sessionStorage.removeItem("fs:deCero");
      else sessionStorage.setItem("fs:deCero", ahora);
    } catch { /* sin almacenamiento: abre como siempre */ }
    setDespegando(true);
  }

  return (
    <div className={`lp ${sinWebgl ? "sin-webgl" : ""} ${despegando ? "despegando" : ""}`} onClickCapture={alTocar}>
      <canvas ref={lienzo} className={`lp-lienzo ${listo ? "listo" : ""}`} aria-hidden />
      <div ref={sombra} className="lp-sombra" aria-hidden />
      <div ref={velo} className="lp-velo" aria-hidden />

      {/* con la página bajada, la barra toma fondo: transparente, sus enlaces chocaban con los títulos y botones que
          pasaban por detrás */}
      <header className={`lp-barra ${bajo ? "con-fondo" : ""}`}>
        <a className="lp-marca" href="#arriba"><MarcaFieldShift size={28} /> Seasons Ahead</a>
        <nav className="lp-enlaces" aria-label="Secciones">
          <a href="#terrenos">Ejemplos</a>
          <a href="#para-que">Para qué sirve</a>
          <a href="#datos">Datos de la NASA</a>
          <a href="#apoyo">Para quién</a>
        </nav>
        <SelectorIdioma />
        <a className="lp-btn chico" href="/app">Abrir la herramienta</a>
      </header>

      <main id="arriba">
        <section className="lp-heroe" data-vista="0" data-sat="0" data-velo="0">
          <p className="lp-antetitulo">NASA Space Apps Challenge 2026 · Field Shift: Adapting Farms with NASA Data</p>
          {/* «desde el espacio» en color trigo y en su renglón, el único golpe de color del título */}
          <h1>Tu campo, visto <em>desde el espacio.</em></h1>
          <p className="lp-bajada">
            Una herramienta para decidir qué sembrar en cada lote en los próximos años. Compara rotaciones: cuánto
            suelo se pierde y en cuántos años de cada 10 falta agua en la floración.
          </p>
          <div className="lp-acciones">
            <a className="lp-btn" href="/app">Planificar mi campo</a>
            <a className="lp-btn claro" href="/app?demo">Ver un campo de ejemplo</a>
          </div>
          <p className={`lp-pista ${acariciado || bajo ? "oculta" : ""}`} aria-hidden>
            <span className="lp-pista-punto" />
            {tactil ? "Pasá el dedo por el trigo" : "Pasá el mouse por el trigo"}
          </p>
          {/* */}
          <a className={`lp-bajar ${bajo ? "oculta" : ""}`} href="#terrenos" aria-label="Bajar a los campos de ejemplo">
            <svg width="44" height="44" viewBox="0 0 44 44" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M11 11 22 21 33 11" />
              <path d="M11 23 22 33 33 23" />
            </svg>
          </a>
        </section>

        {/* Tres terrenos de ejemplo en 3D, con su solución; justo después de la portada */}
        <section id="terrenos" className="lp-seccion" data-vista="0.1" data-sat="0" data-velo="0.6">
          <div className="lp-caja">
            <p className="lp-etiqueta">Tres campos de ejemplo</p>
            <h2>Mirá la solución en tres paisajes distintos.</h2>
            <p className="lp-texto">
              Al pie de un volcán en Chile, en la curva de un río entre viñedos en Alemania y al borde de las quebradas
              del norte uruguayo. Cada uno con su plan por lote, el porqué de cada opción y el chat para preguntar.
            </p>
            <Terrenos />
          </div>
        </section>

        {/* Justo debajo de los ejemplos, que es donde dan ganas de probar con el campo propio */}
        <section className="lp-final" data-vista="0.1" data-sat="0" data-velo="0.35">
          <h2>Probalo con tu campo.</h2>
          <div className="lp-acciones">
            {/* Un solo botón. EE. UU. y el relieve 3D son funciones de la herramienta (el país
                se elige en el paso 1 y el 3D está en el Plan), no botones aparte */}
            <a className="lp-btn" href="/app">Planificar mi campo</a>
          </div>
        </section>

        {/*
            Para cualquier país, no solo Uruguay */}
        <section id="para-que" className="lp-seccion" data-vista="0.2" data-sat="0" data-velo="0.5">
          {/* Tres puntos numerados en vez de dos párrafos largos, con el mismo contenido */}
          <div className="lp-caja">
            <p className="lp-etiqueta">Para qué sirve</p>
            <h2>Elegir la rotación de cada lote con datos, antes de sembrar.</h2>
            <p className="lp-texto">
              Cada campo pierde suelo a su manera y tiene su propio riesgo de seca. Seasons Ahead prueba varias rotaciones
              en cada lote, en campos de cualquier parte del mundo, y muestra para cada una:
            </p>
            <ol className="lp-pasos">
              <li>
                <span className="lp-num" data-no-traducir>1</span>
                <h3>Cuánto suelo se pierde</h3>
                <p>Frente a lo que ese suelo aguanta, según la pendiente, el tipo de suelo y la forma en que llueve.</p>
              </li>
              <li>
                <span className="lp-num" data-no-traducir>2</span>
                <h3>En cuántos años de cada 10 falta agua</h3>
                <p>Justo cuando florecen los cultivos, con el clima de los últimos 35 años.</p>
              </li>
              <li>
                <span className="lp-num" data-no-traducir>3</span>
                <h3>Cómo queda frente a lo que hacés hoy</h3>
                <p>
                  Y frente a la norma: el Plan de Uso y Manejo del MGAP en Uruguay y el límite de pérdida de suelo del
                  NRCS en Estados Unidos.
                </p>
              </li>
            </ol>
            <p className="lp-texto">Al final tenés un plan por temporada y un informe para revisar con tu agrónomo.</p>
          </div>
        </section>

        <section id="datos" className="lp-seccion" data-vista="1" data-sat="1" data-velo="0.35">
          <div className="lp-caja">
            <p className="lp-etiqueta">Datos de la NASA</p>
            <h2>Cada número sale de un dato que se puede revisar.</h2>
            <p className="lp-texto">
              Detrás, el campo cambió de color: así se ve un índice de vegetación por potrero (ilustración). La app hace
              lo mismo con los datos reales de tu campo, y siempre dice de dónde salió cada cifra.
            </p>
            <ul className="lp-datos">
              {DATOS.map((d) => (
                <li key={d.sigla}>
                  <span className="lp-sigla" data-no-traducir>{d.sigla}</span>
                  <h3>{d.t}</h3>
                  <p>{d.d}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section id="apoyo" className="lp-seccion" data-vista="0.3" data-sat="0" data-velo="0.5">
          <div className="lp-caja angosta">
            <p className="lp-etiqueta">Para quién</p>
            <h2>Una ayuda para decidir, no una receta.</h2>
            <p className="lp-texto">
              Seasons Ahead es para productores, agrónomos y técnicos que quieren conversar con números. No reemplaza al
              agrónomo ni a quien conoce el campo: para cada opción dice qué revisar con ellos antes de decidir.
            </p>
            <ul className="lp-lista">
              <li>La app no ve plagas ni malezas, ni conoce el mercado, los fletes o la maquinaria.</li>
              <li>Cuando la erosión queda cerca de lo que aguanta el suelo, pide calcularla con el programa oficial del MGAP.</li>
              <li>Muestra la incertidumbre: rangos, no un solo número.</li>
            </ul>
          </div>
        </section>

        {/* La página cierra con los botones; antes terminaba en «Para quién» y había que volver a subir */}
        <section className="lp-final lp-cierre" data-vista="0.3" data-sat="0" data-velo="0.3">
          <h2>Empezá por tu campo.</h2>
          <div className="lp-acciones">
            <a className="lp-btn" href="/app">Planificar mi campo</a>
            <a className="lp-btn claro" href="/app?demo">Ver un campo de ejemplo</a>
          </div>
        </section>
      </main>

      <footer className="lp-pie">
        <p>Hecho para el NASA Space Apps Challenge 2026. Usa datos abiertos de la NASA y del MGAP.</p>
        <p>No es un producto oficial de la NASA ni está respaldado por ella.</p>
      </footer>
    </div>
  );
}
