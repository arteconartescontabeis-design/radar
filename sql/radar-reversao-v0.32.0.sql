-- =====================================================================
-- RADAR ARTECON — radar-reversao-v0.32.0.sql
-- DESFAZ a instalação do radar-setup-v0.32.0.sql (e tira a agenda da Pauta, sql/radar-redes-agenda.sql, e a do corretor de vídeo,
-- sql/radar-video-agenda.sql, se existirem).
-- ATENÇÃO: apaga TODAS as tabelas radar_* e os dados nelas contidos.
-- Só toca em objetos com prefixo "radar_"; nada mais no banco é alterado.
-- v0.22.0: os ARQUIVOS do corretor de vídeo (bucket privado radar-videos: clipes, transcrições, vídeos corrigidos e quadros) NÃO saem
-- por SQL — apagar as linhas de storage.objects deixaria os arquivos órfãos no armazenamento. Apague pelo painel ANTES (Supabase →
-- Storage → radar-videos → selecione tudo → Delete; depois, no menu do bucket, Delete bucket) ou pela API do armazenamento.
-- O mesmo para o bucket privado radar-pauta (a radar-redes guarda nele as lâminas aprovadas da Pauta, com foto e nome da equipe, em
-- nomes sem dono, p-<uuid>.jpg): depois deste SQL, só as tabelas apagadas diriam de quem é cada arquivo, e a revogação de um termo
-- não teria mais como ser atendida. Se precisar dessa relação depois, guarde antes o resultado da consulta do passo 3 da revogação
-- (LEIAME, "Pessoas e termos") fora do repositório público. Desde a v0.22.0, as imagens das notícias publicadas também vão para o
-- radar-pauta (os mesmos nomes p-<uuid>.jpg; o radar_redes_envios.imagem_url diz de que envio é cada um). O bucket público radar-redes só tem
-- as imagens das notícias publicadas antes da v0.22.0 (apague pelo painel as que ainda estiverem lá).
-- Também fora do banco (este arquivo não alcança; LEIAME, "Da v0.21.0 para a v0.22.0", "Para desfazer a versão"):
--   * no repositório PRIVADO radar-video: Actions → "Radar — corretor de vídeo" → Disable workflow (ou apague
--     .github/workflows/radar-video.yml). A agenda própria dele (47 13,19 * * 1-5) roda duas vezes por dia útil e, sem o banco, cada
--     execução falharia e mandaria um e-mail, para sempre. Apague os segredos RADAR_VIDEO_ROBO_CHAVE, AZURE_FALA_CHAVE e
--     AZURE_FALA_REGIAO (e os opcionais AZURE_FALA_MODO e AZURE_FALA_ENDPOINT);
--   * no Supabase: Edge Functions → apague a função radar-video (ou, pelo menos, o segredo RADAR_VIDEO_GITHUB_TOKEN);
--   * no GitHub: revogue o token fino "Radar — acionar o corretor de vídeo" (Settings → Developer settings → Personal access tokens →
--     Fine-grained tokens → Delete): ele tem escrita em Actions no radar-video;
--   * as chaves 'radar_video_robo' e 'radar_video_agenda' ficam no Vault de propósito (para zerar, o delete do comentário do
--     sql/radar-video-agenda-reversao.sql). As chaves do Azure nunca são regeneradas: a do artecon-voz é a mesma da Agenda.
-- v0.29.0: os lembretes por e-mail. O agendamento radar-redes-agenda-lembretes sai com os da Pauta (radar-redes-agenda%) e a tabela
-- radar_lembretes com as outras. Fora do banco: no GitHub, Actions → "Radar — lembretes por e-mail" → Disable workflow (sem o banco, a
-- rodada de hora em hora só diria "nada a fazer", mas não precisa rodar) e os avisos "Radar: lembrete — …" abertos ficam no GitHub:
-- feche-os à mão (o robô nunca fecha, para não mandar mais um e-mail).
-- v0.30.0: as duas funções do aviso de possível prorrogação (radar_prorrogacoes e radar_prorrogacao_obrigacoes) saem com as outras, e
-- a lista de obrigações e o "Conferido" (radar_config) saem com a tabela. Fora do banco: o aviso "Radar: possível prorrogação na agenda
-- de obrigações", se estiver aberto no GitHub, fica aberto: feche-o à mão.
-- v0.32.0: o quadro de vencimentos e o registro das cópias saem com as tabelas; a agenda da cópia (radar-copia%) sai junto. Fora do
-- banco: Supabase → Edge Functions → apague a função radar-copia e os segredos COPIA_CLIENT_ID, COPIA_CLIENT_SECRET, COPIA_DRIVE_ID e
-- COPIA_PASTA_ID (o GRAPH_TENANT_ID é da ITC: fica); entra.microsoft.com → Registros de aplicativo → apague “Radar Artecon — cópias de
-- segurança” (corta o acesso à pasta na hora); a chave 'radar_copia_agenda' fica no Vault de propósito; os arquivos no OneDrive ficam
-- (são seus); o aviso “Radar: lembrete — …” aberto no GitHub fica: feche à mão.
-- =====================================================================
begin;

-- estado antes (aparece na aba de resultados se executado sozinho)
select c.relname as tabela_que_sera_apagada,
       (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from public.%I', c.relname), false, true, '')))[1]::text as linhas
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%'
order by 1;

drop view if exists public.radar_v_capas;
drop view if exists public.radar_v_pauta_pessoas;
drop view if exists public.radar_v_divulgacoes;
drop view if exists public.radar_v_ia_mes;
drop view if exists public.radar_v_painel;
drop view if exists public.radar_v_em_alta;
drop view if exists public.radar_v_assuntos;
drop view if exists public.radar_v_fila;
drop view if exists public.radar_v_saude_fontes;

-- v0.12.1: a agenda da leitura do boletim da ITC (pg_cron), se existir
-- v0.21.0: e a que publica a Pauta (radar-redes-agenda e a limpeza dela), ANTES de apagar as funções que ela chama; o que sobrar
-- do Radar no pg_cron é avisado. A chave 'radar_redes_agenda' fica no Vault (rodar a agenda de novo reaproveita a mesma).
-- v0.22.0: e a do corretor de vídeo (radar-video-reserva e radar-video-limpeza). As chaves 'radar_video_robo' e 'radar_video_agenda'
-- ficam no Vault (a do robô é a mesma do segredo RADAR_VIDEO_ROBO_CHAVE do repositório radar-video).
do $$
begin
  if exists (select 1 from pg_namespace where nspname = 'cron') then
    perform cron.unschedule(j.jobid) from cron.job j
     where j.jobname like 'radar-itc%' or j.jobname like 'radar-redes-agenda%' or j.jobname like 'radar-video-%'
        or j.jobname like 'radar-copia%';                                       -- v0.32.0
    if exists (select 1 from cron.job where jobname like 'radar-%') then
      raise notice 'Sobrou agendamento do Radar no pg_cron: confira cron.job';
    end if;
  end if;
exception when others then null;
end $$;

drop table if exists
  public.radar_copias,
  public.radar_vencimentos,
  public.radar_lembretes,
  public.radar_video_acessos,
  public.radar_videos,
  public.radar_site_exclusoes,
  public.radar_redes_envios,
  public.radar_pauta_pecas,
  public.radar_pessoas,
  public.radar_itc_lidos,
  public.radar_site_envios,
  public.radar_informativo_itens,
  public.radar_informativos,
  public.radar_config,
  public.radar_ia_uso,
  public.radar_publicacao_normas,
  public.radar_publicacoes,
  public.radar_conteudos,
  public.radar_evidencias,
  public.radar_assunto_capturas,
  public.radar_assuntos,
  public.radar_normas,
  public.radar_capturas_versoes,
  public.radar_capturas,
  public.radar_execucoes,
  public.radar_fontes,
  public.radar_categorias,
  public.radar_perfis,
  public.radar_auditoria,
  public.radar_instalacoes,
  public.radar_imagens,
  public.radar_divulgacoes
  cascade;

drop function if exists public.radar_papel();
drop function if exists public.radar_normalizar(text);
drop function if exists public.radar_trecho_confere(text, text);
drop function if exists public.radar_fn_atualizado_em();
drop function if exists public.radar_fn_auditar();
drop function if exists public.radar_fn_auditoria_imutavel();
drop function if exists public.radar_fn_captura_versionar();
drop function if exists public.radar_fn_captura_reconferir();
drop function if exists public.radar_fn_evidencia_conferir();
drop function if exists public.radar_fn_conteudo_aprovacao();
drop function if exists public.radar_fn_publicacao_portao();
drop function if exists public.radar_fn_execucao_saude();
drop function if exists public.radar_fn_sinalizar();
drop function if exists public.radar_sinalizar_assunto(bigint);
drop function if exists public.radar_pendencia_assunto(bigint);
drop function if exists public.radar_hash_texto(text);
drop function if exists public.radar_manter_usuario(uuid, uuid);
drop function if exists public.radar_fn_publicacao_efeitos();
drop function if exists public.radar_ignorar_capturas(bigint[]);
drop function if exists public.radar_gravar_avaliacao_ia(jsonb);
drop function if exists public.radar_limpar_imagens_sem_uso(int);
drop function if exists public.radar_arquivar_fila(int);
drop function if exists public.radar_separar_captura(bigint, bigint);
drop function if exists public.radar_separar_repeticao(bigint);
drop function if exists public.radar_autorizar_copia(bigint, text, timestamptz);
drop function if exists public.radar_autorizar_todos(bigint, text, timestamptz, text, text, text);
drop function if exists public.radar_autorizar_todos(bigint, text, timestamptz, text, text, text, boolean);
drop function if exists public.radar_fn_site_envio_redes();
drop function if exists public.radar_rede_marcar_excluida(bigint, text);
drop function if exists public.radar_pedir_exclusao_site(bigint);
drop function if exists public.radar_cancelar_exclusao_site(bigint);
drop function if exists public.radar_site_exclusao_concluir(bigint, boolean, text);
drop function if exists public.radar_avisos_acrescimo(jsonb, jsonb);
drop function if exists public.radar_fn_conteudo_fonte() cascade;
drop function if exists public.radar_abrir_assunto(bigint, boolean);
drop function if exists public.radar_admin_usuarios();
drop function if exists public.radar_slug(text);
drop function if exists public.radar_fn_ultimo_admin();
drop function if exists public.radar_fn_ia_uso();
drop function if exists public.radar_fn_informativo_item();
drop function if exists public.radar_fn_informativo();
drop function if exists public.radar_fn_imagem();
drop function if exists public.radar_fn_captura_relevancia();
drop function if exists public.radar_fn_config_relevancia();
drop function if exists public.radar_reavaliar_capturas();
drop function if exists public.radar_fn_imagem_sem_uso() cascade;
drop function if exists public.radar_avaliar_relevancia(text, text, text);
drop function if exists public.radar_relevancia_com_ia(text, int, jsonb, smallint);
drop function if exists public.radar_relevancia_idade(text, jsonb, date, timestamptz);
drop function if exists public.radar_envelhecer_fila();
drop function if exists public.radar_fn_captura_origem() cascade;
drop function if exists public.radar_fn_captura_promover() cascade;
drop function if exists public.radar_promover_oficial(bigint, bigint);
drop function if exists public.radar_relevancia_com_ia(text, jsonb, smallint);
drop function if exists public.radar_sem_acento(text);
drop function if exists public.radar_fn_divulgacao();
drop function if exists public.radar_fundamentacao(bigint);
drop function if exists public.radar_fn_fonte_formato();
drop function if exists public.radar_url_base(text);
drop function if exists public.radar_incluir_texto_oficial(bigint, bigint, text, text, date, text);
drop function if exists public.radar_fn_divulgacao_efeitos();
drop function if exists public.radar_registrar_uso_ia(text, text, int, int, bigint);
drop function if exists public.radar_registrar_evidencia_ia(bigint, bigint, text, text);
drop function if exists public.radar_autorizar_site(bigint, text, timestamptz);
drop function if exists public.radar_cancelar_site(bigint);
drop function if exists public.radar_fn_conteudo_envio();
drop function if exists public.radar_tirar_aviso_fonte(text);
drop function if exists public.radar_marcas_verificar(text);
drop function if exists public.radar_autorizar_rede(bigint, text, text, text, timestamptz);
drop function if exists public.radar_autorizar_rede(bigint, text, text, text, timestamptz, boolean);
drop function if exists public.radar_rede_cancelada_no_envio(bigint, text);
drop function if exists public.radar_url_host(text);
drop function if exists public.radar_site_host();
drop function if exists public.radar_copia_paga(text[], text[]);
drop function if exists public.radar_copia_paga_assunto(bigint, text[]);
drop function if exists public.radar_copia_paga_trechos(bigint, text[]);
drop function if exists public.radar_copia_paga_livres(bigint);
drop function if exists public.radar_copia_paga_base();
drop function if exists public.radar_copia_paga_ato_oficial(text);
drop function if exists public.radar_crc_padrao(text);
drop function if exists public.radar_dispensar_rede(bigint, text);
drop function if exists public.radar_cancelar_rede(bigint);
drop function if exists public.radar_rede_iniciar(bigint);
drop function if exists public.radar_rede_concluir(bigint, boolean, text, text, text, text);
drop function if exists public.radar_receber_email(text, jsonb);
drop function if exists public.radar_data_valida(text);
drop function if exists public.radar_itc_ja_lidos(text[]);
drop function if exists public.radar_itc_marcar_lido(text, text, timestamptz, int, int);
drop function if exists public.radar_itc_conferir_agenda(text);
drop function if exists public.radar_itc_registrar_falha(text);
drop function if exists public.radar_liberar_sem_fundamentacao(bigint, text);
drop function if exists public.radar_converter_analise(bigint);
drop function if exists public.radar_fn_assunto_liberacao() cascade;
drop function if exists public.radar_fn_captura_base_legal();
drop function if exists public.radar_recalcular_base_legal();
drop function if exists public.radar_base_legal(text, text, text);
drop function if exists public.radar_base_legal_codigos_rx();
drop function if exists public.radar_base_legal_rx();
drop function if exists public.radar_base_legal_lista_rx();
drop function if exists public.radar_base_legal_ano_rx();
drop function if exists public.radar_base_legal_ano(text);
drop function if exists public.radar_base_legal_apelido_rx();
drop function if exists public.radar_base_legal_nomes_rx();
drop function if exists public.radar_base_legal_parcial(jsonb, jsonb);
drop function if exists public.radar_base_legal_orgao(text);
drop function if exists public.radar_base_legal_orgao_exibir(text);
drop function if exists public.radar_base_legal_tipo(text);
drop function if exists public.radar_base_legal_valida(text[], text);
drop function if exists public.radar_base_legal_preparar(text);
drop function if exists public.radar_base_legal_chave(text);
drop function if exists public.radar_rx_termo(text);
-- v0.21.0: Pauta (peças das redes) e publicação agendada
drop function if exists public.radar_pauta_hoje();
drop function if exists public.radar_pauta_normalizar(text);
drop function if exists public.radar_pauta_sem_acento(text);
drop function if exists public.radar_pauta_rx_nome(text);
drop function if exists public.radar_pauta_janela();
drop function if exists public.radar_pauta_canais(text, text);
drop function if exists public.radar_pauta_identificacao_falta(text);
drop function if exists public.radar_pauta_numeros(text);
drop function if exists public.radar_pauta_numeros_escritos(text);
drop function if exists public.radar_pauta_numeros_fora(text, text);
drop function if exists public.radar_pauta_copia_paga(text[]);
drop function if exists public.radar_pauta_copia_paga_ia(text[]);
drop function if exists public.radar_pauta_termo_ok(bigint, text, text, date);
drop function if exists public.radar_pauta_problemas(bigint, text[], date);
drop function if exists public.radar_fn_pauta_peca();
drop function if exists public.radar_fn_pessoa_apagar();
drop function if exists public.radar_pauta_importar(jsonb);
-- v0.28.0: "+ Nova peça" e a conferência da linha do calendário que ela divide com a importação
drop function if exists public.radar_pauta_criar(jsonb);
drop function if exists public.radar_pauta_linha_invalida(jsonb);
drop function if exists public.radar_pauta_hora_padrao();
drop function if exists public.radar_pauta_conferir(bigint, text[]);
drop function if exists public.radar_pauta_marcar_pronta(bigint, timestamptz);
drop function if exists public.radar_pauta_aprovar(bigint, timestamptz, text[], text, bigint[], text, text[]);
drop function if exists public.radar_pauta_aprovar(bigint, timestamptz, text[], text, bigint[], text, text[], text);
drop function if exists public.radar_pauta_desaprovar(bigint, boolean);
drop function if exists public.radar_pauta_publicar_agora(bigint, boolean);
drop function if exists public.radar_pauta_pode_copiar(bigint, timestamptz, text);
drop function if exists public.radar_pauta_registrar_manual(bigint, text, text, date);
drop function if exists public.radar_agenda_situacao();
drop function if exists public.radar_pauta_pode_sair(bigint);
drop function if exists public.radar_agenda_vencidas(int);
drop function if exists public.radar_pauta_iniciar(bigint);
drop function if exists public.radar_redes_conferir_agenda(text);
-- v0.22.0: corretor de vídeo dos reels
drop function if exists public.radar_video_cfg_num(text, numeric, numeric, numeric);
drop function if exists public.radar_video_cfg_texto(text);
drop function if exists public.radar_video_config();
drop function if exists public.radar_video_segundos_mes();
drop function if exists public.radar_video_limite_s();
drop function if exists public.radar_video_fala_no_roteiro(text, text);
drop function if exists public.radar_video_pessoa_falta(bigint, bigint);
drop function if exists public.radar_video_pessoas_falta(bigint, bigint, bigint[]);
drop function if exists public.radar_video_pessoas_falta(bigint, bigint);
drop function if exists public.radar_video_cartela_falta(text[], bigint);
drop function if exists public.radar_video_ajustes_falta(jsonb);
drop function if exists public.radar_video_pendencia(bigint);
drop function if exists public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[], numeric);
drop function if exists public.radar_video_criar(bigint, jsonb, bigint, text, text[], boolean, text[]);
drop function if exists public.radar_video_cota();
drop function if exists public.radar_video_para_envio(uuid);
drop function if exists public.radar_video_enviado(uuid);
drop function if exists public.radar_video_ajustar(uuid, jsonb, text[]);
drop function if exists public.radar_video_reconferir(uuid, text);
drop function if exists public.radar_video_de_novo(uuid, text[]);
drop function if exists public.radar_video_de_novo(uuid);
drop function if exists public.radar_video_descartar(uuid);
drop function if exists public.radar_video_apaguei(uuid);
drop function if exists public.radar_video_apaguei_baixado(uuid);
drop function if exists public.radar_video_para_previa(uuid);
drop function if exists public.radar_video_para_baixar(bigint, timestamptz);
drop function if exists public.radar_pauta_pecas_da_pessoa(bigint);
drop function if exists public.radar_video_resumo();
drop function if exists public.radar_video_conferir_robo(text);
drop function if exists public.radar_video_conferir_agenda(text);
drop function if exists public.radar_video_ha_fila(int);
drop function if exists public.radar_video_reserva();
drop function if exists public.radar_video_pegar();
drop function if exists public.radar_video_em_curso(uuid, int);
drop function if exists public.radar_video_registrar_audio(uuid, int, numeric, boolean);
drop function if exists public.radar_video_parcial(uuid, int, jsonb);
drop function if exists public.radar_video_concluir(uuid, int, text, jsonb, text, bigint, numeric);
drop function if exists public.radar_video_falhar(uuid, int, text);
drop function if exists public.radar_video_limpeza();
drop function if exists public.radar_video_limpo(uuid, text[]);
-- as que recebem ou devolvem a linha de radar_videos já saíram com a tabela (cascade); ficam aqui para a reversão rodar de novo
drop function if exists public.radar_video_travar(uuid);
drop function if exists public.radar_video_refazer(public.radar_videos);
drop function if exists public.radar_video_do_robo(uuid, int, boolean);
-- v0.24.0: Conferência das Diretrizes (as que recebem a linha de radar_conteudos já saíram com a tabela; ficam aqui para rodar de novo)
drop function if exists public.radar_registrar_conferencia(bigint, timestamptz, jsonb, text);
drop function if exists public.radar_assumir_conferencia(bigint, text, timestamptz);
drop function if exists public.radar_cita_norma(text);
drop function if exists public.radar_tem_fundamentacao(text);
drop function if exists public.radar_conferencia_versao(public.radar_conteudos);
drop function if exists public.radar_conferencia_codigo(public.radar_conteudos);
drop function if exists public.radar_conferencia_pendente(public.radar_conteudos);
-- v0.24.0 (etapa 5): a revisão editorial
drop function if exists public.radar_registrar_revisao_editorial(bigint, timestamptz, jsonb);
drop function if exists public.radar_texto_versao(public.radar_conteudos);
-- v0.29.0: os lembretes por e-mail
drop function if exists public.radar_lembretes_cfg();
drop function if exists public.radar_lembretes_madura(text, text, jsonb, timestamptz, jsonb, timestamptz);
drop function if exists public.radar_lembretes_observar(timestamptz);
drop function if exists public.radar_lembretes_devidos(timestamptz);
drop function if exists public.radar_lembretes_acionar();
drop function if exists public.radar_lembretes_ha_envio();
drop function if exists public.radar_lembretes_lote_em(timestamptz);
drop function if exists public.radar_lembretes_lote();
drop function if exists public.radar_lembretes_enviado_em(uuid, int, bigint[], timestamptz);
drop function if exists public.radar_lembretes_enviado(uuid, int, bigint[]);
drop function if exists public.radar_lembretes_situacao();
-- v0.19.1 (opcional): a conferência da chave da radar-concorrentes (sql/radar-concorrentes.sql), se foi instalada
drop function if exists public.radar_concorrentes_conferir(text);
-- v0.30.0: o aviso de possível prorrogação na agenda de obrigações
drop function if exists public.radar_prorrogacoes(int);
drop function if exists public.radar_prorrogacao_obrigacoes(text, jsonb);
-- v0.32.0: o quadro de vencimentos e a cópia mensal no OneDrive
drop function if exists public.radar_vencimento_parece_segredo(text);
drop function if exists public.radar_fn_vencimento();
drop function if exists public.radar_vencimentos_conhecidos();
drop function if exists public.radar_vencimentos_renovei(bigint, date);
drop function if exists public.radar_copia_conferir_agenda(text);
drop function if exists public.radar_copias_pode(text);
drop function if exists public.radar_copias_comecar(text);
drop function if exists public.radar_copias_terminar(text, bigint, boolean, bigint, bigint, bigint, int, text, text);
drop function if exists public.radar_copias_exportar(text, text, text, int);
drop function if exists public.radar_copias_falta_mes();
drop function if exists public.radar_copias_situacao();

commit;

-- EVIDÊNCIA: deve devolver zero linhas.
select 'tabela' as tipo, c.relname as nome
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname like 'radar\_%'
union all
select 'funcao', p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname like 'radar\_%';
