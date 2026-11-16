-- sql/radar-correcoes-v0.108.0.sql — Comercial na Pauta (tipo 'comercial', venda de serviços)
-- Idempotente; pode rodar de novo. Acrescenta o tipo 'comercial' ao CHECK e às duas funções do tipo.
begin;

alter table public.radar_pauta_pecas drop constraint if exists radar_pauta_pecas_tipo_check;
alter table public.radar_pauta_pecas add constraint radar_pauta_pecas_tipo_check
  check (tipo in ('noticia','reel','quem_cuida','agenda','bastidor','educativo','captacao','data_equipe','sem_post','comercial'));

create or replace function public.radar_pauta_termo_ok(p_pessoa bigint, p_tipo text, p_canal text, p_data date) returns text
language plpgsql stable set search_path = public as $$
declare
  v     public.radar_pessoas%rowtype;
  v_uso text := case when p_tipo in ('quem_cuida','bastidor') then 'equipe'
                     when p_tipo in ('reel','educativo','agenda','noticia') then 'orientacao'
                     when p_tipo = 'data_equipe' then 'datas'
                     when p_tipo in ('captacao','comercial') then 'captacao' end;   -- comercial (venda de serviços) usa o termo de captação
begin
  select * into v from public.radar_pessoas where id = p_pessoa;
  if v.id is null then return 'pessoa não cadastrada'; end if;
  if not v.ativo then return 'pessoa inativa'; end if;
  -- v0.46.0: todos assinam (inclusive sócios): a dispensa por "socio" foi removida
  if v.termo_assinado_em is null then return 'sem termo assinado'; end if;
  if p_data is null or v.termo_assinado_em > p_data then return 'termo assinado depois desta data'; end if;
  if v.termo_revogado_em is not null and v.termo_revogado_em <= p_data then return 'termo revogado'; end if;
  if v.termo_valido_ate is not null and v.termo_valido_ate < p_data then return 'termo vencido'; end if;
  if p_canal is null or not p_canal = any(v.termo_canais) then return 'canal não autorizado no termo'; end if;
  if v_uso is null or not v_uso = any(v.termo_usos) then return 'finalidade não autorizada no termo'; end if;
  return null;
end $$;

create or replace function public.radar_pauta_linha_invalida(x jsonb) returns text
language plpgsql stable set search_path = public as $$
begin
  return case
    when jsonb_typeof(x) is distinct from 'object' then 'linha'
    when coalesce(x->>'data', '') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' or not public.radar_data_valida(x->>'data') then 'data'
    when (x->>'data')::date not between date '2020-01-01' and date '2100-12-31' then 'data'
    when coalesce(x->>'tipo', '') not in ('noticia','reel','quem_cuida','agenda','bastidor','educativo','captacao','data_equipe','sem_post','comercial') then 'tipo'
    when coalesce(x->>'formato', '') not in ('imagem','foto','carrossel','carrossel_fotos','reel','story','nenhum') then 'formato'
    when jsonb_typeof(x->'assunto') not in ('string','null') or length(coalesce(x->>'assunto', '')) > 1000 then 'assunto'
    when jsonb_typeof(x->'quem_aparece') not in ('string','null') or length(coalesce(x->>'quem_aparece', '')) > 300 then 'quem_aparece'
    when jsonb_typeof(x->'objetivo') not in ('string','null') or length(coalesce(x->>'objetivo', '')) > 200 then 'objetivo'
    when jsonb_typeof(x->'observacao') not in ('string','null') or length(coalesce(x->>'observacao', '')) > 1000 then 'observacao'
  end;
end $$;

commit;
