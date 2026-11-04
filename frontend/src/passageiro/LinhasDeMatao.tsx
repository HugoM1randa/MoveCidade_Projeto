import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useCatalogo } from '../estado/Catalogo';
import type { Linha } from '../tipos';

/** As linhas de Matão (Azul, Verde, Vermelha) com os dois itinerários de cada uma. */
export function LinhasDeMatao() {
  const { linhas } = useCatalogo();
  const grupos = new Map<string, Linha[]>();
  for (const l of linhas) grupos.set(l.cor_nome, [...(grupos.get(l.cor_nome) ?? []), l]);
  if (!grupos.size) return null;
  return (
    <section aria-labelledby="titulo-linhas" className="secao linhas-matao">
      <h2 id="titulo-linhas">Linhas de Matão</h2>
      <ul className="grade-linhas">
        {[...grupos.values()].map((itinerarios) => {
          const base = itinerarios[0];
          return (
            <li key={base.cor_nome} className="cartao-linha" style={{ ['--cor-linha' as string]: base.cor }}>
              <h3><span className="faixa-cor" aria-hidden="true" /> Linha {base.numero}</h3>
              <ul>
                {itinerarios.map((l) => (
                  <li key={l.id}>
                    <Link to={`/linha/${l.id}`} className="itinerario">
                      <span>Centro ↔ {l.destino}<span className="sr-only">, linha {base.numero}</span></span>
                      <ChevronRight aria-hidden="true" size={20} />
                    </Link>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
      <p className="nota">
        Itinerários e horários oficiais da Viação Paraty. A posição dos ônibus no mapa é simulada enquanto a
        empresa não libera o GPS da frota.
      </p>
    </section>
  );
}
