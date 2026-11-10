-- =====================================================================
-- Radar Artecon — v0.73.0: o TERMO DE USO DE IMAGEM novo (texto do dono, 10/11/2026) e o PRAZO DE 12 MESES.
-- Rode no Supabase (SQL Editor). Pode rodar de novo: reescreve o texto (versão 2) e a função.
--
-- O que muda:
--   * radar_config.termo_imagem vira a versão 2, com o texto completo fornecido pelo administrador
--     (empregador qualificado, autorização com anúncios pagos e impulsionamento, edição pelo Radar e IA,
--     participação voluntária, prazo de 12 meses ou fim do vínculo, revogação e direitos LGPD);
--   * radar_pessoa_assinar_termo passa a gravar termo_valido_ate = assinatura + 12 meses (antes: sem
--     vencimento). Quem já assinou continua sob o termo antigo (sem vencimento) até assinar de novo.
--
-- Ajustes feitos no texto colado para a assinatura NA TELA (conferir com o administrador):
--   * "EMPREGADO(A) — ." ganhou {NOME} e {CPF}, que a tela preenche na hora;
--   * as duas caixas "Autorizo/Não autorizo" viraram a frase afirmativa "Ao assinar este termo, AUTORIZO…"
--     (na tela não há caixa para marcar: assinar É autorizar; quem não autoriza não assina — sem penalidade,
--     como garante a cláusula 2);
--   * "[e-mail da Artecon]" virou artecon@artecon.cnt.br (o e-mail do Atendimento Geral do Fale Conosco);
--   * "[Local], [data]" e as linhas de assinatura manual viraram a frase da assinatura eletrônica (o sistema
--     guarda CPF, imagem da assinatura, data/hora e o texto exato como prova);
--   * erros de digitação corrigidos (n.0 → n.º, SSP,/SC → SSP/SC, "cidade de Cidade de Palhoça" etc.).
-- =====================================================================

update public.radar_config
   set valor = jsonb_build_object('versao', 2, 'texto', $termo$TERMO DE AUTORIZAÇÃO DE USO DE IMAGEM, VOZ E NOME

EMPREGADO(A) — {NOME}, inscrito(a) no CPF {CPF}.

EMPREGADORA E CONTROLADORA DOS DADOS — ARTECON ARTES CONTÁBEIS SOCIEDADE SIMPLES, pessoa jurídica de direito privado, inscrita no Cadastro Nacional de Pessoa Jurídica (CNPJ) sob o n.º 79.876.769/0001-28, com sede na Rua Livorno, n.º 15, Sala 101, CEP 88.132-274, Bairro Parque Residencial Pagani, na cidade de Palhoça, no Estado de Santa Catarina, por seu administrador, Cleiver Gonçalves, portador do documento de identidade RG n.º 3.789.248, expedido pela SSP/SC, inscrito no CPF sob o n.º 004.838.919-67 e no Conselho Regional de Contabilidade de Santa Catarina sob o n.º SC-030315/O-8, doravante denominada Artecon.

1. AUTORIZAÇÃO DE USO DE IMAGEM, VOZ E NOME

A autorização prevista nesta cláusula abrange a captação da minha imagem e voz em fotos e vídeos produzidos pela Artecon ou a seu pedido, o uso e a divulgação desses materiais e a identificação pelo meu nome profissional. Os materiais poderão ser utilizados para comunicação institucional, divulgação de conteúdo informativo e publicidade da Artecon e de seus serviços.

A divulgação poderá ocorrer no site oficial e nos perfis oficiais da Artecon no Instagram e no Facebook. Nessas duas redes sociais, a autorização também abrange anúncios pagos, conteúdos patrocinados e publicações impulsionadas, inclusive o reaproveitamento ou impulsionamento de conteúdo já publicado.

Ao assinar este termo, AUTORIZO a captação, o uso e a divulgação da minha imagem e voz e a identificação pelo meu nome profissional, para as finalidades e nos canais indicados nesta cláusula. Se eu não autorizar, basta não assinar — a recusa não gera penalidade, como garante a cláusula 2.

Estou ciente de que as fotos e os vídeos abrangidos por esta autorização poderão ser editados e tratados pela equipe da Artecon ou por prestadores contratados para essa finalidade, inclusive com o auxílio da ferramenta Radar e de ferramentas de inteligência artificial (IA). O tratamento técnico poderá incluir seleção de trechos, cortes, ajustes de áudio e imagem, redução de ruídos, inclusão e correção de legendas e conferência da gravação com o roteiro, desde que sejam preservados o sentido das minhas falas e o contexto da minha participação. Quando necessário à edição, os arquivos poderão ser disponibilizados aos prestadores responsáveis e terceiros contratados, exclusivamente para essa finalidade e conforme as instruções da Artecon.

2. PARTICIPAÇÃO VOLUNTÁRIA, GRATUIDADE E PRAZO

Minha participação nas gravações é facultativa. A recusa ou a revogação de qualquer autorização não acarretará penalidade nem prejuízo ao meu vínculo de emprego, à minha remuneração, às minhas avaliações ou às minhas oportunidades profissionais.

As autorizações concedidas neste termo são gratuitas e vigoram por 12 meses a partir da assinatura ou até o encerramento do vínculo de emprego, o que ocorrer primeiro.

3. REVOGAÇÃO, RETIRADA DOS MATERIAIS E DIREITOS DO TITULAR

Posso revogar esta autorização, total ou parcialmente, a qualquer momento e sem custo, mediante mensagem enviada ao e-mail artecon@artecon.cnt.br. Posso, inclusive, revogar apenas o uso publicitário e manter a autorização para divulgação institucional e informativa.

Encerrada ou revogada a autorização, a Artecon cessará novas publicações e republicações abrangidas pelo encerramento ou pela revogação e desativará os anúncios e impulsionamentos ativos sob seu controle. As publicações abrangidas serão removidas ou despublicadas dos canais sob controle da Artecon em até 15 dias corridos, contados do término da autorização ou do recebimento da solicitação, conforme o caso. Cópias e compartilhamentos realizados por terceiros podem permanecer fora do controle da Artecon.

Pelo mesmo canal, posso solicitar confirmação e acesso aos dados tratados, correção, informações sobre compartilhamento e eliminação dos dados tratados com base no meu consentimento, observadas as hipóteses legais de conservação, bem como exercer os demais direitos previstos no art. 18 da Lei Geral de Proteção de Dados Pessoais.

Palhoça, SC, na data da assinatura eletrônica registrada pelo sistema — que guarda, como prova, o CPF, a imagem da assinatura, a data e a hora e o texto exato deste termo.

Li e concordo com este termo, que assino eletronicamente.$termo$)
 where chave = 'termo_imagem';

-- a assinatura passa a valer por 12 meses (cláusula 2); o encerramento do vínculo continua manual
-- (desmarcar "Ativa" ou "Revogar termo" no cadastro da pessoa)
create or replace function public.radar_pessoa_assinar_termo(
  p_pessoa bigint, p_cpf text, p_assinatura text, p_aparelho text default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_pessoa public.radar_pessoas%rowtype;
  v_cfg    jsonb;
  v_cpf    text := regexp_replace(coalesce(p_cpf, ''), '\D', '', 'g');   -- só os dígitos
  v_canais text[] := array['instagram','facebook'];       -- os canais que a conferência da Pauta usa (o texto do termo cobre também o site)
  v_usos   text[] := array['equipe','orientacao','datas','captacao'];
  v_hist   bigint;
begin
  if auth.uid() is null or coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR190: só o administrador registra a assinatura do termo.' using errcode = 'P0001';
  end if;
  select * into v_pessoa from public.radar_pessoas where id = p_pessoa;
  if v_pessoa.id is null then raise exception 'RADAR190: pessoa não encontrada.' using errcode = 'P0001'; end if;
  if length(v_cpf) <> 11 then raise exception 'RADAR190: CPF inválido (precisa de 11 dígitos).' using errcode = 'P0001'; end if;
  if p_assinatura is null or p_assinatura !~ '^data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+$'
     or length(p_assinatura) < 400 or length(p_assinatura) > 400000 then
    raise exception 'RADAR190: assinatura ausente ou inválida (assine no quadro antes de confirmar).' using errcode = 'P0001';
  end if;
  select valor into v_cfg from public.radar_config where chave = 'termo_imagem';
  if v_cfg is null then raise exception 'RADAR190: o texto do termo não está configurado.' using errcode = 'P0001'; end if;

  insert into public.radar_pessoas_termos (pessoa_id, nome, cpf, termo_versao, termo_texto, canais, usos, assinatura, aparelho)
  values (p_pessoa, coalesce(v_pessoa.nome, v_pessoa.nome_na_peca, ''), v_cpf,
          coalesce((v_cfg->>'versao')::int, 1), coalesce(v_cfg->>'texto', ''), v_canais, v_usos,
          p_assinatura, left(coalesce(p_aparelho, ''), 400))
  returning id into v_hist;

  update public.radar_pessoas set
    cpf = v_cpf,
    termo_assinado_em = public.radar_pauta_hoje(),
    termo_corretor_em = public.radar_pauta_hoje(),
    termo_canais = v_canais,
    termo_usos = v_usos,
    -- v0.73.0: o termo vale por 12 meses a partir da assinatura (cláusula 2 do termo versão 2)
    termo_valido_ate = (public.radar_pauta_hoje() + interval '12 months')::date,
    termo_revogado_em = null,
    atualizado_em = now()
  where id = p_pessoa;

  return jsonb_build_object('ok', true, 'historico', v_hist, 'assinado_em', public.radar_pauta_hoje());
end $$;

select (valor->>'versao')::int as versao_do_termo, length(valor->>'texto') as tamanho_do_texto
  from public.radar_config where chave = 'termo_imagem';
