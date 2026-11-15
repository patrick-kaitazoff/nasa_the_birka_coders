/** Qué quiere decir cada término de la pestaña Datos, y en qué se diferencia el dato del satélite del
 * que mide una estación en el campo. Lo pide el desafío ("explicar términos científicos" y "cómo difieren
 * las observaciones satelitales de las mediciones en tierra"). Textos cortos, sin fórmulas: el detalle
 * técnico queda en el README. */

const TERMINOS: Array<{ t: string; d: string }> = [
  {
    t: "Evapotranspiración (ET)",
    d: "El agua que se va del campo al aire: la que se evapora del suelo y la que transpiran las plantas. La app calcula la de un pasto de referencia (ET0, método FAO-56) con el clima de la NASA y la ajusta a cada cultivo y a cada etapa: un maíz en floración pide más agua que recién nacido.",
  },
  {
    t: "Balance de agua",
    d: "Lo que entra con la lluvia menos lo que se va por evapotranspiración, día a día. El suelo funciona como un tanque: cuando la lluvia no alcanza, el cultivo vive de lo que quedó guardado; cuando el tanque se vacía en el momento crítico (la floración), se pierde rinde.",
  },
  {
    t: "Agua útil",
    d: "Los milímetros de agua que el suelo puede guardar y la planta puede sacar. Depende de la textura y la profundidad: un suelo profundo y arcilloso guarda mucho más que uno superficial y arenoso.",
  },
  {
    t: "NDVI (índice de verdor)",
    d: "Un número de 0 a 1 que el satélite calcula con la luz roja e infrarroja que refleja el campo. Las hojas vivas reflejan mucho infrarrojo: cerca de 1 es un cultivo cerrado y verde; valores bajos son suelo desnudo, rastrojo o pasto seco. Así se ve desde el espacio cuándo el campo estuvo descubierto.",
  },
  {
    t: "Anomalía",
    d: "Cuánto se aparta algo de lo normal para esa zona y esa época del año. «20 % menos de lluvia que lo normal» compara estos meses con el promedio de los mismos meses de los últimos 35 años, no con el año anterior.",
  },
  {
    t: "Riesgo de helada",
    d: "Cuántos años de cada 10 la temperatura bajó a 2 °C o menos justo cuando el cultivo es sensible. La NASA da la temperatura del aire a 2 m de altura; en los bajos y a ras del cultivo suele hacer más frío, así que en esos lugares el riesgo real es mayor.",
  },
  {
    t: "«Años de cada 10»",
    d: "Es lo que pasó en los últimos 35 años, no un pronóstico. «3 de cada 10» quiere decir que en esos años pasó en 3 de cada 10 temporadas; el año que viene puede pasar o no.",
  },
  {
    t: "Erosividad (R) y tolerancia (T)",
    d: "R mide cuánta fuerza tienen las lluvias de la zona para arrastrar suelo: pesa más un aguacero fuerte que muchas lloviznas. T es cuánto suelo por hectárea puede perder un campo por año sin degradarse. Son los dos números que usa el MGAP en los Planes de Uso: una rotación que pierde más que T no cumple.",
  },
];

const FUENTES: Array<{ t: string; d: string }> = [
  {
    t: "Clima de la NASA (POWER)",
    d: "Combina satélites y modelos en una grilla de unos 50 km de lado. Tiene la ventaja de que hay datos de todos los días desde 1981 en cualquier lugar, sin huecos; la desventaja es que da el promedio de toda esa zona: no ve los bajos, las lomas ni una tormenta que cayó en un solo campo.",
  },
  {
    t: "Satélite sobre el campo (MODIS y HLS)",
    d: "Miran el campo desde arriba. MODIS ve cuadros de 250 m (6,25 ha) y la app usa su mejor imagen de cada 16 días; HLS ve cuadros de 30 m cada pocos días, pero las nubes tapan algunos. Dicen cómo estuvo la vegetación, no cuánto llovió.",
  },
  {
    t: "Tu estación meteorológica",
    d: "Mide exactamente en tu campo, pero solo en ese punto y solo desde que la tenés, y a veces con días que faltan o un sensor que se corrió.",
  },
  {
    t: "Temperatura del potrero (ECOSTRESS 70 m)",
    d: "Mide la temperatura de la superficie a 70 m desde la Estación Espacial. Ve diferencias adentro del potrero, pero la hora de pasada cambia y las nubes dejan pocas pasadas limpias al año: sirve para mirar días puntuales, no para seguir el campo día a día.",
  },
  {
    t: "Aptitud de cultivos (FAO GAEZ v4)",
    d: "Modelo agroecológico global de la FAO y el IIASA (celdas de ~9 km) que dice qué tan apto es el clima y el suelo de la zona para cada cultivo en secano. Es una segunda opinión, independiente de la app, para los cultivos de cada rotación.",
  },
  {
    t: "Por qué combinarlos",
    d: "La estación muestra cuánto se aparta tu campo del promedio de la zona (por ejemplo, si llueve un poco más o hiela más seguido), y la NASA aporta los 35 años y todo el campo. Si cargás tu estación, la app compara las dos y lo dice en «Tu estación contra NASA POWER».",
  },
];

/** id del término en la página, para que un término nombrado en otro bloque abra su explicación (Termino.tsx) */
export function idTermino(t: string): string {
  return "glos-" + t.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function Lista({ items }: { items: Array<{ t: string; d: string }> }) {
  return (
    <div className="cinco">
      {items.map((x) => (
        <details key={x.t} id={idTermino(x.t)}>
          <summary>{x.t}</summary>
          <p style={{ margin: "0 0 10px", fontSize: 12.8, color: "var(--texto-2)", lineHeight: 1.5 }}>{x.d}</p>
        </details>
      ))}
    </div>
  );
}

export function Glosario() {
  return (
    <div className="grilla-cajas">
      <div className="caja">
        <h3>Qué quiere decir cada término</h3>
        <p className="bajada">Tocá un término para ver la explicación.</p>
        <Lista items={TERMINOS} />
      </div>
      <div className="caja">
        <h3>Satélite, modelo o estación: qué mide cada uno</h3>
        <p className="bajada">Ningún dato es perfecto: cada fuente ve una parte distinta.</p>
        <Lista items={FUENTES} />
      </div>
    </div>
  );
}
