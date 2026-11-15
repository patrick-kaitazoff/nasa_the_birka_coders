import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { crearSeccion, useApp } from "../store";
import { importarArchivo, poligonoDesdeTexto, rectangulo, unir, areaHa } from "./geo";
import type { Geo } from "../tipos";
import { enPalabras } from "../errores";
import { dondeEstoy } from "./ubicacion";
import { EstadoMarcado } from "./EstadoMarcado";
import { Cargando } from "../comun/Cargando";
import { BuscarLugar } from "./BuscarLugar";
import { useIdioma } from "../i18n/idioma";
import { traducir } from "../i18n/traducir";

type Metodo = "padron" | "dibujar" | "coordenadas" | "condado" | "lote";

// Tres botones con su nombre solo, y arriba el buscador. Un archivo (KML, KMZ, GeoJSON…) se puede
// igual soltar arriba de esta tarjeta.
const METODOS: Array<{ id: Metodo; titulo: string }> = [
  { id: "dibujar", titulo: "Marcar en el mapa" },
  { id: "padron", titulo: "Número de padrón" },
  { id: "coordenadas", titulo: "Coordenadas" },
];
// En EE. UU. no hay padrón
// público: el lote sale del Cropland Data Layer tocándolo en el mapa.
const METODOS_US: Array<{ id: Metodo; titulo: string }> = [
  { id: "dibujar", titulo: "Marcar en el mapa" },
  { id: "condado", titulo: "Estado y condado" },
  { id: "lote", titulo: "Tocar el lote" },
  { id: "coordenadas", titulo: "Coordenadas" },
];

type Lugar = { fips: string; nombre: string; sigla?: string; base?: string };

export function UbicarCampo({ compacto = false, alListo }: { compacto?: boolean; alListo?: (texto: string) => void }) {
  const [metodo, setMetodo] = useState<Metodo | null>(compacto ? null : "dibujar");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  // el aviso queda abajo de todo en la tarjeta del chat: en una pantalla baja aparecía fuera
  // de la vista y parecía que «Buscar» no había hecho nada
  const verError = useRef<HTMLDivElement>(null);
  useEffect(() => { if (error) verError.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [error]);
  const [buscandome, setBuscandome] = useState(false);
  const [cargando, setCargando] = useState(false);
  const { catalogo, setContorno, setSecciones, setPestania, modoMapa, setModoMapa, setVistaMovil, setCentrar, actualizarCampo, setExplorando,
    paisMapa, tocandoLote, setTocandoLote } = useApp();
  const [estados, setEstados] = useState<Lugar[]>([]);
  const [estadoFips, setEstadoFips] = useState("");
  const [condados, setCondados] = useState<Lugar[]>([]);
  const [condadoFips, setCondadoFips] = useState("");
  const [buscandoLote, setBuscandoLote] = useState(false);
  const metodos = paisMapa === "US" ? METODOS_US : METODOS;
  // las listas de estado y condado llevan data-no-traducir (los nombres quedan en inglés): su primera opción se traduce acá
  const idioma = useIdioma((i) => i.idioma);
  const tr = (t: string) => (idioma === "en" ? traducir(t) : t);
  const [depto, setDepto] = useState("DURAZNO");
  const [numero, setNumero] = useState("");
  const [modoCoord, setModoCoord] = useState<"rect" | "lista">("rect");
  const [c, setC] = useState({ lat: "", lon: "", ancho: "800", largo: "1200", angulo: "0" });
  const [lista, setLista] = useState("");
  const [sobre, setSobre] = useState(false);
  const formulario = useRef<HTMLDivElement>(null);

  // al elegir una forma, su formulario se trae a la vista (el del padrón quedaba abajo, fuera de la pantalla, y
  // no se notaba que el botón había hecho algo)
  useEffect(() => {
    if (!metodo || !compacto) return;
    const t = window.setTimeout(() => formulario.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 60);
    return () => window.clearTimeout(t);
  }, [metodo, compacto]);

  // clic en un departamento del mapa: queda elegido para buscar el padrón
  useEffect(() => {
    const sinTilde = (x: string) => x.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
    const alElegir = (e: Event) => {
      const n = sinTilde(String((e as CustomEvent).detail || ""));
      const d = (catalogo?.departamentos || []).find((x) => sinTilde(x) === n);
      if (d) setDepto(d);
    };
    window.addEventListener("fieldshift:departamento", alElegir);
    return () => window.removeEventListener("fieldshift:departamento", alElegir);
  }, [catalogo]);

  // EE. UU.: la lista de estados, y la de condados del estado elegido (tocar el mapa también los elige)
  useEffect(() => {
    if (paisMapa !== "US" || estados.length) return;
    api.estadosUs().then((fc) => setEstados(fc.features.map((f: any) => f.properties))).catch(() => setError("No pude traer los estados."));
  }, [paisMapa, estados.length]);
  useEffect(() => {
    setCondados([]);
    if (!estadoFips) return;
    api.condadosUs(estadoFips).then((fc) => setCondados(fc.features.map((f: any) => f.properties))).catch(() => setError("No pude traer los condados."));
  }, [estadoFips]);
  useEffect(() => {
    const alEstado = (e: Event) => { setEstadoFips(String((e as CustomEvent).detail || "")); setCondadoFips(""); };
    const alCondado = (e: Event) => {
      const fips = String((e as CustomEvent).detail || "");
      setEstadoFips(fips.slice(0, 2));
      setCondadoFips(fips);
    };
    window.addEventListener("fieldshift:estado-us", alEstado);
    window.addEventListener("fieldshift:condado-us", alCondado);
    return () => { window.removeEventListener("fieldshift:estado-us", alEstado); window.removeEventListener("fieldshift:condado-us", alCondado); };
  }, []);
  // el toque en el mapa con «Tocar el lote» activo: el contorno del Cropland Data Layer en ese punto
  useEffect(() => {
    const alTocar = async (e: Event) => {
      const { lat, lon } = (e as CustomEvent).detail as { lat: number; lon: number };
      setError(null);
      setBuscandoLote(true);
      try {
        const r = await api.loteCdl(lat, lon);
        setTocandoLote(false);
        const est = estados.find((x) => x.fips === estadoFips);
        const cond = condados.find((x) => x.fips === condadoFips);
        const seq = r.anios.map((a) => `${a.anio}: ${a.nombre_cdl}`).join(", ");
        listo(r.contorno, `Listo, tomé el lote del Cropland Data Layer del USDA (${Math.round(r.area_ha)} ha; ${seq}). Si agarró de más o de menos, corregilo en el mapa.`,
          { ubicacion: { lat, lon, pais: "US", origen: "cdl", ...(est ? { estado: est.nombre } : {}), ...(cond ? { condado: cond.nombre } : {}) } });
      } catch (err: any) {
        setError(enPalabras(err, "No pude sacar el lote"));
      } finally {
        setBuscandoLote(false);
      }
    };
    window.addEventListener("fieldshift:toque-lote", alTocar);
    return () => window.removeEventListener("fieldshift:toque-lote", alTocar);
  }, [estados, condados, estadoFips, condadoFips]); // eslint-disable-line react-hooks/exhaustive-deps

  // «Mi campo está en EE. UU.» (chat) o ?pais=us: con EE. UU. elegido, se abren las listas de estado y condado
  useEffect(() => {
    const alPedir = () => { setMetodo("condado"); setError(null); };
    window.addEventListener("fieldshift:elegir-condado", alPedir);
    return () => window.removeEventListener("fieldshift:elegir-condado", alPedir);
  }, []);
  // el país se cambia en la barra de arriba (SelectorPais) o lo fija la IP: al pasar a EE. UU. se abren las listas de
  // estado y condado (lo que hacía «Mi campo está en EE. UU.»); al volver a Uruguay, lo de siempre
  const paisAntes = useRef(paisMapa);
  useEffect(() => {
    const cambio = paisAntes.current !== paisMapa;
    paisAntes.current = paisMapa;
    if (cambio) {
      setError(null);
      setInfo(null);
      if (modoMapa !== "ver") setModoMapa("ver");
      setExplorando(false);
      setMetodo(paisMapa === "US" ? "condado" : compacto ? null : "dibujar");
      return;
    }
    if (paisMapa === "US" && (metodo === "padron" || metodo === null)) setMetodo("condado");
    if (paisMapa === "UY" && (metodo === "condado" || metodo === "lote")) setMetodo(compacto ? null : "dibujar");
  }, [paisMapa]); // eslint-disable-line react-hooks/exhaustive-deps

  // elegido el condado aparecen «Tocar el lote» y «Marcarlo a mano»: en una pantalla baja quedaban cortados abajo de
  // la tarjeta y no se notaba que había un paso más
  const botonesLote = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!condadoFips) return;
    const t = window.setTimeout(() => botonesLote.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }), 80);
    return () => window.clearTimeout(t);
  }, [condadoFips]);

  function irACondado(fips: string) {
    setCondadoFips(fips);
    if (!fips) return;
    setPestania("mapa");
    setVistaMovil("trabajo");
    setExplorando(true);
    window.dispatchEvent(new CustomEvent("fieldshift:ir-condado", { detail: fips }));
  }

  function irAEstado(fips: string) {
    setEstadoFips(fips);
    setCondadoFips("");
    // «Elegí el estado» (vacío) vuelve a mostrar todo el país
    if (!fips) { window.dispatchEvent(new CustomEvent("fieldshift:ir-estado", { detail: "" })); return; }
    setPestania("mapa");
    setVistaMovil("trabajo");
    setExplorando(true);
    window.dispatchEvent(new CustomEvent("fieldshift:ir-estado", { detail: fips }));
  }

  const listo = (g: Geo, texto: string, extra?: any) => {
    setContorno(g, extra);
    setModoMapa("ver");
    alListo?.(texto);
  };

  async function buscarPadron() {
    setError(null);
    const n = parseInt(numero, 10);
    if (!n) return setError("Escribí el número de padrón.");
    setCargando(true);
    try {
      const r = await api.padron(depto, n);
      actualizarCampo({ partes_suelo: r.secciones_por_suelo });
      // Se dice la superficie medida en el mapa, que es la que después muestra el panel y usa el plan.
      // Antes iba solo la que declara Catastro, y en el padrón 1200 de Durazno el mensaje decía 74 ha y el panel 63.
      // Si las dos difieren en más de 5 %, se aclara en una frase aparte.
      const medida = Math.round(areaHa(r.contorno));
      const declarada = r.area_ha_catastro ? Math.round(r.area_ha_catastro) : null;
      const aclara = declarada && Math.abs(declarada - medida) > medida * 0.05 ? ` Catastro declara ${declarada} ha; el plan usa la superficie del contorno.` : "";
      // en campos chicos, con un decimal como el panel (decía «9 ha» y el panel «8,6 ha»)
      const ha = areaHa(r.contorno);
      const medidaTxt = ha < 20 ? ha.toLocaleString("es-UY", { maximumFractionDigits: 1 }) : String(medida);
      listo(r.contorno, `Listo, cargué el padrón ${n} de ${titulo(depto)} (${medidaTxt} ha, ${r.secciones_por_suelo.length === 1 ? "una sola zona de suelo" : `${r.secciones_por_suelo.length} zonas de suelo distintas`} según el MGAP).${aclara}`,
        { ubicacion: { departamento: depto, padron: n, origen: "padron" } });
    } catch (e: any) {
      setError(String(e?.message || "").includes("No se encontró") ? `No se encontró el padrón ${n} en ${titulo(depto)}.` : enPalabras(e, "No pude traer el padrón"));
    } finally {
      setCargando(false);
    }
  }

  async function subir(f: File) {
    setError(null);
    setCargando(true);
    try {
      const r = await importarArchivo(f);
      if (!r.poligonos.length) throw new Error("El archivo no tiene polígonos (solo puntos o líneas abiertas).");
      const contorno = unir(r.poligonos.map((p) => p.geometria))!;
      let texto = `Listo, subí el contorno desde ${f.name} (${r.formato}, ${Math.round(areaHa(contorno))} ha).`;
      if (r.poligonos.length > 1) {
        setSecciones(r.poligonos.map((p, i) => crearSeccion(p.geometria, p.nombre || `Sección ${i + 1}`)));
        texto += ` Traía ${r.poligonos.length} polígonos y los usé como secciones.`;
      }
      listo(contorno, texto, { ubicacion: { origen: r.formato } });
    } catch (e: any) {
      setError(enPalabras(e));
    } finally {
      setCargando(false);
    }
  }

  function porCoordenadas() {
    setError(null);
    if (modoCoord === "rect") {
      const lat = parseFloat(c.lat.replace(",", ".")), lon = parseFloat(c.lon.replace(",", "."));
      const an = parseFloat(c.ancho), la = parseFloat(c.largo), ang = parseFloat(c.angulo) || 0;
      if ([lat, lon, an, la].some(Number.isNaN)) return setError("Completá latitud, longitud, ancho y largo.");
      if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return setError("Latitud o longitud fuera de rango (Uruguay: −30 a −35 y −53 a −58).");
      const g = rectangulo(lat, lon, an, la, ang);
      listo(g, `Listo, armé el campo con centro en ${lat.toFixed(4)}, ${lon.toFixed(4)} y ${an} × ${la} m (${Math.round(areaHa(g))} ha).`,
        { ubicacion: { origen: "medidas" } });
    } else {
      const g = poligonoDesdeTexto(lista);
      if (!g) return setError("Necesito al menos 3 esquinas, una por línea, como «-33.38, -56.52».");
      listo(g, `Listo, armé el campo con ${g.coordinates[0].length - 1} esquinas (${Math.round(areaHa(g))} ha).`, { ubicacion: { origen: "coordenadas" } });
    }
  }

  async function usarGPS() {
    setError(null);
    setInfo(null);
    setBuscandome(true);
    try {
      const d = await dondeEstoy();
      setExplorando(true);
      setCentrar(d.lat, d.lon, d.zoom);
      setC((x) => ({ ...x, lat: d.lat.toFixed(5), lon: d.lon.toFixed(5) }));
      setPestania("mapa");
      setVistaMovil("trabajo");
      if (d.aviso) setInfo(d.aviso);
    } catch (e: any) {
      setError(enPalabras(e));
    } finally {
      setBuscandome(false);
    }
  }

  return (
    <div
      className={`ubicar-campo ${sobre ? "sobre" : ""}`}
      style={{ display: "flex", flexDirection: "column", gap: 10 }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setSobre(true); } }}
      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setSobre(false); }}
      onDrop={(e) => { e.preventDefault(); setSobre(false); const f = e.dataTransfer.files[0]; if (f) void subir(f); }}
    >
      {sobre && <div className="ubicar-soltar">Soltá el archivo para cargar el contorno</div>}
      <BuscarLugar pais={paisMapa} />
      <div className={`metodos ${metodos.length === 4 ? "cuatro" : ""}`}>
        {metodos.map((m) => (
          <button key={m.id} className={`metodo ${metodo === m.id ? "on" : ""}`} onClick={() => {
            setMetodo(m.id);
            setError(null);
            setTocandoLote(m.id === "lote");
            if (m.id === "dibujar") {
              setPestania("mapa");
              setModoMapa("contorno");
              setVistaMovil("trabajo");
            }
            if (m.id === "lote") {
              setPestania("mapa");
              setModoMapa("ver");
              setVistaMovil("trabajo");
            }
          }}>
            <b>{m.titulo}</b>
          </button>
        ))}
      </div>

      {metodo === "padron" && (
        <div className="fila">
          <label className="campo" style={{ flex: "1 1 140px" }}>Departamento
            <select className="entrada" value={depto} onChange={(e) => setDepto(e.target.value)}>
              {(catalogo?.departamentos || ["DURAZNO"]).map((d) => <option key={d} value={d}>{titulo(d)}</option>)}
            </select>
          </label>
          <label className="campo" style={{ flex: "1 1 90px" }}>Padrón
            <input className="entrada" inputMode="numeric" value={numero} placeholder="ej. 1000" onChange={(e) => setNumero(e.target.value.replace(/\D/g, ""))}
              onKeyDown={(e) => e.key === "Enter" && buscarPadron()} />
          </label>
          <button className="btn primario" style={{ flex: "0 0 auto" }} onClick={buscarPadron} disabled={cargando}>
            {cargando ? <Cargando que="buscando" claro etiqueta="Buscando el padrón" /> : "Buscar"}
          </button>
        </div>
      )}

      {metodo === "condado" && (
        <div className="fila">
          <label className="campo" style={{ flex: "1 1 140px" }}>Estado de EE. UU.
            <select className="entrada" value={estadoFips} onChange={(e) => irAEstado(e.target.value)} data-no-traducir>
              <option value="">{tr("Elegí el estado")}</option>
              {estados.map((x) => <option key={x.fips} value={x.fips}>{x.nombre}</option>)}
            </select>
          </label>
          <label className="campo" style={{ flex: "1 1 140px" }}>Condado
            <select className="entrada" value={condadoFips} onChange={(e) => irACondado(e.target.value)} disabled={!condados.length} data-no-traducir>
              <option value="">{tr(estadoFips ? "Elegí el condado" : "Primero el estado")}</option>
              {condados.map((x) => <option key={x.fips} value={x.fips}>{x.nombre}</option>)}
            </select>
          </label>
        </div>
      )}
      {metodo === "condado" && condadoFips && (
        <div className="fila" ref={botonesLote}>
          <button className="btn primario" style={{ flex: "0 0 auto" }} onClick={() => { setMetodo("lote"); setTocandoLote(true); setPestania("mapa"); setVistaMovil("trabajo"); }}>Tocar el lote en el mapa</button>
          <button className="btn" style={{ flex: "0 0 auto" }} onClick={() => { setMetodo("dibujar"); setPestania("mapa"); setModoMapa("contorno"); setVistaMovil("trabajo"); }}>Marcarlo a mano</button>
        </div>
      )}

      {metodo === "lote" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="alerta azul">
            {buscandoLote ? <><Cargando que="buscando" etiqueta="Buscando el lote" /> Buscando el lote en el Cropland Data Layer…</>
              : tocandoLote ? "Acercate a tu campo y tocá adentro del lote. El contorno sale del Cropland Data Layer del USDA: los cuadrados de 30 m que tuvieron los mismos cultivos los últimos tres años."
                : "Listo. Para otro lote, tocá «Tocar el lote» de nuevo."}
          </div>
          {!estadoFips && <div className="nota">Si no sabés dónde está, elegí antes el estado y el condado.</div>}
        </div>
      )}

      {cargando && metodo !== "padron" && <div className="fila"><Cargando que="calculando" etiqueta="Leyendo el archivo" /> Leyendo el archivo…</div>}

      {metodo === "dibujar" && (modoMapa === "contorno" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="alerta azul">Tocá cada esquina del campo en el mapa y cerrá en el primer punto.</div>
          <EstadoMarcado que="campo" />
          <div className="fila">
            <button className="btn chico" style={{ flex: "0 0 auto" }} onClick={usarGPS} disabled={buscandome}>
              {buscandome ? <Cargando que="buscando" etiqueta="Buscando dónde estás" /> : <IconoUbicacion />} Ir a donde estoy
            </button>
            <button className="btn texto chico" style={{ flex: "0 0 auto" }} onClick={() => setModoMapa("ver")}>
              Pausar para mover el mapa
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="alerta azul">{paisMapa === "US"
            ? "Buscá arriba o tocá tu estado y tu condado en el mapa. Cuando veas tu campo, «Empezar a marcar»."
            : "Buscá arriba o tocá tu departamento en el mapa. Cuando veas tu campo, «Empezar a marcar»."}</div>
          <div className="fila">
            <button className="btn" style={{ flex: "0 0 auto" }} onClick={usarGPS} disabled={buscandome}>
              {buscandome ? <Cargando que="buscando" etiqueta="Buscando dónde estás" /> : <IconoUbicacion />} Ir a donde estoy
            </button>
            <button className="btn primario" style={{ flex: "0 0 auto" }} onClick={() => { setPestania("mapa"); setModoMapa("contorno"); setVistaMovil("trabajo"); }}>Empezar a marcar</button>
          </div>
        </div>
      ))}

      {metodo === "coordenadas" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="chips">
            <button className={`chip ${modoCoord === "rect" ? "on" : ""}`} onClick={() => setModoCoord("rect")}>Centro y medidas</button>
            <button className={`chip ${modoCoord === "lista" ? "on" : ""}`} onClick={() => setModoCoord("lista")}>Lista de esquinas</button>
          </div>
          {modoCoord === "rect" ? (
            <>
              <div className="grilla2">
                <label className="campo">Latitud<input className="entrada" value={c.lat} placeholder="-33.38" onChange={(e) => setC({ ...c, lat: e.target.value })} /></label>
                <label className="campo">Longitud<input className="entrada" value={c.lon} placeholder="-56.52" onChange={(e) => setC({ ...c, lon: e.target.value })} /></label>
                <label className="campo">Ancho (m, este-oeste)<input className="entrada" value={c.ancho} onChange={(e) => setC({ ...c, ancho: e.target.value })} /></label>
                <label className="campo">Largo (m, norte-sur)<input className="entrada" value={c.largo} onChange={(e) => setC({ ...c, largo: e.target.value })} /></label>
              </div>
              <label className="campo">Giro respecto del norte: {c.angulo}°
                <input type="range" min={-90} max={90} value={c.angulo} onChange={(e) => setC({ ...c, angulo: e.target.value })} style={{ accentColor: "var(--verde-700)" }} />
              </label>
            </>
          ) : (
            <textarea className="entrada" rows={4} value={lista} onChange={(e) => setLista(e.target.value)} placeholder={"-33.3712, -56.5301\n-33.3755, -56.5104\n-33.3901, -56.5150\n-33.3860, -56.5352"} />
          )}
          <div className="fila">
            <button className="btn texto chico" style={{ flex: "0 0 auto" }} onClick={usarGPS} disabled={buscandome}>Usar dónde estoy ahora</button>
            <button className="btn primario" style={{ flex: "0 0 auto", marginLeft: "auto" }} onClick={porCoordenadas}>Armar el campo</button>
          </div>
        </div>
      )}

      {info && <div className="alerta azul">{info}</div>}
      {error && <div className="alerta ambar" role="alert" ref={verError}>{error}</div>}
      <div ref={formulario} aria-hidden style={{ height: 1, marginTop: -11 }} />
    </div>
  );
}

export function IconoUbicacion() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2.2" fill="currentColor" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
    </svg>
  );
}

/** Los departamentos llegan en mayúsculas y sin tildes («TREINTA Y TRES», «PAYSANDU»); en pantalla, bien escritos. */
const CON_TILDE: Record<string, string> = { "Paysandu": "Paysandú", "Rio Negro": "Río Negro", "San Jose": "San José", "Tacuarembo": "Tacuarembó" };
export function titulo(s: string) {
  const t = s.toLowerCase().replace(/(^|\s)\S/g, (l) => l.toUpperCase()).replace(/ Y /g, " y ");
  return CON_TILDE[t] || t;
}
