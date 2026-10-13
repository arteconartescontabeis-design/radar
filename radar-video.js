"use strict";
/* ====================================================================
   RADAR ARTECON — corretor de vídeo dos reels (v0.22.0)
   Na peça "reel" da Pauta: a fala para conferência (extrairFala: a mesma regra de robo/video/alinhar.py, extrair_fala), o envio de 1
   a 12 clipes direto do navegador ao bucket PRIVADO radar-videos (TUS retomável, com o token de envio de um caminho só que a função
   radar-video entrega no cabeçalho x-signature; nada passa por servidor), a situação (de 20 em 20 s enquanto o robô trabalha; para com
   a aba oculta), o relatório (parcial e final), a prévia (links de 600 s, prazo fixo na função), os ajustes do administrador ("Manter
   este trecho", "A transcrição errou (vale o roteiro)", o editor de legenda com as recusas do robô, legenda compacta, sem o gancho e
   refazer a cartela; o áudio nunca muda), "Tentar de novo", "Conferir com o roteiro novo", "Descartar", o "Apaguei do celular" e, na
   peça aprovada à mão, "Baixar o vídeo aprovado" (link de 300 s). A aprovação do reel (radar-pauta.js) pega daqui o sha256 do vídeo que
   o administrador abriu na prévia (videoParaAprovar) e a conferência dos termos de publicidade na fala transcrita (conferenciaDoVideo).
   Carregado ANTES do script principal, depois do radar-pauta.js (index.html): aqui só há declarações e o objeto VIDEO ({acoes, forms,
   navegacao}), que o script principal junta aos dele. Nada roda no carregamento. Quem trava de verdade é o banco (radar_video_*) e a
   função radar-video: a tela ajuda, mostra e confere antes de mandar. Tudo o que vem do relatório (a fala, o roteiro, os nomes dos
   arquivos) é escapado (h()); nenhum link, token ou nome vai para o console nem para o localStorage (lá fica só o endereço do envio
   retomável, bruto/<id>/<n>, sem nome).
   ==================================================================== */
const VIDEO_VERSAO = "0.22.0";        // igual à VERSAO do index.html; diferente, um dos dois ficou guardado no navegador (Ctrl+F5)
const VIDEO_PEDACO = 6 * 1024 * 1024;                 // TUS do Supabase: pedaços de 6 MiB (“must be set to 6MB”), o último menor
const VIDEO_MAX_CLIPES = 12, VIDEO_MAX_BYTES = 500 * 1024 * 1024, VIDEO_MAX_SEGUNDOS = 120;
// o envio retomável: o caminho com o token assinado (a rota "/sign" do Storage confere o x-signature, sem sessão); o segundo é a reserva
// do desenho (a documentação manda o x-signature no envio retomável sem dizer a rota): o teste real 3 confirma qual vale
const TUS_CAMINHOS = ["/storage/v1/upload/resumable/sign", "/storage/v1/upload/resumable"];
let VIDEO_INTERVALO = 20000;          // a situação, enquanto na fila ou com o robô (os testes encurtam)
let VIDEO_ESPERAS = [1000, 3000, 9000, 20000];        // novas tentativas de um pedaço que não foi (rede ruim): depois, “Continuar o envio”
const VIDEO_TEMPO_PEDACO = 180000;    // um pedaço de 6 MiB em até 3 min (35 KB/s)
const SITUACOES_VIDEO = {aguardando_envio:"Envio não terminado", na_fila:"Na fila do corretor", processando:"O corretor está trabalhando",
  pronto:"Vídeo corrigido pronto", regravar:"Precisa regravar", erro:"O corretor parou", substituido:"Substituído", descartado:"Descartado"};
const TIPO_SELO_VIDEO = {aguardando_envio:"alerta", na_fila:"neutro", processando:"neutro", pronto:"ok", regravar:"erro", erro:"erro"};
const DECLARACOES_VIDEO = [["so_marcadas", "No vídeo só aparecem as pessoas marcadas"], ["sem_fundo", "Sem tela, documento ou cliente ao fundo"],
  ["so_voz", "Só a voz: sem música, rádio ou TV"], ["fala_confere", "A fala para conferência é o que foi gravado"]];
const RECADO_GRAVAR = "Grave em 1080p, 30 quadros por segundo, Vídeo HDR desligado, na vertical. Grave por bloco; apague as tomadas ruins e envie as boas na ordem. Não edite antes de enviar; sem música, rádio ou TV ao fundo.";
const AVISO_FORMATO_FALA = "Formato não reconhecido: confira a fala para conferência; se estiver errada, deixe no roteiro só o que vai ser falado (ou a tabela Tempo | Fala | Texto na tela).";
const AVISO_NAO_FECHE = "Não feche nem bloqueie a tela até 100%.";
// os códigos do robô (robo/video) e do banco (radar_video_falhar), em português; o que não estiver aqui aparece com o código
const ERROS_VIDEO = {
  formato:"um dos clipes não é MP4 ou MOV de câmera (ou não tem imagem): envie os arquivos originais do celular",
  sem_audio:"um dos clipes está sem som: grave de novo com o microfone ligado",
  deitado:"um dos clipes está deitado (horizontal): grave na vertical",
  longo_demais:"os clipes somam mais de 120 s: envie só as tomadas boas",
  arquivo_grande:"um clipe chegou maior que o declarado: envie a gravação de novo",
  sem_fala:"nenhuma fala foi encontrada nos clipes: confira o som e grave de novo",
  cartela_nao_cabe:"a cartela final não coube: encurte a identificação (Configurações → Assinatura) ou o texto extra (Configurações → Corretor de vídeo)",
  conferencia_falhou:"o vídeo montado não passou na conferência final: tente de novo; se repetir, avise o administrador",
  transcricao_ocupada:"Transcrição ocupada; tente de novo (a Azure gratuita atende um pedido por vez e é dividida com a Agenda)",
  azure_cota:"A cota grátis da Azure do mês acabou (5 h, divididas com a Agenda) ou a assinatura parou",
  azure_chave:"Chave da Azure recusada: o administrador confere o segredo AZURE_FALA_CHAVE no repositório privado radar-video",
  azure_fora:"a Azure não respondeu: tente de novo em alguns minutos",
  azure_erro:"a Azure recusou o pedido de transcrição: tente de novo; se repetir, avise o administrador",
  azure_sem_chave:"falta o segredo AZURE_FALA_CHAVE (ou AZURE_FALA_REGIAO) no repositório privado radar-video",
  azure_config:"a configuração da transcrição no repositório privado radar-video está errada (AZURE_FALA_MODO, AZURE_FALA_REGIAO ou AZURE_FALA_ENDPOINT)",
  azure_sem_sdk:"o robô ficou sem o Speech SDK da Azure: o administrador confere o workflow do repositório privado",
  cota_radar:"Limite de minutos do Radar no mês (Configurações → Corretor de vídeo → limite_min_mes)",
  termo:"uma pessoa da peça não pode mais aparecer no vídeo (termo revogado ou vencido, pessoa inativa ou menor de idade, ou quem fala desmarcada da peça): confira em Pauta → Pessoas e termos e depois use Tentar de novo",
  robo_nao_pegou:"o robô não pegou o pedido depois de 3 acionamentos da reserva: o administrador confere no repositório privado radar-video o segredo RADAR_VIDEO_ROBO_CHAVE e as variáveis RADAR_VIDEO_URL e RADAR_VIDEO_COMMIT (e, no Supabase, o segredo RADAR_VIDEO_GITHUB_TOKEN); depois, Tentar de novo",
  robo_chave:"o robô foi recusado pela função radar-video: o administrador confere o segredo RADAR_VIDEO_ROBO_CHAVE do repositório privado (cópia do Vault radar_video_robo)",
  robo_sem_chave:"falta o segredo RADAR_VIDEO_ROBO_CHAVE no repositório privado radar-video",
  robo_config:"a configuração do repositório privado radar-video está errada (RADAR_VIDEO_URL ou RADAR_VIDEO_COMMIT)",
  github:"o robô parou antes de terminar (ele tenta de novo sozinho; depois de 3 vezes, use Tentar de novo)",
  tempo_esgotado:"o robô passou do tempo: tente de novo",
  storage:"o armazenamento não respondeu: tente de novo", rede:"falha de rede no robô: tente de novo",
  ffmpeg_falhou:"a montagem do vídeo falhou: tente de novo; se repetir, avise o administrador",
  ffmpeg_tempo:"a montagem do vídeo passou do tempo: tente de novo", medida_falhou:"a medida do som falhou: tente de novo"};
const ERRO_INTERNO_VIDEO = "erro interno do corretor: tente de novo; se repetir, avise o administrador";
const AVISOS_VIDEO = {
  fala_diferente_do_roteiro:"A fala ficou muito diferente do roteiro (menos de 60% do roteiro foi reconhecido): ouça a prévia e confira a fala para conferência.",
  legenda_recusada:"Parte da edição da legenda foi recusada (veja em Legenda).",
  duracao_acima_do_limite:"O vídeo passou do limite de duração das Configurações: a aprovação pede confirmação.",
  relatorio_resumido:"O relatório ficou grande e foi resumido (as divergências estão todas aqui).",
  transcricao_vazia:"A transcrição não reconheceu nenhuma palavra: os cortes foram feitos só pelos silêncios; ouça a prévia antes de aprovar.",
  boletim_pago:"A fala tem frase igual à do boletim pago (ITC): grave de novo com palavras próprias.",
  gancho_nao_cabe:"O texto do gancho não coube na tela e ficou de fora: encurte o texto do gancho ou marque “Sem o texto do gancho”.",
  lista_resumida:"As listas do relatório ficaram longas e foram resumidas."};
const MOTIVOS_LEGENDA = {bloco_inexistente:"o bloco não existe mais (o vídeo mudou: recarregue a peça)",
  texto_invalido:"texto vazio, com mais de 120 caracteres ou com { } \\ < >",
  numero_de_palavras:"o bloco fica com o mesmo número de palavras (troque palavra por palavra)",
  numero_ou_termo:"número, data, mês ou termo do glossário não muda pela legenda (se a fala está errada, regrave; se a transcrição errou, use “A transcrição errou (vale o roteiro)”)",
  palavra_diferente:"cada palavra nova é a do roteiro ou parecida com a que estava"};
const TIPOS_CORTE = {pausa:"pausa longa encurtada", hesitacao:"hesitação", voz_entre_palavras:"voz entre palavras (hesitação ou repetição)",
  repeticao:"repetição", falso_inicio:"falso início", remover:"trecho"};
const TIPOS_DIVERGENCIA = {numero:"número", data:"data", termo:"termo"};
const CAMPOS_VIDEO = "id,peca_id,versao,situacao,modo,partes,fala_pessoa,fala_roteiro,roteiro_hash,cartela_linhas,gancho,ajustes,tentativas," +
  "sha256,bytes,duracao_final,relatorio,erro_codigo,enviado_por,enviado_em,atualizado_em,apagado_aparelho_em,arquivos_apagados";
const VIVAS_VIDEO = "in.(aguardando_envio,na_fila,processando,pronto,regravar,erro)";

/* ------------------------------------------------------------- utilidades */
const estadoVideo = () => (E.video ||= {arquivos:{}});
const objVideo = v => v && typeof v === "object" && !Array.isArray(v) ? v : {};
const listaVideo = v => (Array.isArray(v) ? v : []).filter(x => x && typeof x === "object");
const numVideo = v => { const n = Number(v); return v !== null && v !== "" && Number.isFinite(n) ? n : null; };
const segVideo = (v, casas = 1) => Number(v).toLocaleString("pt-BR", {minimumFractionDigits:0, maximumFractionDigits:casas});
const mbVideo = b => (b / 1024 / 1024).toLocaleString("pt-BR", {maximumFractionDigits:1}) + " MB";
const UUID_VIDEO = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ehJwtVideo = k => /^[\w-]+\.[\w-]+\.[\w-]+$/.test(k);
const lerLocalVideo = k => { try{ return JSON.parse(localStorage.getItem(k) || "null"); }catch(e){ return null; } };
const guardarLocalVideo = (k, v) => { try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} };
const apagarLocalVideo = k => { try{ localStorage.removeItem(k); }catch(e){} };
const esperarVideo = ms => new Promise(ok => setTimeout(ok, ms));
// o link assinado que a função devolve: só do armazenamento deste projeto (nunca outro endereço na tela)
const linkVideoOk = u => typeof u === "string" && /^https?:\/\/[!-~]+$/.test(u) && !/["'<>`\\]/.test(u) && u.startsWith(URL_BASE + "/storage/v1/object/sign/radar-videos/");
const confVideo = () => objVideo(CONF_PAUTA.corretor_video);
const limiteDuracaoVideo = () => { const n = numVideo(confVideo().duracao_max_s); return n !== null && n >= 15 && n <= 90 ? n : 45; };
// o texto de um código do robô ou do relatório: só o que é do mapa (nunca "constructor" ou "__proto__", que o objeto herda)
const deMapaVideo = (m, k) => typeof k === "string" && Object.prototype.hasOwnProperty.call(m, k) ? m[k] : null;
const erroDoVideo = c => deMapaVideo(ERROS_VIDEO, c) || (/^[a-z_]{3,40}$/.test(String(c || "")) ? ERRO_INTERNO_VIDEO + ` (${c})` : ERRO_INTERNO_VIDEO);
// o banco ainda é o da v0.21.0 (sem a tabela do vídeo): a tela diz o que falta em vez do erro cru do PostgREST
const semTabelaDoVideo = e => e.status === 404 || /radar_videos|termo_corretor_em|quer_ver_peca/.test(e.message || "");

/* A função radar-video (o banco confere tudo; a função assina os links com prazo fixo). Os erros conhecidos viram recado claro. */
async function funcaoVideo(acao, extra = {}, tempo = 60000){
  try{ return await pedir("POST", "/functions/v1/radar-video", {corpo:{acao, ...extra}, tempo}); }
  catch(e){
    if(e.status === 404 && /function was not found|not_found/i.test(e.message || ""))
      throw new ErroApi("A função radar-video ainda não foi instalada no Supabase (Edge Functions): o administrador cria a função desta versão (passo a passo no LEIAME).", 404);
    if(e.status === 0) throw new ErroApi("Não foi possível falar com o corretor de vídeo (sem resposta). Confira a internet e tente de novo.", 0);
    if(/invalid jwt|missing authorization/i.test(e.message || "")) throw new ErroApi("O corretor de vídeo recusou a sessão. Saia do Radar, entre de novo e repita.", e.status);
    throw e;
  }
}
/* Aciona o robô (só com pedido na fila; a função tem pausa de 30 s). Nunca lança: o pedido já está na fila e a reserva da agenda aciona. */
async function acionarCorretor(){
  try{ return textoDe((await funcaoVideo("acionar", {}, 30000))?.mensagem); }
  catch(e){ return `O robô não foi acionado agora (${e.message}); o vídeo continua na fila e a reserva da agenda tenta de novo em até 10 minutos.`; }
}

/* ------------------------------------------- a fala para conferência (a mesma regra de alinhar.extrair_fala) */
/* (a) formato do kit: as linhas "… — Fala: X | Na tela: …" (roteiroDoKit, index.html): pega o X; (b) a tabela do plano: a coluna "Fala"
   de cada linha (Tempo | Fala | Texto na tela), sem as aspas; (c) sem marcador: o texto inteiro (a tela avisa). "Na tela", "Tarja",
   "Gancho" e "Chamada final" nunca entram. testes/test_radar_telas.py compara com o Python, roteiro por roteiro. */
const ASPAS_FALA = "\"'“”‘’«»";
const letrasFala = t => String(t ?? "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]/g, "");
const juntarFala = t => String(t).split(/\s+/).filter(Boolean).join(" ");
const cortarFala = t => Array.from(t).slice(0, 6000).join("");                  // radar_videos.fala_roteiro: até 6.000 caracteres
const semAspasFala = c => { c = c.trim(); return c.length >= 2 && ASPAS_FALA.includes(c[0]) && ASPAS_FALA.includes(c[c.length - 1]) ? c.slice(1, -1).trim() : c; };
function extrairFala(roteiro){
  const linhas = String(roteiro ?? "").replace(/\r\n/g, "\n").split("\n");
  const kit = linhas.map(l => /^[^\n]*?\s[—–]\s*Fala:\s*([^\n]+?)(?:\s+\|\s*Na tela:[^\n]*)?$/.exec(l.trim())).filter(Boolean).map(m => m[1]);
  if(kit.length) return {fala:cortarFala(kit.map(juntarFala).join(" ")), formato:"kit"};
  const falas = []; let col = null;
  for(const l of linhas){
    const s = l.trim();
    if(!s.startsWith("|")){ col = null; continue; }
    const cel = s.replace(/^\|+|\|+$/g, "").split("|").map(c => c.trim());
    if(col === null){ const nomes = cel.map(letrasFala); col = nomes.includes("fala") ? nomes.indexOf("fala") : null; continue; }   // o cabeçalho
    if(cel.filter(Boolean).every(c => /^:?-{2,}:?$/.test(c))) continue;                                                                 // |---|---|
    const c = col < cel.length ? semAspasFala(cel[col]) : "";
    if(c) falas.push(juntarFala(c));
  }
  if(falas.length) return {fala:cortarFala(falas.join(" ")), formato:"tabela"};
  return {fala:cortarFala(juntarFala(String(roteiro ?? ""))), formato:"texto"};
}
/* radar_hash_texto (o banco): sha256 do texto com o espaço sem quebra virando espaço, os brancos juntados e sem espaço nas pontas.
   Diferente do roteiro_hash do vídeo: o roteiro mudou depois da gravação. Sem o crypto.subtle (página fora de https), null. */
async function hashTextoVideo(t){
  if(t === null || t === undefined) return null;
  const s = String(t).replace(/\u00a0/g, " ").replace(/[ \t\n\r\f\v]+/g, " ").replace(/^ +| +$/g, "");
  try{ const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)); return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, "0")).join(""); }
  catch(e){ return null; }
}

/* ------------------------------------------------------------- a cartela */
/* As linhas que a tela manda (o banco confere: radar_video_cartela_falta): a identificação legal das Configurações e, se quem fala tem
   registro no CRC (Pauta → Pessoas e termos), a linha dela ("Ana, contadora · CRC-SC 012345/O-9", a mesma da arte: linhaPessoa). O texto
   extra (Configurações → Corretor de vídeo → cartela_extra) o robô acrescenta: a tela só mostra. */
function linhasCartela(pessoa){
  const x = (E.pauta.pessoas || {})[pessoa], linhas = [linhaIdentificacao()].filter(Boolean);
  if(x && ROTULO_CATEGORIA[x.categoria]) linhas.push(linhaPessoa(x));
  return linhas;
}
function htmlCartela(pessoa){
  const linhas = linhasCartela(pessoa), extra = textoDe(confVideo().cartela_extra);
  return `<ul class="video-cartela">${linhas.map(l => `<li>${h(l)}</li>`).join("")}${extra ? `<li class="sub">${h(extra)} <i>(texto extra das Configurações)</i></li>` : ""}</ul>
    ${faltaIdentificacao().length ? `<div class="aviso erro">A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura (o administrador preenche).</div>` : ""}`;
}

/* ---------------------------------------------------------- o bloco na peça */
/* Chamado por telaPeca (radar-pauta.js) na peça reel, para quem edita: lê o vídeo vivo e o envio a caminho da peça e devolve o quadro
   "Corretor de vídeo" (fora do formulário da peça: os campos daqui não contam como mudança da peça). */
async function blocoVideo(p){
  const ev = estadoVideo();
  if(VIDEO_VERSAO !== VERSAO) return `<div class="aviso erro" id="video-versao">Esta tela (v${h(VERSAO)}) e o arquivo do corretor de vídeo (radar-video.js, v${h(VIDEO_VERSAO)}) são de versões diferentes: um deles ficou guardado no navegador. Aperte Ctrl+F5 (no celular, recarregue a página).</div>`;
  let vivos;
  try{ vivos = await videosDaPeca(p.id); }
  catch(e){ if(semTabelaDoVideo(e)) return `<div class="aviso erro" id="video-sem-banco">O corretor de vídeo precisa do banco da v0.22.0: o administrador roda o <b>sql/radar-setup-v0.22.0.sql</b> (Supabase → SQL Editor) e recarrega esta página.</div>`; throw e; }
  if(ev.peca !== p.id){ ev.nova = false; ev.previa = null; ev.visto = null; }
  ev.peca = p.id;
  ev.pecaDados = {id:p.id, data:p.data, situacao:p.situacao, roteiro:p.roteiro || "", chamada:p.chamada || "", pessoas:p.pessoas || [], aprovado_modo:p.aprovado_modo};
  await guardarVideos(vivos);
  return `<details class="painel video-reel" id="video-reel" data-peca="${p.id}" open><summary><h2>Corretor de vídeo</h2> <span id="video-selo">${seloVideo(ev.atual || ev.envio)}</span></summary>
    <div id="video-corpo">${corpoVideo()}</div></details>`;
}
/* O vídeo vivo da peça (na fila, com o robô, pronto, para regravar ou com erro) e, ao lado dele, o envio que espera os arquivos: o vivo
   só sai quando os clipes do novo chegam (radar_video_enviado). */
async function videosDaPeca(pid){
  const vivos = await ler("radar_videos", {select:CAMPOS_VIDEO, peca_id:"eq." + pid, situacao:VIVAS_VIDEO, order:"versao.desc", limit:"2"});
  return {atual:vivos.find(x => x.situacao !== "aguardando_envio") || null, envio:vivos.find(x => x.situacao === "aguardando_envio") || null};
}
async function guardarVideos({atual, envio}){
  const ev = estadoVideo(), p = ev.pecaDados, v = atual;
  ev.atual = v; ev.envio = envio;
  const hash = v ? await hashTextoVideo(p.roteiro || "") : null;
  ev.roteiroMudou = !!v && (hash ? hash !== v.roteiro_hash : extrairFala(p.roteiro).fala !== v.fala_roteiro);
  if(ev.previa && (!v || ev.previa.id !== v.id || ev.previa.sha256 !== v.sha256)) ev.previa = null;
}
/* Depois de uma ação do corretor: com a peça sem alteração, a tela inteira (a lista do que falta na peça muda junto); com texto não
   salvo na peça, só o quadro do corretor (relido do banco), sem apagar o que foi digitado; se a pessoa saiu da peça (o envio leva
   minutos no celular), nada. */
async function depoisDoVideo(pid){
  if(E.aba !== "pauta" || E.pauta.peca !== pid) return;
  if(!pecaMudou($("form[data-form=peca]"))) return desenhar();
  const ev = estadoVideo();
  if(ev.pecaDados?.id !== pid || !$("#video-reel")) return;
  await guardarVideos(await videosDaPeca(pid));
  if(estadoVideo().peca !== pid) return;
  const c = $("#video-corpo"), s = $("#video-selo");
  if(c) c.innerHTML = corpoVideo();
  if(s) s.innerHTML = seloVideo(ev.atual || ev.envio);
  depoisDeDesenharVideo();
}
const seloVideo = v => v ? selo(`${deMapaVideo(SITUACOES_VIDEO, v.situacao) || v.situacao} (gravação ${v.versao})`, deMapaVideo(TIPO_SELO_VIDEO, v.situacao) ?? "neutro") : selo("Sem gravação", "neutro");
/* O miolo do quadro (refeito pela sondagem sem redesenhar a peça) */
function corpoVideo(){
  const ev = estadoVideo(), p = ev.pecaDados, v = ev.atual, envio = ev.envio, adm = ehAdmin();
  if(!p) return "";
  const livre = ["planejada", "em_producao", "pronta"].includes(p.situacao);
  const partes = [];
  if(p.situacao === "aprovada") partes.push(`<div class="aviso info">Peça aprovada${v?.sha256 ? ` com o vídeo da gravação ${v.versao}` : ""}: o vídeo não muda. Para mudar, Desfazer aprovação.</div>`);
  if(p.situacao === "cancelada") partes.push(`<div class="aviso alerta">Peça cancelada: para gravar, Reabrir.</div>`);
  if(v) partes.push(situacaoVideo(v, p, livre, adm));
  const formulario = livre && (!v || ev.nova || !!envio);
  if(formulario || !v) partes.push(blocoFala(p));
  if(formulario) partes.push(formEnvio(p, v, envio));
  else if(livre && v)
    partes.push(`<div class="acoes"><button class="btn sec" type="button" data-acao="video-nova">Enviar nova gravação</button>
      <span class="sub">${h(AVISO_SUBSTITUI)}</span></div>`);
  return partes.join("");
}
const AVISO_SUBSTITUI = "A gravação atual continua valendo até os clipes da nova chegarem ao armazenamento; só então a nova a substitui.";
/* A fala para conferência (o que o robô compara) e o recado de como gravar */
function blocoFala(p){
  const {fala, formato} = extrairFala(p.roteiro), n = fala ? fala.split(" ").length : 0;
  return `<div class="video-antes"><h3>Antes de gravar</h3><p class="sub">${h(RECADO_GRAVAR)}</p>
    ${!fala ? `<div class="aviso alerta">Cole o roteiro na peça e salve antes de gravar: a fala para conferência sai dele.</div>`
      : `<details class="video-fala"${formato === "texto" ? " open" : ""}><summary>Fala para conferência (${n} palavra${n === 1 ? "" : "s"}): o que o corretor compara com a gravação</summary>
        <p class="video-fala-texto">${h(fala)}</p></details>
        ${formato === "texto" ? `<div class="aviso alerta" id="video-formato-fala">${h(AVISO_FORMATO_FALA)}</div>` : ""}`}</div>`;
}

/* ------------------------------------------------------------- o envio */
const clipesDe = pid => (estadoVideo().arquivos[pid] ||= []);
// o tipo que o banco aceita: MP4 ou MOV (o iPhone manda "video/quicktime"; sem tipo, pela extensão)
const tipoClipe = a => /^video\/(mp4|quicktime)$/.test(a.type) ? a.type : /\.(mp4|m4v)$/i.test(a.name) ? "video/mp4" : /\.mov$/i.test(a.name) ? "video/quicktime" : "";
/* v: o vídeo vivo da peça (a gravação nova o substitui quando os clipes chegam); envio: o que espera os arquivos ("Continuar o envio") */
function formEnvio(p, v, envio){
  const lista = clipesDe(p.id), pessoas = p.pessoas.map(id => (E.pauta.pessoas || {})[id]).filter(Boolean);
  const pr = estadoVideo().progresso;
  if(pr && pr.peca === p.id) return blocoProgresso(pr);
  const vivo = v ? `<p class="sub">${h(AVISO_SUBSTITUI)}</p>` : "";
  // só quem começou o envio (ou o administrador) continua (radar_video_para_envio): para os outros, o aviso e o descartar
  if(envio && envio.enviado_por !== E.sessao?.user?.id && !ehAdmin()) return `<div class="video-envio" id="video-envio"><h3>Envio não terminado</h3>
      <div class="aviso alerta" id="video-envio-outro">O envio da gravação ${h(envio.versao)} foi começado por outra pessoa e não terminou: só ela (ou o administrador) continua. Você pode descartar este envio e enviar de novo.</div>${vivo}
      <div class="acoes"><button class="btn perigo" type="button" data-acao="video-descartar" data-id="${h(envio.id)}">Descartar este envio</button></div></div>`;
  if(envio) return `<div class="video-envio" id="video-envio"><h3>Continuar o envio</h3>
      <div class="aviso alerta">O envio da gravação ${h(envio.versao)} não terminou (${listaVideo(envio.partes).length} clipe(s)). ${lista.length === listaVideo(envio.partes).length ? "Os arquivos ainda estão nesta tela:" : "Escolha de novo os MESMOS arquivos, na mesma ordem:"} o envio continua de onde parou.</div>${vivo}
      ${campoClipes(p)}<div id="video-clipes">${listaClipes(p.id, listaVideo(envio.partes))}</div>
      <p class="sub">${h(AVISO_NAO_FECHE)}</p>
      <div class="acoes"><button class="btn verde" type="button" data-acao="video-continuar" data-id="${h(envio.id)}">Continuar o envio</button>
        <button class="btn perigo" type="button" data-acao="video-descartar" data-id="${h(envio.id)}">Descartar este envio</button></div></div>`;
  const quem = estadoVideo().quem?.[p.id] ?? (pessoas.length === 1 ? pessoas[0].id : "");
  const falta = pessoas.map(x => [x, x.menor ? "menor de idade: o corretor não aceita nesta versão" : !x.termo_corretor_em ? "sem o termo novo, que cita o corretor de vídeo" : !x.ativo ? "inativa" : ""]).filter(([, m]) => m);
  return `<div class="video-envio" id="video-envio"><h3>${v ? "Enviar nova gravação" : "Enviar a gravação"}</h3>
    ${!pessoas.length ? `<div class="aviso alerta">Marque em Quem aparece (e salve) a pessoa que fala no vídeo.</div>` : ""}
    ${falta.length ? `<div class="aviso alerta" id="video-pessoas-falta"><b>Antes de gravar, em Pauta → Pessoas e termos:</b><ul class="pauta-erros">${falta.map(([x, m]) => `<li>${h(x.nome_na_peca)}: ${h(m)}</li>`).join("")}</ul></div>` : ""}
    ${campoClipes(p)}<div id="video-clipes">${listaClipes(p.id)}</div>
    <div class="grade"><div><label for="video-quem">Quem fala</label><select id="video-quem">${pessoas.length > 1 ? `<option value="">Escolha</option>` : ""}${pessoas.map(x =>
      `<option value="${x.id}"${String(x.id) === String(quem) ? " selected" : ""}>${h(x.nome_na_peca)}</option>`).join("")}</select></div></div>
    <label>Cartela final (a identificação legal${pessoas.some(x => ROTULO_CATEGORIA[x.categoria]) ? " e a linha de quem fala, se tem registro no CRC" : ""})</label><div id="video-cartela">${htmlCartela(quem)}</div>
    ${textoDe(p.chamada) ? `<label class="video-check"><input type="checkbox" id="video-gancho"> Texto do gancho de 0 a 3 s: “${h(p.chamada)}”</label>` : `<p class="sub">Sem texto do gancho (o campo “Texto do gancho” da peça está vazio).</p>`}
    <fieldset class="checks video-declaracoes"><legend>Declarações (as quatro são obrigatórias)</legend>${DECLARACOES_VIDEO.map(([k, t]) =>
      `<label><input type="checkbox" class="video-declaracao" value="${k}" data-texto="${h(t)}"> ${h(t)}</label>`).join("")}</fieldset>
    <p class="sub"><b>${h(AVISO_NOVO_ENVIO)}</b></p>${vivo}
    <div class="acoes"><button class="btn verde" type="button" data-acao="video-enviar">${v ? "Enviar a gravação nova" : "Enviar a gravação"}</button>
      ${v ? `<button class="btn sec" type="button" data-acao="video-nova-cancelar">Cancelar</button>` : ""}</div></div>`;
}
const AVISO_NOVO_ENVIO = "Os clipes vão direto para o armazenamento privado do Radar. " + AVISO_NAO_FECHE + " Se a internet cair, o envio continua de onde parou.";
const campoClipes = p => `<label for="video-arquivos">Clipes, na ordem do roteiro (1 a 12, MP4 ou MOV, até 500 MB no total)</label>
  <input id="video-arquivos" type="file" multiple accept="video/mp4,video/quicktime,.mp4,.mov,.m4v" data-video-arquivos="${p.id}">`;
/* A lista dos clipes escolhidos (reordenável); "partes": as do envio que não terminou (o tamanho de cada uma confere) */
function listaClipes(pid, partes){
  const l = clipesDe(pid);
  if(!l.length) return `<p class="sub">Nenhum clipe escolhido.</p>`;
  const total = l.reduce((s, c) => s + c.bytes, 0), dur = l.every(c => c.duracao) ? l.reduce((s, c) => s + c.duracao, 0) : null;
  const avisos = [l.length > VIDEO_MAX_CLIPES ? `São ${l.length} clipes: envie no máximo ${VIDEO_MAX_CLIPES}.` : "",
    total > VIDEO_MAX_BYTES ? `Os clipes somam ${mbVideo(total)}: o máximo é 500 MB.` : "",
    dur && dur > VIDEO_MAX_SEGUNDOS ? `Os clipes somam cerca de ${segVideo(dur, 0)} s: o corretor recusa acima de ${VIDEO_MAX_SEGUNDOS} s (envie só as tomadas boas).` : ""].filter(Boolean);
  return `<ol class="video-clipes">${l.map((c, i) => { const parte = partes?.[i], difere = parte && (parte.bytes !== c.bytes || parte.tipo !== c.tipo);
    return `<li data-i="${i}"><span class="video-clipe-nome"><b>${i + 1}.</b> ${h(c.nome)} · ${mbVideo(c.bytes)}${c.duracao ? ` · ${segVideo(c.duracao)} s` : ""}</span>
      ${!c.tipo ? selo("não é MP4 nem MOV", "erro") : ""}${c.aviso ? " " + selo(c.aviso, "alerta") : ""}${difere ? " " + selo(`não é o clipe nº ${i + 1} do envio`, "erro") : ""}
      <span class="acoes"><button class="btn peq sec" type="button" data-acao="video-clipe-mover" data-i="${i}" data-passo="-1"${i ? "" : " disabled"} aria-label="Subir o clipe ${i + 1}">↑</button>
        <button class="btn peq sec" type="button" data-acao="video-clipe-mover" data-i="${i}" data-passo="1"${i < l.length - 1 ? "" : " disabled"} aria-label="Descer o clipe ${i + 1}">↓</button>
        <button class="btn peq perigo" type="button" data-acao="video-clipe-tirar" data-i="${i}">Tirar</button></span></li>`; }).join("")}</ol>
    <p class="sub">${l.length} clipe(s), ${mbVideo(total)} no total${dur ? `, cerca de ${segVideo(dur, 0)} s` : ""}.</p>
    ${avisos.map(a => `<div class="aviso alerta">${h(a)}</div>`).join("")}`;
}
const redesenharClipes = pid => { const box = $("#video-clipes"); if(box) box.innerHTML = listaClipes(pid, estadoVideo().envio ? listaVideo(estadoVideo().envio.partes) : null); };
/* A duração e a orientação lidas pelo <video> do navegador: SÓ aviso (o HEVC do iPhone não abre em todo navegador; o robô confere). */
const lerMetadadosVideo = arquivo => new Promise(ok => {
  const u = URL.createObjectURL(arquivo), el = document.createElement("video");
  const fim = r => { clearTimeout(relogio); el.removeAttribute("src"); el.load?.(); URL.revokeObjectURL(u); ok(r); };
  const relogio = setTimeout(() => fim(null), 5000);
  el.preload = "metadata"; el.muted = true;
  el.onloadedmetadata = () => fim({duracao:Number.isFinite(el.duration) ? el.duration : null, largura:el.videoWidth, altura:el.videoHeight});
  el.onerror = () => fim(null);
  el.src = u;
});
/* Os arquivos escolhidos entram no fim da lista (o mesmo campo pode ser usado de novo) */
async function escolherClipes(campo){
  const pid = Number(campo.dataset.videoArquivos), novos = [...campo.files]; campo.value = "";
  if(!novos.length || estadoVideo().peca !== pid) return;
  const l = clipesDe(pid);
  for(const a of novos){
    const m = await lerMetadadosVideo(a);
    l.push({arquivo:a, nome:a.name, bytes:a.size, tipo:tipoClipe(a), duracao:m?.duracao || null,
      aviso:!m ? "o navegador não abriu: o robô confere" : m.largura > m.altura ? "parece deitado (horizontal)" : ""});
  }
  redesenharClipes(pid);
  if(l.length > VIDEO_MAX_CLIPES) recado(`São ${l.length} clipes: tire ${l.length - VIDEO_MAX_CLIPES} (no máximo ${VIDEO_MAX_CLIPES}).`, true);
}
/* O que vai à função no envio: confere tudo o que a tela sabe ANTES de qualquer arquivo sair (o banco confere de novo) */
function conferirEnvio(p, lista){
  if(!lista.length) throw new ErroApi("Escolha os clipes do reel (de 1 a 12, na ordem do roteiro).");
  if(lista.length > VIDEO_MAX_CLIPES) throw new ErroApi(`São ${lista.length} clipes: envie no máximo ${VIDEO_MAX_CLIPES} (tire as tomadas que não vão).`);
  const ruim = lista.filter(c => !c.tipo);
  if(ruim.length) throw new ErroApi(`Só vídeo MP4 ou MOV, como sai da câmera do celular: ${ruim.map(c => c.nome).join(", ")}.`);
  const vazio = lista.filter(c => c.bytes < 1);
  if(vazio.length) throw new ErroApi(`Arquivo vazio: ${vazio.map(c => c.nome).join(", ")}.`);
  const total = lista.reduce((s, c) => s + c.bytes, 0);
  if(total > VIDEO_MAX_BYTES) throw new ErroApi(`Os clipes somam ${mbVideo(total)}: o máximo é 500 MB. Grave em 1080p e envie só as tomadas boas.`);
}

/* ----------------------------------------------------- o envio retomável (TUS) */
/* O endereço do armazenamento: o direto do Storage (https://<ref>.storage.supabase.co, o recomendado para arquivo grande); fora do
   Supabase (os testes), o do projeto */
function enderecoArmazenamento(){
  const m = /^https:\/\/([a-z0-9]{20})\.supabase\.co$/.exec(URL_BASE);
  return m ? `https://${m[1]}.storage.supabase.co` : URL_BASE;
}
async function pedidoTus(url, metodo, cab, corpo, tempo){
  const limite = new AbortController(), relogio = setTimeout(() => limite.abort(), tempo);
  try{ return await fetch(url, {method:metodo, headers:cab, body:corpo, signal:limite.signal}); }
  finally{ clearTimeout(relogio); }
}
/* Um clipe por TUS (protocolo 1.0.0, como o tus-js-client da documentação do Supabase): cria o envio (POST, com o tamanho e os metadados:
   bucket, caminho, tipo e cache de 60 s), manda em pedaços de 6 MiB (PATCH com o Upload-Offset) e, se um pedaço não vai (rede ruim),
   espera e pergunta ao armazenamento até onde chegou (HEAD) antes de seguir. O endereço do envio fica no localStorage (só o caminho
   bruto/<id>/<n>, sem nome): ao reabrir a peça e escolher o mesmo arquivo, continua de onde parou. Sem x-upsert: o caminho que já existe
   dá "já existe" (o clipe já tinha chegado). Devolve sem erro quando o clipe está inteiro no armazenamento. */
async function enviarTus(arquivo, envio, bucket, tipo, aoProgresso){
  const chave = "radar_tus_" + envio.caminho, base = enderecoArmazenamento(), n = envio.n;
  const cab = extra => ({apikey:CHAVE, ...(ehJwtVideo(CHAVE) ? {Authorization:"Bearer " + CHAVE} : {}), "x-signature":envio.token, "Tus-Resumable":"1.0.0", ...extra});
  // o endereço do envio (o Location do armazenamento, ou o guardado): só deste projeto, para o token nunca ir a outro lugar
  const doArmazenamento = u => typeof u === "string" && [base, URL_BASE].some(b => u.startsWith(b + "/storage/v1/upload/resumable/"));
  const ondeEsta = async u => { try{ const r = await pedidoTus(u, "HEAD", cab({}), undefined, 30000), o = Number(r.headers.get("Upload-Offset"));
    return r.ok && r.headers.get("Upload-Offset") !== null && Number.isSafeInteger(o) && o >= 0 && o <= arquivo.size ? o : null; }catch(e){ return null; } };
  let url = null, offset = 0;
  const salvo = lerLocalVideo(chave);
  if(salvo && salvo.bytes === arquivo.size && doArmazenamento(salvo.url)){
    const o = await ondeEsta(salvo.url);
    if(o !== null){ url = salvo.url; offset = o; }
  }
  if(!url){
    const meta = [["bucketName", bucket], ["objectName", envio.caminho], ["contentType", tipo], ["cacheControl", "60"]].map(([k, v]) => k + " " + btoa(v)).join(",");
    let r = null;
    for(let i = 0; i <= VIDEO_ESPERAS.length && !r; i++){
      for(const caminho of TUS_CAMINHOS){
        try{ r = await pedidoTus(base + caminho, "POST", cab({"Upload-Length":String(arquivo.size), "Upload-Metadata":meta}), undefined, 60000); }
        catch(e){ r = null; break; }
        if(r.status !== 404) break;
      }
      if(r && r.status >= 500){ r = null; }
      if(!r && i < VIDEO_ESPERAS.length) await esperarVideo(VIDEO_ESPERAS[i]);
    }
    if(!r) throw new ErroApi(`O envio do clipe nº ${n} não começou: o armazenamento não respondeu. Confira a internet e clique em Continuar o envio.`, 0);
    const texto = r.status === 201 ? "" : await r.text().catch(() => "");
    if(r.status === 409 || (r.status === 400 && /already exists|duplicate|409/i.test(texto))){ apagarLocalVideo(chave); aoProgresso(1); return; }
    const loc = r.headers.get("Location");
    if(r.status === 413) throw new ErroApi(`O clipe nº ${n} passou do limite de tamanho do armazenamento: grave em 1080p, 30 quadros por segundo.`, 413);
    if(r.status === 401 || r.status === 403) throw new ErroApi(`O armazenamento recusou o envio do clipe nº ${n} (o link de envio vale 2 horas): clique em Continuar o envio.`, r.status);
    if(r.status !== 201 || !loc) throw new ErroApi(`O armazenamento não aceitou o clipe nº ${n} (erro ${r.status}): clique em Continuar o envio; se repetir, avise o administrador.`, r.status);
    url = new URL(loc, base + "/").href;
    if(!doArmazenamento(url)) throw new ErroApi(`O armazenamento devolveu um endereço de envio fora deste projeto para o clipe nº ${n}: nada foi enviado. Avise o administrador.`);
    guardarLocalVideo(chave, {url, bytes:arquivo.size});
  }
  aoProgresso(offset / arquivo.size);
  let falhas = 0;
  while(offset < arquivo.size){
    const pedaco = arquivo.slice(offset, Math.min(arquivo.size, offset + VIDEO_PEDACO));
    let r = null;
    try{ r = await pedidoTus(url, "PATCH", cab({"Upload-Offset":String(offset), "Content-Type":"application/offset+octet-stream"}), pedaco, VIDEO_TEMPO_PEDACO); }
    catch(e){ r = null; }
    const novo = r && r.status === 204 ? Number(r.headers.get("Upload-Offset")) : NaN;
    if(Number.isSafeInteger(novo) && novo > offset && novo <= arquivo.size){ offset = novo; falhas = 0; aoProgresso(offset / arquivo.size); continue; }
    if(r && (r.status === 401 || r.status === 403))
      throw new ErroApi(`O armazenamento recusou o envio do clipe nº ${n} (o link de envio vale 2 horas): clique em Continuar o envio (o que já subiu fica).`, r.status);
    if(r && (r.status === 404 || r.status === 410)){
      apagarLocalVideo(chave);
      throw new ErroApi(`O envio do clipe nº ${n} venceu no armazenamento: clique em Continuar o envio (este clipe recomeça).`, r.status);
    }
    // a rede caiu, o armazenamento falhou ou o deslocamento não confere (o pedaço chegou e a resposta não): espera e pergunta até onde foi
    if(++falhas > VIDEO_ESPERAS.length)
      throw new ErroApi(`O envio parou no clipe nº ${n} (${Math.floor(100 * offset / arquivo.size)}%): a internet caiu ou ficou lenta. Clique em Continuar o envio (o que já subiu fica).`, 0);
    await esperarVideo(VIDEO_ESPERAS[falhas - 1]);
    const o = await ondeEsta(url);
    if(o !== null && o >= offset){ offset = o; aoProgresso(offset / arquivo.size); }
  }
  apagarLocalVideo(chave);
}
/* Enquanto os clipes sobem: o andamento de cada um na tela (refeito se a tela for redesenhada) e o aviso do navegador ao sair */
const naoSairVideo = ev => { ev.preventDefault(); ev.returnValue = ""; };
function blocoProgresso(pr){
  return `<div class="video-envio" id="video-envio"><h3>Enviando a gravação</h3><div class="aviso alerta"><b>${h(AVISO_NAO_FECHE)}</b></div>
    <ol class="video-progresso">${Object.entries(pr.partes).map(([n, f]) => `<li><span>Clipe ${h(n)}</span>
      <progress id="video-prog-${h(n)}" max="100" value="${Math.round(100 * f)}"></progress><span class="sub" id="video-pct-${h(n)}">${Math.round(100 * f)}%</span></li>`).join("")}</ol></div>`;
}
function mostrarProgresso(n, f){
  const pr = estadoVideo().progresso; if(pr) pr.partes[n] = f;
  const b = $("#video-prog-" + n), t = $("#video-pct-" + n);
  if(b) b.value = Math.round(100 * f);
  if(t) t.textContent = Math.round(100 * f) + "%";
}
/* Os clipes do envio, um de cada vez (envios: os tokens da função, [{n, caminho, token}]) */
async function subirClipes(pid, id, envios, lista, bucket){
  const caminho = new RegExp(`^bruto/${id}/(\\d{1,2})$`);
  for(const e of envios){
    const m = caminho.exec(String(e?.caminho || ""));
    if(!m || Number(m[1]) !== e.n || !lista[e.n - 1] || typeof e.token !== "string" || !e.token) throw new ErroApi("A função devolveu um envio fora do formato. Nada foi enviado: tente de novo.");
  }
  const ev = estadoVideo();
  ev.progresso = {peca:pid, id, partes:Object.fromEntries(envios.map(e => [e.n, 0]))};
  const box = $("#video-envio"); if(box) box.outerHTML = blocoProgresso(ev.progresso);
  window.addEventListener("beforeunload", naoSairVideo);
  // no celular, a tela acesa enquanto sobe (a tela bloqueada para o envio): o pedido do navegador (Screen Wake Lock); sem ele, só o aviso.
  // O navegador solta o pedido sozinho quando a página fica oculta (a troca rápida de aplicativo): ao voltar, pede de novo
  let acesa = null;
  const acender = async () => { try{ acesa = await navigator.wakeLock?.request("screen") || null; }catch(e){ acesa = null; } };
  const voltou = () => { if(!document.hidden && ev.progresso) acender(); };
  await acender();
  document.addEventListener("visibilitychange", voltou);
  try{
    for(const e of envios){ const c = lista[e.n - 1]; await enviarTus(c.arquivo, e, bucket, c.tipo, f => mostrarProgresso(e.n, f)); }
  }finally{
    window.removeEventListener("beforeunload", naoSairVideo); document.removeEventListener("visibilitychange", voltou);
    ev.progresso = null; if(acesa) acesa.release().catch(() => {});
  }
}

/* ------------------------------------------------------------- a situação */
function situacaoVideo(v, p, livre, adm){
  const r = objVideo(v.relatorio), final = ["pronto", "regravar"].includes(v.situacao) && !relatorioParcial(v);
  const podeAjustar = adm && livre && ["pronto", "regravar", "erro"].includes(v.situacao) && !relatorioParcial(v) && Object.keys(r).length > 0;
  const partes = [];
  if(v.situacao === "aguardando_envio") return "";                         // o formulário do envio mostra
  if(v.situacao === "na_fila" || v.situacao === "processando")
    partes.push(`<div class="aviso info" id="video-trabalhando">${v.situacao === "na_fila" ? "Na fila do corretor" : "O corretor está trabalhando"} (gravação ${v.versao}${v.modo === "montagem" ? ", só a montagem: a transcrição é a mesma" : ""}). Esta tela atualiza sozinha; pode sair e voltar depois.</div>`);
  if(v.situacao === "erro"){
    partes.push(`<div class="aviso erro" id="video-erro"><b>O corretor parou:</b> ${h(erroDoVideo(v.erro_codigo))}.</div>`);
    if(livre) partes.push(`<div class="acoes"><button class="btn" type="button" data-acao="video-de-novo" data-id="${h(v.id)}">Tentar de novo</button></div>`);
  }
  if(livre && estadoVideo().roteiroMudou && ["pronto", "regravar", "erro"].includes(v.situacao))
    partes.push(`<div class="aviso alerta" id="video-roteiro-mudou">O roteiro da peça mudou depois desta gravação. Se a fala gravada continua valendo, “Conferir com o roteiro novo” (o corretor compara de novo, sem transcrever de novo); senão, grave de novo.
      <div class="acoes"><button class="btn peq" type="button" data-acao="video-reconferir" data-id="${h(v.id)}">Conferir com o roteiro novo</button></div></div>`);
  if(Object.keys(r).length) partes.push(blocoRelatorio(v, podeAjustar));
  if(final && v.sha256 && !(Array.isArray(v.arquivos_apagados) ? v.arquivos_apagados : []).includes("corrigido"))
    partes.push(`<div class="video-previa-quadro"><h3>Prévia</h3><div id="video-previa">${htmlPrevia()}</div></div>`);
  if(podeAjustar) partes.push(blocoAjustes(v));
  if(livre && ["pronto", "regravar", "erro"].includes(v.situacao))
    partes.push(`<div class="acoes video-descartar"><button class="btn peq perigo" type="button" data-acao="video-descartar" data-id="${h(v.id)}">Descartar esta gravação</button></div>`);
  if(v.enviado_em && ["na_fila", "processando", "pronto", "regravar", "erro"].includes(v.situacao))
    partes.push(v.apagado_aparelho_em ? `<p class="sub" id="video-apaguei-feito">Registrado: os clipes foram apagados do celular e da nuvem pessoal em ${h(dataHora(v.apagado_aparelho_em))}.</p>`
      : `<div class="acoes video-apaguei"><button class="btn peq sec" type="button" data-acao="video-apaguei" data-id="${h(v.id)}">Apaguei do celular e da nuvem pessoal</button>
        <span class="sub">O termo pede apagar os clipes do aparelho no mesmo dia do envio.</span></div>`);
  return `<div class="video-situacao" id="video-situacao">${partes.join("")}</div>`;
}

/* ------------------------------------------------------------- o relatório */
/* Em português simples, com os tempos do vídeo corrigido (em_s). O parcial (logo depois do alinhamento) já diz se precisa regravar. */
function blocoRelatorio(v, podeAjustar){
  const r = objVideo(v.relatorio), parcial = relatorioParcial(v), aj = objVideo(v.ajustes);
  const manter = new Set(listaNumeros(aj.manter)), errou = new Set(listaNumeros(aj.transcricao_errou));
  const em = x => numVideo(x) !== null ? `aos ${segVideo(x)} s` : "";
  const ouvir = x => !parcial && numVideo(x) !== null ? ` <button class="btn peq sec" type="button" data-acao="video-ouvir" data-em="${numVideo(x)}">▶ ouvir</button>` : "";
  const itens = [], saida = objVideo(r.saida), conf = objVideo(r.conferencia), entrada = objVideo(r.entrada);
  const avisos = [...new Set((Array.isArray(r.avisos) ? r.avisos : []).map(String))];
  if(avisos.length) itens.push(`<div class="aviso alerta video-avisos"><ul class="pauta-erros">${avisos.map(a => `<li>${h(deMapaVideo(AVISOS_VIDEO, a) || "Aviso do corretor: " + a)}</li>`).join("")}</ul></div>`);
  // o que precisa regravar: número, data ou termo diferente do roteiro
  const divs = listaVideo(r.divergencias), abertas = divs.filter(d => d.regravar !== false && !d.transcricao_errou && !errou.has(Number(d.k)));
  if(divs.length) itens.push(`<div class="${abertas.length ? "aviso erro" : "aviso info"} video-divergencias"><b>${abertas.length ? "Precisa regravar:" : "Divergências (marcadas: a transcrição errou):"}</b>
    <ul class="pauta-erros">${divs.map(d => { const k = Number(d.k), marcado = !!d.transcricao_errou || errou.has(k);
      return `<li class="video-divergencia" data-k="${h(k)}">${h(em(d.em_s) ? em(d.em_s)[0].toUpperCase() + em(d.em_s).slice(1) : "No vídeo")} a fala diz “${h(d.falado)}” e o roteiro diz “${h(d.roteiro)}”${deMapaVideo(TIPOS_DIVERGENCIA, d.tipo) ? ` (${h(deMapaVideo(TIPOS_DIVERGENCIA, d.tipo))})` : ""}.${ouvir(d.em_s)}
        ${podeAjustar ? `<label class="video-check"><input type="checkbox" class="video-errou" value="${h(k)}"${marcado ? " checked" : ""}> A transcrição errou (vale o roteiro)</label>`
          : marcado ? ` <span class="selo ok">a transcrição errou: vale o roteiro</span>` : ""}</li>`; }).join("")}</ul>
    ${podeAjustar && abertas.length ? `<p class="sub">Administrador: ouça na prévia; se a pessoa disse o que está no roteiro, marque “A transcrição errou (vale o roteiro)” e aplique os ajustes (a legenda passa a usar o roteiro naquele trecho; o áudio não muda). Se a fala está errada, grave de novo.</p>` : ""}</div>`);
  if(parcial) itens.unshift(`<p class="sub video-parcial">${["na_fila", "processando"].includes(v.situacao) ? "Relatório parcial: a fala já foi comparada com o roteiro; o vídeo ainda está sendo montado."
    : "Relatório parcial da última rodada: o corretor parou antes de montar o vídeo."}</p>`);
  // a duração
  const dur = numVideo(saida.duracao_s) ?? numVideo(v.duracao_final), max = limiteDuracaoVideo();
  if(dur !== null) itens.push(`<li id="video-duracao">Duração: ${segVideo(dur)} s${numVideo(saida.fala_s) !== null ? ` (fala ${segVideo(saida.fala_s)} s + cartela ${segVideo(saida.cartela_s ?? 3)} s)` : ""}. ${dur > 90
    ? "<b>Passou de 90 s: o Facebook não aceita; grave mais curto.</b>" : dur > max ? `<b>Acima do limite de ${max} s</b> (Configurações → Corretor de vídeo): a aprovação pede confirmação.` : `Dentro do limite de ${max} s.`}</li>`);
  // os cortes
  const cortes = listaVideo(r.cortes), borda = new Set(cortes.filter(c => c.tipo === "inicio" || c.tipo === "fim").map(c => c.clipe)).size;
  const meio = cortes.filter(c => numVideo(c.em_s) !== null), pausas = meio.filter(c => c.tipo === "pausa"), hes = meio.filter(c => c.tipo !== "pausa");
  const soma = l => segVideo(l.reduce((s, c) => s + (numVideo(c.dur_s) || 0), 0), 2);
  const semFala = cortes.filter(c => c.tipo === "clipe_sem_fala").length;
  if(cortes.length) itens.push(`<li id="video-cortes">Cortes: começo e fim de ${borda} clipe(s)${pausas.length ? `; ${pausas.length} pausa(s) longa(s) encurtada(s) (${soma(pausas)} s)` : ""}${hes.length ? `; ${hes.length} trecho(s) de hesitação (${soma(hes)} s)` : ""}${semFala ? `; ${semFala} clipe(s) sem fala ficaram de fora` : ""}.
    ${meio.length ? `<details class="video-cortes-meio"${meio.length <= 8 ? " open" : ""}><summary>Cortes no meio da fala (${meio.length})</summary><ul>${meio.map(c => { const k = Number(c.k), mantido = !!c.mantido || manter.has(k);
      return `<li class="video-corte" data-k="${h(k)}">${h(em(c.em_s))}: ${h(deMapaVideo(TIPOS_CORTE, c.tipo) || c.tipo)} (${segVideo(c.dur_s, 2)} s)${textoDe(c.texto) ? ` — “${h(c.texto)}”` : ""}${ouvir(c.em_s)}
        ${podeAjustar ? `<label class="video-check"><input type="checkbox" class="video-manter" value="${h(k)}"${mantido ? " checked" : ""}> Manter este trecho</label>` : mantido ? ` <span class="selo neutro">mantido</span>` : ""}</li>`; }).join("")}</ul></details>` : ""}</li>`);
  const sug = listaVideo(r.sugestoes);
  if(sug.length) itens.push(`<li id="video-sugestoes">Para ouvir (não foi cortado): ${sug.map(s => `${h(em(s.em_s))}, ${h(deMapaVideo(TIPOS_CORTE, s.tipo) || s.tipo)}${textoDe(s.texto) ? ` “${h(s.texto)}”` : ""}${ouvir(s.em_s)}`).join("; ")}. Se atrapalhar, grave o trecho de novo.</li>`);
  // a legenda
  const trocas = listaVideo(r.trocas);
  if(trocas.length) itens.push(`<li id="video-trocas">Legenda na grafia do roteiro: ${trocas.map(t => `“${h(t.de)}” → “${h(t.para)}”${em(t.em_s) ? ` (${h(em(t.em_s))})` : ""}`).join("; ")}.</li>`);
  const fora = listaVideo(r.fora_do_roteiro), omitido = listaVideo(r.omitido);
  if(fora.length) itens.push(`<li id="video-fora">Falado fora do roteiro (vai na legenda como foi dito): ${fora.map(x => `“${h(x.texto)}”${em(x.em_s) ? ` (${h(em(x.em_s))})` : ""}`).join("; ")}.</li>`);
  if(omitido.length) itens.push(`<li id="video-omitido">Do roteiro e não dito (fica fora da legenda): ${omitido.map(x => `“${h(x.texto)}”`).join("; ")}.</li>`);
  const fala = textoDe(r.texto_final);
  if(!parcial){
    const trava = [...new Set([...termosPublicidade(fala).trava, ...termosPeca(fala)])], aviso = termosPublicidade(fala).aviso.filter(x => !trava.some(y => y.includes(x)));
    itens.push(trava.length ? `<li id="video-termos" class="video-trava"><b>Precisa regravar:</b> a fala tem ${trava.map(t => `“${h(t)}”`).join(", ")}, que a publicidade da profissão contábil não usa.</li>`
      : `<li id="video-termos">Termos de publicidade na fala: ${aviso.length ? `${aviso.map(t => `“${h(t)}”`).join(", ")} (confira se é informação, e não propaganda; a aprovação pede confirmação)` : "nenhum"}.</li>`);
    const leg = objVideo(r.legenda), rec = listaVideo(leg.recusados);
    itens.push(`<li id="video-legenda-resumo">Legenda: ${numVideo(leg.blocos) ?? 0} bloco(s), ${leg.estilo === "compacta" ? "compacta (1 linha)" : "normal (até 2 linhas)"}${leg.gancho ? ", com o texto do gancho de 0 a 3 s" : ""}${numVideo(leg.editados) ? `; ${numVideo(leg.editados)} bloco(s) editado(s)` : ""}.
      ${rec.length ? `<span class="video-recusados">Edição recusada: ${rec.map(x => `bloco ${h(x.bloco)}, ${h(deMapaVideo(MOTIVOS_LEGENDA, x.motivo) || x.motivo)}`).join("; ")}.</span>` : ""}</li>`);
    const lufs = numVideo(saida.lufs ?? conf.lufs), pico = numVideo(saida.pico_dbtp ?? conf.pico_dbtp), audio = objVideo(r.audio);
    const ra = numVideo(audio.ruido_antes_db), rd = numVideo(audio.ruido_depois_db);
    // ruído "reduzido" só com a medida: o ruído de fundo em relação à voz caiu (o relatório traz os dois números)
    if(lufs !== null) itens.push(`<li id="video-som">Som: volume ${segVideo(lufs)} LUFS (o padrão das redes é −14)${pico !== null ? `, pico ${segVideo(pico)} dBTP` : ""}${ra !== null && rd !== null && rd < ra - 1 ? `; ruído de fundo ${segVideo(ra - rd)} dB mais baixo em relação à voz` : ""}.</li>`);
    if(conf.codec) itens.push(`<li id="video-imagem">Imagem: 1080×1920, ${h(conf.fps || 30)} quadros por segundo${entrada.clipes ? ` (gravação: ${h(entrada.clipes)} clipe(s), ${segVideo(entrada.duracao_s)} s${entrada.resolucao ? `, ${h(String(entrada.resolucao).replace("x", "×"))}` : ""}${entrada.hdr ? ", HDR convertido" : ""}${entrada.girado ? ", girado" : ""})` : ""}.</li>`);
    if(conf.moov_inicio && conf.sem_edit_list) itens.push(`<li id="video-formato">Formato aceito pelo Instagram e pelo Facebook${conf.sem_gps ? "; localização do celular removida" : ""}.</li>`);
    itens.push(`<li>Confira nos 4 quadros da prévia: o fundo, as pessoas e a posição da legenda.</li>`);
  }
  const tr = objVideo(r.transcricao), cob = numVideo(r.cobertura);
  if(numVideo(tr.segundos_audio) !== null) itens.push(`<li id="video-transcricao" class="sub">Transcrição: ${segVideo(tr.segundos_audio)} s de áudio (${tr.servico === "azure_rapido" ? "Azure, modo rápido" : "Azure gratuita"}), ${numVideo(tr.palavras) ?? 0} palavra(s)${cob !== null ? `; ${Math.round(100 * cob)}% do roteiro reconhecido` : ""}.</li>`);
  const lista = itens.filter(x => x.startsWith("<li")), fora_lista = itens.filter(x => !x.startsWith("<li"));
  return `<div class="video-relatorio" id="video-relatorio"><h3>${parcial ? "Relatório parcial" : "Vídeo corrigido"} — gravação ${h(v.versao)}</h3>${fora_lista.join("")}<ul>${lista.join("")}</ul></div>`;
}
const listaNumeros = v => (Array.isArray(v) ? v : []).map(Number).filter(n => Number.isInteger(n) && n >= 0 && n <= 9999);
// o relatório é parcial (robo: parcial true; o concluir grava false); sem a marca, o do vídeo pronto ou para regravar é o final
const relatorioParcial = v => { const r = objVideo(v.relatorio); return r.parcial === true || (r.parcial !== false && !["pronto", "regravar"].includes(v.situacao)); };

/* ------------------------------------------------------------- a prévia */
function htmlPrevia(){
  const ev = estadoVideo(), pv = ev.previa, v = ev.atual;
  if(!pv || !v || pv.id !== v.id) return `<div class="acoes"><button class="btn" type="button" data-acao="video-previa" data-id="${h(v?.id || "")}">Ver o vídeo corrigido</button>
    <span class="sub">Link de 10 minutos, só para quem está logado; quem viu fica registrado.${ehAdmin() ? " A aprovação fica amarrada ao vídeo que você abrir aqui." : ""}</span></div>`;
  const quadros = Array.isArray(objVideo(v.relatorio).quadros_ms) ? objVideo(v.relatorio).quadros_ms : [];
  return `<video id="video-player" controls playsinline preload="metadata" src="${h(pv.video)}"></video>
    <div class="video-quadros">${pv.quadros.map((q, i) => `<figure><img src="${h(q)}" alt="Quadro ${i + 1} do vídeo corrigido">
      <figcaption class="sub">Quadro ${i + 1}${numVideo(quadros[i]) !== null ? `, aos ${segVideo(quadros[i] / 1000)} s` : ""}</figcaption></figure>`).join("")}</div>
    <p class="sub">Aberto às ${h(new Date(pv.em).toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"}))}; o link vale 10 minutos (vencido, a tela pede outro sozinha).</p>`;
}
async function abrirPreviaVideo(id, silencioso){
  const ev = estadoVideo(), v = ev.atual;
  if(!v || v.id !== id) throw new ErroApi("A gravação mudou: recarregue a peça.");
  const r = await funcaoVideo("previa", {id});
  if(!linkVideoOk(r?.video) || !Array.isArray(r?.quadros) || r.quadros.length !== 4 || !r.quadros.every(linkVideoOk) || !/^[0-9a-f]{64}$/.test(String(r?.sha256)))
    throw new ErroApi("A função devolveu a prévia fora do formato.");
  if(r.sha256 !== v.sha256) throw new ErroApi("O vídeo corrigido mudou enquanto a prévia abria: recarregue a peça.");
  ev.previa = {id, sha256:r.sha256, video:r.video, quadros:r.quadros, em:Date.now()};
  ev.visto = {id, sha256:r.sha256};                 // o que a aprovação manda (videoParaAprovar)
  const box = $("#video-previa"); if(box) box.innerHTML = htmlPrevia();
  ligarPlayerVideo();
  if(!silencioso) $("#video-player")?.scrollIntoView({block:"nearest"});
}
/* O link venceu (10 minutos) e o <video> deu erro: pede outro uma vez (sem repetir sem parar) */
function ligarPlayerVideo(){
  const pl = $("#video-player"); if(!pl || pl.dataset.ligado) return;
  pl.dataset.ligado = "1";
  pl.addEventListener("error", () => { const pv = estadoVideo().previa;
    if(pv && !pv.renovado && Date.now() - pv.em > 60000){ pv.renovado = true; abrirPreviaVideo(pv.id, true).catch(() => {}); } });
}

/* ------------------------------------------------------------- os ajustes */
/* Do administrador, depois de ouvir: "Manter este trecho" e "A transcrição errou" (no relatório), o editor de legenda (palavra por
   palavra), legenda compacta, sem o gancho e refazer a cartela. Tudo vai num radar_video_ajustar só; o robô monta de novo, sem
   transcrever de novo. */
function blocoAjustes(v){
  const r = objVideo(v.relatorio), leg = objVideo(r.legenda), aj = objVideo(v.ajustes), blocos = listaVideo(leg.lista);
  const cartelaNova = linhasCartela(v.fala_pessoa), mudouCartela = JSON.stringify(cartelaNova) !== JSON.stringify(v.cartela_linhas || []);
  return `<div class="video-ajustes painel" id="video-ajustes"><h3>Ajustes do administrador</h3>
    <p class="sub">Junto com o que estiver marcado no relatório (“Manter este trecho” e “A transcrição errou”). O vídeo é montado de novo; o áudio não muda.</p>
    ${blocos.length ? `<details class="video-legenda"><summary>Editar a legenda (${blocos.length} bloco${blocos.length > 1 ? "s" : ""})</summary>
      <p class="sub">Troque palavra por palavra, com o mesmo número de palavras: cada palavra nova é a do roteiro ou parecida com a que estava; número, data, mês e termo do glossário não mudam aqui. O robô confere de novo e lista o que recusar.</p>
      ${blocos.map((b, i) => { const u = numVideo(b.u), n = numVideo(b.palavras), ok = Number.isInteger(u) && Number.isInteger(n);
        return `<div class="video-bloco"><label for="video-leg-${i}">${numVideo(b.em_s) !== null ? `Aos ${segVideo(b.em_s)} s` : `Bloco ${i + 1}`} · ${ok ? `${n} palavra${n === 1 ? "" : "s"}` : "não editável"}</label>
          <input id="video-leg-${i}" type="text" class="video-legenda-texto" maxlength="120" value="${h(b.texto)}" data-original="${h(b.texto)}" data-bloco="${i}"${ok ? ` data-u="${u}" data-n="${n}"` : " disabled"}></div>`; }).join("")}</details>` : ""}
    <label class="video-check"><input type="checkbox" id="video-compacta"${aj.estilo === "compacta" ? " checked" : ""}> Legenda compacta (1 linha, letra menor: quando a legenda cobre a boca)</label>
    ${v.gancho ? `<label class="video-check"><input type="checkbox" id="video-sem-gancho"${aj.sem_gancho === true ? " checked" : ""}> Sem o texto do gancho (0 a 3 s)</label>` : ""}
    <label class="video-check"><input type="checkbox" id="video-refazer-cartela"> Refazer a cartela com as Configurações e Pessoas e termos de hoje${mudouCartela ? ` <span class="selo alerta">mudou: ${h(cartelaNova.join(" / "))}</span>` : ""}</label>
    <div class="acoes"><button class="btn" type="button" data-acao="video-ajustar" data-id="${h(v.id)}">Aplicar os ajustes e montar de novo</button></div></div>`;
}
/* As recusas do editor de legenda, como o robô (alinhar._edicao): o texto, o número de palavras, o sentido (números, meses e termos do
   glossário) e cada palavra (igual a uma do roteiro PERTO do bloco — `perto`, as letras que o robô manda em cada bloco da lista — ou
   parecida, ≥ 0,6, com a que estava). null = passa; senão o código do motivo. O que o robô recusa, a tela recusa antes
   (testes/test_radar_telas.py compara os dois, caso a caso); a tela é mais rígida só no número escrito de outro jeito ("20" e "vinte",
   "dois" e "duas": o mesmo valor para o robô). Sem o `perto` (o relatório de antes dele), vale a fala inteira do roteiro. */
const MESES_VIDEO = new Set(["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]);
const EXTENSO_VIDEO = new Set(("zero dois duas tres quatro cinco seis sete oito nove dez onze doze treze catorze quatorze quinze dezesseis dezessete dezoito " +
  "dezenove vinte trinta quarenta cinquenta sessenta setenta oitenta noventa cem cento duzentos duzentas trezentos trezentas quatrocentos quatrocentas " +
  "quinhentos quinhentas seiscentos seiscentas setecentos setecentas oitocentos oitocentas novecentos novecentas mil milhao milhoes bilhao bilhoes " +
  "primeiro primeira segundo segunda terceiro terceira quarto quarta quinto quinta sexto sexta setimo setima oitavo oitava nono nona decimo decima " +
  "reais real centavos").split(" "));
const COMUNS_VIDEO = new Set(["das", "dar", "mas"]);   // termo de uma palavra que também é palavra do dia a dia: só em maiúsculas (numeros.COMUNS)
// os termos do glossário pela chave do robô: as letras juntas ("Simples Nacional" → simplesnacional, "PGDAS-D" → pgdasd)
function termosDoGlossario(){
  const g = Array.isArray(confVideo().glossario) ? confVideo().glossario : [];
  return new Set(g.filter(t => typeof t === "string").map(letrasFala).filter(k => k.length >= 2));
}
const termoDaPalavra = (w, termos) => { const l = letrasFala(w); return termos.has(l) && (!COMUNS_VIDEO.has(l) || /\p{Lu}/u.test(w)) ? l : ""; };
function sentidoDaPalavra(w, termos){
  if(/[\d$]/.test(w)) return "n" + w.replace(/[^0-9A-Za-z%º°ª$\/]/g, "");              // "20", "30/10", "13º", "R$", "US$"
  const l = letrasFala(w);
  if(MESES_VIDEO.has(l)) return "m" + l;
  if(EXTENSO_VIDEO.has(l)) return "e" + l;
  const t = termoDaPalavra(w, termos);
  return t ? "t" + t : "";
}
// os termos do texto, como numeros.fichas: até 6 palavras seguidas cujas letras, juntas, são as de um termo ("e social", "Simples Nacional")
function sentidoDoTexto(ws, termos){
  const ls = ws.map(letrasFala), r = [];
  for(let i = 0; i < ls.length; i++)
    for(let tam = Math.min(6, ls.length - i); tam >= 1; tam--){
      const k = ls.slice(i, i + tam).join("");
      if(ls[i] && termos.has(k) && (tam > 1 || termoDaPalavra(ws[i], termos))){ r.push(k); i += tam - 1; break; }
    }
  return r.join("|");
}
/* SequenceMatcher.ratio do difflib (sem lixo: palavras curtas), para a semelhança das letras */
function razaoVideo(a, b){
  if(!a.length && !b.length) return 1;
  const b2j = {}; [...b].forEach((c, j) => (b2j[c] ||= []).push(j));
  const maior = (alo, ahi, blo, bhi) => { let bi = alo, bj = blo, bk = 0, j2len = {};
    for(let i = alo; i < ahi; i++){ const novo = {};
      for(const j of b2j[a[i]] || []){ if(j < blo) continue; if(j >= bhi) break; const k = novo[j] = (j2len[j - 1] || 0) + 1; if(k > bk){ bi = i - k + 1; bj = j - k + 1; bk = k; } }
      j2len = novo; }
    return [bi, bj, bk]; };
  let m = 0; const fila = [[0, a.length, 0, b.length]];
  while(fila.length){ const [alo, ahi, blo, bhi] = fila.pop(), [i, j, k] = maior(alo, ahi, blo, bhi);
    if(k){ m += k; if(alo < i && blo < j) fila.push([alo, i, blo, j]); if(i + k < ahi && j + k < bhi) fila.push([i + k, ahi, j + k, bhi]); } }
  return 2 * m / (a.length + b.length);
}
function recusaLegenda(velho, novo, n, perto){
  if(!novo || novo.length > 120 || /[{}\\<>\u0000-\u001f\u007f]/.test(novo)) return "texto_invalido";
  const vs = velho.split(" ").filter(Boolean), ns = novo.split(" ").filter(Boolean);
  if(ns.length !== n || vs.length !== ns.length) return "numero_de_palavras";
  const termos = termosDoGlossario();
  if(sentidoDoTexto(vs, termos) !== sentidoDoTexto(ns, termos)) return "numero_ou_termo";
  const doRoteiro = new Set((Array.isArray(perto) ? perto : String(perto || "").split(/\s+/)).map(letrasFala).filter(Boolean));
  for(let i = 0; i < vs.length; i++){
    if(sentidoDaPalavra(vs[i], termos) !== sentidoDaPalavra(ns[i], termos)) return "numero_ou_termo";
    const lv = letrasFala(vs[i]), ln = letrasFala(ns[i]);
    if(ln !== lv && !doRoteiro.has(ln) && razaoVideo(lv, ln) < 0.6) return "palavra_diferente";
  }
  return null;
}
/* Os ajustes da tela: os de antes (as edições da legenda ficam: o robô já aplicou, e a chave "u:n" aponta as palavras do alinhamento,
   que não muda com os cortes) e o que está marcado agora. As edições vão numa LISTA [["u:n", "texto"], …], na ordem em que o robô
   aplica: a nova, no fim, vale sobre a antiga que cai no mesmo trecho (num objeto, o jsonb devolveria as chaves em outra ordem e a
   antiga desfaria a nova em silêncio). */
function ajustesDaTela(v){
  const antes = objVideo(v.ajustes), aj = {}, blocos = listaVideo(objVideo(objVideo(v.relatorio).legenda).lista);
  const manter = [...document.querySelectorAll("#video-reel .video-manter:checked")].map(c => Number(c.value));
  const errou = [...document.querySelectorAll("#video-reel .video-errou:checked")].map(c => Number(c.value));
  if(manter.length) aj.manter = manter;
  if(errou.length) aj.transcricao_errou = errou;
  let legenda = edicoesLegenda(antes.legenda);
  for(const c of document.querySelectorAll("#video-reel .video-legenda-texto:not(:disabled)")){
    const novo = c.value.replace(/\s+/g, " ").trim(), u = c.dataset.u, n = Number(c.dataset.n);
    if(novo === c.dataset.original) continue;
    const perto = blocos[Number(c.dataset.bloco)]?.perto;
    const motivo = recusaLegenda(c.dataset.original, novo, n, Array.isArray(perto) ? perto : v.fala_roteiro);
    if(motivo) throw new ErroApi(`Legenda (${c.labels?.[0]?.textContent?.split(" · ")[0] || "bloco"}): ${MOTIVOS_LEGENDA[motivo]}.`);
    legenda = legenda.filter(([k]) => k !== u && !k.startsWith(u + ":"));
    legenda.push([`${u}:${n}`, novo]);
  }
  if(legenda.length) aj.legenda = legenda;
  if($("#video-compacta")?.checked) aj.estilo = "compacta";
  if($("#video-sem-gancho")?.checked) aj.sem_gancho = true;
  return aj;
}
/* As edições da legenda guardadas: a lista [["u:n", "texto"], …] (na ordem) ou o objeto de antes */
const edicoesLegenda = x => Array.isArray(x) ? x.filter(e => Array.isArray(e) && e.length === 2 && typeof e[0] === "string" && typeof e[1] === "string").map(([k, t]) => [k, t])
  : Object.entries(objVideo(x)).filter(([, t]) => typeof t === "string");
const ajustesIguais = (a, b) => {
  // manter e transcricao_errou em qualquer ordem; a legenda, na ordem (é a ordem em que o robô aplica)
  const ord = x => JSON.stringify(Object.keys(x).sort().map(k => [k, k === "legenda" ? edicoesLegenda(x[k]) : Array.isArray(x[k]) ? [...x[k]].sort((p, q) => p - q) : x[k]]));
  const sem = x => { const y = {...objVideo(x)}; if(y.estilo === "normal") delete y.estilo; if(y.sem_gancho === false) delete y.sem_gancho; return y; };
  return ord(sem(a)) === ord(sem(b)); };

/* ------------------------------------------- depois de desenhar: a sondagem da situação */
/* Enquanto o vídeo está na fila ou com o robô, a tela pergunta ao banco de VIDEO_INTERVALO em VIDEO_INTERVALO (só a linha do vídeo)
   e refaz só o quadro do corretor; para com a aba oculta (visibilitychange) e quando a peça sai da tela. */
function depoisDeDesenharVideo(atraso){
  const ev = estadoVideo();
  clearTimeout(ev.relogio);
  if(!ev.visibilidade){ ev.visibilidade = true; document.addEventListener("visibilitychange", () => { if(!document.hidden) depoisDeDesenharVideo(500); }); }
  ligarPlayerVideo();
  const v = ev.atual;
  if(!v || !$("#video-reel") || !["na_fila", "processando"].includes(v.situacao)) return;
  ev.relogio = setTimeout(sondarVideo, atraso ?? VIDEO_INTERVALO);
}
async function sondarVideo(){
  const ev = estadoVideo(), v = ev.atual, caixa = $("#video-reel");
  if(!v || !caixa || Number(caixa.dataset.peca) !== v.peca_id || E.aba !== "pauta" || E.pauta.peca !== v.peca_id || document.hidden) return;
  let novo = null;
  try{ [novo] = await ler("radar_videos", {select:CAMPOS_VIDEO, id:"eq." + v.id}); }
  catch(e){ depoisDeDesenharVideo(); return; }
  if(estadoVideo().atual?.id !== v.id || !$("#video-reel")) return;                       // a tela mudou enquanto o banco respondia
  if(novo && (novo.atualizado_em !== v.atualizado_em || novo.situacao !== v.situacao)){
    ev.atual = novo;
    const c = $("#video-corpo"), s = $("#video-selo");
    if(c) c.innerHTML = corpoVideo();
    if(s) s.innerHTML = seloVideo(novo);
    if(novo.situacao !== v.situacao && ["pronto", "regravar", "erro"].includes(novo.situacao))
      recado(novo.situacao === "pronto" ? "Vídeo corrigido pronto: veja o relatório e a prévia." : novo.situacao === "regravar" ? "O vídeo corrigido ficou pronto, mas precisa regravar: veja o relatório." : "O corretor parou com erro: veja o motivo no quadro do vídeo.", novo.situacao === "pronto" ? false : "aviso");
  }
  depoisDeDesenharVideo();
}

/* ------------------------------------------- o que a aprovação do reel usa (radar-pauta.js) */
/* O sha256 do vídeo que o administrador abriu na prévia: é o que a aprovação manda (radar_pauta_aprovar confere com o vídeo pronto). */
function videoParaAprovar(){
  const ev = estadoVideo(), v = ev.atual, visto = ev.visto;
  if(!v || v.situacao !== "pronto" || !v.sha256) throw new ErroApi("O reel só é aprovado com o vídeo corrigido pronto (quadro Corretor de vídeo).");
  if(!visto || visto.id !== v.id || visto.sha256 !== v.sha256)
    throw new ErroApi("Abra a prévia (“Ver o vídeo corrigido”) e assista antes de aprovar: a aprovação fica amarrada ao vídeo que você viu.");
  return v.sha256;
}
/* Os termos de publicidade na fala transcrita (texto_final: a legenda do vídeo) e a duração: o que trava vira "Precisa regravar"; o
   aviso, confirmação na aprovação (conferirPecaTela, radar-pauta.js) */
function conferenciaDoVideo(){
  const ev = estadoVideo(), v = ev.atual, travas = [], avisos = [];
  if(!v || !E.pauta.aberta || E.pauta.aberta.formato !== "reel" || v.peca_id !== E.pauta.aberta.id) return {travas, avisos};
  const r = objVideo(v.relatorio), fala = textoDe(r.texto_final);
  const trava = [...new Set([...termosPublicidade(fala).trava, ...termosPeca(fala)])];
  if(trava.length) travas.push(`Precisa regravar: a fala do vídeo tem ${trava.map(t => `“${t}”`).join(", ")}. A publicidade da profissão contábil informa, não vende: grave de novo sem ${trava.length > 1 ? "esses termos" : "esse termo"}.`);
  const aviso = termosPublicidade(fala).aviso.filter(x => !trava.some(y => y.includes(x)));
  if(aviso.length) avisos.push(`Termos que a publicidade contábil evita na fala do vídeo: ${aviso.map(t => `“${t}”`).join(", ")}. Confira se é informação, e não propaganda.`);
  const dur = numVideo(v.duracao_final) ?? numVideo(objVideo(r.saida).duracao_s), max = limiteDuracaoVideo();
  if(dur !== null && dur > max && dur <= 90) avisos.push(`O vídeo tem ${segVideo(dur)} s, acima do limite de ${max} s (Configurações → Corretor de vídeo): confirme que é isso mesmo.`);
  return {travas, avisos};
}
/* Na peça aprovada à mão: "Baixar o vídeo aprovado" (link de 300 s, depois que o banco confere o termo de hoje e o hash aprovado) */
const botaoBaixarVideo = () => `<button class="btn sec" type="button" data-acao="video-baixar">Baixar o vídeo aprovado</button>`;

/* ------------------------------------------- Configurações: o diagnóstico (só o administrador) */
async function diagnosticoVideo(){
  const box = $("#diag-video"); if(!box) return;
  box.innerHTML = `<p class="sub">Testando…</p>`;
  try{
    const r = await funcaoVideo("diagnostico");
    box.innerHTML = `<ul class="diag">${listaVideo(r?.itens).map(i => `<li>${selo(i.ok ? "ok" : "falta", i.ok ? "ok" : "erro")} <b>${h(i.item)}</b>: ${h(i.detalhe)}</li>`).join("")}</ul>
      <p class="sub">${r?.tudo_certo ? "Tudo certo." : "Corrija o que falta (passo a passo no LEIAME)."} Função radar-video v${h(r?.versao || "?")}.</p>`;
  }catch(e){ box.innerHTML = `<div class="aviso erro">${h(e.message)}</div>`; }
}

/* O fim do envio (a função confere os clipes no armazenamento e põe na fila). Se falhar com os clipes já no armazenamento (falta um,
   tempo esgotado, rede), o quadro sai do "Enviando… 100%" e volta ao "Continuar o envio", com os arquivos ainda na tela. */
async function concluirEnvio(pid, id){
  return await funcaoVideo("envio_concluido", {id});
}

/* ------------------------------------------------- ações (o index.html junta) */
const pecaDoVideo = () => { const f = $("form[data-form=peca]"), p = estadoVideo().pecaDados;
  if(!f || !p || Number(f.dataset.id) !== p.id) throw new ErroApi("Abra a peça de novo."); return {f, p}; };
const videoDaTela = el => { const ev = estadoVideo(), v = [ev.atual, ev.envio].find(x => x && x.id === el.dataset.id);
  if(!v) throw new ErroApi("A gravação mudou: recarregue a peça."); return v; };
const VIDEO = {
  // não gravam nada: só a tela (o que grava é feito uma ação por vez)
  navegacao:["video-nova", "video-nova-cancelar", "video-clipe-mover", "video-clipe-tirar", "video-ouvir"],
  acoes:{
    "video-nova"(){ const ev = estadoVideo(); ev.nova = true; const c = $("#video-corpo"); if(c) c.innerHTML = corpoVideo(); $("#video-envio")?.scrollIntoView({block:"nearest"}); },
    "video-nova-cancelar"(){ const ev = estadoVideo(); ev.nova = false; const c = $("#video-corpo"); if(c) c.innerHTML = corpoVideo(); },
    "video-clipe-mover"(el){ const pid = estadoVideo().peca, l = clipesDe(pid), i = Number(el.dataset.i), j = i + Number(el.dataset.passo);
      if(i < 0 || j < 0 || j >= l.length) return; [l[i], l[j]] = [l[j], l[i]]; redesenharClipes(pid); },
    "video-clipe-tirar"(el){ const pid = estadoVideo().peca, l = clipesDe(pid); l.splice(Number(el.dataset.i), 1); redesenharClipes(pid); },
    "video-ouvir"(el){ const pl = $("#video-player");
      if(!pl){ recado("Abra a prévia (“Ver o vídeo corrigido”) para ouvir o trecho.", "aviso"); $("#video-previa")?.scrollIntoView({block:"nearest"}); return; }
      pl.currentTime = Math.max(0, Number(el.dataset.em) - 1.5); pl.scrollIntoView({block:"nearest"}); pl.play?.().catch(() => {}); },
    /* Enviar a gravação: o banco confere tudo ANTES (radar_video_criar, pela função) e só então os clipes sobem, um de cada vez */
    async "video-enviar"(){
      const {f, p} = pecaDoVideo();
      if(pecaMudou(f)) throw new ErroApi(AVISO_PECA_SUJA);
      const lista = clipesDe(p.id);
      conferirEnvio(p, lista);
      const quem = Number($("#video-quem")?.value || 0);
      if(!quem) throw new ErroApi("Escolha quem fala no vídeo.");
      const decl = [...document.querySelectorAll("#video-envio .video-declaracao")], falta = decl.filter(c => !c.checked);
      if(decl.length !== 4 || falta.length) throw new ErroApi("Marque as quatro declarações: " + falta.map(c => `“${c.dataset.texto}”`).join(", ") + ".");
      const {fala} = extrairFala(p.roteiro);
      if(fala.length < 20 || fala.split(" ").length < 10) throw new ErroApi("A fala para conferência ficou curta (menos de 10 palavras): confira o roteiro da peça.");
      const termos = [...new Set([...termosPublicidade(fala).trava, ...termosPeca(fala)])];
      if(termos.length) throw new ErroApi(msgTermosPeca([["roteiro", termos]], "gravar"));
      if(faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura (o administrador preenche).`);
      const r = await funcaoVideo("envio_iniciar", {peca:p.id, partes:lista.map((c, i) => ({n:i + 1, tipo:c.tipo, bytes:c.bytes})), fala_pessoa:quem,
        fala_roteiro:fala, cartela:linhasCartela(quem), gancho:!!$("#video-gancho")?.checked, declaracoes:decl.map(c => c.value)}, 90000);
      if(!UUID_VIDEO.test(String(r?.id)) || !Array.isArray(r?.envios) || r.envios.length !== lista.length) throw new ErroApi("A função devolveu o envio fora do formato. Nada foi enviado.");
      try{ await subirClipes(p.id, r.id, r.envios, lista, String(r.bucket || "radar-videos")); }
      catch(e){ await depoisDoVideo(p.id); throw e; }
      const fim = await concluirEnvio(p.id, r.id);
      delete estadoVideo().arquivos[p.id]; estadoVideo().nova = false;
      await depoisDoVideo(p.id);
      recado(`Gravação enviada: na fila do corretor. ${textoDe(fim?.robo?.mensagem)} Depois, apague os clipes do celular e da nuvem pessoal.`);
    },
    /* Continuar o envio que não terminou: tokens novos só para os clipes que faltam (a função lista o armazenamento) */
    async "video-continuar"(el){
      const {p} = pecaDoVideo(), v = videoDaTela(el), lista = clipesDe(p.id), partes = listaVideo(v.partes);
      if(lista.length !== partes.length || lista.some((c, i) => c.bytes !== partes[i].bytes || c.tipo !== partes[i].tipo))
        throw new ErroApi(`Escolha os MESMOS ${partes.length} arquivos do envio, na mesma ordem (o tamanho de cada um confere), ou descarte este envio e envie de novo.`);
      const r = await funcaoVideo("envio_renovar", {id:v.id});
      try{ await subirClipes(p.id, v.id, Array.isArray(r?.envios) ? r.envios : [], lista, String(r?.bucket || "radar-videos")); }
      catch(e){ await depoisDoVideo(p.id); throw e; }
      const fim = await concluirEnvio(p.id, v.id);
      delete estadoVideo().arquivos[p.id]; estadoVideo().nova = false;
      await depoisDoVideo(p.id);
      recado(`Gravação enviada: na fila do corretor. ${textoDe(fim?.robo?.mensagem)}`);
    },
    async "video-previa"(el){ await abrirPreviaVideo(videoDaTela(el).id, false); },
    async "video-de-novo"(el){
      const v = videoDaTela(el);
      await rpc("radar_video_de_novo", {p_id:v.id});
      const robo = await acionarCorretor(); await depoisDoVideo(v.peca_id); recado(`Pedido de novo ao corretor. ${robo}`);
    },
    async "video-reconferir"(el){
      const {f, p} = pecaDoVideo(), v = videoDaTela(el);
      if(pecaMudou(f)) throw new ErroApi(AVISO_PECA_SUJA);
      const {fala} = extrairFala(p.roteiro);
      if(!confirm("Conferir a gravação com o roteiro novo? O corretor compara de novo a fala gravada com a fala para conferência do roteiro salvo (sem transcrever de novo); “Manter este trecho”, “A transcrição errou” e a legenda editada deixam de valer.")) return;
      await rpc("radar_video_reconferir", {p_id:v.id, p_fala_roteiro:fala});
      const robo = await acionarCorretor(); await depoisDoVideo(p.id); recado(`O corretor confere com o roteiro novo. ${robo}`);
    },
    async "video-descartar"(el){
      const v = videoDaTela(el);
      const envio = v.situacao === "aguardando_envio", vivo = envio ? estadoVideo().atual : null;
      if(!confirm(envio ? `Descartar o envio da gravação ${v.versao}? O que já subiu sai do armazenamento na limpeza seguinte.${vivo ? ` A gravação ${vivo.versao} continua valendo.` : ""}`
        : `Descartar a gravação ${v.versao}? Os arquivos saem do armazenamento na limpeza seguinte; para o reel, envie outra gravação.`)) return;
      await rpc("radar_video_descartar", {p_id:v.id});
      delete estadoVideo().arquivos[v.peca_id];
      for(const p of listaVideo(v.partes)) apagarLocalVideo(`radar_tus_bruto/${v.id}/${p.n}`);
      await depoisDoVideo(v.peca_id); recado(envio ? "Envio descartado." : "Gravação descartada.");
    },
    async "video-apaguei"(el){
      const v = videoDaTela(el);
      await rpc("radar_video_apaguei", {p_id:v.id});
      await depoisDoVideo(v.peca_id); recado("Registrado: os clipes foram apagados do celular e da nuvem pessoal.");
    },
    /* Depois de baixar e postar o vídeo aprovado: registra que quem baixou apagou o vídeo final do aparelho (à parte dos clipes) */
    async "video-apaguei-baixado"(el){
      const v = videoDaTela(el);
      const em = await rpc("radar_video_apaguei_baixado", {p_id:v.id});
      const box = $("#video-apaguei-baixado"); if(box) box.outerHTML = `<p class="sub" id="video-apaguei-baixado-feito">Registrado: você apagou o vídeo aprovado do celular e da nuvem pessoal${typeof em === "string" ? ` em ${h(dataHora(em))}` : ""}.</p>`;
      recado("Registrado: você apagou o vídeo aprovado que baixou do celular e da nuvem pessoal.");
    },
    async "video-ajustar"(el){
      const {p} = pecaDoVideo(), v = videoDaTela(el);
      if(!ehAdmin()) throw new ErroApi("Só o administrador ajusta o vídeo corrigido.");
      const aj = ajustesDaTela(v), cartela = $("#video-refazer-cartela")?.checked ? linhasCartela(v.fala_pessoa) : null;
      if(ajustesIguais(aj, v.ajustes) && !cartela){ recado("Nada mudou nos ajustes."); return; }
      if(cartela && faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura.`);
      if(!confirm("Montar o vídeo de novo com estes ajustes? O áudio não muda (sem transcrever de novo); leva alguns minutos.")) return;
      await rpc("radar_video_ajustar", {p_id:v.id, p_ajustes:aj, p_cartela:cartela});
      if(p.id !== estadoVideo().peca) return;
      const robo = await acionarCorretor(); estadoVideo().previa = null; await depoisDoVideo(p.id);
      recado(`Ajustes gravados: o corretor monta o vídeo de novo. ${robo}`);
    },
    /* À mão: o vídeo aprovado, com o banco conferindo o termo de hoje e o hash aprovado (radar_video_para_baixar, pela função) */
    async "video-baixar"(){
      const f = $("form[data-form=peca]"), box = $("#video-baixar"), a = E.pauta.aberta; if(!f || !box || !a) return;
      const r = await funcaoVideo("baixar", {peca:Number(f.dataset.id), lido:f.dataset.lido});
      if(!linkVideoOk(r?.url)) throw new ErroApi("A função devolveu o link fora do formato.");
      const nome = `reel-${a.data}.mp4`, v = estadoVideo().atual;
      box.innerHTML = `<p><a class="btn peq" id="video-baixar-link" href="${h(r.url)}" download="${h(nome)}" rel="noopener noreferrer">Baixar ${h(nome)}</a>
        <span class="sub">O link vale 5 minutos (vencido, clique em “Baixar o vídeo aprovado” de novo). Poste no Instagram e no Facebook e registre o link abaixo.</span></p>
        ${v ? `<div class="acoes" id="video-apaguei-baixado"><button class="btn peq sec" type="button" data-acao="video-apaguei-baixado" data-id="${h(v.id)}">Apaguei do celular e da nuvem pessoal (depois de postar)</button></div>` : ""}`;
      recado("Vídeo aprovado liberado: baixe, poste e depois apague do aparelho.");
    },
    "video-diagnostico"(){ return diagnosticoVideo(); }
  },
  forms:{}
};
