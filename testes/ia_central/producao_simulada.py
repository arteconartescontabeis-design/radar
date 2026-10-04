"""Monta, num PostgreSQL local, uma réplica do estado de produção da IA Central (v1.0.2):
v1.0.0 original + as diferenças lidas da própria produção (CSV de 03/10/2026)."""
import csv, json, subprocess, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PSQL = ["psql", "-h", "/tmp", "-p", "5544", "-U", "postgres", "-q", "-v", "ON_ERROR_STOP=1"]

STUBS = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticator') then create role authenticator login noinherit password 'x'; end if;
end $$;
grant anon, authenticated, service_role to authenticator;
create schema if not exists auth; create schema if not exists core; create schema if not exists extensions;
create schema if not exists vault; create schema if not exists cron; create schema if not exists net;
create or replace function auth.jwt() returns jsonb language sql stable as
  $$ select nullif(current_setting('request.jwt.claims', true), '')::jsonb $$;
grant usage on schema auth to anon, authenticated, service_role;
create table if not exists vault.secrets (id serial primary key, name text unique, secret text, description text);
create or replace view vault.decrypted_secrets as select name, secret as decrypted_secret from vault.secrets;
create or replace function vault.create_secret(s text, n text, d text default null) returns int language sql as
  $$ insert into vault.secrets (secret, name, description) values (s, n, d) returning id $$;
create table if not exists cron.job (jobname text primary key, schedule text, command text);
create or replace function cron.schedule(j text, s text, c text) returns int language sql as
  $$ insert into cron.job values (j, s, c) on conflict (jobname) do update set schedule = excluded.schedule, command = excluded.command returning 1 $$;
create or replace function cron.unschedule(j text) returns boolean language sql as $$ delete from cron.job where jobname = j returning true $$;
"""

def psql(banco, sql=None, arquivo=None):
    cmd = PSQL + [banco] + (["-f", str(arquivo)] if arquivo else ["-c", sql])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-3000:])
    return r.stdout

def linhas_csv():
    with open(RAIZ / "producao-2026-10-03.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))

def montar(banco="ia_teste"):
    psql("postgres", f"drop database if exists {banco} with (force)")
    psql("postgres", f"create database {banco}")
    psql(banco, STUBS)
    psql(banco, arquivo=RAIZ / "ia_central_v1.0.0-referencia.sql")
    # v1.0.1 e v1.0.2, reconstruídas do estado real
    sql = ["alter table core.ia_config add column if not exists modo_recarga text not null default 'manual';",
           "alter table core.ia_config add column if not exists recarga_auto_gatilho numeric;",
           "alter table core.ia_config add column if not exists recarga_auto_valor numeric;"]
    for l in linhas_csv():
        if l["tipo"] == "funcao":
            sql.append(l["definicao"].rstrip() + ";")
        elif l["tipo"] == "app":
            a = json.loads(l["definicao"])
            sql.append("insert into core.ia_apps (app, nome, limite_mensal_usd, limite_diario_usd, modelos, max_tokens) values "
                       f"('{a['app']}', '{a['nome']}', {a['limite_mensal_usd']}, {a['limite_diario_usd']}, "
                       f"array[{','.join(repr(m) for m in a['modelos'])}], {a['max_tokens']}) on conflict (app) do nothing;")
    sql.append("grant execute on function core.ia_salvar_recarga(text, numeric, numeric) to authenticated;")
    sql.append("revoke all on function core.ia_salvar_recarga(text, numeric, numeric) from public, anon;")
    (RAIZ / "_v102.sql").write_text("\n".join(sql), encoding="utf-8")
    psql(banco, arquivo=RAIZ / "_v102.sql")
    return banco

if __name__ == "__main__":
    print(montar(*sys.argv[1:]))
