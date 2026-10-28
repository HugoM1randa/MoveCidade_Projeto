# MoveCidade — ônibus de Matão/SP

App de ônibus urbano com duas partes:

- **App do passageiro** (PWA, mobile-first) em `http://localhost:5173/`: pontos perto de você com o tempo de chegada de cada linha, busca, detalhe da linha, mapa ao vivo, acessibilidade e histórico.
- **Painel do gestor** (desktop) em `http://localhost:5173/gestor`: indicadores, alertas da IA com Aceitar/Ignorar, resumo do turno (Hermes) e cadastro de linhas e pontos.

Os dados são **simulados**: cada ônibus é uma "central de telemetria" que anda pelas ruas reais de Matão e envia um pacote a cada 1,5–2 s (lógica do protótipo `script_ramon.py`).

## Como rodar

Requisitos: **Node 20+** e **Python 3.11+**.

```bash
npm run dev
```

Esse comando prepara tudo na primeira vez (cria o `.env`, o ambiente Python em `backend/.venv` e instala as dependências) e sobe a API e o front juntos. `Ctrl+C` encerra os dois.

- Passageiro: http://localhost:5173/
- Gestor: http://localhost:5173/gestor — usuário `gestor`, senha `movecidade` (definidos no `.env`)
- API: http://127.0.0.1:8000/docs

Funciona **sem internet**: o traçado real das ruas já vem salvo em `backend/movecidade/seed/tracados_cache.json`. Sem conexão, só os blocos do mapa (OpenStreetMap) não carregam; as linhas, os pontos e os ônibus aparecem normalmente.

Para usar a versão compilada (PWA com modo offline) servida pela própria API em http://127.0.0.1:8000:

```bash
npm start
```

## Testes

```bash
npm test
```

Roda o pytest do backend e o vitest do front. O pytest cobre: ETA até qualquer ponto, inclusive "o ônibus já passou"; previsão × chegada simulada (±20%); pontos próximos; validação de cor e contraste; contrato de telemetria (422); exigência de aceite nos alertas; e login do gestor.

```bash
npm run test:e2e
```

Roda o Playwright + axe-core no celular (Pixel 7) e no computador: move o pino pelo teclado, vê os pontos próximos com previsão e abre o detalhe da linha. Também passa pelo mapa, pela busca, pela acessibilidade e pelo histórico, e faz login no gestor e abre as quatro telas. O critério é **zero violações graves ou críticas**. Na primeira vez, instale o navegador com `npx --prefix frontend playwright install chromium`.

## Teste manual em 2 minutos

1. Abra http://localhost:5173/. O pino "Você está aqui" começa na Praça da Matriz, e a lista mostra os 3 pontos mais próximos com cada linha, o tempo ("3 min", "chegando"), "ao vivo", a lotação e se o ônibus é acessível.
2. Toque no mapa, arraste o pino **ou** dê Tab até o pino e use as setas (Shift anda 100 m). A lista muda e o leitor de tela anuncia o ponto mais próximo.
3. Toque numa linha da lista. No detalhe, veja o número grande, as abas Próximos/Horários/Trajeto e o botão "Ver no mapa". Toque em **Embarquei neste ônibus** e, depois, em **Desembarquei** no aviso do topo: a viagem vai para o **Histórico** (só no aparelho).
4. Em **Acessibilidade**, ligue "Ponto com rampa": a tela Início passa a mostrar só pontos com rampa. Teste também o alto contraste e o A / A+ / A++. Escolha um ônibus e toque em **Acionar botão de acessibilidade**.
5. Em http://localhost:5173/gestor, entre e veja o pedido de acessibilidade em **Alertas**. **Aceitar** executa a sugestão (por exemplo, coloca um ônibus reserva na linha) e registra a decisão com horário.
6. Em **Linhas**, edite a 102: mude a ordem dos pontos com ↑ ↓ e tente a cor `#FDE047`, que é reprovada no contraste. Em **Pontos**, crie um ponto clicando no mapa. As mudanças aparecem no app do passageiro em até 5 s.

## Estrutura

```
backend/                       Python + FastAPI (evolução do script_ramon.py)
  movecidade/
    config.py                  variáveis de ambiente (FATOR_TEMPO, login, OSRM…)
    seed/dados.py              pontos, linhas, cores e frota — FICTÍCIOS, fáceis de trocar
    seed/tracados_cache.json   traçado real das ruas (OSRM) para funcionar offline
    geo/                       haversine, reamostragem, projeção dos pontos, OSRM + fallback
    simulador/central.py       central de telemetria (uma thread por ônibus)
    eta/calculo.py             ETA de cada ônibus até QUALQUER ponto da rota
    ia/                        anomalias/alertas, indicadores (5 KPIs), resumo Hermes
    repositorio.py             estado em memória + SQLite (linhas, pontos, veículos, decisões)
    servicos.py                consultas do passageiro (pontos próximos, busca, detalhe)
    api/                       rotas: passageiro, gestor (login por cookie), IoT
  scripts/gerar_tracados.py    regenera o cache de traçados quando o seed mudar
  tests/                       pytest
frontend/                      React + Vite + TypeScript + Leaflet (PWA)
  src/passageiro/              Início, Busca, Linha, Mapa, Acessibilidade, Histórico
  src/gestor/                  Login, Painel, Alertas, Linhas, Pontos
  src/mapa/Mapa.tsx            mapa base, traçados com padrão, pontos, ônibus e o pino
  e2e/                         Playwright + axe-core
scripts/                       npm run dev / setup / api (sem dependências)
```

Os arquivos antigos da raiz (`movecidade.py`, `gestor.html`, `passageiro.html`, `mapa.js`, `leaflet.*`) são de uma versão anterior. Não são usados pelo app novo e não foram alterados.

## Endpoints principais

| Método | Caminho | Uso |
|---|---|---|
| GET | `/api/pontos/proximos?lat&lon&raio=800&limite=3` | pontos próximos com a previsão de cada linha (não grava a localização) |
| GET | `/api/pontos/{id}` | um ponto e as chegadas de cada linha |
| GET | `/api/linhas`, `/api/linhas/{id}/detalhe?ponto=` | linhas (com traçado e cor) e detalhe com próximos, horários e trajeto |
| GET | `/api/veiculos/mapa` | posição dos ônibus para o mapa (sem dados técnicos) |
| GET | `/api/busca?q&tipo` | busca por linha, ponto, bairro ou trajeto |
| POST | `/api/veiculos/{id}/acessibilidade` | botão de acessibilidade do passageiro |
| POST | `/api/iot/telemetria` | ingestão IoT (contrato do protótipo; 422 com mensagem clara) |
| GET | `/api/gestor/painel`, `/api/gestor/alertas` | indicadores, frota, alertas e resumo Hermes |
| POST | `/api/gestor/alertas/{id}/decisao` | `{"decisao": "aceitar" \| "ignorar"}` |
| POST/PUT/DELETE | `/api/linhas`, `/api/pontos`, `/api/veiculos` | cadastro (exige login do gestor) |

## Decisões

Estas decisões tratam de detalhes pequenos ou ambíguos. Em cada caso escolhi o mais simples que funciona.

- **Relógio do usuário.** A simulação roda `FATOR_TEMPO` vezes mais rápido (padrão **2**, configurável no `.env`). Todo tempo mostrado (ETA, horários, indicadores) é convertido para o relógio do usuário: quando a contagem chega a "agora", o ônibus está chegando ao ponto no mapa. As regras operacionais (tolerância de pontualidade, 2 min de comboiamento, 5 min de atraso) valem em tempo de operação; com `FATOR_TEMPO=1`, tudo coincide com o tempo real. O campo `eta_next_stop_s` da telemetria também já vem no relógio do usuário.
- **Linhas em volta fechada.** Cada linha sai do primeiro ponto, passa pelos demais na ordem e volta ao primeiro pelo traçado do OSRM, sem o "teletransporte" do fim para o início que existia no script. No terminal o ônibus faz uma pausa de regulação (60 s de operação). Os pontos são atendidos no sentido da ida.
- **ETA.** É a soma, trecho a trecho, de (distância ÷ velocidade média histórica do trecho) mais o tempo médio de parada em cada ponto intermediário. Se o ônibus já passou do ponto, a conta vai até o fim da volta, soma a regulação e segue até o ponto. A média histórica é exponencial, como no script, mas uma passagem fora do normal entra limitada a ±35% da média. Isso evita que um único congestionamento distorça a previsão dos próximos ônibus. Ao iniciar, o simulador "aquece" esse histórico em silêncio. No simulador, cerca de 90% das previsões de 2 min ou mais ficam dentro de ±20% (há um teste para isso).
- **Programado.** Um ônibus sem telemetria há mais de 10 s fica "sem sinal" e sai das previsões ao vivo. Se nenhum ônibus da linha tem sinal, a previsão vem da tabela programada (partidas a cada N min, das 05h à meia-noite) e aparece como "programado HH:MM". O simulador derruba o sinal de vez em quando (`SIM_FALHA_GPS=1`) para mostrar esse caso.
- **Pontos compartilhados.** São uma entidade própria. A posição de cada ponto em cada linha é calculada por projeção **monotônica** no traçado, o que evita projetar um ponto da ida no trecho de volta pela mesma rua.
- **Simulador → ingestão.** As centrais publicam pelo mesmo caminho de validação do `POST /api/iot/telemetria`, só que dentro do processo, para não depender da porta HTTP. O endpoint continua disponível para dispositivos externos.
- **Aceitar um alerta executa a sugestão.** Lotação crítica e atraso colocam um ônibus reserva na linha (no máximo 5 por linha). Comboiamento segura o ônibus de trás 1 min no próximo ponto. Pedido de acessibilidade avisa o motorista. "Ignorar" não executa nada. As duas decisões ficam gravadas no SQLite com horário.
- **Mapa.** As cores das linhas são definidas só no backend (tabela `linhas`). Os blocos do mapa são do OpenStreetMap, deixados em tons de cinza por CSS para as cores das linhas se destacarem. O serviço de mapa claro da CARTO passou a exigir chave de API. Os botões de zoom e os créditos ficam **abaixo** do mapa: por cima, eles cobriam marcadores (alvo de toque encoberto, WCAG 2.5.8).
- **Ônibus no mapa.** Os ônibus são clicáveis com mouse e toque, mas não entram na ordem do Tab: são alvos que se movem a cada 2 s e se sobrepõem. Pelo teclado e pelo leitor de tela, a mesma informação está em "Ver em lista" (mapa do passageiro) e na tabela da frota (gestor). Os pontos no mapa são focáveis e abrem com Enter.
- **Validação de cor.** O formato é `#RRGGBB`, com contraste ≥ 4,5:1 com branco e diferente das cores das outras linhas. Tons quase iguais (distância RGB < 30) também são reprovados. Linhas novas recebem a próxima cor livre da paleta.
- **Pontos desativados.** Continuam no traçado, mas os ônibus não param neles e eles não aparecem para o passageiro. Um ponto usado por alguma linha não pode ser excluído; nesse caso, é só desativá-lo.
- **LGPD.** A localização do pino é sempre simulada e nunca é gravada no servidor. O log de acesso do servidor omite a query string, onde estariam `lat` e `lon`. O histórico de viagens, os favoritos e as preferências ficam só no `localStorage` do aparelho e podem ser apagados.
- **Resumo Hermes.** É gerado por template a partir dos dados reais. Ponto de extensão opcional: com `HERMES_LLM_URL` no `.env`, as frases são enviadas a esse endpoint para reescrita; qualquer falha volta ao template.
- **Dados fictícios.** Os nomes e as posições dos 20 pontos são fictícios e aproximados, encaixados na rua mais próxima. Para usar dados reais, edite `backend/movecidade/seed/dados.py`, rode `python -m scripts.gerar_tracados` dentro de `backend/` e apague `backend/dados/movecidade.db`.
