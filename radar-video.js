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
   v0.28.0: o(a) sócio(a) da Artecon (Pauta → Pessoas e termos) não precisa do termo do corretor: o aviso "sem o termo novo" não aparece
   para ele(a); as quatro declarações do envio continuam obrigatórias para todos.
   v0.29.0: só a versão e o recado do banco (o setup da v0.29.0); o lembrete "vídeo do reel para conferir" é do banco e do robô dos
   lembretes (robo/radar_lembretes.py).
   v0.30.0: só a versão e o recado do banco (o setup da v0.30.0).
   v0.31.0: só a versão e o recado do banco (o setup da v0.31.0); a versão traz as fontes oficiais que faltavam (robô).
   v0.33.0: a aba Vídeo (o editor do vídeo corrigido: cortes, legenda, estilo, gancho, cartela e capa), os cortes por padrão
   (muletas, repetições e voz entre palavras), a meta de duração (90 s; o teto é o reel de 15 min do Instagram) e o recado do banco
   (o setup então em uso).
   v0.36.0: a correção avulsa — analisar e corrigir um vídeo SEM criar uma peça na Pauta (pedido do dono de 18/10). Na aba Vídeo:
   "Corrigir um vídeo avulso" (título próprio, a fala para conferência colada direto, quem aparece escolhida ali, a mesma cartela,
   as mesmas 4 declarações e a mesma cota) e a lista das correções avulsas. O avulso segue o MESMO caminho do reel (envio TUS,
   robô, relatório, ajustes, editor, prévia); o que muda: não passa pela aprovação da peça e NUNCA é publicado pelo Radar — o
   administrador baixa o vídeo pronto (registrado) e "Conferir com o roteiro novo" não existe (a fala É o roteiro). Banco: o setup
   então em uso (radar_video_criar_avulso, radar_video_baixar_avulso; peca_id opcional + titulo em radar_videos).
   v0.40.0 (a melhoria "v0.37" da proposta): o corretor entende paráfrase e diz o que faltou — o robô ganha o juiz de sentido
   (robo/video/juiz.py, IA Central): a divergência de TERMO em que a pessoa quis dizer o mesmo deixa de pedir regravação sozinha, e
   cada divergência julgada chega com o motivo em português (relatorio.divergencias[].veredito/juiz e relatorio.veredito.resumo).
   Na tela: o resumo do juiz, o motivo em cada divergência e o botão "Aceitar (quis dizer o mesmo)" (radar_video_aceitar: o banco
   decide a situação de novo NA HORA, sem montar de novo — o avulso pronto já libera o Baixar). Avisos novos de arquivo fraco na
   chegada: resolucao_baixa (o WhatsApp comprime) e ruido_alto. Banco: a função radar_video_aceitar e a chave ajustes.aceitas
   (ajustes_falta/ajustar/concluir/reconferir). O robô honra as aceitas e carrega o veredito no parcial e no final.
   v0.44.0: o TELEPROMPTER com gravação pelo navegador — na peça de reel (e no avulso), o botão "Gravar pelo navegador
   (teleprompter)" abre o roteiro rolando em letras grandes (tamanho, velocidade e espelho ajustáveis) com a câmera do aparelho;
   a gravação (MediaRecorder) entra na LISTA DE CLIPES como um arquivo normal — o envio TUS, o robô (sondagem endurecida, agora
   também para o WEBM do navegador), a cota, os termos e as 4 declarações são os de sempre, e nada sobe até a pessoa ENVIAR.
   O WEBM do Chrome/Android sai sem a duração escrita e consertarDuracaoWebm a escreve (Segment → Info → Duration) antes de
   entrar na lista; o Safari grava MP4, que já entrava. Banco: radar_video_criar e radar_video_criar_avulso aceitam 'video/webm'
   (setup v0.44.0); função radar-video v0.44.0 (a lista TIPOS). As letras grandes do aplicativo ficam no index.html.
   ==================================================================== */
const VIDEO_VERSAO = "0.47.0";        // igual à VERSAO do index.html; diferente, um dos dois ficou guardado no navegador (Ctrl+F5)
const VIDEO_PEDACO = 6 * 1024 * 1024;                 // TUS do Supabase: pedaços de 6 MiB (“must be set to 6MB”), o último menor
const VIDEO_MAX_CLIPES = 12, VIDEO_MAX_BYTES = 500 * 1024 * 1024, VIDEO_MAX_SEGUNDOS = 960;   // v0.33.0: o Instagram aceita reel de 15 min pela API; 960 s dão folga
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
  formato:"um dos clipes não é MP4 ou MOV de câmera nem gravação do navegador (ou não tem imagem, ou está sem a duração): envie os arquivos originais do celular ou grave de novo pelo teleprompter",
  sem_audio:"um dos clipes está sem som: grave de novo com o microfone ligado",
  deitado:"um dos clipes está deitado (horizontal): grave na vertical",
  longo_demais:"os clipes somam mais de 16 minutos (960 s): envie só as tomadas boas",
  arquivo_grande:"um clipe chegou maior que o declarado: envie a gravação de novo",
  sem_fala:"nenhuma fala foi encontrada nos clipes: confira o som e grave de novo",
  cartela_nao_cabe:"a cartela final não coube: encurte a identificação (Configurações → Assinatura), o nome na peça de quem fala (Pauta → Pessoas e termos) ou o texto extra (Configurações → Corretor de vídeo) e use Tentar de novo (a cartela é refeita com o que estiver lá; o texto extra próprio deste vídeo, escolhido na aba Vídeo, sai e volta o das Configurações: um mais curto se escolhe de novo na aba Vídeo, com o vídeo pronto)",
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
  termo:"uma pessoa da peça não pode mais aparecer no vídeo (termo revogado ou vencido, pessoa inativa ou menor de idade, ou quem fala desmarcada da peça, ou a marca de sócio(a) tirada sem os termos): confira em Pauta → Pessoas e termos e depois use Tentar de novo",
  robo_nao_pegou:"o robô não pegou o pedido depois de 3 acionamentos da reserva: o administrador confere no repositório privado radar-video o segredo RADAR_VIDEO_ROBO_CHAVE e as variáveis RADAR_VIDEO_URL e RADAR_VIDEO_COMMIT (e, no Supabase, o segredo RADAR_VIDEO_GITHUB_TOKEN); depois, Tentar de novo",
  robo_chave:"o robô foi recusado pela função radar-video: o administrador confere o segredo RADAR_VIDEO_ROBO_CHAVE do repositório privado (cópia do Vault radar_video_robo)",
  robo_sem_chave:"falta o segredo RADAR_VIDEO_ROBO_CHAVE no repositório privado radar-video",
  robo_config:"a configuração do repositório privado radar-video está errada (RADAR_VIDEO_URL ou RADAR_VIDEO_COMMIT)",
  github:"o robô parou antes de terminar (ele tenta de novo sozinho; depois de 3 vezes, use Tentar de novo)",
  tempo_esgotado:"o robô passou do tempo: tente de novo",
  storage:"o armazenamento não respondeu: tente de novo", rede:"falha de rede no robô: tente de novo",
  limite_armazenamento:"o vídeo corrigido passou do limite de tamanho de arquivo do armazenamento (no plano Free do Supabase, 50 MB por arquivo): grave um reel mais curto e envie de novo; no plano Pro, o administrador sobe o limite em Supabase → Storage → Settings e usa Tentar de novo",
  ffmpeg_falhou:"a montagem do vídeo falhou: tente de novo; se repetir, avise o administrador",
  ffmpeg_tempo:"a montagem do vídeo passou do tempo: tente de novo", medida_falhou:"a medida do som falhou: tente de novo",
  // v0.33.0: a aba Vídeo
  robo_desatualizado:"o robô do repositório privado ainda está no commit antigo e não aplica as mudanças da aba Vídeo: o administrador troca a variável RADAR_VIDEO_COMMIT do repositório radar-video pelo commit desta versão (LEIAME) e usa Tentar de novo",
  edicao_curta:"os cortes da aba Vídeo deixaram menos de 2 s de fala: desfaça os cortes do editor e monte de novo"};
const ERRO_INTERNO_VIDEO = "erro interno do corretor: tente de novo; se repetir, avise o administrador";
const AVISOS_VIDEO = {
  fala_diferente_do_roteiro:"A fala ficou muito diferente do roteiro (menos de 60% do roteiro foi reconhecido): ouça a prévia e confira a fala para conferência.",
  legenda_recusada:"Parte da edição da legenda foi recusada (veja em Legenda).",
  duracao_acima_do_limite:"O vídeo passou do limite de duração das Configurações: a aprovação pede confirmação.",
  relatorio_resumido:"O relatório ficou grande e foi resumido (as divergências estão todas aqui).",
  transcricao_vazia:"A transcrição não reconheceu nenhuma palavra: os cortes foram feitos só pelos silêncios; ouça a prévia antes de aprovar.",
  boletim_pago:"A fala tem frase igual à do boletim pago (ITC): grave de novo com palavras próprias.",
  gancho_nao_cabe:"O texto do gancho não coube na tela e ficou de fora: encurte o texto do gancho ou marque “Sem o texto do gancho”.",
  lista_resumida:"As listas do relatório ficaram longas e foram resumidas.",
  capa_movida:"A capa escolhida caiu num trecho cortado e foi para o quadro mais perto: confira na aba Vídeo.",
  // v0.40.0: o arquivo fraco na chegada e o juiz de sentido
  resolucao_baixa:"A gravação chegou com resolução baixa (o WhatsApp comprime o vídeo): da próxima vez, envie o arquivo original do celular (cabo, AirDrop ou um drive) para um reel nítido.",
  ruido_alto:"O áudio chegou com muito ruído de fundo: o corretor limpa o que dá, mas fica melhor gravando em lugar silencioso ou com microfone.",
  juiz_indisponivel:"O juiz de sentido (IA) não respondeu nesta rodada: as divergências ficaram sem julgamento (dá para aceitar à mão ou montar de novo)."};
const MOTIVOS_LEGENDA = {bloco_inexistente:"o bloco não existe mais (o vídeo mudou: recarregue a peça)",
  texto_invalido:"texto vazio, com mais de 120 caracteres ou com { } \\ < >",
  numero_de_palavras:"o bloco fica com o mesmo número de palavras (troque palavra por palavra)",
  numero_ou_termo:"número, data, mês ou termo do glossário não muda pela legenda (se a fala está errada, regrave; se a transcrição errou, use “A transcrição errou (vale o roteiro)”)",
  palavra_diferente:"cada palavra nova é a do roteiro ou parecida com a que estava"};
const TIPOS_CORTE = {pausa:"pausa longa encurtada", hesitacao:"hesitação", muleta:"muleta (né, tipo…)", voz_entre_palavras:"voz entre palavras (hesitação ou repetição)",
  repeticao:"repetição", falso_inicio:"falso início", remover:"trecho", editor:"corte da aba Vídeo", editor_fora:"fora do começo ou do fim marcados"};
const TIPOS_DIVERGENCIA = {numero:"número", data:"data", termo:"termo"};
// varredura geral (v0.22.0): + "pessoas" (quem estava marcada no envio): a caixa "A pessoa viu o vídeo final" da aprovação olha para elas
const CAMPOS_VIDEO = "id,peca_id,titulo,versao,situacao,modo,partes,fala_pessoa,pessoas,fala_roteiro,roteiro_hash,cartela_linhas,gancho,ajustes,tentativas," +
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
const limiteDuracaoVideo = () => { const n = numVideo(confVideo().duracao_max_s); return n !== null && n >= 15 && n <= 900 ? n : 90; };   // v0.33.0: a meta (só aviso); o teto da API é 900 s
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
  catch(e){ if(semTabelaDoVideo(e)) return `<div class="aviso erro" id="video-sem-banco">O corretor de vídeo precisa do banco da v0.32.0 (ou mais nova): o administrador roda o <b>sql/radar-setup-v0.47.0.sql</b> (Supabase → SQL Editor) e recarrega esta página.</div>`; throw e; }
  if(ev.peca !== p.id){ ev.nova = false; ev.previa = null; ev.visto = null; }
  ev.peca = p.id;
  ev.pecaDados = {id:p.id, data:p.data, situacao:p.situacao, roteiro:p.roteiro || "", chamada:p.chamada || "", pessoas:p.pessoas || [], aprovado_modo:p.aprovado_modo};
  // quanto o corretor ainda transcreve neste mês (o banco confere de novo no envio, com a duração dos clipes); sem a resposta, nada
  ev.cota = ["planejada", "em_producao", "pronta"].includes(p.situacao) ? await rpc("radar_video_cota", {}).catch(() => null) : null;
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
// quando apagar os clipes do celular: depois do relatório (o envio novo substitui TODOS os clipes: quem apagou cedo regrava tudo por um
// bloco só), e no mesmo dia do envio, como o termo pede
const QUANDO_APAGAR = {
  na_fila:"Guarde os clipes no celular até o relatório (em alguns minutos): se precisar regravar um bloco, os outros vão de novo sem regravar. Depois, apague do celular e da nuvem pessoal, no mesmo dia do envio (o termo pede).",
  pronto:"Vídeo corrigido pronto: apague hoje os clipes do celular e da nuvem pessoal (inclusive da lixeira) e marque aqui; o termo pede no mesmo dia do envio.",
  regravar:"Para enviar de novo, regrave só o bloco errado e mande os outros clipes como estão. Apague todos do celular e da nuvem pessoal no mesmo dia do envio (o termo pede).",
  erro:"Guarde os clipes até o corretor terminar (Tentar de novo) ou até enviar de novo; apague do celular e da nuvem pessoal no mesmo dia do envio (o termo pede)."};
QUANDO_APAGAR.processando = QUANDO_APAGAR.na_fila;
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
// o tipo que o banco aceita: MP4 ou MOV (o iPhone manda "video/quicktime"; sem tipo, pela extensão);
// v0.44.0: + o WEBM da gravação do teleprompter pelo navegador (o MediaRecorder do Chrome/Android; o do Safari grava MP4)
const tipoClipe = a => /^video\/(mp4|quicktime|webm)$/.test(String(a.type).split(";")[0]) ? String(a.type).split(";")[0]
  : /\.(mp4|m4v)$/i.test(a.name) ? "video/mp4" : /\.mov$/i.test(a.name) ? "video/quicktime" : /\.webm$/i.test(a.name) ? "video/webm" : "";
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
  // v0.28.0: sócio(a) da Artecon (maior de idade) não precisa do termo novo (o banco também dispensa: radar_video_pessoa_falta)
  const falta = pessoas.map(x => [x, x.menor ? "menor de idade: o corretor não aceita nesta versão" : !x.socio && !x.termo_corretor_em ? "sem o termo novo, que cita o corretor de vídeo" : !x.ativo ? "inativa" : ""]).filter(([, m]) => m);
  return `<div class="video-envio" id="video-envio"><h3>${v ? "Enviar nova gravação" : "Enviar a gravação"}</h3>
    ${!pessoas.length ? `<div class="aviso alerta">Marque em Quem aparece (e salve) a pessoa que fala no vídeo.</div>` : ""}
    ${falta.length ? `<div class="aviso alerta" id="video-pessoas-falta"><b>Antes de gravar, em Pauta → Pessoas e termos:</b><ul class="pauta-erros">${falta.map(([x, m]) => `<li>${h(x.nome_na_peca)}: ${h(m)}</li>`).join("")}</ul></div>` : ""}
    ${campoClipes(p)}<div id="video-clipes">${listaClipes(p.id)}</div>${linhaCotaVideo()}
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
const campoClipes = p => `<label for="video-arquivos">Clipes, na ordem do roteiro (1 a 12, MP4, MOV ou a gravação do navegador, até 500 MB no total)</label>
  <input id="video-arquivos" type="file" multiple accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.m4v,.webm" data-video-arquivos="${p.id}">
  <div class="acoes"><button class="btn sec" type="button" data-acao="video-teleprompter" data-id="${p.id}">Gravar pelo navegador (teleprompter)</button></div>`;
/* Os segundos de transcrição que sobram no mês (radar_video_cota) ou null; a linha que o formulário do envio mostra */
const restaVideo = () => { const c = objVideo(estadoVideo().cota), u = numVideo(c.segundos_mes), l = numVideo(c.limite_s); return u !== null && l !== null ? Math.max(0, l - u) : null; };
const linhaCotaVideo = () => { const c = objVideo(estadoVideo().cota), r = restaVideo(); return r === null ? "" :
  `<p class="sub" id="video-cota">Transcrição do corretor neste mês: ${segVideo(numVideo(c.segundos_mes) / 60)} de ${segVideo(numVideo(c.limite_s) / 60)} minutos usados (restam ${segVideo(r / 60)} min, cerca de ${segVideo(r, 0)} s).</p>`; };
/* A soma das durações que o navegador leu (null se algum clipe não abriu: o robô confere) */
const duracaoClipes = l => l.length && l.every(c => c.duracao) ? l.reduce((s, c) => s + c.duracao, 0) : null;
/* A lista dos clipes escolhidos (reordenável); "partes": as do envio que não terminou (o tamanho de cada uma confere) */
function listaClipes(pid, partes){
  const l = clipesDe(pid);
  if(!l.length) return `<p class="sub">Nenhum clipe escolhido.</p>`;
  const total = l.reduce((s, c) => s + c.bytes, 0), dur = duracaoClipes(l), resta = restaVideo();
  const avisos = [l.length > VIDEO_MAX_CLIPES ? `São ${l.length} clipes: envie no máximo ${VIDEO_MAX_CLIPES}.` : "",
    total > VIDEO_MAX_BYTES ? `Os clipes somam ${mbVideo(total)}: o máximo é 500 MB.` : "",
    dur && dur > VIDEO_MAX_SEGUNDOS ? `Os clipes somam cerca de ${segVideo(dur, 0)} s: o corretor recusa acima de 16 minutos (envie só as tomadas boas).` : "",
    dur && resta !== null && dur > resta ? `Os clipes somam cerca de ${segVideo(dur, 0)} s, e o corretor só pode transcrever mais ${segVideo(resta, 0)} s neste mês: o envio é recusado (grave mais curto, espere o mês que vem ou peça ao administrador a transcrição paga da Azure — segredo AZURE_FALA_MODO “rapido” no repositório privado).` : ""].filter(Boolean);
  return `<ol class="video-clipes">${l.map((c, i) => { const parte = partes?.[i], difere = parte && (parte.bytes !== c.bytes || parte.tipo !== c.tipo);
    return `<li data-i="${i}"><span class="video-clipe-nome"><b>${i + 1}.</b> ${h(c.nome)} · ${mbVideo(c.bytes)}${c.duracao ? ` · ${segVideo(c.duracao)} s` : ""}</span>
      ${!c.tipo ? selo("não é MP4, MOV nem gravação do navegador", "erro") : ""}${c.aviso ? " " + selo(c.aviso, "alerta") : ""}${difere ? " " + selo(`não é o clipe nº ${i + 1} do envio`, "erro") : ""}
      <span class="acoes"><button class="btn peq sec" type="button" data-acao="video-clipe-mover" data-i="${i}" data-passo="-1"${i ? "" : " disabled"} aria-label="Subir o clipe ${i + 1}">↑</button>
        <button class="btn peq sec" type="button" data-acao="video-clipe-mover" data-i="${i}" data-passo="1"${i < l.length - 1 ? "" : " disabled"} aria-label="Descer o clipe ${i + 1}">↓</button>
        <button class="btn peq perigo" type="button" data-acao="video-clipe-tirar" data-i="${i}">Tirar</button></span></li>`; }).join("")}</ol>
    <p class="sub">${l.length} clipe(s), ${mbVideo(total)} no total${dur ? `, cerca de ${segVideo(dur, 0)} s` : ""}.${dur && resta !== null && dur <= resta ? ` <span id="video-gasto-cota">Este envio gasta cerca de ${segVideo(dur, 0)} s da transcrição do mês (sobram ${segVideo(Math.max(0, resta - dur), 0)} s).</span>` : ""}</p>
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

/* ------------------------------------------------------------- o teleprompter (v0.44.0) */
/* O roteiro rolando em LETRAS GRANDES enquanto a pessoa grava pelo próprio navegador (de preferência o do celular, em pé: o
   corretor só aceita vídeo na vertical). A gravação (MediaRecorder) entra na lista de clipes como um arquivo normal — o envio,
   o robô e as travas são os de sempre; nada sobe daqui. No Chrome/Android a gravação sai WEBM, e o MediaRecorder não escreve a
   duração no arquivo: consertarDuracaoWebm a escreve (sem ela o robô recusa, de propósito). No Safari/iPhone sai MP4, que já
   entrava. Nenhuma imagem ou som sai do aparelho até a pessoa ENVIAR os clipes, como sempre. */
/* As linhas que rolam: no roteiro do kit, a Fala de cada linha; na tabela do plano, a coluna Fala; sem marcador, as frases. */
function linhasTeleprompter(roteiro){
  const linhas = String(roteiro ?? "").replace(/\r\n/g, "\n").split("\n");
  const kit = linhas.map(l => /^[^\n]*?\s[—–]\s*Fala:\s*([^\n]+?)(?:\s+\|\s*Na tela:[^\n]*)?$/.exec(l.trim())).filter(Boolean).map(m => juntarFala(m[1]));
  if(kit.length) return kit;
  const falas = []; let col = null;
  for(const l of linhas){
    const s = l.trim();
    if(!s.startsWith("|")){ col = null; continue; }
    const cel = s.replace(/^\|+|\|+$/g, "").split("|").map(c => c.trim());
    if(col === null){ const nomes = cel.map(letrasFala); col = nomes.includes("fala") ? nomes.indexOf("fala") : null; continue; }
    if(cel.filter(Boolean).every(c => /^:?-{2,}:?$/.test(c))) continue;
    const c = col < cel.length ? semAspasFala(cel[col]) : "";
    if(c) falas.push(juntarFala(c));
  }
  if(falas.length) return falas;
  return juntarFala(String(roteiro ?? "")).split(/(?<=[.!?…])\s+/).filter(Boolean);
}
/* O WEBM do MediaRecorder sai sem a duração escrita (o navegador não sabe o fim na hora do cabeçalho). Aqui a duração medida
   pelo relógio da gravação entra no lugar certo (Segment → Info → Duration, id 0x4489), sem tocar no resto do arquivo. EBML:
   cada elemento é id (1–4 bytes) + tamanho (VINT de 1–8 bytes) + conteúdo; só o começo do arquivo é lido. Qualquer coisa fora
   do esperado devolve o blob como veio (o robô então recusa com o motivo, como deve). */
function lerVintTele(b, i, ehId){
  if(i >= b.length || !b[i]) return null;
  const n = Math.clz32(b[i]) - 24 + 1;
  if(n < 1 || n > 8 || i + n > b.length) return null;
  let v = ehId ? b[i] : b[i] & (0xff >> n);
  for(let k = 1; k < n; k++) v = v * 256 + b[i + k];
  return {v, n, desconhecido:!ehId && v === Math.pow(2, 7 * n) - 1};
}
async function consertarDuracaoWebm(blob, duracaoMs){
  try{
    const b = new Uint8Array(await blob.slice(0, 65536).arrayBuffer());
    const cab = lerVintTele(b, 0, true);                                        // o cabeçalho EBML (0x1A45DFA3)
    if(!cab || cab.v !== 0x1A45DFA3) return blob;
    const cabTam = lerVintTele(b, cab.n);
    if(!cabTam || cabTam.desconhecido) return blob;
    let i = cab.n + cabTam.n + cabTam.v;
    const seg = lerVintTele(b, i, true);                                        // o Segment (0x18538067), tamanho desconhecido
    if(!seg || seg.v !== 0x18538067) return blob;
    const segTam = lerVintTele(b, i + seg.n);
    if(!segTam) return blob;
    i += seg.n + segTam.n;
    while(i < b.length){                                                        // os filhos do Segment, até o Info (0x1549A966)
      const id = lerVintTele(b, i, true), tam = id && lerVintTele(b, i + id.n);
      if(!id || !tam || tam.desconhecido) return blob;
      const conteudo = i + id.n + tam.n, fim = conteudo + tam.v;
      if(id.v === 0x1549A966){
        if(fim > b.length) return blob;
        let escala = 1e6, j = conteudo, dur = null;
        while(j < fim){                                                         // dentro do Info: TimecodeScale e Duration
          const fid = lerVintTele(b, j, true), ftam = fid && lerVintTele(b, j + fid.n);
          if(!fid || !ftam || ftam.desconhecido) return blob;
          const c = j + fid.n + ftam.n;
          if(fid.v === 0x2AD7B1){ let e = 0; for(let k = 0; k < ftam.v; k++) e = e * 256 + b[c + k]; if(e) escala = e; }
          if(fid.v === 0x4489) dur = {pos:c, bytes:ftam.v};
          j = c + ftam.v;
        }
        const valor = duracaoMs * 1e6 / escala;
        if(dur){                                                                // já tem a duração: troca no lugar (4 ou 8 bytes)
          if(dur.bytes !== 4 && dur.bytes !== 8) return blob;
          const f = new Uint8Array(dur.bytes), dv = new DataView(f.buffer);
          if(dur.bytes === 8) dv.setFloat64(0, valor); else dv.setFloat32(0, valor);
          return new Blob([blob.slice(0, dur.pos), f, blob.slice(dur.pos + dur.bytes)], {type:blob.type});
        }
        const f8 = new Uint8Array(8); new DataView(f8.buffer).setFloat64(0, valor);
        // o Info cresce 11 bytes (44 89 + 88 + os 8 do número) e o tamanho dele é reescrito num VINT de 8 bytes (sempre cabe);
        // o Segment tem tamanho desconhecido, então nada acima precisa mudar
        const vint8 = new Uint8Array(8); vint8[0] = 0x01;
        let v = tam.v + 11;
        for(let k = 7; k >= 1; k--){ vint8[k] = v % 256; v = Math.floor(v / 256); }
        if(v) return blob;
        return new Blob([blob.slice(0, i + id.n), vint8, blob.slice(conteudo, fim),
                         new Uint8Array([0x44, 0x89, 0x88, ...f8]), blob.slice(fim)], {type:blob.type});
      }
      i = fim;
    }
    return blob;
  }catch(e){ return blob; }
}
/* O estado do teleprompter aberto (só um por vez); nada dele fica guardado além da gravação que entra na lista de clipes */
let TELE = null;
function fecharTeleprompter(){
  if(!TELE) return;
  try{ if(TELE.gravador && TELE.gravador.state !== "inactive") TELE.gravador.stop(); }catch(e){ /* já parou */ }
  try{ (TELE.fluxo?.getTracks() || []).forEach(t => t.stop()); }catch(e){ /* sem câmera */ }
  if(TELE.relogio) cancelAnimationFrame(TELE.relogio);
  if(TELE.url) URL.revokeObjectURL(TELE.url);
  $("#teleprompter")?.remove();
  TELE = null;
}
function rolarTeleprompter(agora){
  if(!TELE || !TELE.rolando) return;
  const rolo = $("#tele-rolo");
  if(rolo){
    TELE.y += TELE.veloc * ((agora - (TELE.antes || agora)) / 1000);
    rolo.style.transform = `translateY(${-Math.round(TELE.y)}px)`;
  }
  TELE.antes = agora;
  TELE.relogio = requestAnimationFrame(rolarTeleprompter);
}
async function abrirTeleprompter(pid){
  if(TELE) fecharTeleprompter();
  // na peça, o roteiro dela; no avulso (pid 0), a fala para conferência colada no formulário (ela é o "roteiro" do avulso)
  const roteiro = pid ? pecaDoVideo().p?.roteiro : $("#vaba-avulso-fala")?.value;
  const linhas = linhasTeleprompter(roteiro);
  if(!linhas.length || !textoDe(roteiro)){ recado(pid ? "A peça está sem roteiro: escreva o roteiro antes de abrir o teleprompter." :
    "Cole primeiro a fala para conferência: é ela que o teleprompter mostra.", true); return; }
  const podeGravar = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
  TELE = {pid, veloc:40, letra:44, y:0, rolando:false, tomadas:0, gravador:null, fluxo:null, pedacos:[], inicioMs:0, url:null};
  document.body.insertAdjacentHTML("beforeend", `<div class="fundo-previa" id="teleprompter"><div class="caixa-previa caixa-tele" role="dialog" aria-modal="true" aria-label="Teleprompter">
    <div class="tele-topo">
      <video id="tele-camera" autoplay muted playsinline></video>
      <div class="tele-controles">
        <div class="acoes">${podeGravar ? `<button class="btn verde" type="button" data-acao="tele-gravar" id="tele-gravar">Começar a gravar</button>` : ""}
          <button class="btn sec" type="button" data-acao="tele-rolar" id="tele-rolar">Rolar o texto</button>
          <button class="btn sec" type="button" data-acao="tele-fechar">Fechar</button></div>
        <div class="acoes"><button class="btn peq sec" type="button" data-acao="tele-letra" data-passo="-1" aria-label="Letra menor">A−</button>
          <button class="btn peq sec" type="button" data-acao="tele-letra" data-passo="1" aria-label="Letra maior">A+</button>
          <button class="btn peq sec" type="button" data-acao="tele-veloc" data-passo="-1">Mais devagar</button>
          <button class="btn peq sec" type="button" data-acao="tele-veloc" data-passo="1">Mais rápido</button>
          <button class="btn peq sec" type="button" data-acao="tele-espelho">Espelhar o texto</button></div>
        <p class="sub" id="tele-aviso">${podeGravar ? "Grave no celular, EM PÉ (vertical): o corretor recusa vídeo deitado. A gravação entra na lista de clipes; nada é enviado até você mandar."
          : "Este navegador não grava vídeo: use o teleprompter só para ler e grave pela câmera do celular."}</p>
      </div>
    </div>
    <div class="tele-janela"><div class="tele-rolo" id="tele-rolo" style="font-size:${TELE.letra}px">${linhas.map(l => `<p>${h(l)}</p>`).join("")}</div></div>
  </div></div>`);
  if(podeGravar){
    try{
      TELE.fluxo = await navigator.mediaDevices.getUserMedia({audio:true,
        video:{facingMode:"user", width:{ideal:1080}, height:{ideal:1920}, aspectRatio:{ideal:9 / 16}}});
      const cam = $("#tele-camera");
      if(cam) cam.srcObject = TELE.fluxo;
      const faixa = TELE.fluxo.getVideoTracks()[0], d = faixa?.getSettings?.() || {};
      if(d.width && d.height && d.width > d.height)
        $("#tele-aviso").textContent = "A câmera está DEITADA (horizontal): o corretor recusa. Grave pelo celular em pé, ou use o teleprompter só para ler.";
    }catch(e){
      const av = $("#tele-aviso");
      if(av) av.textContent = "A câmera não abriu (sem permissão ou sem câmera): use o teleprompter só para ler e grave pelo celular.";
    }
  }
}
/* O tipo da gravação: o primeiro que o navegador sabe gravar (Safari grava MP4; Chrome/Android, WEBM) */
function tipoGravacaoTele(){
  for(const t of ["video/mp4", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"])
    if(window.MediaRecorder?.isTypeSupported?.(t)) return t;
  return "";
}
async function pararGravacaoTele(){
  const g = TELE?.gravador;
  if(!g || g.state === "inactive") return;
  const fim = new Promise(ok => { g.onstop = ok; });
  g.stop();
  await fim;
  const duracaoMs = Math.max(200, Date.now() - TELE.inicioMs);
  const tipo = String(g.mimeType || tipoGravacaoTele()).split(";")[0] || "video/webm";
  let blob = new Blob(TELE.pedacos, {type:tipo});
  TELE.pedacos = []; TELE.gravador = null;
  if(tipo === "video/webm") blob = await consertarDuracaoWebm(blob, duracaoMs);
  TELE.tomadas += 1;
  const nome = `teleprompter-${TELE.tomadas}.${tipo === "video/mp4" ? "mp4" : "webm"}`;
  const arquivo = new File([blob], nome, {type:tipo});
  const d = TELE.fluxo?.getVideoTracks?.()[0]?.getSettings?.() || {};
  clipesDe(TELE.pid).push({arquivo, nome, bytes:arquivo.size, tipo:tipoClipe(arquivo), duracao:duracaoMs / 1000,
    aviso:d.width && d.height && d.width > d.height ? "parece deitado (horizontal)" : ""});
  redesenharClipes(TELE.pid);
  if(TELE.url) URL.revokeObjectURL(TELE.url);
  TELE.url = URL.createObjectURL(arquivo);
  const g2 = $("#tele-gravar");
  if(g2){ g2.textContent = "Começar a gravar"; g2.classList.remove("perigo"); g2.classList.add("verde"); }
  const av = $("#tele-aviso");
  if(av) av.innerHTML = `Tomada ${TELE.tomadas} (${segVideo(duracaoMs / 1000)} s) entrou na lista de clipes. <a href="${TELE.url}" download="${h(nome)}">Baixar esta tomada</a> (se quiser guardar).`;
}
/* O que vai à função no envio: confere tudo o que a tela sabe ANTES de qualquer arquivo sair (o banco confere de novo) */
function conferirEnvio(p, lista){
  if(!lista.length) throw new ErroApi("Escolha os clipes do reel (de 1 a 12, na ordem do roteiro).");
  if(lista.length > VIDEO_MAX_CLIPES) throw new ErroApi(`São ${lista.length} clipes: envie no máximo ${VIDEO_MAX_CLIPES} (tire as tomadas que não vão).`);
  const ruim = lista.filter(c => !c.tipo);
  if(ruim.length) throw new ErroApi(`Só vídeo MP4 ou MOV, como sai da câmera do celular, ou a gravação do teleprompter: ${ruim.map(c => c.nome).join(", ")}.`);
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
    if(r.status === 413) throw new ErroApi(`O clipe nº ${n} passou do limite de tamanho de arquivo do armazenamento (no plano Free do Supabase, 50 MB por arquivo): grave blocos mais curtos (de 10 a 20 s, em 1080p e 30 quadros por segundo) e envie de novo.`, 413);
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
  // v0.33.0: o editor do vídeo na aba Vídeo (cortes, legenda, estilo, gancho, cartela e capa)
  if(v.situacao !== "aguardando_envio")
    partes.push(`<div class="acoes video-ir-aba"><button class="btn sec" type="button" data-acao="video-aba" data-id="${h(v.id)}">${adm ? "Editar na aba Vídeo" : "Ver na aba Vídeo"}</button></div>`);
  if(final && v.sha256 && !(Array.isArray(v.arquivos_apagados) ? v.arquivos_apagados : []).includes("corrigido"))
    partes.push(`<div class="video-previa-quadro"><h3>Prévia</h3><div id="video-previa">${htmlPrevia()}</div></div>`);
  if(podeAjustar) partes.push(blocoAjustes(v));
  if(livre && ["pronto", "regravar", "erro"].includes(v.situacao))
    partes.push(`<div class="acoes video-descartar"><button class="btn peq perigo" type="button" data-acao="video-descartar" data-id="${h(v.id)}">Descartar esta gravação</button></div>`);
  // os clipes no celular: guardados até o relatório (para regravar só o bloco errado: o envio novo substitui todos) e apagados no
  // mesmo dia do envio, como o termo pede; o "Apaguei" ganha destaque quando o vídeo fica pronto
  if(v.enviado_em && ["na_fila", "processando", "pronto", "regravar", "erro"].includes(v.situacao))
    partes.push(v.apagado_aparelho_em ? `<p class="sub" id="video-apaguei-feito">Registrado: os clipes foram apagados do celular e da nuvem pessoal em ${h(dataHora(v.apagado_aparelho_em))}.</p>`
      : `<div class="acoes video-apaguei"><button class="btn ${v.situacao === "pronto" ? "" : "peq sec"}" type="button" data-acao="video-apaguei" data-id="${h(v.id)}">Apaguei do celular e da nuvem pessoal</button>
        <span class="sub" id="video-apaguei-quando">${h(QUANDO_APAGAR[v.situacao] || QUANDO_APAGAR.na_fila)}</span></div>`);
  return `<div class="video-situacao" id="video-situacao">${partes.join("")}</div>`;
}

/* ------------------------------------------------------------- o relatório */
/* v0.33.0 (pedido do dono: "o aplicativo não corrigiu nada"): o resumo, no topo, do que o corretor corrigiu e do que falta decidir */
function resumoCorrecoesVideo(v){
  const r = objVideo(v.relatorio), aj = objVideo(v.ajustes);
  const manter = new Set(listaMarcas(aj.manter, CHAVE_CORTE)), errou = new Set(listaMarcas(aj.transcricao_errou, ID_DIVERGENCIA));
  const aceitas = new Set(listaMarcas(aj.aceitas, ID_DIVERGENCIA));                      // v0.40.0: "Aceitar — quis dizer o mesmo"
  const cortes = listaVideo(r.cortes), meio = cortes.filter(c => numVideo(c.em_s) !== null && !c.mantido && !manter.has(String(c.chave ?? "")));
  const soma = l => segVideo(l.reduce((t, c) => t + (numVideo(c.dur_s) || 0), 0));
  const bordas = new Set(cortes.filter(c => c.tipo === "inicio" || c.tipo === "fim").map(c => c.clipe)).size;
  const pausas = meio.filter(c => c.tipo === "pausa"), editor = meio.filter(c => c.tipo === "editor");
  const sons = meio.filter(c => !["pausa", "editor"].includes(c.tipo));
  const fez = [];
  if(bordas) fez.push(`aparou o começo e o fim de ${bordas} clipe(s)`);
  if(sons.length) fez.push(`tirou ${sons.length} muleta(s), hesitação(ões) ou repetição(ões) (−${soma(sons)} s)`);
  if(pausas.length) fez.push(`encurtou ${pausas.length} pausa(s) longa(s) (−${soma(pausas)} s)`);
  if(editor.length) fez.push(`aplicou ${editor.length} corte(s) da aba Vídeo`);
  const trocas = listaVideo(r.trocas);
  if(trocas.length) fez.push(`escreveu ${trocas.length} palavra(s) da legenda na grafia do roteiro`);
  if(numVideo(objVideo(r.saida).lufs) !== null) fez.push("acertou o volume");
  if(numVideo(objVideo(r.legenda).blocos)) fez.push("gravou a legenda e a cartela");
  const divs = listaVideo(r.divergencias).filter(d => d.regravar !== false && !d.transcricao_errou && d.aceita !== true
    && !errou.has(String(d.id ?? "")) && !aceitas.has(String(d.id ?? "")));
  const fora = listaVideo(r.fora_do_roteiro), sug = listaVideo(r.sugestoes);
  const falta = [];
  if(divs.length) falta.push(`${divs.length} divergência(s) com o roteiro (regravar, cortar o trecho na aba Vídeo, marcar “A transcrição errou” ou “Aceitar — quis dizer o mesmo”)`);
  if(fora.length) falta.push(`${fora.length} trecho(s) falado(s) fora do roteiro (ficam no vídeo; a aba Vídeo corta cada um com um clique)`);
  if(sug.length) falta.push(`${sug.length} trecho(s) para ouvir`);
  if(!fez.length && !falta.length) return "";
  return `<p class="sub" id="video-resumo-correcoes"><b>O corretor corrigiu:</b> ${fez.length ? fez.join("; ") : "nada precisou de correção"}. ${falta.length ? `<b>Falta decidir:</b> ${falta.join("; ")}.` : "<b>Nada falta decidir.</b>"}</p>`;
}
/* Em português simples, com os tempos do vídeo corrigido (em_s). O parcial (logo depois do alinhamento) já diz se precisa regravar. */
function blocoRelatorio(v, podeAjustar){
  const r = objVideo(v.relatorio), parcial = relatorioParcial(v), aj = objVideo(v.ajustes);
  const manter = new Set(listaMarcas(aj.manter, CHAVE_CORTE)), errou = new Set(listaMarcas(aj.transcricao_errou, ID_DIVERGENCIA));
  const aceitasAj = new Set(listaMarcas(aj.aceitas, ID_DIVERGENCIA));                     // v0.40.0
  const podeAceitar = podeAjustar && ["pronto", "regravar"].includes(v.situacao);         // o aceitar libera NA HORA, sem montar de novo
  const em = x => numVideo(x) !== null ? `aos ${segVideo(x)} s` : "";
  const ouvir = x => !parcial && numVideo(x) !== null ? ` <button class="btn peq sec" type="button" data-acao="video-ouvir" data-em="${numVideo(x)}">▶ ouvir</button>` : "";
  const itens = [], saida = objVideo(r.saida), conf = objVideo(r.conferencia), entrada = objVideo(r.entrada);
  const avisos = [...new Set((Array.isArray(r.avisos) ? r.avisos : []).map(String))];
  if(!parcial) itens.push(resumoCorrecoesVideo(v));                                  // v0.33.0: o que foi corrigido e o que falta, no topo
  // v0.40.0: o resumo do juiz de sentido (a IA que compara o sentido da fala com o roteiro), quando ele julgou
  const ver = objVideo(r.veredito);
  if(textoDe(ver.resumo)) itens.push(`<p class="sub video-veredito" id="video-veredito"><b>Juiz de sentido:</b> ${h(ver.resumo)}${numVideo(ver.liberadas) ? ` (${numVideo(ver.liberadas)} divergência(s) liberada(s): quis dizer o mesmo)` : ""}</p>`);
  if(avisos.length) itens.push(`<div class="aviso alerta video-avisos"><ul class="pauta-erros">${avisos.map(a => `<li>${h(deMapaVideo(AVISOS_VIDEO, a) || "Aviso do corretor: " + a)}</li>`).join("")}</ul></div>`);
  // o que precisa regravar: número, data ou termo diferente do roteiro
  const divs = listaVideo(r.divergencias), abertas = divs.filter(d => d.regravar !== false && !d.transcricao_errou && d.aceita !== true && !errou.has(d.id) && !aceitasAj.has(String(d.id ?? "")));
  if(divs.length) itens.push(`<div class="${abertas.length ? "aviso erro" : "aviso info"} video-divergencias"><b>${abertas.length ? "Precisa regravar:" : "Divergências (todas decididas):"}</b>
    <ul class="pauta-erros">${divs.map(d => { const k = Number(d.k), marca = ID_DIVERGENCIA.test(String(d.id ?? "")) ? d.id : "", marcado = !!d.transcricao_errou || errou.has(marca);
      const aceita = d.aceita === true || aceitasAj.has(marca);                           // v0.40.0
      return `<li class="video-divergencia" data-k="${h(k)}">${h(em(d.em_s) ? em(d.em_s)[0].toUpperCase() + em(d.em_s).slice(1) : "No vídeo")} a fala diz “${h(d.falado)}” e o roteiro diz “${h(d.roteiro)}”${deMapaVideo(TIPOS_DIVERGENCIA, d.tipo) ? ` (${h(deMapaVideo(TIPOS_DIVERGENCIA, d.tipo))})` : ""}.${d.parece_transcricao === true && !marcado && !aceita && d.cortada !== true ? ` <b>Parece erro da transcrição</b> (palavra repetida ou confiança baixa): ouça e, se a pessoa disse certo, marque “A transcrição errou”.` : ""}${textoDe(d.juiz) && !marcado && !aceita && d.cortada !== true ? ` <span class="video-juiz">Juiz de sentido: ${h(d.juiz)}</span>` : ""}${d.veredito === "equivalente" && d.regravar === false && !aceita ? ` <span class="selo ok">quis dizer o mesmo (juiz de sentido)</span>` : ""}${aceita ? ` <span class="selo ok">aceita: quis dizer o mesmo</span>` : ""}${d.cortada === true ? ` <span class="selo ok">cortada na aba Vídeo: não vai ao ar</span>` : ""}${ouvir(d.em_s)}
        ${podeAjustar && marca && !aceita ? `<label class="video-check"><input type="checkbox" class="video-errou" value="${h(marca)}"${marcado ? " checked" : ""}> A transcrição errou (vale o roteiro)</label>`
          : marcado ? ` <span class="selo ok">a transcrição errou: vale o roteiro</span>` : ""}${podeAceitar && marca && !aceita && !marcado && d.regravar !== false && d.cortada !== true ? ` <button class="btn peq sec video-btn-aceitar" type="button" data-acao="video-aceitar" data-id="${h(v.id)}" data-marca="${h(marca)}">Aceitar (quis dizer o mesmo)</button>` : ""}</li>`; }).join("")}</ul>
    ${podeAjustar && abertas.length ? `<p class="sub">Administrador: ouça na prévia. Se a pessoa disse o que está no roteiro e a transcrição é que errou, marque “A transcrição errou (vale o roteiro)” e aplique os ajustes (a legenda passa a usar o roteiro naquele trecho; o áudio não muda). Se disse o MESMO com outras palavras, use “Aceitar (quis dizer o mesmo)”: libera na hora, sem montar de novo. Se a fala está errada, grave de novo.</p>` : ""}</div>`);
  if(parcial) itens.unshift(`<p class="sub video-parcial">${["na_fila", "processando"].includes(v.situacao) ? "Relatório parcial: a fala já foi comparada com o roteiro; o vídeo ainda está sendo montado."
    : "Relatório parcial da última rodada: o corretor parou antes de montar o vídeo."}</p>`);
  // a duração
  const dur = numVideo(saida.duracao_s) ?? numVideo(v.duracao_final), max = limiteDuracaoVideo();
  if(dur !== null) itens.push(`<li id="video-duracao">Duração: ${segVideo(dur)} s${numVideo(saida.fala_s) !== null ? ` (fala ${segVideo(saida.fala_s)} s + cartela ${segVideo(saida.cartela_s ?? 3)} s)` : ""}. ${dur > 900
    ? "<b>Passou de 15 minutos: o Instagram não aceita reel mais longo pela API — corte na aba Vídeo ou grave mais curto.</b>"
    : dur > max ? `<b>Acima da meta de ${max} s</b> (Configurações → Corretor de vídeo): aceito, e a aprovação pede confirmação.${dur > 90 ? " Acima de 90 s o Facebook não aceita reel: publique só no Instagram." : ""}`
    : `Dentro da meta de ${max} s.${dur > 90 ? " Acima de 90 s o Facebook não aceita reel: publique só no Instagram." : ""}`}</li>`);
  // os cortes
  const cortes = listaVideo(r.cortes), borda = new Set(cortes.filter(c => c.tipo === "inicio" || c.tipo === "fim").map(c => c.clipe)).size;
  const meio = cortes.filter(c => numVideo(c.em_s) !== null), pausas = meio.filter(c => c.tipo === "pausa"), hes = meio.filter(c => c.tipo !== "pausa");
  const soma = l => segVideo(l.reduce((s, c) => s + (numVideo(c.dur_s) || 0), 0), 2);
  const semFala = cortes.filter(c => c.tipo === "clipe_sem_fala").length;
  if(cortes.length) itens.push(`<li id="video-cortes">Cortes: começo e fim de ${borda} clipe(s)${pausas.length ? `; ${pausas.length} pausa(s) longa(s) encurtada(s) (${soma(pausas)} s)` : ""}${hes.length ? `; ${hes.length} trecho(s) de hesitação (${soma(hes)} s)` : ""}${semFala ? `; ${semFala} clipe(s) sem fala ficaram de fora` : ""}.
    ${meio.length ? `<details class="video-cortes-meio"${meio.length <= 8 ? " open" : ""}><summary>Cortes no meio da fala (${meio.length})</summary><ul>${meio.map(c => { const k = Number(c.k), chave = CHAVE_CORTE.test(String(c.chave ?? "")) ? c.chave : "", mantido = !!c.mantido || manter.has(chave);
      return `<li class="video-corte" data-k="${h(k)}">${h(em(c.em_s))}: ${h(deMapaVideo(TIPOS_CORTE, c.tipo) || c.tipo)} (${segVideo(c.dur_s, 2)} s)${textoDe(c.texto) ? ` — “${h(c.texto)}”` : ""}${ouvir(c.em_s)}
        ${podeAjustar && chave ? `<label class="video-check"><input type="checkbox" class="video-manter" value="${h(chave)}"${mantido ? " checked" : ""}> Manter este trecho</label>` : mantido ? ` <span class="selo neutro">mantido</span>` : ""}</li>`; }).join("")}</ul></details>` : ""}</li>`);
  const sug = listaVideo(r.sugestoes);
  if(sug.length) itens.push(`<li id="video-sugestoes">Para ouvir (não foi cortado): ${sug.map(s => `${h(em(s.em_s))}, ${h(deMapaVideo(TIPOS_CORTE, s.tipo) || s.tipo)}${textoDe(s.texto) ? ` “${h(s.texto)}”` : ""}${ouvir(s.em_s)}`).join("; ")}. Se atrapalhar, grave o trecho de novo.</li>`);
  // a legenda
  const trocas = listaVideo(r.trocas);
  if(trocas.length) itens.push(`<li id="video-trocas">Legenda na grafia do roteiro: ${trocas.map(t => `“${h(t.de)}” → “${h(t.para)}”${em(t.em_s) ? ` (${h(em(t.em_s))})` : ""}`).join("; ")}.</li>`);
  const fora = listaVideo(r.fora_do_roteiro), omitido = listaVideo(r.omitido);
  if(fora.length) itens.push(`<li id="video-fora">Falado fora do roteiro (vai na legenda como foi dito): ${fora.map(x => `“${h(x.texto)}”${em(x.em_s) ? ` (${h(em(x.em_s))})` : ""}`).join("; ")}. A aba Vídeo corta cada trecho com um clique.</li>`);
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
/* As marcas dos ajustes apontam o trecho pelo que ele é, e não pela posição na lista (o robô alinha de novo a cada rodada, e a
   numeração muda): a divergência pelo id (o instante e o texto dela) e o corte pela chave "<clipe>:<quadro>" (onde começa o que ele
   corta). A que não confere com nenhum item do relatório novo fica sem efeito. */
const ID_DIVERGENCIA = /^[0-9a-f]{16}$/, CHAVE_CORTE = /^\d{1,2}:\d{1,6}b{0,3}$/;
const listaMarcas = (v, forma) => (Array.isArray(v) ? v : []).filter(x => typeof x === "string" && forma.test(x));
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
  const manter = [...document.querySelectorAll("#video-reel .video-manter:checked")].map(c => c.value).filter(x => CHAVE_CORTE.test(x));
  const errou = [...document.querySelectorAll("#video-reel .video-errou:checked")].map(c => c.value).filter(x => ID_DIVERGENCIA.test(x));
  if(manter.length) aj.manter = manter;
  if(errou.length) aj.transcricao_errou = errou;
  // v0.40.0: as aceitas ("quis dizer o mesmo") ficam valendo na montagem nova (radar_video_ajustar substitui a lista: vai a de antes)
  const aceitas = listaMarcas(antes.aceitas, ID_DIVERGENCIA);
  if(aceitas.length) aj.aceitas = aceitas;
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
  const ord = x => JSON.stringify(Object.keys(x).sort().map(k => [k, k === "legenda" ? edicoesLegenda(x[k]) : Array.isArray(x[k]) ? x[k].map(String).sort() : x[k]]));
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
/* Os termos de publicidade no que está gravado no vídeo — a fala transcrita (texto_final: a legenda do vídeo), o texto do gancho (a
   cópia da chamada no envio, que pode ser diferente da chamada de hoje) e o texto extra da cartela que o robô gravou — e a duração: o
   que trava vira "Precisa regravar"; o aviso, confirmação na aprovação (conferirPecaTela, radar-pauta.js) */
function conferenciaDoVideo(){
  const ev = estadoVideo(), v = ev.atual, travas = [], avisos = [];
  if(!v || !E.pauta.aberta || E.pauta.aberta.formato !== "reel" || v.peca_id !== E.pauta.aberta.id) return {travas, avisos};
  const r = objVideo(v.relatorio), fala = textoDe(r.texto_final);
  const gancho = objVideo(v.ajustes).sem_gancho === true ? "" : textoDe(v.gancho), extra = textoDe(r.cartela_extra);
  const trava = [...new Set([...termosPublicidade(fala).trava, ...termosPeca(fala)])];
  if(trava.length) travas.push(`Precisa regravar: a fala do vídeo tem ${trava.map(t => `“${t}”`).join(", ")}. A publicidade da profissão contábil informa, não vende: grave de novo sem ${trava.length > 1 ? "esses termos" : "esse termo"}.`);
  const noGancho = [...new Set([...termosPublicidade(gancho).trava, ...termosPeca(gancho)])], naCartela = [...new Set([...termosPublicidade(extra).trava, ...termosPeca(extra)])];
  if(noGancho.length) travas.push(`O texto do gancho gravado no vídeo tem ${noGancho.map(t => `“${t}”`).join(", ")}: o administrador marca “Sem o texto do gancho” nos ajustes, ou envie a gravação de novo com a chamada reescrita.`);
  if(naCartela.length) travas.push(`O texto extra da cartela gravado no vídeo tem ${naCartela.map(t => `“${t}”`).join(", ")}: troque em Configurações → Corretor de vídeo e refaça a cartela nos ajustes.`);
  const aviso = termosPublicidade(fala, gancho, extra).aviso.filter(x => ![...trava, ...noGancho, ...naCartela].some(y => y.includes(x)));
  if(aviso.length) avisos.push(`Termos que a publicidade contábil evita no que está gravado no vídeo (fala, gancho, cartela): ${aviso.map(t => `“${t}”`).join(", ")}. Confira se é informação, e não propaganda.`);
  const dur = numVideo(v.duracao_final) ?? numVideo(objVideo(r.saida).duracao_s), max = limiteDuracaoVideo();
  if(dur !== null && dur > max) avisos.push(`O vídeo tem ${segVideo(dur)} s, acima da meta de ${max} s (Configurações → Corretor de vídeo): confirme que é isso mesmo.${dur > 90 ? " Acima de 90 s o Facebook não aceita reel pela API: publique só no Instagram." : ""}`);
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
  try{ return await funcaoVideo("envio_concluido", {id}); }
  catch(e){
    await depoisDoVideo(pid).catch(() => {});
    throw new ErroApi(`${String(e.message || "").replace(/[\s.]*$/, "")}. Depois, clique em “Continuar o envio” (os arquivos continuam escolhidos nesta tela).`, e.status);
  }
}

/* ====================================================================
   v0.33.0: a aba Vídeo — o editor do vídeo corrigido
   A aba lista os reels com vídeo (o vivo de cada peça) e abre o EDITOR: a prévia, a linha do tempo com as palavras da legenda, os
   cortes (o começo, o fim e trechos do meio), o texto da legenda palavra por palavra, o estilo (tamanho, posição e cor, só a paleta da
   Artecon: radar_video_paleta), o texto do gancho, o texto extra da cartela e a capa. Só o administrador muda; o editor só vê (o
   leitor não vê a aba: o vídeo tem o rosto e a voz da equipe). As mudanças ficam SÓ na memória desta tela (E.video.aba.rascunhos,
   por vídeo: nada no localStorage, nem a fala) até "Montar de novo com estas mudanças" (radar_video_editar): o robô monta outra
   rodada SEM transcrever de novo. A prévia pula os cortes novos no próprio navegador, sobre o vídeo já montado.
   Os cortes, o começo, o fim e a capa vão em QUADROS (1/30 s) da linha original (os clipes em sequência): a tela converte o instante
   do vídeo que o administrador vê pelo "mapa" que o robô gravou no relatório (qDoVideo; tDoQ é o contrário), e a duração depois de
   montar é a mesma conta do banco e do robô (duracaoEstimadaVideo). Quem trava de verdade é o banco: a tela só ajuda e confere antes.
   ==================================================================== */
const CHAVES_EDITOR_VIDEO = ["cortar", "inicio_q", "fim_q", "capa_q", "legenda_tamanho", "legenda_posicao", "legenda_cor", "cartela_extra"];
const ABA_VIDEO_FPS = 30;
const ABA_VIDEO_LIMITES = {min:5, max:900, fala:2, cortes:30, corteMin:3};   // v0.33.0: o teto é o da API do Instagram (15 min); a meta das Configurações é só aviso
const ABA_VIDEO_CAMPOS = CAMPOS_VIDEO + ",palavras_tentativa,rodada";
const ABA_VIDEO_SEM_BANCO = `<div class="aviso erro" id="vaba-sem-banco">A aba Vídeo precisa do banco desta versão: o administrador roda o <b>sql/radar-setup-v0.47.0.sql</b> (Supabase → SQL Editor) e recarrega esta página.</div>`;
const abaVideo = () => (estadoVideo().aba ||= {filtro:"futuro", rascunhos:{}, previaLigada:true, abertas:{cortar:true}});
const ehEditorVideo = v => CHAVES_EDITOR_VIDEO.some(k => Object.prototype.hasOwnProperty.call(objVideo(v?.ajustes), k));
const inteiroVideo = x => Number.isInteger(x) ? x : null;

/* ------------------------------------------------------------- o mapa (a linha original) */
const mapaVideo = v => { const m = objVideo(objVideo(v?.relatorio).mapa);
  return Number.isInteger(m.linha_q) && Array.isArray(m.trechos) && Array.isArray(m.faixas) ? m : null; };
/* o quadro da linha original do instante t do vídeo corrigido (null: depois da fala, na cartela) — cortes.original do robô */
function qDoVideo(mapa, t){
  const q = Math.floor(Number(t) * ABA_VIDEO_FPS + 1e-6); let acum = 0;
  for(const [qa, qb] of mapa.trechos){ if(q < acum + (qb - qa)) return qa + Math.max(0, q - acum); acum += qb - qa; }
  return null;
}
/* o instante no vídeo corrigido do quadro q da linha original e se ele ficou (false: caiu num corte, levado à emenda) — cortes.video_de */
function tDoQ(mapa, q){
  let acum = 0;
  for(const [qa, qb] of mapa.trechos){
    if(q < qa) return [acum / ABA_VIDEO_FPS, false];
    if(q < qb) return [(acum + q - qa) / ABA_VIDEO_FPS, true];
    acum += qb - qa;
  }
  return [acum / ABA_VIDEO_FPS, false];
}
const falaDoVideoS = mapa => mapa.trechos.reduce((s, [a, b]) => s + b - a, 0) / ABA_VIDEO_FPS;
/* o quadro q fica depois de montar com estes ajustes? (radar_video_edicao_duracao no banco, cortes._fica no robô) */
function quadroFicaVideo(mapa, aj, q){
  const manter = new Set((Array.isArray(aj.manter) ? aj.manter : []).filter(x => typeof x === "string"));
  const ini = inteiroVideo(aj.inicio_q), fim = inteiroVideo(aj.fim_q), cortar = Array.isArray(aj.cortar) ? aj.cortar : [];
  return mapa.faixas.some(([a, b]) => q >= a && q < b) && !listaVideo(mapa.automaticos).some(x => q >= x.de && q < x.ate && !manter.has(x.chave))
    && !cortar.some(([a, b]) => q >= a && q < b) && (ini === null || q >= ini) && (fim === null || q < fim);
}
const quadrosQueFicamVideo = (mapa, aj) => { const out = []; for(let q = 0; q < Math.min(mapa.linha_q, 29000); q++) if(quadroFicaVideo(mapa, aj, q)) out.push(q); return out; };
const falaEstimadaQVideo = (mapa, aj) => quadrosQueFicamVideo(mapa, aj).length;
const cartelaSVideo = () => { const n = numVideo(confVideo().cartela_s); return n !== null && n >= 2 && n <= 5 ? n : 3; };
/* o pad do fim (o último quadro parado, como o robô monta): o vídeo precisa de 0,45 s depois da última palavra que fica. O último trecho
   é a última sequência de quadros que ficam, dentro da faixa do clipe; a última palavra é a que termina mais tarde entre as que passam
   por ele (mapa.palavras, [ini, fim] em ms; cortada no meio, termina onde o trecho termina; nenhuma, o começo do trecho) */
function padEstimadoVideo(mapa, ficam){
  if(!ficam.length) return 0;
  const qb = ficam[ficam.length - 1] + 1, f = mapa.faixas.filter(([a, b]) => qb - 1 >= a && qb - 1 < b).map(([a]) => a);
  const f0 = f.length ? Math.min(...f) : qb - 1; let i = ficam.length - 1;
  while(i > 0 && ficam[i - 1] === ficam[i] - 1 && ficam[i - 1] >= f0) i--;
  const qa = ficam[i], fins = listaVideo(mapa.palavras).filter(w => Array.isArray(w) && w.length === 2 && w.every(Number.isFinite) && w[0] * 3 < qb * 100 && w[1] * 3 > qa * 100).map(w => w[1]);
  const u = fins.length ? Math.min(Math.max(...fins) * 3 / 100, qb) : qa;
  return Math.max(0, Math.ceil(u - qb + 13.5 - 1e-6));                                      // 13,5 quadros = 0,45 s
}
/* a duração depois de montar: a fala que fica + o pad do fim + a cartela − 0,4 s da transição, arredondada como o numeric do banco */
function duracaoEstimadaVideo(mapa, aj, cartela_s = cartelaSVideo()){
  const ficam = quadrosQueFicamVideo(mapa, objVideo(aj)), total = ficam.length + padEstimadoVideo(mapa, ficam);
  return Math.floor((total - 12 + 30 * cartela_s) / 3 + 0.5 + 1e-9) / 10;                // (quadros − 0,4 s + cartela) × 10 / 30
}

/* ------------------------------------------------------------- o rascunho (as mudanças ainda não montadas) */
function rascunhoNovoVideo(v){
  const aj = objVideo(v.ajustes);
  return {sha256:v.sha256, cortar:(Array.isArray(aj.cortar) ? aj.cortar : []).map(c => [c[0], c[1]]),
    inicio_q:inteiroVideo(aj.inicio_q), fim_q:inteiroVideo(aj.fim_q), capa_q:inteiroVideo(aj.capa_q),
    tamanho:aj.legenda_tamanho || "M", posicao:aj.legenda_posicao || "baixo", cor:aj.legenda_cor || "marinho", compacta:aj.estilo === "compacta",
    gancho:textoDe(v.gancho), sem_gancho:aj.sem_gancho === true,
    extra:typeof aj.cartela_extra === "string" ? {modo:aj.cartela_extra ? "proprio" : "sem", texto:aj.cartela_extra} : {modo:"config", texto:""},
    refazer:false, legenda:{}, manter:listaMarcas(aj.manter, CHAVE_CORTE), errou:listaMarcas(aj.transcricao_errou, ID_DIVERGENCIA)};
}
function rascunhoVideo(v){
  const a = abaVideo(); let r = a.rascunhos[v.id];
  if(r && r.sha256 !== v.sha256){ a.rascunhoPerdido = r.mexido === true; r = null; }     // montado de novo (ou trocado) enquanto a tela guardava
  return (a.rascunhos[v.id] = r || rascunhoNovoVideo(v));
}
/* o rascunho que vai mudar agora (a marca "mexido": só a mudança de verdade conta como perdida, se o vídeo for montado de novo) */
const rascunhoMexidoVideo = v => { const r = rascunhoVideo(v); r.mexido = true; return r; };
/* os cortes em ordem, juntos e dentro da linha (o banco recusa os que se sobrepõem) */
function juntarCortesVideo(lista, linha){
  const ord = lista.map(([a, b]) => [Math.max(0, Math.min(linha, a)), Math.max(0, Math.min(linha, b))]).filter(([a, b]) => b - a >= ABA_VIDEO_LIMITES.corteMin)
    .sort((x, y) => x[0] - y[0] || x[1] - y[1]), out = [];
  for(const c of ord){ if(out.length && c[0] <= out[out.length - 1][1]) out[out.length - 1][1] = Math.max(out[out.length - 1][1], c[1]); else out.push([c[0], c[1]]); }
  return out;
}
/* os ajustes que vão ao banco: os de antes que o editor não mexe (as edições da legenda já aplicadas) e o que está no rascunho */
function ajustesDoEditor(v, r){
  const antes = objVideo(v.ajustes), aj = {}, blocos = listaVideo(objVideo(objVideo(v.relatorio).legenda).lista);
  if(r.manter.length) aj.manter = [...r.manter];
  if(r.errou.length) aj.transcricao_errou = [...r.errou];
  // v0.40.0: as aceitas ("quis dizer o mesmo") não se editam aqui — vão sempre as do vídeo de agora, para continuarem valendo
  // na montagem nova (o aceitar é na hora, radar_video_aceitar, e pode acontecer com o rascunho já aberto)
  const aceitas = listaMarcas(antes.aceitas, ID_DIVERGENCIA);
  if(aceitas.length) aj.aceitas = aceitas;
  let legenda = edicoesLegenda(antes.legenda);
  for(const [i, novo] of Object.entries(r.legenda)){
    const b = blocos[Number(i)], u = numVideo(b?.u), n = numVideo(b?.palavras);
    if(!b || !Number.isInteger(u) || !Number.isInteger(n) || novo === b.texto) continue;
    legenda = legenda.filter(([k]) => k !== String(u) && !k.startsWith(u + ":"));
    legenda.push([`${u}:${n}`, novo]);
  }
  if(legenda.length) aj.legenda = legenda;
  if(r.compacta) aj.estilo = "compacta";
  if(r.sem_gancho) aj.sem_gancho = true;
  const m = mapaVideo(v), cortar = juntarCortesVideo(r.cortar, m ? m.linha_q : 29000);
  if(cortar.length) aj.cortar = cortar;
  for(const k of ["inicio_q", "fim_q", "capa_q"]) if(r[k] !== null && r[k] !== undefined) aj[k] = r[k];
  if(r.tamanho !== "M") aj.legenda_tamanho = r.tamanho;
  if(r.posicao !== "baixo") aj.legenda_posicao = r.posicao;
  if(r.cor !== "marinho") aj.legenda_cor = r.cor;
  if(r.extra.modo === "proprio") aj.cartela_extra = r.extra.texto.replace(/\s+/g, " ").trim();
  if(r.extra.modo === "sem") aj.cartela_extra = "";
  return aj;
}
/* o texto do gancho que vai à função: null = não mexe; "" = sem o texto do gancho; texto = o novo (muda também a chamada da peça) */
function ganchoDoEditor(v, r){
  const antes = objVideo(v.ajustes).sem_gancho === true, texto = r.gancho.replace(/\s+/g, " ").trim(), atual = textoDe(v.gancho);
  if(r.sem_gancho || !texto) return antes || (!atual && !texto) ? null : "";
  if(texto !== atual || antes) return texto;
  return null;
}
const cartelaDoEditor = (v, r) => r.refazer ? linhasCartela(v.fala_pessoa) : null;
const mudouAbaVideo = (v, r) => !ajustesIguais(ajustesDoEditor(v, r), v.ajustes) || ganchoDoEditor(v, r) !== null || r.refazer;
/* as recusas da legenda (a mesma regra do robô): {bloco: motivo} */
function recusasLegendaVideo(v, r){
  const blocos = listaVideo(objVideo(objVideo(v.relatorio).legenda).lista), out = {};
  for(const [i, novo] of Object.entries(r.legenda)){
    const b = blocos[Number(i)]; if(!b || novo === b.texto) continue;
    const n = numVideo(b.palavras), motivo = Number.isInteger(n) ? recusaLegenda(b.texto, novo, n, Array.isArray(b.perto) ? b.perto : v.fala_roteiro) : "bloco_inexistente";
    if(motivo) out[i] = motivo;
  }
  return out;
}
/* os termos da publicidade que travam no gancho e no texto extra (antes de mandar) */
function termosDoEditor(r){
  const trava = t => [...new Set([...termosPublicidade(t).trava, ...termosPeca(t)])];
  return [["no texto do gancho", r.sem_gancho ? "" : r.gancho], ["no texto extra da cartela", r.extra.modo === "proprio" ? r.extra.texto : ""]]
    .map(([lugar, t]) => [lugar, trava(t)]).filter(([, l]) => l.length);
}
/* o resumo das mudanças, em português */
function resumoMudancasVideo(v, r){
  const antes = objVideo(v.ajustes), m = mapaVideo(v), partes = [], velhos = Array.isArray(antes.cortar) ? antes.cortar : [];
  const chave = c => c[0] + ":" + c[1], novos = r.cortar.filter(c => !velhos.some(x => chave(x) === chave(c))), desfeitos = velhos.filter(c => !r.cortar.some(x => chave(x) === chave(c)));
  if(novos.length) partes.push(`${novos.length} corte${novos.length > 1 ? "s" : ""} novo${novos.length > 1 ? "s" : ""} (−${segVideo(novos.reduce((s, [a, b]) => s + b - a, 0) / ABA_VIDEO_FPS)} s)`);
  if(desfeitos.length) partes.push(`${desfeitos.length} corte${desfeitos.length > 1 ? "s" : ""} desfeito${desfeitos.length > 1 ? "s" : ""}`);
  if(r.inicio_q !== inteiroVideo(antes.inicio_q)) partes.push(r.inicio_q === null ? "sem o começo marcado" : `começo aos ${segVideo(m ? tDoQ(m, r.inicio_q)[0] : 0)} s`);
  if(r.fim_q !== inteiroVideo(antes.fim_q)) partes.push(r.fim_q === null ? "sem o fim marcado" : `fim aos ${segVideo(m ? tDoQ(m, r.fim_q)[0] : 0)} s`);
  const nLeg = Object.entries(r.legenda).filter(([i, t]) => t !== listaVideo(objVideo(objVideo(v.relatorio).legenda).lista)[Number(i)]?.texto).length;
  if(nLeg) partes.push(`legenda: ${nLeg} bloco${nLeg > 1 ? "s" : ""} editado${nLeg > 1 ? "s" : ""}`);
  const pal = objVideo(abaVideo().paleta), nome = (lista, k) => listaVideo(pal[lista]).find(x => x.chave === k)?.nome?.replace(/ \(padrão\)$/, "").toLowerCase() || k;
  if(r.tamanho !== (antes.legenda_tamanho || "M") || r.posicao !== (antes.legenda_posicao || "baixo") || r.cor !== (antes.legenda_cor || "marinho"))
    partes.push(`legenda ${nome("tamanhos", r.tamanho)}, ${nome("posicoes", r.posicao)}, ${nome("cores", r.cor)}`);
  if(r.compacta !== (antes.estilo === "compacta")) partes.push(r.compacta ? "legenda compacta" : "legenda normal");
  const g = ganchoDoEditor(v, r);
  if(g !== null) partes.push(g === "" ? "sem o texto do gancho" : "texto do gancho novo");
  const extraAntes = typeof antes.cartela_extra === "string" ? antes.cartela_extra : null, extraAgora = r.extra.modo === "config" ? null : r.extra.modo === "sem" ? "" : r.extra.texto.trim();
  if(extraAgora !== extraAntes) partes.push(extraAgora === null ? "texto extra das Configurações" : extraAgora === "" ? "sem texto extra na cartela" : "texto extra próprio na cartela");
  if(r.refazer) partes.push("cartela refeita");
  if(r.capa_q !== inteiroVideo(antes.capa_q)) partes.push(r.capa_q === null ? "sem a capa escolhida" : `capa aos ${segVideo(m ? tDoQ(m, r.capa_q)[0] : 0)} s`);
  if(JSON.stringify([...r.manter].sort()) !== JSON.stringify(listaMarcas(antes.manter, CHAVE_CORTE).sort())) partes.push("cortes do robô mantidos ou desfeitos");
  if(JSON.stringify([...r.errou].sort()) !== JSON.stringify(listaMarcas(antes.transcricao_errou, ID_DIVERGENCIA).sort())) partes.push("“a transcrição errou” marcada ou desmarcada");
  return partes;
}
/* os trechos que a prévia pula (no tempo do vídeo já montado): os cortes novos, o começo e o fim marcados agora */
function pulosDaPreviaVideo(v, r){
  const m = mapaVideo(v); if(!m) return [];
  const antes = objVideo(v.ajustes), velhos = (Array.isArray(antes.cortar) ? antes.cortar : []).map(c => c.join(":")), pulos = [];
  const fala = falaDoVideoS(m), cartela = Math.max(0, fala + numVideo(m.pad_q || 0) / ABA_VIDEO_FPS - 0.4);
  for(const c of r.cortar){ if(velhos.includes(c.join(":"))) continue; const a = tDoQ(m, c[0])[0], b = tDoQ(m, c[1])[0]; if(b - a > 0.01) pulos.push([a, b]); }
  if(r.inicio_q !== null && (inteiroVideo(antes.inicio_q) === null || r.inicio_q > antes.inicio_q)){ const b = tDoQ(m, r.inicio_q)[0]; if(b > 0.01) pulos.push([0, b]); }
  if(r.fim_q !== null && (inteiroVideo(antes.fim_q) === null || r.fim_q < antes.fim_q)){ const a = tDoQ(m, r.fim_q)[0]; if(cartela - a > 0.01) pulos.push([a, cartela]); }
  return pulos.sort((x, y) => x[0] - y[0]);
}

/* ------------------------------------------------------------- a lista */
async function telaAbaVideo(){
  const a = abaVideo();
  if(VIDEO_VERSAO !== VERSAO) return `<h1>Vídeo</h1><div class="aviso erro" id="vaba-versao">Esta tela (v${h(VERSAO)}) e o arquivo do corretor de vídeo (radar-video.js, v${h(VIDEO_VERSAO)}) são de versões diferentes: um deles ficou guardado no navegador. Aperte Ctrl+F5 (no celular, recarregue a página).</div>`;
  try{
    if(!a.paleta) a.paleta = objVideo(await rpc("radar_video_paleta", {}));
    await lerConfPauta();
    return a.id ? await editorAbaVideo(a.id) : a.nova ? await formAvulso() : await listaAbaVideo();
  }catch(e){ if(semTabelaDoVideo(e) || /radar_video_paleta/.test(e.message || "")) return `<h1>Vídeo</h1>${ABA_VIDEO_SEM_BANCO}`; throw e; }
}
async function listaAbaVideo(){
  const a = abaVideo(), hoje = hojeBrasilia(), desde = a.filtro === "60" ? somarDias(hoje, -60) : hoje;
  const vivos = await ler("radar_videos", {select:"id,peca_id,titulo,versao,situacao,duracao_final,sha256,ajustes,erro_codigo,atualizado_em,rodada", situacao:VIVAS_VIDEO,
    order:"atualizado_em.desc", limit:"200"});
  const avulsos = vivos.filter(v => v.peca_id === null);
  const ids = [...new Set(vivos.filter(v => v.peca_id !== null).map(v => v.peca_id))];
  const pecas = ids.length ? await ler("radar_pauta_pecas", {select:"id,data,hora,situacao,assunto,formato", id:`in.(${ids.join(",")})`, data:"gte." + desde}) : [];
  const linhas = pecas.map(p => { const dela = vivos.filter(v => v.peca_id === p.id);
    return {p, v:dela.find(v => v.situacao !== "aguardando_envio") || dela[0], envio:dela.some(v => v.situacao === "aguardando_envio") && dela.some(v => v.situacao !== "aguardando_envio")}; })
    .filter(x => x.v).sort((x, y) => (x.p.data + x.p.hora).localeCompare(y.p.data + y.p.hora));
  const adm = ehAdmin();
  return `<h1>Vídeo dos reels</h1><p class="sub">O vídeo corrigido de cada reel da Pauta. O administrador edita aqui; a aprovação continua na peça e nada é publicado sem ela.</p>
    <div class="acoes vaba-filtros"><button class="btn peq${a.filtro === "60" ? " sec" : ""}" type="button" data-acao="vaba-filtro" data-filtro="futuro">De hoje em diante</button>
      <button class="btn peq${a.filtro === "60" ? "" : " sec"}" type="button" data-acao="vaba-filtro" data-filtro="60">Últimos 60 dias</button></div>
    ${!linhas.length ? `<p class="sub" id="vaba-vazia">Nenhum reel com vídeo neste período.</p>` : `<div class="vaba-lista-caixa"><table class="vaba-lista" id="vaba-lista">
      <thead><tr><th>Dia</th><th>Reel</th><th>Vídeo</th><th>Peça</th><th></th></tr></thead><tbody>
      ${linhas.map(({p, v, envio}) => `<tr data-video="${h(v.id)}"><td data-rotulo="Dia">${h(dataCurta(p.data))} ${h(String(p.hora || "").slice(0, 5))}</td>
        <td data-rotulo="Reel" class="vaba-assunto">${h(cortarPauta(p.assunto || "Reel sem assunto", 60))}</td>
        <td data-rotulo="Vídeo">${seloVideo(v)}${numVideo(v.duracao_final) !== null ? ` <span class="sub">${segVideo(v.duracao_final)} s</span>` : ""}${ehEditorVideo(v) ? " " + selo("editado", "neutro") : ""}${envio ? " " + selo("envio novo a caminho", "alerta") : ""}</td>
        <td data-rotulo="Peça">${selo(deMapaVideo(SITUACOES_PAUTA, p.situacao) || p.situacao, p.situacao === "aprovada" ? "ok" : "neutro")}</td>
        <td><button class="btn peq${adm ? "" : " sec"}" type="button" data-acao="vaba-abrir" data-id="${h(v.id)}">${adm ? "Editar" : "Ver"}</button></td></tr>`).join("")}
      </tbody></table></div>`}
    <h2 class="vaba-avulsos-titulo">Correções avulsas</h2>
    <p class="sub">O vídeo avulso é analisado e corrigido SEM peça na Pauta: ele não passa pela aprovação e nunca é publicado pelo Radar — o administrador baixa o vídeo pronto e posta à mão. As travas são as mesmas (termos das pessoas, cartela, declarações e o limite de minutos do mês).</p>
    <div class="acoes"><button class="btn verde" type="button" data-acao="vaba-avulso-novo">Corrigir um vídeo avulso</button></div>
    ${!avulsos.length ? `<p class="sub" id="vaba-avulsos-vazia">Nenhuma correção avulsa em andamento.</p>` : `<div class="vaba-lista-caixa"><table class="vaba-lista" id="vaba-avulsos">
      <thead><tr><th>Título</th><th>Vídeo</th><th></th></tr></thead><tbody>
      ${avulsos.map(v => `<tr data-video="${h(v.id)}"><td data-rotulo="Título" class="vaba-assunto">${h(cortarPauta(v.titulo || "Vídeo avulso", 60))}</td>
        <td data-rotulo="Vídeo">${seloVideo(v)}${numVideo(v.duracao_final) !== null ? ` <span class="sub">${segVideo(v.duracao_final)} s</span>` : ""}${ehEditorVideo(v) ? " " + selo("editado", "neutro") : ""}</td>
        <td><button class="btn peq${adm ? "" : " sec"}" type="button" data-acao="vaba-abrir" data-id="${h(v.id)}">${adm ? "Editar" : "Ver"}</button></td></tr>`).join("")}
      </tbody></table></div>`}`;
}

/* ------------------------------------------------------------- a correção avulsa (v0.36.0) */
/* O formulário do vídeo avulso: título, a fala para conferência colada direto (ela É o roteiro do avulso), quem aparece e quem fala
   (Pauta → Pessoas e termos), a cartela, as quatro declarações e os clipes. O banco confere tudo ANTES de qualquer arquivo sair
   (radar_video_criar_avulso, pela função radar-video); dali em diante o caminho é o mesmo do reel. Os clipes escolhidos ficam em
   clipesDe(0): o avulso não tem número de peça (nenhuma peça tem id 0). */
async function formAvulso(){
  const ev = estadoVideo(), a = abaVideo();
  const pessoas = await ler("radar_pessoas", {select:"id,nome_na_peca,area,categoria,crc,ativo,termo_corretor_em,quer_ver_peca,menor,socio", order:"nome_na_peca,id"});
  E.pauta.pessoas = Object.fromEntries(pessoas.map(x => [x.id, x]));
  ev.peca = 0; ev.envio = null;
  ev.cota = await rpc("radar_video_cota", {}).catch(() => null);
  const f = (a.avulso ||= {titulo:"", fala:"", quem:"", marcadas:[]});
  // v0.28.0: sócio(a) da Artecon (maior de idade) não precisa do termo novo (o banco também dispensa: radar_video_pessoa_falta)
  const falta = pessoas.map(x => [x, x.menor ? "menor de idade: o corretor não aceita nesta versão" : !x.ativo ? "inativa" : !x.socio && !x.termo_corretor_em ? "sem o termo novo, que cita o corretor de vídeo" : ""]);
  const aptas = falta.filter(([, m]) => !m).map(([x]) => x);
  const pr = ev.progresso;
  const miolo = pr && pr.peca === 0 ? blocoProgresso(pr) : `<div class="video-envio" id="video-envio">
    <div class="grade"><div><label for="vaba-avulso-titulo">Título (como o vídeo aparece na lista da aba; nada de nome de cliente)</label>
      <input id="vaba-avulso-titulo" maxlength="120" value="${h(f.titulo)}"></div></div>
    <label for="vaba-avulso-fala">Fala para conferência: o que foi falado na gravação, palavra por palavra (ela é o “roteiro” do avulso; ao menos 10 palavras)</label>
    <textarea id="vaba-avulso-fala" rows="6" maxlength="6000">${h(f.fala)}</textarea>
    <p class="sub">${h(RECADO_GRAVAR)}</p>
    ${!aptas.length ? `<div class="aviso alerta" id="vaba-avulso-sem-pessoa">Nenhuma pessoa pode aparecer no vídeo hoje: confira em Pauta → Pessoas e termos (“Ativa”, a idade e o termo do corretor).</div>` : ""}
    <fieldset class="checks" id="vaba-avulso-pessoas"><legend>Quem aparece no vídeo</legend>${falta.map(([x, m]) =>
      `<label><input type="checkbox" class="vaba-avulso-pessoa" value="${x.id}"${f.marcadas.includes(x.id) ? " checked" : ""}${m ? " disabled" : ""}> ${h(x.nome_na_peca)}${m ? ` <span class="sub">(${h(m)})</span>` : ""}</label>`).join("")}</fieldset>
    <div class="grade"><div><label for="vaba-avulso-quem">Quem fala</label><select id="vaba-avulso-quem"><option value="">Escolha</option>${aptas.map(x =>
      `<option value="${x.id}"${String(x.id) === String(f.quem) ? " selected" : ""}>${h(x.nome_na_peca)}</option>`).join("")}</select></div></div>
    <label>Cartela final (a identificação legal${aptas.some(x => ROTULO_CATEGORIA[x.categoria]) ? " e a linha de quem fala, se tem registro no CRC" : ""})</label><div id="vaba-avulso-cartela">${htmlCartela(numVideo(f.quem))}</div>
    ${campoClipes({id:0})}<div id="video-clipes">${listaClipes(0)}</div>${linhaCotaVideo()}
    <fieldset class="checks video-declaracoes"><legend>Declarações (as quatro são obrigatórias)</legend>${DECLARACOES_VIDEO.map(([k, t]) =>
      `<label><input type="checkbox" class="video-declaracao" value="${k}" data-texto="${h(t)}"> ${h(t)}</label>`).join("")}</fieldset>
    <p class="sub"><b>${h(AVISO_NOVO_ENVIO)}</b></p>
    <div class="acoes"><button class="btn verde" type="button" data-acao="vaba-avulso-enviar">Enviar para o corretor</button>
      <button class="btn sec" type="button" data-acao="vaba-avulso-cancelar">Cancelar</button></div></div>`;
  return `<div id="vaba-avulso-form"><button class="voltar" data-acao="vaba-avulso-cancelar">← Voltar à lista</button>
    <h1>Corrigir um vídeo avulso</h1>
    <p class="sub">Sem peça na Pauta: o corretor transcreve, compara com a fala para conferência, corta e legenda; o vídeo aparece na lista da aba com o relatório e o editor. O avulso não passa pela aprovação e nunca é publicado pelo Radar: só o administrador baixa o vídeo pronto (fica registrado).</p>
    ${miolo}</div>`;
}
/* O envio do avulso que não terminou ("Continuar o envio", dentro do editor da aba) */
function htmlAvulsoContinuar(v){
  const lista = clipesDe(0), pr = estadoVideo().progresso;
  if(pr && pr.peca === 0) return blocoProgresso(pr);
  if(v.enviado_por !== E.sessao?.user?.id && !ehAdmin()) return `<div class="video-envio" id="video-envio"><h3>Envio não terminado</h3>
    <div class="aviso alerta" id="vaba-avulso-envio-outro">O envio deste avulso foi começado por outra pessoa e não terminou: só ela (ou o administrador) continua. Você pode descartar este envio e enviar de novo.</div>
    <div class="acoes"><button class="btn perigo" type="button" data-acao="vaba-avulso-descartar">Descartar este envio</button></div></div>`;
  return `<div class="video-envio" id="video-envio"><h3>Continuar o envio</h3>
    <div class="aviso alerta">O envio deste avulso não terminou (${listaVideo(v.partes).length} clipe(s)). ${lista.length === listaVideo(v.partes).length ? "Os arquivos ainda estão nesta tela:" : "Escolha de novo os MESMOS arquivos, na mesma ordem:"} o envio continua de onde parou.</div>
    ${campoClipes({id:0})}<div id="video-clipes">${listaClipes(0, listaVideo(v.partes))}</div>
    <p class="sub">${h(AVISO_NAO_FECHE)}</p>
    <div class="acoes"><button class="btn verde" type="button" data-acao="vaba-avulso-continuar">Continuar o envio</button>
      <button class="btn perigo" type="button" data-acao="vaba-avulso-descartar">Descartar este envio</button></div></div>`;
}
/* Baixar (só o administrador, só o vídeo pronto), o registro do "apaguei" e o descartar do avulso */
function htmlRodapeAvulso(v){
  if(v.peca_id !== null || v.situacao === "aguardando_envio") return "";
  const adm = ehAdmin(), partes = [`<h2 class="vaba-avulsos-titulo">Baixar e postar à mão</h2>`];
  const pronto = v.situacao === "pronto" && v.sha256 && !(Array.isArray(v.arquivos_apagados) ? v.arquivos_apagados : []).includes("corrigido");
  if(!pronto) partes.push(`<p class="sub">O vídeo avulso se baixa quando está “Vídeo corrigido pronto” (sem divergência pendente e sem erro).</p>`);
  else if(!adm) partes.push(`<p class="sub">Só o administrador baixa o vídeo avulso (fica registrado quem baixou).</p>`);
  else partes.push(`<div id="vaba-avulso-baixar"><div class="acoes"><button class="btn" type="button" data-acao="vaba-avulso-baixar">Baixar o vídeo corrigido (link de 5 minutos)</button></div>
    <p class="sub">Fica registrado quem baixou. O avulso não é publicado pelo Radar: poste onde quiser e depois apague do aparelho.</p></div>`);
  partes.push(v.apagado_aparelho_em ? `<p class="sub" id="vaba-avulso-apagou">Registrado: os clipes foram apagados do celular e da nuvem pessoal em ${h(dataHora(v.apagado_aparelho_em))}.</p>`
    : `<div class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-avulso-apaguei">Apaguei os clipes do celular e da nuvem pessoal</button>
      <span class="sub">O termo pede apagar no mesmo dia do envio; guarde até o relatório, se precisar regravar um bloco.</span></div>`);
  partes.push(`<div class="acoes"><button class="btn peq perigo" type="button" data-acao="vaba-avulso-descartar">Descartar esta gravação</button>
    <span class="sub">Os arquivos saem do armazenamento na limpeza seguinte.</span></div>`);
  return `<div class="vaba-avulso-rodape" id="vaba-avulso-rodape">${partes.join("")}</div>`;
}

/* ------------------------------------------------------------- o editor */
async function editorAbaVideo(id){
  const a = abaVideo();
  const [v] = await ler("radar_videos", {select:ABA_VIDEO_CAMPOS, id:"eq." + id});
  if(!v){ a.id = null; return `<button class="voltar" data-acao="vaba-voltar">← Voltar à lista</button><div class="aviso erro">Vídeo não encontrado (foi substituído ou descartado).</div>`; }
  const avulso = v.peca_id === null;           // v0.36.0: a correção avulsa não tem peça
  const [p] = avulso ? [null] : await ler("radar_pauta_pecas", {select:"id,data,hora,situacao,assunto,chamada,roteiro,pessoas,formato,aprovado_modo,video_id", id:"eq." + v.peca_id});
  const pessoas = await ler("radar_pessoas", {select:"id,nome_na_peca,area,categoria,crc,ativo,termo_corretor_em,quer_ver_peca,menor,socio", order:"nome_na_peca,id"});
  E.pauta.pessoas = Object.fromEntries(pessoas.map(x => [x.id, x]));
  const hash = avulso ? null : await hashTextoVideo(p?.roteiro || "");
  a.v = v; a.peca = p || null;
  a.roteiroMudou = !!p && (hash ? hash !== v.roteiro_hash : extrairFala(p.roteiro).fala !== v.fala_roteiro);
  if(a.previa && (a.previa.id !== v.id || a.previa.sha256 !== v.sha256)) a.previa = null;
  if(avulso && v.situacao === "aguardando_envio"){ const ev = estadoVideo(); ev.peca = 0; ev.envio = v; }
  if(v.situacao !== "aguardando_envio") rascunhoVideo(v);
  return htmlEditorAbaVideo();
}
/* o vídeo pode ser editado agora? (o administrador, a peça livre — ou o avulso, que não tem peça —, o vídeo pronto ou para regravar,
   montado, com a transcrição guardada) */
function editavelVideo(v, p){
  const livre = v.peca_id === null || (!!p && ["planejada", "em_producao", "pronta"].includes(p.situacao));
  return ehAdmin() && livre && ["pronto", "regravar"].includes(v.situacao)
    && !relatorioParcial(v) && !!v.sha256 && !(Array.isArray(v.arquivos_apagados) ? v.arquivos_apagados : []).includes("corrigido") && v.palavras_tentativa !== null;
}
function htmlEditorAbaVideo(){
  const a = abaVideo(), v = a.v, p = a.peca, adm = ehAdmin();
  const avulso = v.peca_id === null;                    // v0.36.0: a correção avulsa não tem peça
  const livre = avulso || (p && ["planejada", "em_producao", "pronta"].includes(p.situacao));
  const topo = `<div class="vaba-topo"><button class="voltar" data-acao="vaba-voltar">← Voltar à lista</button>
    <h1>${avulso ? "Vídeo avulso" : `Reel de ${p ? h(dataCurta(p.data)) + " · " + h(String(p.hora || "").slice(0, 5)) : "—"}`}</h1>
    <p class="vaba-titulo"><span class="vaba-assunto">${h(cortarPauta(avulso ? v.titulo || "" : p?.assunto || "", 90))}</span> ${seloVideo(v)}${numVideo(v.duracao_final) !== null ? ` <span class="sub">${segVideo(v.duracao_final)} s</span>` : ""}${numVideo(v.rodada) > 1 ? ` <span class="sub">· montado ${numVideo(v.rodada)} vezes</span>` : ""}
      ${p ? `<button class="btn peq sec" type="button" data-acao="vaba-peca" data-id="${h(p.id)}">Abrir a peça na Pauta</button>` : ""}</p></div>`;
  const avisos = [];
  if(a.rascunhoPerdido){ avisos.push(`<div class="aviso alerta" id="vaba-perdido">O vídeo foi montado de novo enquanto esta tela guardava mudanças: as mudanças ainda não montadas foram descartadas.</div>`); a.rascunhoPerdido = false; }
  if(p?.situacao === "aprovada") avisos.push(`<div class="aviso info" id="vaba-aprovada">Peça aprovada: o vídeo não muda. Para editar, Desfazer aprovação na peça.</div>`);
  if(p?.situacao === "cancelada") avisos.push(`<div class="aviso alerta" id="vaba-cancelada">Peça cancelada: o vídeo não muda. Para editar, Reabrir a peça.</div>`);
  if(v.situacao === "aguardando_envio" && !avulso) avisos.push(`<div class="aviso alerta" id="vaba-envio">O envio da gravação ${h(v.versao)} não terminou: termine (ou descarte) na peça.</div>`);
  if(["na_fila", "processando"].includes(v.situacao))
    avisos.push(`<div class="aviso info" id="vaba-trabalhando">O corretor está montando${v.modo === "montagem" ? " (sem transcrever de novo)" : ""}. Esta tela atualiza sozinha; pode sair e voltar depois.</div>`);
  if(v.situacao === "erro"){
    const r = objVideo(v.relatorio);
    avisos.push(`<div class="aviso erro" id="vaba-erro"><b>O corretor parou:</b> ${h(erroDoVideo(v.erro_codigo))}.
      ${livre ? `<div class="acoes"><button class="btn peq" type="button" data-acao="vaba-de-novo" data-id="${h(v.id)}">Tentar de novo</button>
        ${adm && v.erro_codigo === "edicao_curta" && r.parcial === false && r.mapa ? `<button class="btn peq sec" type="button" data-acao="vaba-desfazer-edicao" data-id="${h(v.id)}">Desfazer os cortes do editor e montar de novo</button>` : ""}</div>` : ""}</div>`);
  }
  if(a.roteiroMudou && ["pronto", "regravar", "erro"].includes(v.situacao))
    avisos.push(`<div class="aviso alerta" id="vaba-roteiro-mudou">O roteiro da peça mudou depois desta gravação: confira na peça (“Conferir com o roteiro novo”) antes de editar.</div>`);
  if(v.palavras_tentativa === null && ["pronto", "regravar"].includes(v.situacao))
    avisos.push(`<div class="aviso alerta" id="vaba-sem-transcricao">A transcrição desta gravação não ficou guardada: o editor não monta de novo (transcreveria outra vez e gastaria minutos do mês). Para mudar, envie a gravação de novo.</div>`);
  if(!adm) avisos.push(`<p class="sub" id="vaba-so-ver">Só o administrador muda o vídeo; aqui você vê o vídeo e o que foi feito.</p>`);
  // v0.36.0: a fala do avulso fica à mão (no reel ela está no roteiro da peça); para mudar a fala, envia-se um avulso novo
  if(avulso && v.situacao !== "aguardando_envio" && textoDe(v.fala_roteiro)){
    const n = v.fala_roteiro.split(" ").length;
    avisos.push(`<details class="video-fala" id="vaba-avulso-fala-guardada"><summary>Fala para conferência (${n} palavra${n === 1 ? "" : "s"}): o que o corretor compara com a gravação</summary>
      <p class="video-fala-texto">${h(v.fala_roteiro)}</p><p class="sub">Para mudar a fala, envie a gravação de novo (um avulso novo): o avulso não tem “Conferir com o roteiro novo”.</p></details>`);
  }
  const tem = ["pronto", "regravar"].includes(v.situacao) && v.sha256 && !(Array.isArray(v.arquivos_apagados) ? v.arquivos_apagados : []).includes("corrigido");
  return `<div id="vaba-editor" class="vaba-pagina" data-video="${h(v.id)}">${topo}<div id="vaba-avisos">${avisos.join("")}</div>
    ${avulso && v.situacao === "aguardando_envio" ? htmlAvulsoContinuar(v) : ""}
    ${tem ? `<div class="vaba-editor"><div class="vaba-player" id="vaba-player-col">${htmlPlayerAbaVideo()}</div>
      <div class="vaba-secoes" id="vaba-secoes">${htmlSecoesAbaVideo()}</div></div>
      <div class="vaba-rodape" id="vaba-rodape">${htmlRodapeAbaVideo()}</div>`
      : avulso && v.situacao === "aguardando_envio" ? "" : `<p class="sub">${v.situacao === "aguardando_envio" ? "" : "O vídeo corrigido aparece aqui quando o corretor terminar."}</p>`}
    ${htmlRodapeAvulso(v)}</div>`;
}
function htmlPlayerAbaVideo(){
  const a = abaVideo(), v = a.v, pv = a.previa, r = objVideo(v.relatorio), qms = Array.isArray(r.quadros_ms) ? r.quadros_ms : [], capa = objVideo(r.capa);
  if(!pv || pv.id !== v.id) return `<div class="acoes"><button class="btn" type="button" data-acao="vaba-previa" data-id="${h(v.id)}">Ver o vídeo (link de 10 minutos)</button></div>
    <p class="sub">Só para quem está logado; quem viu fica registrado.</p>`;
  return `<video id="vaba-player" controls playsinline preload="auto" src="${h(pv.video)}"></video>
    <p class="sub" id="vaba-tempo">0 s</p>
    <div class="acoes vaba-passos"><button class="btn peq sec" type="button" data-acao="vaba-passo" data-passo="-1">−1 s</button>
      <button class="btn peq sec" type="button" data-acao="vaba-passo" data-passo="-0.1">−0,1 s</button>
      <button class="btn peq" type="button" data-acao="vaba-passo" data-passo="0" aria-label="Tocar ou pausar">▶ / ❚❚</button>
      <button class="btn peq sec" type="button" data-acao="vaba-passo" data-passo="0.1">+0,1 s</button>
      <button class="btn peq sec" type="button" data-acao="vaba-passo" data-passo="1">+1 s</button></div>
    <label class="video-check"><input type="checkbox" id="vaba-previa-ligada"${a.previaLigada ? " checked" : ""}> Prévia com as mudanças (pula os cortes)</label>
    <details class="vaba-quadros"><summary>Capa e quadros</summary>
      ${pv.capa ? `<figure><img src="${h(pv.capa)}" alt="Capa do reel"><figcaption class="sub">Capa${numVideo(capa.em_ms) !== null ? `, aos ${segVideo(capa.em_ms / 1000)} s` : ""}</figcaption></figure>` : `<p class="sub">Sem capa escolhida.</p>`}
      <div class="video-quadros">${pv.quadros.map((q, i) => `<figure><img src="${h(q)}" alt="Quadro ${i + 1} do vídeo corrigido">
        <figcaption class="sub">Quadro ${i + 1}${numVideo(qms[i]) !== null ? `, aos ${segVideo(qms[i] / 1000)} s` : ""}</figcaption></figure>`).join("")}</div></details>
    <p class="sub">Aberto às ${h(new Date(pv.em).toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"}))}; o link vale 10 minutos (vencido, a tela pede outro sozinha). A prévia pula os cortes novos; o que volta ao vídeo (um corte desfeito, um trecho mantido) só aparece depois de montar.</p>`;
}
const secaoAbaVideo = (id, titulo, corpo) => `<details class="painel vaba-secao" id="vaba-sec-${id}" data-secao="${id}"${abaVideo().abertas[id] ? " open" : ""}><summary><h2>${titulo}</h2></summary>${corpo}</details>`;
function htmlSecoesAbaVideo(){
  const a = abaVideo(), v = a.v, ed = editavelVideo(v, a.peca), r = rascunhoVideo(v);
  return [secaoAbaVideo("cortar", "1. Cortar: começo, fim e trechos", htmlCortesAbaVideo(v, r, ed)),
    secaoAbaVideo("legenda", "2. Texto da legenda (palavra por palavra)", htmlLegendaAbaVideo(v, r, ed)),
    secaoAbaVideo("estilo", "3. Estilo da legenda", htmlEstiloAbaVideo(v, r, ed)),
    secaoAbaVideo("gancho", "4. Gancho (0 a 3 s)", htmlGanchoAbaVideo(v, r, ed)),
    secaoAbaVideo("cartela", "5. Cartela final", htmlCartelaAbaVideo(v, r, ed)),
    secaoAbaVideo("capa", "6. Capa do reel", htmlCapaAbaVideo(v, r, ed))].join("");
}
/* 1. Cortar: a linha do tempo, as palavras, a seleção, os cortes novos, os já no vídeo, os do robô e as divergências */
function htmlCortesAbaVideo(v, r, ed){
  const a = abaVideo(), m = mapaVideo(v), rel = objVideo(v.relatorio), dis = ed ? "" : " disabled";
  if(!m) return `<div class="aviso alerta" id="vaba-sem-mapa">Este vídeo foi montado pelo robô de antes desta versão: os cortes e a capa precisam de uma montagem nova (não transcreve de novo).</div>
    ${ed ? `<div class="acoes"><button class="btn" type="button" data-acao="vaba-liberar">Montar de novo para liberar os cortes e a capa</button></div>` : ""}`;
  const fala = falaDoVideoS(m), total = fala + numVideo(m.pad_q || 0) / ABA_VIDEO_FPS + cartelaSVideo() - 0.4, pct = t => Math.max(0, Math.min(100, 100 * t / total));
  const pulos = pulosDaPreviaVideo(v, r), unidades = listaVideo(rel.unidades);
  const linha = `<div class="vaba-linha" id="vaba-linha" role="img" aria-label="Linha do tempo do vídeo">
    ${pulos.map(([x, y]) => `<span class="vaba-faixa novo" style="left:${pct(x)}%;width:${pct(y) - pct(x)}%"></span>`).join("")}
    <span class="vaba-faixa cartela" style="left:${pct(Math.max(0, fala + numVideo(m.pad_q || 0) / ABA_VIDEO_FPS - 0.4))}%;right:0"></span>
    <span class="vaba-cursor" id="vaba-cursor" style="left:0"></span></div>
    <p class="sub vaba-legenda-linha"><span class="vaba-marca novo"></span> corte novo · <span class="vaba-marca cartela"></span> cartela (fica sempre)</p>`;
  const cortada = u => pulos.some(([x, y]) => u.a >= x - 0.01 && u.b <= y + 0.01);
  const sel = a.selecao;
  const palavras = unidades.length ? `<div class="vaba-palavras" id="vaba-palavras">${unidades.map((u, i) => `<button type="button" class="vaba-p${cortada(u) ? " cortada" : ""}${sel && i >= sel[0] && i <= sel[1] ? " sel" : ""}" data-acao="vaba-palavra" data-i="${i}" data-a="${numVideo(u.a) ?? 0}">${h(u.t)}</button>`).join("")}</div>`
    : `<p class="sub">As palavras não vieram no relatório (ele ficou grande e foi resumido): marque os cortes pelo player.</p>`;
  const nomeSel = sel ? `“${h(unidades[sel[0]]?.t)}”${sel[1] !== sel[0] ? ` a “${h(unidades[sel[1]]?.t)}”` : ""}` : "";
  const botoes = !ed ? "" : `<div class="acoes vaba-sel">${sel ? `<button class="btn peq" type="button" data-acao="vaba-cortar">Cortar ${nomeSel}</button>
      <button class="btn peq sec" type="button" data-acao="vaba-comecar-palavra">Começar nesta palavra</button>
      <button class="btn peq sec" type="button" data-acao="vaba-terminar-palavra">Terminar depois dela</button>
      <button class="btn peq sec" type="button" data-acao="vaba-limpar-selecao">Limpar a seleção</button>` : `<span class="sub">Selecione uma palavra (ou duas, para um trecho).</span>`}</div>
    <div class="acoes vaba-pelo-player"><span class="sub">Pelo player:</span>
      <button class="btn peq sec" type="button" data-acao="vaba-marcar-de"${a.previa ? "" : " disabled"}>Marcar começo do corte</button>
      <button class="btn peq sec" type="button" data-acao="vaba-marcar-ate"${a.previa && a.marca !== null && a.marca !== undefined ? "" : " disabled"}>Marcar fim do corte</button>
      <button class="btn peq sec" type="button" data-acao="vaba-comecar-aqui"${a.previa ? "" : " disabled"}>Começar aqui</button>
      <button class="btn peq sec" type="button" data-acao="vaba-terminar-aqui"${a.previa ? "" : " disabled"}>Terminar aqui</button></div>
    ${a.marca !== null && a.marca !== undefined ? `<p class="sub" id="vaba-marca">Começo do corte marcado aos ${segVideo(tDoQ(m, a.marca)[0])} s: leve o player ao fim e clique em “Marcar fim do corte”.</p>` : ""}`;
  // os cortes novos (ainda não montados) e os do editor que já estão no vídeo (com o desfazer)
  const antes = objVideo(v.ajustes), velhos = Array.isArray(antes.cortar) ? antes.cortar : [], chave = c => c[0] + ":" + c[1];
  const cortesRel = listaVideo(rel.cortes).filter(c => c.tipo === "editor");
  const novos = r.cortar.filter(c => !velhos.some(x => chave(x) === chave(c)));
  const listaNovos = `<h3>Mudanças de corte (ainda não montadas)</h3>${novos.length || r.inicio_q !== inteiroVideo(antes.inicio_q) || r.fim_q !== inteiroVideo(antes.fim_q) ? `<ol class="vaba-cortes" id="vaba-cortes-novos">
    ${novos.map(c => { const x = tDoQ(m, c[0])[0], y = tDoQ(m, c[1])[0], txt = unidades.filter(u => u.a >= x - 0.01 && u.b <= y + 0.01).map(u => u.t).join(" ");
      return `<li>${segVideo(x)} s a ${segVideo(y)} s (${segVideo((c[1] - c[0]) / ABA_VIDEO_FPS)} s)${txt ? ` “${h(cortarPauta(txt, 60))}”` : ""}
        <span class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-ouvir" data-em="${x}">Ouvir</button>${ed ? `<button class="btn peq sec" type="button" data-acao="vaba-desfazer" data-de="${c[0]}" data-ate="${c[1]}">Desfazer</button>` : ""}</span></li>`; }).join("")}
    ${r.inicio_q !== inteiroVideo(antes.inicio_q) ? `<li>${r.inicio_q === null ? "Sem o começo marcado (volta na próxima montagem)" : `Começa aos ${segVideo(tDoQ(m, r.inicio_q)[0])} s`}${ed ? ` <span class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-desfazer" data-marca="inicio_q">Desfazer</button></span>` : ""}</li>` : ""}
    ${r.fim_q !== inteiroVideo(antes.fim_q) ? `<li>${r.fim_q === null ? "Sem o fim marcado (volta na próxima montagem)" : `Termina aos ${segVideo(tDoQ(m, r.fim_q)[0])} s`}${ed ? ` <span class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-desfazer" data-marca="fim_q">Desfazer</button></span>` : ""}</li>` : ""}</ol>`
    : `<p class="sub">Nenhuma ainda. Até 30 cortes por vídeo.</p>`}`;
  const listaVelhos = velhos.length || inteiroVideo(antes.inicio_q) !== null || inteiroVideo(antes.fim_q) !== null ? `<h3>Já no vídeo</h3><ul class="vaba-cortes" id="vaba-cortes-velhos">
    ${velhos.map(c => { const fica = r.cortar.some(x => chave(x) === chave(c)), info = cortesRel.find(x => x.chave === "e:" + c[0]);
      return `<li>Corte do editor${info && numVideo(info.em_s) !== null ? ` aos ${segVideo(info.em_s)} s` : ""} (${segVideo((c[1] - c[0]) / ABA_VIDEO_FPS)} s)${textoDe(info?.texto) ? ` “${h(info.texto)}”` : ""}
        ${fica ? (ed ? `<span class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-desfazer-salvo" data-de="${c[0]}" data-ate="${c[1]}">Desfazer</button></span>` : "")
          : ` ${selo("desfeito: volta na próxima montagem (a prévia ainda não mostra)", "alerta")}${ed ? ` <span class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-refazer-salvo" data-de="${c[0]}" data-ate="${c[1]}">Manter o corte</button></span>` : ""}`}</li>`; }).join("")}
    ${inteiroVideo(antes.inicio_q) !== null ? `<li>Começo marcado (${segVideo(objVideo(rel.edicao).inicio_cortado_s || 0)} s tirados do começo)</li>` : ""}
    ${inteiroVideo(antes.fim_q) !== null ? `<li>Fim marcado (${segVideo(objVideo(rel.edicao).fim_cortado_s || 0)} s tirados do fim)</li>` : ""}</ul>` : "";
  // os cortes do robô no meio da fala ("Manter este trecho") e as divergências ("A transcrição errou" e "Cortar este trecho")
  const meio = listaVideo(rel.cortes).filter(c => numVideo(c.em_s) !== null && c.tipo !== "editor");
  const robo = meio.length ? `<h3>Cortes do robô</h3><ul class="vaba-cortes" id="vaba-cortes-robo">${meio.map(c => { const k = CHAVE_CORTE.test(String(c.chave ?? "")) ? c.chave : "";
    return `<li>${h(deMapaVideo(TIPOS_CORTE, c.tipo) || c.tipo)} aos ${segVideo(c.em_s)} s (${segVideo(c.dur_s, 2)} s)${textoDe(c.texto) ? ` “${h(c.texto)}”` : ""}
      ${k ? `<label class="video-check"><input type="checkbox" class="vaba-manter" value="${h(k)}"${r.manter.includes(k) ? " checked" : ""}${dis}> Manter este trecho</label>` : ""}</li>`; }).join("")}</ul>` : "";
  const divs = listaVideo(rel.divergencias), aceitasAba = listaMarcas(objVideo(v.ajustes).aceitas, ID_DIVERGENCIA);
  const divergencias = divs.length ? `<h3>Divergências com o roteiro</h3><ul class="vaba-cortes" id="vaba-divergencias">${divs.map((d, i) => { const marca = ID_DIVERGENCIA.test(String(d.id ?? "")) ? d.id : "";
    const aceita = d.aceita === true || aceitasAba.includes(marca);                      // v0.40.0: "Aceitar — quis dizer o mesmo"
    return `<li>${numVideo(d.em_s) !== null ? `Aos ${segVideo(d.em_s)} s` : "No vídeo"} a fala diz “${h(d.falado)}” e o roteiro diz “${h(d.roteiro)}”${d.parece_transcricao === true && !d.cortada && !aceita ? ` — <b>parece erro da transcrição</b>: ouça e confirme` : ""}${textoDe(d.juiz) && !d.cortada && !aceita && !d.transcricao_errou ? ` — juiz de sentido: ${h(d.juiz)}` : ""}${d.veredito === "equivalente" && d.regravar === false && !aceita ? ` ${selo("quis dizer o mesmo (juiz de sentido)", "ok")}` : ""}${aceita ? ` ${selo("aceita: quis dizer o mesmo", "ok")}` : ""}${d.cortada ? ` ${selo("cortada: não vai ao ar", "ok")}` : ""}
      ${!d.cortada && ed && numVideo(d.ate_s) !== null ? `<span class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-cortar-divergencia" data-i="${i}">Cortar este trecho</button></span>` : ""}
      ${!d.cortada && marca && !aceita ? `<label class="video-check"><input type="checkbox" class="vaba-errou" value="${h(marca)}"${r.errou.includes(marca) ? " checked" : ""}${dis}> A transcrição errou (vale o roteiro)</label>` : ""}
      ${ed && ["pronto", "regravar"].includes(v.situacao) && marca && !aceita && !d.transcricao_errou && !r.errou.includes(marca) && d.regravar !== false && !d.cortada ? `<span class="acoes"><button class="btn peq sec video-btn-aceitar" type="button" data-acao="vaba-aceitar" data-marca="${h(marca)}">Aceitar (quis dizer o mesmo)</button></span>` : ""}</li>`; }).join("")}</ul>` : "";
  // v0.33.0 (pedido do dono): o falado fora do roteiro, marcado para cortar com um clique (não sai sozinho: pode mudar o sentido)
  const foras = listaVideo(rel.fora_do_roteiro);
  const foraDoRoteiro = foras.length ? `<h3>Falado fora do roteiro (fica no vídeo e na legenda)</h3><ul class="vaba-cortes" id="vaba-fora">${foras.map((x, i) =>
    `<li>${numVideo(x.em_s) !== null ? `Aos ${segVideo(x.em_s)} s` : "No vídeo"}: “${h(x.texto)}”
      ${ed && numVideo(x.em_s) !== null && numVideo(x.ate_s) !== null ? `<span class="acoes"><button class="btn peq sec" type="button" data-acao="vaba-cortar-fora" data-i="${i}">Cortar este trecho</button></span>` : ""}</li>`).join("")}</ul>` : "";
  return linha + palavras + botoes + listaNovos + listaVelhos + robo + divergencias + foraDoRoteiro;
}
/* 2. Texto da legenda: um bloco por linha, cada palavra num campo */
function htmlLegendaAbaVideo(v, r, ed){
  const blocos = listaVideo(objVideo(objVideo(v.relatorio).legenda).lista), recusas = recusasLegendaVideo(v, r), rec = listaVideo(objVideo(objVideo(v.relatorio).legenda).recusados);
  const pulos = pulosDaPreviaVideo(v, r);
  if(!blocos.length) return `<p class="sub">A lista dos blocos da legenda não veio no relatório.</p>`;
  return `<p class="sub">Troque palavra por palavra: cada palavra nova é a do roteiro ou parecida com a que estava; número, data, mês e termo do glossário não mudam aqui (se a fala está errada, corte o trecho ou grave de novo).</p>
    ${rec.length ? `<div class="aviso alerta" id="vaba-recusados">Na montagem anterior, foi recusado: ${rec.map(x => `bloco ${h(x.bloco)}, ${h(deMapaVideo(MOTIVOS_LEGENDA, x.motivo) || x.motivo)}`).join("; ")}.</div>` : ""}
    ${blocos.map((b, i) => { const texto = String(r.legenda[i] ?? b.texto ?? ""), ok = Number.isInteger(numVideo(b.u)) && Number.isInteger(numVideo(b.palavras)), em = numVideo(b.em_s);
      const sai = em !== null && pulos.some(([x, y]) => em >= x - 0.01 && em < y);
      return `<div class="vaba-bloco${sai ? " sai" : ""}" data-bloco="${i}"><span class="sub">${em !== null ? `Aos ${segVideo(em)} s` : `Bloco ${i + 1}`}${sai ? " · sai com o corte" : ""}${!ok ? " · não editável" : ""}</span>
        <span class="vaba-bloco-palavras">${texto.split(" ").map((w, k) => `<input type="text" class="vaba-leg" data-bloco="${i}" data-k="${k}" value="${h(w)}" size="${Math.max(2, Array.from(w).length + 1)}" maxlength="40" aria-label="Palavra ${k + 1} do bloco ${i + 1}"${ed && ok ? "" : " disabled"}>`).join("")}</span>
        ${ed && ok ? `<button class="btn peq sec" type="button" data-acao="vaba-desfazer-bloco" data-bloco="${i}" aria-label="Desfazer a edição do bloco ${i + 1}">Desfazer</button>` : ""}
        <span class="vaba-recusa sub" id="vaba-recusa-${i}">${recusas[i] ? h("Recusado: " + (deMapaVideo(MOTIVOS_LEGENDA, recusas[i]) || recusas[i]) + ".") : ""}</span></div>`; }).join("")}`;
}
/* 3. Estilo: tamanho, posição e cor (a paleta do banco), a compacta e a amostra */
function htmlEstiloAbaVideo(v, r, ed){
  const pal = objVideo(abaVideo().paleta), dis = ed ? "" : " disabled";
  const grupo = (nome, lista, atual, rotulo) => `<fieldset class="checks vaba-escolha"><legend>${rotulo}</legend>${listaVideo(pal[lista]).map(x =>
    `<label><input type="radio" name="vaba-${nome}" value="${h(x.chave)}"${x.chave === atual ? " checked" : ""}${dis}> ${h(x.nome)}</label>`).join("")}</fieldset>`;
  return `${grupo("tamanho", "tamanhos", r.tamanho, "Tamanho")}${grupo("posicao", "posicoes", r.posicao, "Posição")}
    <fieldset class="checks vaba-cores"><legend>Cor (só as da Artecon)</legend>${listaVideo(pal.cores).map(c =>
      `<label class="vaba-cor"><input type="radio" name="vaba-cor" value="${h(c.chave)}"${c.chave === r.cor ? " checked" : ""}${dis}>
        <span class="vaba-amostra-cor" style="background:${/^#[0-9A-Fa-f]{6}$/.test(c.caixa) ? c.caixa : "#011F48"};color:${/^#[0-9A-Fa-f]{6}$/.test(c.texto) ? c.texto : "#FFFFFF"}">Aa</span> ${h(c.nome)}</label>`).join("")}</fieldset>
    <label class="video-check"><input type="checkbox" id="vaba-compacta"${r.compacta ? " checked" : ""}${dis}> Legenda compacta (1 linha, letra menor)</label>
    <div class="vaba-amostra-caixa">${htmlAmostraLegenda(v, r)}<p class="sub">Amostra: o vídeo muda depois de montar de novo. “Em cima” pode cobrir o rosto.</p></div>`;
}
function htmlAmostraLegenda(v, r){
  const c = listaVideo(objVideo(abaVideo().paleta).cores).find(x => x.chave === r.cor) || {texto:"#FFFFFF", caixa:"#011F48"};
  const cor = x => /^#[0-9A-Fa-f]{6}$/.test(x) ? x : "#011F48", bloco = listaVideo(objVideo(objVideo(v.relatorio).legenda).lista)[0];
  const texto = r.legenda[0] ?? bloco?.texto ?? "O texto da legenda";
  const gancho = r.sem_gancho ? "" : r.gancho.replace(/\s+/g, " ").trim();
  return `<div class="vaba-amostra" id="vaba-amostra" data-posicao="${h(r.posicao)}" data-tamanho="${h(r.tamanho)}">
    <span class="vaba-amostra-rosto"></span>
    ${gancho ? `<span class="vaba-amostra-gancho" style="background:${cor(c.caixa)}cc;color:${cor(c.texto)}">${h(cortarPauta(gancho, 44))}</span>` : ""}
    <span class="vaba-amostra-fala${r.compacta ? " compacta" : ""}" style="background:${cor(c.caixa)}cc;color:${cor(c.texto)}">${h(cortarPauta(texto, r.compacta ? 30 : 48))}</span></div>`;
}
/* 4. Gancho */
function htmlGanchoAbaVideo(v, r, ed){
  const dis = ed ? "" : " disabled", travas = termosDoEditor(r).filter(([l]) => l === "no texto do gancho");
  return `<label for="vaba-gancho">Texto do gancho (de 0 a 3 s)</label>
    <input id="vaba-gancho" type="text" maxlength="120" value="${h(r.gancho)}"${r.sem_gancho ? " disabled" : dis}>
    <p class="sub"><span id="vaba-gancho-conta">${Array.from(r.gancho).length}</span>/120 · Até uns 44 caracteres cabem em 2 linhas; o que não couber fica de fora com aviso.</p>
    <label class="video-check"><input type="checkbox" id="vaba-sem-gancho"${r.sem_gancho ? " checked" : ""}${dis}> Sem texto do gancho</label>
    <div id="vaba-gancho-termos">${travas.length ? `<div class="aviso erro">${h(msgTermosPeca(travas, "montar"))}</div>` : ""}</div>
    <p class="sub">É o “Texto do gancho” da peça: mudar aqui muda lá também (a peça pronta volta a “em produção”).</p>`;
}
/* 5. Cartela final: as linhas (refazer) e o texto extra (o das Configurações, um próprio ou sem) */
function htmlCartelaAbaVideo(v, r, ed){
  const dis = ed ? "" : " disabled", nova = linhasCartela(v.fala_pessoa), mudou = JSON.stringify(nova) !== JSON.stringify(v.cartela_linhas || []);
  const linhas = r.refazer ? nova : (Array.isArray(v.cartela_linhas) ? v.cartela_linhas : []), conf = textoDe(confVideo().cartela_extra);
  const travas = termosDoEditor(r).filter(([l]) => l === "no texto extra da cartela");
  return `<ul class="video-cartela" id="vaba-cartela-linhas">${linhas.map(l => `<li>${h(l)}</li>`).join("")}</ul>
    <label class="video-check"><input type="checkbox" id="vaba-refazer"${r.refazer ? " checked" : ""}${dis}> Refazer com as Configurações e Pessoas e termos de hoje${mudou ? ` <span class="selo alerta">mudou</span>` : ""}</label>
    <fieldset class="checks vaba-extra"><legend>Texto extra</legend>
      <label><input type="radio" name="vaba-extra" value="config"${r.extra.modo === "config" ? " checked" : ""}${dis}> O das Configurações: “${h(conf || "nenhum")}”</label>
      <label><input type="radio" name="vaba-extra" value="proprio"${r.extra.modo === "proprio" ? " checked" : ""}${dis}> Próprio deste vídeo:</label>
      <input id="vaba-extra-texto" type="text" maxlength="120" value="${h(r.extra.texto)}" aria-label="Texto extra próprio deste vídeo"${ed && r.extra.modo === "proprio" ? "" : " disabled"}>
      <label><input type="radio" name="vaba-extra" value="sem"${r.extra.modo === "sem" ? " checked" : ""}${dis}> Sem texto extra</label></fieldset>
    <div id="vaba-extra-termos">${travas.length ? `<div class="aviso erro">${h(msgTermosPeca(travas, "montar"))}</div>` : ""}</div>
    ${faltaIdentificacao().length ? `<div class="aviso erro">A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura.</div>` : ""}
    <p class="sub">A identificação legal e a linha de quem fala vêm das Configurações e de Pessoas e termos: não se editam aqui.</p>`;
}
/* 6. Capa */
function htmlCapaAbaVideo(v, r, ed){
  const a = abaVideo(), m = mapaVideo(v), capa = objVideo(objVideo(v.relatorio).capa);
  const caiu = m && r.capa_q !== null && !quadroFicaVideo(m, ajustesDoEditor(v, r), r.capa_q);
  return `${a.previa?.capa ? `<figure class="vaba-capa"><img src="${h(a.previa.capa)}" alt="Capa atual do reel"><figcaption class="sub">Capa atual${numVideo(capa.em_ms) !== null ? `, aos ${segVideo(capa.em_ms / 1000)} s` : ""}${capa.movida ? " (foi para o quadro mais perto)" : ""}</figcaption></figure>`
      : `<p class="sub" id="vaba-capa-atual">${numVideo(capa.em_ms) !== null ? `Capa aos ${segVideo(capa.em_ms / 1000)} s (abra o vídeo para ver).` : "Sem capa escolhida: o Instagram usa o primeiro quadro."}</p>`}
    ${r.capa_q !== inteiroVideo(objVideo(v.ajustes).capa_q) && m ? `<p id="vaba-capa-nova">${r.capa_q === null ? "A capa escolhida sai na próxima montagem." : `Capa nova aos ${segVideo(tDoQ(m, r.capa_q)[0])} s (aparece depois de montar).`}</p>` : ""}
    ${caiu ? `<div class="aviso erro" id="vaba-capa-cortada">A capa caiu num trecho cortado: escolha outro quadro.</div>` : ""}
    ${ed && m ? `<div class="acoes"><button class="btn peq" type="button" data-acao="vaba-capa-aqui"${a.previa ? "" : " disabled"}>Usar o quadro do player como capa (agora: <span id="vaba-capa-agora">0</span> s)</button>
      ${r.capa_q !== null ? `<button class="btn peq sec" type="button" data-acao="vaba-capa-tirar">Tirar a capa escolhida</button>` : ""}</div>` : ""}
    <p class="sub">A capa é um quadro da fala, sem a legenda; na peça aprovada, baixe-a junto com o vídeo para postar.</p>`;
}
/* O rodapé: o resumo, a duração e os botões (só o administrador, com o vídeo editável) */
function htmlRodapeAbaVideo(){
  const a = abaVideo(), v = a.v;
  if(!editavelVideo(v, a.peca)) return "";
  const r = rascunhoVideo(v), m = mapaVideo(v), mudou = mudouAbaVideo(v, r), resumo = resumoMudancasVideo(v, r);
  const dur = m ? duracaoEstimadaVideo(m, ajustesDoEditor(v, r)) : null, meta = limiteDuracaoVideo();
  const fora = dur !== null && (dur < ABA_VIDEO_LIMITES.min || dur > ABA_VIDEO_LIMITES.max), acima = !fora && dur !== null && dur > meta;
  return `<p class="vaba-resumo" id="vaba-resumo">${resumo.length ? "Mudanças: " + h(resumo.join(", ")) : "Nenhuma mudança ainda."}</p>
    ${dur !== null ? `<p id="vaba-duracao" class="${fora ? "vaba-fora" : acima ? "vaba-acima" : ""}">Duração depois de montar: cerca de ${segVideo(dur)} s (meta: até ${segVideo(meta)} s; mínimo 5 s, máximo 15 min)${acima ? " — acima da meta: aceito, e a aprovação pede confirmação" + (dur > 90 ? "; acima de 90 s o reel sai só no Instagram" : "") : ""}</p>` : ""}
    <div class="acoes">${mudou ? `<button class="btn peq sec" type="button" data-acao="vaba-descartar">Descartar as mudanças</button>` : ""}
      <button class="btn verde" type="button" data-acao="vaba-montar"${mudou && !fora ? "" : " disabled"}>Montar de novo com estas mudanças</button></div>`;
}
/* refaz as seções e o rodapé (o player fica: o vídeo não recarrega), com as seções abertas como estavam */
function redesenharEditorVideo(){
  const a = abaVideo(); if(!a.v || !$("#vaba-secoes")) return;
  a.pulos = pulosDaPreviaVideo(a.v, rascunhoVideo(a.v));
  const s = $("#vaba-secoes"), rod = $("#vaba-rodape"), y = window.scrollY;
  s.innerHTML = htmlSecoesAbaVideo();
  if(rod) rod.innerHTML = htmlRodapeAbaVideo();
  window.scrollTo(0, y);
  atualizarTempoVideo();
}
/* só o rodapé, a amostra e as recusas (enquanto digita: o campo não perde o foco) */
function atualizarRodapeVideo(){
  const a = abaVideo(), v = a.v; if(!v) return;
  const r = rascunhoVideo(v), rod = $("#vaba-rodape"), am = $("#vaba-amostra"), rec = recusasLegendaVideo(v, r);
  a.pulos = pulosDaPreviaVideo(v, r);
  if(rod) rod.innerHTML = htmlRodapeAbaVideo();
  if(am) am.outerHTML = htmlAmostraLegenda(v, r);
  document.querySelectorAll(".vaba-recusa").forEach(el => { const i = el.id.replace("vaba-recusa-", "");
    el.textContent = rec[i] ? "Recusado: " + (deMapaVideo(MOTIVOS_LEGENDA, rec[i]) || rec[i]) + "." : ""; });
  const termos = termosDoEditor(r), g = $("#vaba-gancho-termos"), x = $("#vaba-extra-termos");
  const msg = lugar => { const t = termos.filter(([l]) => l === lugar); return t.length ? `<div class="aviso erro">${h(msgTermosPeca(t, "montar"))}</div>` : ""; };
  if(g) g.innerHTML = msg("no texto do gancho");
  if(x) x.innerHTML = msg("no texto extra da cartela");
}

/* ------------------------------------------------------------- o player e a prévia */
async function abrirPreviaAbaVideo(silencioso){
  const a = abaVideo(), v = a.v; if(!v) return;
  const r = await funcaoVideo("previa", {id:v.id});
  if(!linkVideoOk(r?.video) || !Array.isArray(r?.quadros) || r.quadros.length !== 4 || !r.quadros.every(linkVideoOk) || !/^[0-9a-f]{64}$/.test(String(r?.sha256))
     || (r.capa !== null && r.capa !== undefined && !linkVideoOk(r.capa)))
    throw new ErroApi("A função devolveu a prévia fora do formato.");
  if(r.sha256 !== v.sha256) throw new ErroApi("O vídeo corrigido mudou enquanto a prévia abria: volte à lista e abra de novo.");
  a.previa = {id:v.id, sha256:r.sha256, video:r.video, quadros:r.quadros, capa:r.capa || null, em:Date.now()};
  const col = $("#vaba-player-col"); if(col) col.innerHTML = htmlPlayerAbaVideo();
  redesenharEditorVideo();
  ligarPlayerAbaVideo();
  if(!silencioso) $("#vaba-player")?.scrollIntoView({block:"nearest"});
}
/* o instante do player nos textos (o tempo, a palavra atual, o cursor da linha do tempo e a capa "agora") */
function atualizarTempoVideo(){
  const a = abaVideo(), pl = $("#vaba-player"); if(!pl || !a.v) return;
  const t = pl.currentTime || 0, m = mapaVideo(a.v), el = $("#vaba-tempo"), agora = $("#vaba-capa-agora"), cur = $("#vaba-cursor");
  if(el) el.textContent = `${segVideo(t)} s${Number.isFinite(pl.duration) ? ` de ${segVideo(pl.duration)} s` : ""}`;
  if(agora) agora.textContent = segVideo(t);
  if(cur && m){ const total = falaDoVideoS(m) + numVideo(m.pad_q || 0) / ABA_VIDEO_FPS + cartelaSVideo() - 0.4; cur.style.left = Math.max(0, Math.min(100, 100 * t / total)) + "%"; }
  const us = listaVideo(objVideo(a.v.relatorio).unidades);
  document.querySelectorAll("#vaba-palavras .vaba-p").forEach((b, i) => b.classList.toggle("atual", !!us[i] && t >= us[i].a && t < us[i].b + 0.05));
}
/* a prévia com as mudanças: dentro de um trecho que sai, o player salta para o fim dele (laço a cada quadro enquanto toca) */
function pularCortesVideo(){
  const a = abaVideo(), pl = $("#vaba-player");
  if(!pl || !a.previaLigada) return;
  const t = pl.currentTime;
  for(const [x, y] of a.pulos || []) if(t >= x && t < y - 0.02){ pl.currentTime = y; break; }
}
function ligarPlayerAbaVideo(){
  const a = abaVideo(), pl = $("#vaba-player"); if(!pl || pl.dataset.ligado) return;
  pl.dataset.ligado = "1";
  a.pulos = a.v ? pulosDaPreviaVideo(a.v, rascunhoVideo(a.v)) : [];
  const laco = () => { if(pl.paused || pl.ended || !pl.isConnected) return; pularCortesVideo(); atualizarTempoVideo(); requestAnimationFrame(laco); };
  pl.addEventListener("play", () => { pularCortesVideo(); requestAnimationFrame(laco); });
  for(const ev of ["seeking", "timeupdate"]) pl.addEventListener(ev, () => { pularCortesVideo(); atualizarTempoVideo(); });
  pl.addEventListener("loadedmetadata", atualizarTempoVideo);
  // o link venceu (10 minutos): pede outro uma vez
  pl.addEventListener("error", () => { const pv = abaVideo().previa;
    if(pv && !pv.renovado && Date.now() - pv.em > 60000){ pv.renovado = true; abrirPreviaAbaVideo(true).catch(() => {}); } });
}
/* os campos do editor (input e change, no próprio #vaba-editor; nada roda no carregamento do arquivo) */
function ligarEditorVideo(){
  const box = $("#vaba-editor"); if(!box || box.dataset.ligado) return;
  box.dataset.ligado = "1";
  const r = () => rascunhoMexidoVideo(abaVideo().v);
  box.addEventListener("input", ev => {
    const t = ev.target, a = abaVideo(); if(!a.v || !editavelVideo(a.v, a.peca)) return;
    if(t.matches(".vaba-leg")){
      const i = t.dataset.bloco, ws = [...box.querySelectorAll(`.vaba-leg[data-bloco="${i}"]`)].map(x => x.value.replace(/\s+/g, " ").trim());
      r().legenda[i] = ws.join(" ").replace(/\s+/g, " ").trim();
    }
    if(t.id === "vaba-gancho"){ r().gancho = t.value; const c = $("#vaba-gancho-conta"); if(c) c.textContent = Array.from(t.value).length; }
    if(t.id === "vaba-extra-texto") r().extra.texto = t.value;
    atualizarRodapeVideo();
  });
  box.addEventListener("change", ev => {
    const t = ev.target, a = abaVideo(); if(!a.v) return;
    if(t.id === "vaba-previa-ligada"){ a.previaLigada = t.checked; return; }
    if(!editavelVideo(a.v, a.peca)) return;
    const rr = r();
    if(t.matches(".vaba-manter")) rr.manter = [...box.querySelectorAll(".vaba-manter:checked")].map(x => x.value).filter(x => CHAVE_CORTE.test(x));
    else if(t.matches(".vaba-errou")) rr.errou = [...box.querySelectorAll(".vaba-errou:checked")].map(x => x.value).filter(x => ID_DIVERGENCIA.test(x));
    else if(t.name === "vaba-tamanho") rr.tamanho = t.value;
    else if(t.name === "vaba-posicao") rr.posicao = t.value;
    else if(t.name === "vaba-cor") rr.cor = t.value;
    else if(t.id === "vaba-compacta") rr.compacta = t.checked;
    else if(t.id === "vaba-sem-gancho"){ rr.sem_gancho = t.checked; const g = $("#vaba-gancho"); if(g) g.disabled = t.checked; }
    else if(t.id === "vaba-refazer"){ rr.refazer = t.checked; return redesenharEditorVideo(); }
    else if(t.name === "vaba-extra"){ rr.extra.modo = t.value; const x = $("#vaba-extra-texto"); if(x) x.disabled = t.value !== "proprio"; }
    else return;
    atualizarRodapeVideo();
  });
  box.addEventListener("toggle", ev => { if(ev.target.dataset?.secao) abaVideo().abertas[ev.target.dataset.secao] = ev.target.open; }, true);
  // a linha do tempo: o toque leva o player ao ponto tocado
  box.addEventListener("click", ev => {
    const barra = ev.target.closest?.("#vaba-linha"), pl = $("#vaba-player"), m = mapaVideo(abaVideo().v);
    if(!barra || !pl || !m) return;
    const c = barra.getBoundingClientRect(), total = falaDoVideoS(m) + numVideo(m.pad_q || 0) / ABA_VIDEO_FPS + cartelaSVideo() - 0.4;
    pl.currentTime = Math.max(0, Math.min(total, total * (ev.clientX - c.left) / Math.max(1, c.width)));
  });
}
/* Depois de desenhar (index.html, desenhar()): liga o editor e o player; enquanto o vídeo está na fila ou com o robô, sonda */
function depoisDeDesenharAbaVideo(atraso){
  const a = abaVideo();
  clearTimeout(a.relogio);
  if(!a.visibilidade){ a.visibilidade = true; document.addEventListener("visibilitychange", () => { if(!document.hidden && E.aba === "video") depoisDeDesenharAbaVideo(500); }); }
  ligarEditorVideo();
  ligarPlayerAbaVideo();
  atualizarTempoVideo();
  const v = a.v;
  if(!a.id || !v || !$("#vaba-editor") || !["na_fila", "processando"].includes(v.situacao)) return;
  a.relogio = setTimeout(sondarAbaVideo, atraso ?? VIDEO_INTERVALO);
}
async function sondarAbaVideo(){
  const a = abaVideo(), v = a.v;
  if(!v || E.aba !== "video" || a.id !== v.id || !$("#vaba-editor") || document.hidden) return;
  let novo = null;
  try{ [novo] = await ler("radar_videos", {select:"id,situacao,atualizado_em", id:"eq." + v.id}); }
  catch(e){ depoisDeDesenharAbaVideo(); return; }
  if(abaVideo().id !== v.id || !$("#vaba-editor")) return;
  if(novo && (novo.situacao !== v.situacao || novo.atualizado_em !== v.atualizado_em)){
    if(["pronto", "regravar"].includes(novo.situacao)) recado(v.peca_id === null ? "Vídeo montado de novo: confira a prévia; o avulso pronto se baixa nesta aba (só o administrador)."
      : "Vídeo montado de novo: confira a prévia; a aprovação é na peça.");
    else if(novo.situacao === "erro") recado("O corretor parou com erro: veja o motivo.", "aviso");
    if(!["na_fila", "processando"].includes(novo.situacao) || novo.situacao !== v.situacao) return desenhar();
  }
  depoisDeDesenharAbaVideo();
}

/* ------------------------------------------------------------- as ações */
const videoDaAba = () => { const a = abaVideo(); if(!a.v || !$("#vaba-editor")) throw new ErroApi("Abra o vídeo de novo na aba Vídeo."); return a.v; };
const playerDaAba = () => { const pl = $("#vaba-player"); if(!pl) throw new ErroApi("Abra o vídeo (“Ver o vídeo”) para marcar pelo player."); return pl; };
const editavelDaAba = () => { const a = abaVideo(), v = videoDaAba(); if(!editavelVideo(v, a.peca)) throw new ErroApi("Este vídeo não pode ser editado agora."); return v; };
/* a seleção de palavras vira quadros da linha original: do meio do vão antes da 1ª ao meio do vão depois da última */
function corteDasPalavrasVideo(v, i0, i1){
  const m = mapaVideo(v), us = listaVideo(objVideo(v.relatorio).unidades), fala = falaDoVideoS(m), u0 = us[i0], u1 = us[i1], ant = us[i0 - 1], prox = us[i1 + 1];
  const de = ant ? (ant.b + u0.a) / 2 : Math.max(0, u0.a - 0.1), ate = prox ? (u1.b + prox.a) / 2 : Math.min(fala, u1.b + 0.1);
  const q0 = qDoVideo(m, de), q1 = qDoVideo(m, Math.max(de, ate - 1e-6));
  if(q0 === null || q1 === null) throw new ErroApi("A cartela fica sempre (identificação legal).");
  return [q0, q1 + 1];
}
function acrescentarCorteVideo(v, c){
  const r = rascunhoMexidoVideo(v), m = mapaVideo(v), novo = juntarCortesVideo([...r.cortar, c], m.linha_q);
  if(novo.length > ABA_VIDEO_LIMITES.cortes) throw new ErroApi("Até 30 cortes por vídeo.");
  if(c[1] - c[0] < ABA_VIDEO_LIMITES.corteMin) throw new ErroApi("O trecho é curto demais (menos de 0,1 s): marque um trecho maior.");
  r.cortar = novo; abaVideo().selecao = null;
  redesenharEditorVideo();
}
/* v0.33.0: corta um trecho apontado pelo relatório (uma divergência ou um falado fora do roteiro), pelas palavras quando dá */
function cortarTrechoRelatado(v, lista, i, recado){
  const d = listaVideo(objVideo(v.relatorio)[lista])[i], us = listaVideo(objVideo(v.relatorio).unidades);
  if(!d || numVideo(d.em_s) === null || numVideo(d.ate_s) === null) throw new ErroApi(recado);
  const dentro = us.map((u, k) => [u, k]).filter(([u]) => u.b > d.em_s + 0.01 && u.a < d.ate_s - 0.01).map(([, k]) => k);
  if(dentro.length) return acrescentarCorteVideo(v, corteDasPalavrasVideo(v, dentro[0], dentro[dentro.length - 1]));
  const m = mapaVideo(v), q0 = qDoVideo(m, Math.max(0, d.em_s - 0.05)), q1 = qDoVideo(m, d.ate_s + 0.05);
  if(q0 === null || q1 === null) throw new ErroApi("A cartela fica sempre (identificação legal).");
  acrescentarCorteVideo(v, [q0, q1 + 1]);
}
const ACOES_ABA_VIDEO = {
  /* da peça (radar-pauta.js): "Editar na aba Vídeo"; com texto não salvo na peça, pergunta antes */
  "video-aba"(el){
    const f = $("form[data-form=peca]");
    if(f && pecaMudou(f) && !confirm(avisoPecaSuja(f, "A peça tem alteração não salva.") + " Sair da peça sem salvar?")) return;
    E.etapa = null; E.assunto = null; E.informativo = null; E.aba = "video"; E.pauta.peca = null;
    const a = abaVideo(); a.id = String(el.dataset.id || ""); a.selecao = null; a.marca = null;
    window.scrollTo(0, 0); return desenhar();
  },
  "vaba-filtro"(el){ const a = abaVideo(); a.filtro = el.dataset.filtro === "60" ? "60" : "futuro"; return desenhar(); },
  "vaba-abrir"(el){ const a = abaVideo(); a.id = String(el.dataset.id || ""); a.nova = false; a.selecao = null; a.marca = null; window.scrollTo(0, 0); return desenhar(); },
  "vaba-voltar"(){ const a = abaVideo(); a.id = null; a.v = null; a.nova = false; a.selecao = null; a.marca = null; return desenhar(); },
  /* v0.36.0: a correção avulsa (o formulário abre e fecha sem gravar nada) */
  "vaba-avulso-novo"(){ const a = abaVideo(); a.nova = true; a.id = null; a.v = null; window.scrollTo(0, 0); return desenhar(); },
  "vaba-avulso-cancelar"(){ const a = abaVideo(); a.nova = false; return desenhar(); },
  "vaba-peca"(el){ E.aba = "pauta"; E.pauta.peca = Number(el.dataset.id); E.pauta.vista = "semana"; E.pauta.nova = null; abaVideo().id = null; window.scrollTo(0, 0); return desenhar(); },
  "vaba-palavra"(el){
    const a = abaVideo(), i = Number(el.dataset.i), pl = $("#vaba-player");
    if(pl && Number.isFinite(Number(el.dataset.a))) pl.currentTime = Number(el.dataset.a);
    if(!editavelVideo(a.v, a.peca)) return;
    a.selecao = a.selecao && a.selecao[0] === a.selecao[1] && a.selecao[0] !== i ? [Math.min(a.selecao[0], i), Math.max(a.selecao[0], i)] : [i, i];
    redesenharEditorVideo();
  },
  "vaba-limpar-selecao"(){ abaVideo().selecao = null; redesenharEditorVideo(); },
  "vaba-cortar"(){ const v = editavelDaAba(), s = abaVideo().selecao; if(!s) throw new ErroApi("Selecione uma palavra (ou duas, para um trecho).");
    acrescentarCorteVideo(v, corteDasPalavrasVideo(v, s[0], s[1])); },
  "vaba-comecar-palavra"(){ const v = editavelDaAba(), s = abaVideo().selecao, u = listaVideo(objVideo(v.relatorio).unidades)[s?.[0]];
    if(!u) throw new ErroApi("Selecione uma palavra.");
    rascunhoMexidoVideo(v).inicio_q = qDoVideo(mapaVideo(v), Math.max(0, u.a - 0.12)); abaVideo().selecao = null; redesenharEditorVideo(); },
  "vaba-terminar-palavra"(){ const v = editavelDaAba(), s = abaVideo().selecao, us = listaVideo(objVideo(v.relatorio).unidades), u = us[s?.[1]], prox = us[(s?.[1] ?? -2) + 1];
    if(!u) throw new ErroApi("Selecione uma palavra.");
    const m = mapaVideo(v), t = Math.min(u.b + 0.45, prox ? prox.a - 0.05 : u.b + 0.45, falaDoVideoS(m) - 1e-6), q = qDoVideo(m, Math.max(u.b, t));
    rascunhoMexidoVideo(v).fim_q = q === null ? null : q + 1; abaVideo().selecao = null; redesenharEditorVideo(); },
  "vaba-marcar-de"(){ const v = editavelDaAba(), q = qDoVideo(mapaVideo(v), playerDaAba().currentTime);
    if(q === null) throw new ErroApi("A cartela fica sempre (identificação legal)."); abaVideo().marca = q; redesenharEditorVideo(); },
  "vaba-marcar-ate"(){ const v = editavelDaAba(), a = abaVideo(), q = qDoVideo(mapaVideo(v), playerDaAba().currentTime);
    if(a.marca === null || a.marca === undefined) throw new ErroApi("Marque antes o começo do corte.");
    if(q === null) throw new ErroApi("A cartela fica sempre (identificação legal).");
    const c = [Math.min(a.marca, q), Math.max(a.marca, q) + 1]; a.marca = null; acrescentarCorteVideo(v, c); },
  "vaba-comecar-aqui"(){ const v = editavelDaAba(), q = qDoVideo(mapaVideo(v), playerDaAba().currentTime);
    if(q === null) throw new ErroApi("A cartela fica sempre (identificação legal)."); rascunhoMexidoVideo(v).inicio_q = q; redesenharEditorVideo(); },
  "vaba-terminar-aqui"(){ const v = editavelDaAba(), q = qDoVideo(mapaVideo(v), playerDaAba().currentTime);
    if(q === null) throw new ErroApi("A cartela fica sempre (identificação legal)."); rascunhoMexidoVideo(v).fim_q = q; redesenharEditorVideo(); },
  "vaba-desfazer"(el){ const v = editavelDaAba(), r = rascunhoMexidoVideo(v), antes = objVideo(v.ajustes);
    if(el.dataset.marca === "inicio_q" || el.dataset.marca === "fim_q") r[el.dataset.marca] = inteiroVideo(antes[el.dataset.marca]);
    else r.cortar = r.cortar.filter(c => !(c[0] === Number(el.dataset.de) && c[1] === Number(el.dataset.ate)));
    redesenharEditorVideo(); },
  "vaba-desfazer-salvo"(el){ const v = editavelDaAba(), r = rascunhoMexidoVideo(v);
    r.cortar = r.cortar.filter(c => !(c[0] === Number(el.dataset.de) && c[1] === Number(el.dataset.ate))); redesenharEditorVideo(); },
  "vaba-refazer-salvo"(el){ const v = editavelDaAba(), r = rascunhoMexidoVideo(v);
    r.cortar = juntarCortesVideo([...r.cortar, [Number(el.dataset.de), Number(el.dataset.ate)]], mapaVideo(v).linha_q); redesenharEditorVideo(); },
  "vaba-desfazer-bloco"(el){ const v = editavelDaAba(); delete rascunhoMexidoVideo(v).legenda[el.dataset.bloco]; redesenharEditorVideo(); },
  "vaba-ouvir"(el){ const pl = playerDaAba(); pl.currentTime = Math.max(0, Number(el.dataset.em) - 2); pl.scrollIntoView({block:"nearest"}); pl.play?.().catch(() => {}); },
  "vaba-passo"(el){ const pl = playerDaAba(), passo = Number(el.dataset.passo);
    if(!passo){ if(pl.paused) pl.play?.().catch(() => {}); else pl.pause(); return; }
    pl.pause(); pl.currentTime = Math.max(0, Math.min(Number.isFinite(pl.duration) ? pl.duration : 1e9, pl.currentTime + passo)); },
  "vaba-capa-aqui"(){ const v = editavelDaAba(), q = qDoVideo(mapaVideo(v), playerDaAba().currentTime);
    if(q === null) throw new ErroApi("A capa é um quadro da fala: a cartela não vira capa."); rascunhoMexidoVideo(v).capa_q = q; redesenharEditorVideo(); },
  "vaba-capa-tirar"(){ const v = editavelDaAba(); rascunhoMexidoVideo(v).capa_q = null; redesenharEditorVideo(); },
  "vaba-cortar-divergencia"(el){
    cortarTrechoRelatado(editavelDaAba(), "divergencias", Number(el.dataset.i), "O trecho desta divergência não está no relatório.");
  },
  /* v0.33.0 (pedido do dono): o falado fora do roteiro se corta com um clique */
  "vaba-cortar-fora"(el){
    cortarTrechoRelatado(editavelDaAba(), "fora_do_roteiro", Number(el.dataset.i), "O trecho não está no relatório: monte de novo para liberar.");
  },
  "vaba-descartar"(){ const a = abaVideo(), v = videoDaAba();
    if(!confirm("Descartar as mudanças que ainda não foram montadas?")) return;
    a.rascunhos[v.id] = rascunhoNovoVideo(v); a.selecao = null; a.marca = null; redesenharEditorVideo(); recado("Mudanças descartadas."); },
  async "vaba-previa"(){ await abrirPreviaAbaVideo(false); },
  /* Montar de novo com estas mudanças (só o administrador): a tela confere o que sabe; o banco confere tudo de novo */
  async "vaba-montar"(){
    if(!ehAdmin()) throw new ErroApi("Só o administrador edita o vídeo do reel.");
    const v = editavelDaAba(), r = rascunhoMexidoVideo(v), m = mapaVideo(v);
    if(!mudouAbaVideo(v, r)) throw new ErroApi("Nada mudou.");
    const aj = ajustesDoEditor(v, r), dur = m ? duracaoEstimadaVideo(m, aj) : null;
    if(m && falaEstimadaQVideo(m, aj) < ABA_VIDEO_LIMITES.fala * ABA_VIDEO_FPS) throw new ErroApi("Os cortes deixam menos de 2 s de fala: desfaça um corte.");
    if(dur !== null && (dur < ABA_VIDEO_LIMITES.min || dur > ABA_VIDEO_LIMITES.max))
      throw new ErroApi(`O vídeo ficaria com cerca de ${segVideo(dur)} s: ${dur < ABA_VIDEO_LIMITES.min ? "o mínimo é 5 s" : "o máximo é 15 minutos (o Instagram não aceita reel mais longo)"}.`);
    const recusas = recusasLegendaVideo(v, r), blocos = listaVideo(objVideo(objVideo(v.relatorio).legenda).lista);
    for(const [i, motivo] of Object.entries(recusas)) throw new ErroApi(`Legenda (aos ${segVideo(numVideo(blocos[Number(i)]?.em_s) ?? 0)} s): ${MOTIVOS_LEGENDA[motivo] || motivo}.`);
    const termos = termosDoEditor(r);
    if(termos.length) throw new ErroApi(msgTermosPeca(termos, "montar"));
    if(m && aj.capa_q !== undefined && !quadroFicaVideo(m, aj, aj.capa_q)) throw new ErroApi("A capa caiu num trecho cortado: escolha outro quadro.");
    if(r.refazer && faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura.`);
    const gancho = ganchoDoEditor(v, r);
    if(!confirm("Montar o vídeo de novo com estas mudanças? Não transcreve de novo (não gasta minutos do mês) e leva alguns minutos." + (v.peca_id === null ? "" : " Enquanto o robô monta, o reel não pode ser aprovado.")
      + (gancho !== null && gancho !== "" && v.peca_id !== null ? " O texto do gancho também muda na peça." : "")
      + (dur !== null && dur > limiteDuracaoVideo() ? ` O vídeo fica com cerca de ${segVideo(dur)} s, acima da meta de ${segVideo(limiteDuracaoVideo())} s${dur > 90 ? " (acima de 90 s, o reel sai só no Instagram)" : ""}.` : ""))) return;
    await rpc("radar_video_editar", {p_id:v.id, p_sha256:v.sha256, p_ajustes:aj, p_cartela:cartelaDoEditor(v, r), p_gancho:gancho});
    const robo = await acionarCorretor();
    delete abaVideo().rascunhos[v.id];
    abaVideo().previa = null;
    await desenhar();
    recado(`Mudanças gravadas: o corretor monta o vídeo de novo. ${robo}`);
  },
  /* o vídeo do robô de antes (sem o mapa): monta de novo com os mesmos ajustes, para liberar os cortes e a capa (não transcreve) */
  async "vaba-liberar"(){
    const v = editavelDaAba();
    if(!confirm("Montar o vídeo de novo, sem mudança, para liberar os cortes e a capa? Não transcreve de novo e leva alguns minutos.")) return;
    await rpc("radar_video_editar", {p_id:v.id, p_sha256:v.sha256, p_ajustes:objVideo(v.ajustes), p_cartela:null, p_gancho:null});
    const robo = await acionarCorretor(); abaVideo().previa = null; await desenhar(); recado(`O corretor monta o vídeo de novo. ${robo}`);
  },
  async "vaba-de-novo"(){
    const v = videoDaAba(), refazer = v.erro_codigo === "cartela_nao_cabe";
    if(refazer && faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura.`);
    await rpc("radar_video_de_novo", {p_id:v.id, p_cartela:refazer ? linhasCartela(v.fala_pessoa) : null});
    const robo = await acionarCorretor(); await desenhar(); recado(`Pedido de novo ao corretor. ${robo}`);
  },
  /* v0.40.0: "Aceitar (quis dizer o mesmo)" na aba Vídeo — o mesmo radar_video_aceitar da peça: na hora, sem montar de novo */
  async "vaba-aceitar"(el){
    if(!ehAdmin()) throw new ErroApi("Só o administrador aceita uma divergência do vídeo.");
    const v = videoDaAba(), marca = String(el.dataset.marca || "");
    if(!ID_DIVERGENCIA.test(marca)) throw new ErroApi("A divergência não confere com o relatório: recarregue a aba Vídeo.");
    if(!confirm("Aceitar esta divergência: a pessoa quis dizer o MESMO com outras palavras? Ela deixa de pedir regravação na hora (sem montar de novo); a legenda fica com o que foi dito.")) return;
    const r = await rpc("radar_video_aceitar", {p_id:v.id, p_aceitas:[marca]});
    await desenhar();
    recado(r?.situacao === "pronto" ? "Divergência aceita: o vídeo corrigido está pronto." : "Divergência aceita; ainda há o que decidir.");
  },
  /* edicao_curta: os cortes do editor deixaram menos de 2 s de fala — tira os cortes, o começo e o fim e monta de novo */
  async "vaba-desfazer-edicao"(){
    if(!ehAdmin()) throw new ErroApi("Só o administrador edita o vídeo do reel.");
    const v = videoDaAba(), aj = {...objVideo(v.ajustes)};
    for(const k of ["cortar", "inicio_q", "fim_q", "capa_q"]) delete aj[k];
    if(!confirm("Tirar os cortes, o começo e o fim marcados na aba Vídeo e montar de novo? Não transcreve de novo.")) return;
    await rpc("radar_video_editar", {p_id:v.id, p_sha256:v.sha256, p_ajustes:aj, p_cartela:null, p_gancho:null});
    delete abaVideo().rascunhos[v.id];
    const robo = await acionarCorretor(); await desenhar(); recado(`O corretor monta o vídeo de novo, sem os cortes do editor. ${robo}`);
  },
  /* v0.36.0: o envio do vídeo avulso — a tela confere o que sabe; o banco confere tudo ANTES de qualquer arquivo sair
     (radar_video_criar_avulso) e só então os clipes sobem, um de cada vez (o mesmo TUS do reel) */
  async "vaba-avulso-enviar"(){
    const a = abaVideo();
    const titulo = juntarFala($("#vaba-avulso-titulo")?.value || "");
    const fala = cortarFala(juntarFala($("#vaba-avulso-fala")?.value || ""));
    const quem = Number($("#vaba-avulso-quem")?.value || 0);
    const marcadas = [...document.querySelectorAll(".vaba-avulso-pessoa:checked")].map(c => Number(c.value));
    const lista = clipesDe(0);
    a.avulso = {titulo, fala, quem:quem || "", marcadas};
    if(titulo.length < 3) throw new ErroApi("Dê um título ao vídeo avulso (de 3 a 120 caracteres).");
    conferirEnvio(null, lista);
    if(fala.length < 20 || fala.split(" ").length < 10) throw new ErroApi("Cole a fala para conferência (ao menos 10 palavras): é com ela que o corretor compara a gravação.");
    if(!marcadas.length) throw new ErroApi("Marque quem aparece no vídeo.");
    if(!quem || !marcadas.includes(quem)) throw new ErroApi("Escolha quem fala (e marque essa pessoa em Quem aparece).");
    const decl = [...document.querySelectorAll("#video-envio .video-declaracao")], faltaD = decl.filter(c => !c.checked);
    if(decl.length !== 4 || faltaD.length) throw new ErroApi("Marque as quatro declarações: " + faltaD.map(c => `“${c.dataset.texto}”`).join(", ") + ".");
    const achados = [["na fala para conferência", [...new Set([...termosPublicidade(fala).trava, ...termosPeca(fala)])]]].filter(([, l]) => l.length);
    if(achados.length) throw new ErroApi(msgTermosPeca(achados, "gravar"));
    if(faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura (o administrador preenche).`);
    const r = await funcaoVideo("envio_iniciar_avulso", {titulo, partes:lista.map((c, i) => ({n:i + 1, tipo:c.tipo, bytes:c.bytes})), fala_pessoa:quem,
      pessoas:marcadas, fala_roteiro:fala, cartela:linhasCartela(quem), declaracoes:decl.map(c => c.value), duracao:duracaoClipes(lista)}, 90000);
    if(!UUID_VIDEO.test(String(r?.id)) || !Array.isArray(r?.envios) || r.envios.length !== lista.length) throw new ErroApi("A função devolveu o envio fora do formato. Nada foi enviado.");
    try{ await subirClipes(0, r.id, r.envios, lista, String(r.bucket || "radar-videos")); }
    catch(e){ a.nova = false; a.id = String(r.id); await desenhar().catch(() => {}); throw e; }   // o editor do avulso tem o "Continuar o envio"
    const fim = await concluirEnvio(0, r.id);
    delete estadoVideo().arquivos[0]; a.nova = false; a.avulso = null; a.id = String(r.id);
    await desenhar();
    recado(`Gravação enviada: na fila do corretor. ${textoDe(fim?.robo?.mensagem)} Guarde os clipes no celular até o relatório dizer “Vídeo corrigido pronto” (se precisar regravar um bloco, os outros vão de novo) e então apague do celular e da nuvem pessoal, no mesmo dia.`);
  },
  /* Continuar o envio do avulso que não terminou: tokens novos só para os clipes que faltam (como na peça) */
  async "vaba-avulso-continuar"(){
    const v = videoDaAba();
    if(v.peca_id !== null || v.situacao !== "aguardando_envio") throw new ErroApi("Este envio não está mais esperando os arquivos.");
    const lista = clipesDe(0), partes = listaVideo(v.partes);
    if(lista.length !== partes.length || lista.some((c, i) => c.bytes !== partes[i].bytes || c.tipo !== partes[i].tipo))
      throw new ErroApi(`Escolha os MESMOS ${partes.length} arquivos do envio, na mesma ordem (o tamanho de cada um confere), ou descarte este envio e envie de novo.`);
    const r = await funcaoVideo("envio_renovar", {id:v.id});
    try{ await subirClipes(0, v.id, Array.isArray(r?.envios) ? r.envios : [], lista, String(r?.bucket || "radar-videos")); }
    catch(e){ await desenhar().catch(() => {}); throw e; }
    const fim = await concluirEnvio(0, v.id);
    delete estadoVideo().arquivos[0];
    await desenhar();
    recado(`Gravação enviada: na fila do corretor. ${textoDe(fim?.robo?.mensagem)}`);
  },
  /* Baixar o vídeo avulso pronto (só o administrador; o banco confere e registra: radar_video_baixar_avulso, pela função) */
  async "vaba-avulso-baixar"(){
    if(!ehAdmin()) throw new ErroApi("Só o administrador baixa o vídeo avulso corrigido.");
    const v = videoDaAba();
    const r = await funcaoVideo("baixar_avulso", {id:v.id});
    if(!linkVideoOk(r?.url) || (r.capa_url !== null && r.capa_url !== undefined && !linkVideoOk(r.capa_url))) throw new ErroApi("A função devolveu o link fora do formato.");
    const nome = `avulso-${hojeBrasilia()}.mp4`, capa = linkVideoOk(r.capa_url), box = $("#vaba-avulso-baixar");
    if(box) box.innerHTML = `<p><a class="btn peq" id="vaba-avulso-link" href="${h(r.url)}" download="${h(nome)}" rel="noopener noreferrer">Baixar ${h(nome)}</a>
      ${capa ? `<a class="btn peq sec" id="vaba-avulso-capa" href="${h(r.capa_url)}" download="${h(`avulso-${hojeBrasilia()}-capa.jpg`)}" rel="noopener noreferrer">Baixar a capa</a>` : ""}
      <span class="sub">O link vale 5 minutos (vencido, clique em “Baixar o vídeo corrigido” de novo). Poste onde quiser e depois apague do celular e da nuvem pessoal.</span></p>`;
    recado("Vídeo avulso liberado: baixe, poste à mão e depois apague do aparelho.");
  },
  async "vaba-avulso-apaguei"(){
    const v = videoDaAba();
    await rpc("radar_video_apaguei", {p_id:v.id});
    await desenhar(); recado("Registrado: os clipes foram apagados do celular e da nuvem pessoal.");
  },
  async "vaba-avulso-descartar"(){
    const v = videoDaAba(), envio = v.situacao === "aguardando_envio";
    if(!confirm(envio ? "Descartar o envio deste avulso? O que já subiu sai do armazenamento na limpeza seguinte."
      : "Descartar este vídeo avulso? Os arquivos saem do armazenamento na limpeza seguinte; para corrigir de novo, envie outro avulso.")) return;
    await rpc("radar_video_descartar", {p_id:v.id});
    delete estadoVideo().arquivos[0];
    for(const pt of listaVideo(v.partes)) apagarLocalVideo(`radar_tus_bruto/${v.id}/${pt.n}`);
    const a = abaVideo(); a.id = null; a.v = null;
    await desenhar(); recado(envio ? "Envio descartado." : "Gravação descartada.");
  }
};
// as que não gravam nada (só a tela): navegam sem a trava de "uma ação por vez"
const NAVEGACAO_ABA_VIDEO = ["video-aba", "vaba-filtro", "vaba-abrir", "vaba-voltar", "vaba-avulso-novo", "vaba-avulso-cancelar", "vaba-peca", "vaba-palavra", "vaba-limpar-selecao", "vaba-cortar",
  "vaba-comecar-palavra", "vaba-terminar-palavra", "vaba-marcar-de", "vaba-marcar-ate", "vaba-comecar-aqui", "vaba-terminar-aqui", "vaba-desfazer",
  "vaba-desfazer-salvo", "vaba-refazer-salvo", "vaba-desfazer-bloco", "vaba-ouvir", "vaba-passo", "vaba-capa-aqui", "vaba-capa-tirar",
  "vaba-cortar-divergencia", "vaba-cortar-fora", "vaba-descartar"];

/* ------------------------------------------------- ações (o index.html junta) */
const pecaDoVideo = () => { const f = $("form[data-form=peca]"), p = estadoVideo().pecaDados;
  if(!f || !p || Number(f.dataset.id) !== p.id) throw new ErroApi("Abra a peça de novo."); return {f, p}; };
const videoDaTela = el => { const ev = estadoVideo(), v = [ev.atual, ev.envio].find(x => x && x.id === el.dataset.id);
  if(!v) throw new ErroApi("A gravação mudou: recarregue a peça."); return v; };
const VIDEO = {
  // não gravam nada: só a tela (o que grava é feito uma ação por vez)
  navegacao:["video-nova", "video-nova-cancelar", "video-clipe-mover", "video-clipe-tirar", "video-ouvir",
    "video-teleprompter", "tele-fechar", "tele-rolar", "tele-letra", "tele-veloc", "tele-espelho", "tele-gravar",   // v0.44.0
    ...NAVEGACAO_ABA_VIDEO],
  acoes:{
    /* v0.44.0: o teleprompter (ler o roteiro em letras grandes e, se o navegador souber, gravar ali mesmo) */
    async "video-teleprompter"(el){ await abrirTeleprompter(Number(el.dataset.id)); },
    "tele-fechar"(){ fecharTeleprompter(); },
    "tele-rolar"(){ if(!TELE) return; TELE.rolando = !TELE.rolando; TELE.antes = null;
      const b = $("#tele-rolar"); if(b) b.textContent = TELE.rolando ? "Parar o texto" : "Rolar o texto";
      if(TELE.rolando) TELE.relogio = requestAnimationFrame(rolarTeleprompter); },
    "tele-letra"(el){ if(!TELE) return; TELE.letra = Math.min(96, Math.max(24, TELE.letra + 8 * Number(el.dataset.passo)));
      const r = $("#tele-rolo"); if(r) r.style.fontSize = `${TELE.letra}px`; },
    "tele-veloc"(el){ if(!TELE) return; TELE.veloc = Math.min(160, Math.max(10, TELE.veloc + 10 * Number(el.dataset.passo))); },
    "tele-espelho"(){ $("#tele-rolo")?.classList.toggle("tele-espelhado"); },
    async "tele-gravar"(){
      if(!TELE) return;
      if(TELE.gravador && TELE.gravador.state === "recording"){ await pararGravacaoTele(); return; }
      if(!TELE.fluxo){ recado("A câmera não está aberta: grave pelo celular e use o teleprompter só para ler.", true); return; }
      const tipo = tipoGravacaoTele();
      TELE.pedacos = [];
      TELE.gravador = new MediaRecorder(TELE.fluxo, tipo ? {mimeType:tipo} : undefined);
      TELE.gravador.ondataavailable = ev => { if(ev.data?.size) TELE.pedacos.push(ev.data); };
      TELE.inicioMs = Date.now();
      TELE.gravador.start(1000);
      const b = $("#tele-gravar");
      if(b){ b.textContent = "Parar e guardar"; b.classList.remove("verde"); b.classList.add("perigo"); }
      const av = $("#tele-aviso");
      if(av) av.textContent = "Gravando… Fale com o texto rolando; ao terminar, “Parar e guardar” põe a tomada na lista de clipes.";
    },
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
      if(pecaMudou(f)) throw new ErroApi(avisoPecaSuja(f));                 // v0.28.1: o aviso diz o que mudou (radar-pauta.js)
      const lista = clipesDe(p.id);
      conferirEnvio(p, lista);
      const quem = Number($("#video-quem")?.value || 0);
      if(!quem) throw new ErroApi("Escolha quem fala no vídeo.");
      const decl = [...document.querySelectorAll("#video-envio .video-declaracao")], falta = decl.filter(c => !c.checked);
      if(decl.length !== 4 || falta.length) throw new ErroApi("Marque as quatro declarações: " + falta.map(c => `“${c.dataset.texto}”`).join(", ") + ".");
      const {fala} = extrairFala(p.roteiro), gancho = !!$("#video-gancho")?.checked;
      if(fala.length < 20 || fala.split(" ").length < 10) throw new ErroApi("A fala para conferência ficou curta (menos de 10 palavras): confira o roteiro da peça.");
      // o texto do gancho também vai gravado no vídeo (de 0 a 3 s): passa pelos mesmos termos antes de qualquer arquivo sair
      const achados = [["roteiro", fala], ["no texto do gancho", gancho ? p.chamada : ""]]
        .map(([lugar, t]) => [lugar, [...new Set([...termosPublicidade(t).trava, ...termosPeca(t)])]]).filter(([, l]) => l.length);
      if(achados.length) throw new ErroApi(msgTermosPeca(achados, "gravar"));
      if(faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura (o administrador preenche).`);
      const r = await funcaoVideo("envio_iniciar", {peca:p.id, partes:lista.map((c, i) => ({n:i + 1, tipo:c.tipo, bytes:c.bytes})), fala_pessoa:quem,
        fala_roteiro:fala, cartela:linhasCartela(quem), gancho, declaracoes:decl.map(c => c.value), duracao:duracaoClipes(lista)}, 90000);
      if(!UUID_VIDEO.test(String(r?.id)) || !Array.isArray(r?.envios) || r.envios.length !== lista.length) throw new ErroApi("A função devolveu o envio fora do formato. Nada foi enviado.");
      try{ await subirClipes(p.id, r.id, r.envios, lista, String(r.bucket || "radar-videos")); }
      catch(e){ await depoisDoVideo(p.id); throw e; }
      const fim = await concluirEnvio(p.id, r.id);
      delete estadoVideo().arquivos[p.id]; estadoVideo().nova = false;
      await depoisDoVideo(p.id);
      recado(`Gravação enviada: na fila do corretor. ${textoDe(fim?.robo?.mensagem)} Guarde os clipes no celular até o relatório dizer “Vídeo corrigido pronto” (se precisar regravar um bloco, os outros vão de novo) e então apague do celular e da nuvem pessoal, no mesmo dia.`);
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
    /* A cartela que não coube só sai do erro refeita (as linhas ficam guardadas desde o envio): manda as de hoje */
    async "video-de-novo"(el){
      const v = videoDaTela(el), refazer = v.erro_codigo === "cartela_nao_cabe";
      if(refazer && faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura.`);
      await rpc("radar_video_de_novo", {p_id:v.id, p_cartela:refazer ? linhasCartela(v.fala_pessoa) : null});
      const robo = await acionarCorretor(); await depoisDoVideo(v.peca_id); recado(`Pedido de novo ao corretor. ${robo}`);
    },
    /* Com a mesma fala para conferência (mudou só o "Texto na tela", os tempos ou a tarja), o vídeo é o mesmo: o banco só registra o
       roteiro novo, e as marcas do administrador continuam valendo. Com a fala mudada, o corretor alinha e monta de novo. */
    async "video-reconferir"(el){
      const {f, p} = pecaDoVideo(), v = videoDaTela(el);
      if(pecaMudou(f)) throw new ErroApi(avisoPecaSuja(f));
      const {fala} = extrairFala(p.roteiro), igual = fala === v.fala_roteiro;
      if(!confirm(igual ? "A fala para conferência do roteiro novo é a mesma da gravação (mudou só o que não é falado): o vídeo continua o mesmo, com os ajustes de antes. Registrar o roteiro novo?"
        : "Conferir a gravação com o roteiro novo? O corretor compara de novo a fala gravada com a fala para conferência do roteiro salvo (sem transcrever de novo); “Manter este trecho”, “A transcrição errou” e a legenda editada deixam de valer.")) return;
      const r = await rpc("radar_video_reconferir", {p_id:v.id, p_fala_roteiro:fala});
      if(!r?.modo){ await depoisDoVideo(p.id); recado("Roteiro novo registrado: a fala para conferência é a mesma, e o vídeo corrigido continua valendo."); return; }
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
      // v0.33.0: as chaves do editor da aba Vídeo não estão neste quadro (o banco as guarda): compara sem elas
      const semEditor = x => { const y = {...objVideo(x)}; for(const k of CHAVES_EDITOR_VIDEO) delete y[k]; return y; };
      if(ajustesIguais(aj, semEditor(v.ajustes)) && !cartela){ recado("Nada mudou nos ajustes."); return; }
      if(cartela && faltaIdentificacao().length) throw new ErroApi(`A cartela leva a identificação legal: falta ${faltaIdentificacao().join(" e ")} em Configurações → Assinatura.`);
      if(!confirm("Montar o vídeo de novo com estes ajustes? O áudio não muda (sem transcrever de novo); leva alguns minutos.")) return;
      await rpc("radar_video_ajustar", {p_id:v.id, p_ajustes:aj, p_cartela:cartela});
      if(p.id !== estadoVideo().peca) return;
      const robo = await acionarCorretor(); estadoVideo().previa = null; await depoisDoVideo(p.id);
      recado(`Ajustes gravados: o corretor monta o vídeo de novo. ${robo}`);
    },
    /* v0.40.0: "Aceitar (quis dizer o mesmo)" — o banco tira a regravação daquela divergência e decide a situação de novo NA HORA
       (radar_video_aceitar): nada é montado de novo (a legenda já é o que foi dito) e o vídeo pode ficar pronto no mesmo clique */
    async "video-aceitar"(el){
      const {p} = pecaDoVideo(), v = videoDaTela(el), marca = String(el.dataset.marca || "");
      if(!ehAdmin()) throw new ErroApi("Só o administrador aceita uma divergência do vídeo.");
      if(!ID_DIVERGENCIA.test(marca)) throw new ErroApi("A divergência não confere com o relatório: recarregue a peça.");
      if(!confirm("Aceitar esta divergência: a pessoa quis dizer o MESMO com outras palavras? Ela deixa de pedir regravação na hora (sem montar de novo); a legenda fica com o que foi dito.")) return;
      const r = await rpc("radar_video_aceitar", {p_id:v.id, p_aceitas:[marca]});
      await depoisDoVideo(p.id);
      recado(r?.situacao === "pronto" ? "Divergência aceita: o vídeo corrigido está pronto." : "Divergência aceita; ainda há o que decidir no relatório.");
    },
    /* À mão: o vídeo aprovado, com o banco conferindo o termo de hoje e o hash aprovado (radar_video_para_baixar, pela função) */
    async "video-baixar"(){
      const f = $("form[data-form=peca]"), box = $("#video-baixar"), a = E.pauta.aberta; if(!f || !box || !a) return;
      const r = await funcaoVideo("baixar", {peca:Number(f.dataset.id), lido:f.dataset.lido});
      if(!linkVideoOk(r?.url) || (r.capa_url !== null && r.capa_url !== undefined && !linkVideoOk(r.capa_url))) throw new ErroApi("A função devolveu o link fora do formato.");
      const nome = `reel-${a.data}.mp4`, v = estadoVideo().atual, capa = linkVideoOk(r.capa_url);    // v0.33.0: + a capa escolhida na aba Vídeo
      box.innerHTML = `<p><a class="btn peq" id="video-baixar-link" href="${h(r.url)}" download="${h(nome)}" rel="noopener noreferrer">Baixar ${h(nome)}</a>
        ${capa ? `<a class="btn peq sec" id="video-baixar-capa" href="${h(r.capa_url)}" download="${h(`reel-${a.data}-capa.jpg`)}" rel="noopener noreferrer">Baixar a capa</a>` : ""}
        <span class="sub">O link vale 5 minutos (vencido, clique em “Baixar o vídeo aprovado” de novo). Poste no Instagram e no Facebook e registre o link abaixo.${capa ? " Ao postar o reel, na tela da capa, escolha adicionar da galeria e use esta imagem." : ""}</span></p>
        ${v ? `<div class="acoes" id="video-apaguei-baixado"><button class="btn peq sec" type="button" data-acao="video-apaguei-baixado" data-id="${h(v.id)}">Apaguei do celular e da nuvem pessoal (depois de postar${capa ? ": o vídeo e a capa" : ""})</button></div>` : ""}`;
      recado("Vídeo aprovado liberado: baixe, poste e depois apague do aparelho.");
    },
    "video-diagnostico"(){ return diagnosticoVideo(); },
    ...ACOES_ABA_VIDEO                                    // v0.33.0: a aba Vídeo
  },
  forms:{}
};
