"""Infraestrutura dos testes: banco PostgreSQL de teste com o setup real aplicado."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "robo"))

PG = {"host": os.environ.get("RADAR_PGHOST", "/tmp"), "port": os.environ.get("RADAR_PGPORT", "5544"),
      "user": os.environ.get("RADAR_PGUSER", "postgres")}
BANCO = "radar_teste"
SETUP = RAIZ / "sql" / "radar-setup-v0.40.0.sql"
REVERSAO = RAIZ / "sql" / "radar-reversao-v0.40.0.sql"

ADMIN = "00000000-0000-0000-0000-00000000000a"
EDITOR = "00000000-0000-0000-0000-00000000000e"
LEITOR = "00000000-0000-0000-0000-000000000001"
SEM_PERFIL = "00000000-0000-0000-0000-000000000009"


def psql(arquivo: Path, banco: str = BANCO) -> subprocess.CompletedProcess:
    return subprocess.run(["psql", "-h", PG["host"], "-p", PG["port"], "-U", PG["user"], "-d", banco,
                           "-v", "ON_ERROR_STOP=1", "-q", "-A", "-t", "-f", str(arquivo)],
                          capture_output=True, text=True)


def conectar(banco: str = BANCO, autocommit: bool = True) -> psycopg.Connection:
    return psycopg.connect(host=PG["host"], port=PG["port"], user=PG["user"], dbname=banco, autocommit=autocommit)


@pytest.fixture(scope="session")
def banco_pronto():
    with conectar("postgres") as c:
        c.execute(f"drop database if exists {BANCO} with (force)")
        c.execute(f"create database {BANCO}")
    r = psql(RAIZ / "testes" / "supabase_simulado.sql")
    assert r.returncode == 0, r.stderr
    r = psql(SETUP)
    assert r.returncode == 0, r.stderr
    with conectar() as c:
        c.execute(CONFERENCIA_AUTOMATICA)
        for uid, nome, papel in [(ADMIN, "Admin", "admin"), (EDITOR, "Editora", "editor"), (LEITOR, "Leitor", "leitor")]:
            c.execute("insert into auth.users (id, email) values (%s, %s) on conflict do nothing", (uid, nome))
            c.execute("insert into radar_perfis (user_id, nome, papel) values (%s, %s, %s) on conflict do nothing",
                      (uid, nome, papel))
        c.execute("insert into auth.users (id, email) values (%s, 'x') on conflict do nothing", (SEM_PERFIL,))
    yield BANCO


# v0.24.0: a aprovação de um conteúdo pede a Conferência das Diretrizes da versão do texto (a lista da IA ou o "Revisei e assumo"). Nos
# testes que não são dela, um gatilho SÓ DOS TESTES (esquema "teste", fora do setup) grava a conferência completa a cada gravação do
# conteúdo, depois dos gatilhos do Radar: o que eles testam (aprovar, publicar, o Informativo Mensal…) segue como antes. Os testes da
# conferência desligam isso (fixture conferencia_de_verdade) e conferem o caminho de verdade: a função radar-ia, as funções do banco e a tela.
CONFERENCIA_AUTOMATICA = """
create schema if not exists teste;
create table if not exists teste.ajustes (conferencia_automatica boolean not null default true);
insert into teste.ajustes select true where not exists (select 1 from teste.ajustes);
create or replace function teste.conferencia_automatica() returns trigger language plpgsql security definer set search_path = public as $$
begin
  if (select a.conferencia_automatica from teste.ajustes a limit 1) then
    new.conferencia := jsonb_build_object('versao', public.radar_conferencia_versao(new), 'em', now(), 'teste', true,
      'itens', (select jsonb_agg(jsonb_build_object('item', n, 'situacao', 'atende', 'motivo', 'Conferido (teste).') order by n)
                  from generate_series(1, 10) n))
      -- v0.24.0 (etapa 5): a revisão editorial gravada pelo Radar (na mesma coluna) fica
      || case when new.conferencia ? 'editorial' then jsonb_build_object('editorial', new.conferencia->'editorial') else '{}'::jsonb end;
  end if;
  return new;
end $$;
drop trigger if exists radar_tg_zz_teste_conferencia on public.radar_conteudos;
create trigger radar_tg_zz_teste_conferencia before insert or update on public.radar_conteudos
  for each row execute function teste.conferencia_automatica();
"""


@pytest.fixture()
def conferencia_de_verdade(banco_pronto):
    """Desliga a conferência automática dos testes (CONFERENCIA_AUTOMATICA) durante o teste: vale a de verdade."""
    with conectar() as c:
        c.execute("update teste.ajustes set conferencia_automatica = false")
    yield
    with conectar() as c:
        c.execute("update teste.ajustes set conferencia_automatica = true")


@pytest.fixture()
def db(banco_pronto):
    """Conexão de superusuário (equivale ao SQL Editor do Supabase)."""
    with conectar() as c:
        yield c


@contextmanager
def como(papel: str, uid: str | None = None):
    """Abre uma conexão agindo como anon / authenticated / service_role, como a API faz."""
    c = conectar(autocommit=True)
    try:
        claims = {"role": papel}
        if uid:
            claims["sub"] = uid
        c.execute("select set_config('request.jwt.claims', %s, false)", (json.dumps(claims),))
        c.execute(f"set role {papel}")
        yield c
    finally:
        c.close()



FONTES_NOVAS_SLUGS = "('dou-destaques','econet-blog','portalcontabilsc-noticias','dou-inlabs','itc-email')"

# v0.21.0: o Postgres dos testes não tem pg_cron, pg_net nem Vault. Esquemas de mentira, com o que os arquivos da agenda usam:
# cron.job, cron.job_run_details, cron.schedule (o mesmo nome troca o agendamento, como no pg_cron) e cron.unschedule; net.http_post
# grava cada pedido em net.pedidos (o pg_net de verdade manda depois do commit); o Vault guarda o segredo em texto (só nos testes).
CRON_SIMULADO = """
create schema cron;
create table cron.job (jobid bigserial primary key, schedule text not null, command text not null, nodename text not null default 'localhost',
                       nodeport int not null default 5432, database text not null default current_database(),
                       username text not null default current_user, active boolean not null default true, jobname text);
create table cron.job_run_details (jobid bigint, runid bigserial primary key, job_pid int, database text, username text, command text,
                                   status text, return_message text, start_time timestamptz, end_time timestamptz);
create function cron.schedule(p_nome text, p_quando text, p_comando text) returns bigint language plpgsql as $$
declare v bigint;
begin
  update cron.job j set schedule = p_quando, command = p_comando where j.jobname = p_nome returning j.jobid into v;
  if v is null then
    insert into cron.job (jobname, schedule, command) values (p_nome, p_quando, p_comando) returning jobid into v;
  end if;
  return v;
end $$;
create function cron.unschedule(p_job bigint) returns boolean language sql as $$
  with d as (delete from cron.job where jobid = p_job returning 1) select exists (select 1 from d)
$$;
"""
NET_SIMULADO = """
create schema net;
create table net.pedidos (id bigserial primary key, url text, body jsonb, headers jsonb, timeout_milliseconds int);
create function net.http_post(url text, body jsonb default '{}'::jsonb, params jsonb default '{}'::jsonb,
                              headers jsonb default '{"Content-Type": "application/json"}'::jsonb, timeout_milliseconds int default 5000)
returns bigint language sql as $$
  insert into net.pedidos (url, body, headers, timeout_milliseconds) values (url, body, headers, timeout_milliseconds) returning id
$$;
"""
VAULT_SIMULADO = """
create schema vault;
create table vault.secrets (id uuid primary key default gen_random_uuid(), name text unique, description text, secret text not null);
create function vault.create_secret(new_secret text, new_name text default null, new_description text default '') returns uuid
language sql as $$ insert into vault.secrets (secret, name, description) values (new_secret, new_name, new_description) returning id $$;
create view vault.decrypted_secrets as select id, name, description, secret, secret as decrypted_secret from vault.secrets;
"""


def carregar_fontes_novas(db, request):
    """Cadastra as fontes de sql/radar-fontes-novas-2026-10.sql (entre elas o boletim pago, itc-email) e as tira no fim do teste,
    como a fixture da ITC: o resultado dos outros testes não depende da ordem."""
    assert psql(RAIZ / "sql" / "radar-fontes-novas-2026-10.sql").returncode == 0

    def tirar():
        caps = f"select c.id from radar_capturas c join radar_fontes f on f.id = c.fonte_id where f.slug in {FONTES_NOVAS_SLUGS}"
        for tabela in ("radar_evidencias", "radar_assunto_capturas", "radar_capturas_versoes"):
            db.execute(f"delete from {tabela} where captura_id in ({caps})")
        db.execute(f"delete from radar_capturas where id in ({caps})")
        db.execute(f"delete from radar_fontes where slug in {FONTES_NOVAS_SLUGS}")
    request.addfinalizer(tirar)


@pytest.fixture()
def limpo(db):
    """Zera os dados operacionais entre testes (mantém fontes, categorias e perfis)."""
    db.execute("alter table radar_auditoria disable trigger user")
    # v0.21.0: a Pauta e as pessoas não são alcançadas pelo cascade de radar_conteudos; v0.22.0: nem os vídeos dos reels; v0.29.0: nem
    # os lembretes
    db.execute("""truncate radar_conteudos, radar_evidencias,
                  radar_assunto_capturas, radar_assuntos, radar_normas, radar_capturas_versoes,
                  radar_capturas, radar_execucoes, radar_auditoria, radar_ia_uso, radar_informativo_itens,
                  radar_informativos, radar_imagens, radar_divulgacoes, radar_pauta_pecas, radar_pessoas,
                  radar_videos, radar_video_acessos, radar_lembretes restart identity cascade""")
    db.execute("update radar_fontes set ultimo_sucesso_em = null, ultima_falha_em = null, "
               "falhas_consecutivas = 0, ultimo_erro = null")
    db.execute("delete from radar_fontes where slug like 'teste-%'")
    # v0.11.0: as datas dos testes são fixas (setembro/outubro de 2026); a regra "notícia com mais de 5 dias é baixa"
    # fica desligada aqui e é ligada só no teste dela
    db.execute("""update radar_config set valor = valor || '{"dias_baixa": 0}'::jsonb
                  where chave = 'relevancia' and valor->'dias_baixa' is distinct from '0'::jsonb""")
    # v0.30.0: o “Conferido” do aviso de prorrogação de um teste não vale no outro (os números das capturas recomeçam do 1)
    db.execute("delete from radar_config where chave = 'prorrogacoes_conferidas'")
    db.execute("truncate radar_auditoria restart identity")
    db.execute("alter table radar_auditoria enable trigger user")
    return db


@pytest.fixture()
def lembretes_abertos(limpo):
    """v0.29.0: Configurações → Lembretes por e-mail com o horário aberto (os quatro tipos a qualquer hora do dia: os testes que usam o
    relógio de verdade não dependem da hora em que rodam). No fim, a configuração volta ao que era."""
    antes = limpo.execute("select valor from radar_config where chave = 'lembretes'").fetchone()
    limpo.execute("""insert into radar_config (chave, valor) values ('lembretes', %s)
                     on conflict (chave) do update set valor = excluded.valor""",
                  (json.dumps({"ligado": True, "hora": "00:00", "de": "00:00", "ate": "23:59", "aprovacao_horas": 24, "parada_horas": 3,
                               "pauta": True, "aprovacao": True, "video": True, "noticia": True}),))
    yield limpo
    if antes:
        limpo.execute("update radar_config set valor = %s where chave = 'lembretes'", (json.dumps(antes[0]),))
    else:
        limpo.execute("delete from radar_config where chave = 'lembretes'")


# ------------------------------------------------------------ API (PostgREST) para os testes
import base64
import hashlib
import hmac
import shutil
import time

SEGREDO = "segredo-de-teste-com-mais-de-32-caracteres-ok"
PORTA_API = 3999
API = f"http://127.0.0.1:{PORTA_API}"


def jwt(papel: str, sub: str | None = None, exp: int | None = None, segredo: str = SEGREDO) -> str:
    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    carga = {"role": papel}
    if sub:
        carga["sub"] = sub
    if exp:
        carga["exp"] = exp
    cab, corpo = b64(b'{"alg":"HS256","typ":"JWT"}'), b64(json.dumps(carga).encode())
    return f"{cab}.{corpo}." + b64(hmac.new(segredo.encode(), f"{cab}.{corpo}".encode(), hashlib.sha256).digest())


# v0.14.2: chave interna nova do Supabase (sb_secret_…, não é JWT). O gateway de verdade aceita essa chave SÓ no cabeçalho
# apikey (e troca por um JWT de service_role para o banco e o armazenamento); no "Authorization: Bearer" ela é recusada.
SECRETA = "sb_secret_testeRadar0123456789abcdef"


def gateway(cab) -> str | None:
    """Faz o papel do gateway do Supabase. Devolve o Authorization a repassar (vazio: visitante) ou None (recusado)."""
    apikey, auth = cab.get("apikey") or "", cab.get("Authorization") or ""
    if auth.removeprefix("Bearer ").startswith("sb_"):
        return None                                                    # "Invalid Compact JWS"
    if apikey.startswith("sb_secret_"):
        if apikey != SECRETA:
            return None
        return auth or "Bearer " + jwt("service_role")
    return auth


@pytest.fixture(scope="session")
def api_postgrest(banco_pronto, tmp_path_factory):
    if shutil.which("postgrest") is None:
        pytest.skip("postgrest não instalado")
    import requests
    conf = tmp_path_factory.mktemp("pgrst") / "postgrest.conf"
    conf.write_text(f'''db-uri = "postgres://authenticator:teste@/{BANCO}?host={PG["host"]}&port={PG["port"]}"
db-schemas = "public"
db-anon-role = "anon"
jwt-secret = "{SEGREDO}"
server-host = "127.0.0.1"
server-port = {PORTA_API}
''')
    proc = subprocess.Popen(["postgrest", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            if requests.get(API + "/radar_categorias", timeout=1).status_code in (200, 401, 403):   # respondeu (o visitante não lê nada)
                break
        except requests.RequestException:
            pass
        time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("PostgREST não respondeu")
    yield API
    proc.terminate()
