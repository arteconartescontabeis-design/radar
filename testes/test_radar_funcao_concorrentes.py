"""Função radar-concorrentes (v0.19.1, opcional, SOMENTE LEITURA) rodando de verdade no Deno, com o banco real (PostgREST) e
uma Meta (Graph API, Business Discovery) de mentira. Sem o Deno instalado, o arquivo é pulado.

Confere: só o administrador ou quem tem a chave do Vault (conferida por radar_concorrentes_conferir) chama; a chave errada leva
401 sem vazar nada; nomes de perfil fora do padrão do Instagram são recusados antes de chegar à Meta; os posts vêm em páginas
(paging.cursors.after) até completar o pedido; campo recusado pela Meta (#100) → tenta de novo sem view_count (e depois sem
media_product_type); perfil que não é comercial volta com erro sem derrubar os outros; curtidas ocultas viram null; o tempo
total tem limite; o token nunca aparece na resposta nem no registro (log); e o diagnóstico lê a própria conta da Artecon.
Também: a paginação que para antes da hora (cursor fora do padrão, posts repetidos, páginas demais) avisa; campo essencial
recusado não aciona o plano B e vale para todos; as recusas da Meta que valem para todos (limite, permissão, conta da Artecon)
não insistem nos outros perfis; prazo estourado, falha de rede e resposta que não é JSON derrubam só aquele perfil.

No banco de teste não há Vault nem pg_net: um Vault simulado (vault.secrets, vault.create_secret e vault.decrypted_secrets)
recebe a chave e o sql/radar-concorrentes.sql roda sem a linha do pg_net. Como a função de conferência nasce depois que o
PostgREST pode já ter subido (outro arquivo de testes), ele é avisado para recarregar o esquema. Tudo é desfeito no fim do módulo.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import psycopg
import pytest
import requests

from conftest import ADMIN, API, EDITOR, LEITOR, RAIZ, SECRETA, como, conectar, gateway, jwt, psql

PORTA_PONTE, PORTA_FUNCAO, PORTA_SEM_TOKEN, PORTA_TEMPO, PORTA_PRAZO = 3984, 3983, 3982, 3981, 3990
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
SQL = RAIZ / "sql" / "radar-concorrentes.sql"
SQL_REVERSAO = RAIZ / "sql" / "radar-concorrentes-reversao.sql"
IG = "17841400000000001"                        # META_IG_USER_ID da Artecon (de mentira)
TOKEN_IG = "EAAinstagramSecreto321"             # META_IG_TOKEN
TOKEN_PAGINA = "EAApaginaSecreta456"            # META_PAGE_TOKEN: não é usado, mas também nunca pode aparecer
CAMPOS_CONTA = "username,name,biography,website,followers_count,follows_count,media_count"
CAMPOS_POST = "id,caption,media_type,media_product_type,timestamp,like_count,comments_count,view_count,permalink,media_url,thumbnail_url"
NAO_COUBE = "não coube no tempo; peça de novo só esses"
LEITURA = "Leitura de perfis (Business Discovery, instagram_manage_insights)"     # item do diagnóstico
ESTADO: dict = {}

VAULT_SIMULADO = """
create schema vault;
create table vault.secrets (id uuid primary key default gen_random_uuid(), name text unique, description text, secret text not null);
create function vault.create_secret(new_secret text, new_name text default null, new_description text default '') returns uuid
language sql as $$ insert into vault.secrets (secret, name, description) values (new_secret, new_name, new_description) returning id $$;
create view vault.decrypted_secrets as select id, name, description, secret, secret as decrypted_secret from vault.secrets;
"""


def _posts(u, quantos):
    """Posts no formato da Meta. Curtidas ocultas pelo dono: a Meta não manda o like_count. Só vídeo tem view_count e capa."""
    lista = []
    for i in range(quantos):
        tipo = ("IMAGE", "VIDEO", "CAROUSEL_ALBUM")[i % 3]
        p = {"id": f"{u}-{i}", "caption": f"Legenda {i} de {u} LEGENDA_SECRETA", "media_type": tipo,
             "media_product_type": "REELS" if tipo == "VIDEO" else "FEED", "timestamp": f"2026-10-{1 + i % 28:02d}T12:00:00+0000",
             "comments_count": i, "permalink": f"https://www.instagram.com/p/{u}{i}/",
             "media_url": f"https://cdn.teste/{u}/{i}.{'mp4' if tipo == 'VIDEO' else 'jpg'}"}
        if i % 7 != 3:
            p["like_count"] = 10 + i
        if tipo == "VIDEO":
            p["view_count"], p["thumbnail_url"] = 1000 + i, f"https://cdn.teste/{u}/{i}-capa.jpg"
        lista.append(p)
    return lista


def _conta(u, nome, posts, site=None):
    c = {"username": u, "name": nome, "biography": f"Contabilidade — {nome}", "followers_count": 5400, "follows_count": 210,
         "media_count": posts, "posts": _posts(u, posts)}
    return c | ({"website": site} if site else {})


CONTAS = {c["username"]: c for c in (
    _conta("escritorio.um", "Escritório Um", 120, "https://um.teste"), _conta("escritorio_dois", "Escritório Dois", 3),
    _conta("arteconcontabeis", "Artecon Contábeis", 40, "https://artecon.cnt.br"),
    _conta("lento1", "Lento Um", 10), _conta("lento2", "Lento Dois", 10), _conta("rapido", "Rápido", 10))}


def _cursor(i):
    """Cursor da página que começa no post i, no formato que o teste pedir (a Ponte lê o último número dele)."""
    return {"base64": f"QVFI+ab/c{i}==", "longo": "Q" * 700 + f"x{i}", "enorme": "Q" * 3000 + f"x{i}", "invalido": f"CUR{i}) x",
            "repete": "CUR0"}.get(ESTADO["cursor"], f"CUR{i}")


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST (pelo gateway do Supabase); /meta → Graph API (Business Discovery)."""
    def _responder(self, status, corpo):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
        except (BrokenPipeError, ConnectionResetError):
            pass                                                           # a função desistiu de esperar (prazo)

    def _rest(self):
        apikey, auth = self.headers.get("apikey") or "", self.headers.get("Authorization") or ""
        ESTADO["chaves"].append((self.path.split("?")[0], apikey[:10], auth.removeprefix("Bearer ")[:10]))
        auth = gateway(self.headers)
        if auth is None:
            return self._responder(401, {"message": "Invalid Compact JWS"})
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        cab = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "prefer")} | ({"Authorization": auth} if auth else {})
        r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo, timeout=30)
        self._responder(r.status_code, r.content)

    def _erro(self, status, **e):
        return self._responder(status, {"error": {"type": "OAuthException", "fbtrace_id": "AbC", **e}})

    def _meta(self):
        url = urlparse(self.path)
        caminho = url.path.removeprefix("/meta/")
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        tk, campos = q.get("access_token"), q.get("fields", "")
        ESTADO["meta"].append((caminho, campos, tk))
        if tk != TOKEN_IG or ESTADO["token_recusado"]:
            return self._erro(400, code=190, message=f"Invalid OAuth access token - Cannot parse access token {tk}")
        if caminho != IG:
            return self._erro(400, code=100, error_subcode=33, message=f"Unsupported get request. Object with ID '{caminho}' does not exist")
        if ESTADO["erro_geral_depois"] is not None and campos != "username":   # o limite chega depois de N chamadas
            ESTADO["erro_geral_depois"] -= 1
            if ESTADO["erro_geral_depois"] < 0:
                ESTADO["erro_geral"] = (4, "Application request limit reached")
        if ESTADO["erro_geral"]:                                           # (código, mensagem[, subcódigo])
            codigo, msg, *sub = ESTADO["erro_geral"]
            return self._erro(400, code=codigo, message=f"{msg} {TOKEN_IG} {TOKEN_PAGINA}", **({"error_subcode": sub[0]} if sub else {}))
        if campos == "username":
            return self._responder(200, {"username": "ArteconContabeis", "id": IG})
        if ESTADO["erro_bd"]:                    # sem instagram_manage_insights: só a Business Discovery é recusada
            codigo, msg = ESTADO["erro_bd"]
            return self._erro(403, code=codigo, message=msg)
        m = re.fullmatch(r"business_discovery\.username\(([^)]*)\)\{(.*)\}", campos)
        mm = m and re.search(r"media(?:\.after\(([^)]*)\))?\.limit\((\d+)\)\{([^}]*)\}", m.group(2))
        if not mm:
            return self._erro(400, code=100, message="(#100) Syntax error")
        u, resto = m.groups()
        conta_campos = [c for c in resto[:mm.start()].split(",") if c]
        cursor, limite, cmp = mm.group(1), int(mm.group(2)), mm.group(3).split(",")
        if u in ESTADO["derrubar"]:                                        # falha de rede: fecha a conexão sem responder
            self.close_connection = True
            return
        if u in ESTADO["corpo_bruto"]:                                     # um proxy no caminho devolve HTML
            return self._responder(502, b"<html><body>502 Bad Gateway</body></html>")
        for campo in ("website", "view_count", "media_product_type", "like_count"):   # a Meta recusa um campo de cada vez
            if campo in ESTADO["recusa"] and campo in conta_campos + cmp:
                no = "ShadowIGUser" if campo in conta_campos else "ShadowIGMedia"
                nome = "an unsupported field" if ESTADO["recusa_anonima"] else f"nonexisting field ({campo})"
                return self._erro(400, code=100, message=f"(#100) Tried accessing {nome} on node type ({no})")
        if ESTADO["limite_dados"] and limite > ESTADO["limite_dados"]:
            return self._erro(500, code=1, message="Please reduce the amount of data you're asking for, then retry your request")
        if u in ESTADO["atraso"]:
            time.sleep(ESTADO["atraso"][u])
        conta = CONTAS.get(u)
        if conta is None:                                                  # não existe ou não é conta comercial/criador
            return self._erro(400, code=110, error_subcode=2207013, message="Invalid user id",
                              error_user_title="Cannot find User", error_user_msg=f"The user with username: {u} cannot be found.")
        inicio = int(re.findall(r"\d+", cursor)[-1]) if cursor else 0
        fatia = min(limite, ESTADO["max_pagina"] or limite)
        media = {"data": [{k: v for k, v in p.items() if k in cmp} for p in conta["posts"][inicio:inicio + fatia]]}
        # só cursores: sem next/previous; no modo "sempre", a última página também traz o cursor (a seguinte vem vazia)
        if inicio + fatia < len(conta["posts"]) or (ESTADO["cursor"] == "sempre" and media["data"]):
            media["paging"] = {"cursors": {"before": f"CUR{inicio}", "after": _cursor(inicio + fatia)}}
        bd = {"id": "bd-" + u, "media": media} | {k: conta[k] for k in conta_campos if k in conta}
        self._responder(200, {"business_discovery": bd, "id": IG})

    def do_GET(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path.startswith("/meta/"):
            return self._meta()
        self._responder(404, {})

    def do_POST(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        self._responder(404, {})

    def log_message(self, *a):
        pass


def aplicar_sql(pasta):
    """O sql/radar-concorrentes.sql como está, menos a linha do pg_net (o banco de teste não tem a extensão)."""
    texto = SQL.read_text()
    assert texto.count("create extension if not exists pg_net;") == 1
    arquivo = pasta / "radar-concorrentes-sem-pg_net.sql"
    arquivo.write_text(texto.replace("create extension if not exists pg_net;", "-- (sem pg_net no banco de teste)"))
    r = psql(arquivo)
    assert r.returncode == 0, r.stderr


def recarregar_api():
    """O PostgREST guarda na memória as funções do banco (cache do esquema), e a radar_concorrentes_conferir é criada depois
    que ele pode já ter subido (por outro arquivo de testes): sem recarregar, a RPC daria 404 e toda chave seria recusada.
    No Supabase, um gatilho de DDL pede o recarregamento sozinho; aqui, pede-se à mão e espera-se a RPC aparecer (é assíncrono)."""
    with conectar() as c:
        c.execute("notify pgrst, 'reload schema'")
    cab = {"Authorization": "Bearer " + jwt("service_role")}
    for _ in range(50):
        try:
            if requests.post(API + "/rpc/radar_concorrentes_conferir", json={"p_chave": "x" * 40}, headers=cab, timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.1)
    pytest.fail("o PostgREST não passou a mostrar a função radar_concorrentes_conferir")


@pytest.fixture(scope="module")
def chave(banco_pronto, tmp_path_factory):
    """Vault simulado + sql/radar-concorrentes.sql; devolve a chave que o SQL guardou no Vault. Tudo sai no fim do módulo."""
    with conectar() as c:
        tinha_vault = c.execute("select count(*) from pg_namespace where nspname = 'vault'").fetchone()[0] == 1
        if not tinha_vault:
            c.execute(VAULT_SIMULADO)
    try:
        aplicar_sql(tmp_path_factory.mktemp("concorrentes"))
        with conectar() as c:
            k = c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_concorrentes'").fetchone()[0]
        yield k
    finally:
        with conectar() as c:
            c.execute("drop function if exists public.radar_concorrentes_conferir(text)")
            if tinha_vault:
                c.execute("delete from vault.secrets where name = 'radar_concorrentes'")
            else:
                c.execute("drop schema vault cascade")
            c.execute("notify pgrst, 'reload schema'")                   # não deixa o cache do PostgREST com a função apagada


def _subir(porta, extra, registro):
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), SUPABASE_SERVICE_ROLE_KEY=jwt("service_role"),
                    META_GRAPH_URL=PONTE + "/meta", RADAR_PORTA_LOCAL=str(porta), NO_COLOR="1")
    for nome in ("SUPABASE_SECRET_KEYS", "META_IG_TOKEN", "META_PAGE_TOKEN", "META_IG_USER_ID", "RADAR_CONCORRENTES_ORCAMENTO_MS",
                 "RADAR_CONCORRENTES_PRAZO_MS"):
        ambiente.pop(nome, None)                                # só o que o teste pedir
    ambiente.update(extra)
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                             str(RAIZ / "supabase" / "functions" / "radar-concorrentes" / "index.ts")],
                            env=ambiente, stdout=registro, stderr=subprocess.STDOUT)
    for _ in range(150):
        try:
            requests.options(f"http://127.0.0.1:{porta}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.2)
    return proc


@pytest.fixture(scope="module")
def funcao(api_postgrest, chave, tmp_path_factory):
    """Sobe a ponte e 4 instâncias da função; devolve a pasta com o registro (log) de cada uma (<porta>.log)."""
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    recarregar_api()
    pasta = tmp_path_factory.mktemp("registros")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    # como no projeto da Artecon: a chave interna é a nova (sb_secret_…), na lista nova e no lugar da antiga
    meta_ok = {"META_IG_USER_ID": IG, "META_IG_TOKEN": TOKEN_IG, "META_PAGE_TOKEN": TOKEN_PAGINA,
               "SUPABASE_SERVICE_ROLE_KEY": SECRETA, "SUPABASE_SECRET_KEYS": json.dumps({"default": SECRETA})}
    processos, arquivos = [], []          # encerrados mesmo se a subida de um deles falhar (senão ficam presos nas portas)
    try:
        for porta, extra in ((PORTA_FUNCAO, meta_ok),
                             (PORTA_SEM_TOKEN, {"META_IG_USER_ID": IG, "META_PAGE_TOKEN": TOKEN_PAGINA}),   # chave interna antiga (JWT)
                             (PORTA_TEMPO, {**meta_ok, "RADAR_CONCORRENTES_ORCAMENTO_MS": "3000", "RADAR_CONCORRENTES_PRAZO_MS": "2900"}),
                             # prazo curto por chamada (1 s), mas orçamento de sobra (30 s)
                             (PORTA_PRAZO, {**meta_ok, "RADAR_CONCORRENTES_ORCAMENTO_MS": "30000", "RADAR_CONCORRENTES_PRAZO_MS": "1000"})):
            arquivos.append(open(pasta / f"{porta}.log", "wb"))
            processos.append(_subir(porta, extra, arquivos[-1]))
        yield pasta
    finally:
        for p in processos:
            p.terminate()
        for p in processos:
            p.wait(timeout=10)
        for a in arquivos:
            a.close()
        ponte.shutdown()
        ponte.server_close()          # libera a porta na hora


@pytest.fixture()
def meta(funcao):
    ESTADO.update(meta=[], chaves=[], recusa=set(), recusa_anonima=False, max_pagina=None, limite_dados=None, erro_geral=None,
                  erro_geral_depois=None, erro_bd=None, token_recusado=False, cursor=None, derrubar=set(), corpo_bruto=set(),
                  atraso={"lento1": 1.5, "lento2": 1.5})
    yield funcao


def pedir(corpo, uid=ADMIN, porta=PORTA_FUNCAO, cab=None, timeout=60):
    cab = cab if cab is not None else {"Authorization": "Bearer " + jwt("authenticated", uid)}
    r = requests.post(f"http://127.0.0.1:{porta}/", timeout=timeout, json=corpo, headers=cab)
    return r.status_code, r.json()


def campos_pedidos(usuario=None):
    return [f for _, f, _ in ESTADO["meta"] if usuario is None or f"username({usuario})" in f]


# ------------------------------------------------------------------- SQL (rodar uma vez no Supabase)
def test_sql_guarda_a_chave_no_vault_e_so_o_papel_interno_confere(chave, db, tmp_path):
    assert re.fullmatch(r"[0-9a-f]{64}", chave)                               # 64 hexadecimais, como a da agenda da ITC
    with como("service_role") as c:
        assert c.execute("select radar_concorrentes_conferir(%s)", (chave,)).fetchone()[0] is True
        for errada in ("0" * 64, chave[:31], chave + "0", "", None):
            assert c.execute("select radar_concorrentes_conferir(%s)", (errada,)).fetchone()[0] is False
    for papel, uid in [("authenticated", ADMIN), ("authenticated", EDITOR), ("anon", None)]:
        with como(papel, uid) as c:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                c.execute("select radar_concorrentes_conferir(%s)", (chave,))
    # no padrão das outras funções do Radar: security definer e search_path fixo
    assert db.execute("select prosecdef, proconfig is not null from pg_proc where proname = 'radar_concorrentes_conferir'").fetchone() == (True, True)
    # rodar de novo mantém a mesma chave; a reversão apaga só a função (a chave fica no Vault) e o SQL reinstala
    aplicar_sql(tmp_path)
    assert db.execute("select count(*), min(decrypted_secret) from vault.decrypted_secrets where name = 'radar_concorrentes'").fetchone() == (1, chave)
    for _ in range(2):                                                         # a reversão pode rodar mais de uma vez
        r = psql(SQL_REVERSAO)
        assert r.returncode == 0, r.stderr
    assert db.execute("select count(*) from pg_proc where proname = 'radar_concorrentes_conferir'").fetchone()[0] == 0
    assert db.execute("select count(*) from vault.secrets where name = 'radar_concorrentes'").fetchone()[0] == 1
    aplicar_sql(tmp_path)
    with como("service_role") as c:
        assert c.execute("select radar_concorrentes_conferir(%s)", (chave,)).fetchone()[0] is True


# ------------------------------------------------------------------- quem chama
def test_so_o_administrador_ou_a_chave_certa(meta, chave):
    corpo = {"perfis": ["escritorio_dois"], "posts": 3}
    assert pedir(corpo, uid=EDITOR)[0] == 403
    assert pedir(corpo, uid=LEITOR)[0] == 403
    assert pedir(corpo, cab={})[0] == 401
    assert pedir(corpo, cab={"Authorization": "Bearer " + jwt("anon")})[0] == 401
    forjada = jwt("authenticated", ADMIN, segredo="outro-segredo-qualquer-com-32-caracteres")
    assert pedir(corpo, cab={"Authorization": "Bearer " + forjada}) == (401, {"message": "Sessão inválida ou vencida. Entre de novo."})
    assert ESTADO["meta"] == []                                                # ninguém disso chegou à Meta
    status, r = pedir(corpo)                                                   # o administrador logado
    assert status == 200 and r["perfis"][0]["ok"] is True, r
    ESTADO["chaves"] = []
    status, r = pedir(corpo, cab={"x-radar-chave": chave})                     # o banco ou um script, com a chave do Vault
    assert status == 200 and r["perfis"][0]["ok"] is True and len(r["perfis"][0]["posts"]) == 3, r
    # a conferência chega ao banco com a chave interna nova só no apikey (no Authorization, o Supabase recusaria)
    assert [c for c in ESTADO["chaves"] if c[0] == "/rest/v1/rpc/radar_concorrentes_conferir"] == [
        ("/rest/v1/rpc/radar_concorrentes_conferir", SECRETA[:10], "")]
    assert all(not auth.startswith("sb_") for *_, auth in ESTADO["chaves"])


def test_chave_errada_leva_401_sem_vazar_nada(meta, chave):
    alterada = chave[:-1] + ("1" if chave[-1] == "0" else "0")
    for errada in ("0" * 64, alterada, "curta-demais"):
        r = requests.post(f"http://127.0.0.1:{PORTA_FUNCAO}/", timeout=30, json={"perfis": ["escritorio.um"]},
                          headers={"x-radar-chave": errada})
        assert r.status_code == 401 and r.json() == {"message": "Chave não confere."}, r.text
        assert chave not in r.text and "vault" not in r.text.lower() and "radar_concorrentes" not in r.text
    # a chave curta nem chega ao banco; nenhuma chega à Meta
    assert len([c for c in ESTADO["chaves"] if c[0] == "/rest/v1/rpc/radar_concorrentes_conferir"]) == 2
    assert ESTADO["meta"] == []
    # chave errada junto com a sessão do administrador: vale a chave (recusada)
    cab = {"x-radar-chave": "0" * 64, "Authorization": "Bearer " + jwt("authenticated", ADMIN)}
    assert pedir({"perfis": ["escritorio.um"]}, cab=cab)[0] == 401 and ESTADO["meta"] == []


# ------------------------------------------------------------------- pedido
@pytest.mark.parametrize("corpo", [
    {}, {"perfis": []}, {"perfis": "escritorio.um"}, {"perfis": [f"perfil{i}" for i in range(13)]},
    {"perfis": ["escritorio um"]}, {"perfis": ["x){id}"]}, {"perfis": ["escritorio.um{media}"]}, {"perfis": ["a" * 31]},
    {"perfis": [123]}, {"perfis": ["escritório"]}, {"perfis": ["../me"]}, {"perfis": ["escritorio.um&fields=id"]},
    {"perfis": ["escritorio.um", "@@duplo"]}, {"perfis": [""]},
    {"perfis": ["escritorio.um"], "posts": 0}, {"perfis": ["escritorio.um"], "posts": 101}, {"perfis": ["escritorio.um"], "posts": "50"},
    {"perfis": ["escritorio.um"], "posts": 2.5}, {"perfis": ["escritorio.um"], "posts": True},
    {"acao": "publicar", "perfis": ["escritorio.um"]},
])
def test_pedido_fora_do_padrao_e_recusado_antes_de_chegar_a_meta(meta, corpo):
    status, r = pedir(corpo)
    assert status == 400 and r["message"], r
    assert ESTADO["meta"] == []


def test_doze_perfis_cabem_e_o_nome_e_normalizado(meta):
    status, r = pedir({"perfis": ["@Escritorio_Dois", " escritorio_dois "] + [f"nao.existe{i}" for i in range(10)], "posts": 1})
    assert status == 200 and len(r["perfis"]) == 11                            # sem @, minúsculo e sem repetição
    assert r["perfis"][0]["usuario"] == "escritorio_dois" and r["perfis"][0]["ok"] is True
    assert campos_pedidos()[0].startswith("business_discovery.username(escritorio_dois){")


# ------------------------------------------------------------------- leitura
def test_posts_vem_em_paginas_ate_completar_o_pedido(meta):
    ESTADO["max_pagina"] = 30                                                  # a Meta pode mandar menos do que o limite pedido
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 100})
    assert status == 200 and r["versao"] == "0.19.1", r
    um, dois = r["perfis"]
    assert um["ok"] is True and "aviso" not in um and [p["id"] for p in um["posts"]] == [f"escritorio.um-{i}" for i in range(100)]
    assert um["conta"] == {"username": "escritorio.um", "name": "Escritório Um", "biografia": "Contabilidade — Escritório Um",
                           "site": "https://um.teste", "seguidores": 5400, "seguindo": 210, "posts_total": 120}
    assert campos_pedidos("escritorio.um") == [
        f"business_discovery.username(escritorio.um){{{CAMPOS_CONTA},media.limit(50){{{CAMPOS_POST}}}}}",
        f"business_discovery.username(escritorio.um){{media.after(CUR30).limit(50){{{CAMPOS_POST}}}}}",
        f"business_discovery.username(escritorio.um){{media.after(CUR60).limit(40){{{CAMPOS_POST}}}}}",
        f"business_discovery.username(escritorio.um){{media.after(CUR90).limit(10){{{CAMPOS_POST}}}}}"]
    assert all(c == IG and tk == TOKEN_IG for c, _, tk in ESTADO["meta"])     # sempre a partir da conta da Artecon, com o META_IG_TOKEN
    # a conta com só 3 posts devolve os 3, sem pedir outra página
    assert dois["ok"] is True and len(dois["posts"]) == 3 and dois["conta"]["site"] is None and dois["conta"]["posts_total"] == 3
    assert len(campos_pedidos("escritorio_dois")) == 1
    # sem "posts": 50, numa chamada só
    ESTADO.update(meta=[], max_pagina=None)
    status, r = pedir({"perfis": ["escritorio.um"]})
    assert len(r["perfis"][0]["posts"]) == 50 and len(ESTADO["meta"]) == 1 and "media.limit(50)" in ESTADO["meta"][0][1]


@pytest.mark.parametrize("modo", ["base64", "longo"])
def test_cursor_da_meta_com_mais_e_barra_ou_longo_tambem_pagina(meta, modo):
    ESTADO.update(cursor=modo, max_pagina=5)
    status, r = pedir({"perfis": ["escritorio.um"], "posts": 10})
    p = r["perfis"][0]
    assert p["ok"] is True and "aviso" not in p and [x["id"] for x in p["posts"]] == [f"escritorio.um-{i}" for i in range(10)], r
    assert campos_pedidos()[1] == f"business_discovery.username(escritorio.um){{media.after({_cursor(5)}).limit(5){{{CAMPOS_POST}}}}}"


@pytest.mark.parametrize("modo, motivo, chamadas", [
    ("invalido", "a Meta não mandou como continuar", 1),           # parêntese e espaço mudariam a consulta: não vai
    ("enorme", "a Meta não mandou como continuar", 1),             # mais de 2048 caracteres
    ("repete", "a Meta repetiu os posts da página anterior", 2),
])
def test_paginacao_que_para_antes_da_hora_avisa(meta, modo, motivo, chamadas):
    ESTADO.update(cursor=modo, max_pagina=5)
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 10})
    um, dois = r["perfis"]
    assert um["ok"] is True and len(um["posts"]) == 5 and um["aviso"] == f"vieram 5 dos 10 posts pedidos: {motivo}.", r
    assert len(campos_pedidos("escritorio.um")) == chamadas
    assert dois["ok"] is True and len(dois["posts"]) == 3 and "aviso" not in dois   # acabaram os posts: fim normal


def test_paginas_demais_e_ultima_pagina_vazia(meta):
    # a Meta manda 2 posts por página: a leitura para em 20 páginas, com aviso
    ESTADO["max_pagina"] = 2
    status, r = pedir({"perfis": ["escritorio.um"], "posts": 50})
    p = r["perfis"][0]
    assert len(p["posts"]) == 40 and len(ESTADO["meta"]) == 20, r
    assert p["aviso"] == "vieram 40 dos 50 posts pedidos: a Meta mandou poucos posts por página e a leitura parou em 20 páginas."
    # a última página também traz o cursor e a seguinte vem vazia: acabaram os posts, sem aviso
    ESTADO.update(meta=[], max_pagina=None, cursor="sempre")
    status, r = pedir({"perfis": ["escritorio_dois"], "posts": 10})
    p = r["perfis"][0]
    assert p["ok"] is True and len(p["posts"]) == 3 and "aviso" not in p and len(ESTADO["meta"]) == 2, r


def test_lote_menor_quando_a_meta_pede_menos_dados(meta):
    ESTADO["limite_dados"] = 20                                                # "Please reduce the amount of data..."
    status, r = pedir({"perfis": ["escritorio.um"], "posts": 50})
    assert status == 200 and [p["id"] for p in r["perfis"][0]["posts"]] == [f"escritorio.um-{i}" for i in range(50)], r
    assert [int(re.search(r"limit\((\d+)\)", f).group(1)) for f in campos_pedidos()] == [50, 25, 13, 13, 13, 11]
    # nem 10 por vez a Meta aceita: o perfil volta com o erro dela, sem insistir com lotes menores
    ESTADO.update(meta=[], limite_dados=5)
    status, r = pedir({"perfis": ["escritorio.um"], "posts": 50})
    p = r["perfis"][0]
    assert p["ok"] is False and p["erro"].startswith("a Meta recusou (Meta 1): Please reduce the amount of data"), r
    assert [int(re.search(r"limit\((\d+)\)", f).group(1)) for f in campos_pedidos()] == [50, 25, 13, 10]


def test_campo_recusado_pela_meta_tenta_de_novo_sem_view_count(meta):
    ESTADO["recusa"] = {"view_count"}
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 10})
    assert status == 200, r
    um, dois = r["perfis"]
    assert um["ok"] and dois["ok"] and len(um["posts"]) == 10 and len(dois["posts"]) == 3
    assert all(p["visualizacoes"] is None for p in um["posts"] + dois["posts"])
    assert {p["produto"] for p in um["posts"]} == {"FEED", "REELS"}
    assert "view_count" in um["aviso"] and "view_count" in dois["aviso"]
    pedidos = campos_pedidos()
    # o 1º perfil pede de novo sem view_count; o 2º já vai sem (vale para o resto da chamada)
    assert len(pedidos) == 3 and "view_count" in pedidos[0] and all("view_count" not in f for f in pedidos[1:])
    assert pedidos[1] == pedidos[0].replace(",view_count", "")
    # se a Meta recusar também o media_product_type, sai ele depois
    ESTADO.update(meta=[], recusa={"view_count", "media_product_type"})
    status, r = pedir({"perfis": ["escritorio_dois"], "posts": 5})
    p = r["perfis"][0]
    assert p["ok"] is True and all(x["produto"] is None and x["visualizacoes"] is None for x in p["posts"])
    assert "view_count" in p["aviso"] and "media_product_type" in p["aviso"]
    pedidos = campos_pedidos()
    assert len(pedidos) == 3 and "view_count" not in pedidos[1] and "media_product_type" in pedidos[1]
    assert "media_product_type" not in pedidos[2] and "like_count" in pedidos[2]


@pytest.mark.parametrize("campo", ["website", "like_count"])
def test_campo_essencial_recusado_nao_tira_os_opcionais_e_vale_para_todos(meta, campo):
    """A Meta recusa um campo que a leitura precisa (da conta ou dos posts): tirar view_count ou media_product_type não
    resolve, e a consulta é a mesma para todos os perfis — uma chamada só, e os outros perfis nem são pedidos."""
    ESTADO["recusa"] = {campo}
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 5})
    a, b = r["perfis"]
    assert a["ok"] is False and f"nonexisting field ({campo})" in a["erro"] and "Meta 100" in a["erro"], r
    assert b == {"usuario": "escritorio_dois", "ok": False, "erro": a["erro"]}
    assert len(ESTADO["meta"]) == 1 and "view_count" in ESTADO["meta"][0][1]


def test_recusa_sem_nome_do_campo_tira_os_opcionais_na_ordem(meta):
    ESTADO.update(recusa={"media_product_type"}, recusa_anonima=True)       # "(#100) Tried accessing an unsupported field ..."
    status, r = pedir({"perfis": ["escritorio_dois"], "posts": 3})
    p = r["perfis"][0]
    assert p["ok"] is True and "view_count" in p["aviso"] and "media_product_type" in p["aviso"], r
    pedidos = campos_pedidos()
    assert len(pedidos) == 3 and "view_count" not in pedidos[1] and "media_product_type" in pedidos[1]


def test_perfil_que_nao_e_comercial_volta_com_erro_sem_derrubar_os_outros(meta):
    status, r = pedir({"perfis": ["escritorio_dois", "pessoal", "escritorio.um"], "posts": 5})
    assert status == 200 and [p["usuario"] for p in r["perfis"]] == ["escritorio_dois", "pessoal", "escritorio.um"], r
    a, b, c = r["perfis"]
    assert a["ok"] is True and c["ok"] is True and len(c["posts"]) == 5
    assert b["ok"] is False and set(b) == {"usuario", "ok", "erro"}
    assert "não é comercial/criador" in b["erro"] and "110" in b["erro"]
    assert len(ESTADO["meta"]) == 3                                            # o perfil com erro não foi pedido de novo


def test_curtidas_ocultas_viram_null_e_os_campos_vem_em_portugues(meta):
    status, r = pedir({"perfis": ["escritorio.um"], "posts": 7})
    posts = r["perfis"][0]["posts"]
    assert posts[0] == {"id": "escritorio.um-0", "data": "2026-10-01T12:00:00+0000", "tipo": "IMAGE", "produto": "FEED", "curtidas": 10,
                        "comentarios": 0, "visualizacoes": None, "legenda": "Legenda 0 de escritorio.um LEGENDA_SECRETA",
                        "link": "https://www.instagram.com/p/escritorio.um0/", "imagem": "https://cdn.teste/escritorio.um/0.jpg"}
    assert posts[3]["curtidas"] is None and posts[2]["curtidas"] == 12        # o dono ocultou as curtidas do post 3
    video = posts[1]                                                           # em vídeo, a imagem é a capa
    assert (video["tipo"], video["produto"], video["visualizacoes"], video["imagem"]) == ("VIDEO", "REELS", 1001, "https://cdn.teste/escritorio.um/1-capa.jpg")


def test_perfis_que_nao_cabem_no_tempo_voltam_para_pedir_de_novo(meta):
    """Instância com orçamento de 3 s e prazo de 2,9 s por chamada: um perfil (ou a página seguinte) só começa se sobrar
    1/3 do prazo (~0,97 s; no Supabase, 5 s de 120 s)."""
    # lento1 demora 1,2 s; lento2 começa, mas a Meta demora 2,5 s e o orçamento acaba antes; rapido nem começa
    ESTADO["atraso"] = {"lento1": 1.2, "lento2": 2.5}
    status, r = pedir({"perfis": ["lento1", "lento2", "rapido"], "posts": 5}, porta=PORTA_TEMPO, timeout=30)
    assert status == 200, r
    um, dois, tres = r["perfis"]
    assert um["ok"] is True and len(um["posts"]) == 5
    assert dois == {"usuario": "lento2", "ok": False, "erro": NAO_COUBE}
    assert tres == {"usuario": "rapido", "ok": False, "erro": NAO_COUBE}
    assert len(campos_pedidos("lento2")) == 1 and not campos_pedidos("rapido")
    # lento1 demora 2,45 s: os posts que já vieram ficam (com aviso), a página seguinte e o lento2 nem são pedidos
    ESTADO.update(meta=[], atraso={"lento1": 2.45}, max_pagina=5)
    status, r = pedir({"perfis": ["lento1", "lento2"], "posts": 10}, porta=PORTA_TEMPO, timeout=30)
    um, dois = r["perfis"]
    assert um["ok"] is True and len(um["posts"]) == 5 and "vieram 5 dos 10 posts pedidos" in um["aviso"], r
    assert dois == {"usuario": "lento2", "ok": False, "erro": NAO_COUBE}
    assert campos_pedidos() == [f"business_discovery.username(lento1){{{CAMPOS_CONTA},media.limit(10){{{CAMPOS_POST}}}}}"]


@pytest.mark.parametrize("codigo, sub, msg, esperado", [
    (17, None, "(#17) User request limit reached", "limite de chamadas da Meta atingido"),
    (32, None, "(#32) Page request limit reached", "limite de chamadas da Meta atingido"),
    (613, None, "(#613) Calls to this api have exceeded the rate limit.", "limite de chamadas da Meta atingido"),
    (80002, None, "There have been too many calls to this Instagram account.", "limite de chamadas da Meta atingido"),
    (200, None, "(#200) Permissions error", "falta permissão no META_IG_TOKEN"),
    # o META_IG_USER_ID não é a conta do Instagram que o token alcança: sem plano B de campos
    (100, 33, "Unsupported get request. Object with ID '1' does not exist", "o META_IG_USER_ID não é a conta"),
    (100, None, "(#100) Tried accessing nonexisting field (business_discovery) on node type (User)", "o META_IG_USER_ID não é a conta"),
])
def test_recusa_que_vale_para_todos_nao_insiste_nos_outros_perfis(meta, codigo, sub, msg, esperado):
    ESTADO["erro_geral"] = (codigo, msg, sub) if sub else (codigo, msg)
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 5})
    assert status == 200, r
    a, b = r["perfis"]
    assert a["ok"] is False and a["erro"].startswith(esperado) and f"(Meta {codigo}{'/' + str(sub) if sub else ''})" in a["erro"], r
    assert b == {"usuario": "escritorio_dois", "ok": False, "erro": a["erro"]}
    assert len(ESTADO["meta"]) == 1                                            # uma chamada só
    assert TOKEN_IG not in json.dumps(r) and TOKEN_PAGINA not in json.dumps(r)


def test_prazo_de_uma_chamada_estourado_nao_impede_os_outros_perfis(meta):
    """Instância com prazo de 1 s por chamada e orçamento de 30 s: a Meta demora 1,5 s com lento1, só ele falha."""
    status, r = pedir({"perfis": ["lento1", "escritorio_dois"], "posts": 3}, porta=PORTA_PRAZO, timeout=30)
    um, dois = r["perfis"]
    assert um == {"usuario": "lento1", "ok": False, "erro": "a Meta não respondeu em 1 s; tente de novo em alguns minutos"}, r
    assert dois["ok"] is True and len(dois["posts"]) == 3 and len(campos_pedidos("escritorio_dois")) == 1
    assert "códigos da Meta: sem_resposta" in (meta / f"{PORTA_PRAZO}.log").read_text()


def test_falha_de_rede_nao_manda_esperar_o_prazo(meta):
    """Conexão que cai sem resposta (como porta fechada, DNS ou META_GRAPH_URL errado): falha na hora e diz que é rede."""
    ESTADO["derrubar"] = {"escritorio.um"}
    inicio = time.monotonic()
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 3})
    um, dois = r["perfis"]
    assert um == {"usuario": "escritorio.um", "ok": False,
                  "erro": "não foi possível falar com a Meta (rede ou META_GRAPH_URL errado); tente de novo em alguns minutos"}, r
    assert dois["ok"] is True and time.monotonic() - inicio < 10
    assert "códigos da Meta: rede" in (meta / f"{PORTA_FUNCAO}.log").read_text()


def test_resposta_da_meta_que_nao_e_json(meta):
    ESTADO["corpo_bruto"] = {"escritorio.um"}
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 3})
    um, dois = r["perfis"]
    assert um == {"usuario": "escritorio.um", "ok": False, "erro": "a Meta devolveu uma resposta ilegível (HTTP 502); tente de novo"}, r
    assert dois["ok"] is True and len(ESTADO["meta"]) == 2


def test_token_nunca_aparece_na_resposta_nem_no_registro(meta):
    # limite da Meta (a mensagem traz os tokens): vale para todos, e o 2º perfil nem é pedido
    ESTADO["erro_geral"] = (4, "Application request limit reached")
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"]})
    texto = json.dumps(r)
    assert status == 200 and TOKEN_IG not in texto and TOKEN_PAGINA not in texto
    a, b = r["perfis"]
    assert a["ok"] is False and "limite de chamadas da Meta" in a["erro"] and b["erro"] == a["erro"] and len(ESTADO["meta"]) == 1
    # o limite chega no meio das páginas do 1º perfil: os posts que vieram ficam (com aviso) e o 2º perfil nem é pedido
    ESTADO.update(meta=[], erro_geral=None, max_pagina=5, erro_geral_depois=1)
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"], "posts": 10})
    a, b = r["perfis"]
    assert a["ok"] is True and len(a["posts"]) == 5 and "vieram 5 dos 10 posts pedidos: limite de chamadas da Meta" in a["aviso"], r
    assert b["ok"] is False and "limite de chamadas da Meta" in b["erro"] and len(ESTADO["meta"]) == 2
    assert TOKEN_IG not in json.dumps(r) and TOKEN_PAGINA not in json.dumps(r)
    # recusa desconhecida: a mensagem da Meta aparece, mas com "***" no lugar dos tokens
    ESTADO.update(meta=[], erro_geral=(2, "Service temporarily unavailable"), erro_geral_depois=None, max_pagina=None)
    status, r = pedir({"perfis": ["escritorio.um", "escritorio_dois"]})
    assert all("***" in p["erro"] and "Service temporarily unavailable" in p["erro"] for p in r["perfis"]) and len(ESTADO["meta"]) == 2
    assert TOKEN_IG not in json.dumps(r) and TOKEN_PAGINA not in json.dumps(r)
    # token recusado (a Meta repete o token na mensagem): explica qual segredo trocar
    ESTADO.update(meta=[], erro_geral=None, token_recusado=True)
    status, r = pedir({"perfis": ["escritorio.um"]})
    assert "META_IG_TOKEN" in r["perfis"][0]["erro"] and "190" in r["perfis"][0]["erro"] and TOKEN_IG not in json.dumps(r)
    status, r = pedir({"acao": "diagnostico"})
    assert status == 200 and r["tudo_certo"] is False and TOKEN_IG not in json.dumps(r) and TOKEN_PAGINA not in json.dumps(r)
    registro = (meta / f"{PORTA_FUNCAO}.log").read_text()
    for proibido in (TOKEN_IG, TOKEN_PAGINA, "escritorio", "LEGENDA_SECRETA"):
        assert proibido not in registro, proibido
    assert "perfil(s)" in registro and "códigos da Meta: 4" in registro and "códigos da Meta: 190" in registro


# ------------------------------------------------------------------- diagnóstico
def test_diagnostico_le_a_propria_conta_pela_business_discovery(meta, chave):
    status, r = pedir({"acao": "diagnostico"})
    assert status == 200 and r["tudo_certo"] is True and r["versao"] == "0.19.1", r
    detalhes = {i["item"]: i["detalhe"] for i in r["itens"]}
    assert detalhes["Conta do Instagram da Artecon"] == "@arteconcontabeis"
    assert detalhes["Chave para chamar pelo banco"].startswith("instalada")
    assert detalhes[LEITURA] == "leu a própria conta: 5400 seguidores, 40 posts"
    assert campos_pedidos() == ["username", f"business_discovery.username(arteconcontabeis){{{CAMPOS_CONTA},media.limit(1){{{CAMPOS_POST}}}}}"]
    # pela chave do Vault também; o editor não
    assert pedir({"acao": "diagnostico"}, cab={"x-radar-chave": chave})[1]["tudo_certo"] is True
    assert pedir({"acao": "diagnostico"}, uid=EDITOR)[0] == 403
    # sem a permissão instagram_manage_insights: a própria conta ainda lê (instagram_basic), só a Business Discovery é recusada
    ESTADO.update(meta=[], erro_bd=(10, "(#10) Application does not have permission for this action"))
    status, r = pedir({"acao": "diagnostico"})
    itens = {i["item"]: i for i in r["itens"]}
    assert r["tudo_certo"] is False and itens["Conta do Instagram da Artecon"]["ok"] is True, r
    assert itens[LEITURA]["ok"] is False and itens[LEITURA]["detalhe"].startswith("falta permissão no META_IG_TOKEN")
    assert "(Meta 10)" in itens[LEITURA]["detalhe"] and len(ESTADO["meta"]) == 2
    # sem nem o instagram_basic: a leitura da própria conta já falha e a Business Discovery nem é tentada
    ESTADO.update(meta=[], erro_bd=None, erro_geral=(10, "(#10) Application does not have permission for this action"))
    status, r = pedir({"acao": "diagnostico"})
    itens = {i["item"]: i for i in r["itens"]}
    assert r["tudo_certo"] is False and LEITURA not in itens and len(ESTADO["meta"]) == 1, r
    conta = itens["Conta do Instagram da Artecon"]
    assert conta["ok"] is False and conta["detalhe"].startswith("falta permissão no META_IG_TOKEN")


def test_sem_o_meta_ig_token_explica_e_nao_chama_a_meta(meta):
    status, r = pedir({"acao": "diagnostico"}, porta=PORTA_SEM_TOKEN)
    assert status == 200 and r["tudo_certo"] is False, r
    segredos = next(i for i in r["itens"] if i["item"] == "Segredos da Meta")
    assert segredos["ok"] is False and "META_IG_TOKEN" in segredos["detalhe"] and "META_PAGE_TOKEN não é usado" in segredos["detalhe"]
    # a conferência da chave funciona também com a chave interna antiga (JWT service_role, nos dois cabeçalhos)
    assert next(i for i in r["itens"] if i["item"] == "Chave para chamar pelo banco")["ok"] is True
    status, r = pedir({"perfis": ["escritorio.um"]}, porta=PORTA_SEM_TOKEN)
    assert status == 503 and "META_IG_TOKEN" in r["message"] and "instagram_manage_insights" in r["message"]
    assert ESTADO["meta"] == [] and TOKEN_PAGINA not in json.dumps(r)


def test_registro_so_tem_contagens_e_codigos(meta, chave):
    """O registro (log) das 4 instâncias nunca tem token, nome de perfil ou legenda. O teste faz as chamadas que confere (não
    depende dos outros testes); rodando no fim do módulo, confere também tudo o que eles registraram."""
    assert pedir({"perfis": ["escritorio_dois", "pessoal"], "posts": 2})[0] == 200                       # administrador
    assert pedir({"perfis": ["escritorio_dois"], "posts": 1}, cab={"x-radar-chave": chave})[0] == 200    # chave do Vault
    assert pedir({"acao": "diagnostico"}, porta=PORTA_SEM_TOKEN)[0] == 200
    assert pedir({"perfis": ["rapido"], "posts": 1}, porta=PORTA_TEMPO, timeout=30)[0] == 200
    assert pedir({"perfis": ["rapido"], "posts": 1}, porta=PORTA_PRAZO, timeout=30)[0] == 200
    for porta in (PORTA_FUNCAO, PORTA_SEM_TOKEN, PORTA_TEMPO, PORTA_PRAZO):
        registro = (meta / f"{porta}.log").read_text()
        for proibido in (TOKEN_IG, TOKEN_PAGINA, "escritorio", "pessoal", "nao.existe", "lento", "rapido", "arteconcontabeis",
                         "LEGENDA_SECRETA", "Escritório", "access_token", "CUR", "QVFI"):
            assert proibido not in registro, (porta, proibido)
    registro = (meta / f"{PORTA_FUNCAO}.log").read_text()
    assert "radar-concorrentes (admin): 2 perfil(s), 1 lido(s), 1 com erro, 2 post(s), códigos da Meta: 110/2207013\n" in registro
    assert "radar-concorrentes (chave): 1 perfil(s), 1 lido(s), 0 com erro, 1 post(s)\n" in registro
    assert "radar-concorrentes (admin): diagnóstico, 2 de 3 item(ns) OK\n" in (meta / f"{PORTA_SEM_TOKEN}.log").read_text()
