"""Função radar-redes (v0.13.0; v0.14.1: token do usuário do sistema; v0.14.2: chave interna nova do Supabase) rodando de verdade no Deno, com o banco real (PostgREST), uma Meta (Graph API) de mentira
e um armazenamento (Supabase Storage) de mentira. Sem o Deno instalado, o arquivo é pulado.

Confere: só o administrador chama; sem os segredos da Meta a autorização continua guardada; o Instagram publica em
duas etapas (contêiner + media_publish) e o Facebook pela foto da Página; a imagem vai para o armazenamento público;
o link do post fica registrado; o erro da Meta fica na autorização sem mostrar o token; e nunca publica duas vezes.
v0.19.0: só o administrador aciona o robô do site no GitHub (uma API do GitHub de mentira), só com algo esperando o robô,
uma vez a cada 30 s e sem mostrar o token.
v0.21.0: a peça da Pauta vai para o armazenamento PRIVADO (nome aleatório) e a Meta recebe um link assinado de 10 min; no banco fica
o endereço interno, e a nova tentativa assina de novo sem reenviar. A agenda do banco (chave do Vault de mentira no x-radar-agenda)
só publica peça vencida, uma vez, e faz o teste da instalação (agenda_teste); a função nova publica a notícia com o banco antigo;
os registros da função não levam legenda, nome, link nem chave.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from conftest import ADMIN, API, EDITOR, RAIZ, SECRETA, VAULT_SIMULADO, como, gateway, jwt
from test_radar_banco import aprovar, cenario_publicavel, registrar_site
# v0.21.0: a Pauta (a fixture pauta põe o CNPJ e o CRC de mentira nas Configurações, como a Pauta exige)
from test_radar_banco import IDENT, LEG_PECA, aprovar_peca, lamina, marcar_pronta, nova_peca, pauta, situacao_envio, vencer  # noqa: F401

PORTA_PONTE, PORTA_FUNCAO, PORTA_SEM_META, PORTA_TOKEN_PAGINA, PORTA_SEM_ACESSO = 3994, 3993, 3995, 3996, 3997
PORTA_CHAVE_NOVA, PORTA_LISTA_NOVA = 3988, 3987
PUBLICA_NOVA = "sb_publishable_" + "Ab9_-x" * 6            # v0.22.0 (rodada 2): a chave pública nova do Supabase (de mentira)
PORTA_GITHUB = 3989                                         # v0.22.0 (rodada 2): os robôs agendados (a pausa de 30 s fica noutra instância)
PORTA_IG_TOKEN, PORTA_IG_SEM_ID = 3986, 3985               # v0.14.4: META_IG_TOKEN; e sem o META_IG_USER_ID          # v0.14.2: SUPABASE_SERVICE_ROLE_KEY = sb_secret_…; SUPABASE_SECRET_KEYS
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
TOKEN = "EAAtokenSecreto123"                  # token do usuário do sistema (o que fica no META_PAGE_TOKEN)
TOKEN_PAGINA = "EAApaginaSecreta456"          # token da Página, que a Meta devolve para o token do usuário do sistema
TOKEN_OUTRO = "EAAsemAcesso789"               # usuário do sistema sem a Página atribuída
TOKEN_IG = "EAAinstagramSecreto321"           # v0.14.4: token gerado no aplicativo do Instagram (META_IG_TOKEN)
TOKEN_GITHUB = "tokenGithubSecreto654"        # v0.19.0: RADAR_GITHUB_TOKEN, só na instância principal
CAMINHO_GITHUB = "/github/repos/arteconartescontabeis-design/radar/actions/workflows/radar-site-publicar.yml/dispatches"
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()
ESTADO = {"chaves": [], "bucket_get_falha": False, "busca_token": [], "meta": [], "storage": [], "buckets": set(), "erro_meta": None, "status_ig": ["IN_PROGRESS", "FINISHED"], "cai_publicar": False,
          "github": [], "github_status": 204, "workflows": {}, "github_wf": [],
          "publicos": set(), "upsert": [], "assinaturas": [], "assinar_falha": False, "apagados": [],   # v0.21.0: buckets públicos, x-upsert, links assinados
          "filhos_ig": [], "carrossel_ig": [], "fotos_fb": [], "feed_fb": []}                           # v0.42.0: o carrossel
LOGS: dict = {}                               # v0.21.0: a saída de cada instância da função (o que o Supabase mostra em Logs), por porta


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST; /storage/v1 → armazenamento; /meta → Graph API; /github → API do GitHub (v0.19.0)."""
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
            if caminho.startswith("cont-f") or caminho == "cont-car":        # v0.42.0: os contêineres do carrossel ficam prontos na hora
                return self._responder(200, {"status_code": "FINISHED"})
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
            # v0.42.0: o carrossel — um contêiner por lâmina (is_carousel_item) e o contêiner CAROUSEL (children + caption)
            if params.get("is_carousel_item") == "true":
                ESTADO["filhos_ig"].append(params)
                return self._responder(200, {"id": f"cont-f{len(ESTADO['filhos_ig'])}"})
            if params.get("media_type") == "CAROUSEL":
                ESTADO["carrossel_ig"].append(params)
                return self._responder(200, {"id": "cont-car"})
            return self._responder(200, {"id": "cont-1"})
        if caminho == "ig-1/media_publish":
            if ESTADO["cai_publicar"]:
                return self._responder(503, {"error": {"code": 2, "message": "Service temporarily unavailable"}})
            return self._responder(200, {"id": "midia-1"})
        if caminho == "pagina-1/photos":
            if params.get("published") == "false":                           # v0.42.0: a foto do carrossel sobe SEM publicar
                ESTADO["fotos_fb"].append(params)
                return self._responder(200, {"id": f"foto-u{len(ESTADO['fotos_fb'])}"})
            return self._responder(200, {"id": "foto-9", "post_id": "pagina-1_post-9"})
        if caminho == "pagina-1/feed":                                       # v0.42.0: a publicação única com as fotos (attached_media)
            ESTADO["feed_fb"].append(params)
            return self._responder(200, {"id": "pagina-1_post-9"})
        self._responder(404, {"error": {"code": 803, "message": "não existe"}})

    def do_GET(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path.startswith("/storage/v1/bucket/"):
            if not self._armazenamento_ok():
                return
            nome = self.path.rsplit("/", 1)[1]
            if ESTADO.get("bucket_preso"):                                # v0.21.0: o armazenamento não responde (a conexão fica presa)
                time.sleep(ESTADO["bucket_preso"])
                self.close_connection = True
                return
            if ESTADO["bucket_get_falha"]:
                return self._responder(400, {"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"})
            return self._responder(200 if nome in ESTADO["buckets"] else 404,
                                   {"name": nome, "public": nome in ESTADO["publicos"]} if nome in ESTADO["buckets"] else {"error": "Bucket not found"})
        if self.path.startswith("/meta/"):
            return self._meta({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
        if self.path.startswith("/github/repos/arteconartescontabeis-design/radar/actions/workflows/"):   # v0.22.0: o estado do workflow
            arquivo = self.path.rsplit("/", 1)[1]
            ESTADO["github_wf"].append(("GET", arquivo, self.headers.get("Authorization")))
            if arquivo in ESTADO["workflows"]:
                estado = ESTADO["workflows"][arquivo]
                return self._responder(200, {"path": f".github/workflows/{arquivo}", "state": "disabled_inactivity" if estado == "nao_religa" else estado})
        self._responder(404, {})

    def do_PUT(self):
        if self.path.startswith("/github/") and self.path.endswith("/enable"):     # v0.22.0 (rodada 2): religar um workflow
            arquivo = self.path.rsplit("/", 2)[1]
            ESTADO["github_wf"].append(("PUT", arquivo, self.headers.get("Authorization")))
            if ESTADO["workflows"].get(arquivo) == "nao_religa":
                return self._responder(403, {"message": "Resource not accessible by personal access token"})
            ESTADO["workflows"][arquivo] = "active"
            self.send_response(204)
            self.end_headers()
            return
        self._responder(404, {})

    def do_DELETE(self):
        if self.path.startswith("/storage/v1/object/"):                    # v0.22.0 (rodada 2): a imagem antiga sai do bucket público
            ESTADO.setdefault("apagados", []).append((self.path, self.headers.get("apikey")))
            return self._responder(200, {"message": "Successfully deleted"})
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
            assert b["public"] is (b["id"] != "radar-pauta") and b["allowed_mime_types"] == ["image/jpeg"]   # v0.21.0: o da Pauta é privado
            ESTADO["buckets"].add(b["id"])
            if b["public"]:
                ESTADO["publicos"].add(b["id"])
            return self._responder(200, {"name": b["id"]})
        if self.path.startswith("/storage/v1/object/sign/"):                  # v0.21.0: link assinado (POST /object/sign/:bucket/*)
            ESTADO["assinaturas"].append((self.path, json.loads(corpo or b"null")))
            if ESTADO["assinar_falha"]:
                return self._responder(400, {"statusCode": "404", "error": "not_found", "message": "Object not found"})
            return self._responder(200, {"signedURL": self.path.removeprefix("/storage/v1") + f"?token=assinado.{len(ESTADO['assinaturas'])}"})
        if self.path.startswith("/storage/v1/object/"):
            ESTADO["storage"].append((self.path, self.headers.get("Content-Type"), corpo))
            ESTADO["upsert"].append(self.headers.get("x-upsert"))
            return self._responder(200, {"Key": self.path})
        if self.path.startswith("/meta/"):
            return self._meta({k: v[0] for k, v in parse_qs(corpo.decode()).items()})
        if self.path.startswith("/github/"):                               # v0.19.0: acionar o workflow (workflow_dispatch)
            ESTADO["github"].append((self.command, self.path, self.headers.get("Authorization"), json.loads(corpo or b"null")))
            if ESTADO["workflows"].get(self.path.split("/")[-2], "active") != "active":    # v0.22.0: desligado não aceita acionamento
                return self._responder(422, {"message": "Cannot trigger a 'workflow_dispatch' on a disabled workflow"})
            if not ESTADO["github_status"]:                                 # GitHub fora do ar: fecha sem responder
                self.close_connection = True
                return
            if ESTADO["github_status"] == 204:
                self.send_response(204)
                self.end_headers()
                return
            return self._responder(ESTADO["github_status"], {"message": "Bad credentials " + TOKEN_GITHUB})
        self._responder(404, {})

    def log_message(self, *a):
        pass


def _subir(porta, extra, pasta):
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), SUPABASE_SERVICE_ROLE_KEY=jwt("service_role"),
                    META_GRAPH_URL=PONTE + "/meta", RADAR_REDES_PASSO_MS="50", RADAR_REDES_ESPERA_MS="2000", RADAR_REDES_BUCKET_MS="1500",
                    RADAR_GITHUB_API=PONTE + "/github", RADAR_PORTA_LOCAL=str(porta), NO_COLOR="1")
    for nome in ("SUPABASE_SECRET_KEYS", "RADAR_GITHUB_TOKEN", "RADAR_GITHUB_REPO", "RADAR_GITHUB_RAMO"):
        ambiente.pop(nome, None)                                # só o que o teste pedir
    ambiente.update(extra)
    LOGS[porta] = pasta / f"radar-redes-{porta}.log"            # v0.21.0: a saída fica num arquivo (o teste dos registros lê)
    with open(LOGS[porta], "wb") as saida:
        proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                                 str(RAIZ / "supabase" / "functions" / "radar-redes" / "index.ts")],
                                env=ambiente, stdout=saida, stderr=subprocess.STDOUT)
    for _ in range(150):
        try:
            requests.options(f"http://127.0.0.1:{porta}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.2)
    return proc


@pytest.fixture(scope="module")
def funcao(api_postgrest, tmp_path_factory):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    pasta = tmp_path_factory.mktemp("radar-redes")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    meta_ok = {"META_PAGE_ID": "pagina-1", "META_PAGE_TOKEN": TOKEN, "META_IG_USER_ID": "ig-1"}
    processos = []                    # encerrados mesmo se a subida de um deles falhar (senão ficam presos nas portas dos outros testes)
    try:
        for porta, extra in ((PORTA_FUNCAO, {**meta_ok, "RADAR_GITHUB_TOKEN": TOKEN_GITHUB}), (PORTA_SEM_META, {}),
                             (PORTA_TOKEN_PAGINA, {**meta_ok, "META_PAGE_TOKEN": TOKEN_PAGINA}),
                             (PORTA_SEM_ACESSO, {**meta_ok, "META_PAGE_TOKEN": TOKEN_OUTRO}),
                             (PORTA_CHAVE_NOVA, {**meta_ok, "SUPABASE_SERVICE_ROLE_KEY": SECRETA}),        # como no projeto da Artecon
                             (PORTA_LISTA_NOVA, {**meta_ok, "SUPABASE_SECRET_KEYS": json.dumps({"default": SECRETA}),   # a antiga ainda é JWT
                                                 "SUPABASE_PUBLISHABLE_KEYS": json.dumps({"default": PUBLICA_NOVA})}),         # v0.22.0 (rodada 2)
                             (PORTA_IG_TOKEN, {**meta_ok, "META_IG_TOKEN": TOKEN_IG}),
                             (PORTA_GITHUB, {**meta_ok, "RADAR_GITHUB_TOKEN": TOKEN_GITHUB}),
                             (PORTA_IG_SEM_ID, {"META_PAGE_ID": "pagina-1", "META_PAGE_TOKEN": TOKEN, "META_IG_TOKEN": TOKEN_IG})):
            processos.append(_subir(porta, extra, pasta))
        yield
    finally:
        for p in processos:
            p.terminate()
        ponte.shutdown()
        ponte.server_close()          # libera a porta na hora: outro módulo de teste usa a mesma


@pytest.fixture()
def redes(funcao, limpo):
    ESTADO.update(chaves=[], bucket_get_falha=False, bucket_preso=0, busca_token=[], meta=[], storage=[], buckets=set(), erro_meta=None, status_ig=["IN_PROGRESS", "FINISHED"], cai_publicar=False,
                  github=[], github_status=204, publicos=set(), upsert=[], assinaturas=[], assinar_falha=False, apagados=[], workflows={}, github_wf=[],
                  filhos_ig=[], carrossel_ig=[], fotos_fb=[], feed_fb=[])
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


def test_instagram_publica_em_duas_etapas_com_a_imagem_no_armazenamento_privado(redes):
    """v0.22.0 (rodada 2 da varredura geral): a imagem da notícia vai, como a da Pauta, para o bucket PRIVADO com nome aleatório, e
    a Meta recebe só um link assinado de 10 minutos. Antes: o bucket público "radar-redes", com o nome <conteúdo>-<canal>-<envio>.jpg
    (fácil de adivinhar), para sempre — mesmo depois de excluída da rede."""
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 200 and r == {"situacao": "publicado", "url": "https://www.instagram.com/p/ABC123/", "post_id": "midia-1"}, r
    caminho, tipo, dados = ESTADO["storage"][0]
    assert re.fullmatch(r"/storage/v1/object/radar-pauta/p-[0-9a-f-]{36}\.jpg", caminho) and tipo == "image/jpeg" and dados.startswith(b"\xff\xd8")
    assert ESTADO["buckets"] == {"radar-pauta"} and ESTADO["publicos"] == set()  # nenhum bucket público é criado
    assert ESTADO["upsert"] == [None]                                            # nunca sobrescreve
    chamadas = [(m, p) for m, p, _ in ESTADO["meta"]]
    assert chamadas == [("POST", "ig-1/media"), ("GET", "cont-1"), ("GET", "cont-1"), ("POST", "ig-1/media_publish"), ("GET", "midia-1")]
    criar = ESTADO["meta"][0][2]
    assert criar["image_url"] == f"{PONTE}/storage/v1" + caminho.replace("/storage/v1/object/", "/object/sign/") + "?token=assinado.1"
    assert ESTADO["assinaturas"] == [(caminho.replace("/object/", "/object/sign/"), {"expiresIn": 600})]
    assert criar["caption"].startswith("Prazo do Simples") and ESTADO["meta"][3][2]["creation_id"] == "cont-1"
    linha = db.execute("select situacao, post_id, url, imagem, imagem_url from radar_redes_envios where id = %s", (envio,)).fetchone()
    assert linha[:4] == ("publicado", "midia-1", "https://www.instagram.com/p/ABC123/", None) and linha[4] == PONTE + caminho   # o interno
    # de novo: não publica duas vezes
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 400 and "não está aguardando envio" in r["message"] and len(ESTADO["meta"]) == 5


def test_facebook_publica_a_foto_na_pagina_com_a_legenda(redes):
    db, c1 = redes
    envio = autorizar(db, c1, "facebook")
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 200 and r["url"] == "https://www.facebook.com/artecon/posts/9" and r["post_id"] == "pagina-1_post-9"
    metodo, caminho, params = ESTADO["meta"][0]
    assert (metodo, caminho) == ("POST", "pagina-1/photos") and params["message"].startswith("Prazo")
    assert params["url"].startswith(f"{PONTE}/storage/v1/object/sign/radar-pauta/p-") and "?token=" in params["url"]   # v0.22.0: o link assinado


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
    itens = {i["item"]: i for i in r["itens"]}                     # v0.21.0: depois dele vem o armazenamento privado da Pauta
    assert status == 200 and itens["Armazenamento das imagens"] == {"item": "Armazenamento das imagens", "ok": True,
                                                                    "detalhe": 'bucket privado "radar-pauta" (a notícia e a Pauta; a Meta recebe um link de 10 minutos)'}
    assert "Armazenamento privado da Pauta" not in itens and ESTADO["publicos"] == set()   # v0.22.0 (rodada 2): um só, privado
    envio = autorizar(db, c1, "facebook")
    status, r = pedir({"acao": "publicar", "envio": envio}, porta=porta)
    assert status == 200 and r["situacao"] == "publicado", r
    caminhos = {c[1] for c in _so_no_apikey()}
    assert "/rest/v1/rpc/radar_rede_iniciar" in caminhos and "/rest/v1/rpc/radar_rede_concluir" in caminhos
    assert any(c.startswith("/storage/v1/object/radar-pauta/p-") for c in caminhos)
    assert db.execute("select situacao from radar_redes_envios where id = %s", (envio,)).fetchone()[0] == "publicado"


def test_com_a_chave_publica_nova_o_apikey_dos_pedidos_com_o_token_de_quem_chama_e_ela(redes):
    """Rodada 2 da varredura geral: o Supabase desliga a chave anon antiga até o fim de 2026; desligada, ela seria recusada no apikey.
    Com SUPABASE_PUBLISHABLE_KEYS (a nova, sb_publishable_…), o apikey dos pedidos feitos com o token do administrador é ela; sem a
    lista nova, continua a anon."""
    db, c1 = redes
    for porta, prefixo in ((PORTA_LISTA_NOVA, PUBLICA_NOVA[:10]), (PORTA_FUNCAO, jwt("anon")[:10])):
        ESTADO["chaves"] = []
        assert pedir({"acao": "diagnostico"}, porta=porta)[0] == 200
        papel = [c for c in ESTADO["chaves"] if c[1] == "/rest/v1/rpc/radar_papel"]
        assert papel and all(apikey == prefixo and auth == jwt("authenticated", ADMIN)[:10] for _, _, apikey, auth in papel), papel


def test_chave_antiga_continua_nos_dois_cabecalhos_e_bucket_que_ja_existe_nao_e_erro(redes):
    db, c1 = redes
    ESTADO["buckets"].add("radar-pauta")
    ESTADO["bucket_get_falha"] = True                         # a consulta falhou, mas o bucket existe: o Supabase responde "409"
    status, r = pedir({"acao": "diagnostico"})
    assert status == 200 and next(i for i in r["itens"] if i["item"] == "Armazenamento das imagens")["ok"] is True, r
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


def test_envio_de_antes_da_versao_com_o_link_publico_sai_e_a_imagem_some_ao_excluir(redes):
    """v0.22.0 (rodada 2 da varredura geral): o envio que deu erro antes desta versão guardou o link do bucket público: a nova
    tentativa ainda manda esse link (não sobe de novo); e, ao excluir da rede pela função, a imagem sai do bucket público (a Meta
    já tem a cópia). Endereço que não é desse formato nunca é apagado."""
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    publica = f"{PONTE}/storage/v1/object/public/radar-redes/{c1}-instagram-{envio}.jpg"
    db.execute("update radar_redes_envios set situacao = 'erro', erro = 'Meta fora do ar', imagem = null, imagem_url = %s where id = %s",
               (publica, envio))
    assert pedir({"acao": "publicar", "envio": envio})[0] == 200
    assert ESTADO["storage"] == [] and ESTADO["assinaturas"] == [] and ESTADO["meta"][0][2]["image_url"] == publica
    assert pedir({"acao": "excluir", "envio": envio}) == (200, {"situacao": "excluido", "canal": "instagram"})
    assert [c for c, _ in ESTADO["apagados"]] == [f"/storage/v1/object/radar-redes/{c1}-instagram-{envio}.jpg"]
    # a de agora (privada) não é apagada ao excluir: não está à vista de ninguém (e a revogação de um termo a acha pelo envio)
    fb = autorizar(db, c1, "facebook")
    assert pedir({"acao": "publicar", "envio": fb})[0] == 200
    assert pedir({"acao": "excluir", "envio": fb})[0] == 200 and len(ESTADO["apagados"]) == 1


def test_excluir_que_a_meta_recusa_fica_publicado_e_explica(redes):
    db, c1 = redes
    ig = autorizar(db, c1, "instagram")
    assert pedir({"acao": "publicar", "envio": ig})[0] == 200
    ESTADO["erro_meta"] = "Unsupported delete request."
    st, r = pedir({"acao": "excluir", "envio": ig})
    assert st == 502 and "Já apaguei" in r["message"] and TOKEN not in r["message"] and TOKEN_PAGINA not in r["message"]
    assert db.execute("select situacao from radar_redes_envios where id = %s", (ig,)).fetchone()[0] == "publicado"


def robo_registra_site(conteudo, envio_site, url):
    """O robô do site (radar_site_publicar.py, sem usuário): marca o envio "enviando" e registra a publicação. Varredura geral
    (v0.22.0): com o site na vez do robô, o registro à mão é recusado (RADAR145) e só o do robô, com o link do site, libera as redes."""
    with como("service_role") as c:
        c.execute("update radar_site_envios set situacao = 'enviando' where id = %s", (envio_site,))
        c.execute("insert into radar_divulgacoes (conteudo_id, url, publicado_em) values (%s, %s, current_date)", (conteudo, url))


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
    robo_registra_site(c2, r["site"], "https://artecon.cnt.br/news/view/todos")
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
    db, c1 = redes
    a2, c2 = cenario_publicavel(db, slug_fonte="rfb-noticias")
    aprovar(c2)
    lido = db.execute("select atualizado_em from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        r = c.execute("select radar_autorizar_todos(%s, 'Tributário', %s, %s, null, %s)", (c2, lido, JPEG, "Leia: {LINK DO SITE}")).fetchone()[0]
    robo_registra_site(c2, r["site"], "https://artecon.cnt.br/news/view/chave")
    falsa = jwt("service_role", segredo="outro-segredo-qualquer-com-32-caracteres")
    st, res = pedir({"acao": "publicar", "envio": r["facebook"]}, porta=PORTA_CHAVE_NOVA, cab={"Authorization": "Bearer " + falsa, "apikey": falsa})
    assert st in (401, 403) and db.execute("select situacao from radar_redes_envios where id = %s", (r["facebook"],)).fetchone()[0] == "autorizado"
    robo = {"Authorization": "Bearer " + jwt("service_role"), "apikey": jwt("service_role")}
    st, res = pedir({"acao": "publicar", "envio": r["facebook"]}, porta=PORTA_CHAVE_NOVA, cab=robo)
    assert (st, res["situacao"]) == (200, "publicado")



# ------------------------------------------------------------------- v0.19.0: a tela aciona o robô do site na hora (workflow_dispatch)
def autorizar_site(db):
    """Deixa uma publicação no site esperando o robô (de outro conteúdo: o do cenário já está no site)."""
    a2, c2 = cenario_publicavel(db, slug_fonte="rfb-noticias")
    aprovar(c2)
    lido = db.execute("select atualizado_em from radar_conteudos where id = %s", (c2,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        return c.execute("select radar_autorizar_site(%s, 'Tributário', %s)", (c2, lido)).fetchone()[0]


def test_admin_aciona_o_robo_do_site_uma_vez_e_a_recusa_do_github_nao_mostra_o_token(redes):
    """O único teste que chega ao GitHub na instância principal: a pausa de 30 s fica na memória da função, que serve o módulo
    inteiro. Por isso as recusas do GitHub (que não contam como acionamento) vêm antes do acionamento que dá certo."""
    db, c1 = redes
    with como("authenticated", ADMIN) as c:
        exclusao = c.execute("select radar_pedir_exclusao_site(%s)", (c1,)).fetchone()[0]   # o pedido de exclusão também espera o robô
    ESTADO["github_status"] = 401                                                  # token vencido ou revogado
    status, r = pedir({"acao": "acionar_robo"})
    assert status == 200 and (r["acionado"], r["motivo"]) == (False, "token_recusado") and "RADAR_GITHUB_TOKEN" in r["mensagem"], r
    assert r["mensagem"].endswith("a autorização continua guardada e sai na próxima rodada automática.") and TOKEN_GITHUB not in json.dumps(r)
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_cancelar_exclusao_site(%s)", (exclusao,)).fetchone()[0] is True
    assert pedir({"acao": "acionar_robo"})[1]["motivo"] == "nada_pendente" and len(ESTADO["github"]) == 1
    autorizar_site(db)
    for st, motivo, trecho in ((403, "sem_acesso", "Actions"), (404, "sem_acesso", "arteconartescontabeis-design/radar"),
                               (422, "workflow_recusou", "radar-site-publicar.yml"), (0, "github_fora", "não respondeu")):
        ESTADO["github_status"] = st
        status, r = pedir({"acao": "acionar_robo"})
        assert (status, r["acionado"], r["motivo"]) == (200, False, motivo) and trecho in r["mensagem"], r
        assert "continua guardada" in r["mensagem"] and TOKEN_GITHUB not in json.dumps(r)
    assert len(ESTADO["github"]) == 5                                              # cada recusa foi uma chamada: nenhuma segura a próxima
    ESTADO.update(github=[], github_status=204)
    status, r = pedir({"acao": "acionar_robo"})
    assert status == 200 and r["acionado"] is True and r["mensagem"] == "Robô acionado: a publicação deve sair em 1 a 2 minutos." and r["em"], r
    assert ESTADO["github"] == [("POST", CAMINHO_GITHUB, "Bearer " + TOKEN_GITHUB, {"ref": "main"})]
    # clicar de novo logo em seguida não aciona outra vez
    status, r = pedir({"acao": "acionar_robo"})
    assert (status, r["acionado"], r["mensagem"]) == (200, True, "O robô já foi acionado há instantes.") and len(ESTADO["github"]) == 1


def test_robo_do_site_desligado_pelo_github_e_religado_e_o_desligado_a_mao_nao_promete_rodada(redes):
    """Rodada 2 da varredura geral: no repositório público, o GitHub desliga o workflow agendado depois de 60 dias sem atividade, e
    o acionamento recebe 422. Antes a função dizia "não aceita acionamento manual" e prometia "a próxima rodada automática", que
    também não vinha. Agora: desligado por inatividade, ela religa e aciona; desligado à mão, diz onde religar, sem prometer rodada."""
    db, c1 = redes
    autorizar_site(db)
    wf = "radar-site-publicar.yml"
    ESTADO["workflows"][wf] = "disabled_manually"
    status, r = pedir({"acao": "acionar_robo"}, porta=PORTA_GITHUB)
    assert (status, r["acionado"], r["motivo"]) == (200, False, "workflow_desligado"), r
    assert "desligado à mão" in r["mensagem"] and "Enable workflow" in r["mensagem"] and "próxima rodada automática" not in r["mensagem"]
    assert "só sai depois que ele for religado" in r["mensagem"] and not [g for g in ESTADO["github_wf"] if g[0] == "PUT"]
    ESTADO["workflows"][wf] = "nao_religa"                                          # por inatividade, e o token não consegue religar
    status, r = pedir({"acao": "acionar_robo"}, porta=PORTA_GITHUB)
    assert r["motivo"] == "workflow_desligado" and "60 dias" in r["mensagem"] and "próxima rodada automática" not in r["mensagem"], r
    ESTADO["workflows"][wf] = "disabled_inactivity"
    status, r = pedir({"acao": "acionar_robo"}, porta=PORTA_GITHUB)
    assert (status, r["acionado"]) == (200, True) and "o Radar religou e acionou" in r["mensagem"], r
    assert ESTADO["workflows"][wf] == "active" and [g[:2] for g in ESTADO["github"]][-2:] == [("POST", CAMINHO_GITHUB)] * 2
    assert TOKEN_GITHUB not in json.dumps(r)


def test_agenda_religa_os_robos_agendados_desligados_por_inatividade_e_nao_os_desligados_a_mao(peca):
    """Rodada 2 da varredura geral: uma vez por dia, a agenda do banco pede "manter_robos" (sql/radar-redes-agenda.sql). Cada robô
    agendado do repositório público (coleta, robô do site, resumo) ativo é renovado e o desligado por inatividade, religado; o
    desligado à mão fica (o LEIAME manda desligar ao desfazer a versão). Só a agenda e o administrador; o robô do site, não."""
    db, c1 = peca
    ESTADO["workflows"].update({"radar-coletar.yml": "disabled_inactivity", "radar-site-publicar.yml": "active",
                                "radar-resumo.yml": "disabled_manually", "radar-lembretes.yml": "disabled_inactivity"})
    status, r = pedir({"acao": "manter_robos"}, cab=AGENDA, porta=PORTA_GITHUB)
    assert status == 200 and r == {"ok": False, "robos": [{"workflow": "radar-coletar.yml", "estado": "active", "religado": True},
                                                          {"workflow": "radar-site-publicar.yml", "estado": "active", "religado": False},
                                                          {"workflow": "radar-resumo.yml", "estado": "disabled_manually", "religado": False},
                                                          # v0.29.0: o robô dos lembretes (a rodada de hora em hora é a reserva)
                                                          {"workflow": "radar-lembretes.yml", "estado": "active", "religado": True}]}, r
    assert [(m, a) for m, a, _ in ESTADO["github_wf"] if m == "PUT"] == [("PUT", "radar-coletar.yml"), ("PUT", "radar-site-publicar.yml"),
                                                                         ("PUT", "radar-lembretes.yml")]
    assert ESTADO["workflows"]["radar-resumo.yml"] == "disabled_manually" and ESTADO["github"] == []     # nada é acionado
    assert all(auth == "Bearer " + TOKEN_GITHUB for *_, auth in ESTADO["github_wf"])
    registro = LOGS[PORTA_GITHUB].read_text()
    assert "radar-coletar.yml active (religado)" in registro and TOKEN_GITHUB not in registro
    assert pedir({"acao": "manter_robos"}, porta=PORTA_GITHUB)[0] == 200                     # o administrador também
    assert pedir({"acao": "manter_robos"}, uid=EDITOR, porta=PORTA_GITHUB)[0] == 403
    assert pedir({"acao": "manter_robos"}, cab=ROBO, porta=PORTA_GITHUB)[0] == 403            # o robô do site só publica
    st, r = pedir({"acao": "manter_robos"}, cab=AGENDA, porta=PORTA_SEM_META)                 # sem o token: diz o que falta
    assert st == 200 and r["ok"] is False and "RADAR_GITHUB_TOKEN" in r["mensagem"]


def test_sem_nada_esperando_o_robo_do_site_nao_chama_o_github(redes):
    db, c1 = redes
    autorizar(db, c1, "instagram")                    # autorização avulsa das redes: quem publica é a tela, não o robô do site
    status, r = pedir({"acao": "acionar_robo"})
    assert status == 200 and (r["acionado"], r["motivo"]) == (False, "nada_pendente") and ESTADO["github"] == [], r


def test_sem_o_segredo_do_github_explica_e_a_autorizacao_continua_guardada(redes):
    db, c1 = redes
    envio = autorizar_site(db)
    status, r = pedir({"acao": "acionar_robo"}, porta=PORTA_SEM_META)
    assert status == 200 and (r["acionado"], r["motivo"]) == (False, "sem_token") and "RADAR_GITHUB_TOKEN" in r["mensagem"], r
    assert ESTADO["github"] == [] and db.execute("select situacao from radar_site_envios where id = %s", (envio,)).fetchone()[0] == "autorizado"


def test_so_o_administrador_aciona_o_robo_do_site(redes):
    db, c1 = redes
    autorizar_site(db)
    st, r = pedir({"acao": "acionar_robo"}, uid=EDITOR)
    assert st == 403 and r["message"] == "Só o administrador aciona o robô do site."
    robo = {"Authorization": "Bearer " + jwt("service_role"), "apikey": jwt("service_role")}
    assert pedir({"acao": "acionar_robo"}, cab=robo)[0] == 403                       # o robô só publica
    assert pedir({"acao": "acionar_robo"}, cab={})[0] == 401
    assert ESTADO["github"] == []


# ------------------------------------------------------------------- v0.21.0: a peça da Pauta (bucket privado, link assinado) e a agenda do banco
CHAVE_AGENDA = "a1" * 32                                    # a chave 'radar_redes_agenda' do Vault (de mentira)
AGENDA = {"Authorization": "Bearer " + jwt("anon"), "x-radar-agenda": CHAVE_AGENDA}   # como o comando do pg_cron manda (sql/radar-redes-agenda.sql)
ROBO = {"Authorization": "Bearer " + jwt("service_role"), "apikey": jwt("service_role")}
RE_INTERNA = re.escape(PONTE) + r"/storage/v1/object/radar-pauta/p-[0-9a-f-]{36}\.jpg"


@pytest.fixture()
def peca(redes, pauta):
    """O cenário da notícia (redes), a Pauta (pauta) e o Vault de mentira com a chave da agenda. No fim, o Vault sai (ou só a chave,
    se ele já existia)."""
    db, c1 = redes
    tinha = db.execute("select count(*) from pg_namespace where nspname = 'vault'").fetchone()[0] == 1
    if not tinha:
        db.execute(VAULT_SIMULADO)
    db.execute("insert into vault.secrets (name, secret) values ('radar_redes_agenda', %s)", (CHAVE_AGENDA,))
    try:
        yield db, c1
    finally:
        if tinha:
            db.execute("delete from vault.secrets where name = 'radar_redes_agenda'")
        else:
            db.execute("drop schema vault cascade")


def agendada(db, canais=("instagram",), vencida=True, dias=2, artes=None, **campos):
    """Peça pronta e aprovada pelo administrador para sair pela agenda, com a lâmina (JPEG) desenhada por ele (ou as lâminas do
    carrossel, em `artes`). vencida: a hora marcada passou há 1 minuto. Devolve {canal: envio}."""
    campos.setdefault("legenda_facebook", LEG_PECA if "facebook" in canais else "")
    pid = nova_peca(db, dias=dias, **campos)
    marcar_pronta(db, pid)
    envios = aprovar_peca(db, pid, canais=canais, artes=artes if artes is not None else [lamina(dados=JPEG)])["envios"]
    if vencida:
        for envio in envios.values():
            vencer(db, envio)
    return envios


# v0.42.0: as lâminas do carrossel (JPEGs distintos, para conferir a ordem no armazenamento)
JPEGS_CARROSSEL = ["data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + bytes([65 + n]) * 64).decode() for n in range(3)]
CARTOES_PECA = [{"titulo": "Um", "texto": "Primeiro passo."}, {"titulo": "Dois", "texto": "Segundo passo."}]


def carrossel_agendado(db, canais=("instagram",)):
    """Peça em carrossel aprovada para a agenda (capa + 2 cartões = 3 lâminas), já vencida. Devolve {canal: envio}."""
    return agendada(db, canais=canais, tipo="educativo", formato="carrossel", cartoes=CARTOES_PECA,
                    artes=[lamina(dados=d) for d in JPEGS_CARROSSEL])


def publicar_agora(db, envio, conferi=False):
    """O "Publicar agora" / "Tentar de novo" do administrador: só remarca a hora (e devolve "erro" para "autorizado")."""
    pid = db.execute("select peca_id from radar_redes_envios where id = %s", (envio,)).fetchone()[0]
    with como("authenticated", ADMIN) as c:
        return c.execute("select radar_pauta_publicar_agora(%s, %s)", (pid, conferi)).fetchone()[0]


def ler_log(porta=PORTA_FUNCAO, espera=None):
    """A saída da instância da função (o módulo inteiro). Com `espera`, aguarda até 3 s essa linha aparecer no fim."""
    for _ in range(30):
        texto = LOGS[porta].read_text(errors="replace")
        if espera is None or texto.rstrip().endswith(espera):
            break
        time.sleep(0.1)
    return texto


def test_peca_instagram_bucket_privado_link_assinado_e_publica_uma_vez(peca):
    db, c1 = peca
    ig = agendada(db)["instagram"]
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert status == 200 and r == {"situacao": "publicado", "url": "https://www.instagram.com/p/ABC123/", "post_id": "midia-1"}, r
    caminho, tipo, dados = ESTADO["storage"][0]
    assert re.fullmatch(RE_INTERNA, PONTE + caminho) and tipo == "image/jpeg" and dados.startswith(b"\xff\xd8")
    assert ESTADO["upsert"] == [None]                                              # nome aleatório: nunca sobrescreve
    assert ESTADO["buckets"] == {"radar-pauta"} and ESTADO["publicos"] == set()     # o bucket PRIVADO é criado na primeira vez
    assinar = caminho.replace("/object/radar-pauta/", "/object/sign/radar-pauta/")
    assert ESTADO["assinaturas"] == [(assinar, {"expiresIn": 600})]                 # link de 10 minutos
    chamadas = [(m, p) for m, p, _ in ESTADO["meta"]]
    assert chamadas == [("POST", "ig-1/media"), ("GET", "cont-1"), ("GET", "cont-1"), ("POST", "ig-1/media_publish"), ("GET", "midia-1")]
    criar = ESTADO["meta"][0][2]
    assert criar["image_url"] == PONTE + assinar + "?token=assinado.1" and criar["caption"] == LEG_PECA   # a Meta baixa pelo link assinado
    linha = db.execute("select situacao, post_id, url, imagem, imagem_url from radar_redes_envios where id = %s", (ig,)).fetchone()
    # no banco fica o endereço interno (não abre sem a chave), nunca o link assinado; a cópia da arte sai do banco
    assert linha == ("publicado", "midia-1", "https://www.instagram.com/p/ABC123/", None, PONTE + caminho)
    # de novo (a agenda chamou duas vezes, ou o administrador clicou): não publica duas vezes
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert status == 400 and "não está aguardando envio" in r["message"] and len(ESTADO["meta"]) == 5 and len(ESTADO["storage"]) == 1


def test_peca_facebook_photos_com_link_assinado(peca):
    """O administrador também manda a peça (o "Publicar agora" com a agenda desligada chama a função direto), mas só na hora."""
    db, c1 = peca
    envios = agendada(db, canais=("instagram", "facebook"), vencida=False)
    status, r = pedir({"acao": "publicar", "envio": envios["facebook"]})
    assert status == 400 and r["message"].startswith("ainda não é a hora: agendada para ")      # RADAR172: nada muda
    assert situacao_envio(db, envios["facebook"]) == ("autorizado", None) and ESTADO["storage"] == [] and ESTADO["meta"] == []
    assert sorted(publicar_agora(db, envios["facebook"])) == sorted(envios.values())
    status, r = pedir({"acao": "publicar", "envio": envios["facebook"]})
    assert status == 200 and r["url"] == "https://www.facebook.com/artecon/posts/9" and r["post_id"] == "pagina-1_post-9", r
    metodo, caminho, params = ESTADO["meta"][0]
    assert (metodo, caminho) == ("POST", "pagina-1/photos") and params["message"] == LEG_PECA
    assert re.fullmatch(RE_INTERNA.replace("/object/", "/object/sign/") + r"\?token=assinado\.1", params["url"]), params["url"]
    assert re.fullmatch(RE_INTERNA, db.execute("select imagem_url from radar_redes_envios where id = %s", (envios["facebook"],)).fetchone()[0])
    # o robô do site nunca manda a peça (ela nunca vai junto com o site)
    st, r = pedir({"acao": "publicar", "envio": envios["instagram"]}, cab=ROBO)
    assert st == 403 and "junto com o site" in r["message"] and situacao_envio(db, envios["instagram"]) == ("autorizado", None)


def test_peca_nova_tentativa_reassina_sem_reenviar(peca):
    db, c1 = peca
    ig = agendada(db)["instagram"]
    ESTADO["erro_meta"] = "Application does not have permission"
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert status == 502 and "instagram_content_publish" in r["message"] and TOKEN_PAGINA not in json.dumps(r)
    sit, erro, imagem, interna = db.execute("select situacao, erro, imagem, imagem_url from radar_redes_envios where id = %s", (ig,)).fetchone()
    assert sit == "erro" and "permission" in erro and "token=" not in erro and imagem is None and re.fullmatch(RE_INTERNA, interna)
    ESTADO["erro_meta"] = None
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)                # "erro" não volta pela agenda: só pelo administrador
    assert status == 400 and "não está aguardando envio" in r["message"] and len(ESTADO["meta"]) == 1
    assert publicar_agora(db, ig, conferi=True) == [ig]
    ESTADO["assinar_falha"] = True                                                  # o link não saiu: nada vai à Meta
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert (status, r["message"]) == (502, "Não foi possível preparar o link da imagem para a Meta. Nada foi publicado.")
    assert situacao_envio(db, ig)[0] == "erro" and len(ESTADO["meta"]) == 1
    ESTADO["assinar_falha"] = False
    assert publicar_agora(db, ig, conferi=True) == [ig]
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert (status, r["situacao"]) == (200, "publicado"), r
    assert len(ESTADO["storage"]) == 1                                              # a imagem não sobe de novo
    assert [a for a, _ in ESTADO["assinaturas"]] == [ESTADO["storage"][0][0].replace("/object/", "/object/sign/")] * 3   # cada tentativa assina
    assert [prm["image_url"].rsplit("=", 1)[1] for m, p, prm in ESTADO["meta"] if p == "ig-1/media"] == ["assinado.1", "assinado.3"]
    assert db.execute("select situacao, imagem_url from radar_redes_envios where id = %s", (ig,)).fetchone() == ("publicado", interna)



def test_peca_carrossel_instagram_um_conteiner_por_lamina_e_media_publish(peca):
    """v0.42.0: a peça em carrossel agendada sai sozinha — cada lâmina vai ao bucket privado e vira um contêiner (is_carousel_item);
    o contêiner CAROUSEL leva os filhos e a legenda; media_publish publica. No banco ficam os endereços internos (imagens_urls)."""
    db, c1 = peca
    ig = carrossel_agendado(db)["instagram"]
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert status == 200 and r == {"situacao": "publicado", "url": "https://www.instagram.com/p/ABC123/", "post_id": "midia-1"}, r
    # as 3 lâminas no bucket privado, na ordem do post (os bytes de cada uma), e um link assinado para cada
    assert len(ESTADO["storage"]) == 3 and all(re.fullmatch(RE_INTERNA, PONTE + c) for c, _, _ in ESTADO["storage"])
    assert [d[4:5] for _, _, d in ESTADO["storage"]] == [b"A", b"B", b"C"]
    assert [a for a, _ in ESTADO["assinaturas"]] == [c.replace("/object/", "/object/sign/") for c, _, _ in ESTADO["storage"]]
    chamadas = [(m, p) for m, p, _ in ESTADO["meta"]]
    assert chamadas == [("POST", "ig-1/media")] * 3 + [("GET", "cont-f1"), ("GET", "cont-f2"), ("GET", "cont-f3"),
                                                       ("POST", "ig-1/media"), ("GET", "cont-car"), ("POST", "ig-1/media_publish"), ("GET", "midia-1")]
    assert [f["image_url"].rsplit("=", 1)[1] for f in ESTADO["filhos_ig"]] == ["assinado.1", "assinado.2", "assinado.3"]
    assert all("caption" not in f for f in ESTADO["filhos_ig"])                     # a legenda vai só no contêiner CAROUSEL
    assert ESTADO["carrossel_ig"] == [{"media_type": "CAROUSEL", "children": "cont-f1,cont-f2,cont-f3", "caption": LEG_PECA,
                                       "access_token": TOKEN_PAGINA}]
    assert ESTADO["meta"][-2][2]["creation_id"] == "cont-car"
    linha = db.execute("select situacao, post_id, imagem, imagem_url, imagens_urls from radar_redes_envios where id = %s", (ig,)).fetchone()
    assert linha[:4] == ("publicado", "midia-1", None, None) and [re.fullmatch(RE_INTERNA, u) is not None for u in linha[4]] == [True] * 3
    assert linha[4] == [PONTE + c for c, _, _ in ESTADO["storage"]]                 # na ordem do post
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)                # nunca duas vezes
    assert status == 400 and "não está aguardando envio" in r["message"] and len(ESTADO["storage"]) == 3


def test_peca_carrossel_facebook_fotos_sem_publicar_e_feed_com_attached_media(peca):
    db, c1 = peca
    fb = carrossel_agendado(db, canais=("facebook",))["facebook"]
    status, r = pedir({"acao": "publicar", "envio": fb}, cab=AGENDA)
    assert status == 200 and r["url"] == "https://www.facebook.com/artecon/posts/9" and r["post_id"] == "pagina-1_post-9", r
    chamadas = [(m, p) for m, p, _ in ESTADO["meta"]]
    assert chamadas == [("POST", "pagina-1/photos")] * 3 + [("POST", "pagina-1/feed"), ("GET", "pagina-1_post-9")]
    assert [f["published"] for f in ESTADO["fotos_fb"]] == ["false"] * 3            # nenhuma foto aparece sozinha
    assert all("message" not in f for f in ESTADO["fotos_fb"])
    [feed] = ESTADO["feed_fb"]
    assert feed["message"] == LEG_PECA
    assert [json.loads(feed[f"attached_media[{n}]"]) for n in range(3)] == [{"media_fbid": f"foto-u{n + 1}"} for n in range(3)]
    assert db.execute("select situacao, post_id from radar_redes_envios where id = %s", (fb,)).fetchone() == ("publicado", "pagina-1_post-9")


def test_peca_carrossel_nova_tentativa_reassina_as_laminas_sem_reenviar(peca):
    db, c1 = peca
    ig = carrossel_agendado(db)["instagram"]
    ESTADO["erro_meta"] = "Application does not have permission"
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert status == 502 and TOKEN_PAGINA not in json.dumps(r)
    sit, erro, urls = db.execute("select situacao, erro, imagens_urls from radar_redes_envios where id = %s", (ig,)).fetchone()
    assert sit == "erro" and "token=" not in erro and len(urls) == 3                # os endereços ficam para a nova tentativa
    ESTADO["erro_meta"] = None
    assert publicar_agora(db, ig, conferi=True) == [ig]
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert (status, r["situacao"]) == (200, "publicado"), r
    assert len(ESTADO["storage"]) == 3                                              # nenhuma lâmina sobe de novo
    assert len(ESTADO["assinaturas"]) == 6                                          # cada tentativa assina as 3 de novo
    assert db.execute("select imagens_urls from radar_redes_envios where id = %s", (ig,)).fetchone()[0] == urls


def test_noticia_em_carrossel_autorizada_com_as_laminas_sai_como_carrossel(redes):
    """v0.42.0: a notícia aprovada também sai como carrossel — o administrador autoriza com as lâminas desenhadas na tela
    (radar_autorizar_rede, p_artes) e a função publica igual à peça da Pauta."""
    db, c1 = redes
    lido = db.execute("select atualizado_em from radar_conteudos where id = %s", (c1,)).fetchone()[0]
    artes = [lamina(dados=d) for d in JPEGS_CARROSSEL]
    with como("authenticated", ADMIN) as c:
        envio = c.execute("select radar_autorizar_rede(%s, 'instagram', %s, null, %s, false, %s::bigint[])",
                          (c1, "Prazo do Simples prorrogado. Leia no site da Artecon.", lido, artes)).fetchone()[0]
    status, r = pedir({"acao": "publicar", "envio": envio})
    assert status == 200 and r == {"situacao": "publicado", "url": "https://www.instagram.com/p/ABC123/", "post_id": "midia-1"}, r
    assert len(ESTADO["filhos_ig"]) == 3 and len(ESTADO["storage"]) == 3
    assert ESTADO["carrossel_ig"][0]["children"] == "cont-f1,cont-f2,cont-f3"
    assert ESTADO["carrossel_ig"][0]["caption"].startswith("Prazo do Simples")
    sit, imagem, urls = db.execute("select situacao, imagem, imagens_urls from radar_redes_envios where id = %s", (envio,)).fetchone()
    assert (sit, imagem) == ("publicado", None) and len(urls) == 3


def test_peca_armazenamento_preso_vira_erro_e_nao_fica_enviando(peca):
    """O armazenamento não responde ao conferir o bucket (a conexão fica presa): a função desiste no tempo-limite, nada vai à Meta e a
    publicação vira "erro" (a falha certa, que "Tentar de novo" resolve), e não fica parada em "enviando" até o Supabase encerrar a
    função (o que viraria um caso "pode ter saído"). Vale também para a notícia."""
    db, c1 = peca
    ig = agendada(db)["instagram"]
    ESTADO["bucket_preso"] = 8
    antes = time.monotonic()
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert time.monotonic() - antes < 3.5                                            # RADAR_REDES_BUCKET_MS = 1,5 s nos testes
    assert (status, r["message"]) == (502, "Não foi possível guardar a imagem para a Meta (o armazenamento não respondeu). Nada foi publicado.")
    assert situacao_envio(db, ig)[0] == "erro" and ESTADO["meta"] == [] and ESTADO["storage"] == []
    noticia = autorizar(db, c1, "facebook")
    status, r = pedir({"acao": "publicar", "envio": noticia})
    assert status == 502 and "o armazenamento não respondeu" in r["message"] and situacao_envio(db, noticia)[0] == "erro"
    ESTADO["bucket_preso"] = 0
    assert publicar_agora(db, ig, conferi=True) == [ig]
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert (status, r["situacao"]) == (200, "publicado"), r

def test_agenda_com_a_chave_publica_so_peca_vencida_e_recusa_o_resto(peca):
    db, c1 = peca
    noticia = autorizar(db, c1, "instagram")
    envios = agendada(db, canais=("instagram", "facebook"))
    futura = agendada(db, dias=3, vencida=False)["instagram"]
    estado = "select situacao, enviado_em, erro, atualizado_em from radar_redes_envios where id = %s"
    antes = {e: db.execute(estado, (e,)).fetchone() for e in (noticia, futura, *envios.values())}
    # chave errada, curta ou longa demais: a mesma recusa, também com a sessão do administrador junto (com o cabeçalho, só a chave vale)
    admin = {"Authorization": "Bearer " + jwt("authenticated", ADMIN)}
    for chave in ("b2" * 32, CHAVE_AGENDA[:31], CHAVE_AGENDA * 4):
        for cab in (AGENDA, admin):
            for corpo in ({"acao": "publicar", "envio": envios["instagram"]}, {"acao": "agenda_teste"}):
                assert pedir(corpo, cab={**cab, "x-radar-agenda": chave}) == (401, {"message": "Chave não confere."})
    # com a chave certa: a notícia não (nem a do "Publicar em todos"), a peça só na hora, e só publicar
    st, r = pedir({"acao": "publicar", "envio": noticia}, cab=AGENDA)
    assert (st, r["message"]) == (403, "A agenda só publica peças da Pauta.")
    st, r = pedir({"acao": "publicar", "envio": futura}, cab=AGENDA)
    assert st == 400 and r["message"].startswith("ainda não é a hora: agendada para ") and "(Brasília)" in r["message"]
    for corpo in ({"acao": "excluir", "envio": noticia}, {"acao": "diagnostico"}, {"acao": "acionar_robo"}, {"acao": "apagar_tudo"}):
        assert pedir(corpo, cab=AGENDA) == (403, {"message": "A agenda só publica."})
    assert ESTADO["meta"] == [] and ESTADO["storage"] == [] and ESTADO["assinaturas"] == [] and ESTADO["github"] == []
    assert {e: db.execute(estado, (e,)).fetchone() for e in antes} == antes
    # sem a Meta configurada, a peça continua agendada (a agenda chama de novo daqui a 10 minutos, até 3 vezes)
    st, r = pedir({"acao": "publicar", "envio": envios["facebook"]}, cab=AGENDA, porta=PORTA_SEM_META)
    assert st == 503 and "continua guardada" in r["message"] and situacao_envio(db, envios["facebook"]) == ("autorizado", None)
    # a peça vencida sai, uma vez em cada canal
    for envio in envios.values():
        st, r = pedir({"acao": "publicar", "envio": envio}, cab=AGENDA)
        assert (st, r["situacao"]) == (200, "publicado"), r
    assert sorted(p for m, p, _ in ESTADO["meta"] if m == "POST") == ["ig-1/media", "ig-1/media_publish", "pagina-1/photos"]
    assert situacao_envio(db, noticia) == ("autorizado", None) and situacao_envio(db, futura) == ("autorizado", None)


CAMINHO_LEMBRETES = "/github/repos/arteconartescontabeis-design/radar/actions/workflows/radar-lembretes.yml/dispatches"


def test_agenda_aciona_o_robo_dos_lembretes_e_so_ela(peca):
    """v0.29.0: a agenda do banco (sql/radar-redes-agenda.sql, só quando o banco diz que há lembrete para mandar) pede "acionar_lembretes"
    e a função aciona o robô dos lembretes no GitHub: o workflow é FIXO (radar-lembretes.yml, nunca vem do pedido), com o mesmo
    RADAR_GITHUB_TOKEN. O administrador, o editor e o robô do site não acionam. Sem o token ou com a recusa do GitHub, responde 200 com o
    motivo (a rodada de hora em hora do workflow é a reserva); desligado pelo GitHub por inatividade, religa e aciona; desligado à mão,
    fica. Uma vez acionado, a pausa de 60 s não aciona de novo. O registro é um texto fixo, sem o token."""
    db, c1 = peca
    corpo = {"acao": "acionar_lembretes", "workflow": "radar-site-publicar.yml"}               # o workflow do pedido não vale
    assert pedir(corpo, porta=PORTA_GITHUB) == (403, {"message": "Só a agenda do banco aciona os lembretes."})
    assert pedir(corpo, uid=EDITOR, porta=PORTA_GITHUB)[0] == 403
    assert pedir(corpo, cab=ROBO, porta=PORTA_GITHUB)[0] == 403
    assert pedir(corpo, cab={}, porta=PORTA_GITHUB)[0] == 401
    assert pedir(corpo, cab={**AGENDA, "x-radar-agenda": "b2" * 32}, porta=PORTA_GITHUB) == (401, {"message": "Chave não confere."})
    assert ESTADO["github"] == []
    assert pedir(corpo, cab=AGENDA, porta=PORTA_SEM_META) == (200, {"acionado": False, "motivo": "sem_token"})
    for st, motivo in ((401, "token_recusado"), (403, "sem_acesso"), (404, "sem_acesso"), (429, "limite_github"), (500, "erro_github"),
                       (0, "github_fora")):
        ESTADO["github_status"] = st
        assert pedir(corpo, cab=AGENDA, porta=PORTA_GITHUB) == (200, {"acionado": False, "motivo": motivo}), motivo
    assert len(ESTADO["github"]) == 6                                                            # cada recusa: o próximo pedido tenta
    ESTADO["github_status"] = 204
    ESTADO["workflows"]["radar-lembretes.yml"] = "disabled_manually"
    assert pedir(corpo, cab=AGENDA, porta=PORTA_GITHUB) == (200, {"acionado": False, "motivo": "workflow_desligado"})
    assert not [g for g in ESTADO["github_wf"] if g[0] == "PUT"]                                 # o desligado à mão fica
    ESTADO["workflows"]["radar-lembretes.yml"] = "disabled_inactivity"
    assert pedir(corpo, cab=AGENDA, porta=PORTA_GITHUB) == (200, {"acionado": True, "religado": True})
    assert ESTADO["workflows"]["radar-lembretes.yml"] == "active"
    assert pedir(corpo, cab=AGENDA, porta=PORTA_GITHUB) == (200, {"acionado": True, "motivo": "ja_acionado"})   # a pausa de 60 s
    assert {(m, c, a, json.dumps(b)) for m, c, a, b in ESTADO["github"]} == {("POST", CAMINHO_LEMBRETES, "Bearer " + TOKEN_GITHUB, '{"ref": "main"}')}
    assert len(ESTADO["github"]) == 9
    registro = ler_log(PORTA_GITHUB, espera="radar-redes: robô dos lembretes religado e acionado")
    assert "radar-redes: robô dos lembretes não acionado (token_recusado)" in registro and TOKEN_GITHUB not in registro
    assert "Bad credentials" not in registro and ESTADO["meta"] == [] and ESTADO["storage"] == []


def test_agenda_teste_responde_sem_publicar(peca):
    db, c1 = peca
    ig = agendada(db)["instagram"]                                                  # há peça vencida: o teste não a toca
    for porta in (PORTA_FUNCAO, PORTA_SEM_META):                                    # nem precisa da Meta configurada
        assert pedir({"acao": "agenda_teste"}, cab=AGENDA, porta=porta) == (200, {"ok": True, "versao": "0.42.0"})
    assert pedir({"acao": "agenda_teste"}) == (403, {"message": "Só a agenda do banco usa o teste da agenda."})
    assert pedir({"acao": "agenda_teste"}, uid=EDITOR)[0] == 403
    assert pedir({"acao": "agenda_teste"}, cab=ROBO)[0] == 403
    assert pedir({"acao": "agenda_teste"}, cab={})[0] == 401
    assert pedir({"acao": "agenda_teste"}, cab={"Authorization": "Bearer " + jwt("anon")})[0] in (401, 403)   # a chave anon sozinha não vale
    assert ESTADO["meta"] == [] and ESTADO["storage"] == [] and ESTADO["buckets"] == set() and situacao_envio(db, ig) == ("autorizado", None)
    db.execute("delete from vault.secrets where name = 'radar_redes_agenda'")       # sem a chave no Vault: nunca confere
    assert pedir({"acao": "agenda_teste"}, cab=AGENDA) == (401, {"message": "Chave não confere."})


@pytest.mark.parametrize("porta", [PORTA_CHAVE_NOVA, PORTA_LISTA_NOVA], ids=["service_role_key-nova", "secret_keys"])
def test_peca_pela_agenda_com_a_chave_interna_nova_vai_so_no_apikey(peca, porta):
    """Como no projeto da Artecon: a conferência da chave, o início da peça, o bucket privado e o link assinado com a chave nova."""
    db, c1 = peca
    ig = agendada(db)["instagram"]
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA, porta=porta)
    assert (status, r["situacao"]) == (200, "publicado"), r
    caminhos = {c[1] for c in _so_no_apikey()}
    assert {"/rest/v1/rpc/radar_redes_conferir_agenda", "/rest/v1/rpc/radar_pauta_iniciar", "/rest/v1/rpc/radar_rede_concluir",
            "/storage/v1/bucket"} <= caminhos
    assert any(c.startswith("/storage/v1/object/radar-pauta/p-") for c in caminhos)
    assert any(c.startswith("/storage/v1/object/sign/radar-pauta/p-") for c in caminhos)


def test_diagnostico_confere_o_armazenamento_privado_da_pauta(peca):
    db, c1 = peca
    status, r = pedir({"acao": "diagnostico"})
    item = next(i for i in r["itens"] if i["item"] == "Armazenamento das imagens")
    assert status == 200 and r["tudo_certo"] is True and item["ok"] is True and item["detalhe"].startswith('bucket privado "radar-pauta"')
    assert ESTADO["buckets"] == {"radar-pauta"} and ESTADO["publicos"] == set()     # v0.22.0 (rodada 2): o público não é mais criado
    # alguém deixou o "radar-pauta" público no painel: o diagnóstico mostra, e a peça não sai (nenhuma foto vai para lá)
    ESTADO["publicos"].add("radar-pauta")
    status, r = pedir({"acao": "diagnostico"})
    item = next(i for i in r["itens"] if i["item"] == "Armazenamento das imagens")
    assert r["tudo_certo"] is False and item["ok"] is False and 'O armazenamento "radar-pauta" está público' in item["detalhe"]
    ig = agendada(db)["instagram"]
    status, r = pedir({"acao": "publicar", "envio": ig}, cab=AGENDA)
    assert status == 502 and "está público" in r["message"] and ESTADO["storage"] == [] and ESTADO["assinaturas"] == []
    assert not [m for m in ESTADO["meta"] if m[1] in ("ig-1/media", "ig-1/media_publish")]
    assert situacao_envio(db, ig)[0] == "erro"                                      # contado e avisado; "Tentar de novo" depois de arrumar


def test_funcao_nova_com_banco_antigo_publica_noticia(redes):
    """A radar-redes v0.21.0 instalada antes do SQL: o banco ainda não tem radar_redes_envios.peca_id (nem a recusa RADAR171 no início
    da notícia, que é da v0.21.0). A notícia continua saindo: a leitura do envio tenta de novo sem a coluna."""
    db, c1 = redes
    envio = autorizar(db, c1, "instagram")
    original = db.execute("select pg_get_functiondef('public.radar_rede_iniciar(bigint)'::regprocedure)").fetchone()[0]
    trava = re.search(r"\n  -- v0\.21\.0: a peça da Pauta.*?\n  end if;", original, re.S)
    assert trava and "RADAR171" in trava.group(0)
    servico = {"Authorization": "Bearer " + jwt("service_role")}
    ve_peca_id = lambda: requests.get(API + "/radar_redes_envios?select=peca_id&limit=1", headers=servico, timeout=5).status_code == 200
    try:
        db.execute("alter table radar_redes_envios rename column peca_id to peca_id_futura")
        db.execute(original.replace(trava.group(0), ""))                            # radar_rede_iniciar como na v0.20.0
        db.execute("notify pgrst, 'reload schema'")
        for _ in range(50):
            if not ve_peca_id():
                break
            time.sleep(0.1)
        assert not ve_peca_id()
        status, r = pedir({"acao": "publicar", "envio": envio})
        assert status == 200 and r == {"situacao": "publicado", "url": "https://www.instagram.com/p/ABC123/", "post_id": "midia-1"}, r
        leituras = [c for c in ESTADO["chaves"] if c[:2] == ("GET", "/rest/v1/radar_redes_envios")]
        assert len(leituras) == 2                                                    # com peca_id (recusada) e de novo sem ela
        # v0.22.0 (rodada 2): a notícia também vai ao bucket privado, com o link assinado (que não depende do banco)
        assert ESTADO["storage"][0][0].startswith("/storage/v1/object/radar-pauta/p-") and len(ESTADO["assinaturas"]) == 1
        assert db.execute("select situacao, post_id from radar_redes_envios where id = %s", (envio,)).fetchone() == ("publicado", "midia-1")
    finally:
        if db.execute("""select count(*) from information_schema.columns
                         where table_name = 'radar_redes_envios' and column_name = 'peca_id_futura'""").fetchone()[0]:
            db.execute("alter table radar_redes_envios rename column peca_id_futura to peca_id")
        db.execute(original)
        db.execute("notify pgrst, 'reload schema'")
        for _ in range(50):
            if ve_peca_id():
                break
            time.sleep(0.1)
    assert ve_peca_id() and "RADAR171" in db.execute("select prosrc from pg_proc where proname = 'radar_rede_iniciar'").fetchone()[0]


def test_logs_sem_legenda_nome_link_nem_chave(peca):
    """O que a função registra (Supabase → Edge Functions → Logs): só o número do envio, a situação e "(agenda)". Nunca a legenda, o nome
    de quem aparece, o link (assinado ou interno), a chave da agenda ou a mensagem da Meta (que pode repetir a legenda)."""
    db, c1 = peca
    legenda = "Bruno Exemplo conta como cuida da folha de pagamento.\n\n" + IDENT + "\n\n#Contabilidade #Palhoça"
    envios = agendada(db, canais=("instagram", "facebook"), legenda_instagram=legenda, legenda_facebook=legenda)
    ja = len(ler_log())                                       # os números dos envios recomeçam a cada teste: confere só o que veio agora
    assert pedir({"acao": "publicar", "envio": envios["instagram"]}, cab=AGENDA)[0] == 200
    ESTADO["erro_meta"] = "Bruno Exemplo: Application does not have permission"
    assert pedir({"acao": "publicar", "envio": envios["facebook"]}, cab=AGENDA)[0] == 502
    ESTADO["erro_meta"] = None
    assert pedir({"acao": "publicar", "envio": envios["facebook"]}, cab={**AGENDA, "x-radar-agenda": "c3" * 32})[0] == 401
    linha = f"radar-redes: envio {envios['instagram']} → publicado (agenda)"
    texto = ler_log(espera=linha)
    assert texto[ja:].strip() == linha, texto[ja:]            # um registro só, do que saiu; o erro da Meta e a chave errada não registram
    interna = db.execute("select imagem_url from radar_redes_envios where id = %s", (envios["instagram"],)).fetchone()[0]
    for proibido in ("Bruno", "Exemplo", "folha de pagamento", "11.222.333", "CRC-SC", "radar-pauta", "token=", interna, CHAVE_AGENDA, "c3c3",
                     "permission", TOKEN, TOKEN_PAGINA, TOKEN_IG, "eyJ"):
        assert proibido not in texto, proibido


def test_funcao_passa_na_conferencia_de_tipos_do_deno():
    """A função é colada no editor do Supabase e pode ser publicada por um caminho que confere os tipos: o "deno check" passa limpo
    (o "deno run" dos outros testes não confere tipos)."""
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    r = subprocess.run(["deno", "check", str(RAIZ / "supabase" / "functions" / "radar-redes" / "index.ts")], capture_output=True, text=True,
                       timeout=300, env=dict(os.environ, NO_COLOR="1"))
    assert r.returncode == 0, r.stdout + r.stderr
