"""Módulo Respostas Automáticas (v0.35.0): a função radar-meta-webhook de verdade no Deno, com o banco real (PostgREST) e uma Meta
(Graph API) de mentira. Sem o Deno instalado, o arquivo é pulado.

Confere: o GET de verificação do webhook (token certo devolve o hub.challenge; errado, 403; sem segredo, 503); o POST da Meta só
passa com a assinatura X-Hub-Signature-256 válida (sem ela ou errada, 401 e NADA no banco); o comentário com a palavra-chave gera a
resposta pública (POST /{comentário}/replies no Instagram; /{comentário}/comments no Facebook) e a mensagem privada
(POST /{página}/messages com o comment_id e o link na linha de baixo), com o token SÓ no cabeçalho Authorization; o sem palavra-chave
é descartado sem chamada nenhuma à Meta; a privada que falha não derruba a pública (registro "enviado" com privada_ok = false e o
erro anotado); a pública que falha vira erro; sem a página gravada, a privada fica anotada para rodar o Testar conexão; as ações
(agenda_teste, pendentes, diagnostico) exigem a chave do Vault ou o administrador; o diagnostico grava as contas; com o token do
USUÁRIO DE SISTEMA no META_PAGE_TOKEN a função troca sozinha pelo da página (v0.35.1); e o registro (log) da função nunca tem
token, nome, texto de comentário ou palavra-chave.

Dados de mentira: comentários de "Ana Teste" e "Bruno Exemplo" em mídias "123"/"101_202"; nada real.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest
import requests

from conftest import ADMIN, API, EDITOR, RAIZ, SECRETA, como, conectar, gateway, jwt
from test_radar_funcao_concorrentes import VAULT_SIMULADO


def recarregar_api():
    """Pede ao PostgREST para recarregar o esquema e espera a RPC desta versão aparecer (é assíncrono)."""
    with conectar() as c:
        c.execute("notify pgrst, 'reload schema'")
    cab = {"Authorization": "Bearer " + jwt("service_role")}
    for _ in range(50):
        try:
            if requests.post(API + "/rpc/radar_respostas_conferir", json={"p_chave": "x" * 40}, headers=cab, timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.1)
    pytest.fail("o PostgREST não passou a mostrar a função radar_respostas_conferir")

PORTA_PONTE, PORTA_FUNCAO, PORTA_SEM_SEGREDO = 3959, 3958, 3957
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
FUNCAO = f"http://127.0.0.1:{PORTA_FUNCAO}/"
APP_SECRET = "segredo-do-app-de-teste"
VERIFY = "token-de-verificacao-teste"
TOKEN_PAGINA = "EAApaginaRespostas345"
TOKEN_USUARIO = "EAAusuarioDeSistema678"                    # v0.35.1: o token do usuário de sistema; a função troca sozinha
PAGINA, IG = "101", "17841400000000001"
APP_ID, APP_ID_2 = "2452237768635139", "4470474209936489"   # v0.35.4: o app principal e o irmão do Instagram (veredito do Testar conexão)
APPS_VALIDOS = {f"{APP_ID}|{APP_SECRET}"}                    # os pares app|segredo que a Graph de mentira aceita como token de app
ESTADO: dict = {"meta": [], "erro_publica": None, "erro_privada": None, "erro_me": None}


def assinar(corpo: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), corpo, hashlib.sha256).hexdigest()


def aviso_instagram(comentario="111", midia="123", autor="555", nome="ana.teste", texto="Oi, QUERO o material!"):
    return {"object": "instagram", "entry": [{"id": IG, "time": 1, "changes": [{"field": "comments",
            "value": {"id": comentario, "from": {"id": autor, "username": nome}, "text": texto, "media": {"id": midia}}}]}]}


def aviso_facebook(comentario="202_303", post="101_202", autor="556", nome="Bruno Exemplo", texto="quero sim"):
    return {"object": "page", "entry": [{"id": PAGINA, "time": 1, "changes": [{"field": "feed",
            "value": {"item": "comment", "verb": "add", "comment_id": comentario, "post_id": post,
                      "from": {"id": autor, "name": nome}, "message": texto}}]}]}


def webhook(aviso, assinatura=None, porta=PORTA_FUNCAO):
    corpo = json.dumps(aviso).encode()
    return requests.post(f"http://127.0.0.1:{porta}/", data=corpo,
                         headers={"Content-Type": "application/json",
                                  "X-Hub-Signature-256": assinar(corpo) if assinatura is None else assinatura}, timeout=30)


def acao(corpo, chave=None, uid=None, porta=PORTA_FUNCAO):
    cab = {"Content-Type": "application/json"}
    if chave:
        cab["x-radar-chave"] = chave
    if uid:
        cab["Authorization"] = "Bearer " + jwt("authenticated", uid)
    return requests.post(f"http://127.0.0.1:{porta}/", json=corpo, headers=cab, timeout=60)


class PonteRespostas(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST (pelo gateway do Supabase); /meta → a Graph API de mentira (replies, comments, messages, me)."""

    def _responder(self, status, corpo):
        dados = json.dumps(corpo).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _rest(self):
        auth = gateway(self.headers)
        if auth is None:
            return self._responder(401, {"message": "Invalid Compact JWS"})
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        cab = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "prefer")} | ({"Authorization": auth} if auth else {})
        r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo, timeout=30)
        try:
            self.send_response(r.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(r.content)))
            self.end_headers()
            self.wfile.write(r.content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _erro(self, code, message):
        return self._responder(400, {"error": {"type": "OAuthException", "code": code, "message": message, "fbtrace_id": "AbC"}})

    def _meta(self):
        caminho = urlparse(self.path).path.removeprefix("/meta/")
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}") if self.command == "POST" else {}
        pedido = {"metodo": self.command, "caminho": caminho, "corpo": corpo, "auth": self.headers.get("Authorization", ""),
                  "query": urlparse(self.path).query}
        ESTADO["meta"].append(pedido)
        if self.command == "GET" and caminho.isdigit():
            # v0.35.4: o veredito do app — GET {app}?fields=id com Bearer {app}|{segredo}; devolve o id só se o par for válido
            tok = pedido["auth"].removeprefix("Bearer ")
            if tok in APPS_VALIDOS and tok.split("|", 1)[0] == caminho:
                return self._responder(200, {"id": caminho})
            return self._erro(190, "Invalid OAuth access token")
        if self.command == "GET" and caminho == "me/accounts":
            # v0.35.1: a troca do token do usuário de sistema pelo da página — o token vai no cabeçalho, como nas outras chamadas
            if pedido["auth"] == "Bearer " + TOKEN_USUARIO:
                return self._responder(200, {"data": [{"access_token": TOKEN_PAGINA, "id": PAGINA}]})
            if pedido["auth"] == "Bearer " + TOKEN_PAGINA:
                return self._erro(100, "Tried accessing nonexisting field (accounts)")   # o token de página não tem /accounts
            return self._erro(190, "Invalid OAuth access token")
        if pedido["auth"] != "Bearer " + TOKEN_PAGINA:
            return self._erro(190, "Invalid OAuth access token")
        if self.command == "GET" and caminho == "me":
            if ESTADO["erro_me"]:
                return self._erro(*ESTADO["erro_me"])
            return self._responder(200, {"id": PAGINA, "name": "Artecon Página Teste",
                                         "instagram_business_account": {"id": IG, "username": "artecon.teste"}})
        if self.command != "POST":
            return self._erro(100, "Unsupported get request")
        if caminho.endswith("/replies") or caminho.endswith("/comments"):
            if ESTADO["erro_publica"]:
                return self._erro(*ESTADO["erro_publica"])
            return self._responder(200, {"id": "r-" + caminho.split("/")[0]})
        if caminho == f"{PAGINA}/messages":
            if ESTADO["erro_privada"]:
                return self._erro(*ESTADO["erro_privada"])
            return self._responder(200, {"recipient_id": "999", "message_id": "m-1"})
        if caminho == f"{PAGINA}/subscribed_apps":
            # v0.35.2: o diagnostico inscreve o app na própria página (campo "feed")
            return self._responder(200, {"success": True})
        self._erro(100, "Unsupported post request")

    def do_GET(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path.startswith("/meta/"):
            return self._meta()
        self._responder(404, {})

    do_POST = do_PATCH = do_DELETE = do_PUT = do_GET

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def chave(banco_pronto):
    """Vault simulado + a chave 'radar_respostas' e a radar_respostas_conferir (como o sql/radar-respostas-agenda.sql cria)."""
    with conectar() as c:
        tinha_vault = c.execute("select count(*) from pg_namespace where nspname = 'vault'").fetchone()[0] == 1
        if not tinha_vault:
            c.execute(VAULT_SIMULADO)
        c.execute("""do $$ begin
            if not exists (select 1 from vault.secrets where name = 'radar_respostas') then
              perform vault.create_secret(replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''), 'radar_respostas', 'teste');
            end if; end $$""")
        trecho = (RAIZ / "sql" / "radar-respostas-agenda.sql").read_text(encoding="utf-8")
        inicio = trecho.index("create or replace function public.radar_respostas_conferir")
        c.execute(trecho[inicio:trecho.index("end $$;", trecho.index("grant execute", inicio)) + 7])
        c.execute("notify pgrst, 'reload schema'")
    try:
        with conectar() as c:
            yield c.execute("select decrypted_secret from vault.decrypted_secrets where name = 'radar_respostas'").fetchone()[0]
    finally:
        with conectar() as c:
            c.execute("drop function if exists public.radar_respostas_conferir(text)")
            if tinha_vault:
                c.execute("delete from vault.secrets where name = 'radar_respostas'")
            else:
                c.execute("drop schema vault cascade")
            c.execute("notify pgrst, 'reload schema'")


def _subir(porta, extra, registro):
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), META_GRAPH_URL=PONTE + "/meta",
                    RADAR_PORTA_LOCAL=str(porta), NO_COLOR="1")
    for nome in ("SUPABASE_SECRET_KEYS", "SUPABASE_SERVICE_ROLE_KEY", "META_APP_SECRET", "META_VERIFY_TOKEN", "META_PAGE_TOKEN",
                 "RADAR_RESPOSTAS_PRAZO_MS"):
        ambiente.pop(nome, None)
    ambiente.update(extra)
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                             str(RAIZ / "supabase" / "functions" / "radar-meta-webhook" / "index.ts")],
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
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    recarregar_api()
    pasta = tmp_path_factory.mktemp("registros-respostas")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), PonteRespostas)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    completa = {"META_APP_SECRET": APP_SECRET, "META_VERIFY_TOKEN": VERIFY, "META_PAGE_TOKEN": TOKEN_PAGINA,
                "SUPABASE_SERVICE_ROLE_KEY": SECRETA, "SUPABASE_SECRET_KEYS": json.dumps({"default": SECRETA})}
    processos, arquivos = [], []
    try:
        for porta, extra in ((PORTA_FUNCAO, completa),
                             (PORTA_SEM_SEGREDO, {"SUPABASE_SERVICE_ROLE_KEY": SECRETA})):
            arquivos.append(open(pasta / f"{porta}.log", "wb"))
            processos.append(_subir(porta, extra, arquivos[-1]))
        yield chave
    finally:
        for p in processos:
            p.terminate()
        for a in arquivos:
            a.close()
        ponte.shutdown()
        ponte.server_close()
        # o registro da função: nunca o token, a palavra-chave, o nome ou o texto de ninguém
        for porta in (PORTA_FUNCAO, PORTA_SEM_SEGREDO):
            texto = (pasta / f"{porta}.log").read_text(encoding="utf-8", errors="replace")
            for proibido in (TOKEN_PAGINA, APP_SECRET, "QUERO", "ana.teste", "Bruno", "material"):
                assert proibido not in texto, (porta, proibido)


@pytest.fixture()
def resp(funcao, limpo):
    limpo.execute("truncate radar_respostas_registro, radar_respostas_gatilhos, radar_respostas_contas restart identity cascade")
    limpo.execute("delete from radar_config where chave = 'respostas'")
    limpo.execute("""insert into radar_respostas_gatilhos (rede, midia_id, titulo, palavra_chave, resposta_publica, mensagem_privada,
                                                           link_material, limite_hora)
                     values ('instagram', '123', 'Material', 'quero', 'Mandamos no privado!', 'Aqui está o material:',
                             'https://exemplo.test/m', 5),
                            ('facebook', '101_202', 'Post da página', 'quero', 'Olha o privado!', 'Segue o material:', '', 5)""")
    limpo.execute("insert into radar_respostas_contas (rede, conta_id, nome) values ('facebook', %s, 'Artecon Página Teste')", (PAGINA,))
    ESTADO.update(meta=[], erro_publica=None, erro_privada=None, erro_me=None)
    yield limpo
    limpo.execute("truncate radar_respostas_registro, radar_respostas_gatilhos, radar_respostas_contas restart identity cascade")
    limpo.execute("delete from radar_config where chave = 'respostas'")


# ------------------------------------------------------------------------------------- a verificação e a assinatura
def test_get_de_verificacao(funcao):
    r = requests.get(FUNCAO, params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345"}, timeout=15)
    assert (r.status_code, r.text) == (200, "12345")
    assert requests.get(FUNCAO, params={"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "1"}, timeout=15).status_code == 403
    r = requests.get(f"http://127.0.0.1:{PORTA_SEM_SEGREDO}/", params={"hub.mode": "subscribe", "hub.verify_token": VERIFY,
                                                                       "hub.challenge": "1"}, timeout=15)
    assert r.status_code == 503 and "META_VERIFY_TOKEN" in r.json()["message"]


def test_post_sem_assinatura_valida_nao_toca_no_banco(resp):
    corpo = json.dumps(aviso_instagram()).encode()
    sem = requests.post(FUNCAO, data=corpo, headers={"Content-Type": "application/json"}, timeout=30)
    assert sem.status_code == 401                                                   # sem o cabeçalho: cai na trilha das ações, sem sessão
    assert webhook(aviso_instagram(), assinatura="sha256=" + "0" * 64).status_code == 401
    assert webhook(aviso_instagram(), assinatura="lixo").status_code == 401
    assert resp.execute("select count(*) from radar_respostas_registro").fetchone()[0] == 0
    assert ESTADO["meta"] == []


# ------------------------------------------------------------------------------------- o fluxo do comentário
def test_comentario_com_palavra_chave_responde_e_manda_a_privada(resp):
    assert webhook(aviso_instagram()).status_code == 200
    situacao, privada, resposta_id = resp.execute(
        "select situacao, privada_ok, resposta_id from radar_respostas_registro where comentario_id = '111'").fetchone()
    assert (situacao, privada, resposta_id) == ("enviado", True, "r-111")
    caminhos = [(p["metodo"], p["caminho"]) for p in ESTADO["meta"]]
    assert caminhos == [("POST", "111/replies"), ("POST", f"{PAGINA}/messages")]
    assert ESTADO["meta"][0]["corpo"] == {"message": "Mandamos no privado!"}
    assert ESTADO["meta"][1]["corpo"] == {"recipient": {"comment_id": "111"},
                                          "message": {"text": "Aqui está o material:\nhttps://exemplo.test/m"}}
    assert all(p["auth"] == "Bearer " + TOKEN_PAGINA and "access_token" not in p["query"] for p in ESTADO["meta"])


def test_comentario_do_facebook_vai_pelo_caminho_da_pagina(resp):
    assert webhook(aviso_facebook()).status_code == 200
    situacao, privada = resp.execute(
        "select situacao, privada_ok from radar_respostas_registro where comentario_id = '202_303'").fetchone()
    assert (situacao, privada) == ("enviado", True)
    caminhos = [(p["metodo"], p["caminho"]) for p in ESTADO["meta"]]
    assert caminhos == [("POST", "202_303/comments"), ("POST", f"{PAGINA}/messages")]
    assert ESTADO["meta"][1]["corpo"]["message"] == {"text": "Segue o material:"}        # sem link: só o texto


def test_sem_palavra_chave_descarta_sem_chamar_a_meta(resp):
    assert webhook(aviso_instagram(comentario="112", texto="parabéns pelo conteúdo")).status_code == 200
    assert resp.execute("select situacao, motivo from radar_respostas_registro where comentario_id = '112'").fetchone() == \
        ("descartado", "sem a palavra-chave")
    assert webhook(aviso_instagram(comentario="112", texto="agora eu QUERO")).status_code == 200     # repetido: continua descartado
    assert resp.execute("select count(*) from radar_respostas_registro").fetchone()[0] == 1
    assert ESTADO["meta"] == []


def test_privada_que_falha_nao_derruba_a_publica(resp):
    ESTADO["erro_privada"] = (10903, "This user cant reply to this message")
    assert webhook(aviso_instagram(comentario="113")).status_code == 200
    situacao, privada, erro = resp.execute(
        "select situacao, privada_ok, erro from radar_respostas_registro where comentario_id = '113'").fetchone()
    assert situacao == "enviado" and privada is False and "Meta 10903" in erro and "privada" in erro


def test_publica_que_falha_vira_erro_e_o_reenviar_tenta_de_novo(resp, funcao):
    ESTADO["erro_publica"] = (368, "Temporarily blocked for policies violations")
    assert webhook(aviso_instagram(comentario="114")).status_code == 200
    rid, situacao, erro = resp.execute(
        "select id, situacao, erro from radar_respostas_registro where comentario_id = '114'").fetchone()
    assert situacao == "erro" and "Meta 368" in erro
    ESTADO.update(erro_publica=None, meta=[])
    with como("authenticated", ADMIN) as c:
        c.execute("select radar_respostas_reenviar(%s)", (rid,))
    r = acao({"acao": "pendentes"}, chave=funcao)
    assert r.status_code == 200 and r.json()["enviados"] == 1
    assert resp.execute("select situacao from radar_respostas_registro where id = %s", (rid,)).fetchone()[0] == "enviado"


def test_sem_a_pagina_gravada_a_publica_sai_e_a_privada_fica_anotada(resp):
    resp.execute("truncate radar_respostas_contas restart identity cascade")
    assert webhook(aviso_instagram(comentario="115")).status_code == 200
    situacao, privada, erro = resp.execute(
        "select situacao, privada_ok, erro from radar_respostas_registro where comentario_id = '115'").fetchone()
    assert situacao == "enviado" and privada is False and "Testar conexão" in erro
    assert [p["caminho"] for p in ESTADO["meta"]] == ["115/replies"]


# ------------------------------------------------------------------------------------- as ações
def test_acoes_exigem_a_chave_ou_o_administrador(resp, funcao):
    assert acao({"acao": "agenda_teste"}).status_code == 401
    assert acao({"acao": "agenda_teste"}, chave="x" * 64).status_code == 401
    r = acao({"acao": "agenda_teste"}, chave=funcao)
    assert (r.status_code, r.json()) == (200, {"ok": True, "versao": "0.35.4"})
    assert acao({"acao": "diagnostico"}, chave=funcao).status_code == 403            # o Testar conexão é só do administrador
    assert acao({"acao": "diagnostico"}, uid=EDITOR).status_code == 403
    assert acao({"acao": "qualquer"}, chave=funcao).status_code == 400


def test_diagnostico_grava_as_contas(resp):
    resp.execute("truncate radar_respostas_contas restart identity cascade")
    r = acao({"acao": "diagnostico"}, uid=ADMIN)
    assert r.status_code == 200
    dados = r.json()
    assert dados["ok"] is True and {c["rede"] for c in dados["contas"]} == {"facebook", "instagram"}
    assert resp.execute("select conta_id from radar_respostas_contas where rede = 'facebook'").fetchone()[0] == PAGINA
    assert resp.execute("select nome from radar_respostas_contas where rede = 'instagram'").fetchone()[0] == "artecon.teste"
    assert dados["pagina_inscrita"] is True                                          # v0.35.2: o app inscrito na própria página
    assert [p["caminho"] for p in ESTADO["meta"]] == ["me", f"{PAGINA}/subscribed_apps"]
    assert ESTADO["meta"][1]["corpo"] == {"subscribed_fields": "feed"}
    ESTADO["erro_me"] = (190, "Error validating access token: Session has expired")
    r = acao({"acao": "diagnostico"}, uid=ADMIN)
    assert r.status_code == 503 and "Meta 190" in r.json()["message"]


def test_diagnostico_nao_da_alarme_falso_na_chave_do_instagram(resp, tmp_path):
    """v0.35.4: com os números dos apps, o veredito diz qual segredo confere com qual app. O app principal confere na Graph do
    Facebook; a "Chave secreta do app do Instagram" a Graph do Facebook NÃO reconhece — e, em vez de pedir recópia (o alarme
    falso), o aviso diz que a chave está salva, conferida pela Meta só na hora do comentário. A chave nunca vai para o registro."""
    resp.execute("truncate radar_respostas_contas restart identity cascade")
    porta = 3955
    with open(tmp_path / "apps.log", "wb") as registro:
        proc = _subir(porta, {"META_APP_SECRET": APP_SECRET, "META_VERIFY_TOKEN": VERIFY, "META_PAGE_TOKEN": TOKEN_PAGINA,
                              "SUPABASE_SERVICE_ROLE_KEY": SECRETA, "SUPABASE_SECRET_KEYS": json.dumps({"default": SECRETA}),
                              "META_APP_ID": APP_ID, "META_APP_ID_2": APP_ID_2,
                              "META_APP_SECRET_2": "chave-do-instagram-que-a-graph-fb-ignora",
                              "META_INSTAGRAM_GRAPH_URL": PONTE + "/meta"}, registro)
        try:
            r = acao({"acao": "diagnostico"}, uid=ADMIN, porta=porta)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    assert r.status_code == 200 and r.json()["ok"] is True
    avisos = r.json()["avisos"]
    assert f"App {APP_ID}: o META_APP_SECRET confere." in avisos                 # o principal confere na Graph do Facebook
    ig = [a for a in avisos if a.startswith(f"App {APP_ID_2}")]
    assert len(ig) == 1 and "está salva" in ig[0] and "não precisa recopiar" in ig[0]
    assert all("recopie na Meta" not in a for a in avisos)                       # nunca mais o alarme falso
    assert "chave-do-instagram-que-a-graph-fb-ignora" not in \
        (tmp_path / "apps.log").read_text(encoding="utf-8", errors="replace")    # a chave nunca no registro


def test_token_do_usuario_de_sistema_troca_sozinho(resp, tmp_path):
    """v0.35.1: com o token do USUÁRIO DE SISTEMA em META_PAGE_TOKEN, a função troca sozinha pelo da página (GET /me/accounts,
    token só no cabeçalho) e o Testar conexão passa; o registro (log) continua sem token nenhum."""
    resp.execute("truncate radar_respostas_contas restart identity cascade")
    porta = 3956
    with open(tmp_path / "usuario.log", "wb") as registro:
        proc = _subir(porta, {"META_APP_SECRET": APP_SECRET, "META_VERIFY_TOKEN": VERIFY, "META_PAGE_TOKEN": TOKEN_USUARIO,
                              "SUPABASE_SERVICE_ROLE_KEY": SECRETA, "SUPABASE_SECRET_KEYS": json.dumps({"default": SECRETA})},
                      registro)
        try:
            r = acao({"acao": "diagnostico"}, uid=ADMIN, porta=porta)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert {c["rede"] for c in r.json()["contas"]} == {"facebook", "instagram"}
    assert resp.execute("select conta_id from radar_respostas_contas where rede = 'facebook'").fetchone()[0] == PAGINA
    trocas = [p for p in ESTADO["meta"] if p["caminho"] == "me/accounts"]
    assert trocas and all(p["auth"] == "Bearer " + TOKEN_USUARIO and TOKEN_USUARIO not in p["query"] for p in trocas)
    assert [p for p in ESTADO["meta"] if p["caminho"] == "me"][-1]["auth"] == "Bearer " + TOKEN_PAGINA   # o /me já vai trocado
    texto = (tmp_path / "usuario.log").read_text(encoding="utf-8", errors="replace")
    assert TOKEN_USUARIO not in texto and TOKEN_PAGINA not in texto


def test_pendentes_envia_a_fila_dentro_da_folga(resp, funcao):
    resp.execute("""insert into radar_respostas_registro (gatilho_id, rede, comentario_id, situacao)
                    values (1, 'instagram', '301', 'pendente'), (1, 'instagram', '302', 'pendente')""")
    r = acao({"acao": "pendentes"}, chave=funcao)
    assert r.status_code == 200
    dados = r.json()
    assert (dados["pendentes"], dados["enviados"], dados["erros"]) == (2, 2, 0)
    assert resp.execute("select count(*) from radar_respostas_registro where situacao = 'enviado'").fetchone()[0] == 2
    r = acao({"acao": "pendentes"}, chave=funcao)
    assert r.json()["pendentes"] == 0                                                # fila vazia: nada a fazer
