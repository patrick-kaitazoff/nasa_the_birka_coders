/** Relieve del campo (NASA SRTM, 30 m): pendiente y cuánta superficie de cada sección supera la tolerancia
 * de erosión, hoy y con el plan, calculado cuadrado por cuadrado (analisis/relieve.py del backend). */
import { useRelieve } from "../relieve/useRelieve";

const f = (n: number | undefined, d = 1) => (n == null ? "—" : n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d }));

export function RelieveDatos() {
  const { relieve, error, cargando } = useRelieve();
  if (error) return <div className="caja"><h3>Relieve y zonas que se lavan</h3><div className="alerta ambar">{error}</div></div>;
  if (!relieve) return cargando ? <div className="caja"><h3>Relieve y zonas que se lavan</h3><p className="fuente">Trayendo el relieve de la NASA (SRTM)…</p></div> : null;
  const peor = [...relieve.secciones].filter((s) => s.erosion_plan).sort((a, b) => (b.erosion_plan!.ha_supera_t - a.erosion_plan!.ha_supera_t))[0];
  return (
    <div className="caja">
      <h3>Relieve y zonas que se lavan</h3>
      <p className="bajada">Con el relieve del satélite SRTM de la NASA (cuadrados de 30 m) se calcula la pendiente de cada parte del campo y, con la misma ecuación del Plan de Uso, la erosión de cada cuadrado. Así se ven las zonas que se lavan dentro de una sección, que el promedio esconde. En el visor 3D se ven sobre el terreno.</p>
      <table className="tabla-mini">
        <thead><tr><th>Sección</th><th>Pendiente media</th><th>Con más de 4 %</th><th>Superan la tolerancia hoy</th><th>Con el plan</th></tr></thead>
        <tbody>
          {relieve.secciones.map((s) => (
            <tr key={s.id}>
              <td>{s.nombre}</td>
              <td>{f(s.pendiente_media)} %</td>
              <td>{s.pct_mas_de_4} %</td>
              <td>{s.erosion_actual ? <><b className={s.erosion_actual.pct_supera_t > 20 ? "cambio-sube" : ""}>{`${f(s.erosion_actual.ha_supera_t, 0)} ha`}</b> ({s.erosion_actual.pct_supera_t} %)</> : "—"}</td>
              <td>{s.erosion_plan ? <><b>{`${f(s.erosion_plan.ha_supera_t, 0)} ha`}</b> ({s.erosion_plan.pct_supera_t} %)</> : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {peor && peor.erosion_plan!.ha_supera_t > 1 && (
        <div className="alerta azul" style={{ marginTop: 10 }}>
          {/* una sola frase: en pedazos, el traductor no la reconocía */}
          {`${peor.nombre}: aun con el plan, ${f(peor.erosion_plan!.ha_supera_t, 0)} ha (${peor.erosion_plan!.pct_supera_t} %) siguen por encima de la tolerancia: son las partes más empinadas. Ahí conviene mirar en el campo si hace falta una medida más (siembra en contorno, terrazas o dejar esa franja empastada).`}
        </div>
      )}
      <p className="bajada" style={{ marginTop: 12 }}>
        Por acá baja el agua cuando llueve fuerte: conviene que esté siempre cubierto (pastura o vía de agua empastada) y no arar a favor de la pendiente.
      </p>
      <details className="tecnico">
        <summary>Cómo se calcula y sus límites</summary>
        <p style={{ margin: "0 0 6px", fontSize: 13, color: "var(--texto-2)" }}>{relieve.metodo}</p>
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--texto-2)" }}>{relieve.limites.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="fuente" style={{ marginTop: 6 }}>{relieve.fuente} · altura de {relieve.elev_min} a {relieve.elev_max} m</p>
      </details>
    </div>
  );
}
