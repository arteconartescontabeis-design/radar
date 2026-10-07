"""Função radar-redes (v0.13.0) rodando de verdade no Deno, com o banco real (PostgREST), uma Meta (Graph API) de mentira
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

from conftest import ADMIN, API, EDITOR, RAIZ, como, jwt
from test_radar_banco import aprovar, cenario_publicavel, registrar_site

PORTA_PONTE, PORTA_FUNCAO, PORTA_SEM_META = 3994, 3993, 3995
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
TOKEN = "EAAtokenSecreto123"
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()
ESTADO = {"meta": [], "storage": [], "buckets": set(), "erro_meta": None, "status_ig": ["IN_PROGRESS", "FINISHED"], "cai_publicar": False}


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST; /storage/v1 → armazenamento; /meta → Graph API."""
    def _responder(self, status, corpo):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _rest(self):
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)) or None
        cab = {k: v for k, v in self.headers.items() if k.lower() in ("authorization", "content-type", "prefer")}
        r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo, timeout=30)
        self._responder(r.status_code, r.content)

    def _meta(self, params):
        ESTADO["meta"].append((self.command, urlparse(self.path).path.removeprefix("/meta/"), params))
        if params.get("access_token") != TOKEN:
            return self._responder(400, {"error": {"code": 190, "message": "Invalid OAuth access token"}})
        if ESTADO["erro_meta"]:
            return self._responder(400, {"error": {"code": 10, "message": ESTADO["erro_meta"] + " " + TOKEN}})
        caminho = urlparse(self.path).path.removeprefix("/meta/")
        if self.command == "GET":
            if caminho == "cont-1":
                return self._responder(200, {"status_code": ESTADO["status_ig"].pop(0) if len(ESTADO["status_ig"]) > 1 else ESTADO["status_ig"][0]})
            if caminho == "midia-1":
                return self._responder(200, {"permalink": "https://www.instagram.com/p/ABC123/"})
            if caminho == "pagina-1_post-9":
                return self._responder(200, {"permalink_url": "https://www.facebook.com/artecon/posts/9"})
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
            nome = self.path.rsplit("/", 1)[1]
            return self._responder(200 if nome in ESTADO["buckets"] else 404, {"name": nome} if nome in ESTADO["buckets"] else {"error": "Bucket not found"})
        if self.path.startswith("/meta/"):
            return self._meta({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
        self._responder(404, {})

    def do_POST(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/storage/v1/bucket":
            b = json.loads(corpo)
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
                    RADAR_PORTA_LOCAL=str(porta), NO_COLOR="1", **extra)
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
    com = _subir(PORTA_FUNCAO, {"META_PAGE_ID": "pagina-1", "META_PAGE_TOKEN": TOKEN, "META_IG_USER_ID": "ig-1"})
    sem = _subir(PORTA_SEM_META, {})
    yield
    com.terminate()
    sem.terminate()
    ponte.shutdown()


@pytest.fixture()
def redes(funcao, limpo):
    ESTADO.update(meta=[], storage=[], buckets=set(), erro_meta=None, status_ig=["IN_PROGRESS", "FINISHED"], cai_publicar=False)
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
    assert status == 502 and "instagram_content_publish" in r["message"] and TOKEN not in json.dumps(r)
    sit, erro = db.execute("select situacao, erro from radar_redes_envios where id = %s", (envio,)).fetchone()
    assert sit == "erro" and "permission" in erro and TOKEN not in erro
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
    assert [i["detalhe"] for i in r["itens"][1:3]] == ["Artecon Contábeis", "@arteconcontabeis"]


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
