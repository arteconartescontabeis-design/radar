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
SETUP = RAIZ / "sql" / "radar-setup-v0.17.0.sql"
REVERSAO = RAIZ / "sql" / "radar-reversao-v0.17.0.sql"

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
        for uid, nome, papel in [(ADMIN, "Admin", "admin"), (EDITOR, "Editora", "editor"), (LEITOR, "Leitor", "leitor")]:
            c.execute("insert into auth.users (id, email) values (%s, %s) on conflict do nothing", (uid, nome))
            c.execute("insert into radar_perfis (user_id, nome, papel) values (%s, %s, %s) on conflict do nothing",
                      (uid, nome, papel))
        c.execute("insert into auth.users (id, email) values (%s, 'x') on conflict do nothing", (SEM_PERFIL,))
    yield BANCO


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


@pytest.fixture()
def limpo(db):
    """Zera os dados operacionais entre testes (mantém fontes, categorias e perfis)."""
    db.execute("alter table radar_auditoria disable trigger user")
    db.execute("""truncate radar_conteudos, radar_evidencias,
                  radar_assunto_capturas, radar_assuntos, radar_normas, radar_capturas_versoes,
                  radar_capturas, radar_execucoes, radar_auditoria, radar_ia_uso, radar_informativo_itens,
                  radar_informativos, radar_imagens, radar_divulgacoes restart identity cascade""")
    db.execute("update radar_fontes set ultimo_sucesso_em = null, ultima_falha_em = null, "
               "falhas_consecutivas = 0, ultimo_erro = null")
    db.execute("delete from radar_fontes where slug like 'teste-%'")
    # v0.11.0: as datas dos testes são fixas (setembro/outubro de 2026); a regra "notícia com mais de 5 dias é baixa"
    # fica desligada aqui e é ligada só no teste dela
    db.execute("""update radar_config set valor = valor || '{"dias_baixa": 0}'::jsonb
                  where chave = 'relevancia' and valor->'dias_baixa' is distinct from '0'::jsonb""")
    db.execute("truncate radar_auditoria restart identity")
    db.execute("alter table radar_auditoria enable trigger user")
    return db


# ------------------------------------------------------------ API (PostgREST) para os testes
import base64
import hashlib
import hmac
import shutil
import time

SEGREDO = "segredo-de-teste-com-mais-de-32-caracteres-ok"
PORTA_API = 3999
API = f"http://127.0.0.1:{PORTA_API}"


def jwt(papel: str, sub: str | None = None, exp: int | None = None) -> str:
    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    carga = {"role": papel}
    if sub:
        carga["sub"] = sub
    if exp:
        carga["exp"] = exp
    cab, corpo = b64(b'{"alg":"HS256","typ":"JWT"}'), b64(json.dumps(carga).encode())
    return f"{cab}.{corpo}." + b64(hmac.new(SEGREDO.encode(), f"{cab}.{corpo}".encode(), hashlib.sha256).digest())


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
