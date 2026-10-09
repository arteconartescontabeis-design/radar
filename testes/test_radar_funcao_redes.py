"""Função radar-redes (v0.13.0; v0.14.1: token do usuário do sistema; v0.14.2: chave interna nova do Supabase) rodando de verdade no Deno, com o banco real (PostgREST), uma Meta (Graph API) de mentira
e um armazenamento (Supabase Storage) de mentira. Sem o Deno instalado, o arquivo é pulado.

Confere: só o administrador chama; sem os segredos da Meta a autorização continua guardada; o Instagram publica em
duas etapas (contêiner + media_publish) e o Facebook pela foto da Página; a imagem vai para o armazenamento público;
o link do post fica registrado; o erro da Meta fica na autorização sem mostrar o token; e nunca publica duas vezes.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from conftest import ADMIN, API, EDITOR, RAIZ, SECRETA, como, gateway, jwt
from test_radar_banco import aprovar, cenario_publicavel, registrar_site

PORTA_PONTE, PORTA_FUNCAO, PORTA_SEM_META, PORTA_TOKEN_PAGINA, PORTA_SEM_ACESSO = 3994, 3993, 3995, 3996, 3997
PORTA_CHAVE_NOVA, PORTA_LISTA_NOVA = 3988, 3987
PORTA_IG_TOKEN, PORTA_IG_SEM_ID = 3986, 3985               # v0.14.4: META_IG_TOKEN; e sem o META_IG_USER_ID          # v0.14.2: SUPABASE_SERVICE_ROLE_KEY = sb_secret_…; SUPABASE_SECRET_KEYS
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
TOKEN = "EAAtokenSecreto123"                  # token do usuário do sistema (o que fica no META_PAGE_TOKEN)
TOKEN_PAGINA = "EAApaginaSecreta456"          # token da Página, que a Meta devolve para o token do usuário do sistema
TOKEN_OUTRO = "EAAsemAcesso789"               # usuário do sistema sem a Página atribuída
TOKEN_IG = "EAAinstagramSecreto321"           # v0.14.4: token gerado no aplicativo do Instagram (META_IG_TOKEN)
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()
ESTADO = {"chaves": [], "bucket_get_falha": False, "busca_token": [], "meta": [], "storage": [], "buckets": set(), "erro_meta": None, "status_ig": ["IN_PROGRESS", "FINISHED"], "cai_publicar": False}


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST; /storage/v1 → armazenamento; /meta → Graph API."""
    def _responder(self, status, corpo):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _anotar(self):
        apikey, auth = self.headers.get("apikey") or "", self.headers.get("Authorization") or ""
        ESTADO["chaves"].append((self.command, self.path.split("?")[0], apikey[:10], auth.removeprefix("Bearer ")[:10]))

    def _armazenamento_ok(self):
        """O armazenamento de verdade: chave nova no Authorization → 400 "Invalid Compact JWS"; sem a chave interna → sem permissão."""
        self._anotar()
        auth = gateway(self.headers)
        if auth is None:
            self._responder(400, {"statusCode": "403", "error": "Unauthorized", "message": "Invalid Compact JWS"})
            return False
        if auth != "Bearer " + jwt("service_role"):
            self._responder(400, {"statusCode": "403", "error": "Unauthorized", "message": "new row violates row-level security policy"})
            return False
        return True

    def _rest(self):
        self._anotar()
        auth = gateway(self.headers)
        if auth is None:
            return self._responder(401, {"message": "Invalid Compact JWS"})
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        cab = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "prefer")} | ({"Authorization": auth} if auth else {})
        r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo, timeout=30)
        self._responder(r.status_code, r.content)

    def _meta(self, params):
        caminho = urlparse(self.path).path.removeprefix("/meta/")
        tk = params.get("access_token")
        # troca do token do usuário do sistema pelo da Página (e "quem sou eu")
        if self.command == "GET" and (params.get("fields") == "access_token" or caminho == "me"):
            ESTADO["busca_token"].append((caminho, tk))
            if caminho == "me":
                ids = {TOKEN: "sistema-1", TOKEN_PAGINA: "pagina-1", TOKEN_OUTRO: "sistema-2"}
                return self._responder(200, {"id": ids[tk]}) if tk in ids else self._responder(400, {"error": {"code": 190, "message": "Invalid OAuth access token"}})
            if caminho == "pagina-1" and tk == TOKEN:
                return self._responder(200, {"access_token": TOKEN_PAGINA, "id": "pagina-1"})
            if caminho == "pagina-1" and tk == TOKEN_PAGINA:
                return self._responder(200, {"access_token": TOKEN_PAGINA, "id": "pagina-1"})
            return self._responder(400, {"error": {"code": 100, "message": "Unsupported get request"}})
        ESTADO["meta"].append((self.command, caminho, params))
        if tk not in (TOKEN_PAGINA, TOKEN_IG):
            return self._responder(400, {"error": {"code": 190, "message": "Invalid OAuth access token"}})
        if ESTADO["erro_meta"]:
            return self._responder(400, {"error": {"code": 10, "message": ESTADO["erro_meta"] + " " + TOKEN + " " + TOKEN_PAGINA}})
        if self.command == "DELETE":                                       # v0.17.0: exclusão do post
            if caminho in ("midia-1", "pagina-1_post-9"):
                return self._responder(200, {"success": True})
            return self._responder(400, {"error": {"code": 100, "message": "Unsupported delete request."}})
        if self.command == "GET":
            if caminho == "cont-1":
                return self._responder(200, {"status_code": ESTADO["status_ig"].pop(0) if len(ESTADO["status_ig"]) > 1 else ESTADO["status_ig"][0]})
            if caminho == "midia-1":
                return self._responder(200, {"permalink": "https://www.instagram.com/p/ABC123/"})
            if caminho == "pagina-1_post-9":
                return self._responder(200, {"permalink_url": "https://www.facebook.com/artecon/posts/9"})
            if caminho == "pagina-1" and params.get("fields", "").startswith("instagram_business_account"):
                return self._responder(200, {"instagram_business_account": {"id": "ig-1", "username": "arteconcontabeis"}, "id": "pagina-1"})
            if caminho == "pagina-1":
                return self._responder(200, {"name": "Artecon Contábeis"})
            if caminho == "ig-1":
                return self._responder(200, {"username": "arteconcontabeis"})
        if caminho == "ig-1/media":
            return self._responder(200, {"id": "cont-1"})
        if caminho == "ig-1/media_publish":
            if ESTADO["cai_publicar"]:
                return self._responder(503, {"error": {"code": 2, "message": "Service temporarily unavailable"}})
            return self._responder(200, {"id": "midia-1"})
        if caminho == "pagina-1/photos":
            return self._responder(200, {"id": "foto-9", "post_id": "pagina-1_post-9"})
        self._responder(404, {"error": {"code": 803, "message": "não existe"}})

    def do_GET(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path.startswith("/storage/v1/bucket/"):
            if not self._armazenamento_ok():
                return
            nome = self.path.rsplit("/", 1)[1]
            if ESTADO["bucket_get_falha"]:
                return self._responder(400, {"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"})
            return self._responder(200 if nome in ESTADO["buckets"] else 404, {"name": nome} if nome in ESTADO["buckets"] else {"error": "Bucket not found"})
        if self.path.startswith("/meta/"):
            return self._meta({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
        self._responder(404, {})

    def do_DELETE(self):
        if self.path.startswith("/meta/"):
            return self._meta({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
        self._responder(404, {})

    def do_POST(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path.startswith("/storage/v1/") and not self._armazenamento_ok():
            return
        if self.path == "/storage/v1/bucket":
            b = json.loads(corpo)
            if b["id"] in ESTADO["buckets"]:                                      # já existe: o Supabase responde 400 com "409"
                return self._responder(400, {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"})
            ESTADO["buckets"].add(b["id"])
            assert b["public"] is True
            return self._responder(200, {"name": b["id"]})
        if self.path.startswith("/storage/v1/object/"):
            ESTADO["storage"].append((self.path, self.headers.get("Content-Type"), corpo))
            return self._responder(200, {"Key": self.path})
        if self.path.startswith("/meta/"):
            return self._meta({k: v[0] for k, v in parse_qs(corpo.decode()).items()})
        self._responder(404, {})

    def log_message(self, *a):
        pass


def _subir(porta, extra):
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), SUPABASE_SERVICE_ROLE_KEY=jwt("service_role"),
                    META_GRAPH_URL=PONTE + "/meta", RADAR_REDES_PASSO_MS="50", RADAR_REDES_ESPERA_MS="2000",
                    RADAR_PORTA_LOCAL=str(porta), NO_COLOR="1")
    ambiente.pop("SUPABASE_SECRET_KEYS", None)                  # só o que o teste pedir
    ambiente.update(extra)
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                             str(RAIZ / "supabase" / "functions" / "radar-redes" / "index.ts")],
                            env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(150):
        try:
            requests.options(f"http://127.0.0.1:{porta}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.2)
    return proc


@pytest.fixture(scope="module")
def funcao(api_postgrest):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    meta_ok = {"META_PAGE_ID": "pagina-1", "META_PAGE_TOKEN": TOKEN, "META_IG_USER_ID": "ig-1"}
    processos = []                    # encerrados mesmo se a subida de um deles falhar (senão ficam presos nas portas dos outros testes)
    try:
        for porta, extra in ((PORTA_FUNCAO, meta_ok), (PORTA_SEM_META, {}),
                             (PORTA_TOKEN_PAGINA, {**meta_ok, "META_PAGE_TOKEN": TOKEN_PAGINA}),
                             (PORTA_SEM_ACESSO, {**meta_ok, "META_PAGE_TOKEN": TOKEN_OUTRO}),
                             (PORTA_CHAVE_NOVA, {**meta_ok, "SUPABASE_SERVICE_ROLE_KEY": SECRETA}),        # como no projeto da Artecon
                             (PORTA_LISTA_NOVA, {**meta_ok, "SUPABASE_SECRET_KEYS": json.dumps({"default": SECRETA})}),  # a antiga ainda é JWT
                             (PORTA_IG_TOKEN, {**meta_ok, "META_IG_TOKEN": TOKEN_IG}),
                             (PORTA_IG_SEM_ID, {"META_PAGE_ID": "pagina-1", "META_PAGE_TOKEN": TOKEN, "META_IG_TOKEN": TOKEN_IG})):
            processos.append(_subir(porta, extra))
        yield
    finally:
        for p in processos:
            p.terminate()
        ponte.shutdown()
        ponte.server_close()          # libera a porta na hora: outro módulo de teste usa a mesma


@pytest.fixture()
def redes(funcao, limpo):
    ESTADO.update(chaves=[], bucket_get_falha=False, busca_token=[], meta=[], storage=[], buckets=set(), erro_meta=None, status_ig=["IN_PROGRESS", "FINISHED"], cai_publicar=False)
    a, c1 = cenario_publicavel(limpo)
    aprovar(c1)
    registrar_site(c1)
    yield limpo, c1


def autorizar(db, c1, canal):
    lido = db.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        return c.execute("select radar_autorizar_rede(%s, %s, %s, %s, %s)",
                         (c1, canal, "Prazo do Simples prorrogado. Leia no site da Artecon.", JPEG, lido)).fetchone()[0]


def pedir(corpo, uid=ADMIN, porta=PORTA_FUNCAO, cab=None):
    cab = cab if cab is not None else {"Authorization": "Bearer " + jwt("authenticated", uid)}
    r = requests.post(f"http://127.0.0.1:{porta}/", timeout=60, json=corpo, headers=cab)
    return r.status_code, r.json()


def test_instagram_publica_em_duas_etapas_com_a_imagem_no_armazenamento_publico(redes):
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 200 and r == {"situacao": "publicado", "url": "https://www.instagram.com/p/ABC123/", "post_id": "midia-1"}, r
    caminho, tipo, dados = ESTADO["storage"][0]
    assert caminho == f"/storage/v1/object/radar-redes/{c1}-instagram-{envio}.jpg" and tipo == "image/jpeg" and dados.startswith(b"\xff\xd8")
    assert "radar-redes" in ESTADO["buckets"]                                   # o bucket público é criado na primeira vez
    chamadas = [(m, p) for m, p, _ in ESTADO["meta"]]
    assert chamadas == [("POST", "ig-1/media"), ("GET", "cont-1"), ("GET", "cont-1"), ("POST", "ig-1/media_publish"), ("GET", "midia-1")]
    criar = ESTADO["meta"][0][2]
    assert criar["image_url"] == f"{PONTE}/storage/v1/object/public/radar-redes/{c1}-instagram-{envio}.jpg"
    assert criar["caption"].startswith("Prazo do Simples") and ESTADO["meta"][3][2]["creation_id"] == "cont-1"
    linha = db.execute("select situacao, post_id, url, imagem, imagem_url from radar_redes_envios where id = %s", (envio,)).fetchone()
    assert linha[:4] == ("publicado", "midia-1", "https://www.instagram.com/p/ABC123/", None) and linha[4].endswith(".jpg")
    # de novo: não publica duas vezes
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 400 and "não está aguardando envio" in r["message"] and len(ESTADO["meta"]) == 5


def test_facebook_publica_a_foto_na_pagina_com_a_legenda(redes):
    db, c1 = redes
    envio = autorizar(db, c1, "facebook")
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 200 and r["url"] == "https://www.facebook.com/artecon/posts/9" and r["post_id"] == "pagina-1_post-9"
    metodo, caminho, params = ESTADO["meta"][0]
    assert (metodo, caminho) == ("POST", "pagina-1/photos") and params["message"].startswith("Prazo") and params["url"].endswith(".jpg")


def test_erro_da_meta_fica_na_autorizacao_sem_o_token_e_a_nova_tentativa_reaproveita_a_imagem(redes):
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    ESTADO["erro_meta"] = "Application does not have permission"
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 502 and "instagram_content_publish" in r["message"] and TOKEN not in json.dumps(r) and TOKEN_PAGINA not in json.dumps(r)
    sit, erro = db.execute("select situacao, erro from radar_redes_envios where id = %s", (envio,)).fetchone()
    assert sit == "erro" and "permission" in erro and TOKEN not in erro and TOKEN_PAGINA not in erro
    ESTADO["erro_meta"] = None
    status, r = pedir({"acao": "publicar", "envio": envio})                      # tentar de novo
    assert status == 200 and r["situacao"] == "publicado" and len(ESTADO["storage"]) == 1   # a imagem não sobe de novo


def test_sem_os_segredos_da_meta_a_autorizacao_continua_guardada(redes):
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    status, r = pedir({"acao": "publicar", "envio": envio}, porta=PORTA_SEM_META)
    assert status == 503 and "META_PAGE_ID" in r["message"] and "continua guardada" in r["message"]
    assert db.execute("select situacao from radar_redes_envios where id = %s", (envio,)).fetchone()[0] == "autorizado"
    status, r = pedir({"acao": "diagnostico"}, porta=PORTA_SEM_META)
    assert status == 200 and r["tudo_certo"] is False and "Faltam" in r["itens"][0]["detalhe"]


def test_so_o_administrador_e_o_diagnostico_confere_pagina_e_conta(redes):
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    assert pedir({"acao": "publicar", "envio": envio}, uid=EDITOR)[0] == 403
    assert pedir({"acao": "publicar", "envio": envio}, cab={})[0] == 401
    assert ESTADO["meta"] == [] and db.execute("select situacao from radar_redes_envios where id = %s", (envio,)).fetchone()[0] == "autorizado"
    status, r = pedir({"acao": "diagnostico"})
    assert status == 200 and r["tudo_certo"] is True
    assert [i["detalhe"] for i in r["itens"][1:4]] == ["token da Página obtido pelo token do usuário do sistema", "Artecon Contábeis", "@arteconcontabeis (pelo token da Página)"]


def test_sem_resposta_clara_da_publicacao_nao_deixa_tentar_de_novo(redes):
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    ESTADO["cai_publicar"] = True                                               # a Meta caiu no meio do media_publish: pode ter saído
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 504 and "Confira na rede" in r["message"]
    assert db.execute("select situacao from radar_redes_envios where id = %s", (envio,)).fetchone()[0] == "enviando"
    ESTADO["cai_publicar"] = False
    status, r = pedir({"acao": "publicar", "envio": envio})                      # o mesmo botão não publica de novo
    assert status == 400 and "não está aguardando envio" in r["message"]
    assert [p for m, p, _ in ESTADO["meta"]].count("ig-1/media_publish") == 1


# ------------------------------------------------ v0.14.1: o META_PAGE_TOKEN pode ser o token do usuário do sistema
def test_token_do_usuario_do_sistema_vira_token_da_pagina_e_e_buscado_uma_vez_so(redes):
    db, c1 = redes
    for canal in ("facebook", "instagram"):
        status, r = pedir({"acao": "publicar", "envio": autorizar(db, c1, canal)})
        assert status == 200 and r["situacao"] == "publicado", r
    # toda chamada de publicação usou o token da Página; o do usuário do sistema só serviu para buscá-lo
    assert ESTADO["meta"] and all(p["access_token"] == TOKEN_PAGINA for _, _, p in ESTADO["meta"])
    assert all(tk == TOKEN for _, tk in ESTADO["busca_token"]) and len(ESTADO["busca_token"]) <= 1   # guardado entre os pedidos


def test_token_da_propria_pagina_continua_valendo(redes):
    db, c1 = redes
    status, r = pedir({"acao": "diagnostico"}, porta=PORTA_TOKEN_PAGINA)
    assert status == 200 and r["tudo_certo"] is True and r["itens"][1]["detalhe"] == "META_PAGE_TOKEN é o token da própria Página"
    status, r = pedir({"acao": "publicar", "envio": autorizar(db, c1, "facebook")}, porta=PORTA_TOKEN_PAGINA)
    assert status == 200 and r["situacao"] == "publicado"


def test_token_que_nao_alcanca_a_pagina_para_antes_de_publicar_e_explica(redes):
    db, c1 = redes
    status, r = pedir({"acao": "diagnostico"}, porta=PORTA_SEM_ACESSO)
    assert status == 200 and r["tudo_certo"] is False
    assert r["itens"][1]["ok"] is False and "Atribuir ativos" in r["itens"][1]["detalhe"]
    envio = autorizar(db, c1, "facebook")
    status, r = pedir({"acao": "publicar", "envio": envio}, porta=PORTA_SEM_ACESSO)
    assert status == 502 and "não alcança a Página" in r["message"] and TOKEN_OUTRO not in json.dumps(r)
    assert not [c for c in ESTADO["meta"] if c[1] == "pagina-1/photos"]            # nada foi pedido para publicar
    assert db.execute("select situacao from radar_redes_envios where id = %s", (envio,)).fetchone()[0] == "erro"   # dá para tentar de novo


# ------------------------------------------------ v0.14.2: chave interna nova do Supabase (sb_secret_…)
def _so_no_apikey():
    """Chamadas com a chave interna: a nova vai só no apikey, nunca no Authorization."""
    internas = [c for c in ESTADO["chaves"] if c[2].startswith("sb_secret_")]
    assert internas and all(not auth.startswith("sb_") for *_, auth in ESTADO["chaves"])
    return internas


@pytest.mark.parametrize("porta", [PORTA_CHAVE_NOVA, PORTA_LISTA_NOVA], ids=["service_role_key-nova", "secret_keys"])
def test_chave_interna_nova_vai_so_no_apikey_e_o_armazenamento_funciona(redes, porta):
    db, c1 = redes
    status, r = pedir({"acao": "diagnostico"}, porta=porta)
    assert status == 200 and r["itens"][-1] == {"item": "Armazenamento das imagens", "ok": True, "detalhe": 'bucket público "radar-redes"'}
    envio = autorizar(db, c1, "facebook")
    status, r = pedir({"acao": "publicar", "envio": envio}, porta=porta)
    assert status == 200 and r["situacao"] == "publicado", r
    caminhos = {c[1] for c in _so_no_apikey()}
    assert "/rest/v1/rpc/radar_rede_iniciar" in caminhos and "/rest/v1/rpc/radar_rede_concluir" in caminhos
    assert any(c.startswith("/storage/v1/object/radar-redes/") for c in caminhos)
    assert db.execute("select situacao from radar_redes_envios where id = %s", (envio,)).fetchone()[0] == "publicado"


def test_chave_antiga_continua_nos_dois_cabecalhos_e_bucket_que_ja_existe_nao_e_erro(redes):
    db, c1 = redes
    ESTADO["buckets"].add("radar-redes")
    ESTADO["bucket_get_falha"] = True                         # a consulta falhou, mas o bucket existe: o Supabase responde "409"
    status, r = pedir({"acao": "diagnostico"})
    assert status == 200 and r["itens"][-1]["ok"] is True, r
    assert all(ak == jwt("service_role")[:10] and auth == ak for _, caminho, ak, auth in ESTADO["chaves"] if caminho.startswith("/storage/"))


# ------------------------------------------------ v0.14.4: token próprio do Instagram (META_IG_TOKEN)
def test_instagram_usa_o_meta_ig_token_e_o_facebook_continua_com_o_da_pagina(redes):
    db, c1 = redes
    for canal in ("instagram", "facebook"):
        status, r = pedir({"acao": "publicar", "envio": autorizar(db, c1, canal)}, porta=PORTA_IG_TOKEN)
        assert status == 200 and r["situacao"] == "publicado", r
    usados = {(m, p): prm["access_token"] for m, p, prm in ESTADO["meta"]}
    assert usados[("POST", "ig-1/media")] == TOKEN_IG and usados[("POST", "ig-1/media_publish")] == TOKEN_IG
    assert usados[("POST", "pagina-1/photos")] == TOKEN_PAGINA
    status, r = pedir({"acao": "diagnostico"}, porta=PORTA_IG_TOKEN)
    assert r["tudo_certo"] is True and "@arteconcontabeis (pelo META_IG_TOKEN)" in [i["detalhe"] for i in r["itens"]]


def test_sem_o_ig_user_id_o_diagnostico_mostra_o_numero_a_gravar(redes):
    status, r = pedir({"acao": "diagnostico"}, porta=PORTA_IG_SEM_ID)
    conta = next(i for i in r["itens"] if i["item"] == "Conta do Instagram")
    assert conta["ok"] is False and "META_IG_USER_ID = ig-1" in conta["detalhe"] and "@arteconcontabeis" in conta["detalhe"]
    assert TOKEN_IG not in json.dumps(r)



# ------------------------------------------------------------------- v0.17.0: excluir e o robô do "Publicar em todos"
def test_excluir_apaga_na_meta_e_registra(redes):
    db, c1 = redes
    ig, fb = autorizar(db, c1, "instagram"), None
    assert pedir({"acao": "publicar", "envio": ig})[0] == 200
    fb = autorizar(db, c1, "facebook")
    assert pedir({"acao": "publicar", "envio": fb})[0] == 200
    assert pedir({"acao": "excluir", "envio": ig}, uid=EDITOR)[0] == 403           # só o administrador
    assert pedir({"acao": "excluir", "envio": ig}) == (200, {"situacao": "excluido", "canal": "instagram"})
    assert pedir({"acao": "excluir", "envio": fb}) == (200, {"situacao": "excluido", "canal": "facebook"})
    apagados = [(m[1], m[2]["access_token"]) for m in ESTADO["meta"] if m[0] == "DELETE"]
    assert apagados == [("midia-1", TOKEN_PAGINA), ("pagina-1_post-9", TOKEN_PAGINA)]
    linhas = db.execute("select situacao, excluido_como, excluido_por::text from radar_redes_envios where id in (%s, %s) order by id", (ig, fb)).fetchall()
    assert linhas == [("excluido", "api", ADMIN)] * 2
    st, r = pedir({"acao": "excluir", "envio": ig})
    assert st == 400 and "não está publicada" in r["message"]


def test_excluir_que_a_meta_recusa_fica_publicado_e_explica(redes):
    db, c1 = redes
    ig = autorizar(db, c1, "instagram")
    assert pedir({"acao": "publicar", "envio": ig})[0] == 200
    ESTADO["erro_meta"] = "Unsupported delete request."
    st, r = pedir({"acao": "excluir", "envio": ig})
    assert st == 502 and "Já apaguei" in r["message"] and TOKEN not in r["message"] and TOKEN_PAGINA not in r["message"]
    assert db.execute("select situacao from radar_redes_envios where id = %s", (ig,)).fetchone()[0] == "publicado"


def test_robo_so_publica_o_que_foi_autorizado_junto_com_o_site(redes):
    db, c1 = redes
    robo = {"Authorization": "Bearer " + jwt("service_role"), "apikey": jwt("service_role")}
    avulsa = autorizar(db, c1, "instagram")                                         # autorização comum: só o administrador manda
    st, r = pedir({"acao": "publicar", "envio": avulsa}, cab=robo)
    assert st == 403 and "junto com o site" in r["message"]
    assert db.execute("select situacao from radar_redes_envios where id = %s", (avulsa,)).fetchone()[0] == "autorizado"
    # "Publicar em todos" de outro conteúdo: depois que a notícia entra no site, o robô manda publicar
    a2, c2 = cenario_publicavel(db, slug_fonte="rfb-noticias")
    aprovar(c2)
    lido = db.execute("select atualizado_em from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        r = c.execute("select radar_autorizar_todos(%s, 'Tributário', %s, %s, null, %s)",
                      (c2, lido, JPEG, "Leia a matéria completa: {LINK DO SITE}")).fetchone()[0]
    registrar_site(c2, url="https://artecon.cnt.br/news/view/todos")
    st, res = pedir({"acao": "publicar", "envio": r["facebook"]}, cab=robo)
    assert (st, res["situacao"]) == (200, "publicado")
    publicado = [m for m in ESTADO["meta"] if m[1] == "pagina-1/photos"][-1][2]
    assert publicado["message"] == "Leia a matéria completa: https://artecon.cnt.br/news/view/todos"
    for corpo in ({"acao": "excluir", "envio": r["facebook"]}, {"acao": "diagnostico"}):      # o robô só publica
        assert pedir(corpo, cab=robo)[0] == 403
    assert pedir({"acao": "publicar", "envio": r["facebook"]}, cab={"Authorization": "Bearer " + jwt("anon")})[0] in (401, 403)



def test_robo_com_a_chave_antiga_e_aceito_quando_a_funcao_tem_a_chave_nova(redes):
    """Como na Artecon: a função tem a chave interna nova (sb_secret) e o robô do GitHub usa a antiga (JWT service_role).
    Quem confere a chave do robô é o banco; uma chave falsificada com o papel service_role é recusada."""
    import jwt as pyjwt
    db, c1 = redes
    a2, c2 = cenario_publicavel(db, slug_fonte="rfb-noticias")
    aprovar(c2)
    lido = db.execute("select atualizado_em from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        r = c.execute("select radar_autorizar_todos(%s, 'Tributário', %s, %s, null, %s)", (c2, lido, JPEG, "Leia: {LINK DO SITE}")).fetchone()[0]
    registrar_site(c2, url="https://artecon.cnt.br/news/view/chave")
    falsa = pyjwt.encode({"role": "service_role", "iss": "supabase"}, "outro-segredo-qualquer-com-32-caracteres", algorithm="HS256")
    st, res = pedir({"acao": "publicar", "envio": r["facebook"]}, porta=PORTA_CHAVE_NOVA, cab={"Authorization": "Bearer " + falsa, "apikey": falsa})
    assert st in (401, 403) and db.execute("select situacao from radar_redes_envios where id = %s", (r["facebook"],)).fetchone()[0] == "autorizado"
    robo = {"Authorization": "Bearer " + jwt("service_role"), "apikey": jwt("service_role")}
    st, res = pedir({"acao": "publicar", "envio": r["facebook"]}, porta=PORTA_CHAVE_NOVA, cab=robo)
    assert (st, res["situacao"]) == (200, "publicado")
