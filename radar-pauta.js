"use strict";
/* ====================================================================
   RADAR ARTECON — aba Pauta (v0.21.0)
   O calendário de publicações nas redes: a semana, a importação do calendário (CSV do plano), cada peça (fotos, quem aparece,
   informações conferidas, textos e legendas), o Gerar com IA da peça (a sugestão da função radar-ia, ação "peca", com o nome na peça no
   lugar de {PESSOA1}), a arte da peça (desenharPeca: as lâminas 1080×1350 com a faixa legal), a conferência,
   a aprovação (agendar ou publicar à mão), a publicação (Publicar agora, Tentar de novo, Desfazer aprovação; à mão: baixar as
   lâminas, copiar a legenda e o roteiro e registrar o link) e as pessoas com o termo de uso de imagem.
   Carregado ANTES do script principal (index.html): aqui só há declarações e o objeto PAUTA ({acoes, forms, navegacao}), que o
   script principal junta aos dele. Nada roda no carregamento: as funções usam os globais do script principal (h, ler, rest, rpc,
   selo, recado, desenhar, E, calcularAgenda, reduzirImagemDe, crcFormatado, linhaIdentificacao, comporLegenda…) só quando são
   chamadas. Quem trava de verdade é o banco (radar_fn_pauta_peca e as funções radar_pauta_*): a tela ajuda e mostra (os termos da
   publicidade, que só a tela confere, travam na aprovação e na cópia).
   v0.22.0: na peça reel, o quadro do corretor de vídeo (radar-video.js: blocoVideo), a aprovação amarrada ao vídeo que o administrador
   viu (videoParaAprovar, p_video_sha256, as caixas "video" e "viu"), "Baixar o vídeo aprovado" e, em Pessoas e termos, o termo do
   corretor, "quer ver a peça" e menor de idade, com as peças publicadas de quem revogou o termo ou ficou inativa.
   v0.27.0: no alto da semana, o cronograma de publicações (blocoCronograma): o mínimo (o plano da Pauta e as notícias de alta que a
   busca achou) ao lado do feito, na semana e no mês dela; só lê e conta números.
   v0.28.0: "+ Nova peça" nos dias da semana sem peça (de hoje em diante, só o administrador: formNovaPeca e radar_pauta_criar, que nasce
   planejada e não publica nem agenda nada) e, em Pessoas e termos, a marca "Sócio(a) da Artecon" (só o administrador marca).
   v0.46.0: o termo de uso de imagem vira uma ASSINATURA de verdade na tela (assinarTermo: CPF + a assinatura desenhada com a caneta/dedo,
   guardada como prova em radar_pessoas_termos). TODOS assinam, sócios inclusive — não há mais dispensa; o selo volta a ser só "termo ok".
   v0.28.1: a trava da peça (estadoPeca) conta as informações conferidas e os cartões como o Salvar os grava (a linha em branco não
   conta), o aviso diz o que mudou e não foi salvo (avisoPecaSuja) e o Salvar sem nada a gravar destrava a peça.
   v0.29.0: só a versão e o recado do banco (o setup da v0.29.0): os lembretes por e-mail ficam em Configurações (index.html).
   v0.30.0: a agenda da semana (agendaDaSemana) vai até o domingo seguinte, e o vencimento prorrogado pelo administrador leva a fonte do
   ato da prorrogação; a versão e o recado do banco (o setup da v0.30.0). O 13º, as anuais e o aviso de prorrogação ficam no
   index.html (Configurações, Painel e Informativo).
   v0.31.0: só a versão e o recado do banco (o setup da v0.31.0); a versão traz as fontes oficiais que faltavam (robô).
   v0.34.0: só a versão e o recado do banco (o setup então em uso); a aba Vídeo fica em radar-video.js e a aba Setor em
   Configurações (index.html).
   v0.36.0: só a versão e o recado do banco (o setup então em uso); a correção avulsa fica na aba Vídeo (radar-video.js).
   v0.42.0: o carrossel (e o carrossel de fotos) também sai pela agenda — "Agendar" deixa de ser só da imagem única (blocoAprovar);
   quem publica as lâminas na Meta é a função radar-redes v0.42.0, e o banco (radar_pauta_aprovar) confere tudo como antes. Só o
   reel continua saindo à mão. As lâminas da notícia em carrossel (tela do assunto) são desenhadas por desenharPeca daqui.
   v0.43.0: só a versão e o recado do banco. A nova tentativa automática (a Meta recusou → o Radar marca outra tentativa, 5 e
   depois 15 minutos; na 3ª recusa, só à mão) é do banco (radar_rede_concluir, radar_agenda_vencidas) e da radar-redes v0.43.0;
   a hora marcada chega na própria mensagem de erro, que o quadro de andamento já mostra.
   v0.44.0: só a versão e o recado do banco. O teleprompter com gravação pelo navegador fica em radar-video.js (o quadro do reel
   desta peça); as letras grandes, no index.html.
   ==================================================================== */
const PAUTA_VERSAO = "0.49.0";        // igual à VERSAO do index.html; diferente, um dos dois ficou guardado no navegador (Ctrl+F5)

const TIPOS_PAUTA = {noticia:"Notícia do Radar", reel:"Reel da semana", quem_cuida:"Série Quem cuida", agenda:"Agenda da semana",
  bastidor:"Bastidor", educativo:"Educativo", captacao:"Captação", data_equipe:"Data com a equipe", sem_post:"Sem post no feed"};
const FORMATOS_PAUTA = {imagem:"Imagem 4:5", foto:"Foto", carrossel:"Carrossel", carrossel_fotos:"Carrossel de fotos", reel:"Reel", story:"Story", nenhum:"—"};
const SITUACOES_PAUTA = {planejada:"Planejada", em_producao:"Em produção", pronta:"Pronta", aprovada:"Aprovada", cancelada:"Cancelada"};
const CATEGORIAS_PESSOA = {"":"Sem registro no CRC", contador:"Contador", contadora:"Contadora", tecnico:"Técnico em contabilidade", tecnica:"Técnica em contabilidade"};
const ROTULO_CATEGORIA = {contador:"contador", contadora:"contadora", tecnico:"técnico em contabilidade", tecnica:"técnica em contabilidade"};
const USOS_TERMO = {equipe:"Apresentar a equipe", orientacao:"Orientação", datas:"Datas da empresa", captacao:"Captação de clientes"};
const DIAS_CURTOS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const RECADO_HEIC = "Foto do iPhone em HEIC: no celular, Ajustes → Câmera → Formatos → Mais compatível; ou envie por captura de tela";

/* ------------------------------------------------------------ datas (de Brasília) */
// "Hoje" é sempre o dia de Brasília, como no banco (radar_pauta_hoje), e não o do fuso do aparelho
const hojeBrasilia = () => new Date().toLocaleDateString("en-CA", {timeZone:"America/Sao_Paulo"});
const somarDias = (iso, n) => isoDia(new Date(Date.parse(iso + "T12:00:00Z") + n * 864e5));
const diaDaSemana = iso => new Date(iso + "T12:00:00Z").getUTCDay();
const segundaDe = iso => somarDias(iso, -((diaDaSemana(iso) + 6) % 7));       // a semana da Pauta começa na segunda
const dataCurta = iso => `${DIAS_CURTOS[diaDaSemana(iso)]}, ${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const horaBrasilia = v => { const d = new Date(v || ""); return isNaN(d) ? "—"
  : d.toLocaleString("pt-BR", {timeZone:"America/Sao_Paulo", day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"}).replace(",", ""); };
const cortarPauta = (t, n) => { const s = String(t || "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s; };

/* -------------------------------------------- Configurações lidas ao entrar na aba */
// assinatura (identificação legal), pauta (agenda, hora padrão, janela e hashtags), obrigacoes e feriados_extras (agenda de domingo);
// v0.27.0: relevancia (o dias_baixa, para o cronograma)
let CONF_PAUTA = {};
async function lerConfPauta(){
  CONF_PAUTA = Object.fromEntries((await ler("radar_config", {select:"chave,valor", chave:"in.(assinatura,pauta,obrigacoes,feriados_extras,corretor_video,relevancia)"})).map(c => [c.chave, c.valor]));
  const ident = CONF_PAUTA.assinatura;
  E.identificacao = ident && typeof ident === "object" && !Array.isArray(ident) ? ident : null;
}
const hashtagsPauta = () => (Array.isArray(CONF_PAUTA.pauta?.hashtags) ? CONF_PAUTA.pauta.hashtags : []).map(textoDe).filter(x => /^#[\p{L}\p{N}_]+$/u.test(x)).slice(0, 3);
// o banco ainda é o da v0.20.0 (a tabela da Pauta não existe): a tela diz o que falta em vez do erro cru do PostgREST
// (v0.22.0: as colunas novas de radar_pessoas também dizem que o banco é de antes)
const semTabelaDaPauta = e => e.status === 404 || /radar_pauta_pecas|radar_pessoas|radar_v_pauta_pessoas|peca_id/.test(e.message || "");
// (v0.28.0: também a coluna socio de radar_pessoas e a termos_dispensados de radar_v_pauta_pessoas, do banco da v0.28.0; v0.29.0 a
// v0.32.0: o recado manda rodar o setup desta versão, que traz junto os anteriores)
const AVISO_SEM_TABELA = `<h1>Pauta</h1><div class="aviso erro" id="pauta-sem-banco">A Pauta desta versão precisa do banco da v0.32.0 (ou mais nova): o administrador roda o <b>sql/radar-setup-v0.47.0.sql</b> (Supabase → SQL Editor) e recarrega esta página.</div>`;

/* ------------------------------------------------------------------------- a aba */
async function telaPauta(){
  if(PAUTA_VERSAO !== VERSAO) return `<h1>Pauta</h1><div class="aviso erro" id="pauta-versao">Esta tela (v${h(VERSAO)}) e o arquivo da Pauta (radar-pauta.js, v${h(PAUTA_VERSAO)}) são de versões diferentes: um deles ficou guardado no navegador. Aperte Ctrl+F5 (no celular, recarregue a página).</div>`;
  // o selo de SC e as capturas (boletim pago) do último assunto aberto não vêm para a Pauta; a identificação legal é relida
  E.fontesAssunto = []; E.abrangencia = null;
  try{
    await lerConfPauta();
    if(E.pauta.peca) return await telaPeca(E.pauta.peca);
    if(E.pauta.vista === "pessoas" && podeEditar()) return await telaPessoas();
    return await telaSemana();
  }catch(e){ if(semTabelaDaPauta(e)) return AVISO_SEM_TABELA; throw e; }
}
/* Depois de desenhar (index.html, desenhar()): a peça aberta guarda o estado do formulário (para saber o que mudou) e monta as artes */
function depoisDeDesenharPauta(){
  const f = $("form[data-form=peca]"); if(f) f.dataset.original = estadoPeca(f);
  if(typeof montarArtesPeca === "function") montarArtesPeca();
  if(typeof depoisDeDesenharVideo === "function") depoisDeDesenharVideo();      // v0.22.0: a situação do vídeo do reel (radar-video.js)
}

/* "Publicada" não é situação gravada: sai dos envios (radar_redes_envios) e do registro manual; o resto é a situação da peça. A aprovada
   para a agenda com todos os canais em "Não publicar neste canal" não vai sair: o selo diz isso (não é "Aprovada") */
function seloPeca(p){
  const envios = (p.radar_redes_envios || []).filter(e => e.situacao !== "cancelado"), tem = s => envios.some(e => e.situacao === s);
  if(p.situacao === "cancelada") return selo("Cancelada", "neutro");
  if(p.situacao === "aprovada" && p.aprovado_modo === "agendar" && !envios.length) return selo("Aprovada, sem canal (não vai sair)", "alerta");
  if(p.publicado_manual_em || (envios.length && envios.every(e => e.situacao === "publicado"))) return selo("Publicada", "ok");
  if(tem("erro")) return selo("Não saiu", "erro");
  if(tem("enviando")) return selo("Publicando", "alerta");
  const agendados = envios.filter(e => e.situacao === "autorizado");
  if(agendados.some(e => new Date(e.agendado_para).getTime() < Date.now() - 20 * 60000)) return selo("Atrasada", "erro");
  if(agendados.length) return selo("Agendada " + horaBrasilia(agendados[0].agendado_para), "ok");
  if(tem("excluido")) return selo("Excluída da rede", "neutro");
  if(p.situacao === "aprovada" && p.aprovado_modo === "manual") return selo("Aprovada (à mão)", "ok");
  return selo(SITUACOES_PAUTA[p.situacao] || p.situacao, {planejada:"neutro", em_producao:"alerta", pronta:"", aprovada:"ok"}[p.situacao] ?? "neutro");
}
/* O selo do termo de uso de imagem de uma pessoa da peça (radar_v_pauta_pessoas: o banco confere no dia da peça). v0.46.0: todos assinam
   (sócios inclusive); sem a dispensa, o selo é só "termo ok" ou o motivo de erro (a coluna termos_dispensados da vista vem sempre falsa). */
function seloTermo(s){
  if(!s) return "";
  if(!s.motivo_instagram && !s.motivo_facebook) return selo("termo ok", "ok");
  const motivos = s.motivo_instagram === s.motivo_facebook ? s.motivo_instagram
    : [s.motivo_instagram ? "Instagram: " + s.motivo_instagram : "", s.motivo_facebook ? "Facebook: " + s.motivo_facebook : ""].filter(Boolean).join("; ");
  return `<span class="selo erro" title="${h(motivos)}">sem termo válido (${h(motivos)})</span>`;
}

/* ------------------------------------------- o cronograma de publicações (v0.27.0) */
// v0.27.0: no alto da semana, o mínimo e o feito da semana mostrada e do mês dela. Só lê e conta: nunca pessoas, quem aparece, fotos,
// títulos nem trechos das notícias (o boletim da ITC é pago); não grava, não publica e não cria nada. As contas são funções puras (sem
// leitura nem relógio: "hoje" vem de fora), testadas com datas fixas
const LIMITE_CRONOGRAMA = 1000;                                   // o Supabase devolve no máximo 1.000 linhas por leitura
const diaBrasilia = v => new Date(v).toLocaleDateString("en-CA", {timeZone:"America/Sao_Paulo"});
const fimDoMes = m => somarDias(somarDias(m + "-01", 31).slice(0, 7) + "-01", -1);               // m = "AAAA-MM"
// o mês do quadro: na semana de hoje, o de hoje; nas outras, o da quinta-feira (o da maior parte da semana: 26/10 a 01/11 é outubro)
const mesDoCronograma = (seg, hoje) => (hoje >= seg && hoje <= somarDias(seg, 6) ? hoje : somarDias(seg, 3)).slice(0, 7);
const periodosCronograma = (seg, hoje) => { const m = mesDoCronograma(seg, hoje);
  return {semana:{ini:seg, fim:somarDias(seg, 6)}, mes:{ini:m + "-01", fim:fimDoMes(m)}}; };
function contarCronograma(ini, fim, hoje, {pecas, noticias, antes = [], capturas, dias}){
  const no = d => d >= ini && d <= fim, passou = d => d < hoje;
  const doPeriodo = pecas.filter(p => no(p.data)), validas = doPeriodo.filter(p => p.situacao !== "cancelada");
  // vai ao feed: a conta de telaPeca (semPauta). Cada peça numa linha só: o dia de notícia em Posts, o reel em Reels, a captação na dela
  const feed = validas.filter(p => p.tipo !== "sem_post" && !["story", "nenhum"].includes(p.formato));
  const grupo = p => p.tipo === "noticia" ? "posts" : p.formato === "reel" ? "reels" : p.tipo === "captacao" ? "captacao" : "posts";
  // feita = já saiu numa rede (a regra do banco, RADAR170): registrada à mão ou com um envio publicado; a excluída da rede não conta
  const saiu = p => !!p.publicado_manual_em || (p.radar_redes_envios || []).some(e => e.situacao === "publicado");
  // a notícia do Radar nas redes: cada uma uma vez, no primeiro dia (de Brasília) em que saiu no Instagram ou no Facebook; a que já tinha
  // saído antes da faixa lida (antes: os ids) não conta de novo, e o mesmo mês dá o mesmo número em qualquer semana aberta
  const primeiro = Object.fromEntries(antes.map(id => [id, ""]));
  for(const e of noticias){ const d = diaBrasilia(e.publicado_em); if(!(primeiro[e.conteudo_id] <= d)) primeiro[e.conteudo_id] = d; }
  const nasRedes = Object.values(primeiro).filter(no).length;
  // o dia de notícia sai por Assuntos e Publicações: feito quando uma notícia saiu nas redes no período (no máximo uma por dia de notícia)
  const linha = (id, rotulo) => { const ps = feed.filter(p => grupo(p) === id), comuns = ps.filter(p => p.tipo !== "noticia");
    const vencidos = ps.filter(p => p.tipo === "noticia" && passou(p.data)).length;
    return {id, rotulo, minimo:ps.length, feito:comuns.filter(saiu).length + Math.min(ps.length - comuns.length, nasRedes),
            atraso:comuns.filter(p => passou(p.data) && !saiu(p)).length + Math.max(0, vencidos - nasRedes)}; };
  // a busca: cada fato uma vez em cada período (o assunto; sem assunto, a captura), pela captura achada no período. Não entram o texto
  // oficial colado à mão (a captura criada pela inclusão: incluída no mesmo instante em que foi capturada), a que já chegou velha e a alta
  // ignorada na triagem (decisão da equipe); a alta que desceu pela idade na fila conta, mesmo ignorada depois (o robô também ignora essa
  // sozinho, e a tela não sabe quem ignorou). Feito = já está no site, em qualquer dia
  const fatos = new Map();
  for(const c of capturas){ const d = diaBrasilia(c.capturado_em), velha = c.relevancia !== "alta";
    if(!no(d) || (c.incluido_em && Math.abs(Date.parse(c.incluido_em) - Date.parse(c.capturado_em)) < 60000)) continue;
    if(velha && c.data_publicacao && c.data_publicacao < somarDias(d, -dias)) continue;
    const ac = c.radar_assunto_capturas || [], as = ac.map(x => x.radar_assuntos).filter(Boolean);
    const chave = ac.length ? "a" + Math.min(...ac.map(x => x.assunto_id)) : "c" + c.id, f = fatos.get(chave);
    const site = as.some(a => (a.radar_conteudos || []).some(k => (k.radar_divulgacoes || []).length > 0));
    const ignorada = !velha && as.length > 0 && as.every(a => ["ignorado", "arquivado"].includes(a.status));
    fatos.set(chave, f ? {dia:f.dia < d ? f.dia : d, site:f.site || site, ignorada:f.ignorada && ignorada} : {dia:d, site, ignorada}); }
  const contam = [...fatos.values()].filter(f => f.site || !f.ignorada), cap = linha("captacao", "Captação de clientes");
  return {fase:fim < hoje ? "passou" : ini > hoje ? "futuro" : "andamento", canceladas:doPeriodo.length - validas.length,
    ignoradas:fatos.size - contam.length, semPlano:!doPeriodo.length,
    linhas:[linha("posts", "Posts no feed"), linha("reels", "Reels"), ...(cap.minimo ? [cap] : []),
      {id:"noticias", rotulo:"Notícias do Radar (alta)", minimo:contam.length, feito:contam.filter(f => f.site).length,
       atraso:contam.filter(f => !f.site && passou(f.dia)).length}]};
}
// uma leitura por tabela para a semana e o mês juntos (a faixa que cobre os dois), só com as colunas da conta
// v0.48.0: carrega os dados do cronograma (peças, publicações e capturas) para a faixa [ini, fim] — usado pela projeção do Painel
// (semana + mês) e pelo período escolhido no seletor "Período". Só leitura; devolve {dados, cortado}.
async function dadosCronograma(ini, fim){
  const limite = String(LIMITE_CRONOGRAMA);
  const desde = ini + "T00:00:00-03:00", ate = somarDias(fim, 1) + "T00:00:00-03:00";    // o dia de Brasília (-03:00 fixo, como em passouDaHora)
  // só a principal de cada fato (sem as repetições); a "baixa" só a que era alta e desceu pela idade (radar_relevancia_idade)
  const capturas = filtro => ler("radar_capturas", {select:"id,relevancia,data_publicacao,capturado_em,incluido_em:metadados->>incluido_em," +
      "radar_assunto_capturas(assunto_id,radar_assuntos(status,radar_conteudos(id,radar_divulgacoes(id))))", duplicata_de:"is.null",
    and:`(capturado_em.gte.${desde},capturado_em.lt.${ate})`, order:"id", limit:limite, ...filtro});
  const [pecas, noticias, altas, velhas] = await Promise.all([
    ler("radar_pauta_pecas", {select:"id,data,tipo,formato,situacao,publicado_manual_em,radar_redes_envios(situacao)", and:`(data.gte.${ini},data.lte.${fim})`}),
    ler("radar_redes_envios", {select:"conteudo_id,publicado_em", conteudo_id:"not.is.null", situacao:"eq.publicado",
      and:`(publicado_em.gte.${desde},publicado_em.lt.${ate})`, order:"id", limit:limite}),
    capturas({relevancia:"eq.alta"}), capturas({relevancia:"eq.baixa", relevancia_motivos:'cs.[{"antes":"alta"}]'})]);
  // das notícias que saíram nas redes na faixa, as que já tinham saído antes dela (o primeiro dia não depende da semana aberta)
  const ids = [...new Set(noticias.map(e => e.conteudo_id))];
  const antes = ids.length ? (await ler("radar_redes_envios", {select:"conteudo_id", conteudo_id:`in.(${ids.join(",")})`, situacao:"eq.publicado",
    publicado_em:`lt.${desde}`, limit:limite})).map(e => e.conteudo_id) : [];
  // a que chegou velha: dias_baixa de Configurações (o padrão do banco é 5; com 0 a idade está desligada e vale o padrão)
  const d = CONF_PAUTA.relevancia?.dias_baixa, dias = Number.isInteger(d) && d > 0 ? d : 5;
  return {dados:{pecas, noticias, antes, capturas:[...altas, ...velhas], dias},
          cortado:[noticias, antes, altas, velhas].some(l => l.length >= LIMITE_CRONOGRAMA)};
}
async function lerCronograma(seg, hoje){
  const {semana, mes} = periodosCronograma(seg, hoje);
  const ini = semana.ini < mes.ini ? semana.ini : mes.ini, fim = semana.fim > mes.fim ? semana.fim : mes.fim;
  const {dados, cortado} = await dadosCronograma(ini, fim);
  // v0.41.0 (pedido do dono): também o dia de hoje, para a projeção do Painel (as mesmas contas; hoje está sempre na faixa lida
  // quando seg é a segunda-feira da semana de hoje — o Painel chama assim)
  return {dia:contarCronograma(hoje, hoje, hoje, dados),
          semana:contarCronograma(semana.ini, semana.fim, hoje, dados), mes:contarCronograma(mes.ini, mes.fim, hoje, dados), cortado};
}
// v0.48.0 (melhoria A): o cronograma de um período escolhido (de..ate, datas ISO) para o seletor "Período" do Painel. É só um
// recorte de LEITURA — mantém todo o histórico. Devolve as contas do período (linhas, fase…) com {cortado, de, ate}, ou null se
// as datas não servem (faltando ou a inicial depois da final).
async function cronogramaPeriodo(de, ate, hoje){
  if(!de || !ate || de > ate) return null;
  const {dados, cortado} = await dadosCronograma(de, ate);
  return Object.assign(contarCronograma(de, ate, hoje, dados), {cortado, de, ate});
}
const FASES_CRONOGRAMA = {passou:"já passou", andamento:"em andamento", futuro:"ainda não começou"};
// o selo da linha: o que faltou (o período passou) ou está em atraso (em vermelho); o que ainda falta, sem atraso; o mínimo cumprido
function seloCronograma(l, fase){
  const falta = l.minimo - l.feito;
  if(l.atraso) return selo(fase === "passou" ? (l.atraso === 1 ? "faltou 1" : `faltaram ${l.atraso}`) : `${l.atraso} em atraso`, "erro");
  if(falta > 0) return selo(falta === 1 ? "falta 1" : `faltam ${falta}`, "neutro");
  return l.minimo ? selo("mínimo cumprido", "ok") : "";
}
// o quadro (c = lerCronograma; nulo, a leitura falhou e a semana aparece mesmo assim). Os textos não repetem os dos botões da barra
// ("Esta semana", "← Semana anterior"…), que os testes procuram pelo texto
function blocoCronograma(seg, hoje, c){
  const topo = `<h2>Cronograma de publicações</h2>
    <p class="sub">O mínimo de publicações e o que já foi feito, na semana mostrada e no mês dela. Em vermelho, o que já devia ter saído e não saiu. O quadro só informa: não publica nem cria nada.</p>`;
  if(!c) return `<div class="painel" id="pauta-cronograma">${topo}<div class="aviso alerta" id="pauta-cronograma-erro">Não deu para montar o cronograma agora (o mínimo e o feito). A semana abaixo está certa; recarregue a página para tentar de novo.</div></div>`;
  const {semana, mes} = periodosCronograma(seg, hoje), ddmm = iso => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`, nome = mesExtenso(mes.ini);
  const periodo = (id, titulo, k) => `<section class="crono-periodo" id="cron-${id}" data-fase="${k.fase}">
      <h3>${h(titulo)} ${selo(FASES_CRONOGRAMA[k.fase], "neutro")}</h3>
      <div class="rolagem"><table><tr><th>Publicação</th><th>Mínimo</th><th>Feito</th></tr>${k.linhas.map(l => `
        <tr data-linha="${l.id}" data-minimo="${l.minimo}" data-feito="${l.feito}" data-atraso="${l.atraso}"${l.atraso ? ` class="abaixo"` : ""}>
          <th scope="row">${h(l.rotulo)}${l.id === "noticias" ? ` <span class="sub">(achadas pela busca)</span>` : ""} ${seloCronograma(l, k.fase)}</th>
          <td>${l.minimo}</td><td>${l.feito}</td></tr>`).join("")}</table></div>
      ${k.semPlano ? `<p class="aviso alerta">Nenhuma peça no plano destes dias.</p>` : ""}
      ${k.canceladas ? `<p class="sub">${k.canceladas === 1 ? "1 peça cancelada não entra no mínimo." : `${k.canceladas} peças canceladas não entram no mínimo.`}</p>` : ""}
      ${k.ignoradas ? `<p class="sub">${k.ignoradas === 1 ? "1 notícia de alta foi ignorada na triagem e não entra no mínimo."
        : `${k.ignoradas} notícias de alta foram ignoradas na triagem e não entram no mínimo.`}</p>` : ""}
    </section>`;
  return `<div class="painel" id="pauta-cronograma">${topo}
    <div class="crono-periodos">${periodo("semana", `Semana de ${ddmm(semana.ini)} a ${ddmm(semana.fim)}`, c.semana)}${periodo("mes", nome[0].toUpperCase() + nome.slice(1), c.mes)}</div>
    ${c.cortado ? `<p class="aviso alerta">Uma das leituras chegou ao limite de 1.000 registros: algum número pode estar abaixo do real.</p>` : ""}
    <details class="crono-como"><summary>Como o quadro conta</summary><ul class="pauta-lista">
      <li><b>Mínimo:</b> as peças do plano da Pauta no período (sem as canceladas) e as notícias de relevância alta que a busca do Radar achou no período.</li>
      <li><b>Posts no feed:</b> as peças de imagem, foto ou carrossel, com os dias de notícia. Reels e captação de clientes têm linha própria; story e dia sem post não entram.</li>
      <li><b>Feito, na peça:</b> a peça já publicada no Instagram ou no Facebook (pela agenda ou registrada à mão), contada no dia dela na Pauta. A excluída da rede não conta.</li>
      <li><b>Feito, no dia de notícia:</b> uma notícia do Radar publicada no Instagram ou no Facebook no período, contada no primeiro dia em que foi publicada (a mesma notícia nas duas redes conta uma vez; no máximo uma por dia de notícia).</li>
      <li><b>Notícias do Radar (alta):</b> cada fato conta uma vez em cada período (sem as repetições), pelo dia em que o Radar achou; o fato achado de novo em outro mês (por exemplo, o texto oficial que chegou dias depois) conta nos dois. Contam também as que desceram para baixa só por ficarem velhas na fila, mesmo se forem ignoradas depois. Não entram o texto oficial colado à mão, a notícia que já chegou velha e a que a equipe ignorou na triagem enquanto ainda era alta. Feito: as que já estão no site, publicadas em qualquer dia.</li>
      <li><b>Vermelho:</b> o que já devia ter saído até ontem e não saiu. No período que já passou, é tudo o que ficou abaixo do mínimo; no que ainda não começou, nada fica vermelho.</li>
      <li>O mês é o de hoje na semana de hoje; nas outras semanas, o da maior parte da semana. Na semana e no mês em andamento, o número de notícias pode mudar durante o dia (a nota da IA chega depois da busca).</li></ul></details>
  </div>`;
}

/* --------------------------------------------------------------------- a semana */
async function telaSemana(){
  const ed = podeEditar(), adm = ehAdmin(), hoje = hojeBrasilia();
  const seg = E.pauta.semana || segundaDe(hoje), dom = somarDias(seg, 6), faixa = `(data.gte.${seg},data.lte.${dom})`;
  const minutosAtras = m => new Date(Date.now() - m * 60000).toISOString();
  // uma leitura leve (sem as imagens); os selos dos termos só para quem lê as pessoas (o leitor não vê nenhuma)
  const [pecas, termos, prontas, falhas, agenda, crono] = await Promise.all([
    ler("radar_pauta_pecas", {select:"id,data,hora,tipo,formato,assunto,situacao,pessoas,aprovado_modo,link_instagram,link_facebook,publicado_manual_em," +
      "radar_redes_envios(id,canal,situacao,agendado_para,enviado_em,erro,url,publicado_em)", and:faixa, order:"data"}),
    ed ? ler("radar_v_pauta_pessoas", {select:"peca_id,pessoa_id,nome_na_peca,motivo_instagram,motivo_facebook,termos_dispensados", and:faixa}) : [],
    adm ? ler("radar_pauta_pecas", {select:"id,data,tipo,formato", situacao:"eq.pronta", order:"data", limit:"20"}) : [],
    // "Não saíram": a mesma condição de radar_v_painel.pauta_falhas (erro; parada em "enviando" há mais de 15 min; agendada que passou da hora há mais de 20 min)
    adm ? ler("radar_redes_envios", {select:"id,peca_id,canal,situacao,agendado_para,enviado_em,erro,radar_pauta_pecas(data,tipo)", peca_id:"not.is.null",
      or:`(situacao.eq.erro,and(situacao.eq.enviando,enviado_em.lt.${minutosAtras(15)}),and(situacao.eq.autorizado,agendado_para.lt.${minutosAtras(20)}))`,
      order:"agendado_para,id", limit:"50"}) : [],
    adm ? rpc("radar_agenda_situacao").catch(() => ({})) : {}, lerCronograma(seg, hoje).catch(() => null)]);    // v0.27.0: o cronograma
  const porDia = Object.fromEntries(pecas.map(p => [p.data, p]));
  const pessoasDe = p => termos.filter(t => t.peca_id === p.id);
  // v0.28.0: o dia sem peça, de hoje em diante, ganha "+ Nova peça" para o administrador (o formulário abre no próprio dia)
  const novaAqui = d => adm && d >= hoje;
  const cartao = d => { const p = porDia[d];
    if(!p && novaAqui(d) && E.pauta.nova === d) return `<article class="pauta-dia nova${d === hoje ? " hoje" : ""}" data-dia="${d}"><h3>${dataCurta(d)}</h3>${formNovaPeca(d, hoje)}</article>`;
    if(!p) return `<article class="pauta-dia vazio${d === hoje ? " hoje" : ""}" data-dia="${d}"><h3>${dataCurta(d)}</h3><p class="sub">Sem peça neste dia.</p>${novaAqui(d)
      ? `<div class="acoes"><button class="btn peq sec" type="button" data-acao="pauta-nova" data-dia="${d}">+ Nova peça</button></div>` : ""}</article>`;
    const quem = pessoasDe(p);
    return `<article class="pauta-dia${d === hoje ? " hoje" : ""}" data-dia="${d}" data-peca="${p.id}">
      <h3>${dataCurta(d)}${p.tipo !== "noticia" && p.tipo !== "sem_post" ? ` · ${h(String(p.hora).slice(0, 5))}` : ""}</h3>
      <div class="selos">${selo(TIPOS_PAUTA[p.tipo] || p.tipo, "neutro")}${p.formato !== "nenhum" ? " " + selo(FORMATOS_PAUTA[p.formato] || p.formato, "neutro") : ""} ${seloPeca(p)}</div>
      ${p.assunto ? `<p class="sub pauta-assunto">${h(cortarPauta(p.assunto, 140))}</p>` : ""}
      ${quem.length ? `<p class="pauta-pessoas">${quem.map(t => `<span>${h(t.nome_na_peca)} ${seloTermo(t)}</span>`).join(" ")}</p>` : ""}
      ${p.tipo === "noticia" ? `<p class="sub">Dia de notícia: publique por <button class="link" type="button" data-acao="aba" data-aba="assuntos">Assuntos</button> ou <button class="link" type="button" data-acao="aba" data-aba="publicacoes">Publicações</button>.</p>` : ""}
      <div class="acoes"><button class="btn peq sec" type="button" data-acao="abrir-peca" data-id="${p.id}">Abrir</button></div></article>`; };
  const desligada = CONF_PAUTA.pauta && typeof CONF_PAUTA.pauta === "object" && CONF_PAUTA.pauta.agenda_ligada === false;
  const avisoAgenda = !adm ? "" : desligada
      ? `<div class="aviso alerta" id="agenda-desligada"><b>Agenda automática desligada</b> (Configurações → Pauta → "agenda_ligada": false): o que está agendado espera; a peça só sai se alguém clicar em Publicar agora.</div>`
    : agenda.instalada === false
      ? `<div class="aviso alerta" id="agenda-desligada"><b>Agenda automática desligada:</b> a agenda do banco não está instalada neste projeto (sql/radar-redes-agenda.sql, no Supabase → SQL Editor). As peças agendadas só saem se alguém clicar em Publicar agora.</div>`
    : agenda.instalada && agenda.ativa === false
      ? `<div class="aviso alerta" id="agenda-desligada"><b>Agenda automática pausada</b> no pg_cron (cron.job → radar-redes-agenda): as peças agendadas só saem se alguém clicar em Publicar agora.</div>` : "";
  return `<h1>Pauta</h1>
    <p class="sub">O calendário de publicações no Instagram e no Facebook: uma peça por dia. Quem prepara monta a peça e marca como pronta; o administrador aprova, e a agenda do banco publica na hora marcada (ou a peça sai à mão).</p>
    ${blocoCronograma(seg, hoje, crono)}${avisoAgenda}
    ${falhas.length ? `<div class="painel" id="pauta-falhas"><h2>Não saíram</h2><div class="rolagem"><table><tr><th>Dia</th><th>Canal</th><th>O que houve</th><th></th></tr>${falhas.map(e => `
      <tr><td style="white-space:nowrap">${e.radar_pauta_pecas ? dataCurta(e.radar_pauta_pecas.data) : "—"}</td><td>${h(NOME_REDE[e.canal] || e.canal)}</td>
        <td>${e.situacao === "erro" ? h(e.erro || "A publicação não foi concluída.") : e.situacao === "enviando" ? `Parada em “publicando” desde ${horaBrasilia(e.enviado_em)}: confira na rede se saiu.`
          : `Agendada para ${horaBrasilia(e.agendado_para)} e ainda não saiu (a agenda do banco está parada?).`}</td>
        <td><span class="acoes" style="margin:0"><button class="btn peq sec" type="button" data-acao="abrir-peca" data-id="${e.peca_id}">Abrir</button>
          ${e.situacao !== "enviando" ? botaoNaoPublicar(e) : ""}</span></td></tr>`).join("")}</table></div></div>` : ""}
    ${prontas.length ? `<div class="painel" id="pauta-prontas"><h2>Prontas para aprovar</h2><ul class="pauta-lista">${prontas.map(p => `
      <li><b>${dataCurta(p.data)}</b> · ${h(TIPOS_PAUTA[p.tipo] || p.tipo)} · ${h(FORMATOS_PAUTA[p.formato] || p.formato)} <button class="btn peq" type="button" data-acao="abrir-peca" data-id="${p.id}">Abrir</button></li>`).join("")}</ul></div>` : ""}
    ${E.pauta.previa ? blocoPreviaPauta(E.pauta.previa) : ""}
    <div class="pauta-barra"><button class="btn peq sec" type="button" data-acao="pauta-semana" data-passo="-1">← Semana anterior</button>
      <button class="btn peq sec" type="button" data-acao="pauta-semana" data-passo="0">Esta semana</button>
      <button class="btn peq sec" type="button" data-acao="pauta-semana" data-passo="1">Próxima semana →</button>
      <b id="pauta-semana-titulo">Semana de ${seg.slice(8, 10)}/${seg.slice(5, 7)} a ${dom.slice(8, 10)}/${dom.slice(5, 7)}/${dom.slice(0, 4)}</b></div>
    <div class="pauta-semana">${Array.from({length:7}, (_, i) => cartao(somarDias(seg, i))).join("")}</div>
    ${ed ? `<div class="painel pauta-ferramentas"><div class="acoes" style="margin:0"><button class="btn sec" type="button" data-acao="pauta-pessoas">Pessoas e termos</button></div>
      <label for="pauta-csv">Importar o calendário (CSV)</label><input id="pauta-csv" type="file" accept=".csv,text/csv" data-csv-pauta>
      <p class="sub" style="margin:4px 0 0">O CSV do plano de publicações, com as colunas data;dia;semana;tipo;formato;assunto;quem_aparece;objetivo;observacao. A tela confere o arquivo inteiro e mostra o que muda antes de gravar. Ele tem nomes da equipe: nunca vai para o GitHub.</p></div>` : ""}`;
}

/* v0.28.0: "+ Nova peça" num dia sem peça (só o administrador; o banco confere tudo de novo em radar_pauta_criar: o papel, o dia livre e
   não passado, de Brasília, e os campos da importação). A peça nasce planejada: abre como qualquer outra (roteiro, Quem aparece, fotos e, no
   reel, o corretor de vídeo) e nunca publica nem agenda nada sozinha */
function formNovaPeca(d, hoje){
  // "novalidate": quem confere é o formulário (forms.novaPeca), com o recado em português; o "—" do formato é dito por extenso
  return `<form class="pauta-nova" id="pauta-nova" data-form="novaPeca" data-dia="${d}" novalidate>
    <p class="sub">Peça nova para ${h(dataAgenda(d))}. Ela entra planejada: não publica nem agenda nada; sai só depois de pronta e aprovada pelo administrador.</p>
    ${d === hoje ? `<p class="sub" id="pauta-nova-hoje">É para hoje: depois de criar, confira a hora na peça (a hora padrão pode já ter passado).</p>` : ""}
    <label for="pauta-nova-tipo">Tipo</label><select id="pauta-nova-tipo" name="tipo" required>${opcoes(TIPOS_PAUTA, "", "Escolha o tipo")}</select>
    <label for="pauta-nova-formato">Formato</label><select id="pauta-nova-formato" name="formato" required>${opcoes({...FORMATOS_PAUTA, nenhum:"Nenhum (sem post no feed)"}, "", "Escolha o formato")}</select>
    <label for="pauta-nova-assunto">Assunto</label><textarea id="pauta-nova-assunto" name="assunto" rows="3" maxlength="1000" required></textarea>
    <label for="pauta-nova-objetivo">Objetivo (opcional)</label><input id="pauta-nova-objetivo" type="text" name="objetivo" maxlength="200">
    <label for="pauta-nova-quem">Quem aparece (lembrete, opcional)</label><input id="pauta-nova-quem" type="text" name="quem_aparece" maxlength="300">
    <label for="pauta-nova-observacao">Observação (opcional)</label><textarea id="pauta-nova-observacao" name="observacao" rows="2" maxlength="1000"></textarea>
    <p class="sub">Reel: escolha o formato Reel (o quadro do corretor de vídeo aparece na peça). As pessoas são marcadas depois, na própria peça, entre as cadastradas em Pessoas e termos.</p>
    <div class="acoes"><button class="btn verde">Criar a peça</button><button class="btn sec" type="button" data-acao="pauta-nova-cancelar">Cancelar</button></div>
  </form>`;
}

/* ------------------------------------------------- importar o calendário (CSV) */
const CABECALHO_PAUTA = ["data", "dia", "semana", "tipo", "formato", "assunto", "quem_aparece", "objetivo", "observacao"];
const LIMITES_PAUTA = {assunto:1000, quem_aparece:300, objetivo:200, observacao:1000};
const normalPauta = t => String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
// os rótulos do plano (sem diferença de maiúsculas e acentos) e também os nomes internos; formato "—", "-" ou vazio = nenhum
const MAPA_TIPOS_PAUTA = Object.fromEntries(Object.entries(TIPOS_PAUTA).flatMap(([k, v]) => [[normalPauta(v), k], [normalPauta(k), k]]));
const MAPA_FORMATOS_PAUTA = Object.fromEntries(Object.entries(FORMATOS_PAUTA).flatMap(([k, v]) => [[normalPauta(v), k], [normalPauta(k), k]]));
/* O texto do CSV em registros (listas de campos): ";" ou "," (o que mais aparece no cabeçalho), aspas com o separador ou quebra de
   linha dentro e "" para aspas, LF ou CRLF. "aberto": o arquivo acabou com aspas abertas. */
function registrosCsv(texto){
  const t = String(texto || "").replace(/^\uFEFF/, ""), cab = t.split(/\r?\n/, 1)[0];
  const sep = (cab.match(/;/g) || []).length >= (cab.match(/,/g) || []).length ? ";" : ",";
  const registros = []; let campo = "", linha = [], aspas = false;
  for(let i = 0; i < t.length; i++){
    const c = t[i];
    if(aspas){ if(c !== '"') campo += c; else if(t[i + 1] === '"'){ campo += '"'; i++; } else aspas = false; }
    else if(c === '"' && !campo) aspas = true;                     // aspas valem só no começo do campo
    else if(c === sep){ linha.push(campo); campo = ""; }
    else if(c === "\n" || c === "\r"){
      if(c === "\r" && t[i + 1] === "\n") i++;
      linha.push(campo); registros.push(linha); linha = []; campo = ""; }
    else campo += c;
  }
  if(campo || linha.length) { linha.push(campo); registros.push(linha); }
  return {registros, aberto:aspas};
}
/* Confere o arquivo inteiro antes de gravar e devolve TODOS os erros, com o número da linha na planilha (o cabeçalho é a linha 1).
   As linhas boas saem no formato de radar_pauta_importar. O texto não é interpretado como HTML em lugar nenhum (h() na tela). */
function analisarCsv(texto){
  const {registros, aberto} = registrosCsv(texto), erros = [], linhas = [], datas = {};
  // as colunas vazias que sobram no fim (o Excel salva ";;" quando alguma coluna depois da "observacao" foi formatada) não contam
  for(const campos of registros) while(campos.length > CABECALHO_PAUTA.length && !campos[campos.length - 1].trim()) campos.pop();
  const util = registros.map((campos, i) => ({n:i + 1, campos})).filter(r => r.campos.some(c => c.trim()));   // linha toda vazia (";;;;") não conta
  if(!util.length) return {linhas, erros:["O arquivo está vazio."]};
  if(util[0].n !== 1 || util[0].campos.map(c => c.trim().toLowerCase()).join(";") !== CABECALHO_PAUTA.join(";"))
    return {linhas, erros:[`Linha 1: o cabeçalho tem de ser exatamente ${CABECALHO_PAUTA.join(";")} (o do calendário do plano de publicações).`]};
  for(const {n, campos} of util.slice(1)){
    const erro = m => erros.push(`Linha ${n}: ${m}`);
    if(campos.length !== CABECALHO_PAUTA.length){ erro(`tem ${campos.length} coluna(s), e o calendário tem ${CABECALHO_PAUTA.length} (confira o separador e as aspas).`); continue; }
    const v = campos.map(c => c.trim()), [d, dia, , tipo, formato] = v, antes = erros.length;
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(d), iso = m ? `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}` : "";
    const dataOk = m && !isNaN(Date.parse(iso + "T12:00:00Z")) && isoDia(new Date(iso + "T12:00:00Z")) === iso && iso >= "2020-01-01" && iso <= "2100-12-31";
    if(!dataOk) erro(`data “${cortarPauta(d, 20)}” inválida (use DD/MM/AAAA, como 26/10/2026).`);
    else if(!dia) erro(`falta o dia da semana de ${d} (${DIAS_CURTOS[diaDaSemana(iso)]}).`);
    else if(normalPauta(dia).slice(0, 3) !== normalPauta(DIAS_CURTOS[diaDaSemana(iso)]))
      erro(`o dia “${cortarPauta(dia, 20)}” não bate com ${d} (${DIAS_CURTOS[diaDaSemana(iso)]}).`);
    else if(datas[iso]) erro(`a data ${d} já está na linha ${datas[iso]}.`);
    const t = MAPA_TIPOS_PAUTA[normalPauta(tipo)], f = MAPA_FORMATOS_PAUTA[normalPauta(formato)];
    if(!t) erro(`tipo “${cortarPauta(tipo, 40)}” desconhecido (os do plano: ${Object.values(TIPOS_PAUTA).join(", ")}).`);
    if(!f) erro(`formato “${cortarPauta(formato, 40)}” desconhecido (os do plano: ${Object.values(FORMATOS_PAUTA).filter(x => x !== "—").join(", ")} ou “—”).`);
    // os textos do plano: "—" ou "-" sozinho é campo vazio (como no formato)
    const textos = Object.fromEntries(["assunto", "quem_aparece", "objetivo", "observacao"].map((k, i) => [k, /^[—–-]$/.test(v[5 + i]) ? "" : v[5 + i]]));
    for(const [k, max] of Object.entries(LIMITES_PAUTA))
      if(textos[k].length > max) erro(`${k === "quem_aparece" ? "quem aparece" : k === "observacao" ? "observação" : k} com mais de ${max.toLocaleString("pt-BR")} caracteres.`);
    if(dataOk && !datas[iso]) datas[iso] = n;
    if(erros.length === antes) linhas.push({linha:n, data:iso, tipo:t, formato:f, ...textos});
  }
  if(aberto) erros.push("O arquivo termina com aspas abertas (uma aspa sem a que fecha): confira a última linha com aspas.");
  if(!linhas.length && !erros.length) erros.push("O arquivo não tem nenhuma linha do calendário, só o cabeçalho.");
  if(util.length - 1 > 400) erros.push(`O arquivo tem ${util.length - 1} linhas: importe no máximo 400 de cada vez.`);
  return {linhas, erros};
}
/* O arquivo escolhido: lê (UTF-8; se vier com caracteres trocados, como o "CSV (separado por vírgulas)" do Excel, lê como
   Windows-1252), confere tudo e compara com o que já está no Radar, sem gravar nada: a prévia aparece no alto da semana. */
async function lerCsvPauta(campo){
  const arquivo = campo.files[0]; campo.value = "";                // o mesmo arquivo pode ser escolhido de novo depois
  if(!arquivo) return;
  if(arquivo.size > 3e6) throw new ErroApi("O arquivo é grande demais para um calendário (mais de 3 MB): confira se escolheu o CSV do plano.");
  let texto = await arquivo.text();
  if(texto.includes("\uFFFD")) texto = new TextDecoder("windows-1252").decode(await arquivo.arrayBuffer());
  const r = analisarCsv(texto.replace(/^\uFEFF/, ""));
  r.nome = arquivo.name;
  if(!r.erros.length){
    // o efeito de cada linha, como o banco vai fazer: nova; mantida (a peça já saiu de "planejada" e não muda); igual; alterada
    const datas = r.linhas.map(l => l.data).sort(), CAMPOS = ["tipo", "formato", "assunto", "quem_aparece", "objetivo", "observacao"];
    const atuais = Object.fromEntries((await ler("radar_pauta_pecas", {select:"data,situacao," + CAMPOS.join(","),
      and:`(data.gte.${datas[0]},data.lte.${datas[datas.length - 1]})`, limit:"2000"})).map(p => [p.data, p]));
    for(const l of r.linhas){ const p = atuais[l.data];
      l.efeito = !p ? "nova" : p.situacao !== "planejada" ? "mantida" : CAMPOS.every(k => (p[k] || "") === l[k]) ? "igual" : "alterada"; }
  }
  E.pauta.previa = r; E.pauta.peca = null; E.pauta.vista = "semana"; E.pauta.nova = null;
  await desenhar();
  $("#pauta-previa")?.scrollIntoView({block:"start"});
}
const EFEITOS_PAUTA = {nova:"nova", alterada:"alterada", igual:"igual", mantida:"mantida (já em produção)"};
function blocoPreviaPauta(pr){
  if(pr.erros.length) return `<div class="painel" id="pauta-previa"><h2>Importar o calendário: ${h(pr.nome)}</h2>
    <div class="aviso erro"><b>O arquivo tem ${pr.erros.length} erro(s). Nada foi gravado:</b> corrija no arquivo e escolha de novo.</div>
    <ul class="pauta-erros">${pr.erros.slice(0, 100).map(e => `<li>${h(e)}</li>`).join("")}</ul>${pr.erros.length > 100 ? `<p class="sub">E mais ${pr.erros.length - 100} erro(s).</p>` : ""}
    <div class="acoes"><button class="btn sec" type="button" data-acao="pauta-importar-cancelar">Fechar</button></div></div>`;
  const n = k => pr.linhas.filter(l => l.efeito === k).length, mudam = n("nova") + n("alterada");
  return `<div class="painel" id="pauta-previa"><h2>Importar o calendário: ${h(pr.nome)}</h2>
    <p id="pauta-previa-resumo">${pr.linhas.length} linha(s): <b>${n("nova")}</b> nova(s), <b>${n("alterada")}</b> alterada(s), <b>${n("igual")}</b> igual(is) e <b>${n("mantida")}</b> mantida(s) (a peça já entrou em produção e não muda).</p>
    <p class="sub">Nada foi gravado ainda. “Quem aparece” entra só como lembrete do plano: as pessoas da peça são marcadas na própria peça, entre as cadastradas em Pessoas e termos.</p>
    <details class="pauta-linhas"${mudam && mudam <= 20 ? " open" : ""}><summary>Ver as linhas</summary><div class="rolagem"><table><tr><th>Linha</th><th>Dia</th><th>Tipo</th><th>Formato</th><th>Assunto</th><th>Efeito</th></tr>${pr.linhas.map(l => `
      <tr><td>${l.linha}</td><td style="white-space:nowrap">${dataCurta(l.data)}/${l.data.slice(0, 4)}</td><td>${h(TIPOS_PAUTA[l.tipo])}</td><td>${h(FORMATOS_PAUTA[l.formato])}</td>
        <td>${h(cortarPauta(l.assunto, 80))}</td><td>${selo(EFEITOS_PAUTA[l.efeito] || "", l.efeito === "mantida" ? "neutro" : l.efeito === "igual" ? "neutro" : "")}</td></tr>`).join("")}</table></div></details>
    <div class="acoes">${mudam ? `<button class="btn verde" type="button" data-acao="pauta-importar-gravar">Gravar ${mudam} peça(s) no Radar</button>` : `<span class="sub">Nada muda: o Radar já tem este calendário.</span>`}
      <button class="btn sec" type="button" data-acao="pauta-importar-cancelar">${mudam ? "Cancelar" : "Fechar"}</button></div></div>`;
}

/* ----------------------------------------------------------------------- a peça */
const conferidasDe = p => (Array.isArray(p.conferidas) ? p.conferidas : []).filter(c => c && typeof c === "object")
  .map(c => ({informacao:textoDe(c.informacao), fonte:textoDe(c.fonte)})).filter(c => c.informacao || c.fonte);
const cartoesDe = p => (Array.isArray(p.cartoes) ? p.cartoes : []).filter(c => c && typeof c === "object")
  .map(c => ({titulo:textoDe(c.titulo), texto:textoDe(c.texto)})).filter(c => c.titulo || c.texto);
const linhaConferida = (c, des) => `<div class="conf-linha">
    <textarea name="conf-informacao" rows="2" maxlength="300" aria-label="Informação conferida" placeholder="Informação (ex.: 10/11 (ter) · ICMS)" class="peca-arte-campo"${des}>${h(c.informacao || "")}</textarea>
    <input type="text" name="conf-fonte" maxlength="300" aria-label="Fonte da informação" placeholder="Fonte oficial" value="${h(c.fonte || "")}"${des}>
    ${des ? "" : `<button class="btn peq perigo" type="button" data-acao="peca-conf-remover" aria-label="Remover esta informação">Remover</button>`}</div>`;
/* Rodada 2 da varredura geral: a legenda do “Usar a sugestão”: o texto da IA, a linha “Fonte: …” das informações conferidas, a
   identificação legal e as hashtags, em até "limite" caracteres. A linha da fonte nunca é cortada (antes ela ia junto do texto para o
   comporLegenda, que corta o fim: com as 9 fontes da agenda de fim de mês, a citação saía quebrada, “…; LC 155/2016, art.”): quem
   encurta é o texto da IA, no fim de uma frase. Se com as fontes inteiras o texto não cabe, elas vão só com a norma, sem o endereço.
   Devolve {legenda, encurtado (o texto da IA não foi inteiro), semEndereco}. */
function legendaDaSugestao(texto, fontes, tags, limite = 2200){
  const t = String(texto || "").trim(), linha = l => l.length ? "Fonte: " + l.join("; ") : "";
  const inteira = linha(fontes), curta = linha([...new Set(fontes.map(x => String(x).replace(/\s*[—–-]?\s*https?:\/\/\S+/g, "").trim()).filter(Boolean))]);
  let legenda = comporLegenda(t, tags, limite, inteira), semEndereco = false;
  if(!legenda.startsWith(t) && curta !== inteira){ legenda = comporLegenda(t, tags, limite, curta); semEndereco = true; }
  return {legenda, encurtado:!legenda.startsWith(t), semEndereco};
}
const linhaCartao = (c, des) => `<div class="cartao-linha">
    <input type="text" name="cartao-titulo" maxlength="60" aria-label="Título do cartão" placeholder="Título do cartão" value="${h(c.titulo || "")}" class="peca-arte-campo"${des}>
    <textarea name="cartao-texto" rows="2" maxlength="300" aria-label="Texto do cartão" placeholder="Texto do cartão" class="peca-arte-campo"${des}>${h(c.texto || "")}</textarea>
    ${des ? "" : `<button class="btn peq perigo" type="button" data-acao="peca-cartao-remover" aria-label="Remover este cartão">Remover</button>`}</div>`;
/* As fotos da peça, na ordem (as miniaturas vêm de E.pauta.fotos, lido ao abrir a peça e completado a cada envio) */
function listaFotosPeca(ids, ed){
  const dados = E.pauta.fotos || {};
  return ids.length ? ids.map((id, i) => `<figure class="peca-foto" data-foto="${id}">
      ${dados[id] ? `<img src="${h(dados[id])}" alt="Foto ${i + 1} da peça">` : `<span class="sub">foto ${i + 1}</span>`}
      <figcaption class="sub">${i + 1} de ${ids.length}</figcaption>
      ${ed ? `<span class="acoes"><button class="btn peq sec" type="button" data-acao="peca-foto-mover" data-foto="${id}" data-passo="-1"${i ? "" : " disabled"} aria-label="Subir a foto ${i + 1}">↑</button>
        <button class="btn peq sec" type="button" data-acao="peca-foto-mover" data-foto="${id}" data-passo="1"${i < ids.length - 1 ? "" : " disabled"} aria-label="Descer a foto ${i + 1}">↓</button>
        <button class="btn peq perigo" type="button" data-acao="peca-foto-tirar" data-foto="${id}">Tirar</button></span>` : ""}</figure>`).join("")
    : `<p class="sub">Nenhuma foto ainda.</p>`;
}
async function telaPeca(id){
  const [p] = await ler("radar_pauta_pecas", {select:"*,radar_redes_envios(id,canal,situacao,agendado_para,enviado_em,erro,url,publicado_em,post_id)", id:"eq." + id});
  if(!p) return `<button class="voltar" data-acao="voltar">← Voltar para a semana</button><div class="aviso erro">Peça não encontrada.</div>`;
  const ed = podeEditar(), travada = ["aprovada", "cancelada"].includes(p.situacao);
  // as fotos (para preparar a peça: na aprovada, elas estão na arte) e as lâminas aprovadas (as imagens que vão ao ar), só para quem
  // edita: são a equipe, como as pessoas, que o leitor não vê; as pessoas com a categoria e o CRC (a linha da pessoa na arte)
  const [fotos, pessoas, termos, artes] = await Promise.all([
    ed && p.fotos.length && p.situacao !== "aprovada" ? ler("radar_imagens", {select:"id,dados", id:"in.(" + p.fotos.join(",") + ")"}) : [],
    ed ? ler("radar_pessoas", {select:"id,nome_na_peca,area,categoria,crc,ativo,termo_corretor_em,quer_ver_peca,menor,socio", order:"nome_na_peca,id"}) : [],
    ed && p.pessoas.length ? ler("radar_v_pauta_pessoas", {select:"pessoa_id,motivo_instagram,motivo_facebook,termos_dispensados", peca_id:"eq." + p.id}) : [],
    ed && p.artes.length ? ler("radar_imagens", {select:"id,dados", id:"in.(" + p.artes.join(",") + ")"}) : []]);
  E.pauta.fotos = Object.fromEntries(fotos.map(x => [x.id, x.dados]));
  E.pauta.pessoas = Object.fromEntries(pessoas.map(x => [x.id, x]));
  E.pauta.aprovadas = p.artes.map(a => artes.find(x => x.id === a)?.dados || "");
  E.pauta.termoFalha = termos.some(t => t.motivo_instagram || t.motivo_facebook);   // o termo de alguém não vale no dia da peça
  E.pauta.aberta = {id:p.id, data:p.data, hora:String(p.hora).slice(0, 5), tipo:p.tipo, formato:p.formato, roteiro:p.roteiro, artes:p.artes,
    arte_identificacao:p.arte_identificacao, aprovado_em:p.aprovado_em};
  E.pauta.ia = p.ia && typeof p.ia === "object" && !Array.isArray(p.ia) ? p.ia : null;       // a sugestão da IA (Gerar com IA), só para quem edita
  // v0.22.0: o reel passa pelo corretor de vídeo (radar-video.js), para quem edita; sem o arquivo, o recado
  const video = !ed || p.formato !== "reel" ? "" : typeof blocoVideo === "function" ? await blocoVideo(p)
    : `<div class="aviso erro" id="video-sem-arquivo">O arquivo radar-video.js (o corretor de vídeo) não carregou. Aperte Ctrl+F5 (no celular, recarregue a página); se continuar, avise o administrador.</div>`;
  // o que vai ao ar e a hora: travados na peça aprovada (ou cancelada) e para o leitor; o plano fica livre para quem edita
  const desAr = ed && !travada ? "" : " disabled", desPlano = ed ? "" : " disabled";
  const semPauta = p.tipo === "sem_post" || ["story", "nenhum"].includes(p.formato), vaiAoAr = !semPauta && p.tipo !== "noticia";
  const comFotos = ["foto", "carrossel_fotos"].includes(p.formato) || p.fotos.length > 0;
  const comCartoes = ["carrossel", "carrossel_fotos"].includes(p.formato) || cartoesDe(p).length > 0;
  const comRoteiro = p.formato === "reel" || !!p.roteiro;
  const erros = (p.radar_redes_envios || []).filter(e => e.situacao === "erro");
  const ativas = pessoas.filter(x => x.ativo || p.pessoas.includes(x.id)), termoDe = pid => termos.find(t => t.pessoa_id === pid);
  const legenda = k => { const v = p["legenda_" + k] || ""; return `<div class="peca-legenda"><label for="peca-legenda-${k}">Legenda do ${NOME_REDE[k]}</label>
      <textarea id="peca-legenda-${k}" name="legenda_${k}" maxlength="2200" rows="7" data-conta="conta-${k}"${desAr}>${h(v)}</textarea>
      <div class="acoes"><span class="sub" id="conta-${k}">${v.length.toLocaleString("pt-BR")}/2.200</span>
        ${desAr ? "" : `<button class="btn peq sec" type="button" data-acao="peca-completar-legenda" data-canal="${k}">Pôr a identificação legal e as hashtags</button>`}</div></div>`; };
  return `<button class="voltar" data-acao="voltar">← Voltar para a semana</button>
    <h1>Peça de ${h(dataAgenda(p.data))}</h1>
    <p class="selos-peca">${selo(TIPOS_PAUTA[p.tipo] || p.tipo)} ${selo(FORMATOS_PAUTA[p.formato] || p.formato)} <span id="peca-situacao">${seloPeca(p)}</span></p>
    ${p.situacao === "aprovada" ? `<div class="aviso info" id="peca-aprovada">A peça está aprovada: o que vai ao ar e a hora não mudam. Para mudar, use Desfazer aprovação.${ed ? " O plano (assunto, objetivo, observação e quem aparece) continua livre." : ""}</div>` : ""}
    ${p.situacao === "cancelada" ? `<div class="aviso alerta" id="peca-cancelada">Peça cancelada.${ed ? " Para voltar a trabalhar nela, clique em Reabrir." : ""}</div>` : ""}
    ${erros.map(e => `<div class="aviso erro peca-erro"><b>${h(NOME_REDE[e.canal] || e.canal)}: não saiu.</b> ${h(e.erro || "A publicação não foi concluída.")}</div>`).join("")}
    ${p.tipo === "noticia" ? `<div class="aviso info">Dia de notícia: publique por <button class="link" type="button" data-acao="aba" data-aba="assuntos">Assuntos</button> ou <button class="link" type="button" data-acao="aba" data-aba="publicacoes">Publicações</button> (o kit das redes do conteúdo).</div>` : ""}
    ${semPauta ? `<div class="aviso info">Sem publicação pela Pauta nesta versão (story ou dia sem post no feed).</div>` : ""}
    <form class="painel peca" data-form="peca" data-id="${p.id}" data-lido="${h(p.atualizado_em)}" data-data="${h(p.data)}" data-fotos="${h(JSON.stringify(p.fotos))}"
      data-pessoas="${h(JSON.stringify(p.pessoas))}" data-conferidas="${h(JSON.stringify(conferidasDe(p)))}" data-cartoes="${h(JSON.stringify(cartoesDe(p)))}"
      data-tipo="${h(p.tipo)}" data-formato="${h(p.formato)}" data-situacao="${h(p.situacao)}">
      ${vaiAoAr ? `<div class="grade">
        <div><label for="peca-hora">Hora (de Brasília)</label><input id="peca-hora" type="time" name="hora" required value="${h(String(p.hora).slice(0, 5))}"${desAr}></div>
        <div><label for="peca-tipo">Tipo</label><select id="peca-tipo" name="tipo" class="peca-arte-campo"${desAr}>${opcoes(TIPOS_PAUTA, p.tipo)}</select></div>
        <div><label for="peca-formato">Formato</label><select id="peca-formato" name="formato" class="peca-arte-campo"${desAr}>${opcoes(FORMATOS_PAUTA, p.formato)}</select></div></div>` : ""}
      ${comFotos && vaiAoAr && ed && p.situacao === "aprovada" ? `<h3>Fotos</h3><p class="sub" id="peca-fotos-na-arte">${p.fotos.length} foto(s), na arte aprovada.</p>` : ""}
      ${comFotos && vaiAoAr && ed && p.situacao !== "aprovada" ? `<h3>Fotos</h3><div class="peca-fotos" id="peca-fotos-lista">${listaFotosPeca(p.fotos, ed && !travada)}</div>
        ${desAr ? "" : `<label for="peca-foto-arquivo">Enviar fotos</label><div class="acoes" style="margin-top:0"><input id="peca-foto-arquivo" type="file" accept="image/jpeg,image/png,image/webp" multiple data-foto-peca="${p.id}">
          <span class="sub" id="peca-fotos-andamento" role="status" aria-live="polite"></span></div>
          <p class="sub">JPG, PNG ou WebP, até 10 por peça. Cada foto vai em 1080×1350 (4:5), cortada no centro, uma de cada vez; a localização (GPS) da foto não vai junto. Foto do iPhone: “Mais compatível” (JPG), não HEIC.</p>`}` : ""}
      ${ed && vaiAoAr ? `<h3>Quem aparece</h3>
        ${p.quem_aparece ? `<p class="sub">No plano: ${h(p.quem_aparece)}</p>` : ""}
        ${ativas.length ? `<div class="peca-pessoas">${ativas.map(x => `<label><input type="checkbox" name="pessoa" class="peca-arte-campo" value="${x.id}"${p.pessoas.includes(x.id) ? " checked" : ""}${desAr}>
            <span><b>${h(x.nome_na_peca)}</b>${x.area ? ` · ${h(x.area)}` : ""}${x.ativo ? "" : " " + selo("inativa", "erro")} ${seloTermo(termoDe(x.id))}</span></label>`).join("")}</div>
          <p class="sub">Marque só quem aparece nas fotos e nos textos (ou ninguém). O selo do termo de uso de imagem vale para o dia da peça e aparece depois de salvar.</p>`
          : `<p class="sub">Nenhuma pessoa cadastrada. ${ehAdmin() ? "Cadastre" : "O administrador cadastra"} em Pauta → Pessoas e termos, e registre o termo de uso de imagem assinado na tela (todos assinam, sócios inclusive).</p>`}` : ""}
      ${vaiAoAr ? `<h3>Informações conferidas</h3>
        <p class="sub">Cada fato da peça (número, data, prazo, regra, o que a Artecon faz) com a fonte oficial em que foi conferido. Número que não estiver aqui trava a aprovação; o boletim pago (ITC) não serve de fonte.</p>
        <div class="conf-linhas" id="peca-conferidas"${desAr ? ` data-travado="1"` : ""}>${conferidasDe(p).map(c => linhaConferida(c, desAr)).join("")}</div>
        ${desAr ? "" : `<div class="acoes"><button class="btn peq sec" type="button" data-acao="peca-conf-linha">Acrescentar informação</button>
          ${p.tipo === "agenda" ? `<button class="btn peq sec" type="button" data-acao="peca-agenda">Calcular a agenda da semana</button><span class="sub">Da segunda ao domingo seguintes (no fim de semana, só vence o que não muda de data, como a DEFIS e a DASN-SIMEI), pelas regras das Configurações: confira as datas.</span>` : ""}</div>`}
        ${ed ? blocoIaPeca(p, travada) : ""}
        <h3>Textos</h3>
        ${p.formato !== "reel" ? `<div class="grade">
          <div><label for="peca-chamada">Chamada da arte</label><input id="peca-chamada" type="text" name="chamada" maxlength="120" value="${h(p.chamada)}" class="peca-arte-campo"${desAr}></div>
          <div><label for="peca-apoio">Linha de apoio</label><input id="peca-apoio" type="text" name="apoio" maxlength="200" value="${h(p.apoio)}" class="peca-arte-campo"${desAr}></div></div>`
          // v0.22.0: no reel, a chamada é o texto do gancho que o corretor escreve de 0 a 3 s (opcional, escolhido no envio)
          : `<label for="peca-chamada">Texto do gancho do reel (aparece de 0 a 3 s, se escolhido no envio; opcional)</label><input id="peca-chamada" type="text" name="chamada" maxlength="120" value="${h(p.chamada)}"${desAr}>`}
        ${comCartoes ? `<label>Cartões ${p.formato === "carrossel_fotos" ? "(um por foto, na mesma ordem)" : "(de 2 a 9, depois da capa)"}</label>
          <div class="cartao-linhas" id="peca-cartoes"${desAr ? ` data-travado="1"` : ""}>${cartoesDe(p).map(c => linhaCartao(c, desAr)).join("")}</div>
          ${desAr ? "" : `<div class="acoes"><button class="btn peq sec" type="button" data-acao="peca-cartao-linha">Acrescentar cartão</button></div>`}` : ""}
        ${comRoteiro ? `<label for="peca-roteiro">Roteiro do reel (colado do plano: a coluna “Fala” é o que o corretor de vídeo compara com a gravação; a cartela final com a identificação legal o corretor grava)</label>
          <textarea id="peca-roteiro" name="roteiro" maxlength="6000" rows="8"${desAr}>${h(p.roteiro)}</textarea>` : ""}
        <p class="sub">Legenda vazia: o canal não entra. Cada legenda leva no fim a identificação legal: ${faltaIdentificacao().length
          ? `<b>falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura</b> (o administrador preenche; sem isso a peça não fica pronta).` : h(linhaIdentificacao()) + "."}</p>
        <div class="peca-legendas">${legenda("instagram")}${legenda("facebook")}</div>
        ${blocoArtePeca(p, ed)}
        <div id="peca-conferencia" class="peca-conferencia" hidden></div>` : ""}
      <details class="peca-plano"${vaiAoAr ? "" : " open"}><summary>Plano (assunto, objetivo, observação e quem aparece)</summary>
        <p class="sub">Do calendário: é referência para quem prepara a peça e não vai ao ar.</p>
        <label for="peca-assunto">Assunto</label><textarea id="peca-assunto" name="assunto" maxlength="1000" rows="3"${desPlano}>${h(p.assunto)}</textarea>
        <div class="grade"><div><label for="peca-objetivo">Objetivo</label><input id="peca-objetivo" type="text" name="objetivo" maxlength="200" value="${h(p.objetivo)}"${desPlano}></div>
          <div><label for="peca-quem">Quem aparece (lembrete)</label><input id="peca-quem" type="text" name="quem_aparece" maxlength="300" value="${h(p.quem_aparece)}"${desPlano}></div></div>
        <label for="peca-observacao">Observação</label><textarea id="peca-observacao" name="observacao" maxlength="1000" rows="2"${desPlano}>${h(p.observacao)}</textarea></details>
      ${ed ? `<div class="acoes peca-acoes"><button class="btn">Salvar</button>
        ${vaiAoAr && ["planejada", "em_producao"].includes(p.situacao) ? `<button class="btn verde" type="button" data-acao="peca-salvar-pronta">Salvar e marcar como pronta</button>` : ""}
        ${vaiAoAr && ["planejada", "em_producao", "pronta"].includes(p.situacao) ? `<button class="btn sec" type="button" data-acao="peca-conferir">Conferir o que falta</button>` : ""}
        ${p.situacao === "pronta" ? `<button class="btn sec" type="button" data-acao="peca-voltar-producao">Voltar para produção</button>` : ""}
        ${["planejada", "em_producao", "pronta"].includes(p.situacao) ? `<button class="btn perigo" type="button" data-acao="peca-cancelar">Cancelar a peça</button>` : ""}
        ${p.situacao === "cancelada" ? `<button class="btn sec" type="button" data-acao="peca-reabrir">Reabrir</button>` : ""}</div>` : ""}
    </form>
    ${video}
    ${vaiAoAr && p.situacao === "pronta" ? ehAdmin() ? blocoAprovar(p) : ed ? `<div class="aviso info" id="peca-espera">Pronta: falta o administrador aprovar.</div>` : "" : ""}
    ${p.situacao === "aprovada" ? blocoAprovada(p) : ""}`;
}
/* O estado do formulário da peça (para saber se há algo não salvo: inclui as linhas acrescentadas ou tiradas). v0.28.1: as informações
   conferidas e os cartões entram como o Salvar os grava (linhasDoForm, a mesma de corpoDaPeca: sem os espaços das pontas e sem a linha em
   branco). Antes, a linha em branco de “Acrescentar informação” (o reel com número no roteiro chega a ela pelo “Conferir o que falta”)
   contava como alteração, e o Salvar, que não grava linha em branco, respondia “Nada mudou na peça.” sem redesenhar: o envio do vídeo, a
   conferência, o Gerar com IA, a aprovação e as mudanças de situação ficavam barrados com AVISO_PECA_SUJA até recarregar a página.
   Cada campo vai com o nome (para o aviso dizer onde está a diferença: mudancasPeca) */
const estadoPeca = f => JSON.stringify({campos:[...f.elements].filter(c => c.name && c.type !== "file" && !c.closest("#peca-conferidas, #peca-cartoes"))
    .map(c => [c.name, c.type === "checkbox" ? c.checked : c.value]),
  conferidas:linhasDoForm(f, "#peca-conferidas", [["informacao", "[name=conf-informacao]"], ["fonte", "[name=conf-fonte]"]], Infinity, ""),
  cartoes:linhasDoForm(f, "#peca-cartoes", [["titulo", "[name=cartao-titulo]"], ["texto", "[name=cartao-texto]"]], Infinity, "")});
const pecaMudou = f => !!f && estadoPeca(f) !== f.dataset.original;
const AVISO_PECA_SUJA = "Há alterações não salvas na peça. Salve (ou recarregue a página para descartar) antes de continuar.";
/* v0.28.1: o que mudou e não foi salvo, com o nome que a tela mostra; vai no fim do aviso (avisoPecaSuja), para o print dizer onde está
   a diferença. Sem o estado de antes (ou num formato que não é este), nada: o aviso sai como sempre. */
function mudancasPeca(f){
  let antes; try{ antes = JSON.parse(f.dataset.original || ""); }catch(e){ return []; }
  if(!antes || !Array.isArray(antes.campos)) return [];
  const agora = JSON.parse(estadoPeca(f)), porNome = l => l.reduce((m, [n, v]) => ((m[n] ||= []).push(v), m), {}), a = porNome(antes.campos), b = porNome(agora.campos);
  const nomes = {hora:"Hora", tipo:"Tipo", formato:"Formato", pessoa:"Quem aparece", chamada:f.dataset.formato === "reel" ? "Texto do gancho" : "Chamada da arte",
    apoio:"Linha de apoio", roteiro:"Roteiro", legenda_instagram:"Legenda do Instagram", legenda_facebook:"Legenda do Facebook", assunto:"Assunto",
    objetivo:"Objetivo", quem_aparece:"Quem aparece (lembrete)", observacao:"Observação"};
  const mudou = [...new Set([...Object.keys(a), ...Object.keys(b)])].filter(n => JSON.stringify(a[n]) !== JSON.stringify(b[n])).map(n => nomes[n] || n);
  if(JSON.stringify(antes.conferidas) !== JSON.stringify(agora.conferidas)) mudou.push("Informações conferidas");
  if(JSON.stringify(antes.cartoes) !== JSON.stringify(agora.cartoes)) mudou.push("Cartões");
  return mudou;
}
const avisoPecaSuja = (f, texto = AVISO_PECA_SUJA) => { const m = f ? mudancasPeca(f) : []; return m.length ? `${texto} O que mudou e não foi salvo: ${m.join(", ")}.` : texto; };
/* As linhas de uma lista do formulário (informações conferidas ou cartões); null quando a lista está travada ou não aparece */
function linhasDoForm(f, caixa, campos, max, nome){
  const box = f.querySelector(caixa); if(!box || box.dataset.travado) return null;
  const linhas = [...box.children].map(l => Object.fromEntries(campos.map(([k, sel]) => [k, (l.querySelector(sel)?.value || "").trim()])))
    .filter(l => Object.values(l).some(Boolean));
  if(linhas.length > max) throw new ErroApi(`A peça leva no máximo ${max} ${nome}: tire ${linhas.length - max}.`);
  return linhas;
}
/* As pessoas marcadas na tela: quem já estava fica na mesma ordem (é a ordem de {PESSOA1}, {PESSOA2}… da IA e das linhas da arte); quem
   entra vai para o fim. Sem as caixas (ninguém cadastrado, ou o leitor), as da peça. */
function pessoasDoForm(f){
  const antes = JSON.parse(f.dataset.pessoas || "[]"), caixas = [...f.querySelectorAll("input[name=pessoa]")];
  if(!caixas.length) return antes;
  const na = new Set(caixas.map(c => Number(c.value))), marcadas = caixas.filter(c => c.checked).map(c => Number(c.value));
  return antes.filter(x => !na.has(x) || marcadas.includes(x)).concat(marcadas.filter(x => !antes.includes(x)));
}
/* Só o que mudou na tela vai ao banco (o que não mudou não conta como mudança do que vai ao ar nem esbarra na trava da peça aprovada) */
function corpoDaPeca(f){
  const corpo = {}, mudou = el => el.tagName === "SELECT" ? [...el.options].some(o => o.selected !== o.defaultSelected) : el.value !== el.defaultValue;
  for(const n of ["hora", "tipo", "formato", "chamada", "apoio", "roteiro", "legenda_instagram", "legenda_facebook", "assunto", "objetivo", "observacao", "quem_aparece"]){
    const el = f.elements[n]; if(el && !el.disabled && mudou(el)) corpo[n] = el.value.trim(); }
  if(corpo.hora === "") throw new ErroApi("Informe a hora da publicação (de Brasília).");
  if(f.querySelector("input[name=pessoa]:not(:disabled)")){
    const lista = pessoasDoForm(f); if(JSON.stringify(lista) !== JSON.stringify(JSON.parse(f.dataset.pessoas || "[]"))) corpo.pessoas = lista; }
  const conferidas = linhasDoForm(f, "#peca-conferidas", [["informacao", "[name=conf-informacao]"], ["fonte", "[name=conf-fonte]"]], 20, "informações conferidas");
  if(conferidas && JSON.stringify(conferidas) !== f.dataset.conferidas) corpo.conferidas = conferidas;
  const cartoes = linhasDoForm(f, "#peca-cartoes", [["titulo", "[name=cartao-titulo]"], ["texto", "[name=cartao-texto]"]], 9, "cartões");
  if(cartoes && JSON.stringify(cartoes) !== f.dataset.cartoes) corpo.cartoes = cartoes;
  return corpo;
}
/* Grava na peça só se ela ainda for a que está na tela (outra pessoa ou outra aba pode ter salvo antes): nenhuma linha = nada gravado */
async function gravarPeca(f, corpo){
  const r = await rest("PATCH", "radar_pauta_pecas", {params:{id:"eq." + f.dataset.id, atualizado_em:"eq." + f.dataset.lido, select:"id,atualizado_em,situacao,fotos"},
    corpo, prefer:"return=representation"});
  if(!Array.isArray(r) || !r.length)
    throw new ErroApi("Esta peça foi alterada em outra tela (ou o seu perfil não permite salvar). Nada foi gravado: anote o que você mudou, recarregue a página e refaça.");
  f.dataset.lido = r[0].atualizado_em;
  return r[0];
}
async function situacaoDaPeca(el, situacao, pergunta, msg){
  const f = el.closest("form[data-form=peca]");
  if(pecaMudou(f)) throw new ErroApi(avisoPecaSuja(f));
  if(pergunta && !confirm(pergunta)) return;
  await gravarPeca(f, {situacao}); await desenhar(); recado(msg);
}
/* Fotos: a lista nova vai com a trava da versão; a tela troca só as miniaturas (o texto digitado e não salvo continua onde está) */
async function gravarFotosPeca(f, fotos){
  const r = await gravarPeca(f, {fotos});
  f.dataset.fotos = JSON.stringify(r.fotos);
  const lista = $("#peca-fotos-lista"); if(lista) lista.innerHTML = listaFotosPeca(r.fotos, true);
  const s = $("#peca-situacao"); if(s && SITUACOES_PAUTA[r.situacao]) s.innerHTML = selo(SITUACOES_PAUTA[r.situacao], r.situacao === "em_producao" ? "alerta" : r.situacao === "planejada" ? "neutro" : "");
  if(typeof montarArtesPeca === "function") montarArtesPeca();
}
const tamanhoDaImagem = origem => new Promise((ok, falha) => { const i = new Image();
  i.onload = () => ok({largura:i.naturalWidth, altura:i.naturalHeight}); i.onerror = () => falha(new ErroApi("Não foi possível ler esta imagem.")); i.src = origem; });
/* Várias fotos de uma vez: vão uma de cada vez (1080×1350, cortada no centro, até 600.000 caracteres), com "x de y" na tela; no fim,
   a lista de fotos da peça é gravada com a trava da versão. Foto HEIC (iPhone) não abre no navegador: recado e fica de fora. */
async function enviarFotosPeca(campo){
  const f = campo.closest("form[data-form=peca]"), arquivos = [...campo.files]; campo.value = "";
  if(!f || !arquivos.length) return;
  const heic = arquivos.filter(a => /^image\/hei[cf]/i.test(a.type) || /\.hei[cf]$/i.test(a.name)), outras = arquivos.filter(a => !heic.includes(a));
  // a foto HEIC fica de fora: o recado vem no fim, junto com o que aconteceu com as outras (nada é dado como enviado antes de ir)
  const foraHeic = heic.length ? `${heic.length === 1 ? "A foto HEIC ficou de fora" : `As ${heic.length} fotos HEIC ficaram de fora`} (${heic.map(a => a.name).join(", ")}). ${RECADO_HEIC}.` : "";
  if(!outras.length){ recado(foraHeic, true); return; }
  const fotos = JSON.parse(f.dataset.fotos || "[]");
  if(fotos.length + outras.length > 10)
    throw new ErroApi(`A peça leva no máximo 10 fotos (já tem ${fotos.length}): escolha menos fotos ou tire alguma. Nenhuma foto foi enviada.` + (foraHeic ? " " + foraHeic : ""));
  const andamento = $("#peca-fotos-andamento"), novas = [], pequenas = [], falhas = [];
  try{
    for(const [i, a] of outras.entries()){
      if(andamento) andamento.textContent = `Enviando a foto ${i + 1} de ${outras.length}…`;
      if(!/^image\/(jpeg|png|webp)$/.test(a.type)){ falhas.push(`${a.name}: use JPG, PNG ou WebP`); continue; }
      const u = URL.createObjectURL(a);
      try{
        const original = await tamanhoDaImagem(u), img = await reduzirImagemDe(u, 1080, 1350);
        if(original.largura < 1080 || original.altura < 1350) pequenas.push(a.name);
        const [nova] = await rest("POST", "radar_imagens", {corpo:img, params:{select:"id"}, prefer:"return=representation"});
        novas.push(nova.id); (E.pauta.fotos ||= {})[nova.id] = img.dados;
      }catch(e){ falhas.push(`${a.name}: ${e.message || "não foi enviada"}`); }
      finally{ URL.revokeObjectURL(u); }
    }
  }finally{ if(andamento) andamento.textContent = ""; }
  if(novas.length) await gravarFotosPeca(f, fotos.concat(novas));
  if(novas.length) recado(`${novas.length} foto(s) enviada(s).`);
  if(pequenas.length) recado(`Foto pequena (menos de 1080×1350): pode ficar sem nitidez — ${pequenas.join(", ")}.`, "aviso");
  if(falhas.length) recado("Não foram enviadas: " + falhas.join("; ") + ".", true);
  if(foraHeic) recado(foraHeic, true);
}
/* A agenda da semana (tipo "Agenda da semana", no domingo D): os vencimentos de D+1 a D+5 (segunda a sexta seguintes), pelas regras das
   Configurações (calcularAgenda, um mês por vez: a semana pode atravessar o mês), sem as obrigações com "redes": false. Cada uma vira uma
   informação conferida ("10/11 (ter) · ICMS"), com a "fonte" da obrigação; sem ela, a fonte fica em branco (a regra das Configurações
   não é fonte oficial): a peça não fica pronta até alguém conferir e escrever a fonte (o texto provisório iria ao ar no "Fonte: …").
   v0.30.0: o vencimento que vem de uma prorrogação (a nova data que o administrador escreveu em "prorrogacoes") leva a fonte do ato da
   prorrogação; os outros, a da obrigação. E a semana vai até o domingo seguinte (D+7): a DEFIS e a DASN-SIMEI ("ajuste": "nenhum") vencem
   no sábado ou no domingo em alguns anos (31/05/2026 é domingo) e, só de segunda a sexta, não entrariam em post nenhum; o post do
   domingo seguinte (D+7) começa na segunda, D+8, então nada se repete. */
function agendaDaSemana(dia){
  const de = somarDias(dia, 1), ate = somarDias(dia, 7);
  const obrig = (Array.isArray(CONF_PAUTA.obrigacoes) ? CONF_PAUTA.obrigacoes : []).filter(o => o && typeof o === "object" && o.redes !== false);
  const fonteDe = (nome, data) => { const o = obrig.find(x => String(x.nome) === nome);
    const p = (Array.isArray(o?.prorrogacoes) ? o.prorrogacoes : []).find(x => x && typeof x === "object" && x.para === data);
    return textoDe(p ? p.fonte : o?.fonte); };
  return [...new Set([de.slice(0, 7), ate.slice(0, 7)])]
    .flatMap(m => calcularAgenda(Number(m.slice(0, 4)), Number(m.slice(5, 7)), obrig, CONF_PAUTA.feriados_extras))
    .filter(l => l.data >= de && l.data <= ate)
    .flatMap(l => l.obrigacoes.map(nome => ({informacao:`${l.data.slice(8, 10)}/${l.data.slice(5, 7)} (${DIAS_CURTOS[diaDaSemana(l.data)]}) · ${nome}`.slice(0, 300),
                                             fonte:fonteDe(nome, l.data).slice(0, 300)})));
}
const contarPeca = campo => { const s = document.getElementById(campo.dataset.conta); if(s) s.textContent = campo.value.length.toLocaleString("pt-BR") + "/2.200"; };

/* ------------------------------------------------------------- Gerar com IA da peça */
/* O quadro do Gerar com IA (editor e administrador): a IA sugere a chamada e o apoio da arte, as legendas e os cartões a partir do plano e
   das informações conferidas da peça SALVA (radar-ia, ação "peca"); a sugestão fica guardada na peça (radar_pauta_pecas.ia), sem mudar a
   versão dela. Na aprovada ou cancelada, nada (os textos estão travados); no reel, o roteiro é colado à mão nesta versão. */
function blocoIaPeca(p, travada){
  if(travada) return "";
  if(p.formato === "reel") return `<p class="sub peca-ia-reel">Reel: o roteiro é colado à mão nesta versão (sem Gerar com IA).</p>`;
  const o = p.tipo === "agenda" ? "as legendas da agenda (a lista de vencimentos vai na arte)"
    : "a chamada e o apoio da arte" + (["carrossel", "carrossel_fotos"].includes(p.formato) ? ", as legendas e os cartões" : " e as legendas");
  return `<div class="peca-ia" id="peca-ia"><h3>Gerar com IA</h3>
    <p class="sub">A IA sugere ${o}, a partir do plano e das informações conferidas da peça salva. Os nomes da equipe não vão à IA: a pessoa marcada vai como {PESSOA1}, e aqui aparece o nome na peça; não escreva no plano o nome de quem não está cadastrado nem no “quem aparece” do calendário. O fato que não estiver nas informações conferidas vem marcado com [VERIFICAR].</p>
    <div class="acoes"><button class="btn sec" type="button" data-acao="peca-ia">Gerar com IA</button></div>
    <div id="peca-sugestao">${blocoSugestaoPeca(E.pauta.ia, {pessoas:p.pessoas, tipo:p.tipo, formato:p.formato})}</div></div>`;
}
const sugestaoValida = s => !!s && typeof s === "object" && !!textoDe(s.instagram?.texto) && !!textoDe(s.facebook?.texto);
/* A sugestão vale para a peça como está? Feita com outras pessoas (ou noutra ordem: {PESSOA1} seria outra pessoa), outro tipo ou outro
   formato: não. "atual": {pessoas, tipo, formato} (da peça salva, ou do formulário na hora de usar). */
function mudouDesdeSugestao(s, atual){
  if(JSON.stringify((Array.isArray(s.base?.pessoas) ? s.base.pessoas : []).map(Number)) !== JSON.stringify((atual.pessoas || []).map(Number)))
    return "A sugestão foi feita com outras pessoas: gere de novo.";
  if(s.base?.tipo !== atual.tipo || s.base?.formato !== atual.formato) return "A sugestão foi feita para outro tipo ou formato de peça: gere de novo.";
  return "";
}
/* Os textos da IA com o nome na peça no lugar de {PESSOA1}, {PESSOA2}… (na ordem das pessoas da sugestão); sem a pessoa, fica o marcador */
const nomesDaSugestao = s => t => String(t || "").replace(/\{PESSOA(\d+)\}/g, (m, n) =>
  textoDe((E.pauta.pessoas || {})[(Array.isArray(s.base?.pessoas) ? s.base.pessoas : [])[Number(n) - 1]]?.nome_na_peca) || m);
/* O quadro da sugestão: o que falta conferir (as pendências da IA), os avisos, a arte, os cartões e as legendas; "Usar a sugestão" só
   quando ela vale para a peça. Tudo o que vem da IA é escapado. */
function blocoSugestaoPeca(s, atual){
  if(!sugestaoValida(s)) return `<p class="sub" id="peca-sem-sugestao">Ainda não há sugestão da IA para esta peça.</p>`;
  const nome = nomesDaSugestao(s), lista = v => (Array.isArray(v) ? v : []).map(textoDe).filter(Boolean), mudou = mudouDesdeSugestao(s, atual);
  const pendencias = lista(s.pendencias), avisos = lista(s.avisos), cartoes = (Array.isArray(s.cartoes) ? s.cartoes : []).filter(c => c && typeof c === "object");
  const legenda = k => `<div><b>${NOME_REDE[k]}</b><div class="kit-legenda peca-sugestao-legenda" data-canal="${k}">${h(nome(textoDe(s[k].texto)))}</div>
      ${lista(s[k].hashtags).length ? `<span class="sub">Hashtag do tema: ${h(lista(s[k].hashtags).join(" "))}</span>` : ""}</div>`;
  return `<div class="painel peca-sugestao" id="peca-sugestao-quadro"><h4>Sugestão da IA <span class="sub">— gerada em ${h(dataHora(s.gerado_em))}</span></h4>
    ${mudou ? `<div class="aviso alerta" id="peca-sugestao-outra">${h(mudou)}</div>` : ""}
    ${pendencias.length ? `<div class="aviso alerta peca-pendencias"><b>O que falta conferir (a IA deixou fora do texto):</b><ul class="pauta-erros">${pendencias.map(x => `<li>${h(nome(x))}</li>`).join("")}</ul></div>` : ""}
    ${avisos.length ? `<div class="aviso alerta peca-ia-avisos"><b>Pontos a conferir na sugestão (${avisos.length}):</b><ul class="pauta-erros">${avisos.map(x => `<li>${h(nome(x))}</li>`).join("")}</ul></div>` : ""}
    ${s.arte && typeof s.arte === "object" ? `<p class="peca-sugestao-arte"><b>Arte:</b> “${h(nome(textoDe(s.arte.chamada)))}”${textoDe(s.arte.apoio) ? ` — ${h(nome(textoDe(s.arte.apoio)))}` : ""}</p>` : ""}
    ${cartoes.length ? `<b>Cartões</b><ol class="peca-sugestao-cartoes">${cartoes.map(c => `<li>${textoDe(c.titulo) ? `<b>${h(nome(textoDe(c.titulo)))}</b> — ` : ""}${h(nome(textoDe(c.texto)))}</li>`).join("")}</ol>` : ""}
    <div class="kit-legendas">${legenda("instagram")}${legenda("facebook")}</div>
    <p class="sub">É sugestão: “Usar a sugestão” leva os textos aos campos (nas legendas, com a fonte das informações conferidas, a identificação legal e as hashtags no fim), sem salvar. Vai ao ar o que for salvo e aprovado.</p>
    ${mudou ? "" : `<div class="acoes"><button class="btn peq" type="button" data-acao="peca-usar-ia">Usar a sugestão</button></div>`}</div>`;
}

/* ----------------------------------------------------------- a arte da peça (desenharPeca) */
/* As lâminas da peça, 1080×1350 (4:5), desenhadas no navegador numa função própria: a arte da notícia (desenharArte, index.html) não
   muda. Dois modelos. "foto": a foto em capa cheia, véu escuro embaixo, o selo do tipo, a chamada (até 3 linhas), o apoio, a linha de
   cada pessoa marcada (escrita pelo código: linhaPessoa; até 6 linhas: com mais, as pessoas sem registro da mesma área dividem a
   linha, "Ana, Bruno e Carla · Departamento Pessoal", e o que ainda sobrar vai para os cortes) e a página ("2/6"). "texto": fundo
   marinho, o selo, o título, o texto ou a lista (a agenda da semana, agrupada pela data) e a página. Margem lateral de 72 px (guia de
   produção). Sem “Matéria completa” e sem o selo de SC: a peça não é notícia. Faixa legal: fundo branco com a identificação das Configurações (linhaIdentificacao), em letra com
   pelo menos 28 px de ALTURA medida (o “H”; começa em 40 px: a leitura mais rígida do guia), em até 3 linhas quebradas nos “ · ” (a
   2ª linha com os dados reais fica a 2 px da margem: um arredondamento de outro aparelho não pode travar toda aprovação); se uma parte
   sozinha não couber na largura, ou passar de 3 linhas, sai cortada e vai para os cortes — a aprovação trava. JPEG de 0,9 a 0,6 até
   caber em radar_imagens (LIMITE_IMAGEM).
   Devolve {dados, textos, cortes}, como desenharArte ("cortes": titulo, texto, lista, pessoas, identificacao). */
const SELO_PECA = {quem_cuida:"QUEM CUIDA", bastidor:"BASTIDOR", captacao:"CAPTAÇÃO", data_equipe:"COM A EQUIPE", agenda:"AGENDA DA SEMANA",
  educativo:"ORIENTAÇÃO", reel:"REEL"};
const FAIXA_LEGAL = {px:40, altura:28};      // a altura medida do “H” (se o dono confirmar “fonte de 28 px”, só muda aqui)
async function desenharPeca(d){
  const L = 1080, A = 1350, M = 72, LARG = L - 2 * M, cv = document.createElement("canvas"); cv.width = L; cv.height = A;
  const cx = cv.getContext("2d"), textos = [], cortes = new Set();
  try{ await Promise.race([Promise.all([document.fonts.load('700 80px "DM Sans"'), document.fonts.load('500 40px "DM Sans"')]), new Promise(ok => setTimeout(ok, 1500))]); }catch(e){}
  const carregar = src => new Promise(ok => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => ok(null); i.src = src; });
  const caixa = (x, y, w, a, r) => { cx.beginPath(); cx.roundRect ? cx.roundRect(x, y, w, a, r) : cx.rect(x, y, w, a); cx.fill(); };
  const fonte = (peso, px) => `${peso} ${px}px "DM Sans", Arial, sans-serif`;
  const escrever = (t, x, y) => { textos.push(t); cx.fillText(t, x, y, L - M - x); };
  // como na arte da notícia: linhas de até LARG; passando de "max", a última perde a palavra que sobra e termina em "…" ("nome" vai
  // para os cortes: a tela avisa)
  const quebrar = (t, max, nome) => { const linhas = []; let atual = "";
    for(const p of String(t || "").trim().split(/\s+/).filter(Boolean)){ const teste = atual ? atual + " " + p : p;
      if(cx.measureText(teste).width > LARG && atual){ linhas.push(atual); atual = p; } else atual = teste; }
    if(atual) linhas.push(atual);
    if(linhas.length > max){ linhas.length = max; linhas[max - 1] = linhas[max - 1].replace(/[\s,.;:]+\S*$/, "") + "…"; if(nome) cortes.add(nome); }
    return linhas; };
  const larga = linhas => linhas.some(l => cx.measureText(l).width > LARG);
  // o título: a maior letra (de "maior" para baixo) em que ele cabe em "max" linhas, na altura e na largura; a palavra que sozinha
  // passa da largura leva a letra para baixo (até 44 px) em vez de sair espremida
  const ajustar = (t, maior, menor, max, cabe) => { let px = maior;
    for(; px > menor; px -= 4){ cx.font = fonte(700, px); const l = quebrar(t, 99); if(l.length <= max && l.length * px * 1.1 <= cabe && !larga(l)) break; }
    for(; px > 44; px -= 4){ cx.font = fonte(700, px); if(!larga(quebrar(t, 99))) break; }
    cx.font = fonte(700, px); return {px, linhas:quebrar(t, Math.max(1, Math.min(max, Math.floor(cabe / (px * 1.1)))), "titulo")}; };
  // a faixa legal primeiro: a altura dela é o limite de baixo da arte
  const legal = linhaIdentificacao() || "Artecon Artes Contábeis";
  let pxL = FAIXA_LEGAL.px; cx.font = fonte(500, pxL); cx.textBaseline = "alphabetic";          // a altura do “H” acima da linha de base
  const alturaH = () => cx.measureText("H").actualBoundingBoxAscent || pxL * 0.7;
  while(alturaH() < FAIXA_LEGAL.altura && pxL < 64){ pxL += 2; cx.font = fonte(500, pxL); }
  let linhasLegal = [];
  for(const p of legal.split(" · ")){ const junto = linhasLegal.length ? linhasLegal[linhasLegal.length - 1] + " · " + p : "";
    if(junto && cx.measureText(junto).width <= LARG) linhasLegal[linhasLegal.length - 1] = junto; else linhasLegal.push(p); }
  if(linhasLegal.length > 3 || larga(linhasLegal)){ cortes.add("identificacao"); linhasLegal = quebrar(legal, 3); }
  const passoLegal = Math.round(pxL * 1.3), TOPO = A - linhasLegal.length * passoLegal - 48;
  // o fundo: marinho; no modelo "foto", a foto em capa cheia até a faixa legal, com sombra no alto (o logotipo) e o véu embaixo (o texto)
  const foto = d.modelo === "foto" && d.imagem ? await carregar(d.imagem) : null;
  if(d.modelo === "foto" && d.imagem && !(foto && foto.naturalWidth && foto.naturalHeight)) throw new ErroApi("Não foi possível ler a foto da peça: envie de novo.");
  const fundo = cx.createLinearGradient(0, 0, L, A); fundo.addColorStop(0, "#011F48"); fundo.addColorStop(.6, "#0D3B73"); fundo.addColorStop(1, "#1B5E9B");
  cx.fillStyle = fundo; cx.fillRect(0, 0, L, A);
  if(foto){ const f = Math.max(L / foto.naturalWidth, TOPO / foto.naturalHeight);
    cx.drawImage(foto, (L - foto.naturalWidth * f) / 2, (TOPO - foto.naturalHeight * f) / 2, foto.naturalWidth * f, foto.naturalHeight * f);
    const alto = cx.createLinearGradient(0, 0, 0, 260); alto.addColorStop(0, "rgba(1,31,72,.55)"); alto.addColorStop(1, "rgba(1,31,72,0)");
    cx.fillStyle = alto; cx.fillRect(0, 0, L, 260);
    const veu = cx.createLinearGradient(0, TOPO - 720, 0, TOPO); veu.addColorStop(0, "rgba(1,31,72,0)"); veu.addColorStop(.55, "rgba(1,31,72,.72)"); veu.addColorStop(1, "rgba(1,31,72,.95)");
    cx.fillStyle = veu; cx.fillRect(0, TOPO - 720, L, 720); }
  else for(const [raio, cor] of [[380, "rgba(86,157,204,.30)"], [290, "rgba(86,157,204,.45)"], [200, "rgba(86,157,204,.75)"]]){
    cx.beginPath(); cx.arc(L + 60, TOPO + 30, raio, 0, Math.PI * 2); cx.fillStyle = cor; cx.fill(); }
  // faixa tricolor, o logotipo sobre cartão branco e a página ("2/6") à direita
  cx.fillStyle = "#BC151B"; cx.fillRect(0, 0, L * .68, 14); cx.fillStyle = "#00AEEF"; cx.fillRect(L * .68, 0, L * .22, 14); cx.fillStyle = "#FFD700"; cx.fillRect(L * .9, 0, L * .1, 14);
  const logo = await carregar("radar-logo-artecon.png");
  cx.fillStyle = "#fff"; caixa(M, 52, 240, 104, 14); cx.textBaseline = "middle";
  if(logo && logo.naturalWidth){ const f = Math.min(200 / logo.naturalWidth, 80 / logo.naturalHeight);
    cx.drawImage(logo, M + (240 - logo.naturalWidth * f) / 2, 52 + (104 - logo.naturalHeight * f) / 2, logo.naturalWidth * f, logo.naturalHeight * f); }
  else{ cx.fillStyle = "#011F48"; cx.font = '700 40px Georgia, serif'; escrever("Artecon", M + 30, 104); }
  if(d.pagina){ cx.font = fonte(700, 28); const w = cx.measureText(d.pagina).width + 40;
    cx.fillStyle = "rgba(255,255,255,.2)"; caixa(L - M - w, 76, w, 56, 28); cx.fillStyle = "#fff"; escrever(d.pagina, L - M - w + 20, 104); }
  const selo = y => { cx.font = fonte(700, 26); const w = cx.measureText(d.selo).width + 44;
    cx.fillStyle = "#FFD700"; caixa(M, y, w, 52, 26); cx.fillStyle = "#011F48"; cx.textBaseline = "middle"; escrever(d.selo, M + 22, y + 26); cx.textBaseline = "top"; };
  cx.textBaseline = "top";
  if(d.modelo === "foto"){
    // de baixo para cima: as pessoas (amarelo), o apoio, a chamada e o selo, logo acima da faixa legal
    // as pessoas: uma linha (até 2) por pessoa; passando de 6 linhas, as sem registro da mesma área juntas (até 3 linhas por grupo);
    // ainda passando, a 7ª linha em diante fica de fora e vai para os cortes (a tela avisa)
    cx.font = fonte(600, 32);
    const linhasDe = (lista, max, nome) => (lista || []).flatMap(p => quebrar(p, max, nome));
    const juntas = linhasDe(d.pessoas, 2).length > 6 && (d.pessoasJuntas || []).length;
    let pessoas = juntas ? linhasDe(d.pessoasJuntas, 3, "pessoas") : linhasDe(d.pessoas, 2, "pessoas");
    if(pessoas.length > 6){ pessoas = pessoas.slice(0, 6); cortes.add("pessoas"); }
    cx.font = fonte(500, 38); const apoio = d.texto ? quebrar(d.texto, 3, "texto") : [];
    const altPessoas = pessoas.length ? 24 + pessoas.length * 42 : 0, altApoio = apoio.length ? 20 + apoio.length * 48 : 0, altSelo = d.selo ? 76 : 0;
    const t = d.titulo ? ajustar(d.titulo, 76, 52, 3, TOPO - 56 - 220 - altPessoas - altApoio - altSelo) : {px:0, linhas:[]};
    let y = TOPO - 56 - altPessoas - altApoio - t.linhas.length * t.px * 1.1 - altSelo;
    if(d.selo){ selo(y); y += 76; }
    cx.fillStyle = "#fff"; cx.font = fonte(700, t.px); for(const l of t.linhas){ escrever(l, M, y); y += t.px * 1.1; }
    if(apoio.length){ y += 20; cx.font = fonte(500, 38); cx.fillStyle = "#DCEBF7"; for(const l of apoio){ escrever(l, M, y); y += 48; } }
    if(pessoas.length){ y += 24; cx.font = fonte(600, 32); cx.fillStyle = "#FFD700"; for(const l of pessoas){ escrever(l, M, y); y += 42; } }
  } else {
    let y = 200; const fim = TOPO - 60;
    if(d.selo){ selo(y); y += 86; } else y += 20;
    if(Array.isArray(d.lista)){
      // a agenda da semana: o título curto e as linhas das informações conferidas agrupadas pela data ("10/11 (ter) · ICMS" → "10/11
      // (ter)" e, embaixo, "ICMS"); o que não cabe fica de fora e vai para os cortes
      if(d.titulo){ const t = ajustar(d.titulo, 68, 52, 2, 160); cx.fillStyle = "#fff"; for(const l of t.linhas){ escrever(l, M, y); y += t.px * 1.1; } y += 12; }
      if(d.texto){ cx.font = fonte(500, 34); cx.fillStyle = "#DCEBF7"; for(const l of quebrar(d.texto, 2, "texto")){ escrever(l, M, y); y += 44; } }
      const grupos = [];
      for(const item of d.lista){ const m = /^(\d{1,2}\/\d{1,2}(?:\s*\([^)]{1,12}\))?)\s*·\s*(.+)$/u.exec(item), data = m ? m[1] : "";
        let g = grupos[grupos.length - 1]; if(!g || g.data !== data) grupos.push(g = {data, itens:[]}); g.itens.push(m ? m[2] : item); }
      fora: for(const g of grupos){
        y += 18;
        if(g.data){ if(y + 44 > fim){ cortes.add("lista"); break; } cx.font = fonte(700, 34); cx.fillStyle = "#FFD700"; escrever(g.data, M, y); y += 46; }
        for(const item of g.itens){ cx.font = fonte(500, 32); const l = quebrar("• " + item, 2, "lista");
          if(y + l.length * 40 > fim){ cortes.add("lista"); break fora; }
          cx.fillStyle = "#fff"; for(const x of l){ escrever(x, M, y); y += 40; } y += 4; }
      }
    } else {
      const t = d.titulo ? ajustar(d.titulo, 84, 56, 4, (fim - y) * .55) : {px:0, linhas:[]};
      cx.fillStyle = "#fff"; for(const l of t.linhas){ escrever(l, M, y); y += t.px * 1.1; }
      if(d.texto){ y += t.linhas.length ? 28 : 0; let px = 40; cx.font = fonte(500, px);
        if(quebrar(d.texto, 99).length * 52 > fim - y){ px = 36; cx.font = fonte(500, px); }
        const passo = Math.round(px * 1.3); cx.fillStyle = "#DCEBF7";
        for(const l of quebrar(d.texto, Math.max(1, Math.floor((fim - y) / passo)), "texto")){ escrever(l, M, y); y += passo; } }
    }
  }
  // a faixa legal
  cx.fillStyle = "#fff"; cx.fillRect(0, TOPO, L, A - TOPO); cx.fillStyle = "#011F48"; cx.font = fonte(500, pxL); cx.textBaseline = "middle";
  linhasLegal.forEach((l, i) => escrever(l, M, TOPO + 24 + passoLegal * (i + .5)));
  let dados = "";
  for(const q of [0.9, 0.85, 0.8, 0.7, 0.6]){ dados = cv.toDataURL("image/jpeg", q); if(dados.length <= LIMITE_IMAGEM) break; }
  if(dados.length > LIMITE_IMAGEM) throw new ErroApi("A lâmina ficou grande demais para guardar (a foto tem detalhe demais): troque a foto.");
  return {dados, textos, cortes:[...cortes]};
}
/* O que vai na arte, lido do formulário da peça (o que está na tela, salvo ou não) */
function dadosPeca(f){
  const v = n => (f.elements[n]?.value ?? "").trim();
  const linhas = (caixa, campos) => [...(f.querySelector(caixa)?.children || [])]
    .map(l => Object.fromEntries(campos.map(([k, s]) => [k, (l.querySelector(s)?.value || "").trim()]))).filter(l => Object.values(l).some(Boolean));
  return {tipo:f.elements.tipo?.value || f.dataset.tipo, formato:f.elements.formato?.value || f.dataset.formato, chamada:v("chamada"), apoio:v("apoio"),
    cartoes:linhas("#peca-cartoes", [["titulo", "[name=cartao-titulo]"], ["texto", "[name=cartao-texto]"]]),
    lista:linhas("#peca-conferidas", [["informacao", "[name=conf-informacao]"]]).map(c => c.informacao),
    fotos:JSON.parse(f.dataset.fotos || "[]"), ...linhasDasPessoas(pessoasDoForm(f).map(id => (E.pauta.pessoas || {})[id]).filter(Boolean))};
}
/* As linhas das pessoas na arte: uma por pessoa ("pessoas") e, para quando não cabem, as sem registro da mesma área numa linha só
   ("pessoasJuntas": "Ana, Bruno e Carla · Departamento Pessoal"; quem tem registro fica na própria linha, com a categoria e o CRC) */
function linhasDasPessoas(lista){
  const grupos = [];
  for(const x of lista){
    if(ROTULO_CATEGORIA[x.categoria]){ grupos.push({linha:linhaPessoa(x)}); continue; }
    const area = areaPessoa(x), g = grupos.find(y => y.nomes && y.area === area);
    if(g) g.nomes.push(String(x.nome_na_peca || "").trim()); else grupos.push({area, nomes:[String(x.nome_na_peca || "").trim()]});
  }
  const juntar = n => n.length > 1 ? n.slice(0, -1).join(", ") + " e " + n[n.length - 1] : n[0];
  return {pessoas:lista.map(linhaPessoa), pessoasJuntas:grupos.map(g => g.linha || juntar(g.nomes) + (g.area ? " · " + g.area : ""))};
}
/* As lâminas, conforme o formato (a quantidade é a que a aprovação confere): Foto, 1 "foto"; Imagem 4:5, 1 "texto" (na Agenda da
   semana, com a lista); Carrossel, a capa e 1 "texto" por cartão; Carrossel de fotos, 1 "foto" por foto, com o cartão da mesma ordem;
   reel, nenhuma. O selo vai na 1ª; a página, quando há mais de uma; a linha das pessoas, em toda lâmina com foto. */
function laminasPeca(d){
  let l;
  if(["reel", "story", "nenhum"].includes(d.formato) || ["noticia", "sem_post"].includes(d.tipo)) l = [];
  else if(d.formato === "carrossel_fotos") l = d.fotos.map((id, i) => ({modelo:"foto", foto:id, titulo:d.cartoes[i]?.titulo || (i ? "" : d.chamada), texto:d.cartoes[i]?.texto || (i ? "" : d.apoio)}));
  else if(d.formato === "carrossel") l = [{modelo:d.fotos.length ? "foto" : "texto", foto:d.fotos[0] || null, titulo:d.chamada, texto:d.apoio},
    ...d.cartoes.map(c => ({modelo:"texto", titulo:c.titulo, texto:c.texto}))];
  else if(d.formato === "foto") l = [{modelo:"foto", foto:d.fotos[0] || null, titulo:d.chamada, texto:d.apoio}];
  else if(d.tipo === "agenda") l = [{modelo:"texto", titulo:d.chamada || "Agenda da semana", texto:d.apoio, lista:d.lista}];
  else l = [{modelo:"texto", titulo:d.chamada, texto:d.apoio}];
  return l.map((x, i) => ({...x, selo:i ? "" : SELO_PECA[d.tipo] || "", pessoas:x.modelo === "foto" ? d.pessoas : [],
    pessoasJuntas:x.modelo === "foto" ? d.pessoasJuntas : [], pagina:l.length > 1 ? `${i + 1}/${l.length}` : ""}));
}
const NOME_CORTE_PECA = {titulo:"o título", texto:"o texto", lista:"parte da agenda", pessoas:"a linha da pessoa", identificacao:"a identificação legal"};
const msgCortePeca = (n, cortes) => `Lâmina ${n}: ${cortes.map(k => NOME_CORTE_PECA[k] || k).join(" e ")} não ${cortes.length > 1 ? "couberam" : "coube"} e ` +
  `${cortes.length > 1 ? "saíram cortados" : "saiu cortado"} (termina em “…”)${cortes.includes("identificacao") ? ": encurte a identificação em Configurações → Assinatura" : ": encurte o texto"}.`;
/* A arte na tela da peça: na aprovada para a agenda, as lâminas aprovadas (as imagens que vão ao ar), para quem edita e só se o termo de
   uso de imagem de cada pessoa vale no dia da peça; na aprovada à mão, elas aparecem em "Baixar as lâminas", depois que o banco confere
   o termo de hoje (na página, seriam uma cópia pronta para postar sem essa conferência); para quem prepara, a prévia ao vivo
   (montarArtesPeca, depois de desenhar a tela e 400 ms depois da última tecla). O leitor não vê foto nem lâmina, como não vê as pessoas. */
function blocoArtePeca(p, ed){
  if(p.formato === "reel") return `<h3>Arte</h3><p class="sub">Reel: sem lâmina. O vídeo gravado com o roteiro passa pelo corretor de vídeo (abaixo), que grava a legenda e a cartela final com a identificação legal; aprovado, é baixado e postado à mão.</p>`;
  const lista = E.pauta.aprovadas || [];
  if(p.situacao === "aprovada" && (!ed || !lista.length)) return "";
  if(p.situacao === "aprovada" && p.aprovado_modo === "manual")
    return `<h3>Arte aprovada</h3><p class="sub" id="peca-artes-a-mao">${lista.length > 1 ? `As ${lista.length} lâminas aprovadas aparecem` : "A lâmina aprovada aparece"} em “Baixar as lâminas”, depois que o banco confere o termo de uso de imagem de cada pessoa no dia de hoje.</p>`;
  if(p.situacao === "aprovada" && E.pauta.termoFalha)
    return `<h3>Arte aprovada</h3><div class="aviso alerta" id="peca-artes-escondidas">As lâminas não aparecem: o termo de uso de imagem de uma pessoa da peça não vale no dia da peça (Pauta → Pessoas e termos).</div>`;
  if(p.situacao === "aprovada") return `<h3>Arte aprovada</h3><div class="peca-artes" id="peca-artes-aprovadas">${lista.map((d, i) =>
      `<figure><img class="peca-arte-aprovada" src="${h(d)}" alt="Lâmina aprovada ${i + 1} de ${lista.length}"><figcaption class="sub">${lista.length > 1 ? `Lâmina ${i + 1} de ${lista.length}` : "A arte aprovada"}</figcaption></figure>`).join("")}</div>`;
  if(!ed || p.situacao === "cancelada") return "";
  return `<h3>Arte</h3><p class="sub">A prévia das lâminas em 1080×1350, redesenhada a cada mudança (salva ou não). O que se aprova é exatamente o que aparece aqui.</p>
    <div class="peca-artes" id="peca-artes"></div><div id="peca-artes-avisos"></div>`;
}
/* Desenha as lâminas da prévia (uma caixa por lâmina: a quantidade muda com os cartões e as fotos). O desenho mais novo é o que vale: um
   atrasado não troca as imagens. Devolve as lâminas ({dados, textos, cortes} ou {erro}), [] sem a prévia, ou null se um desenho mais
   novo começou. Nunca lança erro (é chamada sem esperar, depois de desenhar a tela). */
async function montarArtesPeca(){
  const f = $("form[data-form=peca]"), box = $("#peca-artes"); if(!f || !box) return [];
  const vez = E.pauta.arteVez = (E.pauta.arteVez || 0) + 1;
  try{
    const lams = laminasPeca(dadosPeca(f)), imgs = () => [...box.querySelectorAll("img.peca-arte")];
    if(imgs().length !== lams.length || !lams.length)
      box.innerHTML = lams.map((_, i) => `<figure><img class="peca-arte" data-ordem="${i + 1}" data-pendente="1" alt="Lâmina ${i + 1} de ${lams.length} (montando…)">
        <figcaption class="sub">${lams.length > 1 ? `Lâmina ${i + 1} de ${lams.length}` : "A arte"}</figcaption></figure>`).join("")
        || `<p class="sub">Sem lâmina neste formato.</p>`;
    imgs().forEach(i => { i.dataset.pendente = "1"; i.removeAttribute("data-erro"); });
    const feitas = [];
    for(const [i, l] of lams.entries()){
      let r;
      try{ r = await desenharPeca({...l, imagem:l.foto ? (E.pauta.fotos || {})[l.foto] || null : null}); }
      catch(e){ r = {erro:e.message || "Não foi possível montar a lâmina."}; }
      if(E.pauta.arteVez !== vez) return null;
      const img = imgs()[i]; if(!img) return null;
      if(r.dados){ img.src = r.dados; img.removeAttribute("data-pendente"); img.alt = img.alt.replace(" (montando…)", ""); }
      else img.dataset.erro = r.erro;
      feitas.push(r);
    }
    const avisos = $("#peca-artes-avisos");
    if(avisos) avisos.innerHTML = feitas.map((r, i) => r.erro ? `<div class="aviso erro arte-erro">Lâmina ${i + 1}: ${h(r.erro)}</div>`
      : r.cortes.length ? `<div class="aviso ${r.cortes.includes("identificacao") ? "erro" : "alerta"} arte-corte">${h(msgCortePeca(i + 1, r.cortes))}</div>` : "").join("");
    return feitas;
  }catch(e){ return E.pauta.arteVez === vez ? [{erro:e.message || "Não foi possível montar a arte."}] : null; }
}
/* Um campo da arte mudou (texto, cartão, pessoa, informação da agenda, tipo ou formato): as lâminas ficam pendentes e são redesenhadas
   400 ms depois da última mudança; o desenho que estava em andamento deixa de valer */
function pecaArteMudou(){
  if(!$("#peca-artes")) return;
  E.pauta.arteVez = (E.pauta.arteVez || 0) + 1;
  document.querySelectorAll("#peca-artes img.peca-arte").forEach(i => { i.dataset.pendente = "1"; i.removeAttribute("data-erro"); });
  clearTimeout(E.pauta.arteRelogio); E.pauta.arteRelogio = setTimeout(() => montarArtesPeca(), 400);
}
/* As lâminas desenhadas agora (para conferir e aprovar): as mesmas que ficam na tela */
async function artesDaTela(){
  clearTimeout(E.pauta.arteRelogio);
  const feitas = await montarArtesPeca();
  if(!feitas) throw new ErroApi("A arte mudou enquanto era desenhada: confira as lâminas e clique de novo.");
  const falha = feitas.find(r => r.erro); if(falha) throw new ErroApi(falha.erro);
  return feitas;
}

/* --------------------------------------------- termos que a Pauta não publica (TERMOS_PECA) */
/* Na Pauta (a peça fala da Artecon, não é notícia), todos estes termos TRAVAM a aprovação e a cópia, além das travas da lista
   compartilhada (TERMOS_PUBLICIDADE): mercantilização, preço, promessa, superlativo, comparação, medo e outros (a lista do plano de
   publicações, regras legais, seção 10; a confirmar com o contador responsável). A palavra que também é termo técnico da contabilidade
   fica de fora só no sentido técnico: “desconto do INSS”, “desconto simplificado”, o desconto perto de INSS, IRRF, parcela, 13º, folha,
   salário ou vale-transporte (“a 1ª parcela não tem esses descontos”), “garantia de emprego”, “mês de referência”, “fórmula de
   cálculo”. A mesma lista vai na função radar-ia (Gerar com IA da peça): mantenha as duas iguais. */
const TERMOS_PECA = [
  ["mercantilização", "gr[áa]tis|gratuit[oa]s?|de gra[çc]a|sem custo|cortesias?|vale-brindes?|brindes?|ganhe|b[ôo]nus|(?:de|um|como) presentes?|" +
    "descontos?(?! (?:do|de|no|na|em) (?:INSS|IRRF|IR|vale-transporte|sal[áa]rio|folha))(?! simplificado)" +
    // o desconto da folha, a até uns 40 caracteres de INSS, IRRF, parcela, 13º, folha, salário ou vale-transporte, é informação
    "(?![^\\n]{0,40}?(?<![\\p{L}\\p{N}])(?:INSS|IRRF|parcelas?|13[º°]|d[ée]cimo terceiro|folha|sal[áa]rios?|vale-transporte|contracheques?|holerites?)(?![\\p{L}\\p{N}]))" +
    "(?<!(?<![\\p{L}\\p{N}])(?:INSS|IRRF|parcelas?|13[º°]|d[ée]cimo terceiro|folha|sal[áa]rios?|vale-transporte|contracheques?|holerites?)(?![\\p{L}\\p{N}])[^\\n]{0,40}?descontos?)|" +
    "promo[çc](?:ão|ões)|ofertas?|" +
    "imperd[íi]ve(?:l|is)|por tempo limitado|chance [úu]nica|sorteios?"],
  ["preço", "R\\$\\s?\\d[\\d.,]*[^\\n]{0,30}?(?:honor[áa]rios?|mensalidades?|planos?|pacotes?)|(?:honor[áa]rios?|mensalidades?|planos?|pacotes?|a partir de)[^\\n]{0,30}?R\\$\\s?\\d[\\d.,]*"],
  ["promessa", "garantimos|garante|garantia de(?! emprego)|pague menos|reduza (?:os |seus |os seus )?impostos?|economize|mais lucro|sem multas?|blindagem|" +
    "blindad[oa]s?|prote[çc][ãa]o total"],
  ["superlativo", "o melhor|os melhores|o maior|n[º°]\\s?1|n[úu]mero 1|l[íi]der(?:es)?|(?<!de )refer[êe]ncia|excel[êe]ncia|premium|nota m[áa]xima|100\\s?%|" +
    "definitiv[oa]s?|a [úu]nica forma|o [úu]nico caminho"],
  ["comparação", "melhor que|mais barat[oa]s?|menor pre[çc]o|diferente dos outros|outros escrit[óo]rios|seu contador atual|(?:troque|mude) de contador|" +
    "insatisfeit[oa]s? com (?:o )?seu contador|contador de verdade|s[óo] envia guias|baratinh[oa]s?|segunda opini[ãa]o"],
  ["medo", "alerta m[áa]ximo|vai parar|fal[êe]ncia|antes que seja tarde|bater [àa] sua porta|multas pesadas"],
  ["outros", "consultoria jur[íi]dica|assessoria jur[íi]dica|parecer jur[íi]dico|comunicado oficial|Receita informa|segredos?|f[óo]rmulas?(?! de c[áa]lculo)|" +
    "truques?|a maioria|milhares de empresas|centenas de clientes"]];
// os termos achados (em minúsculas, sem repetir), na ordem da lista
// @ts-ignore (a tela é JavaScript puro: o texto é o mesmo nos dois arquivos, sem os tipos)
const termosPeca = (...textos) => { const t = textos.join("\n"), r = [];
  for(const [, e] of TERMOS_PECA) for(const m of t.match(new RegExp("(?<![\\p{L}\\p{N}])(?:" + e + ")(?![\\p{L}\\p{N}])", "giu")) || []){
    // @ts-ignore (idem: r é a lista dos termos achados)
    const x = m.toLowerCase().replace(/\s+/g, " "); if(!r.includes(x)) r.push(x); }
  return r; };

/* -------------------------------------------------- conferência, aprovação e publicação */
const LUGAR_PECA = {instagram:"na legenda do Instagram", facebook:"na legenda do Facebook", chamada:"na chamada da arte", apoio:"na linha de apoio da arte",
  roteiro:"no roteiro do reel"};
const msgTermosPeca = (onde, acao = "aprovar") => `Troque antes de ${acao}: ${onde.map(([lugar, termos]) => `${termos.map(t => `“${t}”`).join(", ")} ${LUGAR_PECA[lugar] || lugar}`).join("; ")}. ` +
  "A publicidade da profissão contábil informa, não vende: sem preço, desconto, brinde ou promoção, sem promessa de resultado ou de economia, " +
  "sem superlativo, sem comparação com outros escritórios ou contadores e sem apelo ao medo. Reescreva e salve.";
/* Os textos da peça que vão ao ar, com o lugar de cada um (os canais: os que vão, ou os que têm legenda). Na Agenda da semana em
   Imagem 4:5, a lista desenhada na lâmina (a informação de cada conferida, como em laminasPeca) também vai ao ar */
function textosDaPeca(f, canais){
  const v = n => f.elements[n]?.value || "";
  const naAgenda = (f.elements.tipo?.value || f.dataset.tipo) === "agenda" && (f.elements.formato?.value || f.dataset.formato) === "imagem";
  return [...(canais || ["instagram", "facebook"].filter(k => v("legenda_" + k).trim())).map(k => [k, v("legenda_" + k)]), ["chamada", v("chamada")], ["apoio", v("apoio")],
    ...[...f.querySelectorAll("#peca-cartoes .cartao-linha")].map((l, i) => [`no cartão nº ${i + 1}`,
      (l.querySelector("[name=cartao-titulo]")?.value || "") + "\n" + (l.querySelector("[name=cartao-texto]")?.value || "")]),
    ...(naAgenda ? [...f.querySelectorAll("#peca-conferidas [name=conf-informacao]")].map((c, i) => [`na linha ${i + 1} da agenda (na arte)`, c.value]) : []),
    ["roteiro", v("roteiro")]].filter(([, t]) => t.trim());
}
/* A conferência antes de marcar como pronta e de aprovar (a peça salva): a lista do banco (radar_pauta_conferir: travam) e o que só a
   tela confere — os termos que a publicidade da profissão não usa (as travas da lista compartilhada e todos os de TERMOS_PECA) e a
   identificação que não coube na arte (travam); o texto que não coube na arte, os termos de aviso e o dado sensível (avisos). */
async function conferirPecaTela(f, canais, artes){
  const r = await rpc("radar_pauta_conferir", {p_peca:Number(f.dataset.id), p_canais:canais || null});
  const travas = (Array.isArray(r?.problemas) ? r.problemas : []).map(String), avisos = [], onde = textosDaPeca(f, canais);
  const achados = onde.map(([lugar, t]) => [lugar, [...new Set([...termosPublicidade(t).trava, ...termosPeca(t)])]]).filter(([, l]) => l.length);
  if(achados.length) travas.push(msgTermosPeca(achados));
  (artes || []).forEach((a, i) => { if((a.cortes || []).includes("identificacao")) travas.push(msgCortePeca(i + 1, ["identificacao"]));
    const outros = (a.cortes || []).filter(k => k !== "identificacao"); if(outros.length) avisos.push(msgCortePeca(i + 1, outros)); });
  const travados = achados.flatMap(([, l]) => l), aviso = termosPublicidade(...onde.map(([, t]) => t)).aviso.filter(x => !travados.some(y => y.includes(x)));
  if(aviso.length) avisos.push(`Termos que a publicidade contábil evita: ${aviso.map(t => `“${t}”`).join(", ")}. Confira se é informação, e não propaganda.`);
  // v0.22.0: no reel, a fala transcrita (o texto da legenda gravada no vídeo) passa pelos mesmos termos, e a duração acima do limite
  if(typeof conferenciaDoVideo === "function"){ const v = conferenciaDoVideo(); travas.push(...v.travas); avisos.push(...v.avisos); }
  if((f.elements.tipo?.value || f.dataset.tipo) === "data_equipe")
    avisos.push("Data com a equipe: confira se não há dado sensível (saúde, religião, origem); com dado sensível, só com termo específico (v0.22.0).");
  return {travas, avisos};
}
/* A lista da conferência na peça (o banco e a tela): o que trava em vermelho, o que é só para conferir em amarelo */
function mostrarConferencia(r, titulo){
  const box = $("#peca-conferencia"); if(!box) return;
  box.innerHTML = `<h3>${h(titulo)}</h3>` + (r.travas.length
      ? `<div class="aviso erro"><b>${r.travas.length} ponto(s) a resolver:</b><ul class="pauta-erros">${r.travas.map(t => `<li>${h(t)}</li>`).join("")}</ul></div>`
      : `<div class="aviso info">Nada a resolver: a peça pode ficar pronta e ser aprovada.</div>`) +
    (r.avisos.length ? `<div class="aviso alerta"><b>Para conferir:</b><ul class="pauta-erros">${r.avisos.map(t => `<li>${h(t)}</li>`).join("")}</ul></div>` : "");
  box.hidden = false; box.scrollIntoView({block:"nearest"});
}
/* O dia e a hora da peça como a confirmação mostra: "sáb, 31/10/2026, às 09:30" (de Brasília) */
const quandoPeca = (data, hora) => `${dataCurta(data)}/${data.slice(0, 4)}, às ${String(hora).slice(0, 5)}`;
const passouDaHora = (data, hora) => Date.parse(`${data}T${String(hora).slice(0, 5)}:00-03:00`) < Date.now();     // Brasília: sem horário de verão
// o Instagram antes do Facebook (como em toda a tela); no mesmo canal, o envio mais antigo antes
const ordemCanal = (x, y) => (x.canal === "instagram" ? 0 : 1) - (y.canal === "instagram" ? 0 : 1) || x.id - y.id;
/* A agenda automática não vai publicar sozinha? (desligada nas Configurações, sem o sql/radar-redes-agenda.sql, ou pausada no pg_cron) */
const agendaParada = ag => ag?.agenda_ligada === false || ag?.instalada === false || ag?.ativa === false;
/* O quadro de aprovação (só o administrador, peça pronta): os canais (os que têm legenda), o modo (agendar ou à mão; v0.42.0: o
   carrossel e o carrossel de fotos também agendam — a radar-redes v0.42.0 publica as lâminas; só o reel continua à mão) e as
   conferências obrigatórias. "Confirmar" confere tudo de novo, guarda as lâminas da tela e aprova (radar_pauta_aprovar). */
function blocoAprovar(p){
  const canais = ["instagram", "facebook"].filter(k => (p["legenda_" + k] || "").trim()), soMao = !["imagem", "foto", "carrossel", "carrossel_fotos"].includes(p.formato);
  // um envio caiu no meio (pode ter saído) ou a aprovação à mão foi desfeita (pode ter sido postada): o administrador confere na rede
  const caiu = (p.radar_redes_envios || []).some(e => e.situacao === "cancelado" && e.enviado_em && !e.post_id), mao = !!p.manual_desfeita_em;
  const caixa = (k, t) => `<label><input type="checkbox" class="aprovar-conf" value="${k}" data-texto="${h(t)}"> ${h(t)}</label>`;
  // a das pessoas em toda peça (o banco pede): o nome escrito de um jeito que a conferência não reconhece só quem aprova vê
  // v0.22.0: no reel, o vídeo (o que só quem assiste vê) e, se uma pessoa marcada pediu no termo para ver a peça antes, a caixa dela
  // varredura geral (v0.22.0): também quem estava marcada quando o vídeo foi enviado e foi desmarcada depois (continua no vídeo: o
  // banco pede a caixa dela, radar_pauta_aprovar); antes a caixa não aparecia e o banco recusava (RADAR314) sem saída na tela
  const doVideo = p.formato === "reel" && typeof estadoVideo === "function" && estadoVideo().peca === p.id
    && Array.isArray(estadoVideo().atual?.pessoas) ? estadoVideo().atual.pessoas : [];
  const quer = p.formato === "reel" && [...p.pessoas, ...doVideo].some(id => (E.pauta.pessoas || {})[id]?.quer_ver_peca);
  const caixas = [caixa("pessoas", "Conferi: nas fotos e nos textos só aparecem as pessoas marcadas (ou ninguém)"),
    p.formato === "reel" ? caixa("video", "Conferi o vídeo: só aparecem as pessoas marcadas; sem tela, documento ou cliente ao fundo; só a voz") : "",
    quer ? caixa("viu", "A pessoa viu o vídeo final (ela pediu no termo para ver a peça antes)") : "",
    p.tipo === "agenda" ? caixa("datas", "Conferi as datas da agenda") : "",
    caiu || mao ? caixa("rede", "Conferi no Instagram e no Facebook: não saiu" + (mao && !caiu ? " (nem foi postada à mão)" : "")) : ""].join("");
  return `<details class="painel peca-aprovar" id="peca-aprovar"><summary><b>Aprovar a peça</b></summary>
    <p class="sub">Vai ao ar o que está na tela: as lâminas desenhadas aqui (guardadas na aprovação) e as legendas salvas. Aprovada, a peça não muda; para mudar, Desfazer aprovação.</p>
    <fieldset class="checks"><legend>Canais</legend>${["instagram", "facebook"].map(k => `<label><input type="checkbox" class="aprovar-canal" value="${k}"${canais.includes(k) ? " checked" : " disabled"}>
      ${NOME_REDE[k]}${canais.includes(k) ? "" : " (sem legenda)"}</label>`).join("")}</fieldset>
    <fieldset class="checks"><legend>Como sai</legend>
      <label><input type="radio" name="aprovar-modo" value="agendar"${soMao ? " disabled" : " checked"}> Agendar para ${h(quandoPeca(p.data, p.hora))} (Brasília): a agenda do banco publica</label>
      <label><input type="radio" name="aprovar-modo" value="manual"${soMao ? " checked" : ""}> Vou publicar à mão (baixar ${p.formato === "reel" ? "o vídeo" : "as lâminas"} e copiar a legenda)</label>
      ${soMao ? `<span class="sub">O reel sai à mão nesta versão.</span>` : ""}</fieldset>
    ${caixas ? `<fieldset class="checks"><legend>Conferências</legend>${caixas}</fieldset>` : ""}
    <div class="acoes"><button class="btn verde" type="button" data-acao="peca-aprovar" data-id="${p.id}">Confirmar a aprovação</button></div></details>`;
}
/* A peça aprovada: como sai, o andamento de cada canal e o que dá para fazer. Agendada: Publicar agora e Tentar de novo (o administrador;
   a nova tentativa pede “Conferi … não saiu”), Não publicar neste canal (o que espera a hora ou deu erro: o outro canal pode já ter
   saído), Cancelar o envio parado e Excluir da rede. À mão: baixar as lâminas, copiar a legenda e o roteiro e registrar o link, só nos
   canais aprovados (editor e administrador). Desfazer aprovação: editor e administrador (à mão, com “Conferi … não foi postada”). */
function blocoAprovada(p){
  const adm = ehAdmin(), ed = podeEditar(), manual = p.aprovado_modo === "manual";
  const canais = ["instagram", "facebook"].filter(k => (Array.isArray(p.aprovado_canais) ? p.aprovado_canais : []).includes(k));
  const envios = (p.radar_redes_envios || []).filter(e => e.situacao !== "cancelado").sort(ordemCanal);
  const minutos = v => (Date.now() - new Date(v).getTime()) / 60000;
  const linha = e => { const nome = NOME_REDE[e.canal] || e.canal, s = e.situacao;
    const texto = s === "autorizado" ? (minutos(e.agendado_para) > 20 ? `atrasada: agendada para ${horaBrasilia(e.agendado_para)} e ainda não saiu (a agenda do banco está parada?)`
        : minutos(e.agendado_para) >= 0 ? "saindo agora (na próxima rodada da agenda do banco)" : `agendada para ${horaBrasilia(e.agendado_para)} (Brasília)`)
      : s === "enviando" ? `publicando desde ${horaBrasilia(e.enviado_em)}` + (minutos(e.enviado_em) > 10 ? `: parada há mais de 10 minutos; confira no ${nome} se saiu antes de cancelar` : "")
      : s === "publicado" ? `publicada em ${horaBrasilia(e.publicado_em)}` : s === "erro" ? "não saiu (o motivo está no alto da peça)" : s === "excluido" ? "excluída da rede" : s;
    const botao = !adm ? "" : s === "enviando" && minutos(e.enviado_em) > 10 ? `<button class="btn peq sec" type="button" data-acao="cancelar-rede" data-envio="${e.id}">Cancelar</button>`
      : s === "publicado" ? `<button class="btn peq perigo" type="button" data-acao="peca-excluir" data-envio="${e.id}" data-canal="${h(e.canal)}">Excluir do ${h(nome)}</button>`
      : s === "autorizado" || s === "erro" ? botaoNaoPublicar(e) : "";
    return `<li data-envio="${e.id}" data-situacao="${h(s)}"><b>${h(nome)}:</b> ${h(texto)}${s === "publicado" && e.url ? " — " + linkFonte(e.url, "ver o post") : ""} ${botao}</li>`; };
  const registrado = ["instagram", "facebook"].filter(k => p["link_" + k]);
  const falta = canais.filter(k => !p["link_" + k]);
  const desde = p.aprovado_em ? new Date(p.aprovado_em).toLocaleDateString("en-CA", {timeZone:"America/Sao_Paulo"}) : "";
  const semCanal = !manual && !envios.length;                      // todos os canais em "Não publicar neste canal": nada vai sair
  return `<div class="painel peca-aprovada" id="peca-aprovada-quadro"><h2>${manual ? "Aprovada para publicar à mão" : semCanal ? "Aprovada, sem canal: não vai sair" : "Aprovada: sai pela agenda"}</h2>
    <p class="sub">Aprovada em ${h(horaBrasilia(p.aprovado_em))} (Brasília).${manual ? ` ${p.formato === "reel" ? "Baixe o vídeo aprovado, copie a legenda" : p.artes.length ? "Baixe as lâminas, copie a legenda" : "Copie a legenda e o roteiro"}, poste ` +
      `no ${canais.map(k => NOME_REDE[k]).join(" e no ")} e registre o link aqui.` : ""}</p>
    ${semCanal ? `<div class="aviso alerta" id="peca-sem-canal">Nenhum canal vai sair: a publicação de cada canal foi cancelada (Não publicar neste canal). Para publicar, use Desfazer aprovação e aprove de novo.</div>` : ""}
    ${envios.length ? `<ul class="peca-envios">${envios.map(linha).join("")}</ul>` : ""}
    ${adm && !manual && envios.some(e => e.situacao === "autorizado") ? `<div class="acoes"><button class="btn" type="button" data-acao="peca-publicar-agora">Publicar agora</button>
      <span class="sub">Só remarca a hora para agora: confere tudo de novo antes de sair.</span></div>` : ""}
    ${adm && envios.some(e => e.situacao === "erro") ? `<div class="acoes peca-tentar"><label><input type="checkbox" id="peca-conferi-rede"> Conferi no Instagram e no Facebook: não saiu</label>
      <button class="btn" type="button" data-acao="peca-tentar-de-novo">Tentar de novo</button></div>` : ""}
    ${manual && ed ? `<div class="acoes">${p.artes.length ? `<button class="btn sec" type="button" data-acao="peca-baixar">Baixar as lâminas</button>` : ""}
      ${p.formato === "reel" && p.video_sha256 && typeof botaoBaixarVideo === "function" ? botaoBaixarVideo(p) : ""}
      ${canais.map(k => `<button class="btn sec" type="button" data-acao="peca-copiar-legenda" data-canal="${k}">Copiar legenda do ${NOME_REDE[k]}</button>`).join("")}
      ${p.roteiro ? `<button class="btn sec" type="button" data-acao="peca-copiar-roteiro">Copiar roteiro</button>` : ""}</div><div id="peca-copia"></div><div id="peca-baixar"></div><div id="video-baixar"></div>` : ""}
    ${manual && registrado.length ? `<p id="peca-registro">Publicada à mão em ${h(dataAgenda(p.publicado_manual_em))}: ${registrado.map(k => `${NOME_REDE[k]} (${linkFonte(p["link_" + k], "ver o post")})`).join(" · ")}.</p>` : ""}
    ${manual && ed && falta.length ? `<form class="peca-registro" data-form="pecaRegistrar" data-id="${p.id}"><h3>${registrado.length ? "Registrar o outro canal" : "Depois de postar: registrar a publicação"}</h3>
      <div class="grade">${falta.map(k => `<div><label for="peca-link-${k}">Link do post no ${NOME_REDE[k]}</label><input id="peca-link-${k}" type="url" name="link_${k}" maxlength="500" placeholder="https://www.${k}.com/…"></div>`).join("")}
        <div><label for="peca-data-manual">Postada em</label><input id="peca-data-manual" type="date" name="data" required value="${hojeBrasilia()}"${desde ? ` min="${desde}"` : ""} max="${hojeBrasilia()}"></div></div>
      <div class="acoes"><button class="btn">Registrar a publicação</button></div></form>` : ""}
    ${ed ? `<div class="acoes peca-desfazer">${manual ? `<label><input type="checkbox" id="peca-conferi-mao"> Conferi no Instagram e no Facebook: não foi postada à mão</label>` : ""}
      <button class="btn sec" type="button" data-acao="peca-desaprovar">Desfazer aprovação</button></div>` : ""}</div>`;
}
/* "Não publicar neste canal" (só o administrador): o envio que espera a hora ou que deu erro é cancelado; a peça continua aprovada e o
   outro canal fica como está (radar_cancelar_rede) */
const botaoNaoPublicar = e => `<button class="btn peq sec" type="button" data-acao="peca-nao-publicar-canal" data-envio="${e.id}" data-canal="${h(e.canal)}" data-situacao="${h(e.situacao)}">Não publicar neste canal</button>`;
/* Copiar e baixar (só na peça aprovada para publicar à mão): o banco confere a versão, o canal (só os aprovados) e o termo de cada pessoa
   HOJE (radar_pauta_pode_copiar). "canal": a legenda daquele canal; sem ele, as lâminas e o roteiro (valem para os canais aprovados). */
async function podeCopiarPeca(canal){
  const f = $("form[data-form=peca]"); if(!f) throw new ErroApi("Abra a peça de novo.");
  const r = await rpc("radar_pauta_pode_copiar", {p_peca:Number(f.dataset.id), p_lido:f.dataset.lido, p_canal:canal || null});
  if(!r?.ok) throw new ErroApi(r?.motivo || "Não dá para copiar agora: recarregue a peça e confira.");
  return {f, artes:Array.isArray(r.artes) ? r.artes : []};
}
/* Copiar à mão: a conferência do banco vai DENTRO da cópia (ClipboardItem com a promessa do texto). O Safari (todo navegador do iPhone) só
   deixa escrever na área de transferência durante o toque; depois de esperar o banco, recusaria. Sem ClipboardItem, a cópia vem depois da
   conferência. Recusada a cópia (só ela: o que o banco ou os termos recusam vira o erro de sempre), o texto aparece logo abaixo dos
   botões, num campo só de leitura, para selecionar e copiar. Devolve true se copiou. */
async function copiarDaPeca(conferir){
  const conferido = conferir();
  conferido.catch(() => {});                                        // o erro da conferência é tratado abaixo (await conferido)
  let copiou = false;
  if(typeof ClipboardItem === "function" && navigator.clipboard?.write){
    try{ await navigator.clipboard.write([new ClipboardItem({"text/plain": conferido.then(t => new Blob([t], {type:"text/plain"}))})]); copiou = true; }
    catch(e){}
  }
  const texto = await conferido;
  if(!copiou){ try{ await navigator.clipboard.writeText(texto); copiou = true; }catch(e){} }
  const box = $("#peca-copia"); if(box) box.innerHTML = "";
  if(copiou) return true;
  if(box){ box.innerHTML = `<label for="peca-copia-texto">O navegador não deixou copiar: selecione o texto abaixo e copie</label>
      <textarea id="peca-copia-texto" readonly rows="8">${h(texto)}</textarea>`;
    const t = $("#peca-copia-texto"); t.focus(); t.select(); }
  recado("O navegador não deixou copiar: o texto aprovado está logo abaixo dos botões; selecione e copie (sem redigitar).", true);
  return false;
}
/* Publicar agora e Tentar de novo: o banco remarca a hora para agora (e confere de novo). Com a agenda automática rodando, ela publica
   em até 5 minutos; sem ela, a tela chama a função radar-redes para cada canal, um depois do outro, com um recado só no fim. */
async function publicarPecaAgora(conferi){
  const f = $("form[data-form=peca]"); if(!f) return;
  const ids = await rpc("radar_pauta_publicar_agora", {p_peca:Number(f.dataset.id), p_conferi_rede:conferi});
  const ag = await rpc("radar_agenda_situacao").catch(() => ({}));
  if(!agendaParada(ag) && ag?.instalada){ await desenhar(); recado("Remarcada para agora: a agenda do banco publica em até 5 minutos. Abra a peça de novo depois para ver o link."); return; }
  const envios = (await ler("radar_redes_envios", {select:"id,canal", id:"in.(" + (ids || []).join(",") + ")", order:"id"})).sort(ordemCanal);
  const res = [];
  for(const e of envios) res.push(await publicarRede(e.id, e.canal, false));
  await desenhar(); recado(res.map(r => r.msg).join(" ") || "Nada a publicar.", res.some(r => !r.ok));
}

/* --------------------------------------------------------------- pessoas e termos */
/* A linha da pessoa na arte, escrita pelo código (nunca pela IA): com a categoria, "Ana, contadora · CRC-SC 000000"; sem ela,
   "Ana · Departamento Pessoal" (só o nome, se não há área) */
const areaPessoa = x => { const area = String(x.area || "").trim(); return !area ? "" : /^(departamento|setor)\b/i.test(area) ? area : "Departamento " + area; };
function linhaPessoa(x){
  const nome = String(x.nome_na_peca || "").trim(), area = areaPessoa(x);
  if(ROTULO_CATEGORIA[x.categoria]) return `${nome}, ${ROTULO_CATEGORIA[x.categoria]}${x.crc ? " · " + x.crc : ""}`;
  return area ? `${nome} · ${area}` : nome;
}
async function telaPessoas(){
  const adm = ehAdmin(), lista = await ler("radar_pessoas", {select:"*", order:"ativo.desc,nome_na_peca,id"});
  // v0.22.0: quem revogou o termo ou ficou inativa: as peças publicadas com ela (os links a retirar das redes no prazo do termo).
  const pecas = await Promise.all(lista.map(x => adm && (!x.ativo || x.termo_revogado_em)
    ? rpc("radar_pauta_pecas_da_pessoa", {p_pessoa:x.id}) : null));
  lista.forEach((x, i) => { x.pecasPublicadas = pecas[i]; });
  return `<button class="voltar" data-acao="voltar">← Voltar para a semana</button>
    <h1>Pessoas e termos</h1>
    <p class="sub">Quem pode aparecer nas peças da Pauta e o termo de uso de imagem de cada pessoa. Fica só no banco (o repositório do Radar é público); o leitor não vê. ${adm ? "" : "Só o administrador cadastra e altera."}</p>
    <div class="aviso info">O termo é <b>assinado na própria tela</b> (com o CPF e a assinatura desenhada pela caneta ou pelo dedo). <b>Todos assinam, sócios inclusive.</b> Cadastre a pessoa, abra o cadastro dela e clique em <b>“Assinar o termo na tela”</b>. Um único termo autoriza o uso da imagem nos canais site, Instagram e Facebook e o corretor de vídeo. Fica guardado como prova (data/hora, CPF e a imagem da assinatura).</div>
    ${adm ? `<details class="nova-pessoa"${lista.length ? "" : " open"}><summary>Cadastrar pessoa</summary>${formPessoa({ativo:true}, true)}</details>` : ""}
    <div class="pessoas-lista">${lista.length ? lista.map(x => formPessoa(x, adm)).join("") : `<p class="sub">Nenhuma pessoa cadastrada.</p>`}</div>`;
}
function formPessoa(x, ed){
  const id = x.id || "nova", des = ed ? "" : " disabled";
  const campo = (nome, rotulo, extra) => `<div><label for="pe-${nome}-${id}">${rotulo}</label><input id="pe-${nome}-${id}" name="${nome}" ${extra} value="${h(x[nome] || "")}"${des}></div>`;
  // v0.46.0: a marca "Sócio(a) da Artecon" é só uma referência; o termo é exigido de todos (sócios inclusive)
  const socio = x.socio ? " " + selo("Sócio(a) da Artecon", "neutro") : "";
  return `<form class="painel pessoa${x.id && !x.ativo ? " inativa" : ""}" data-form="${x.id ? "pessoa" : "novaPessoa"}"${x.id ? ` data-id="${x.id}"` : ""} data-socio="${x.socio ? 1 : 0}">
    ${x.id ? `<h2>${h(x.nome_na_peca)}${x.ativo ? "" : " " + selo("inativa", "neutro")}${socio}</h2>` : ""}
    <div class="grade">
      ${campo("nome", "Nome completo (interno)", 'type="text" required minlength="2" maxlength="80"')}
      ${campo("nome_na_peca", "Nome na peça (como o termo autoriza)", 'type="text" required minlength="2" maxlength="60"')}
      ${campo("area", "Área", 'type="text" maxlength="60" placeholder="Departamento Pessoal"')}
      <div><label for="pe-categoria-${id}">Categoria</label><select id="pe-categoria-${id}" name="categoria"${des}>${opcoes(CATEGORIAS_PESSOA, x.categoria || "")}</select></div>
      ${campo("crc", "Registro no CRC (contador e técnico)", 'type="text" maxlength="40" placeholder="CRC-SC 000000/O-0"')}
    </div>
    ${x.id ? blocoTermoAssinatura(x, ed) : `<p class="sub">Cadastre a pessoa primeiro. Depois abra o cadastro dela e clique em <b>“Assinar o termo na tela”</b> para registrar a assinatura (com o CPF, pela caneta ou pelo dedo na tela).</p>`}
    <fieldset class="checks"><legend>Situação</legend><label><input type="checkbox" name="ativo"${x.ativo !== false ? " checked" : ""}${des}> Ativa (desmarque para tirar a pessoa das próximas peças)</label>
      <label><input type="checkbox" name="socio"${x.socio ? " checked" : ""}${des}> Sócio(a) da Artecon (só uma marca de referência; o termo de uso de imagem é exigido de todos, inclusive dos sócios)</label></fieldset>
    <fieldset class="checks"><legend>Corretor de vídeo (reel)</legend>
      <label><input type="checkbox" name="quer_ver_peca"${x.quer_ver_peca ? " checked" : ""}${des}> Pediu no termo para ver a peça antes (a aprovação do reel pede “A pessoa viu o vídeo final”)</label>
      <label><input type="checkbox" name="menor"${x.menor ? " checked" : ""}${des}> Menor de 18 anos (o corretor de vídeo não aceita nesta versão)</label></fieldset>
    ${x.id ? `<p class="sub linha-pessoa">Como sai na arte: <b>${h(linhaPessoa(x))}</b></p>` : ""}
    ${blocoPecasDaPessoa(x.pecasPublicadas)}
    ${ed ? `<div class="acoes"><button class="btn">${x.id ? "Salvar" : "Cadastrar pessoa"}</button>${x.id ? `<button class="btn peq perigo" type="button" data-acao="pessoa-excluir" data-id="${x.id}">Excluir</button>` : ""}</div>` : ""}
  </form>`;
}
/* v0.46.0: o bloco do termo no cadastro da pessoa — o estado atual (assinado/sem/revogado/vencido), o CPF e os botões de assinar e
   revogar (só o administrador). O termo em si é assinado na janela de assinarTermo (CPF + a assinatura desenhada na tela). */
function blocoTermoAssinatura(x, ed){
  const hoje = hojeBrasilia(), ass = x.termo_assinado_em, rev = x.termo_revogado_em, ate = x.termo_valido_ate;
  const vigente = !!ass && !(rev && rev <= hoje) && !(ate && ate < hoje);
  const quando = iso => `${dataCurta(iso)}/${iso.slice(0, 4)}`;
  const estado = vigente ? `${selo("termo assinado", "ok")} em ${h(quando(ass))}`
    : rev ? `${selo("termo revogado", "erro")} em ${h(quando(rev))}`
    : (ass && ate && ate < hoje) ? `${selo("termo vencido", "erro")} (venceu em ${h(quando(ate))})`
    : selo("sem termo assinado", "alerta");
  return `<div class="aviso ${vigente ? "ok" : "alerta"} termo-assinatura">
    <p style="margin:.2em 0"><b>Termo de uso de imagem:</b> ${estado} · CPF: <b>${x.cpf ? h(formatarCpf(x.cpf)) : "—"}</b></p>
    <p class="sub" style="margin:.2em 0">${vigente
      ? "Autoriza o uso da imagem, voz e nome nos canais site, Instagram e Facebook, e o corretor de vídeo. Um único termo, para todos."
      : "Enquanto não houver o termo assinado, as peças e os vídeos com esta pessoa não ficam prontos nem saem."}</p>
    ${ed ? `<div class="acoes" style="margin-top:8px"><button class="btn peq" type="button" data-acao="pessoa-assinar" data-id="${x.id}">${vigente ? "Assinar de novo" : "Assinar o termo na tela"}</button>${vigente ? `<button class="btn peq sec" type="button" data-acao="pessoa-revogar" data-id="${x.id}">Revogar termo</button>` : ""}</div>` : ""}
  </div>`;
}
/* v0.22.0: as peças publicadas com a pessoa que revogou o termo ou ficou inativa (radar_pauta_pecas_da_pessoa, só o administrador): os
   links a retirar das redes no prazo do termo e se ainda há vídeo dela guardado (a limpeza seguinte apaga). */
function blocoPecasDaPessoa(l){
  if(!Array.isArray(l)) return "";
  if(!l.length) return `<p class="sub pecas-da-pessoa">Nenhuma peça publicada com esta pessoa.</p>`;
  return `<div class="aviso alerta pecas-da-pessoa"><b>Peças publicadas com esta pessoa:</b> retire das redes no prazo do termo.<ul class="pauta-erros">${l.map(x => {
    const links = [["instagram", x.link_instagram], ["facebook", x.link_facebook]].filter(([, u]) => u).map(([k, u]) => `${NOME_REDE[k]} (${linkFonte(u, "ver o post")})`);
    const d = String(x.data || "");
    return `<li>${/^\d{4}-\d{2}-\d{2}$/.test(d) ? h(dataCurta(d) + "/" + d.slice(0, 4)) : "—"}: ${links.join(" · ") || "publicada, sem link registrado"}${x.video_guardado ? " · vídeo ainda guardado (sai na próxima limpeza)" : ""}</li>`; }).join("")}</ul></div>`;
}
/* O que vai ao banco pelo Salvar do cadastro: os dados da pessoa (o termo em si é assinado à parte, em assinarTermo, e grava sozinho as
   datas, o CPF, os canais e as finalidades). O CRC é padronizado por crcFormatado (como o da empresa); "contador(a)" e "técnico(a)" só com
   o registro (o banco também recusa). v0.22.0: "quer ver a peça" e menor de idade. v0.46.0: sem as datas/canais/finalidades à mão. */
function dadosPessoa(f){
  const t = n => f.elements[n].value.trim();
  const corpo = {nome:t("nome"), nome_na_peca:t("nome_na_peca"), area:t("area"), categoria:f.elements.categoria.value, crc:"",
    ativo:f.elements.ativo.checked, quer_ver_peca:f.elements.quer_ver_peca.checked, menor:f.elements.menor.checked,
    socio:f.elements.socio.checked};
  if(corpo.nome.length < 2) throw new ErroApi("Informe o nome completo (interno).");
  if(corpo.nome_na_peca.length < 2) throw new ErroApi("Informe o nome na peça, como o termo autoriza (o nome completo ou só o primeiro).");
  if(t("crc")){ corpo.crc = crcFormatado(t("crc"));
    if(!(/^CRC/.test(corpo.crc) && /\d{4,6}/.test(corpo.crc) && corpo.crc.length <= 40))
      throw new ErroApi("Registro no CRC não reconhecido: escreva como “CRC-SC 012345/O-5” (depois da barra vem a letra O, não o número zero)."); }
  if(corpo.categoria && !corpo.crc) throw new ErroApi("Contador(a) e técnico(a) só com o registro no CRC: preencha o registro ou escolha “Sem registro no CRC”.");
  return corpo;
}
/* v0.46.0: o CPF escrito só com os números, "000.000.000-00" (parcial enquanto digita). */
function formatarCpf(v){
  const d = String(v || "").replace(/\D/g, "").slice(0, 11);
  if(!d) return "";
  let s = d.slice(0, 3);
  if(d.length > 3) s += "." + d.slice(3, 6);
  if(d.length > 6) s += "." + d.slice(6, 9);
  if(d.length > 9) s += "-" + d.slice(9, 11);
  return s;
}
/* v0.46.0: a janela de assinatura do termo (só o administrador). Mostra o texto do termo (de radar_config.termo_imagem, com o nome e o CPF),
   pede o CPF e a assinatura DESENHADA na tela (caneta/dedo/mouse, por pointer events) e grava tudo pela função radar_pessoa_assinar_termo,
   que guarda a prova em radar_pessoas_termos. A imagem da assinatura vai como PNG (data URL). */
async function assinarTermo(idPessoa){
  const [pessoa] = await ler("radar_pessoas", {select:"id,nome,nome_na_peca,cpf", id:"eq." + idPessoa});
  if(!pessoa){ recado("Pessoa não encontrada.", true); return; }
  const [cfg] = await ler("radar_config", {select:"valor", chave:"eq.termo_imagem"});
  if(!cfg?.valor?.texto){ recado("O texto do termo não está configurado no banco: rode o SQL da v0.46.0 (Supabase → SQL Editor).", true); return; }
  const nomeLegal = pessoa.nome || pessoa.nome_na_peca || "";
  const corpoTermo = h(cfg.valor.texto)
    .replace(/\{NOME\}/g, `<b>${h(nomeLegal)}</b>`)
    .replace(/\{CPF\}/g, `<b class="cpf-vivo">___.___.___-__</b>`);
  document.body.insertAdjacentHTML("beforeend", `<div class="fundo-previa" id="assinar-termo"><form class="caixa-previa caixa-assinatura" role="dialog" aria-modal="true" aria-label="Assinar o termo de uso de imagem">
    <div class="barra-previa"><span>Assinar o termo de uso de imagem — ${h(nomeLegal)}</span><button class="btn peq sec" type="button" data-cancelar>Fechar</button></div>
    <div style="padding:16px 18px">
      <div class="termo-texto" style="white-space:pre-wrap;max-height:230px;overflow:auto;border:1px solid #e0e3ea;border-radius:8px;padding:12px 14px;background:#fafbfc;font-size:.92rem;line-height:1.5">${corpoTermo}</div>
      <div style="margin-top:12px"><label for="assinar-cpf">CPF de quem assina</label>
        <input id="assinar-cpf" type="text" inputmode="numeric" autocomplete="off" maxlength="14" placeholder="000.000.000-00" value="${pessoa.cpf ? h(formatarCpf(pessoa.cpf)) : ""}" style="width:100%"></div>
      <label style="display:block;margin-top:12px">Assinatura (desenhe com a caneta, o dedo ou o mouse)</label>
      <div class="assinatura-quadro" style="position:relative;border:1px dashed #9aa4b8;border-radius:8px;background:#fff">
        <canvas id="assinar-quadro" style="display:block;width:100%;height:190px;touch-action:none;cursor:crosshair"></canvas>
        <span class="assinatura-linha" style="position:absolute;left:18px;right:18px;bottom:34px;border-bottom:1px solid #c7ccd8;pointer-events:none"></span></div>
      <div class="acoes" style="margin-top:8px"><button class="btn peq sec" type="button" data-limpar>Apagar e refazer</button></div>
      <p class="sub erro-assinatura" hidden style="color:var(--erro)"></p>
      <div class="acoes" style="margin-top:12px"><button class="btn">Assinar e gravar</button><button class="btn sec" type="button" data-cancelar>Cancelar</button></div>
    </div></form></div>`);
  const caixa = $("#assinar-termo"), form = caixa.querySelector("form"), cv = $("#assinar-quadro"), campoCpf = $("#assinar-cpf");
  const ctx = cv.getContext("2d"), msg = form.querySelector(".erro-assinatura");
  const fim = () => { caixa.remove(); document.removeEventListener("keydown", aoEscape, true); };
  const aoEscape = ev => { if(ev.key === "Escape"){ ev.stopPropagation(); fim(); } };
  const erro = txt => { msg.textContent = txt; msg.hidden = false; };
  // o quadro em pixels de verdade (nítido no celular); fundo branco para a imagem não sair transparente
  let desenhou = false;
  function limpar(){ const r = cv.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.max(1, Math.round(r.width * dpr)); cv.height = Math.max(1, Math.round(r.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, r.width, r.height);
    ctx.lineWidth = 2.2; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#01204a"; desenhou = false; }
  const pos = ev => { const r = cv.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
  let tracando = false, px = 0, py = 0;
  cv.addEventListener("pointerdown", ev => { ev.preventDefault(); tracando = true; desenhou = true; [px, py] = pos(ev);
    ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + 0.1, py + 0.1); ctx.stroke(); try{ cv.setPointerCapture(ev.pointerId); }catch(e){} });
  cv.addEventListener("pointermove", ev => { if(!tracando) return; const [x, y] = pos(ev); ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(x, y); ctx.stroke(); [px, py] = [x, y]; });
  const soltar = () => { tracando = false; };
  cv.addEventListener("pointerup", soltar); cv.addEventListener("pointercancel", soltar); cv.addEventListener("pointerleave", soltar);
  const verCpfVivo = () => caixa.querySelectorAll(".cpf-vivo").forEach(s => { s.textContent = formatarCpf(campoCpf.value) || "___.___.___-__"; });
  campoCpf.addEventListener("input", () => { campoCpf.value = formatarCpf(campoCpf.value); verCpfVivo(); });
  caixa.querySelectorAll("[data-cancelar]").forEach(b => { b.onclick = fim; });
  form.querySelector("[data-limpar]").onclick = limpar;
  document.addEventListener("keydown", aoEscape, true);
  requestAnimationFrame(() => { limpar(); verCpfVivo(); });
  form.onsubmit = async ev => {
    ev.preventDefault(); ev.stopPropagation();
    msg.hidden = true;
    const cpf = (campoCpf.value || "").replace(/\D/g, "");
    if(cpf.length !== 11){ erro("Informe o CPF com os 11 números."); campoCpf.focus(); return; }
    if(!desenhou){ erro("Assine no quadro: desenhe a assinatura com a caneta, o dedo ou o mouse."); return; }
    const b = form.querySelector(".btn"); b.disabled = true;
    try{
      await rpc("radar_pessoa_assinar_termo", {p_pessoa:idPessoa, p_cpf:cpf, p_assinatura:cv.toDataURL("image/png"), p_aparelho:navigator.userAgent});
      fim(); await desenhar(); recado("Termo assinado e guardado.");
    }catch(e){ b.disabled = false; erro(e.message || "Não foi possível gravar a assinatura agora."); }
  };
}

/* ------------------------------------------------- ações e formulários (o index.html junta) */
const PAUTA = {
  // não gravam nada: navegação e mudanças só na tela (o que grava é feito uma ação por vez)
  navegacao:["pauta-semana", "abrir-peca", "pauta-pessoas", "pauta-importar-cancelar", "peca-conf-linha", "peca-conf-remover",
             "peca-cartao-linha", "peca-cartao-remover", "peca-agenda", "peca-completar-legenda", "peca-baixar", "peca-copiar-legenda", "peca-copiar-roteiro",
             "peca-usar-ia", "pauta-nova", "pauta-nova-cancelar"],
  acoes:{
    "pauta-semana"(el){ const passo = Number(el.dataset.passo), base = E.pauta.semana || segundaDe(hojeBrasilia());
      E.pauta.semana = passo ? somarDias(base, 7 * passo) : segundaDe(hojeBrasilia()); E.pauta.nova = null; return desenhar(); },
    "abrir-peca"(el){ E.pauta.peca = Number(el.dataset.id); E.pauta.vista = "semana"; E.pauta.nova = null; window.scrollTo(0, 0); return desenhar(); },
    "pauta-pessoas"(){ E.pauta.vista = "pessoas"; E.pauta.peca = null; E.pauta.nova = null; window.scrollTo(0, 0); return desenhar(); },
    // v0.28.0: "+ Nova peça" abre o formulário no próprio dia (um de cada vez); Cancelar fecha sem gravar. A prévia da importação aberta
    // fecha: o efeito de cada linha foi calculado antes da peça nova (o dia dela diria "nova" e "Gravar" trocaria o que foi digitado)
    "pauta-nova"(el){ const previa = !!E.pauta.previa; E.pauta.nova = el.dataset.dia; E.pauta.previa = null;
      return desenhar().then(() => { $("#pauta-nova")?.scrollIntoView({block:"center"}); $("#pauta-nova [name=tipo]")?.focus();
        if(previa) recado("A prévia da importação do calendário foi fechada, sem gravar nada: depois de criar a peça, escolha o arquivo de novo para ver o que muda.", "aviso"); }); },
    "pauta-nova-cancelar"(){ E.pauta.nova = null; return desenhar(); },
    "pauta-importar-cancelar"(){ E.pauta.previa = null; return desenhar(); },
    async "pauta-importar-gravar"(){
      const pr = E.pauta.previa; if(!pr || pr.erros.length || !pr.linhas.length) return;
      const r = await rpc("radar_pauta_importar", {p_linhas:pr.linhas.map(({efeito, ...l}) => l)});
      // a semana mostrada passa a ser a da primeira peça do arquivo que não ficou para trás (ou a da última, se todas ficaram)
      const agora = segundaDe(hojeBrasilia()), datas = pr.linhas.map(l => l.data).sort();
      E.pauta.previa = null; E.pauta.semana = segundaDe(datas.find(d => d >= agora) || datas[datas.length - 1]);
      await desenhar();
      recado(`Calendário gravado: ${r.novas} peça(s) nova(s), ${r.alteradas} alterada(s), ${r.iguais} igual(is) e ${r.mantidas} mantida(s) (já em produção, não mudam).`);
    },
    "peca-conf-linha"(){ const box = $("#peca-conferidas"); if(!box) return;
      if(box.children.length >= 20){ recado("A peça leva no máximo 20 informações conferidas.", true); return; }
      box.insertAdjacentHTML("beforeend", linhaConferida({}, "")); box.lastElementChild.querySelector("textarea").focus(); },
    "peca-conf-remover"(el){ el.closest(".conf-linha").remove(); pecaArteMudou(); },
    "peca-cartao-linha"(){ const box = $("#peca-cartoes"); if(!box) return;
      if(box.children.length >= 9){ recado("A peça leva no máximo 9 cartões.", true); return; }
      box.insertAdjacentHTML("beforeend", linhaCartao({}, "")); box.lastElementChild.querySelector("input").focus(); },
    "peca-cartao-remover"(el){ el.closest(".cartao-linha").remove(); pecaArteMudou(); },
    "peca-agenda"(el){
      const f = el.closest("form"), dia = f.dataset.data, box = $("#peca-conferidas"); if(!box) return;
      const linhas = agendaDaSemana(dia), de = somarDias(dia, 1), ate = somarDias(dia, 7);     // v0.30.0: até o domingo
      if(!linhas.length){ recado(`Não há vencimento de ${dataCurta(de)} a ${dataCurta(ate)} pelas regras das Configurações (Agenda de obrigações).`, true); return; }
      if([...box.querySelectorAll("textarea, input")].some(c => c.value.trim()) && !confirm("Trocar as informações conferidas desta tela pela agenda calculada?")) return;
      box.innerHTML = linhas.slice(0, 20).map(c => linhaConferida(c, "")).join(""); pecaArteMudou();
      const semFonte = linhas.slice(0, 20).filter(c => !c.fonte).length;
      recado(`Agenda calculada: ${linhas.length} vencimento(s) de ${dataCurta(de)} a ${dataCurta(ate)}${diaDaSemana(dia) ? " (a peça não é de domingo: confira a semana)" : ""}. ` +
        (linhas.length > 20 ? `Só cabem 20: ficaram de fora ${linhas.length - 20}. ` : "") + "Confira as datas na fonte oficial, ajuste o que precisar" +
        (semFonte ? `, escreva a fonte de ${semFonte === 1 ? "1 vencimento" : semFonte + " vencimentos"} (ficou em branco)` : "") + " e salve.",
        linhas.length > 20 || diaDaSemana(dia) || semFonte ? "aviso" : false);
    },
    "peca-completar-legenda"(el){
      const t = $(`#peca-legenda-${el.dataset.canal}`); if(!t || t.disabled) return;
      const ident = linhaIdentificacao();
      if(!t.value.trim()){ recado("Escreva a legenda antes: a identificação legal e as hashtags vão no fim dela.", true); return; }
      if(faltaIdentificacao().length){ recado(`A identificação legal está incompleta: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura (o administrador preenche).`, true); return; }
      if(t.value.includes(ident)){ recado("A identificação legal já está nesta legenda."); return; }
      t.value = comporLegenda(t.value, hashtagsPauta().filter(x => !t.value.includes(x)).join(" "), 2200);
      contarPeca(t); recado("Identificação legal e hashtags no fim da legenda. Confira e salve.");
    },
    async "peca-foto-mover"(el){
      const f = el.closest("form"), fotos = JSON.parse(f.dataset.fotos || "[]"), i = fotos.indexOf(Number(el.dataset.foto)), j = i + Number(el.dataset.passo);
      if(i < 0 || j < 0 || j >= fotos.length) return;
      [fotos[i], fotos[j]] = [fotos[j], fotos[i]];
      await gravarFotosPeca(f, fotos);
    },
    async "peca-foto-tirar"(el){
      const f = el.closest("form"), fotos = JSON.parse(f.dataset.fotos || "[]");
      if(!confirm("Tirar esta foto da peça?")) return;
      await gravarFotosPeca(f, fotos.filter(x => x !== Number(el.dataset.foto))); recado("Foto tirada da peça.");
    },
    /* Conferir (sem mudar nada): a lista do banco e a da tela, sobre a peça salva */
    async "peca-conferir"(el){
      const f = el.closest("form[data-form=peca]");
      if(pecaMudou(f)) throw new ErroApi(avisoPecaSuja(f, "Há alterações não salvas: salve antes de conferir (a conferência é feita na peça salva)."));
      mostrarConferencia(await conferirPecaTela(f, null, await artesDaTela()), "Conferência da peça");
    },
    /* "Salvar e marcar como pronta": salva o que mudou, confere (o banco e a tela) e, sem nada a resolver, a peça fica pronta para o
       administrador aprovar; com algo a resolver, a lista aparece na peça (o que foi salvo continua salvo) */
    async "peca-salvar-pronta"(el){
      const f0 = el.closest("form[data-form=peca]");
      if(!f0.reportValidity()) throw new ErroApi("Confira os campos da peça.");
      const corpo = corpoDaPeca(f0), salvou = Object.keys(corpo).length > 0;
      if(salvou){ await gravarPeca(f0, corpo); await desenhar(); }
      const f = $("form[data-form=peca]"); if(!f || f.dataset.id !== f0.dataset.id) return;
      const r = await conferirPecaTela(f, null, await artesDaTela());
      mostrarConferencia(r, "O que falta para a peça ficar pronta");
      if(r.travas.length){ recado(`${salvou ? "Peça salva, mas ainda não" : "A peça ainda não"} fica pronta: há ${r.travas.length} ponto(s) a resolver (a lista está na peça).`, true); return; }
      await rpc("radar_pauta_marcar_pronta", {p_peca:Number(f.dataset.id), p_lido:f.dataset.lido});
      await desenhar(); recado("Peça pronta: falta o administrador aprovar (Pauta → Prontas para aprovar).");
      if(r.avisos.length) mostrarConferencia(r, "Pronta. Para conferir antes da aprovação");
    },
    /* Aprovar (só o administrador): tudo salvo; as caixas; a conferência do banco e da tela sem nada a resolver; a confirmação com o dia
       e a hora (e o aviso da agenda desligada); as lâminas da tela guardadas uma por vez em radar_imagens; e radar_pauta_aprovar, que
       confere tudo de novo. À mão (o reel nesta versão, ou quem preferir), não cria envio: libera baixar e copiar. */
    async "peca-aprovar"(){
      const f = $("form[data-form=peca]"), painel = $("#peca-aprovar"); if(!f || !painel) return;
      if(pecaMudou(f)) throw new ErroApi(avisoPecaSuja(f));
      const canais = [...painel.querySelectorAll(".aprovar-canal:checked:not(:disabled)")].map(c => c.value);
      const modo = painel.querySelector("input[name=aprovar-modo]:checked:not(:disabled)")?.value, caixas = [...painel.querySelectorAll(".aprovar-conf")];
      if(!canais.length) throw new ErroApi("Marque o Instagram, o Facebook ou os dois (só os canais com legenda).");
      if(!modo) throw new ErroApi("Escolha como a peça sai: agendar ou publicar à mão.");
      const falta = caixas.filter(c => !c.checked);
      if(falta.length) throw new ErroApi("Marque antes: " + falta.map(c => `“${c.dataset.texto}”`).join(" e ") + ".");
      // v0.22.0: o reel sai com o vídeo que o administrador abriu na prévia (o hash dele vai na aprovação; o banco confere com o pronto)
      if(E.pauta.aberta?.formato === "reel" && typeof videoParaAprovar !== "function") throw new ErroApi("O arquivo radar-video.js (o corretor de vídeo) não carregou: aperte Ctrl+F5.");
      const sha = E.pauta.aberta?.formato === "reel" ? videoParaAprovar() : null;
      const artes = await artesDaTela(), r = await conferirPecaTela(f, canais, artes);
      if(r.travas.length){ mostrarConferencia(r, "O que falta para aprovar"); recado(`Há ${r.travas.length} ponto(s) a resolver antes de aprovar: a lista está na peça.`, true); return; }
      const a = E.pauta.aberta, nomes = canais.map(k => NOME_REDE[k]).join(" e no "), ag = await rpc("radar_agenda_situacao").catch(() => ({}));
      const pergunta = modo === "agendar"
        ? `Vai ao ar exatamente o que está na tela, no ${nomes}, em ${quandoPeca(a.data, a.hora)} (horário de Brasília).` +
          (passouDaHora(a.data, a.hora) ? "\n\nA hora marcada já passou: a peça sai na próxima rodada da agenda (em até 5 minutos)." : "") +
          (agendaParada(ag) ? "\n\nA agenda automática está DESLIGADA: a peça só sai se alguém clicar em Publicar agora." : "")
        : `Aprovar para publicar à mão no ${nomes}? Depois de aprovada, a peça libera baixar ${sha ? "o vídeo" : "as lâminas"} e copiar a legenda; quem postar registra o link aqui.` +
          (sha ? "\n\nO vídeo aprovado é o que você viu na prévia (o arquivo fica amarrado à peça)." : "");
      if(!confirm(pergunta + (r.avisos.length ? "\n\nConfira também:\n- " + r.avisos.join("\n- ") : ""))) return;
      const ids = [];
      for(const [i, x] of artes.entries()){
        recado(`Guardando a lâmina ${i + 1} de ${artes.length}…`, "aviso");
        const [nova] = await rest("POST", "radar_imagens", {corpo:{dados:x.dados, largura:1080, altura:1350}, params:{select:"id"}, prefer:"return=representation"});
        ids.push(nova.id);
      }
      const res = await rpc("radar_pauta_aprovar", {p_peca:Number(f.dataset.id), p_lido:f.dataset.lido, p_canais:canais, p_modo:modo, p_artes:ids,
        p_arte_identificacao:linhaIdentificacao(), p_conferencias:caixas.map(c => c.value), ...(sha ? {p_video_sha256:sha} : {})});
      await desenhar();
      recado(modo === "agendar" ? `Peça aprovada: sai no ${nomes} em ${horaBrasilia(res?.agendado_para)} (Brasília).` +
          (agendaParada(ag) ? " A agenda automática está desligada: no dia, use Publicar agora." : "")
        : `Peça aprovada para publicar à mão: baixe ${sha ? "o vídeo" : "as lâminas"}, copie a legenda e, depois de postar, registre o link.`);
    },
    async "peca-desaprovar"(){
      const f = $("form[data-form=peca]"); if(!f) return;
      // à mão, a peça pode ter sido postada sem o link registrado: quem desfaz confere na rede antes (o banco também pede)
      const mao = $("#peca-conferi-mao");
      if(mao && !mao.checked) throw new ErroApi("A peça foi aprovada para publicar à mão: confira no Instagram e no Facebook que ela não foi postada e marque “Conferi no Instagram e no Facebook: não foi postada à mão”. Se foi postada, registre o link em vez de desfazer.");
      if(!confirm("Desfazer a aprovação? O que ainda não saiu é cancelado e a peça volta a pronta (as lâminas aprovadas deixam de valer).")) return;
      await rpc("radar_pauta_desaprovar", {p_peca:Number(f.dataset.id), p_conferi_rede:!!mao?.checked});
      await desenhar(); recado("Aprovação desfeita: a peça voltou a pronta.");
    },
    /* "Não publicar neste canal" (só o administrador): na peça ou no quadro "Não saíram" */
    async "peca-nao-publicar-canal"(el){
      const nome = NOME_REDE[el.dataset.canal] || "canal";
      if(!confirm(`Não publicar esta peça no ${nome}? ${el.dataset.situacao === "erro" ? "A publicação que não saiu é cancelada (sem Tentar de novo neste canal)"
        : "A publicação agendada é cancelada e não sai"}; o outro canal fica como está e a peça continua aprovada.`)) return;
      await rpc("radar_cancelar_rede", {p_envio:Number(el.dataset.envio)});
      await desenhar(); recado(`Combinado: a peça não vai ao ${nome}.`);
    },
    async "peca-publicar-agora"(){
      const a = E.pauta.aberta;
      if(!confirm(`Publicar agora? A peça sai como foi aprovada (estava marcada para ${quandoPeca(a.data, a.hora)}).`)) return;
      await publicarPecaAgora(false);
    },
    async "peca-tentar-de-novo"(){
      if(!$("#peca-conferi-rede")?.checked) throw new ErroApi("Antes de tentar de novo, confira no Instagram e no Facebook que a publicação não saiu e marque “Conferi no Instagram e no Facebook: não saiu”.");
      await publicarPecaAgora(true);
    },
    /* Excluir da rede o post da peça (como em Publicações): a função radar-redes apaga; se a Meta não deixar, “Já apaguei” registra */
    async "peca-excluir"(el){
      const envio = Number(el.dataset.envio), nome = NOME_REDE[el.dataset.canal] || "canal";
      if(!confirm(`Excluir este post do ${nome}? Ele sai da rede; a peça continua aprovada (para mudar, depois, Desfazer aprovação).`)) return;
      try{ await pedir("POST", "/functions/v1/radar-redes", {corpo:{acao:"excluir", envio}, tempo:60000}); }
      catch(e){
        const msg = e.status === 404 ? "A função radar-redes desta versão ainda não foi instalada no Supabase." : (e.message || "Erro inesperado.");
        if(e.status === 404 || !confirm(`Não deu para excluir do ${nome} pelo Radar:\n\n${msg}\n\nSe você já apagou este post direto no ${nome}, clique em OK para registrar como excluído (“Já apaguei”).`))
          throw new ErroApi(msg);
        await rpc("radar_rede_marcar_excluida", {p_envio:envio, p_como:"manual"});
        await desenhar(); recado(`Registrado: excluída do ${nome} à mão.`); return;
      }
      await desenhar(); recado(`Excluída do ${nome}.`);
    },
    /* À mão: as lâminas aprovadas, como "pauta-AAAA-MM-DD-N.jpg", depois da conferência do banco (o termo de hoje, nos canais aprovados) */
    async "peca-baixar"(){
      const {artes} = await podeCopiarPeca(), a = E.pauta.aberta, box = $("#peca-baixar"); if(!box) return;
      const dados = artes.map(id => (E.pauta.aprovadas || [])[(a.artes || []).indexOf(id)] || "");
      if(!dados.length || dados.some(d => !/^data:image\/jpeg;base64,/.test(d))) throw new ErroApi("As lâminas aprovadas não foram lidas: recarregue a peça.");
      box.innerHTML = `<p class="sub">Clique em cada lâmina para baixar (na ordem do post):</p><div class="acoes">${dados.map((d, i) =>
        `<a class="btn peq sec" style="text-decoration:none" download="pauta-${a.data}-${i + 1}.jpg" href="${h(d)}">Lâmina ${i + 1} de ${dados.length}</a>`).join("")}</div>
        <div class="peca-artes" id="peca-artes-aprovadas">${dados.map((d, i) => `<figure><img class="peca-arte-aprovada" src="${h(d)}" alt="Lâmina aprovada ${i + 1} de ${dados.length}">
          <figcaption class="sub">Lâmina ${i + 1} de ${dados.length}</figcaption></figure>`).join("")}</div>`;
      recado("Lâminas liberadas: baixe e poste na ordem.");
    },
    /* À mão: a legenda salva (aprovada) do canal aprovado, depois da conferência do banco e dos termos (como na cópia do kit das redes) */
    async "peca-copiar-legenda"(el){
      const k = el.dataset.canal;
      const copiou = await copiarDaPeca(async () => {
        const {f} = await podeCopiarPeca(k), texto = (f.elements["legenda_" + k]?.value || "").trim();
        const termos = [...new Set([...termosPublicidade(texto).trava, ...termosPeca(texto)])];
        if(termos.length) throw new ErroApi(msgTermosPeca([[k, termos]], "copiar") + " (Desfaça a aprovação para corrigir.)");
        return texto; });
      if(copiou) recado(`Legenda do ${NOME_REDE[k]} copiada: cole no ${NOME_REDE[k]} e, depois de postar, registre o link.`);
    },
    async "peca-copiar-roteiro"(){
      const copiou = await copiarDaPeca(async () => {
        const {f} = await podeCopiarPeca(), a = E.pauta.aberta, roteiro = (f.elements.roteiro?.value || "").trim();
        const termos = [...new Set([...termosPublicidade(roteiro).trava, ...termosPeca(roteiro)])];
        if(termos.length) throw new ErroApi(msgTermosPeca([["roteiro", termos]], "copiar") + " (Desfaça a aprovação para corrigir.)");
        return `${roteiro}\n\nÚltimo quadro: ${a.arte_identificacao || linhaIdentificacao()}`; });
      if(copiou) recado("Roteiro copiado, com a identificação legal no último quadro.");
    },
    /* Gerar com IA (a peça salva; a partir da 2ª consulta nesta peça, a senha): a IA grava a sugestão na peça, e a tela troca só o quadro da
       sugestão (o que foi digitado enquanto a IA trabalhava continua onde está) */
    async "peca-ia"(el){
      const f = el.closest("form[data-form=peca]"); if(!f) return;
      if(pecaMudou(f)) throw new ErroApi(avisoPecaSuja(f, "Há alterações não salvas: salve a peça antes de gerar com IA (a IA parte da peça salva)."));
      const id = Number(f.dataset.id), naTela = () => E.aba === "pauta" && E.pauta.peca === id;
      if(!(await liberarIA("pauta-" + id, naTela))) return;
      const r = await ia("peca", {peca_id:id, lido:f.dataset.lido});
      if(!naTela()){ recado("A tela mudou enquanto a IA trabalhava: a sugestão ficou guardada na peça (abra a peça para ver).", "aviso"); return; }
      E.pauta.ia = r?.ia || null;
      const box = $("#peca-sugestao"), atual = $("form[data-form=peca]");
      if(box && atual){ box.innerHTML = blocoSugestaoPeca(E.pauta.ia, {pessoas:pessoasDoForm(atual), tipo:atual.elements.tipo?.value || atual.dataset.tipo,
        formato:atual.elements.formato?.value || atual.dataset.formato}); box.scrollIntoView({block:"nearest"}); }
      const n = (Array.isArray(r?.avisos) ? r.avisos.length : 0) + (Array.isArray(r?.ia?.pendencias) ? r.ia.pendencias.length : 0);
      recado(`Sugestão da IA pronta${n ? `, com ${n} ponto(s) a conferir` : ""}: confira e use “Usar a sugestão” para levar os textos aos campos (nada foi salvo).`, n ? "aviso" : false);
    },
    /* Usar a sugestão: a chamada, o apoio, os cartões e as legendas da tela dão lugar aos da IA, com o nome na peça no lugar de {PESSOA1}
       (as legendas com a fonte das informações conferidas, a identificação legal e as hashtags fixas e a do tema, como no “Pôr a
       identificação legal”); nada é salvo, e a arte é redesenhada. O que se aprova é o texto salvo. */
    "peca-usar-ia"(el){
      const f = el.closest("form[data-form=peca]"), s = E.pauta.ia; if(!f || !sugestaoValida(s)) return;
      const mudou = mudouDesdeSugestao(s, {pessoas:pessoasDoForm(f), tipo:f.elements.tipo?.value || f.dataset.tipo, formato:f.elements.formato?.value || f.dataset.formato});
      if(mudou) throw new ErroApi(mudou + " (Salve a peça antes de gerar.)");
      const nome = nomesDaSugestao(s), arte = s.arte && typeof s.arte === "object" ? s.arte : {};
      const campos = [["chamada", arte.chamada, 120], ["apoio", arte.apoio, 200]].filter(([n, v]) => f.elements[n] && !f.elements[n].disabled && textoDe(v));
      const legendas = ["instagram", "facebook"].filter(k => f.elements["legenda_" + k] && !f.elements["legenda_" + k].disabled && textoDe(s[k]?.texto));
      const box = $("#peca-cartoes"), cartoes = (Array.isArray(s.cartoes) ? s.cartoes : []).filter(c => c && typeof c === "object" && (textoDe(c.titulo) || textoDe(c.texto)));
      const comCartoes = !!box && !box.dataset.travado && cartoes.length > 0;
      const cheio = [...campos.map(([n]) => f.elements[n]), ...legendas.map(k => f.elements["legenda_" + k])].some(c => c.value.trim()) ||
        (comCartoes && [...box.querySelectorAll("input, textarea")].some(c => c.value.trim()));
      if(cheio && !confirm("Trocar a chamada, o apoio, os cartões e as legendas desta tela pelos da sugestão da IA? Nada é salvo até você clicar em Salvar.")) return;
      for(const [n, v, max] of campos) f.elements[n].value = nome(textoDe(v)).slice(0, max);
      if(comCartoes) box.innerHTML = cartoes.slice(0, 9).map(c => linhaCartao({titulo:nome(textoDe(c.titulo)), texto:nome(textoDe(c.texto))}, "")).join("");
      const fontes = [...new Set([...f.querySelectorAll("#peca-conferidas [name=conf-fonte]")].map(c => c.value.trim()).filter(Boolean))], avisos = [];
      for(const k of legendas){
        const tags = [...hashtagsPauta(), ...(Array.isArray(s[k].hashtags) ? s[k].hashtags : []).map(textoDe).filter(x => /^#[\p{L}\p{N}_]+$/u.test(x))]
          .filter((x, i, todas) => todas.findIndex(y => y.toLowerCase() === x.toLowerCase()) === i);
        const c = f.elements["legenda_" + k], r = legendaDaSugestao(nome(textoDe(s[k].texto)), fontes, tags.join(" "));
        c.value = r.legenda;
        contarPeca(c);
        if(r.semEndereco || r.encurtado) avisos.push(`no ${NOME_REDE[k]}, ${[r.semEndereco ? "as fontes foram só com a norma, sem o endereço" : "",
          r.encurtado ? "o texto da IA foi encurtado no fim de uma frase" : ""].filter(Boolean).join(" e ")}`);
      }
      pecaArteMudou();
      recado("Sugestão da IA nos campos (ainda não salva): confira, ajuste e salve." + (avisos.length ? " Para a legenda caber em 2.200 caracteres com a " +
        `fonte inteira, a identificação legal e as hashtags, ${avisos.join("; ")}.` : ""), avisos.length ? "aviso" : false);
    },
    "peca-voltar-producao"(el){ return situacaoDaPeca(el, "em_producao", "", "A peça voltou para a produção."); },
    "peca-cancelar"(el){ return situacaoDaPeca(el, "cancelada", "Cancelar esta peça? Ela fica no calendário como cancelada (dá para reabrir).", "Peça cancelada."); },
    "peca-reabrir"(el){ return situacaoDaPeca(el, "planejada", "", "Peça reaberta: voltou a planejada."); },
    async "pessoa-excluir"(el){
      if(!confirm("Excluir esta pessoa? Só dá se ela não estiver em nenhuma peça nem em vídeo do corretor ainda guardado (para tirá-la das próximas, desmarque “Ativa”; se ela retirou a autorização, clique em “Revogar termo”).")) return;
      await apagar("radar_pessoas", {id:"eq." + el.dataset.id, select:"id"}); await desenhar(); recado("Pessoa excluída.");
    },
    // v0.46.0: assinar e revogar o termo de uso de imagem (a assinatura é na janela de assinarTermo; cada função confere que é o administrador)
    "pessoa-assinar"(el){ return assinarTermo(Number(el.dataset.id)); },
    async "pessoa-revogar"(el){
      if(!confirm("Revogar o termo desta pessoa? As peças e os vídeos com ela deixam de ficar prontos e de sair. O que já foi publicado continua no ar — a revogação não apaga o passado (retire à mão o que for combinado).")) return;
      await rpc("radar_pessoa_revogar_termo", {p_pessoa:Number(el.dataset.id)}); await desenhar(); recado("Termo revogado.");
    }
  },
  forms:{
    /* v0.28.0: "+ Nova peça": o banco confere de novo (só o administrador, o dia livre e não passado, os campos) e devolve o número; a
       peça abre em seguida, planejada */
    async novaPeca(f){
      const v = n => (f.elements[n]?.value || "").trim(), dia = f.dataset.dia;
      if(!v("tipo") || !v("formato")) throw new ErroApi("Escolha o tipo e o formato da peça.");
      if(!v("assunto")) throw new ErroApi("Escreva o assunto da peça.");
      const id = await rpc("radar_pauta_criar", {p_peca:{data:dia, tipo:v("tipo"), formato:v("formato"), assunto:v("assunto"),
        objetivo:v("objetivo"), quem_aparece:v("quem_aparece"), observacao:v("observacao")}});
      E.pauta.nova = null; E.pauta.previa = null; E.pauta.peca = Number(id); E.pauta.vista = "semana"; window.scrollTo(0, 0);
      await desenhar();
      recado(`Peça criada para ${dataAgenda(dia)}. Ela está planejada: nada é publicado sem a aprovação do administrador.`);
    },
    async peca(f){
      if(!f.reportValidity()) throw new ErroApi("Confira os campos da peça.");
      const corpo = corpoDaPeca(f);
      // v0.28.1: nada a gravar é a tela igual à peça salva (o que o Salvar não grava, como a linha em branco, não conta): a trava passa
      // a valer a partir daqui. Antes, uma diferença que o Salvar não grava deixava a peça barrada com o aviso até recarregar a página
      if(!Object.keys(corpo).length){ f.dataset.original = estadoPeca(f); recado("Nada mudou na peça."); return; }
      await gravarPeca(f, corpo); await desenhar(); recado("Peça salva.");
    },
    /* À mão: o link do post (Instagram ou Facebook) e o dia; o banco confere o link, o dia (da aprovação até hoje) e o termo nesse dia */
    async pecaRegistrar(f){
      const ig = (f.elements.link_instagram?.value || "").trim(), fb = (f.elements.link_facebook?.value || "").trim(), dia = f.elements.data.value;
      if(!ig && !fb) throw new ErroApi("Cole o link do post no Instagram ou no Facebook.");
      if(!dia) throw new ErroApi("Informe o dia em que a peça foi postada.");
      await rpc("radar_pauta_registrar_manual", {p_peca:Number(f.dataset.id), p_link_instagram:ig || null, p_link_facebook:fb || null, p_data:dia});
      await desenhar(); recado("Publicação registrada.");
    },
    async pessoa(f){ const corpo = dadosPessoa(f);
      await alterar("radar_pessoas", {id:"eq." + f.dataset.id, select:"id"}, corpo); await desenhar(); recado("Pessoa salva."); },
    async novaPessoa(f){ const corpo = dadosPessoa(f);
      await rest("POST", "radar_pessoas", {corpo}); await desenhar(); recado("Pessoa cadastrada. Agora abra o cadastro dela e clique em “Assinar o termo na tela”."); }
  }
};
