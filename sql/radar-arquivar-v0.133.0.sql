-- Radar Artecon — migração v0.133.0: arquivar (ocultar da lista, reversível, só o administrador)
--
-- Acrescenta a coluna arquivado_em (nulo = ativo; com data = arquivado) em radar_capturas, radar_normas,
-- radar_assuntos e radar_conteudos, e a função radar_arquivar(tabela, id, arquivar) que o administrador usa para
-- arquivar e desarquivar. NADA é apagado — o item só sai da lista normal e volta pelo filtro "Arquivados".
-- Pode rodar quantas vezes quiser (idempotente). O mesmo conteúdo está no sql/radar-setup-v0.50.0.sql.

alter table public.radar_capturas  add column if not exists arquivado_em timestamptz;
alter table public.radar_normas     add column if not exists arquivado_em timestamptz;
alter table public.radar_assuntos   add column if not exists arquivado_em timestamptz;
alter table public.radar_conteudos  add column if not exists arquivado_em timestamptz;

-- Só o administrador arquiva/desarquiva; a tabela precisa ser uma das quatro da lista branca (sem injeção: %I + USING).
create or replace function public.radar_arquivar(p_tabela text, p_id bigint, p_arquivar boolean default true)
returns void language plpgsql security definer set search_path = public as $$
begin
  if coalesce(public.radar_papel(), '') <> 'admin' then
    raise exception 'RADAR385: só o administrador arquiva ou desarquiva' using errcode = '42501';
  end if;
  if p_tabela not in ('radar_capturas', 'radar_normas', 'radar_assuntos', 'radar_conteudos') then
    raise exception 'RADAR385: essa lista não pode ser arquivada' using errcode = '22023';
  end if;
  execute format('update public.%I set arquivado_em = $1 where id = $2', p_tabela)
    using (case when p_arquivar then now() end), p_id;
end $$;
revoke all on function public.radar_arquivar(text, bigint, boolean) from public, anon, authenticated, service_role;
grant execute on function public.radar_arquivar(text, bigint, boolean) to authenticated;
