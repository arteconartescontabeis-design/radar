"use strict";
/* ====================================================================
   RADAR ARTECON — aba Respostas (v0.35.0) — Módulo Respostas Automáticas
   O Radar responde sozinho, no Instagram e no Facebook, aos comentários que trazem a palavra-chave de uma publicação escolhida
   (ex.: "Comente QUERO e receba o material"): uma resposta pública ao comentário e uma mensagem privada com o link do material.
   O administrador cadastra os gatilhos; a equipe toda acompanha o registro. Quem decide se responde é o banco (gatilho ativo,
   palavra-chave sem diferenciar maiúsculas/acentos/pontuação, nunca a própria conta, nunca duas vezes o mesmo comentário, limite
   por hora com fila e o interruptor geral "Pausar todas"). Quem recebe os comentários da Meta é a função radar-meta-webhook.
   AGUARDANDO A META: os avisos de comentário só chegam depois que a Meta aprovar o acesso avançado do aplicativo (o pedido tem
   passo a passo no LEIAME). Até lá dá para cadastrar os gatilhos e testar a conexão.
   Carregado ANTES do script principal (index.html): aqui só há declarações e o objeto RESPOSTAS ({acoes, forms, navegacao}), que
   o script principal junta aos dele. Nada roda no carregamento: as funções usam os globais do script principal (h, rpc, pedir,
   recado, desenhar, ehAdmin, ErroApi, $) só quando são chamadas. Quem confere quem pode o quê é o banco.
   ==================================================================== */
const RESPOSTAS_VERSAO = "0.47.0";    // igual à VERSAO do index.html; diferente, um dos dois ficou guardado no navegador (Ctrl+F5)

// o que só a tela guarda: o formulário aberto (null, "novo" ou o id do gatilho) e os filtros do registro
let RESP_E = {form: null, f_gatilho: "", f_situacao: ""};

const RESP_SITUACOES = {enviado: ["respondido", "ok"], pendente: ["na fila", "neutro"], erro: ["erro", "erro"], descartado: ["descartado", "neutro"]};
const RESP_REDES = {instagram: "Instagram", facebook: "Facebook"};

const respQuando = v => { const d = new Date(v || ""); return !v || isNaN(d) ? "—"
  : d.toLocaleString("pt-BR", {timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}).replace(",", " às"); };
// o banco ainda não tem o módulo (setup de antes desta versão): a tela diz o que falta em vez do erro cru
const respSemBanco = e => e.status === 404 || /radar_respostas/.test(e.message || "");
const RESP_SEM_BANCO = `<h1>Respostas</h1><div class="aviso erro" id="resp-sem-banco">A aba Respostas precisa do banco desta versão: o administrador roda o <b>sql/radar-setup-v0.47.0.sql</b> (Supabase → SQL Editor) e recarrega esta página.</div>`;

/* o campo "publicação" aceita o número (o ID da mídia) ou, no Facebook, o link da publicação (a tela monta pagina_post) */
function respMidia(texto, rede, contas){
  const t = String(texto || "").trim();
  if(/^[0-9][0-9_]{0,39}$/.test(t)) return t;
  if(rede === "facebook"){
    const m = /facebook\.com\/[^ ]*?(?:posts\/|story_fbid=)([0-9]{5,30})/.exec(t);
    const pagina = (contas || []).find(c => c.rede === "facebook");
    if(m && pagina) return `${pagina.conta_id}_${m[1]}`;
  }
  return null;
}

/* ------------------------------------------------------------ a aba */
async function telaRespostas(){
  if(RESPOSTAS_VERSAO !== VERSAO) return `<h1>Respostas</h1><div class="aviso erro" id="resp-versao">Esta tela (v${h(VERSAO)}) e o arquivo da aba Respostas (radar-respostas.js, v${h(RESPOSTAS_VERSAO)}) são de versões diferentes: um deles ficou guardado no navegador. Aperte Ctrl+F5 (no celular, recarregue a página).</div>`;
  let s, registro, publicadas = [];
  try{
    s = await rpc("radar_respostas_situacao");
    registro = await rpc("radar_respostas_listar", {p_gatilho: RESP_E.f_gatilho ? Number(RESP_E.f_gatilho) : null,
                                                    p_situacao: RESP_E.f_situacao || null, p_limite: 100});
    if(RESP_E.form !== null) publicadas = await rpc("radar_respostas_publicadas");
  }catch(e){
    if(respSemBanco(e)) return RESP_SEM_BANCO;
    throw e;
  }
  const adm = ehAdmin();
  const g = s.gatilhos || [], contas = s.contas || [];
  const ligado = !!(s.cfg || {}).ligado;
  const editando = RESP_E.form !== null && RESP_E.form !== "novo" ? g.find(x => x.id === RESP_E.form) : null;
  return `<h1>Respostas automáticas</h1>
  <p class="explica">O Radar responde sozinho ao comentário que traz a <b>palavra-chave</b> de uma publicação escolhida (ex.:
  “Comente <b>QUERO</b> e receba o material”): uma resposta pública e uma mensagem privada com o link. O mesmo comentário nunca é
  respondido duas vezes, a própria conta é ignorada e há um limite por hora (o que passar sai na hora seguinte, sozinho).</p>
  <div class="aviso alerta" id="resp-meta">Os avisos de comentário só chegam depois que a <b>Meta aprovar o acesso avançado</b> do
  aplicativo (comentários e mensagens). O pedido tem passo a passo no LEIAME; até lá dá para cadastrar os gatilhos e testar a conexão.</div>

  <section id="resp-situacao">
    <h2>Situação</h2>
    <p>${ligado ? "Respostas automáticas <b>ligadas</b>." : `<span class="tag erro">PAUSADAS</span> Nenhuma resposta sai até retomar.`}
    ${adm ? `<button class="btn${ligado ? " perigo" : ""}" type="button" data-acao="resp-pausar" data-ligar="${ligado ? "" : "1"}">
      ${ligado ? "Pausar todas as respostas" : "Retomar as respostas"}</button>` : ""}</p>
    <p id="resp-contas">${contas.length ? "Contas conectadas: " + contas.map(c =>
        `<b>${h(RESP_REDES[c.rede] || c.rede)}</b> (${h(c.nome || c.conta_id)})`).join(" e ") + "."
      : "Nenhuma conta conectada ainda: clique em “Testar conexão” depois de guardar os segredos da função (LEIAME)."}
    ${adm ? `<button class="btn" type="button" data-acao="resp-testar">Testar conexão</button>` : ""}</p>
  </section>

  <section id="resp-gatilhos">
    <h2>Gatilhos</h2>
    ${g.length ? `<div class="rolagem"><table><tr><th>Rede</th><th>Publicação</th><th>Palavra-chave</th><th>Situação</th><th>Última hora</th>
      <th>Na fila</th><th>Respondidos</th>${adm ? "<th></th>" : ""}</tr>
      ${g.map(x => `<tr data-gatilho="${x.id}"><td>${h(RESP_REDES[x.rede] || x.rede)}</td>
        <td>${h(x.titulo || x.midia_id)}</td><td>${h(x.palavra_chave)}</td>
        <td>${x.ativo ? '<span class="tag ok">ativo</span>' : '<span class="tag neutro">desligado</span>'}</td>
        <td>${Number(x.ultima_hora)} de ${Number(x.limite_hora)}</td><td>${Number(x.pendentes)}</td><td>${Number(x.enviados)}</td>
        ${adm ? `<td class="acoes-linha"><button class="btn" type="button" data-acao="resp-editar" data-id="${x.id}">Editar</button>
          <button class="btn" type="button" data-acao="resp-mudar" data-id="${x.id}" data-ativo="${x.ativo ? "" : "1"}">${x.ativo ? "Desligar" : "Ligar"}</button>
          <button class="btn perigo" type="button" data-acao="resp-apagar" data-id="${x.id}" data-titulo="${h(x.titulo || x.midia_id)}">Excluir</button></td>` : ""}
      </tr>`).join("")}</table></div>`
      : `<p id="resp-vazio">Nenhum gatilho ainda.${adm ? " Clique em “+ Novo gatilho” e escolha uma publicação." : ""}</p>`}
    ${adm ? `<div class="acoes"><button class="btn" type="button" data-acao="resp-novo">${RESP_E.form === null ? "+ Novo gatilho" : "Fechar o formulário"}</button></div>` : ""}
    ${adm && RESP_E.form !== null ? respFormulario(editando, publicadas, contas) : ""}
  </section>

  <section id="resp-registro">
    <h2>Registro</h2>
    <form data-form="respFiltro" class="filtros">
      <select name="gatilho" id="resp-f-gatilho"><option value="">Todos os gatilhos</option>
        ${g.map(x => `<option value="${x.id}"${String(x.id) === RESP_E.f_gatilho ? " selected" : ""}>${h(x.titulo || x.midia_id)}</option>`).join("")}</select>
      <select name="situacao" id="resp-f-situacao"><option value="">Todas as situações</option>
        ${Object.entries(RESP_SITUACOES).map(([v, [r]]) => `<option value="${v}"${v === RESP_E.f_situacao ? " selected" : ""}>${r}</option>`).join("")}</select>
      <button class="btn">Filtrar</button></form>
    ${(registro || []).length ? `<div class="rolagem"><table id="resp-tabela"><tr><th>Quando</th><th>Rede</th><th>Quem</th><th>Comentário</th>
      <th>Situação</th><th>Detalhe</th>${adm ? "<th></th>" : ""}</tr>
      ${registro.map(r => { const [rot, cls] = RESP_SITUACOES[r.situacao] || [r.situacao, "neutro"]; return `<tr>
        <td>${respQuando(r.criado_em)}</td><td>${h(RESP_REDES[r.rede] || r.rede)}</td><td>${h(r.autor_nome || "—")}</td>
        <td class="resp-texto">${h(r.texto_comentario || "")}</td>
        <td><span class="tag ${cls}">${rot}</span>${r.situacao === "enviado" && !r.privada_ok ? ' <span class="tag alerta">sem a privada</span>' : ""}</td>
        <td>${h(r.motivo || r.erro || (r.situacao === "enviado" ? (r.privada_ok ? "pública + privada" : "só a pública") : ""))}</td>
        ${adm ? `<td>${r.situacao === "erro" ? `<button class="btn" type="button" data-acao="resp-reenviar" data-id="${r.id}">Tentar de novo</button>` : ""}</td>` : ""}
      </tr>`; }).join("")}</table></div>`
      : `<p id="resp-registro-vazio">Nenhum comentário tratado ainda${RESP_E.f_gatilho || RESP_E.f_situacao ? " com este filtro" : ""}.</p>`}
  </section>
  <p class="explica" id="resp-rodape">O registro guarda só o nome público, o texto do comentário e o que o Radar fez. Nenhum token
  fica em tabela nenhuma; a chave da Meta mora nos segredos da função. Respostas com conteúdo geral, sem dado de cliente.</p>`;
}

/* o formulário do gatilho (novo ou edição), com as publicações feitas pelo próprio Radar para escolher */
function respFormulario(ed, publicadas, contas){
  const v = ed || {rede: "instagram", midia_id: "", titulo: "", palavra_chave: "", resposta_publica: "", mensagem_privada: "",
                   link_material: "", limite_hora: 20, ativo: true};
  const opcoes = (publicadas || []).map(p => `<option value="${h(p.rede)}|${h(p.midia_id)}">
    ${h(RESP_REDES[p.rede] || p.rede)} · ${h((p.titulo || "").slice(0, 60) || p.midia_id)}</option>`).join("");
  return `<form data-form="respGatilho" id="resp-form"${ed ? ` data-id="${ed.id}"` : ""}>
    <h3>${ed ? "Editar o gatilho" : "Novo gatilho"}</h3>
    ${opcoes ? `<label for="resp-publicada">Publicação feita pelo Radar (escolher daqui preenche a rede e o número)</label>
      <select id="resp-publicada" data-acao="resp-publicada"><option value="">— escolher —</option>${opcoes}</select>` : ""}
    <div class="grade">
      <div><label for="resp-rede">Rede</label><select id="resp-rede" name="rede">
        <option value="instagram"${v.rede === "instagram" ? " selected" : ""}>Instagram</option>
        <option value="facebook"${v.rede === "facebook" ? " selected" : ""}>Facebook (página)</option></select></div>
      <div><label for="resp-midia">Publicação (o número da mídia; no Facebook pode colar o link)</label>
        <input id="resp-midia" name="midia" required value="${h(v.midia_id)}"></div></div>
    <label for="resp-titulo">Título (só para você reconhecer na lista)</label>
    <input id="resp-titulo" name="titulo" maxlength="120" value="${h(v.titulo)}">
    <label for="resp-chave">Palavra-chave (sem diferenciar maiúsculas, acentos nem pontuação)</label>
    <input id="resp-chave" name="palavra_chave" required maxlength="40" value="${h(v.palavra_chave)}" placeholder="QUERO">
    <label for="resp-publica">Resposta pública ao comentário</label>
    <textarea id="resp-publica" name="resposta_publica" required maxlength="500" rows="2">${h(v.resposta_publica)}</textarea>
    <label for="resp-privada">Mensagem privada (o link do material vai junto, na linha de baixo)</label>
    <textarea id="resp-privada" name="mensagem_privada" required maxlength="900" rows="3">${h(v.mensagem_privada)}</textarea>
    <div class="grade">
      <div><label for="resp-link">Link do material (https://…; pode ficar vazio)</label>
        <input id="resp-link" name="link_material" maxlength="300" value="${h(v.link_material)}"></div>
      <div><label for="resp-limite">Limite de respostas por hora (1 a 200)</label>
        <input id="resp-limite" name="limite_hora" type="number" min="1" max="200" value="${h(v.limite_hora)}"></div></div>
    <label><input type="checkbox" name="ativo"${v.ativo ? " checked" : ""}> Gatilho ativo</label>
    <div class="aviso" id="resp-previa">Como o cliente verá: a resposta pública aparece embaixo do comentário dele; a mensagem
    privada chega no direct/Messenger com o link. A Meta permite <b>uma</b> mensagem privada por comentário, em até <b>7 dias</b>.</div>
    <div class="acoes"><button class="btn">${ed ? "Salvar o gatilho" : "Criar o gatilho"}</button></div></form>`;
}

/* a função radar-meta-webhook: os recados de instalação em português */
function respErroFuncao(e){
  if(e.status === 404) return new ErroApi("A função radar-meta-webhook não está instalada no Supabase: veja no LEIAME, “Da v0.34.0 para a v0.35.0”.", 404);
  if(/Ação desconhecida/.test(e.message || "")) return new ErroApi("A função radar-meta-webhook instalada é de uma versão anterior: faça o Deploy do index.ts desta versão (Verify JWT desligado).", e.status);
  return e;
}
const respFuncao = (corpo, tempo = 60000) => pedir("POST", "/functions/v1/radar-meta-webhook", {corpo, tempo}).catch(e => { throw respErroFuncao(e); });

/* ------------------------------------------------- ações e formulários (o index.html junta) */
const RESPOSTAS = {
  navegacao: ["resp-novo", "resp-editar", "resp-publicada"],
  acoes: {
    "resp-novo"(){ RESP_E.form = RESP_E.form === null ? "novo" : null; return desenhar().then(() => $("#resp-midia")?.focus()); },
    "resp-editar"(el){ RESP_E.form = Number(el.dataset.id); return desenhar().then(() => $("#resp-form")?.scrollIntoView({block: "start"})); },
    "resp-publicada"(el){
      const [rede, midia] = String(el.value || "").split("|");
      if(!midia) return;
      const r = $("#resp-rede"), m = $("#resp-midia");
      if(r) r.value = rede;
      if(m) m.value = midia;
    },
    async "resp-pausar"(el){
      const ligar = el.dataset.ligar === "1";
      if(!ligar && !confirm("Pausar TODAS as respostas automáticas? Os comentários novos com palavra-chave ficam descartados enquanto estiver pausado (não entram na fila).")) return;
      await rpc("radar_respostas_configurar", {p: {ligado: ligar}});
      await desenhar();
      recado(ligar ? "Respostas automáticas retomadas." : "Respostas automáticas pausadas.");
    },
    async "resp-testar"(){
      const r = await respFuncao({acao: "diagnostico"});
      await desenhar();
      if(r.contas?.length) recado(`Conexão ok: ${r.contas.map(c => `${RESP_REDES[c.rede] || c.rede} (${c.nome || c.conta_id})`).join(" e ")}.` +
                                  ((r.avisos || []).length ? " " + r.avisos.join(" ") : ""), (r.avisos || []).length ? "aviso" : false);
      else recado(r.message || "O teste não devolveu conta nenhuma.", true);
    },
    async "resp-mudar"(el){
      await rpc("radar_respostas_gatilho_mudar", {p_id: Number(el.dataset.id), p_ativo: el.dataset.ativo === "1"});
      await desenhar();
      recado(el.dataset.ativo === "1" ? "Gatilho ligado." : "Gatilho desligado: os comentários novos desta publicação não são respondidos.");
    },
    async "resp-apagar"(el){
      if(!confirm(`Excluir o gatilho “${el.dataset.titulo}”? O registro dos comentários já tratados fica guardado. Não dá para desfazer.`)) return;
      await rpc("radar_respostas_gatilho_apagar", {p_id: Number(el.dataset.id)});
      if(RESP_E.form === Number(el.dataset.id)) RESP_E.form = null;
      await desenhar();
      recado("Gatilho excluído.");
    },
    async "resp-reenviar"(el){
      await rpc("radar_respostas_reenviar", {p_id: Number(el.dataset.id)});
      try{ await respFuncao({acao: "pendentes"}, 150000); }catch(e){ /* a agenda tenta de novo em 5 minutos */ }
      await desenhar();
      recado("Reenviado para a fila: sai agora ou em até 5 minutos (pela agenda).");
    }
  },
  forms: {
    async respGatilho(f){
      const contas = (await rpc("radar_respostas_situacao")).contas || [];
      const midia = respMidia(f.midia.value, f.rede.value, contas);
      if(!midia){ recado(f.rede.value === "facebook"
        ? "Não reconheci a publicação: cole o número da mídia, ou o link da publicação da página (depois de “Testar conexão”)."
        : "Não reconheci a publicação: no Instagram, use o número da mídia (escolha uma publicação do Radar na lista, ou copie o número da Meta).", true); return; }
      const id = await rpc("radar_respostas_gatilho_salvar", {p_id: f.dataset.id ? Number(f.dataset.id) : null,
        p: {rede: f.rede.value, midia_id: midia, titulo: f.titulo.value.trim(), palavra_chave: f.palavra_chave.value.trim(),
            resposta_publica: f.resposta_publica.value.trim(), mensagem_privada: f.mensagem_privada.value.trim(),
            link_material: f.link_material.value.trim(), limite_hora: Number(f.limite_hora.value), ativo: f.ativo.checked}});
      RESP_E.form = null;
      await desenhar();
      recado(f.dataset.id ? "Gatilho salvo." : `Gatilho criado (nº ${id}). Agora é esperar os comentários com a palavra-chave.`);
    },
    respFiltro(f){
      RESP_E.f_gatilho = f.gatilho.value;
      RESP_E.f_situacao = f.situacao.value;
      return desenhar();
    }
  }
};
