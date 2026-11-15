/** Portada B: agro-tech luminosa (crema, lima y oliva). Estuvo en `/` al
 *; desde ahí está en `/b` y la A (el trigo al atardecer) volvió a `/`. La
 * herramienta usa la misma estética (`src/tema-b.css`).
 *
 * El hero lleva un video de fondo cuando esté (`VIDEO`); mientras tanto, el mismo campo de trigo en 3D de la
 * portada A, de día y con nubes, que también se acaricia con el mouse. */
import { useEffect, useRef, useState } from "react";
import { CampoTrigo } from "../landing/CampoTrigo";
import { SelectorIdioma } from "../i18n/SelectorIdioma";
import { useIdioma } from "../i18n/idioma";

/** Cuando estén el video y su póster (en `public/`), poner acá las rutas: el 3D deja de cargarse. */
const VIDEO: { src: string; poster: string } | null = null;

const FUENTES = ["NASA POWER", "GPM IMERG", "MODIS", "HLS", "Landsat", "Sentinel-2", "SMAP", "SRTM", "Earthdata", "MGAP"];

const RASGOS = [
  "Clima diario desde 1981",
  "Lo que vio el satélite en cada sección",
  "Humedad del suelo donde están las raíces",
  "Relieve y erosión cuadrado por cuadrado",
  "Rotaciones comparadas con su incertidumbre",
];

const PASOS = [
  { n: "01", t: "Ubicá tu campo", d: "Dibujá el contorno en el mapa, subí un KML o un shapefile, o elegí la zona y marcá las secciones." },
  { n: "02", t: "La app trae los datos", d: "Clima diario desde 1981, lo que vio el satélite en cada sección, la humedad del suelo, el relieve y los suelos del MGAP." },
  { n: "03", t: "Compará y decidí", d: "Cada rotación con su erosión, su riesgo de seca y su ingreso, con el rango de incertidumbre. Y un plan para imprimir." },
];

const PARA_QUIEN = [
  { quien: "PRODUCTOR", d: "Ver qué rotación le conviene a cada sección de tu campo.", items: ["Tu campo en el mapa", "Rotaciones comparadas", "Plan para imprimir"] },
  { quien: "AGRÓNOMO", d: "Llegar a la charla con el productor con los números hechos.", items: ["Erosión con la ecuación del Plan de Uso", "Rangos de incertidumbre", "Qué revisar en el campo"], destacado: true },
  { quien: "TÉCNICO O COOPERATIVA", d: "Mirar varios campos de la zona con los mismos datos.", items: ["Datos abiertos de la NASA", "Ficha para guardar y compartir", "En castellano e inglés"] },
];

const DESAFIO = [
  { pide: "Una herramienta que apoye la decisión, no que la reemplace.", responde: "Cada opción trae qué revisar con el agrónomo antes de decidir." },
  { pide: "Combinar datos de la Tierra de la NASA con el suelo y las prioridades del productor.", responde: "POWER, MODIS, HLS, SMAP y SRTM, junto con los suelos del MGAP y lo que te importa a vos." },
  { pide: "Marcar dónde el criterio humano es especialmente importante.", responde: "Rangos de incertidumbre y una lista de lo que hay que mirar en el campo." },
];

const PREGUNTAS = [
  { p: "¿Cuánto cuesta?", r: "Nada. No hace falta crear una cuenta: abrís la herramienta y empezás." },
  { p: "¿De dónde salen los datos?", r: "De servicios abiertos de la NASA (POWER, MODIS, HLS, SMAP y SRTM) y de los suelos del MGAP. Cada número dice de dónde salió." },
  { p: "¿Reemplaza al agrónomo?", r: "No. Es una ayuda para conversar con números. No ve plagas ni malezas, ni conoce el mercado o la maquinaria: para cada opción dice qué revisar con quien conoce el campo." },
  { p: "¿Sirve fuera de Uruguay?", r: "Los datos de la NASA cubren todo el mundo, pero los suelos y la ecuación de erosión son los del MGAP: hoy la herramienta está pensada para Uruguay." },
  { p: "¿Qué tan exacto es?", r: "Depende del dato: el clima es de una grilla de unos 50 km y el satélite ve cuadrados de 250 m o 30 m. Por eso muestra rangos y avisa cuando una sección es chica para el satélite." },
];

function useHeroFondo() {
  const lienzo = useRef<HTMLCanvasElement>(null);
  const [sinWebgl, setSinWebgl] = useState(false);
  useEffect(() => {
    if (VIDEO || !lienzo.current) return;
    let campo: CampoTrigo | null = null;
    try {
      campo = new CampoTrigo(lienzo.current, { paleta: "dia", polen: 90 });
    } catch {
      setSinWebgl(true);
    }
    return () => campo?.destruir();
  }, []);
  return { lienzo, sinWebgl };
}

function Marca() {
  return (
    // la marca de Seasons Ahead (horizonte, loma y sol), en lima
    <svg width="30" height="30" viewBox="0 0 64 64" aria-hidden>
      <path d="M8 46 L56 46" stroke="#ECF86E" strokeWidth="5" strokeLinecap="round" />
      <path d="M13 37 Q32 16 51 37" fill="none" stroke="#ECF86E" strokeWidth="5" strokeLinecap="round" />
      <circle cx="45" cy="15" r="6" fill="#ECF86E" />
    </svg>
  );
}

function Clima() {
  return (
    <div className="pb-clima" aria-label="Ejemplo de datos de un campo">
      <div className="pb-clima-arco">
        <svg className="pb-clima-camino" viewBox="0 0 400 200" aria-hidden>
          <path d="M 40 200 A 160 160 0 0 1 360 200" fill="none" stroke="rgba(255,255,255,.55)" strokeWidth="1.5" strokeDasharray="2 7" strokeLinecap="round" />
        </svg>
        <div className="pb-sol" aria-hidden>
          <span className="pb-sol-cono" />
          <span className="pb-sol-disco" />
        </div>
        <p className="pb-clima-etiqueta pb-mono">EJEMPLO · PAYSANDÚ</p>
        <p className="pb-temp" data-no-traducir>24°<small>/18°</small></p>
      </div>
      <ul className="pb-clima-tarjetas">
        {[
          { v: "54%", t: "HUMEDAD EN RAÍCES" },
          { v: "72%", t: "SUELO CUBIERTO" },
          { v: "30%", t: "AÑOS CON SECA" },
        ].map((c, i) => (
          <li key={c.t}>
            <span className="pb-dato" data-no-traducir>{c.v}</span>
            <span className="pb-tarjeta-vidrio" aria-hidden>
              <span className={`pb-anillo a${i}`} />
              <span className={`pb-anillo b${i}`} />
              <span className={`pb-anillo c${i}`} />
            </span>
            <span className="pb-mono pb-tarjeta-nombre">{c.t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** La lista grande: se va prendiendo una por una mientras se baja. */
function Rasgos() {
  const caja = useRef<HTMLElement>(null);
  const [activo, setActivo] = useState(0);
  useEffect(() => {
    const medir = () => {
      const el = caja.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const recorrido = Math.max(r.height - innerHeight, 1);
      const p = Math.min(Math.max(-r.top / recorrido, 0), 0.999);
      setActivo(Math.floor(p * RASGOS.length));
    };
    medir();
    addEventListener("scroll", medir, { passive: true });
    addEventListener("resize", medir);
    return () => {
      removeEventListener("scroll", medir);
      removeEventListener("resize", medir);
    };
  }, []);
  return (
    <section className="pb-rasgos" ref={caja} id="sobre">
      <div className="pb-rasgos-fijo">
        <div className="pb-nubes" aria-hidden>
          <span className="n1" /><span className="n2" /><span className="n3" /><span className="n4" /><span className="n5" />
        </div>
        <div className="pb-rasgos-etiquetas pb-mono">
          <span>DATOS DE LA NASA</span>
          <span>SECCIÓN POR SECCIÓN</span>
          <span>UNA AYUDA, NO UNA RECETA</span>
        </div>
        <div className="pb-rasgos-centro">
          <span className="pb-insignia pb-mono">SOBRE SEASONS AHEAD</span>
          <ol className="pb-rasgos-lista">
            {RASGOS.map((t, i) => (
              <li key={t} className={i === activo ? "activo" : i < activo ? "visto" : ""} aria-current={i === activo ? "step" : undefined}>{t}</li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

export function PortadaB() {
  const { lienzo, sinWebgl } = useHeroFondo();
  const { idioma } = useIdioma();

  return (
    <div className="pb">
      <section className="pb-heroe">
        <div className={`pb-heroe-caja ${sinWebgl ? "sin-webgl" : ""}`}>
          {VIDEO ? (
            <video className="pb-fondo" src={VIDEO.src} poster={VIDEO.poster} autoPlay muted loop playsInline aria-hidden />
          ) : (
            <canvas ref={lienzo} className="pb-fondo" aria-hidden />
          )}
          <div className="pb-niebla" aria-hidden />
          <div className="pb-degrade" aria-hidden />

          <header className="pb-nav">
            <a className="pb-logo" href="#arriba"><Marca /> Seasons Ahead</a>
            <nav className="pb-nav-enlaces pb-mono" aria-label="Secciones">
              <a href="#sobre">SOBRE</a>
              <a href="#como">CÓMO FUNCIONA</a>
              <a href="#herramienta">LA HERRAMIENTA</a>
              <a href="#preguntas">PREGUNTAS</a>
            </nav>
            <SelectorIdioma />
            <a className="pb-cta chico" href="/app"><span className="pb-cta-icono" aria-hidden>↗</span><span className="pb-mono">EMPEZAR</span></a>
          </header>

          <div className="pb-heroe-texto" id="arriba">
            <h1>
              Tu campo, visto
              <br />
              desde el <em>espacio</em>
            </h1>
            <p className="pb-mono pb-chica">CON DATOS ABIERTOS DE</p>
            <div className="pb-marquee" aria-label={FUENTES.join(", ")}>
              <div className="pb-marquee-pista" aria-hidden data-no-traducir>
                {[...FUENTES, ...FUENTES].map((f, i) => <span key={i}>{f}</span>)}
              </div>
            </div>
            <p className="pb-bajada">
              Seasons Ahead junta los satélites de la NASA con los suelos del MGAP para comparar rotaciones sección por
              sección, con los números a la vista.
            </p>
            <div className="pb-heroe-acciones">
              <a className="pb-cta" href="/app"><span className="pb-cta-icono" aria-hidden>↗</span><span className="pb-mono">PLANIFICAR MI CAMPO</span></a>
              {/* para probar el flujo entero: abre la herramienta borrando el campo guardado en el navegador */}
              <a className="pb-cta prueba" href="/app?vacio" title="Abre la herramienta con el campo vacío, sin lo guardado antes">
                <span className="pb-cta-icono" aria-hidden>↺</span><span className="pb-mono">PRUEBA · EMPEZAR DE CERO</span>
              </a>
            </div>
          </div>

          <Clima />
        </div>
      </section>

      <Rasgos />

      <section className="pb-seccion" id="como">
        <span className="pb-insignia pb-mono">CÓMO FUNCIONA</span>
        <h2>De un contorno en el mapa a un plan de rotaciones.</h2>
        <ol className="pb-pasos">
          {PASOS.map((p) => (
            <li key={p.n}>
              <span className="pb-dato-grande" data-no-traducir>{p.n}</span>
              <h3>{p.t}</h3>
              <p>{p.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="pb-seccion" id="herramienta">
        <span className="pb-insignia pb-mono">LA HERRAMIENTA</span>
        <h2>Cada número sale de un dato que se puede revisar.</h2>
        <figure className="pb-pantalla">
          <div className="pb-pantalla-barra" aria-hidden>
            <span /><span /><span />
            <p className="pb-mono" data-no-traducir>field-shift / app</p>
          </div>
          <img
            src={idioma === "en" ? "/portada-b/comparar-en.webp" : "/portada-b/comparar-es.webp"}
            alt="La pantalla Comparar de Seasons Ahead con el campo de ejemplo: cuándo queda el suelo expuesto a la lluvia que erosiona y las rotaciones con su puntaje."
            loading="lazy"
            width={1600}
            height={1000}
          />
          <figcaption className="pb-mono">CAPTURA DE LA HERRAMIENTA · CAMPO DE EJEMPLO</figcaption>
        </figure>
      </section>

      <section className="pb-seccion" id="para-quien">
        <span className="pb-insignia pb-mono">PARA QUIÉN</span>
        <h2>Gratis, sin cuenta, para quien decide en el campo.</h2>
        <ul className="pb-planes">
          {PARA_QUIEN.map((q) => (
            <li key={q.quien} className={q.destacado ? "destacado" : ""}>
              <p className="pb-mono pb-plan-quien">{q.quien}</p>
              <p className="pb-plan-precio">Gratis</p>
              <p className="pb-plan-d">{q.d}</p>
              <ul>
                {q.items.map((it) => <li key={it}>{it}</li>)}
              </ul>
              <a className={`pb-cta ${q.destacado ? "" : "claro"}`} href="/app"><span className="pb-cta-icono" aria-hidden>↗</span><span className="pb-mono">EMPEZAR</span></a>
            </li>
          ))}
        </ul>
      </section>

      <section className="pb-seccion" id="desafio">
        <span className="pb-insignia pb-mono">EL DESAFÍO</span>
        <h2>Lo que pide la NASA, y cómo lo responde Seasons Ahead.</h2>
        <ul className="pb-citas">
          {DESAFIO.map((d) => (
            <li key={d.pide}>
              <blockquote>«{d.pide}»</blockquote>
              <p className="pb-mono pb-cita-fuente">DESAFÍO FIELD SHIFT · NASA SPACE APPS 2026 (RESUMIDO)</p>
              <p className="pb-cita-respuesta">{d.responde}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="pb-seccion angosta" id="preguntas">
        <span className="pb-insignia pb-mono">PREGUNTAS</span>
        <h2>Preguntas frecuentes</h2>
        <div className="pb-faq">
          {PREGUNTAS.map((q) => (
            <details key={q.p}>
              <summary>{q.p}<span className="pb-faq-mas" aria-hidden /></summary>
              <p>{q.r}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="pb-pie">
        <div className="pb-pie-arriba">
          <a className="pb-logo" href="#arriba"><Marca /> Seasons Ahead</a>
          <a className="pb-cta" href="/app"><span className="pb-cta-icono" aria-hidden>↗</span><span className="pb-mono">ABRIR LA HERRAMIENTA</span></a>
        </div>
        <p>Hecho para el NASA Space Apps Challenge 2026. Usa datos abiertos de la NASA y del MGAP.</p>
        <p>No es un producto oficial de la NASA ni está respaldado por ella.</p>
      </footer>

    </div>
  );
}
