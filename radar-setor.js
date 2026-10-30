"use strict";
/* ====================================================================
   RADAR ARTECON — aba Setor (v0.34.0)
   Como estão as publicações de um setor no Instagram (ex.: contabilidade): o administrador cria o setor, escolhe as contas públicas
   (comerciais ou de criador) de outros escritórios — e a da Artecon, para comparar — e clica em "Atualizar a análise"; toda segunda-
   feira a leitura automática (sql/radar-setor-agenda.sql) lê de novo. Quem lê o Instagram é a função radar-concorrentes (só leitura
   na API oficial da Meta). A equipe toda vê o painel: publicações por semana, mistura de formatos, engajamento por publicação,
   melhores dias e horários, temas mais frequentes e as publicações de maior engajamento (só o link do Instagram e um trecho curto da
   legenda; nenhuma imagem). Serve para ver formatos e temas, nunca para copiar (NBC PG 01).
   Os números vêm prontos do banco (radar_setor_painel, no fuso de Brasília): a tela só desenha (HTML e SVG, sem biblioteca).
   Carregado ANTES do script principal (index.html): aqui só há declarações e o objeto SETOR ({acoes, forms, navegacao}), que o
   script principal junta aos dele. Nada roda no carregamento: as funções usam os globais do script principal (h, ler, rpc, pedir,
   recado, desenhar, ehAdmin, E, ErroApi, VERSAO, $) só quando são chamadas. Quem confere quem pode o quê é o banco.
   A busca por hashtag fica desligada (Configuração da aba) até a Meta aprovar o recurso Instagram Public Content Access.
   ==================================================================== */
const SETOR_VERSAO = "0.59.0";        // igual à VERSAO do index.html; diferente, um dos dois ficou guardado no navegador (Ctrl+F5)

// o que só a tela guarda: o setor escolhido, o período, o quadro do administrador aberto e o formulário de setor novo
let SETOR_E = {setor: null, dias: 90, gerir: false, novo: false};

// cores dos formatos (fixas: a cor segue o formato, nunca a posição; conferidas no validador de paleta). Foto e Vídeo têm pouco
// contraste com o branco: todo gráfico leva o número escrito ao lado e a tabela. A Artecon é sempre o marinho.
const SETOR_CORES = {reel: "#2a78d6", carrossel: "#eb6834", foto: "#1baf7a", video: "#eda100"};
const SETOR_FORMATOS = {reel: "Reel", carrossel: "Carrossel", foto: "Foto", video: "Vídeo"};
const SETOR_ARTECON = "#011F48", SETOR_AZUL = "#2a78d6", SETOR_CINZA = "#B8C0C8";
const SETOR_DIAS = ["", "seg", "ter", "qua", "qui", "sex", "sáb", "dom"];                 // 1 = segunda … 7 = domingo (como o banco)
const SETOR_FAIXAS = ["0h–5h", "6h–8h", "9h–11h", "12h–14h", "15h–17h", "18h–20h", "21h–23h"];
const SETOR_PERIODOS = [[30, "30 dias"], [90, "90 dias"], [180, "180 dias"], [365, "1 ano"]];
const SETOR_SITUACOES = {ok: ["ok", "ok"], erro: ["erro", "erro"], pausada: ["pausada", "neutro"], poucos_dados: ["poucos dados", "neutro"],
                         nunca: ["ainda não lida", "alerta"]};
const SETOR_ETICA = "Serve para ver formatos e temas, nunca para copiar (NBC PG 01).";
// a lista padrão de temas de contabilidade (a mesma de radar_setor_temas_padrao, no banco; o teste confere): o botão "Voltar aos
// temas padrão" preenche a caixa com ela, sem gravar
const SETOR_TEMAS_PADRAO = [
  ["Reforma tributária", "reforma tributária, IBS, CBS, imposto seletivo, split payment, IVA, Comitê Gestor, EC 132, LC 214"],
  ["Imposto de Renda", "imposto de renda, IRPF, IRPJ, declaração do IR, malha fina, restituição, carnê-leão, leão, DIRPF, informe de rendimentos"],
  ["MEI", "MEI, microempreendedor, microempreendedor individual, DASN-SIMEI, SIMEI, CCMEI, DAS do MEI, desenquadramento"],
  ["Simples Nacional", "Simples Nacional, PGDAS, PGDAS-D, DEFIS, fator R, anexo III, anexo V, sublimite, exclusão do Simples"],
  ["Folha e eSocial", "folha de pagamento, eSocial, FGTS, INSS, 13º salário, décimo terceiro, férias, rescisão, CLT, DCTFWeb, salário mínimo, pró-labore, trabalhista, admissão, demissão"],
  ["Abertura de empresa", "abrir empresa, abertura de empresa, abrir CNPJ, abertura de CNPJ, contrato social, junta comercial, alvará, inscrição estadual, inscrição municipal, natureza jurídica, sociedade limitada, holding, regime tributário, formalizar, formalização"],
  ["Notas e impostos", "nota fiscal, NF-e, NFS-e, NFC-e, ICMS, ISS, DIFAL, substituição tributária, PIS, Cofins, IPI, alíquota"],
  ["Prazos e obrigações", "prazo, prazos, vencimento, obrigação acessória, obrigações acessórias, agenda tributária, ECD, ECF, DCTF, EFD, SPED, Reinf, prorrogação, prorrogado, multa por atraso"],
  ["Gestão e finanças", "fluxo de caixa, capital de giro, planejamento tributário, lucro presumido, lucro real, distribuição de lucros, dividendos, precificação, faturamento, margem, finanças, gestão financeira"],
  ["Dicas e explicações", "dica, dicas, você sabia, saiba, entenda, o que é, como funciona, passo a passo, erros, cuidado, atenção, diferença entre, guia, aprenda, dúvida, dúvidas"],
  ["Institucional e equipe", "nossa equipe, equipe, colaborador, colaboradora, colaboradores, bastidores, nosso escritório, aniversário da empresa, anos de história, confraternização, nosso time, sócio, sócia, sócios, evento, palestra, treinamento, inauguração"],
  ["Datas comemorativas", "feliz, parabéns, dia do contador, dia das mães, dia dos pais, dia da mulher, dia do cliente, dia do trabalhador, natal, ano novo, páscoa, carnaval, feriado, recesso, boas festas, outubro rosa, novembro azul, setembro amarelo, homenagem"],
  ["Serviços e captação", "nossos serviços, orçamento, solicite, contrate, fale com a gente, fale conosco, entre em contato, chame no whatsapp, agende, consultoria, trocar de contador, troque de contador, mudar de contador, seja nosso cliente, planos, promoção, desconto, grátis, gratuita"],
  ["Humor e trends", "meme, memes, trend, pov, kkk, kkkk, humor, quem nunca"],
  ["Vagas", "estamos contratando, vaga, vagas, currículo, trabalhe conosco"],
  ["Depoimentos de clientes", "depoimento, depoimentos, feedback, avaliação, cliente satisfeito, clientes satisfeitos, o que dizem"]];

/* ------------------------------------------------------------ formatação (pt-BR, Brasília) */
const setorNum = (x, casas = 1) => x === null || x === undefined || x === "" || !isFinite(Number(x)) ? "—"
  : Number(x).toLocaleString("pt-BR", {minimumFractionDigits: casas, maximumFractionDigits: casas});
const setorPct = (x, casas = 2) => x === null || x === undefined || !isFinite(Number(x)) ? "—" : setorNum(x, casas) + "%";
const setorVezes = x => x === null || x === undefined || !isFinite(Number(x)) ? "—" : setorNum(x, 1) + "×";
const setorInteiro = x => x === null || x === undefined || !isFinite(Number(x)) ? "—" : Number(x).toLocaleString("pt-BR");
const setorQuando = v => { const d = new Date(v || ""); return !v || isNaN(d) ? "—"
  : d.toLocaleString("pt-BR", {timeZone: "America/Sao_Paulo", weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}).replace(".", ""); };
const setorHora = v => { const d = new Date(v || ""); return isNaN(d) ? "—"
  : d.toLocaleString("pt-BR", {timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"}).replace(",", " às"); };
// "2026-10-09T15:00" (já em Brasília, do banco) → "09/10/2026 15:00"
const setorDataPost = s => { const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(String(s || "")); return m ? `${m[3]}/${m[2]}/${m[1]} ${m[4]}` : "—"; };
const setorDiaMes = iso => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || "")); return m ? `${m[3]}/${m[2]}` : "—"; };
const setorMes = iso => { const m = /^(\d{4})-(\d{2})/.exec(String(iso || "")); return m ? ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"][Number(m[2]) - 1] + "/" + m[1].slice(2) : "—"; };
const setorLinkOk = u => /^https:\/\/www\.instagram\.com\/[A-Za-z0-9_./?=&%-]+$/.test(String(u || ""));
const setorLink = (u, rotulo = "Ver no Instagram ↗") => setorLinkOk(u) ? `<a href="${h(u)}" target="_blank" rel="noopener noreferrer">${h(rotulo)}</a>` : "";
const setorPerfil = nome => /^[a-z0-9._]{1,30}$/.test(String(nome || "")) ? `<a href="https://www.instagram.com/${h(nome)}/" target="_blank" rel="noopener noreferrer">@${h(nome)}</a>` : "@" + h(nome);
// o banco ainda não tem a aba (setup de antes desta versão): a tela diz o que falta em vez do erro cru
const setorSemBanco = e => e.status === 404 || /radar_setor/.test(e.message || "");
const SETOR_SEM_BANCO = `<h1>Setor</h1><div class="aviso erro" id="setor-sem-banco">A aba Setor precisa do banco desta versão: o administrador roda o <b>sql/radar-setup-v0.50.0.sql</b> (Supabase → SQL Editor) e recarrega esta página.</div>`;

/* ------------------------------------------------------------------------- a aba */
async function telaSetor(){
  if(SETOR_VERSAO !== VERSAO) return `<h1>Setor</h1><div class="aviso erro" id="setor-versao">Esta tela (v${h(VERSAO)}) e o arquivo da aba Setor (radar-setor.js, v${h(SETOR_VERSAO)}) são de versões diferentes: um deles ficou guardado no navegador. Aperte Ctrl+F5 (no celular, recarregue a página).</div>`;
  let setores, sit, painel = null, contas = [];
  try{
    setores = await ler("radar_setor_setores", {select: "id,nome,ativo,temas", order: "nome"});
    sit = await rpc("radar_setor_situacao");
    if(!setores.some(s => s.id === SETOR_E.setor)) SETOR_E.setor = (setores.find(s => s.ativo) || setores[0] || {}).id ?? null;
    if(SETOR_E.setor !== null){
      painel = await rpc("radar_setor_painel", {p_setor: SETOR_E.setor, p_dias: SETOR_E.dias});
      if(ehAdmin()) contas = await ler("radar_setor_contas", {select: "id,tipo,nome,ativa,propria,erro,aviso,coletada_em,pedida_em,falhas_consecutivas",
                                                              setor_id: "eq." + SETOR_E.setor, order: "tipo.desc,nome"});
    }
  }catch(e){ if(setorSemBanco(e)) return SETOR_SEM_BANCO; throw e; }
  const setor = setores.find(s => s.id === SETOR_E.setor);
  const topo = `${setorEstilo()}<h1>Setor no Instagram</h1>
    <div class="aviso alerta" id="setor-etica"><b>${SETOR_ETICA}</b> Não reproduza texto, arte ou roteiro de outro escritório e não cite nem compare escritórios nos posts.</div>`;
  if(!setor){
    return `<div id="setor">${topo}${ehAdmin() ? setorFormNovo(true)
      : `<div class="painel" id="setor-vazio"><p>O administrador ainda não cadastrou nenhum setor.</p></div>`}</div>`;
  }
  const cfg = sit.cfg || {};
  const escolha = setores.length > 1 || ehAdmin() ? `<div class="chips setor-escolha" id="setor-escolha">${setores.map(s =>
      `<button type="button" class="chip ${s.id === setor.id ? "ativa" : ""}" data-acao="setor-escolher" data-id="${h(s.id)}">${h(s.nome)}${s.ativo ? "" : " (inativo)"}</button>`).join("")}
    ${ehAdmin() ? `<button type="button" class="chip" data-acao="setor-novo">+ Novo setor</button>` : ""}</div>` : "";
  const periodo = `<div class="chips" id="setor-periodo">${SETOR_PERIODOS.map(([d, r]) =>
      `<button type="button" class="chip ${SETOR_E.dias === d ? "ativa" : ""}" data-acao="setor-dias" data-dias="${d}">${r}</button>`).join("")}</div>`;
  return `<div id="setor">${topo}${escolha}${SETOR_E.novo && ehAdmin() ? setorFormNovo(false) : ""}${periodo}
    ${setorSituacao(painel, sit, cfg, setor)}
    ${setorCorpo(painel)}
    ${setorHashtags(painel, cfg, contas)}
    ${setorComoLer()}
    ${ehAdmin() ? setorGerir(setor, contas, cfg) : ""}</div>`;
}

function setorEstilo(){
  return `<style>
#setor .chips{margin:8px 0}
#setor .cartao{cursor:default}
#setor .cartao small{display:block;font-size:.8rem;color:#5A636D;margin-top:2px}
#setor .setor-situacao{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin:6px 0 14px}
#setor .setor-situacao>span{min-width:0;flex:1 1 16em} #setor .setor-situacao .selo{white-space:normal}
#setor .setor-grafico{width:100%;height:auto;display:block;max-width:760px}
#setor .setor-legenda{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.85rem;margin:8px 0}
#setor .setor-chave{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:5px}
#setor .setor-chave.ponto{border-radius:50%;width:10px;height:10px;border:2px solid #fff;box-shadow:0 0 0 1px #011F48}
#setor .setor-pilha-linha{display:grid;grid-template-columns:5.5em minmax(0,1fr);gap:8px;align-items:center;margin:6px 0}
#setor .setor-pilha{display:flex;gap:2px;height:22px;background:#fff;border-radius:4px;overflow:hidden;min-width:0}
#setor .setor-pilha span{display:block;min-width:2px}
#setor .setor-barra-linha{display:grid;grid-template-columns:minmax(0,11em) minmax(0,1fr) 5.2em;gap:8px;align-items:center;margin:4px 0;font-size:.9rem}
#setor .setor-barra-linha.tema{grid-template-columns:minmax(0,12em) minmax(0,1fr) minmax(0,15em)}
#setor .setor-rotulo{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#setor .setor-trilho{position:relative;height:14px;min-width:0}
#setor .setor-barra{position:absolute;left:0;top:1px;height:12px;border-radius:0 4px 4px 0}
#setor .setor-mediana{position:absolute;top:-3px;bottom:-3px;border-left:2px dashed #4F4C4D}
#setor .setor-marca{position:absolute;top:-3px;width:4px;height:20px;margin-left:-2px;background:#011F48;border:1px solid #fff;border-radius:2px}
#setor .setor-valor{font-variant-numeric:tabular-nums}
#setor table.setor-mapa{width:auto;border-collapse:separate;border-spacing:2px}
#setor table.setor-mapa td,#setor table.setor-mapa th{text-align:center;padding:5px 6px;border:0;font-size:.82rem;white-space:nowrap}
#setor table.setor-mapa td small{display:block;color:#5A636D;font-size:.7rem}
#setor .setor-melhores{list-style:none;padding:0;margin:0}
#setor .setor-melhores li{border-bottom:1px solid var(--linha);padding:8px 0}
#setor .setor-melhores q{display:block;color:#4F4C4D;margin:3px 0;font-style:italic}
#setor .setor-mini{display:flex;gap:1px;width:90px;height:10px;border-radius:3px;overflow:hidden;background:#EEF0F2}
#setor td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
#setor .setor-gerir textarea{min-height:110px}
#setor .setor-gerir h3{margin-top:14px}
@media (max-width:640px){
  #setor .setor-barra-linha{grid-template-columns:minmax(0,7.5em) minmax(0,1fr) 4.6em;font-size:.84rem}
  #setor .setor-barra-linha.tema{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
  #setor .setor-barra-linha.tema .setor-valor{grid-column:1 / -1}
}
</style>`;
}

/* a situação da leitura: a última, a próxima automática, a pausa da Meta e o botão do administrador (setor inativo não é lido: sem botão) */
function setorSituacao(p, sit, cfg, setor){
  const r = p?.resumo || {}, erros = (p?.contas || []).filter(c => c.situacao === "erro").length;
  const partes = [];
  partes.push(p?.atualizado_em ? `Última leitura: ${h(setorQuando(p.atualizado_em))} · ${h(r.com_dados ?? 0)} de ${h(r.contas ?? 0)} conta(s) com dados${erros ? `, ${erros} com erro (veja na tabela)` : ""}`
                               : "Nenhuma conta lida ainda neste setor.");
  if(cfg.coleta_ligada === false) partes.push("Leitura automática desligada (Configuração da aba)");
  else if(sit.proxima) partes.push(`Próxima leitura automática: ${h(setorQuando(sit.proxima))}`);
  if(sit.pausa_ate) partes.push(`<b>A Meta pediu uma pausa até ${h(setorHora(sit.pausa_ate))} (Brasília)</b>${sit.pausa_motivo === "configuracao" ? " por um problema de configuração (token ou permissão): a leitura automática espera" : ""}`);
  if(sit.em_andamento) partes.push("<b>Leitura em andamento…</b>");
  if(ehAdmin() && sit.agenda && sit.agenda.instalada === false) partes.push(`<span class="selo alerta">a leitura automática ainda não foi instalada (sql/radar-setor-agenda.sql)</span>`);
  if(setor && setor.ativo === false) partes.push(`<b>Setor inativo: não é lido</b>${ehAdmin() ? " (para voltar a ler, marque “Setor ativo” em Gerenciar o setor)" : ""}`);
  return `<div class="setor-situacao" id="setor-situacao"><span class="sub">${partes.join(" · ")}</span>
    ${ehAdmin() && setor?.ativo !== false ? `<button type="button" class="btn" data-acao="setor-atualizar">Atualizar a análise</button>` : ""}<span class="sub" id="setor-progresso" role="status" aria-live="polite"></span></div>`;
}

/* os quadros do painel */
function setorCorpo(p){
  const r = p?.resumo || {};
  if(!p || !r.com_dados && !(p.contas || []).some(c => c.propria && c.coletada_em)){
    return `<div class="painel" id="setor-sem-dados"><p>Ainda não há contas lidas neste setor.</p>${ehAdmin()
      ? `<p class="sub">Inclua as contas (Gerenciar o setor, abaixo) e clique em “Atualizar a análise”.</p>` : ""}</div>${setorTabelaContas(p)}`;
  }
  const mais = r.formato_mais_usado;
  const quadro = (titulo, valor, extra) => `<div class="cartao"><span>${titulo}</span><b>${valor}</b>${extra ? `<small>${extra}</small>` : ""}</div>`;
  const resumo = `<div class="cartoes" id="setor-resumo">
    ${quadro("Contas analisadas", h(r.com_dados ?? 0), `${h(r.elegiveis ?? 0)} com dados suficientes para o engajamento`)}
    ${quadro("Publicações por semana", h(setorNum(r.setor_posts_semana)), `setor (mediana das contas)${p.artecon ? ` · Artecon ${h(setorNum(r.artecon_posts_semana))}` : ""}`)}
    ${quadro("Engajamento por publicação", h(setorPct(r.setor_engajamento)), `setor (mediana)${p.artecon ? ` · Artecon ${h(setorPct(r.artecon_engajamento))}` : ""}`)}
    ${quadro("Formato mais usado", mais ? h(SETOR_FORMATOS[mais.formato] || mais.formato) : "—", mais ? `${h(setorNum(mais.pct, 0))}% das publicações do setor` : "")}</div>`;
  return resumo + setorSerie(p) + setorFormatosHtml(p) + setorEngajamento(p) + setorDiasHoras(p) + setorTemas(p) + setorMelhores(p) + setorTabelaContas(p);
}

/* publicações por semana (ou mês): barras = média por conta do setor; pontos = Artecon (SVG, um eixo só) */
function setorSerie(p){
  const s = Array.isArray(p.series) ? p.series : [], semana = p.periodo?.agrupado !== "mes";
  if(!s.length) return "";
  const W = 640, H = 210, ml = 34, mr = 10, mt = 12, mb = 30, larg = W - ml - mr, alt = H - mt - mb;
  const maior = Math.max(1, ...s.map(x => Number(x.setor) || 0), ...s.map(x => Number(x.artecon) || 0));
  const passo = [0.5, 1, 2, 5, 10, 20, 50, 100].find(v => maior / v <= 4) || 200, topo = Math.ceil(maior / passo) * passo;
  const y = v => mt + alt - (v / topo) * alt, banda = larg / s.length, bw = Math.min(36, banda * 0.6);
  const rotulo = x => semana ? setorDiaMes(x.inicio) : setorMes(x.inicio);
  const unidade = semana ? "semana" : "mês";
  let g = "";
  for(let v = 0; v <= topo + 1e-9; v += passo){
    g += `<line x1="${ml}" x2="${W - mr}" y1="${y(v)}" y2="${y(v)}" stroke="#E3E7EC"/><text x="${ml - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#5A636D">${h(setorNum(v, passo < 1 ? 1 : 0))}</text>`;
  }
  s.forEach((x, i) => {
    const cx = ml + banda * i + banda / 2, x0 = cx - bw / 2;
    const dica = `${semana ? "Semana de " + setorDiaMes(x.inicio) : setorMes(x.inicio)}: ${x.setor === null ? "nenhuma conta cobre o período inteiro" : setorNum(x.setor, 1) + " publicação(ões) por conta (" + x.contas + " conta(s))"}` +
                 (x.artecon !== null && x.artecon !== undefined ? `; Artecon: ${x.artecon}` : "") + (x.em_andamento ? " (em andamento)" : "");
    if(x.setor !== null && x.setor !== undefined && Number(x.setor) > 0){
      const yt = y(Number(x.setor)), base = y(0), rr = Math.min(4, (base - yt) / 2, bw / 2);
      g += `<path d="M${x0},${base} V${yt + rr} Q${x0},${yt} ${x0 + rr},${yt} H${x0 + bw - rr} Q${x0 + bw},${yt} ${x0 + bw},${yt + rr} V${base} Z" fill="${SETOR_AZUL}"${x.em_andamento ? ' fill-opacity="0.45"' : ""}><title>${h(dica)}</title></path>`;
    }
    g += `<rect x="${ml + banda * i}" y="${mt}" width="${banda}" height="${alt}" fill="transparent"><title>${h(dica)}</title></rect>`;
    if(x.artecon !== null && x.artecon !== undefined) g += `<circle cx="${cx}" cy="${y(Number(x.artecon))}" r="4" fill="${SETOR_ARTECON}" stroke="#fff" stroke-width="2"><title>${h(dica)}</title></circle>`;
    if(s.length <= 14 || i % Math.ceil(s.length / 14) === 0) g += `<text x="${cx}" y="${H - mb + 15}" text-anchor="middle" font-size="11" fill="#5A636D">${h(rotulo(x))}</text>`;
    if(x.em_andamento) g += `<text x="${cx}" y="${H - 3}" text-anchor="middle" font-size="10" fill="#5A636D">em andamento</text>`;
  });
  g += `<line x1="${ml}" x2="${W - mr}" y1="${y(0)}" y2="${y(0)}" stroke="#B8C0C8"/>`;
  const tabela = `<details><summary>Ver em tabela</summary><div class="rolagem"><table><tr><th>${semana ? "Semana" : "Mês"}</th><th>Setor (por conta)</th><th>Contas</th><th>Artecon</th></tr>${s.map(x =>
    `<tr><td>${h(semana ? setorDiaMes(x.inicio) + " a " + setorDiaMes(x.fim) : setorMes(x.inicio))}${x.em_andamento ? " (em andamento)" : ""}</td><td class="num">${h(setorNum(x.setor, 1))}</td><td class="num">${h(x.contas)}</td><td class="num">${h(x.artecon ?? "—")}</td></tr>`).join("")}</table></div></details>`;
  return `<div class="painel" id="setor-semanas"><h2>Publicações por ${unidade}</h2>
    <p class="sub">Barras: a média de publicações por conta do setor em cada ${unidade} (só as contas cujas publicações lidas cobrem o período inteiro). ${p.artecon ? "Pontos: a Artecon." : ""}</p>
    <svg class="setor-grafico" viewBox="0 0 ${W} ${H}" role="img" aria-label="Publicações por ${unidade}: setor e Artecon">${g}</svg>
    <div class="setor-legenda"><span><span class="setor-chave" style="background:${SETOR_AZUL}"></span>Setor (média por conta)</span>${p.artecon ? `<span><span class="setor-chave ponto" style="background:${SETOR_ARTECON}"></span>Artecon</span>` : ""}</div>${tabela}</div>`;
}

/* a mistura de formatos: barras 100% empilhadas (setor e Artecon), o % escrito na legenda; o engajamento por formato; reel × foto */
function setorFormatosHtml(p){
  const f = p.formatos || {}, ordem = ["reel", "carrossel", "foto", "video"];
  const pilha = (rot, m) => !m ? "" : `<div class="setor-pilha-linha"><span>${rot}</span><div class="setor-pilha" role="img" aria-label="${h(rot)}: ${h(ordem.map(k => `${SETOR_FORMATOS[k]} ${setorNum(m[k]?.pct, 0)}%`).join(", "))}">${ordem.filter(k => (m[k]?.n || 0) > 0).map(k =>
      `<span style="flex:${Number(m[k].n)} 1 0;background:${SETOR_CORES[k]}" title="${h(`${rot} — ${SETOR_FORMATOS[k]}: ${m[k].n} publicação(ões) (${setorNum(m[k].pct, 0)}%)`)}"></span>`).join("")}</div></div>`;
  const legenda = `<div class="setor-legenda">${ordem.filter(k => (f.setor?.[k]?.n || 0) + (f.artecon?.[k]?.n || 0) > 0).map(k =>
      `<span><span class="setor-chave" style="background:${SETOR_CORES[k]}"></span>${SETOR_FORMATOS[k]} ${h(setorNum(f.setor?.[k]?.pct, 0))}%${f.artecon ? ` (Artecon ${h(setorNum(f.artecon?.[k]?.pct, 0))}%)` : ""}</span>`).join("")}</div>`;
  const ef = (p.engajamento_formato || []).filter(x => x.n > 0);
  const rvf = p.reel_vs_foto || {};
  return `<div class="painel" id="setor-formatos"><h2>Mistura de formatos</h2>
    ${pilha("Setor", f.setor)}${pilha("Artecon", f.artecon)}${legenda}
    ${ef.length ? `<p>Engajamento típico por formato (contas com dados suficientes): ${ef.map(x => `${h(SETOR_FORMATOS[x.formato] || x.formato)} <b>${h(setorPct(x.mediana))}</b> <span class="sub">(${h(x.n)})</span>`).join(" · ")}</p>` : ""}
    ${rvf.contas >= 3 ? `<p>Na mesma conta, o reel ficou acima da foto em <b>${h(rvf.acima)} de ${h(rvf.contas)}</b> contas.</p>` : ""}
    <details><summary>Ver em tabela</summary><div class="rolagem"><table><tr><th>Formato</th><th>Setor</th><th>%</th>${f.artecon ? "<th>Artecon</th><th>%</th>" : ""}<th>Engajamento típico</th></tr>${ordem.map(k =>
      `<tr><td>${SETOR_FORMATOS[k]}</td><td class="num">${h(f.setor?.[k]?.n ?? 0)}</td><td class="num">${h(setorNum(f.setor?.[k]?.pct, 1))}%</td>${f.artecon ? `<td class="num">${h(f.artecon[k]?.n ?? 0)}</td><td class="num">${h(setorNum(f.artecon[k]?.pct, 1))}%</td>` : ""}<td class="num">${h(setorPct((p.engajamento_formato || []).find(x => x.formato === k)?.mediana))}</td></tr>`).join("")}</table></div></details></div>`;
}

/* engajamento por publicação, por conta: barras horizontais; a Artecon em marinho; a linha tracejada é a mediana do setor */
function setorEngajamento(p){
  const cs = (p.contas || []).filter(c => c.ativa && c.coletada_em && c.engajamento !== null && c.engajamento !== undefined);
  if(!cs.length) return "";
  const boas = cs.filter(c => c.elegivel).sort((a, b) => b.engajamento - a.engajamento), poucas = cs.filter(c => !c.elegivel);
  const maior = Math.max(...boas.concat(poucas).map(c => Number(c.engajamento)), Number(p.resumo?.setor_engajamento) || 0) * 1.1 || 1;
  const med = p.resumo?.setor_engajamento, pos = v => Math.max(0, Math.min(100, Number(v) / maior * 100));
  const linha = c => `<div class="setor-barra-linha"><span class="setor-rotulo" title="@${h(c.nome)}">@${h(c.nome)}${c.propria ? " <b>(Artecon)</b>" : ""}</span>
    <span class="setor-trilho"><span class="setor-barra" style="width:${pos(c.engajamento)}%;background:${c.propria ? SETOR_ARTECON : c.elegivel ? SETOR_AZUL : SETOR_CINZA}" title="${h(`@${c.nome}: ${setorPct(c.engajamento)} por publicação (mediana de ${c.n_engajamento} publicação(ões))`)}"></span>${med !== null && med !== undefined ? `<span class="setor-mediana" style="left:${pos(med)}%" title="Mediana do setor: ${h(setorPct(med))}"></span>` : ""}</span>
    <span class="setor-valor">${h(setorPct(c.engajamento))}${c.elegivel ? "" : ' <span class="sub">poucos dados</span>'}</span></div>`;
  return `<div class="painel" id="setor-engajamento"><h2>Engajamento por publicação, por conta</h2>
    <p class="sub">(curtidas + comentários) ÷ seguidores, a mediana das publicações do período de cada conta. A linha tracejada é a mediana do setor (${h(setorPct(med))}). Em cinza, as contas com menos de 100 seguidores ou menos de 5 publicações com curtidas visíveis: entram na tabela, mas não nas medianas.</p>
    ${boas.map(linha).join("")}${poucas.map(linha).join("")}</div>`;
}

/* melhores dias e horários (Brasília): cada publicação comparada com o típico da própria conta; "—" com menos de 5 publicações */
function setorDiasHoras(p){
  const dh = p.dias_horas || {}, cel = {};
  (dh.celulas || []).forEach(c => { cel[c.dia + "-" + c.faixa] = c; });
  const cor = rel => rel === null || rel === undefined ? "#fff" : rel < 0.8 ? "#FBE3D6" : rel < 1.2 ? "#F1F1EF" : rel < 1.6 ? "#D6E6F7" : "#A9CBEF";
  const casa = (c, dica) => c && c.rel !== null && c.rel !== undefined
    ? `<td style="background:${cor(c.rel)}" title="${h(dica)}">${h(setorVezes(c.rel))}<small>${h(c.n)}</small></td>`
    : `<td title="${h(dica)}">—${c && c.n ? `<small>${h(c.n)}</small>` : ""}</td>`;
  const linhas = [1, 2, 3, 4, 5, 6, 7].map(d => `<tr><th>${SETOR_DIAS[d]}</th>${SETOR_FAIXAS.map((f, i) => { const c = cel[d + "-" + i];
      return casa(c, `${SETOR_DIAS[d]}, ${f}: ${c ? c.n : 0} publicação(ões)${c && c.rel !== null && c.rel !== undefined ? ", " + setorVezes(c.rel) + " o típico de cada conta" : " (menos de 5: sem conclusão)"}`); }).join("")}
    ${(() => { const x = (dh.dias || []).find(z => z.dia === d); return casa(x, `${SETOR_DIAS[d]}: ${x ? x.n : 0} publicação(ões)`); })()}</tr>`).join("");
  const rodape = `<tr><th>todos</th>${SETOR_FAIXAS.map((f, i) => { const x = (dh.faixas || []).find(z => z.faixa === i); return casa(x, `${f}: ${x ? x.n : 0} publicação(ões)`); }).join("")}<td></td></tr>`;
  return `<div class="painel" id="setor-dias-horas"><h2>Melhores dias e horários (Brasília)</h2>
    <p class="sub">Cada publicação comparada com o engajamento típico da própria conta: 1,3× = 30% acima do normal daquela conta. Com menos de 5 publicações na casa, “—”. A diferença costuma ser pequena; formato e tema pesam mais.</p>
    <div class="rolagem"><table class="setor-mapa"><tr><th></th>${SETOR_FAIXAS.map(f => `<th>${f}</th>`).join("")}<th>dia todo</th></tr>${linhas}${rodape}</table></div>
    <div class="setor-legenda"><span><span class="setor-chave" style="background:#FBE3D6"></span>abaixo de 0,8×</span><span><span class="setor-chave" style="background:#F1F1EF"></span>0,8× a 1,2× (o normal)</span>
      <span><span class="setor-chave" style="background:#D6E6F7"></span>1,2× a 1,6×</span><span><span class="setor-chave" style="background:#A9CBEF"></span>1,6× ou mais</span></div></div>`;
}

/* temas mais frequentes: a parcela das publicações do setor (barra), a da Artecon (marca) e o engajamento relativo */
function setorTemas(p){
  const ts = (p.temas || []).filter(t => t.n > 0 || t.artecon_pct > 0);
  if(!ts.length) return "";
  const maior = Math.max(1, ...ts.map(t => Number(t.pct) || 0), ...ts.map(t => Number(t.artecon_pct) || 0));
  return `<div class="painel" id="setor-temas"><h2>Temas mais frequentes</h2>
    <p class="sub">Classificação automática por palavras (pode errar); uma publicação pode ter mais de um tema. “1,1× o típico”: o engajamento das publicações do tema comparado com o normal de cada conta.${p.artecon ? " A marca escura é a Artecon." : ""}</p>
    ${ts.map(t => `<div class="setor-barra-linha tema"><span class="setor-rotulo" title="${h(t.tema)}">${h(t.tema)}</span>
      <span class="setor-trilho"><span class="setor-barra" style="width:${Number(t.pct) / maior * 100}%;background:${SETOR_AZUL}" title="${h(`${t.tema}: ${t.n} publicação(ões) do setor (${setorNum(t.pct, 0)}%)`)}"></span>${p.artecon && t.artecon_pct !== null && t.artecon_pct !== undefined ? `<span class="setor-marca" style="left:${Number(t.artecon_pct) / maior * 100}%" title="${h(`Artecon: ${setorNum(t.artecon_pct, 0)}%`)}"></span>` : ""}</span>
      <span class="setor-valor">${h(setorNum(t.pct, 0))}%${p.artecon ? ` · Artecon ${h(setorNum(t.artecon_pct, 0))}%` : ""}${t.rel !== null && t.rel !== undefined ? ` · ${h(setorVezes(t.rel))} o típico` : ""}</span></div>`).join("")}</div>`;
}

/* as publicações de maior engajamento: o link do Instagram e um trecho curto (nunca a legenda inteira, nunca a imagem) */
function setorPostHtml(x){
  return `<li><b>@${h(x.conta)}</b> · ${h(setorDataPost(x.data))} · ${h(SETOR_FORMATOS[x.formato] || x.formato)}${Array.isArray(x.temas) && x.temas.length ? " · " + h(x.temas.join(", ")) : ""}
    · ${h(setorInteiro(x.curtidas))} curtidas · ${h(setorInteiro(x.comentarios))} comentários · <b>${h(setorPct(x.engajamento))}</b>${x.rel !== null && x.rel !== undefined ? ` <span class="sub">(${h(setorVezes(x.rel))} o típico da conta)</span>` : ""}
    ${x.trecho ? `<q>${h(x.trecho)}</q>` : ""}${setorLink(x.link)}</li>`;
}
function setorMelhores(p){
  const m = p.melhores || [], a = p.melhores_artecon || [];
  if(!m.length && !a.length) return "";
  return `<div class="painel" id="setor-melhores"><h2>Publicações de maior engajamento</h2>
    <p class="sub">${SETOR_ETICA} No máximo 3 por conta; só um trecho do começo da legenda — o resto, no Instagram.</p>
    <ol class="setor-melhores">${m.map(setorPostHtml).join("")}</ol>
    ${a.length ? `<h3>As melhores da Artecon</h3><ol class="setor-melhores" id="setor-melhores-artecon">${a.map(setorPostHtml).join("")}</ol>` : ""}</div>`;
}

/* a tabela por conta (a situação de cada uma, com a recusa da Meta em português) */
function setorTabelaContas(p){
  const cs = p?.contas || [];
  if(!cs.length) return "";
  const mini = f => { const t = ["reel", "carrossel", "foto", "video"].reduce((s, k) => s + (Number(f?.[k]) || 0), 0);
    return t ? `<span class="setor-mini" title="${h(["reel", "carrossel", "foto", "video"].filter(k => f[k]).map(k => `${SETOR_FORMATOS[k]} ${f[k]}`).join(" · "))}">${["reel", "carrossel", "foto", "video"].filter(k => f[k]).map(k =>
      `<span style="flex:${f[k]} 1 0;background:${SETOR_CORES[k]}"></span>`).join("")}</span><span class="sub">${h(["reel", "carrossel", "foto", "video"].filter(k => f[k]).map(k => `${SETOR_FORMATOS[k]} ${f[k]}`).join(" · "))}</span>` : "—"; };
  const situacao = c => { const [rot, tipo] = SETOR_SITUACOES[c.situacao] || [c.situacao, "neutro"];
    return selo(rot, tipo) + (c.erro ? `<div class="sub setor-erro">${h(c.erro)}</div>` : "") + (c.falhas >= 3 && c.ativa ? `<div class="sub">fora da leitura automática (3 falhas seguidas)${ehAdmin() ? ": use “Retomar” em Gerenciar o setor" : ""}</div>` : "")
      + (c.truncado ? `<div class="sub">as publicações lidas cobrem só ${h(c.dias_cobertos)} dias do período</div>` : "")
      + (c.coletada_em && c.dias_cobertos == null ? `<div class="sub">nenhuma leitura neste período (fica fora das medianas)</div>` : ""); };
  return `<div class="painel" id="setor-contas"><h2>Por conta</h2><div class="rolagem"><table>
    <tr><th>Conta</th><th>Seguidores</th><th>Publicações por semana</th><th>Formatos</th><th>Engajamento típico</th><th>Tema mais frequente</th><th>Lida em</th><th>Situação</th></tr>
    ${cs.map(c => `<tr data-conta="${h(c.nome)}"><td>${setorPerfil(c.nome)}${c.propria ? " " + selo("Artecon") : ""}</td><td class="num">${h(setorInteiro(c.seguidores))}</td>
      <td class="num">${h(setorNum(c.posts_semana))}</td><td>${mini(c.formatos)}</td><td class="num">${h(setorPct(c.engajamento))}</td><td>${h(c.tema_top || "—")}</td>
      <td>${h(setorQuando(c.coletada_em))}</td><td>${situacao(c)}</td></tr>`).join("")}</table></div></div>`;
}

/* a busca por hashtag: desligada até a Meta aprovar o recurso Instagram Public Content Access */
function setorHashtags(p, cfg, contas){
  const hs = p?.hashtags || [];
  if(!cfg.hashtag_ligada){
    const cadastradas = hs.length ? hs : contas.filter(c => c.tipo === "hashtag");
    return `<div class="painel" id="setor-hashtag"><h2>Busca por hashtag</h2>
      <div class="aviso info"><b>Aguardando a aprovação da Meta</b> (recurso Instagram Public Content Access). Enquanto isso, a análise usa só as contas escolhidas.${ehAdmin()
        ? " Passo a passo no LEIAME, “Busca por hashtag: pedir a aprovação da Meta”. Quando a Meta aprovar, ligue a busca em Gerenciar o setor → Configuração." : ""}</div>
      ${cadastradas.length ? `<p class="sub">Hashtags cadastradas, esperando a aprovação: ${cadastradas.map(x => "#" + h(x.nome)).join(", ")}</p>` : ""}</div>`;
  }
  return `<div class="painel" id="setor-hashtag"><h2>Busca por hashtag</h2>
    ${hs.length ? hs.map(x => `<div class="setor-hashtag-item"><h3>#${h(x.nome)}</h3>${x.erro ? `<div class="aviso erro">${h(x.erro)}</div>` : ""}
      <p>${h(x.n)} publicação(ões) no período${x.n ? ` · ${Object.entries(x.formatos || {}).map(([k, n]) => `${h(SETOR_FORMATOS[k] || k)} ${h(n)}`).join(" · ")} · interações típicas (curtidas + comentários): ${h(setorNum(x.interacoes_mediana, 0))}${(x.temas || []).length ? ` · temas: ${h(x.temas.join(", "))}` : ""}` : ""}
      <span class="sub">(lida em ${h(setorQuando(x.coletada_em))})</span></p>
      ${(x.melhores || []).length ? `<ol class="setor-melhores">${x.melhores.map(m => `<li>${h(setorDataPost(m.data))} · ${h(SETOR_FORMATOS[m.formato] || m.formato)} · ${h(setorInteiro(m.interacoes))} interações${m.trecho ? `<q>${h(m.trecho)}</q>` : ""}${setorLink(m.link)}</li>`).join("")}</ol>` : ""}</div>`).join("")
      : `<p class="sub">Nenhuma hashtag neste setor.${ehAdmin() ? " Inclua em Gerenciar o setor (#hashtag, uma por linha)." : ""}</p>`}
    <p class="sub">Sem os seguidores de quem postou (a Meta não informa), o número é absoluto. ${SETOR_ETICA}</p></div>`;
}

function setorComoLer(){
  return `<details class="painel" id="setor-como-ler"><summary>Como ler este painel</summary><ul>
    <li><b>Publicações por semana</b>: quantas publicações a conta fez no período, por semana. Lemos até 50 publicações por conta; quando elas não chegam ao começo do período, a conta vale só no trecho que cobrem.</li>
    <li><b>Engajamento por publicação</b>: (curtidas + comentários) ÷ seguidores. O número da conta é a mediana das publicações (uma publicação que viralizou não distorce); o do setor é a mediana das contas com pelo menos 100 seguidores e 5 publicações, sem a Artecon. Curtidas ocultas pelo dono ficam de fora.</li>
    <li><b>Dias e horários</b>: cada publicação é comparada com o normal da própria conta, para conta grande não engolir as pequenas.</li>
    <li><b>Temas</b>: por palavras (sem IA), editáveis pelo administrador; erram às vezes.</li>
    <li><b>O que a Meta não mostra</b> das outras contas: alcance, salvamentos, compartilhamentos, visualizações e stories. Curtidas podem vir de anúncio pago ou de seguidores comprados: compare formatos e temas, não escritórios.</li>
    <li>${SETOR_ETICA} Não reproduza texto, arte ou roteiro de outro escritório e não cite nem compare escritórios nos posts.</li></ul></details>`;
}

/* ----------------------------------------------- o quadro do administrador */
function setorFormNovo(primeiro){
  return `<form class="painel" data-form="setorNovo" id="setor-novo"><h2>${primeiro ? "Comece criando o setor" : "Novo setor"}</h2>
    <p class="sub">Um setor é um grupo de contas para comparar (por exemplo, escritórios de contabilidade). Ele começa com os temas de contabilidade, que você ajusta depois.</p>
    <label for="setor-novo-nome">Nome do setor</label><input type="text" id="setor-novo-nome" name="nome" value="${primeiro ? "Contabilidade" : ""}" maxlength="60" required>
    <div class="acoes"><button class="btn">Criar o setor</button>${primeiro ? "" : `<button class="btn sec" type="button" data-acao="setor-novo">Cancelar</button>`}</div></form>`;
}
const setorTemasTexto = lista => lista.map(t => `${t[0]}: ${t[1]}`).join("\n");
function setorGerir(setor, contas, cfg){
  if(!SETOR_E.gerir){
    return `<div class="acoes"><button type="button" class="btn sec" data-acao="setor-gerir" id="setor-gerir-abrir">Gerenciar o setor (contas, temas e configuração)</button></div>`;
  }
  const temas = Array.isArray(setor.temas) ? setor.temas.map(t => [t.nome, (t.termos || []).join(", ")]) : [];
  const linhaConta = c => `<tr data-conta-id="${h(c.id)}"><td>${c.tipo === "hashtag" ? "#" + h(c.nome) : setorPerfil(c.nome)}${c.propria ? " " + selo("Artecon") : ""}</td>
    <td>${c.ativa ? (c.erro ? selo("erro", "erro") + `<div class="sub">${h(c.erro)}</div>` : c.coletada_em ? selo("lida", "ok") : selo("esperando a leitura", "alerta"))
                  : selo("pausada", "neutro")}${c.ativa && c.falhas_consecutivas >= 3 ? `<div class="sub">fora da leitura automática (3 falhas seguidas)</div>` : ""}${c.aviso ? `<div class="sub">${h(c.aviso)}</div>` : ""}</td>
    <td class="acoes">${c.ativa && c.falhas_consecutivas < 3 ? `<button type="button" class="btn peq sec" data-acao="setor-conta-pausar" data-id="${h(c.id)}">Pausar</button>`
                  : `<button type="button" class="btn peq sec" data-acao="setor-conta-retomar" data-id="${h(c.id)}">Retomar</button>`}
      <button type="button" class="btn peq perigo" data-acao="setor-conta-remover" data-id="${h(c.id)}" data-nome="${h((c.tipo === "hashtag" ? "#" : "@") + c.nome)}">Remover</button></td></tr>`;
  return `<div class="painel setor-gerir" id="setor-gerir"><h2>Gerenciar o setor “${h(setor.nome)}”</h2>
    <button type="button" class="btn peq sec" data-acao="setor-gerir">Fechar</button>
    <form data-form="setorRenomear" data-id="${h(setor.id)}"><h3>Nome</h3>
      <div class="grade"><div><label for="setor-nome">Nome do setor</label><input type="text" id="setor-nome" name="nome" value="${h(setor.nome)}" maxlength="60" required></div>
      <div><label><input type="checkbox" name="ativo"${setor.ativo ? " checked" : ""}> Setor ativo (inativo: não é lido)</label></div></div>
      <div class="acoes"><button class="btn">Salvar</button><button type="button" class="btn perigo" data-acao="setor-apagar" data-id="${h(setor.id)}" data-nome="${h(setor.nome)}" data-contas="${h(contas.length)}">Apagar o setor</button></div></form>
    <h3>Contas e hashtags (${h(contas.filter(c => c.tipo === "conta").length)} de 30 contas)</h3>
    ${contas.length ? `<div class="rolagem"><table id="setor-lista-contas"><tr><th>Conta</th><th>Situação</th><th></th></tr>${contas.map(linhaConta).join("")}</table></div>` : `<p class="sub">Nenhuma conta ainda.</p>`}
    <form data-form="setorContas" data-id="${h(setor.id)}"><label for="setor-incluir">Incluir contas (uma por linha: @usuario, o link do perfil ou #hashtag)</label>
      <textarea id="setor-incluir" name="texto" placeholder="@escritorio.exemplo&#10;https://www.instagram.com/outro.escritorio/&#10;#contabilidade"></textarea>
      <p class="sub">Só contas públicas comerciais ou de criador — de preferência de empresas (escritórios). Até 30 por setor e 60 no Radar.</p>
      <div class="acoes"><button class="btn">Incluir</button><button type="button" class="btn sec" data-acao="setor-incluir-artecon" data-id="${h(setor.id)}">Incluir a conta da Artecon</button></div></form>
    <form data-form="setorTemas" data-id="${h(setor.id)}"><h3>Temas</h3>
      <label for="setor-temas-texto">Um tema por linha: o nome, dois-pontos e as palavras separadas por vírgula</label>
      <textarea id="setor-temas-texto" name="temas" rows="10">${h(setorTemasTexto(temas))}</textarea>
      <p class="sub">A palavra casa inteira, sem diferença de maiúsculas e acentos; a hashtag casa com a palavra sem espaços (#impostoderenda = “imposto de renda”). Ao salvar, as publicações já lidas são classificadas de novo.</p>
      <div class="acoes"><button class="btn">Salvar os temas</button><button type="button" class="btn sec" data-acao="setor-temas-padrao">Voltar aos temas padrão de contabilidade</button></div></form>
    <form data-form="setorConfig"><h3>Configuração (vale para todos os setores)</h3>
      <label><input type="checkbox" name="coleta_ligada"${cfg.coleta_ligada !== false ? " checked" : ""}> Leitura automática toda segunda-feira</label>
      <label><input type="checkbox" name="hashtag_ligada"${cfg.hashtag_ligada ? " checked" : ""}> Busca por hashtag ligada (só depois que a Meta aprovar)</label>
      <div class="grade"><div><label for="setor-posts">Publicações lidas por conta (10 a 50)</label><input type="number" id="setor-posts" name="posts_por_conta" min="10" max="50" value="${h(cfg.posts_por_conta ?? 50)}"></div>
      <div><label for="setor-modo">Publicações da hashtag</label><select id="setor-modo" name="hashtag_modo">${[["top", "As mais populares"], ["recentes", "As mais recentes"], ["ambos", "As duas"]].map(([v, r]) =>
        `<option value="${v}"${cfg.hashtag_modo === v ? " selected" : ""}>${r}</option>`).join("")}</select></div></div>
      <div class="acoes"><button class="btn">Salvar a configuração</button></div></form></div>`;
}

/* lê o texto dos temas ("Nome: palavra, palavra") e devolve a lista, ou a mensagem do erro (com o número da linha) */
function setorLerTemas(texto){
  const lista = [];
  const linhas = String(texto || "").split(/\r?\n/);
  for(let i = 0; i < linhas.length; i++){
    const l = linhas[i].trim();
    if(!l) continue;
    const k = l.indexOf(":");
    if(k < 0) return {erro: `Linha ${i + 1}: falta o dois-pontos entre o nome do tema e as palavras.`};
    const termos = l.slice(k + 1).split(",").map(t => t.trim()).filter(Boolean);
    lista.push({nome: l.slice(0, k).trim(), termos});
  }
  return {lista};
}

/* a função radar-concorrentes: os recados de instalação em português */
function setorErroFuncao(e){
  if(e.status === 404) return new ErroApi("A função radar-concorrentes não está instalada no Supabase: veja no LEIAME, “Da v0.33.0 para a v0.34.0”.", 404);
  if(/Ação desconhecida/.test(e.message || "")) return new ErroApi("A função radar-concorrentes instalada é de uma versão anterior: faça o Deploy do index.ts desta versão (Verify JWT desligado).", e.status);
  return e;
}
const setorFuncao = (corpo, tempo = 160000) => pedir("POST", "/functions/v1/radar-concorrentes", {corpo, tempo}).catch(e => { throw setorErroFuncao(e); });

/* "Atualizar a análise": pede no banco e chama a função até ler tudo (12 contas por chamada), parando na pausa da Meta */
async function setorAtualizar(){
  const id = SETOR_E.setor;
  const pedido = await rpc("radar_setor_pedir", {p_setor: id});
  if(!pedido.pedidas){ recado("Todas as contas deste setor foram lidas nas últimas 6 horas: nada a atualizar."); return; }
  const total = pedido.pedidas;
  const progresso = t => { const x = $("#setor-progresso"); if(x) x.textContent = t; };
  let lidas = 0, erros = 0, ultimo = null, ocupada = 0;
  progresso(`Lendo as contas no Instagram… 0 de ${total} (cerca de 2 minutos a cada 12 contas; não feche esta aba)`);
  try{
    for(let volta = 0; volta < 6; volta++){
      const r = await setorFuncao({acao: "setor_coletar"});
      if(r.motivo === "em_andamento"){
        if(++ocupada > 3){ ultimo = r; break; }
        progresso("A leitura automática está rodando agora; esperando…");
        await new Promise(ok => setTimeout(ok, 20000));
        volta--;
        continue;
      }
      ultimo = r;
      if(r.motivo) break;
      lidas += r.lidas || 0; erros += r.com_erro || 0;
      progresso(`Lendo as contas no Instagram… ${Math.min(lidas + erros, total)} de ${total} (cerca de 2 minutos a cada 12 contas; não feche esta aba)`);
      if(!r.faltam || r.pausa_ate || r.geral || !((r.lidas || 0) + (r.com_erro || 0))) break;
    }
  }finally{ progresso(""); }
  await desenhar();
  if(ultimo?.motivo === "em_andamento") recado("A leitura automática está rodando agora; tente de novo em alguns minutos.", "aviso");
  else if(ultimo?.motivo === "pausa" || (ultimo?.pausa_ate && ultimo?.pausa_motivo !== "configuracao"))
    recado(`A Meta pediu uma pausa até ${setorHora(ultimo.pausa_ate)} (Brasília): ${Math.max(total - lidas - erros, 0)} conta(s) que faltam serão lidas depois disso, sozinhas.`, "aviso");
  else if(ultimo?.geral) recado(`A leitura parou: ${ultimo.geral}`, true);
  else if(ultimo?.motivo === "nada") recado(lidas ? `Análise atualizada: ${lidas} conta(s) lida(s).` : "Nada a ler agora (as contas pedidas já foram lidas).");
  else recado(`Análise atualizada: ${lidas} conta(s) lida(s)${erros ? `, ${erros} com erro (veja na tabela)` : ""}.`);
}

/* ------------------------------------------------- ações e formulários (o index.html junta) */
const SETOR = {
  // não gravam nada: navegação e mudanças só na tela
  navegacao: ["setor-escolher", "setor-dias", "setor-gerir", "setor-temas-padrao", "setor-novo"],
  acoes: {
    "setor-escolher"(el){ SETOR_E.setor = Number(el.dataset.id); return desenhar(); },
    "setor-dias"(el){ SETOR_E.dias = Number(el.dataset.dias) || 90; return desenhar(); },
    "setor-gerir"(){ SETOR_E.gerir = !SETOR_E.gerir; return desenhar().then(() => { if(SETOR_E.gerir) $("#setor-gerir")?.scrollIntoView({block: "start"}); }); },
    "setor-novo"(){ SETOR_E.novo = !SETOR_E.novo; return desenhar().then(() => $("#setor-novo-nome")?.focus()); },
    "setor-temas-padrao"(){ const t = $("#setor-temas-texto"); if(!t) return;
      if(t.value.trim() && !confirm("Trocar o que está na caixa pelos temas padrão de contabilidade? Nada é gravado até você clicar em “Salvar os temas”.")) return;
      t.value = setorTemasTexto(SETOR_TEMAS_PADRAO); t.focus(); },
    "setor-atualizar"(){ return setorAtualizar(); },
    async "setor-incluir-artecon"(el){
      const r = await setorFuncao({acao: "setor_propria"}, 60000);
      const x = await rpc("radar_setor_conta_incluir", {p_setor: Number(el.dataset.id), p_texto: "@" + r.usuario});
      await desenhar();
      recado(x.contas ? `A conta da Artecon (@${r.usuario}) foi incluída: ela entra na próxima leitura.` : `A conta da Artecon (@${r.usuario}) já está neste setor.`);
    },
    async "setor-conta-pausar"(el){ await rpc("radar_setor_conta_mudar", {p_id: Number(el.dataset.id), p_ativa: false}); await desenhar(); recado("Conta pausada: ela não é lida até você retomar."); },
    async "setor-conta-retomar"(el){ await rpc("radar_setor_conta_mudar", {p_id: Number(el.dataset.id), p_ativa: true}); await desenhar(); recado("Conta retomada: ela entra na próxima leitura."); },
    async "setor-conta-remover"(el){
      if(!confirm(`Tirar ${el.dataset.nome} deste setor? As publicações lidas dela saem junto.`)) return;
      await rpc("radar_setor_conta_remover", {p_id: Number(el.dataset.id)}); await desenhar(); recado("Conta removida.");
    },
    async "setor-apagar"(el){
      if(!confirm(`Apagar o setor “${el.dataset.nome}”? ${el.dataset.contas} conta(s) e as publicações lidas delas saem junto. Não dá para desfazer.`)) return;
      await rpc("radar_setor_apagar", {p_id: Number(el.dataset.id)});
      SETOR_E.setor = null; SETOR_E.gerir = false; await desenhar(); recado("Setor apagado.");
    }
  },
  forms: {
    async setorNovo(f){
      const id = await rpc("radar_setor_salvar", {p_id: null, p_nome: f.nome.value.trim(), p_temas: null, p_ativo: true});
      SETOR_E.setor = Number(id); SETOR_E.novo = false; SETOR_E.gerir = true;
      await desenhar();
      recado("Setor criado. Agora inclua as contas (uma por linha) e clique em “Atualizar a análise”.");
    },
    async setorRenomear(f){
      await rpc("radar_setor_salvar", {p_id: Number(f.dataset.id), p_nome: f.nome.value.trim(), p_temas: null, p_ativo: f.ativo.checked});
      await desenhar(); recado("Setor salvo.");
    },
    async setorContas(f){
      const r = await rpc("radar_setor_conta_incluir", {p_setor: Number(f.dataset.id), p_texto: f.texto.value});
      await desenhar();
      const partes = [];
      if(r.contas) partes.push(`${r.contas} conta${r.contas > 1 ? "s" : ""}`);
      if(r.hashtags) partes.push(`${r.hashtags} hashtag${r.hashtags > 1 ? "s" : ""}`);
      let msg = partes.length ? `${partes.join(" e ")} incluída${r.contas + r.hashtags > 1 ? "s" : ""}` : "Nada novo incluído";
      if(r.repetidas) msg += `; ${r.repetidas} já estava${r.repetidas > 1 ? "m" : ""} no setor`;
      if((r.invalidas || []).length) msg += `; não reconheci ${r.invalidas.length > 1 ? "os itens" : "o item"} ${r.invalidas.map(n => n + "º").join(", ").replace(/, ([^,]*)$/, " e $1")} (use @usuario, o link do perfil ou #hashtag)`;
      recado(msg + ".", (r.invalidas || []).length ? "aviso" : false);
      if(!(r.invalidas || []).length && $("#setor-incluir")) $("#setor-incluir").value = "";
      else if($("#setor-incluir")) $("#setor-incluir").value = f.texto.value;
    },
    async setorTemas(f){
      const r = setorLerTemas(f.temas.value);
      if(r.erro){ recado(r.erro, true); return; }
      await rpc("radar_setor_salvar", {p_id: Number(f.dataset.id), p_nome: null, p_temas: r.lista, p_ativo: null});
      await desenhar(); recado("Temas salvos: as publicações já lidas foram classificadas de novo.");
    },
    async setorConfig(f){
      const n = Number(f.posts_por_conta.value);
      if(!Number.isInteger(n) || n < 10 || n > 50){ recado("Publicações por conta: um número inteiro de 10 a 50.", true); return; }
      await rpc("radar_setor_configurar", {p_valor: {coleta_ligada: f.coleta_ligada.checked, hashtag_ligada: f.hashtag_ligada.checked,
                                                     hashtag_modo: f.hashtag_modo.value, posts_por_conta: n}});
      await desenhar(); recado("Configuração salva.");
    }
  }
};
