/*
 * MoveCidade - camada de mapa compartilhada pelos dois apps.
 *
 * Usa Mapbox GL JS quando o token e a biblioteca estao disponiveis; caso
 * contrario cai para o Leaflet local (vendor/leaflet.js), que nao depende de
 * CDN. A API publica e a mesma nos dois casos, de modo que as paginas nao se
 * preocupam com o provedor.
 *
 *   const mapa = MapaMC.criar("elemento", { token, centro: [lat, lon], zoom: 14 });
 *   mapa.pronto.then(() => { mapa.desenharLinhas(linhas); mapa.desenharVeiculos(v); });
 */
(function (global) {
  "use strict";

  const ESTILO_MAPBOX = "mapbox://styles/mapbox/dark-v11";
  const TILES_LEAFLET = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

  function escapar(texto) {
    return String(texto == null ? "" : texto).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // "LINHA-101" -> "101": o marcador comporta so o numero da linha
  function rotuloLinha(routeId) {
    const numero = String(routeId || "").replace(/\D/g, "");
    return numero ? numero.slice(-3) : String(routeId || "").slice(0, 3);
  }

  function mapboxDisponivel(token) {
    return typeof global.mapboxgl !== "undefined" && token && !token.startsWith("__");
  }

  // ---------------------------------------------------------------- Mapbox
  function criarMapbox(elemento, opcoes) {
    global.mapboxgl.accessToken = opcoes.token;
    const mapa = new global.mapboxgl.Map({
      container: elemento,
      style: ESTILO_MAPBOX,
      center: [opcoes.centro[1], opcoes.centro[0]],
      zoom: opcoes.zoom || 14,
      attributionControl: false,
    });
    const marcadores = [];
    const pronto = new Promise((resolver) => mapa.on("load", () => resolver()));
    let aoClicarPonto = null;

    return {
      tipo: "mapbox",
      pronto,
      desenharLinhas(linhas) {
        pronto.then(() => {
          linhas.forEach((linha) => {
            const id = "linha-" + linha.id;
            const coords = linha.rota.map(([la, lo]) => [lo, la]);
            if (mapa.getSource(id)) {
              mapa.getSource(id).setData({ type: "Feature", geometry: { type: "LineString", coordinates: coords } });
              return;
            }
            mapa.addSource(id, { type: "geojson", data: { type: "Feature", geometry: { type: "LineString", coordinates: coords } } });
            mapa.addLayer({ id: id + "-halo", type: "line", source: id,
              paint: { "line-color": "#0b1220", "line-width": 7, "line-opacity": 0.6 } });
            mapa.addLayer({ id, type: "line", source: id,
              paint: { "line-color": linha.cor, "line-width": 4, "line-opacity": 0.95 } });
          });
        });
      },
      desenharPontos(pontos, selecionadoId) {
        pronto.then(() => {
          marcadores.splice(0).forEach((m) => m.remove());
          pontos.forEach((p) => {
            const el = document.createElement("div");
            el.className = "mc-pino" + (p.id === selecionadoId ? " sel" : "");
            el.title = p.nome;
            el.addEventListener("click", (ev) => { ev.stopPropagation(); aoClicarPonto && aoClicarPonto(p.id); });
            marcadores.push(new global.mapboxgl.Marker({ element: el }).setLngLat([p.longitude, p.latitude]).addTo(mapa));
          });
        });
      },
      desenharVeiculos(veiculos, aoClicar) {
        pronto.then(() => {
          marcadores.splice(0).forEach((m) => m.remove());
          veiculos.forEach((v) => {
            const el = document.createElement("div");
            el.className = "mc-veiculo" + (v.solicitacao_ativa ? " pedido" : "");
            el.style.background = v.cor;
            el.textContent = rotuloLinha(v.route_id);
            el.title = v.vehicle_id_publico;
            el.addEventListener("click", (ev) => { ev.stopPropagation(); aoClicar && aoClicar(v.vehicle_id_publico); });
            marcadores.push(new global.mapboxgl.Marker({ element: el }).setLngLat([v.longitude, v.latitude]).addTo(mapa));
          });
        });
      },
      aoClicarPonto(cb) { aoClicarPonto = cb; },
      centralizar(lat, lon, zoom) { mapa.flyTo({ center: [lon, lat], zoom: zoom || 15, essential: true }); },
      redimensionar() { mapa.resize(); },
      remover() { mapa.remove(); },
      mapa,
    };
  }

  // ---------------------------------------------------------------- Leaflet
  function criarLeaflet(elemento, opcoes) {
    if (!global.L) throw new Error("Leaflet indisponivel");
    const mapa = global.L.map(elemento, { zoomControl: false, attributionControl: false })
      .setView(opcoes.centro, opcoes.zoom || 14);
    global.L.tileLayer(TILES_LEAFLET, { subdomains: "abcd", maxZoom: 19 }).addTo(mapa);
    const camadaLinhas = global.L.layerGroup().addTo(mapa);
    const camadaPontos = global.L.layerGroup().addTo(mapa);
    const camadaVeiculos = global.L.layerGroup().addTo(mapa);
    let aoClicarPonto = null;
    return {
      tipo: "leaflet",
      pronto: Promise.resolve(),
      desenharLinhas(linhas) {
        camadaLinhas.clearLayers();
        linhas.forEach((linha) => {
          global.L.polyline(linha.rota, { color: "#0b1220", weight: 7, opacity: 0.6 }).addTo(camadaLinhas);
          global.L.polyline(linha.rota, { color: linha.cor, weight: 4, opacity: 0.95 }).addTo(camadaLinhas);
        });
      },
      desenharPontos(pontos, selecionadoId) {
        camadaPontos.clearLayers();
        pontos.forEach((p) => {
          const sel = p.id === selecionadoId;
          global.L.circleMarker([p.latitude, p.longitude], {
            radius: sel ? 9 : 6, color: "#f1f5f9", weight: sel ? 3 : 2,
            fillColor: sel ? "#38bdf8" : "#0b1220", fillOpacity: 1,
          }).bindTooltip(escapar(p.nome)).on("click", () => aoClicarPonto && aoClicarPonto(p.id))
            .addTo(camadaPontos);
        });
      },
      desenharVeiculos(veiculos, aoClicar) {
        camadaVeiculos.clearLayers();
        veiculos.forEach((v) => {
          const icone = global.L.divIcon({
            className: "mc-veiculo-leaflet" + (v.solicitacao_ativa ? " pedido" : ""),
            html: `<div class="mc-veiculo" style="background:${escapar(v.cor)}">${escapar(rotuloLinha(v.route_id))}</div>`,
            iconSize: [34, 34], iconAnchor: [17, 17],
          });
          global.L.marker([v.latitude, v.longitude], { icon: icone, title: v.vehicle_id_publico })
            .on("click", () => aoClicar && aoClicar(v.vehicle_id_publico))
            .addTo(camadaVeiculos);
        });
      },
      aoClicarPonto(cb) { aoClicarPonto = cb; },
      centralizar(lat, lon, zoom) { mapa.setView([lat, lon], zoom || 15); },
      redimensionar() { mapa.invalidateSize(); },
      remover() { mapa.remove(); },
    };
  }

  /**
   * Cria o mapa no elemento. Se o Mapbox nao carregar a tempo (sem internet,
   * token recusado) ou falhar antes do primeiro render, troca para o Leaflet
   * local sem interromper a interface; as chamadas de desenho sao repetidas
   * pelas paginas a cada atualizacao, entao nada se perde.
   */
  function criar(elementoOuId, opcoes) {
    const elemento = typeof elementoOuId === "string" ? document.getElementById(elementoOuId) : elementoOuId;
    const cfg = Object.assign({ centro: [-21.6033, -48.3652], zoom: 14, token: "", timeoutMs: 8000 }, opcoes || {});
    let impl = null;
    let carregou = false;
    let aoClicarPontoCb = null;
    let aoClicarVeiculoCb = null;
    let ultimo = {};

    function trocarParaLeaflet() {
      if (impl && impl.tipo === "leaflet") return;
      if (impl && impl.remover) impl.remover();
      elemento.innerHTML = "";
      impl = criarLeaflet(elemento, cfg);
      impl.aoClicarPonto(aoClicarPontoCb);
      redesenhar();
    }

    function redesenhar() {
      if (ultimo.linhas) impl.desenharLinhas(ultimo.linhas);
      if (ultimo.pontos) impl.desenharPontos(ultimo.pontos, ultimo.selecionado);
      if (ultimo.veiculos) impl.desenharVeiculos(ultimo.veiculos, aoClicarVeiculoCb);
    }

    let resolverPronto;
    const pronto = new Promise((r) => { resolverPronto = r; });

    if (mapboxDisponivel(cfg.token)) {
      try {
        impl = criarMapbox(elemento, cfg);
        impl.pronto.then(() => { carregou = true; resolverPronto(api); });
        impl.mapa && impl.mapa.on("error", () => { if (!carregou) trocarParaLeaflet(); });
        setTimeout(() => { if (!carregou) trocarParaLeaflet(); }, cfg.timeoutMs);
      } catch (erro) {
        console.warn("Mapbox indisponivel, usando Leaflet:", erro);
        trocarParaLeaflet();
      }
    } else {
      impl = criarLeaflet(elemento, cfg);
      carregou = true;
      setTimeout(() => resolverPronto(api), 0);
    }

    const api = {
      // so declara "mapbox" depois do primeiro render; ate la, "carregando"
      get tipo() { return !impl ? "carregando" : (impl.tipo === "mapbox" && !carregou ? "carregando" : impl.tipo); },
      pronto,
      desenharLinhas(linhas) { ultimo.linhas = linhas; impl && impl.desenharLinhas(linhas); },
      desenharPontos(pontos, selecionado) {
        ultimo.pontos = pontos; ultimo.selecionado = selecionado;
        impl && impl.desenharPontos(pontos, selecionado);
      },
      desenharVeiculos(veiculos, aoClicar) {
        ultimo.veiculos = veiculos; aoClicarVeiculoCb = aoClicar || aoClicarVeiculoCb;
        impl && impl.desenharVeiculos(veiculos, aoClicarVeiculoCb);
      },
      aoClicarPonto(cb) { aoClicarPontoCb = cb; impl && impl.aoClicarPonto(cb); },
      centralizar(lat, lon, zoom) { impl && impl.centralizar(lat, lon, zoom); },
      redimensionar() { impl && impl.redimensionar(); },
    };
    return api;
  }

  global.MapaMC = { criar, escapar };
})(window);
