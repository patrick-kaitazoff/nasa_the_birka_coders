/**
 * Presentación corta arriba del chat, mientras el campo no está ubicado.
 *
 * Por qué así: decir qué hace, cómo y cuánto lleva,
 * sin tutorial largo (NN/G, "New Users Need Support with Generative-AI Tools"); saludar, poner
 * expectativas y dejar el control a la persona (Google, Conversation Design: Greetings); avatar
 * ilustrado, nunca la foto de una persona, y aclarar que es un asistente automático. En el agro
 * pesan la confianza en las fuentes y que el asesor humano siga en el medio (Rose et al. 2016,
 * Agricultural Systems 149; estudios de 2026 sobre "aversión al algoritmo" en productores).
 */
export function Presentacion() {
  return (
    <section className="presentacion" aria-label="Qué vamos a hacer">
      <div className="presentacion-cabeza">
        <AvatarBrote size={56} />
        <div>
          <h2>Planifiquemos qué sembrar en cada parte de tu campo</h2>
          <p>Vos conocés tu campo mejor que nadie. Yo traigo el clima de la NASA, el suelo del MGAP y lo que vio el satélite, y lo ponemos al lado de lo que ya sabés.</p>
        </div>
      </div>
      <ol className="presentacion-pasos">
        <li>
          <b>Ubicamos el campo</b>
          <span>En el mapa, con el número de padrón o yendo a donde estás. Si tiene lotes o potreros, los marcás.</span>
        </li>
        <li>
          <b>Me contás cómo lo trabajás</b>
          <span>Qué sembrás, qué te importa más (el ingreso, cuidar el suelo, el agua) y qué te anduvo.</span>
        </li>
        <li>
          <b>Comparamos opciones</b>
          <span>Con 35 años de clima de la NASA, el suelo del MGAP y lo que vio el satélite. Te queda un plan para revisar con tu agrónomo.</span>
        </li>
      </ol>
      <p className="presentacion-pie">Son unos 10 minutos, sin crear una cuenta, y lo que cargás queda guardado en este navegador. Es un asistente automático con datos oficiales, y la decisión final es tuya.</p>
    </section>
  );
}

/** Avatar del asistente: un brote con cara. Dibujo propio, hecho para Seasons Ahead. */
export function AvatarBrote({ size = 40 }: { size?: number }) {
  return (
    <svg className="avatar-brote" width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Asistente de Seasons Ahead">
      <circle cx="32" cy="32" r="31" fill="#E8F3EC" stroke="#2b6a4f" strokeWidth="2" />
      {/* surcos */}
      <path d="M8 50 Q32 42 56 50 L56 54 Q32 63 8 54 Z" fill="#8A6A3B" />
      <path d="M14 52 Q32 47 50 52" stroke="#C9A227" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      {/* tallo y hojas */}
      <path d="M32 47 L32 33" stroke="#2b6a4f" strokeWidth="3" strokeLinecap="round" />
      <g className="avatar-hojas">
        <path d="M32 41 C24 41 18 36 17 29 C25 28 31 33 32 41 Z" fill="#4f9a6f" />
        <path d="M32 38 C40 38 47 33 48 25 C39 24 33 30 32 38 Z" fill="#6fb98a" />
      </g>
      {/* cabeza (un sol chico) */}
      <circle cx="32" cy="21" r="10" fill="#F2C80F" />
      <circle cx="28.5" cy="20" r="1.5" fill="#1F4D3A" />
      <circle cx="35.5" cy="20" r="1.5" fill="#1F4D3A" />
      <path d="M28 24 Q32 27.5 36 24" stroke="#1F4D3A" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    </svg>
  );
}
