-- =====================================================================
-- RADAR ARTECON — radar-reversao-v0.15.0.sql
-- DESFAZ a instalação do radar-setup-v0.15.0.sql.
-- ATENÇÃO: apaga TODAS as tabelas radar_* e os dados nelas contidos.
-- Só toca em objetos com prefixo "radar_"; nada mais no banco é alterado.
-- =====================================================================
begin;

-- estado antes (aparece na aba de resultados se executado sozinho)
select c.relname as tabela_que_sera_apagada,
       (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from public.%I', c.relname), false, true, '')))[1]::text as linhas
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'radar\_%'
order by 1;

drop view if exists public.radar_v_divulgacoes;
drop view if exists public.radar_v_ia_mes;
drop view if exists public.radar_v_painel;
drop view if exists public.radar_v_em_alta;
drop view if exists public.radar_v_assuntos;
drop view if exists public.radar_v_fila;
drop view if exists public.radar_v_saude_fontes;

-- v0.12.1: a agenda da leitura do boletim da ITC (pg_cron), se existir
do $$
begin
  if exists (select 1 from pg_namespace where nspname = 'cron') then
    perform cron.unschedule(j.jobid) from cron.job j where j.jobname like 'radar-itc%';
  end if;
exception when others then null;
end $$;

drop table if exists
  public.radar_redes_envios,
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
drop function if exists public.radar_base_legal_tipo(text);
drop function if exists public.radar_rx_termo(text);

commit;

-- EVIDÊNCIA: deve devolver zero linhas.
select 'tabela' as tipo, c.relname as nome
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname like 'radar\_%'
union all
select 'funcao', p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public' and p.proname like 'radar\_%';
