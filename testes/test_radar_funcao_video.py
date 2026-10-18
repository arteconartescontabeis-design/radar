"""Função radar-video (v0.22.0) rodando de verdade no Deno, com o banco real (PostgREST), um armazenamento (Supabase Storage) de mentira e
uma API do GitHub de mentira. Sem o Deno instalado, o arquivo é pulado. Nenhuma chamada à Azure: a transcrição é do robô (ajustes do
dono), e aqui o robô é o próprio teste, com o token estreito do Vault (de mentira).

Confere:
  * quem chama: a tela (editor ou administrador; o leitor e o visitante não), o robô (x-radar-video-robo) e a agenda (x-radar-agenda),
    cada um só nas suas ações; a chave errada recebe sempre a mesma recusa; nenhuma chave interna do Supabase é aceita como quem chama;
  * o envio do navegador: o banco confere tudo ANTES (nenhum token sai se a fala não está no roteiro), um token de envio por clipe,
    sem upsert, num bucket que nasce PRIVADO; a renovação só dos que faltam; o fim do envio confere tamanho e tipo de cada clipe e
    aciona o robô no repositório privado;
  * o robô: pegar (links de leitura de 600 s e o token do palavras.json), o pedido que volta à fila se o armazenamento falha, links só
    dos caminhos do pedido, o corrigido que nunca se sobrescreve, o áudio, o parcial e o concluir que confere o vídeo e os 4 quadros;
  * a prévia sempre com 600 s (o que vier no pedido não conta) e o baixar com 300 s e o nome reel-<data>.mp4, só do aprovado;
  * a limpeza apaga pela API do armazenamento só o que o banco manda (as versões antigas, sem tocar na atual);
  * o diagnóstico devolve o bucket público a privado; o acionamento só com fila, com pausa e sem mostrar o token;
  * os registros e as respostas de erro não levam link assinado, token, chave, nome nem fala.
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
import uuid as uuidlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import pytest
import requests

from conftest import ADMIN, API, EDITOR, LEITOR, RAIZ, SECRETA, VAULT_SIMULADO, como, gateway, jwt
from test_radar_banco import IDENT, SHA_VIDEO, aprovar_peca, hoje, marcar_pronta, pauta  # noqa: F401
from test_radar_video_banco import DECL, DIVERGENCIA, FALA, PARTES, RELATORIO, corretor, na_fila, reel, video  # noqa: F401

PORTA_PONTE, PORTA_FUNCAO, PORTA_SEM_TOKEN, PORTA_ACIONAR = 3978, 3977, 3976, 3975
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
TOKEN_GITHUB = "githubTokenSecretoDoVideo987"
CHAVE_ROBO = "r0b0" * 16                                   # 'radar_video_robo' do Vault (de mentira)
CHAVE_AGENDA = "ag3n" * 16                                 # 'radar_video_agenda'
ANON = {"Authorization": "Bearer " + jwt("anon")}
ROBO = {**ANON, "x-radar-video-robo": CHAVE_ROBO}
AGENDA = {**ANON, "x-radar-agenda": CHAVE_AGENDA}
REPO = "/github/repos/arteconartescontabeis-design/radar-video/actions/workflows/radar-video.yml"
SHA2 = "c" * 64
ARM: dict = {}                                              # o armazenamento de mentira (zerado a cada teste)
LOGS: dict = {}


def zerar():
    ARM.clear()
    ARM.update(buckets={}, objetos={}, tokens={}, envios=[], assinaturas=[], apagados=[], atualizados=[], falha_assinar=False,
               github=[], github_status=204, links={},
               # o limite global de arquivo do projeto (no Free, 50 MB): o bucket com limite maior é recusado (EntityTooLarge)
               limite_global=50 * 1024 * 1024, falha_bucket=False,
               # v0.22.0, a tela (test_radar_telas.py): o envio retomável (TUS) e as falhas de rede que ele tem de aguentar
               tus={}, tus_pedidos=[], tus_pedacos=0, tus_falhar=0, tus_cair=0, tus_parar=None,
               # varredura geral (v0.22.0): o PostgREST com falha passageira num caminho ({trecho do caminho: status 5xx})
               rest_5xx={})


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST; /storage/v1 → armazenamento de mentira (bucket, objetos, tokens de envio, links assinados — e o GET deles,
    para o robô de verdade de test_radar_video_corrigir.py e para a prévia da tela —, lista e exclusão, como a API do Supabase Storage;
    e o envio retomável do navegador, TUS, em test_radar_telas.py); /github → API do GitHub."""
    def _responder(self, status, corpo=None, tipo="application/json"):
        dados = b"" if corpo is None else corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _corpo(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def _servico(self):
        """O armazenamento de verdade só atende a chave interna (a sb_secret_ só no apikey)."""
        auth = gateway(self.headers)
        if auth != "Bearer " + jwt("service_role"):
            self._responder(400, {"statusCode": "403", "error": "Unauthorized", "message": "new row violates row-level security policy"})
            return False
        return True

    def _rest(self):
        auth = gateway(self.headers)
        if auth is None:
            return self._responder(401, {"message": "Invalid Compact JWS"})
        for trecho, status in ARM.get("rest_5xx", {}).items():
            if trecho in self.path:
                self._corpo()
                return self._responder(status, {"code": "PGRST003", "message": "Timed out acquiring connection from connection pool."})
        corpo = self._corpo() or None
        cab = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "prefer")} | ({"Authorization": auth} if auth else {})
        r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo, timeout=30)
        self._responder(r.status_code, r.content)

    def _armazenamento(self):
        url = urlparse(self.path)
        caminho = url.path.removeprefix("/storage/v1/")
        consulta = {k: v[0] for k, v in parse_qs(url.query).items()}
        corpo = self._corpo()
        if caminho == "upload/resumable/sign" or caminho.startswith("upload/resumable/sign/"):
            return self._tus(caminho.removeprefix("upload/resumable/sign").lstrip("/"), corpo)
        # o envio com o token (o navegador e o robô): sem a chave interna, só com o token daquele caminho
        if self.command == "PUT" and caminho.startswith("object/upload/sign/radar-videos/"):
            objeto = caminho.removeprefix("object/upload/sign/radar-videos/")
            if ARM["tokens"].get(consulta.get("token")) != objeto:
                return self._responder(400, {"statusCode": "403", "error": "Unauthorized", "message": "invalid signature"})
            if objeto in ARM["objetos"]:
                return self._responder(400, {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"})
            ARM["objetos"][objeto] = {"bytes": len(corpo), "tipo": self.headers.get("Content-Type", ""), "dados": corpo}
            return self._responder(200, {"Key": "radar-videos/" + objeto})
        # o link assinado de leitura (o robô baixa por ele): só com o token daquele caminho
        if self.command == "GET" and caminho.startswith("object/sign/radar-videos/"):
            objeto = caminho.removeprefix("object/sign/radar-videos/")
            o = ARM["objetos"].get(objeto)
            if ARM["links"].get(consulta.get("token")) != objeto or o is None:
                return self._responder(400, {"statusCode": "404", "error": "not_found", "message": "Object not found"})
            dados, tipo = o.get("dados") or b"x" * o["bytes"], o.get("tipo") or "application/octet-stream"
            # v0.33.0: como o Storage, serve pedaços (Range): o player da aba Vídeo vai a qualquer ponto do vídeo
            pedaco = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range") or "")
            ini = int(pedaco.group(1)) if pedaco else 0
            fim = min(len(dados) - 1, int(pedaco.group(2))) if pedaco and pedaco.group(2) else len(dados) - 1
            corpo = dados[ini:fim + 1] if pedaco else dados
            self.send_response(206 if pedaco else 200)
            self.send_header("Content-Type", tipo)
            self.send_header("Accept-Ranges", "bytes")
            if pedaco:
                self.send_header("Content-Range", f"bytes {ini}-{fim}/{len(dados)}")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)
            return
        if not self._servico():
            return
        dados = json.loads(corpo or b"null")
        if self.command == "GET" and caminho.startswith("bucket/"):
            b = ARM["buckets"].get(caminho.removeprefix("bucket/"))
            return self._responder(200, b) if b else self._responder(400, {"statusCode": "404", "error": "Bucket not found", "message": "Bucket not found"})
        # o Storage confere o limite do bucket contra o limite global do projeto (parseMaxSizeLimit: EntityTooLarge)
        grande = {"statusCode": "413", "error": "Payload too large", "message": "The object exceeded the maximum allowed size"}
        if self.command == "POST" and caminho == "bucket":
            if ARM["falha_bucket"]:
                return self._responder(500, {"statusCode": "500", "error": "internal", "message": "fora do ar"})
            if dados["id"] in ARM["buckets"]:
                return self._responder(400, {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"})
            if (dados.get("file_size_limit") or 0) > ARM["limite_global"]:
                return self._responder(413, grande)
            ARM["buckets"][dados["id"]] = dados
            return self._responder(200, {"name": dados["id"]})
        if self.command == "PUT" and caminho.startswith("bucket/"):
            if (dados.get("file_size_limit") or 0) > ARM["limite_global"]:
                return self._responder(413, grande)
            ARM["atualizados"].append(dados)
            ARM["buckets"][caminho.removeprefix("bucket/")].update(dados)
            return self._responder(200, {"message": "Successfully updated"})
        if self.command == "POST" and caminho.startswith("object/upload/sign/radar-videos/"):
            objeto = caminho.removeprefix("object/upload/sign/radar-videos/")
            token = f"envio.{uuidlib.uuid4().hex}"
            ARM["tokens"][token] = objeto
            ARM["envios"].append((objeto, self.headers.get("x-upsert")))
            return self._responder(200, {"url": f"/object/upload/sign/radar-videos/{objeto}?token={token}"})
        if self.command == "POST" and caminho.startswith("object/sign/radar-videos/"):
            objeto = caminho.removeprefix("object/sign/radar-videos/")
            ARM["assinaturas"].append((objeto, dados.get("expiresIn")))
            if ARM["falha_assinar"] or objeto not in ARM["objetos"]:
                return self._responder(400, {"statusCode": "404", "error": "not_found", "message": "Object not found: " + objeto})
            ARM["links"][f"assinado.{len(ARM['assinaturas'])}"] = objeto
            return self._responder(200, {"signedURL": f"/object/sign/radar-videos/{objeto}?token=assinado.{len(ARM['assinaturas'])}"})
        if self.command == "POST" and caminho == "object/list/radar-videos":
            prefixo = dados["prefix"].rstrip("/") + "/"
            itens = {}
            for nome, o in ARM["objetos"].items():
                if nome.startswith(prefixo):
                    resto = nome[len(prefixo):]
                    if "/" in resto:
                        itens[resto.split("/")[0]] = {"name": resto.split("/")[0], "id": None, "metadata": None}
                    else:
                        itens[resto] = {"name": resto, "id": str(uuidlib.uuid4()), "metadata": {"size": o["bytes"], "mimetype": o["tipo"]}}
            lista = [itens[k] for k in sorted(itens)][dados.get("offset", 0):dados.get("offset", 0) + dados.get("limit", 100)]
            return self._responder(200, lista)
        if self.command == "DELETE" and caminho == "object/radar-videos":
            ARM["apagados"].extend(dados["prefixes"])
            fora = [{"name": k} for k in dados["prefixes"] if ARM["objetos"].pop(k, None) is not None]
            return self._responder(200, fora)
        self._responder(404, {})

    def _tus(self, uid, corpo):
        """O envio retomável (TUS 1.0.0) na rota "/sign" do Storage: o token de envio de um caminho só no x-signature (sem sessão), o
        POST com o tamanho e os metadados (bucketName, objectName, contentType, cacheControl em base64), o HEAD com o Upload-Offset e o
        PATCH em pedaços de 6 MiB (o último menor). Sem x-upsert, o caminho que já existe dá 409. Falhas de mentira: tus_falhar (o pedaço
        não chega), tus_cair (o pedaço chega e a resposta não) e tus_parar (depois de tantos pedaços, nenhum chega mais)."""
        cab = {k.lower(): v for k, v in self.headers.items()}
        ARM["tus_pedidos"].append({"metodo": self.command, "id": uid, "offset": cab.get("upload-offset"), "bytes": len(corpo),
                                   "assinatura": cab.get("x-signature"), "apikey": cab.get("apikey"), "upsert": cab.get("x-upsert"),
                                   "autorizacao": cab.get("authorization"), "tus": cab.get("tus-resumable"), "tipo": cab.get("content-type"),
                                   "metadados": cab.get("upload-metadata"), "tamanho": cab.get("upload-length")})

        def resp(status, extra=None, dados=b""):
            self.send_response(status)
            for k, v in {"Tus-Resumable": "1.0.0", "Content-Type": "application/json", **(extra or {})}.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            if self.command != "HEAD" and dados:
                self.wfile.write(dados)
        if cab.get("tus-resumable") != "1.0.0":
            return resp(412)
        objeto_do_token = ARM["tokens"].get(cab.get("x-signature"))
        if self.command == "POST" and not uid:
            meta = {}
            for par in (cab.get("upload-metadata") or "").split(","):
                if " " in par.strip():
                    k, v = par.strip().split(" ", 1)
                    meta[k] = base64.b64decode(v).decode()
            if meta.get("bucketName") != "radar-videos" or not objeto_do_token or objeto_do_token != meta.get("objectName"):
                return resp(403, dados=b'{"statusCode":"403","error":"Unauthorized","message":"invalid signature"}')
            if cab.get("x-upsert") is None and meta["objectName"] in ARM["objetos"]:
                return resp(409, dados=b'{"statusCode":"409","error":"Duplicate","message":"Asset Already Exists"}')
            novo = uuidlib.uuid4().hex
            ARM["tus"][novo] = {"objeto": meta["objectName"], "tipo": meta.get("contentType", ""), "cache": meta.get("cacheControl"),
                                "tamanho": int(cab.get("upload-length") or 0), "dados": bytearray()}
            return resp(201, {"Location": f"/storage/v1/upload/resumable/sign/{novo}"})
        u = ARM["tus"].get(uid)
        if u is None:
            return resp(404)
        if objeto_do_token != u["objeto"]:
            return resp(403, dados=b'{"statusCode":"403","error":"Unauthorized","message":"invalid signature"}')
        if self.command == "HEAD":
            return resp(200, {"Upload-Offset": str(len(u["dados"])), "Upload-Length": str(u["tamanho"]), "Cache-Control": "no-store"})
        if self.command != "PATCH":
            return resp(405)
        if cab.get("content-type") != "application/offset+octet-stream":
            return resp(415)
        if ARM["tus_falhar"] > 0 or (ARM["tus_parar"] is not None and ARM["tus_pedacos"] >= ARM["tus_parar"]):
            ARM["tus_falhar"] = max(0, ARM["tus_falhar"] - 1)
            return resp(502)
        if int(cab.get("upload-offset") or -1) != len(u["dados"]):
            return resp(409, dados=b'{"error":"offset"}')
        fim = len(u["dados"]) + len(corpo)
        if fim > u["tamanho"] or (fim < u["tamanho"] and len(corpo) != 6 * 1024 * 1024):     # o Supabase pede pedaços de 6 MiB
            return resp(400, dados=b'{"error":"chunk size"}')
        u["dados"] += corpo
        ARM["tus_pedacos"] += 1
        if len(u["dados"]) == u["tamanho"]:
            ARM["objetos"][u["objeto"]] = {"bytes": u["tamanho"], "tipo": u["tipo"], "dados": bytes(u["dados"]), "cache": u["cache"]}
        if ARM["tus_cair"] > 0:
            ARM["tus_cair"] -= 1
            return resp(502)
        return resp(204, {"Upload-Offset": str(len(u["dados"]))})

    def _github(self):
        corpo = self._corpo()
        ARM["github"].append((self.command, self.path, self.headers.get("Authorization"), json.loads(corpo or b"null")))
        if self.headers.get("Authorization") != "Bearer " + TOKEN_GITHUB or ARM["github_status"] == 401:
            return self._responder(401, {"message": "Bad credentials " + TOKEN_GITHUB})
        if self.command == "GET" and self.path == REPO:
            return self._responder(200, {"id": 1, "name": "Radar — corretor de vídeo", "state": "active"})
        if self.command == "POST" and self.path == REPO + "/dispatches":
            self.send_response(ARM["github_status"])
            self.end_headers()
            return
        self._responder(404, {"message": "Not Found"})

    def do_GET(self):
        return self._rest() if self.path.startswith("/rest/v1/") else self._armazenamento() if self.path.startswith("/storage/v1/") \
            else self._github() if self.path.startswith("/github/") else self._responder(404, {})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_GET

    def log_message(self, *a):
        pass


def _subir(porta, extra, pasta):
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), SUPABASE_SERVICE_ROLE_KEY=jwt("service_role"),
                    RADAR_GITHUB_API=PONTE + "/github", RADAR_PORTA_LOCAL=str(porta), RADAR_VIDEO_ARMAZENAMENTO_MS="5000", NO_COLOR="1")
    for nome in ("SUPABASE_SECRET_KEYS", "RADAR_VIDEO_GITHUB_TOKEN", "RADAR_VIDEO_GITHUB_REPO", "RADAR_VIDEO_GITHUB_RAMO"):
        ambiente.pop(nome, None)
    ambiente.update(extra)
    LOGS[porta] = pasta / f"radar-video-{porta}.log"
    with open(LOGS[porta], "wb") as saida:
        proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                                 str(RAIZ / "supabase" / "functions" / "radar-video" / "index.ts")],
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
    pasta = tmp_path_factory.mktemp("radar-video")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    processos = []
    try:
        processos.append(_subir(PORTA_FUNCAO, {"RADAR_VIDEO_GITHUB_TOKEN": TOKEN_GITHUB}, pasta))
        processos.append(_subir(PORTA_SEM_TOKEN, {"SUPABASE_SERVICE_ROLE_KEY": SECRETA}, pasta))      # a chave nova, como no projeto
        processos.append(_subir(PORTA_ACIONAR, {"RADAR_VIDEO_GITHUB_TOKEN": TOKEN_GITHUB}, pasta))      # só para a pausa de 30 s
        yield
    finally:
        for p in processos:
            p.terminate()
        ponte.shutdown()
        ponte.server_close()


@pytest.fixture()
def vid(funcao, corretor):
    """A Pauta (CNPJ e CRC de mentira), as Configurações do corretor no padrão, o armazenamento vazio e o Vault de mentira com as duas
    chaves do corretor. Devolve o banco."""
    db = corretor
    zerar()
    tinha = db.execute("select count(*) from pg_namespace where nspname = 'vault'").fetchone()[0] == 1
    if not tinha:
        db.execute(VAULT_SIMULADO)
    db.execute("insert into vault.secrets (name, secret) values ('radar_video_robo', %s), ('radar_video_agenda', %s)", (CHAVE_ROBO, CHAVE_AGENDA))
    try:
        yield db
    finally:
        if tinha:
            db.execute("delete from vault.secrets where name in ('radar_video_robo', 'radar_video_agenda')")
        else:
            db.execute("drop schema vault cascade")


def pedir(corpo, uid=EDITOR, porta=PORTA_FUNCAO, cab=None):
    cab = cab if cab is not None else {"Authorization": "Bearer " + jwt("authenticated", uid), "apikey": jwt("anon")}
    r = requests.post(f"http://127.0.0.1:{porta}/", timeout=60, json=corpo, headers=cab)
    return r.status_code, r.json()


def subir(url_ou_caminho, dados: bytes, tipo: str, token=None):
    """O envio com o token (o navegador manda por TUS com x-signature; aqui, como o robô, por PUT no endereço assinado)."""
    url = url_ou_caminho if url_ou_caminho.startswith("http") else \
        f"{PONTE}/storage/v1/object/upload/sign/radar-videos/{url_ou_caminho}?token={quote(token)}"
    return requests.put(url, data=dados, headers={"Content-Type": tipo}, timeout=10).status_code


def guardar(caminho, n_bytes=10, tipo="video/mp4", dados=None):
    ARM["objetos"][caminho] = {"bytes": len(dados) if dados is not None else n_bytes, "tipo": tipo, "dados": dados}


def envio(db, pid, pessoa, **extra):
    return {"acao": "envio_iniciar", "peca": pid, "partes": PARTES, "fala_pessoa": pessoa, "fala_roteiro": FALA, "cartela": [IDENT],
            "gancho": False, "declaracoes": DECL, **extra}


def na_fila_com_clipes(db):
    pid, ana = reel(db)
    v = na_fila(db, pid, ana)
    for p in PARTES:
        guardar(f"bruto/{v}/{p['n']}", p["bytes"], p["tipo"])
    return pid, ana, v


# ------------------------------------------------------------------ quem chama
def test_quem_chama_cada_um_nas_suas_acoes_e_nunca_a_chave_interna(vid):
    assert pedir({"acao": "previa", "id": str(uuidlib.uuid4())}, cab={}) == (401, {"message": "Sessão não informada."})
    assert pedir({"acao": "previa", "id": str(uuidlib.uuid4())}, cab=ANON)[0] == 401                    # o visitante (só a anon)
    assert pedir({"acao": "previa", "id": str(uuidlib.uuid4())}, uid=LEITOR) == (403, {"message": "Só o editor ou o administrador usa o corretor de vídeo."})
    assert pedir({"acao": "pegar"}) == (403, {"message": "Esta ação é só do robô ou da agenda."})
    assert pedir({"acao": "limpar"}, uid=ADMIN)[0] == 403 and pedir({"acao": "outra"})[0] == 400
    assert pedir({"acao": "diagnostico"}) == (403, {"message": "Só o administrador vê o diagnóstico do corretor de vídeo."})
    interna = "A chave interna do Supabase não chama o corretor de vídeo."
    for cab in ({"Authorization": "Bearer " + jwt("service_role"), "apikey": jwt("service_role")}, {"apikey": SECRETA},
                {**ROBO, "apikey": SECRETA}, {**AGENDA, "Authorization": "Bearer " + jwt("service_role")}, {"Authorization": "Bearer sb_secret_outro123456789"}):
        assert pedir({"acao": "pegar"}, cab=cab) == (403, {"message": interna}), cab
    errada = (401, {"message": "Chave não confere."})
    for cab in ({**ANON, "x-radar-video-robo": "x" * 64}, {**ANON, "x-radar-video-robo": CHAVE_AGENDA}, {**ANON, "x-radar-agenda": CHAVE_ROBO},
                {**ANON, "x-radar-agenda": "curta"}, {**ROBO, "x-radar-agenda": CHAVE_AGENDA}):
        assert pedir({"acao": "pegar"}, cab=cab) == errada, cab
    assert pedir({"acao": "previa", "id": str(uuidlib.uuid4())}, cab=ROBO) == (403, {"message": "O robô só pega o pedido, pede links e entrega o resultado."})
    assert pedir({"acao": "pegar"}, cab=AGENDA) == (403, {"message": "A agenda só aciona o robô e faz a limpeza."})
    assert pedir({"acao": "agenda_teste"}, cab=AGENDA) == (200, {"ok": True, "versao": "0.33.0"})
    assert pedir({"acao": "pegar"}, cab=ROBO) == (200, {"pedido": None})
    assert pedir({"acao": "pe gar"}, cab=ROBO)[0] == 403 and pedir({"acao": "PEGAR"}, cab=ROBO)[0] == 403   # o nome exato da ação
    assert ARM["objetos"] == {} and ARM["envios"] == [] and ARM["github"] == []


# ------------------------------------------------------------------ envio pelo navegador
def test_envio_confere_no_banco_antes_e_da_um_token_por_clipe_num_bucket_privado(vid):
    db = vid
    pid, ana = reel(db)
    # o armazenamento fora do ar: nada fica registrado (nem gasta uma das 50 gravações da peça)
    ARM["falha_bucket"] = True
    status, r = pedir(envio(db, pid, ana))
    assert status == 502 and r["message"].startswith("Não foi possível criar o armazenamento dos vídeos (500). Nada foi enviado")
    assert db.execute("select count(*) from radar_videos where peca_id = %s", (pid,)).fetchone()[0] == 0
    ARM["falha_bucket"] = False
    status, r = pedir(envio(db, pid, ana, fala_roteiro=FALA.replace("dia 20", "dia 25")))
    assert status == 400 and r["message"].startswith("a fala para conferência tem de estar no roteiro")
    assert ARM["envios"] == []                                                             # nenhum token antes da conferência do banco
    status, r = pedir(envio(db, pid, ana))
    assert status == 200 and r["versao"] == 1 and r["bucket"] == "radar-videos" and r["cache_s"] == 60
    v = r["id"]
    assert [(e["n"], e["caminho"]) for e in r["envios"]] == [(1, f"bruto/{v}/1"), (2, f"bruto/{v}/2")]
    assert ARM["envios"] == [(f"bruto/{v}/1", None), (f"bruto/{v}/2", None)]                # sem x-upsert: o caminho nunca se sobrescreve
    # privado e sem limite próprio de tamanho (vale o global do projeto: no Free, 50 MB, e o bucket com 500 MB não nasceria)
    assert ARM["buckets"]["radar-videos"] == {"id": "radar-videos", "name": "radar-videos", "public": False,
                                              "allowed_mime_types": ["video/mp4", "video/quicktime", "application/json", "image/jpeg"]}
    assert video(db, v) == "aguardando_envio"
    # nada chegou: o fim do envio recusa; chegou só o 1º: a renovação dá token só ao 2º
    assert pedir({"acao": "envio_concluido", "id": v}) == (409, {"message": "Ainda faltam clipes no armazenamento (nº 1, 2): retome o envio."})
    assert subir(f"bruto/{v}/1", b"x" * 1000, "video/mp4", r["envios"][0]["token"]) == 200
    assert subir(f"bruto/{v}/2", b"x" * 1000, "video/mp4", r["envios"][0]["token"]) == 400       # o token é de um caminho só
    assert subir(f"bruto/{v}/1", b"y" * 1000, "video/mp4", r["envios"][0]["token"]) == 400       # e não sobrescreve
    status, novo = pedir({"acao": "envio_renovar", "id": v})
    assert status == 200 and novo["prontos"] == [1] and [e["n"] for e in novo["envios"]] == [2]
    assert subir(f"bruto/{v}/2", b"z" * 1999, "video/quicktime", novo["envios"][0]["token"]) == 200   # 1 byte a menos que o declarado
    assert pedir({"acao": "envio_concluido", "id": v}) == (409, {
        "message": "Os clipes nº 2 chegaram diferentes do que a tela declarou (tamanho ou tipo): envie a gravação de novo."})
    assert video(db, v) == "aguardando_envio" and ARM["github"] == []
    del ARM["objetos"][f"bruto/{v}/2"]
    status, novo = pedir({"acao": "envio_renovar", "id": v}, uid=ADMIN)                           # o administrador também continua
    assert subir(f"bruto/{v}/2", b"z" * 2000, "video/quicktime", novo["envios"][0]["token"]) == 200
    status, fim = pedir({"acao": "envio_concluido", "id": v})
    assert status == 200 and fim["situacao"] == "na_fila" and fim["robo"]["acionado"] is True
    assert video(db, v) == "na_fila"
    assert ARM["github"] == [("POST", REPO + "/dispatches", "Bearer " + TOKEN_GITHUB, {"ref": "main"})]
    assert pedir({"acao": "envio_renovar", "id": v})[0] == 400                                    # já foi para a fila


# ------------------------------------------------------------------ robô
def test_robo_pega_le_os_clipes_grava_a_transcricao_e_conclui_conferido(vid):
    db = vid
    pid, ana, v = na_fila_com_clipes(db)
    status, r = pedir({"acao": "pegar"}, cab=ROBO)
    assert status == 200 and r["pedido"]["id"] == v and r["pedido"]["tentativa"] == 1 and r["pedido"]["modo"] == "completo"
    assert [(p["n"], p["url"].split("?")[0]) for p in r["links"]["partes"]] == [
        (n, f"{PONTE}/storage/v1/object/sign/radar-videos/bruto/{v}/{n}") for n in (1, 2)]
    assert r["links"]["palavras"] is None and r["envio_palavras"]["caminho"] == f"trabalho/{v}/1/palavras.json"
    assert {e for _, e in ARM["assinaturas"]} == {600} and r["expira_s"] == 600
    assert pedir({"acao": "pegar"}, cab=ROBO) == (200, {"pedido": None})
    # a transcrição (o passo do workflow) sobe o palavras.json pelo token e registra os segundos
    assert subir(r["envio_palavras"]["url"], b'{"palavras": []}', "application/json") == 200
    status, a = pedir({"acao": "audio", "id": v, "tentativa": 1, "segundos": 31.5}, cab=ROBO)
    assert status == 200 and a == {"palavras_guardadas": True, "restante_s": 1768.5}
    assert video(db, v, "palavras_tentativa, segundos_audio") == (1, 31.5)
    # links: só os caminhos do pedido que está com o robô, nesta rodada
    outro = str(uuidlib.uuid4())
    for ler, gravar in ([f"bruto/{outro}/1"], []), ([f"bruto/{v}/3"], []), ([f"bruto/{v}/01"], []), ([f"bruto/{v}/1/../2"], []), \
                       ([], [f"bruto/{v}/1"]), ([], [f"trabalho/{v}/2/palavras.json"]), ([], [f"corrigido/{v}/{'A' * 64}.mp4"]), \
                       ([], [f"quadros/{v}/{SHA_VIDEO}/q5.jpg"]), ([], [f"corrigido/{outro}/{SHA_VIDEO}.mp4"]):
        status, x = pedir({"acao": "links", "id": v, "tentativa": 1, "ler": ler, "gravar": gravar}, cab=ROBO)
        assert (status, x) == (403, {"message": "1 caminho(s) fora do pedido."}), (ler, gravar)
    assert pedir({"acao": "links", "id": v, "tentativa": 2, "ler": [f"bruto/{v}/1"]}, cab=ROBO)[0] == 400   # rodada errada
    caminhos = [f"corrigido/{v}/{SHA_VIDEO}.mp4"] + [f"quadros/{v}/{SHA_VIDEO}/q{k}.jpg" for k in range(1, 5)]
    status, ln = pedir({"acao": "links", "id": v, "tentativa": 1, "ler": [f"bruto/{v}/2"], "gravar": caminhos}, cab=ROBO)
    assert status == 200 and set(ln["gravar"]) == set(caminhos) and list(ln["ler"]) == [f"bruto/{v}/2"]
    assert all(e[1] is None for e in ARM["envios"])
    assert subir(ln["gravar"][caminhos[0]]["url"], b"m" * 4000, "video/mp4") == 200
    assert pedir({"acao": "links", "id": v, "tentativa": 1, "gravar": caminhos[:1]}, cab=ROBO) == (409, {
        "message": "O vídeo corrigido com este sha256 já está no armazenamento: o caminho nunca se sobrescreve."})
    assert pedir({"acao": "parcial", "id": v, "tentativa": 1, "relatorio": {"divergencias": []}}, cab=ROBO) == (200, True)
    fim = {"acao": "concluir", "id": v, "tentativa": 1, "situacao": "pronto", "relatorio": RELATORIO, "sha256": SHA_VIDEO, "bytes": 4000, "duracao": 38.4}
    assert pedir(fim, cab=ROBO) == (409, {"message": "Faltam quadros no armazenamento (q1, q2, q3, q4): suba de novo."})
    for k in range(1, 5):
        assert subir(ln["gravar"][caminhos[k]]["url"], b"j" * 300, "image/jpeg") == 200
    assert pedir({**fim, "bytes": 3999}, cab=ROBO) == (409, {"message": "O vídeo corrigido não está no armazenamento com o tamanho e o tipo informados: suba de novo."})
    assert pedir({**fim, "relatorio": {**RELATORIO, "divergencias": [DIVERGENCIA]}}, cab=ROBO) == (200, {"situacao": "regravar"})   # o banco decide
    assert pedir(fim, cab=ROBO)[0] == 400                                                        # já não é mais dele
    # a prévia: sempre 600 s, ainda que o pedido peça outro prazo
    ARM["assinaturas"].clear()
    status, p = pedir({"acao": "previa", "id": v, "expiresIn": 999999, "prazo": 999999})
    assert status == 200 and p["sha256"] == SHA_VIDEO and p["expira_s"] == 600 and len(p["quadros"]) == 4
    assert sorted(ARM["assinaturas"]) == [(f"corrigido/{v}/{SHA_VIDEO}.mp4", 600)] + [(f"quadros/{v}/{SHA_VIDEO}/q{k}.jpg", 600) for k in range(1, 5)]
    assert p["video"].startswith(f"{PONTE}/storage/v1/object/sign/radar-videos/corrigido/{v}/")
    assert db.execute("select acao, usuario::text from radar_video_acessos").fetchall() == [("previa", EDITOR)]
    assert pedir({"acao": "previa", "id": v}, uid=LEITOR)[0] == 403


def test_falha_passageira_do_banco_vai_como_502_e_o_robo_repete(vid):
    """Varredura geral (v0.22.0): o 500, o 503 e o 504 do PostgREST (tempo esgotado, banco reiniciando, pool sem conexão) viravam 400:
    o robô tratava como "robo_recusado", não repetia, e o pedido ia a "erro" de vez (e os segundos do áudio não entravam na cota). Agora
    vão como 502, que o robô (conversa.py) repete e trata como passageiro; a recusa de uma regra (RADARnnn) continua 400."""
    import importlib, sys
    db = vid
    pid, ana, v = na_fila_com_clipes(db)
    assert pedir({"acao": "pegar"}, cab=ROBO)[0] == 200
    for st in (500, 503, 504):
        ARM["rest_5xx"] = {"rpc/radar_video_registrar_audio": st}
        assert pedir({"acao": "audio", "id": v, "tentativa": 1, "segundos": 31.5}, cab=ROBO) == \
            (502, {"message": "O banco não respondeu. Tente de novo em alguns minutos."}), st
    ARM["rest_5xx"] = {}
    assert pedir({"acao": "audio", "id": v, "tentativa": 1, "segundos": 31.5}, cab=ROBO)[0] == 200
    assert video(db, v, "segundos_audio") == 31.5
    assert pedir({"acao": "audio", "id": v, "tentativa": 9, "segundos": 1}, cab=ROBO)[0] == 400       # regra: continua recusa
    sys.path.insert(0, str(RAIZ / "robo" / "video"))
    try:
        conversa = importlib.import_module("conversa")
    finally:
        sys.path.remove(str(RAIZ / "robo" / "video"))
    assert conversa._codigo(502, b'{"message": "O banco n\\u00e3o respondeu."}') == "storage"     # o robô repete
    assert conversa._codigo(400, b'{"message": "Erro 503 no banco."}') == "robo_recusado"           # (o que acontecia antes)


def test_pegar_sem_os_links_devolve_o_pedido_a_fila_e_falhar_tambem(vid):
    db = vid
    pid, ana = reel(db)
    v = na_fila(db, pid, ana)                                       # os clipes não estão no armazenamento
    status, r = pedir({"acao": "pegar"}, cab=ROBO)
    assert status == 502 and "Object not found" not in r["message"] and "bruto/" not in r["message"]
    assert video(db, v, "situacao, erro_codigo, tentativas") == ("na_fila", "storage", 1)
    for p in PARTES:
        guardar(f"bruto/{v}/{p['n']}", p["bytes"], p["tipo"])
    status, r = pedir({"acao": "pegar"}, cab=ROBO)
    assert status == 200 and r["pedido"]["tentativa"] == 2
    # transcreveu e o armazenamento caiu depois: volta à fila só para a montagem (a cota não é gasta de novo)
    subir(r["envio_palavras"]["url"], b"{}", "application/json")
    pedir({"acao": "audio", "id": v, "tentativa": 2, "segundos": 12}, cab=ROBO)
    assert pedir({"acao": "falhar", "id": v, "tentativa": 2, "codigo": "storage"}, cab=ROBO) == (200, {"situacao": "na_fila"})
    assert video(db, v, "modo, palavras_tentativa") == ("montagem", 2)
    status, r = pedir({"acao": "pegar"}, cab=ROBO)
    assert (r["pedido"]["modo"], r["envio_palavras"]) == ("montagem", None) and f"trabalho/{v}/2/palavras.json" in r["links"]["palavras"]
    assert pedir({"acao": "falhar", "id": v, "tentativa": 3, "codigo": "sem_audio"}, cab=ROBO) == (200, {"situacao": "erro"})
    assert video(db, v, "situacao, erro_codigo") == ("erro", "sem_audio")


def test_montagem_le_a_transcricao_guardada_e_nao_ganha_token_de_transcricao(vid):
    db = vid
    pid, ana, v = na_fila_com_clipes(db)
    _, r = pedir({"acao": "pegar"}, cab=ROBO)
    subir(r["envio_palavras"]["url"], b"{}", "application/json")
    pedir({"acao": "audio", "id": v, "tentativa": 1, "segundos": 20}, cab=ROBO)
    pedir({"acao": "falhar", "id": v, "tentativa": 1, "codigo": "formato"}, cab=ROBO)
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_video_ajustar(%s, %s, null)", (v, json.dumps({"estilo": "compacta"}))).fetchone()[0]["modo"] == "montagem"
    _, r = pedir({"acao": "pegar"}, cab=ROBO)
    assert (r["pedido"]["modo"], r["pedido"]["tentativa"], r["envio_palavras"]) == ("montagem", 2, None)
    assert r["links"]["palavras"].split("?")[0] == f"{PONTE}/storage/v1/object/sign/radar-videos/trabalho/{v}/1/palavras.json"
    status, ln = pedir({"acao": "links", "id": v, "tentativa": 2, "ler": [f"trabalho/{v}/1/palavras.json"]}, cab=ROBO)
    assert status == 200 and list(ln["ler"]) == [f"trabalho/{v}/1/palavras.json"]
    # sem o palavras.json desta rodada, o áudio só conta os segundos (a transcrição guardada continua a 1)
    assert pedir({"acao": "audio", "id": v, "tentativa": 2, "segundos": 0}, cab=ROBO) == (200, {"palavras_guardadas": False, "restante_s": 1780})
    assert video(db, v, "palavras_tentativa") == 1


def test_baixar_so_o_aprovado_com_300_s_e_o_nome_do_reel(vid):
    db = vid
    pid, ana, v = na_fila_com_clipes(db)
    db.execute("update radar_videos set situacao = 'pronto', sha256 = %s, bytes = 4000, duracao_final = 38, relatorio = %s where id = %s",
               (SHA_VIDEO, json.dumps(RELATORIO), v))
    guardar(f"corrigido/{v}/{SHA_VIDEO}.mp4", 4000)
    lido = lambda: db.execute("select atualizado_em from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0].isoformat()
    assert pedir({"acao": "baixar", "peca": pid, "lido": lido()}) == (409, {"message": "Só a peça aprovada para publicar à mão pode ser copiada ou baixada."})
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    status, r = pedir({"acao": "baixar", "peca": pid, "lido": lido()})
    data = str(hoje(db) + __import__("datetime").timedelta(days=5))
    assert status == 200 and r["expira_s"] == 300 and r["url"].endswith(f"&download=reel-{data}.mp4")
    assert ARM["assinaturas"][-1] == (f"corrigido/{v}/{SHA_VIDEO}.mp4", 300)
    assert db.execute("select acao from radar_video_acessos").fetchall() == [("baixar",)]


# ------------------------------------------------------------------ agenda, limpeza e diagnóstico
def test_limpeza_apaga_pela_api_so_o_que_o_banco_manda_e_deixa_a_versao_atual(vid):
    db = vid
    pid, ana, velho = na_fila_com_clipes(db)
    guardar(f"trabalho/{velho}/1/palavras.json", 20, "application/json")
    db.execute("update radar_videos set situacao = 'pronto', sha256 = %s, bytes = 4000, duracao_final = 38 where id = %s", (SHA_VIDEO, velho))
    guardar(f"corrigido/{velho}/{SHA_VIDEO}.mp4", 4000)
    guardar(f"quadros/{velho}/{SHA_VIDEO}/q1.jpg", 3, "image/jpeg")
    # o envio novo (substitui o velho), já pronto duas vezes: o sha256 antigo (SHA_VIDEO) e o atual (SHA2)
    v = na_fila(db, pid, ana)
    db.execute("update radar_videos set situacao = 'pronto', sha256 = %s, bytes = 4000, duracao_final = 38, antigos = true where id = %s", (SHA2, v))
    for n in (1, 2):
        guardar(f"bruto/{v}/{n}")
    for sha in (SHA_VIDEO, SHA2):
        guardar(f"corrigido/{v}/{sha}.mp4", 4000)
        for k in (1, 2):
            guardar(f"quadros/{v}/{sha}/q{k}.jpg", 3, "image/jpeg")
    status, r = pedir({"acao": "limpar"}, cab=AGENDA)
    assert status == 200 and r == {"videos": 2, "arquivos": 8, "textos": 0, "falhas": 0, "adiados": 0}
    assert sorted(ARM["objetos"]) == sorted([f"bruto/{v}/1", f"bruto/{v}/2", f"corrigido/{v}/{SHA2}.mp4", f"quadros/{v}/{SHA2}/q1.jpg",
                                              f"quadros/{v}/{SHA2}/q2.jpg"])
    assert video(db, velho, "arquivos_apagados") == ["bruto", "corrigido", "trabalho"] and video(db, v, "antigos, arquivos_apagados") == (False, [])
    assert pedir({"acao": "limpar"}, cab=AGENDA) == (200, {"videos": 0, "arquivos": 0, "textos": 0, "falhas": 0, "adiados": 0})
    linha = [l for l in LOGS[PORTA_FUNCAO].read_text().splitlines() if "limpeza →" in l]
    assert linha and linha[0] == "radar-video: limpeza → 2 vídeo(s), 8 arquivo(s), 0 texto(s)"


def test_diagnostico_devolve_o_bucket_publico_a_privado_e_mostra_a_fila_sem_os_segredos(vid):
    db = vid
    ARM["buckets"]["radar-videos"] = {"id": "radar-videos", "name": "radar-videos", "public": True}
    status, r = pedir({"acao": "diagnostico"}, uid=ADMIN)
    assert status == 200 and r["versao"] == "0.33.0"
    itens = {i["item"]: i for i in r["itens"]}
    assert itens["Armazenamento dos vídeos"] == {"item": "Armazenamento dos vídeos", "ok": True,
                                                 "detalhe": 'bucket privado "radar-videos" (estava público: voltou a privado)'}
    assert ARM["atualizados"] == [{"public": False}]                                           # só o "public" (o limite fica o do projeto)
    assert ARM["buckets"]["radar-videos"]["public"] is False
    assert itens["Workflow do robô"]["ok"] is True and "radar-video.yml" in itens["Workflow do robô"]["detalhe"]
    assert itens["Fila do corretor"]["detalhe"] == "0 na fila, 0 com o robô" and r["tudo_certo"] is True
    assert TOKEN_GITHUB not in json.dumps(r)
    status, r = pedir({"acao": "diagnostico"}, uid=ADMIN, porta=PORTA_SEM_TOKEN)
    itens = {i["item"]: i for i in r["itens"]}
    assert r["tudo_certo"] is False and itens["Token do GitHub"]["ok"] is False and "Workflow do robô" not in itens
    assert itens["Armazenamento dos vídeos"]["detalhe"] == 'bucket privado "radar-videos"'      # a chave nova (sb_secret_) no apikey


def test_acionar_so_com_fila_com_pausa_e_sem_mostrar_o_token(vid):
    db = vid
    assert pedir({"acao": "acionar"}, porta=PORTA_ACIONAR) == (200, {"acionado": False, "motivo": "nada_na_fila",
                                                                     "mensagem": "Não há vídeo na fila: o robô não foi acionado."})
    pid, ana, v = na_fila_com_clipes(db)
    ARM["github_status"] = 401                                                        # o GitHub recusa o token: o próximo pedido tenta de novo
    status, r = pedir({"acao": "acionar"}, cab=AGENDA, porta=PORTA_ACIONAR)
    assert (status, r["acionado"], r["motivo"]) == (200, False, "token_recusado") and TOKEN_GITHUB not in json.dumps(r)
    ARM["github_status"] = 204
    status, r = pedir({"acao": "acionar"}, cab=AGENDA, porta=PORTA_ACIONAR)
    assert status == 200 and r["acionado"] is True and len(ARM["github"]) == 2
    status, r = pedir({"acao": "acionar"}, porta=PORTA_ACIONAR)
    assert r["acionado"] is True and r["mensagem"] == "O robô já foi acionado há instantes." and len(ARM["github"]) == 2   # pausa de 30 s
    status, r = pedir({"acao": "acionar"}, porta=PORTA_SEM_TOKEN)
    assert r["motivo"] == "sem_token" and "RADAR_VIDEO_GITHUB_TOKEN" in r["mensagem"]


def test_robo_que_termina_aciona_de_novo_se_ainda_ha_fila(vid):
    """O robô trata um pedido por execução. O 2º envio, que chegou enquanto ele trabalhava (a tela recebeu "o robô já foi acionado há
    instantes"), não espera a reserva da agenda: ao concluir ou falhar, a função aciona o robô de novo se ainda há pedido na fila — sem
    a pausa de 30 s, que é para dois cliques no mesmo envio. Sem fila, nada."""
    db = vid
    pid, ana, v1 = na_fila_com_clipes(db)
    assert pedir({"acao": "pegar"}, cab=ROBO)[1]["pedido"]["id"] == v1
    pedir({"acao": "acionar"})                                                         # o 2º envio: "já acionado há instantes"
    v2 = na_fila(db, reel(db, dias=6, pessoa=ana)[0], ana)
    for p in PARTES:
        guardar(f"bruto/{v2}/{p['n']}", p["bytes"], p["tipo"])
    despachos = lambda: [g for g in ARM["github"] if g[0] == "POST" and g[1].endswith("/dispatches")]
    antes = len(despachos())
    assert pedir({"acao": "falhar", "id": v1, "tentativa": 1, "codigo": "formato"}, cab=ROBO) == (200, {"situacao": "erro"})
    assert len(despachos()) == antes + 1
    # o 2º pedido termina (concluído): a fila ficou vazia, nada é acionado
    assert pedir({"acao": "pegar"}, cab=ROBO)[1]["pedido"]["id"] == v2
    guardar(f"corrigido/{v2}/{SHA_VIDEO}.mp4", 4000)
    for k in range(1, 5):
        guardar(f"quadros/{v2}/{SHA_VIDEO}/q{k}.jpg", 300, "image/jpeg")
    fim = {"acao": "concluir", "id": v2, "tentativa": 1, "situacao": "pronto", "relatorio": RELATORIO, "sha256": SHA_VIDEO, "bytes": 4000, "duracao": 38.4}
    assert pedir(fim, cab=ROBO) == (200, {"situacao": "pronto"}) and len(despachos()) == antes + 1
    # o concluir com outro pedido esperando aciona também
    v3 = na_fila(db, reel(db, dias=7, pessoa=ana)[0], ana)
    db.execute("update radar_videos set situacao = 'processando', rodada = 2, pego_em = now() where id = %s", (v2,))
    guardar(f"corrigido/{v2}/{SHA2}.mp4", 4000)
    for k in range(1, 5):
        guardar(f"quadros/{v2}/{SHA2}/q{k}.jpg", 300, "image/jpeg")
    assert pedir({**fim, "tentativa": 2, "sha256": SHA2}, cab=ROBO) == (200, {"situacao": "pronto"}) and len(despachos()) == antes + 2
    assert video(db, v3, "situacao") == "na_fila"


def test_registros_e_erros_sem_link_token_chave_nome_nem_fala(vid):
    db = vid
    pid, ana, v = na_fila_com_clipes(db)
    _, r = pedir({"acao": "pegar"}, cab=ROBO)
    pedir({"acao": "links", "id": v, "tentativa": 1, "ler": [f"bruto/{v}/1"]}, cab=ROBO)
    ARM["falha_assinar"] = True
    status, x = pedir({"acao": "links", "id": v, "tentativa": 1, "ler": [f"bruto/{v}/1"]}, cab=ROBO)
    assert status == 502 and "Object not found" not in x["message"] and "bruto/" not in x["message"]
    pedir({"acao": "previa", "id": v})
    pedir({"acao": "pegar"}, cab={**ANON, "x-radar-video-robo": "z" * 64})
    pedir({"acao": "falhar", "id": v, "tentativa": 1, "codigo": "storage"}, cab=ROBO)
    texto = "\n".join(l for p in LOGS.values() for l in p.read_text().splitlines() if not l.startswith("Listening on "))
    assert "radar-video: pegar " + v + " → ok (robo)" in texto
    for proibido in ("token=", "assinado.", "envio.", "http", CHAVE_ROBO, CHAVE_AGENDA, "z" * 64, TOKEN_GITHUB, "Ana", FALA[:20], IDENT[:20],
                     "eyJ", "sb_secret_"):
        assert proibido not in texto, proibido
    assert all(re.fullmatch(r"radar-video: [^:]*", l) for l in texto.splitlines()), texto            # só as linhas fixas da função


# ------------------------------------------------------------------ v0.33.0: a capa escolhida na aba Vídeo
# A capa sobe com o sha256 DELA no nome (quadros/<id>/<sha256 do vídeo>/capa-<sha256 da capa>.jpg): trocar só a capa monta o mesmo vídeo
# (o mesmo sha256), e o armazenamento nunca sobrescreve — com um nome fixo, a capa de antes ficaria no lugar da nova.
CAPA_SHA, CAPA_SHA2 = "c" * 64, "d" * 64
CAPA_REL = {"q": 30, "em_ms": 1000, "movida": False, "sha256": CAPA_SHA}


def test_robo_grava_a_capa_so_do_seu_sha256_e_o_concluir_confere(vid):
    """O robô ganha o token de envio da capa (quadros/<id>/<sha256>/capa-<sha256 da capa>.jpg, ao lado dos quadros) só do pedido que
    está com ele; com a capa no relatório, o concluir confere que ELA (pelo sha256 do nome) está no armazenamento: a capa de antes do
    mesmo vídeo não passa pela nova."""
    db = vid
    pid, ana, v = na_fila_com_clipes(db)
    _, r = pedir({"acao": "pegar"}, cab=ROBO)
    t = r["pedido"]["tentativa"]
    outro = str(uuidlib.uuid4())
    for k in (f"quadros/{v}/{SHA_VIDEO}/capa.png", f"quadros/{v}/{SHA_VIDEO}/capa2.jpg", f"quadros/{outro}/{SHA_VIDEO}/capa-{CAPA_SHA}.jpg",
              f"quadros/{v}/{'A' * 64}/capa-{CAPA_SHA}.jpg", f"quadros/{v}/capa-{CAPA_SHA}.jpg", f"quadros/{v}/{SHA_VIDEO}/capa.jpg",
              f"quadros/{v}/{SHA_VIDEO}/capa-{'C' * 64}.jpg", f"quadros/{v}/{SHA_VIDEO}/capa-{CAPA_SHA[:63]}.jpg"):
        assert pedir({"acao": "links", "id": v, "tentativa": t, "gravar": [k]}, cab=ROBO) == (403, {"message": "1 caminho(s) fora do pedido."}), k
    capa_velha = f"quadros/{v}/{SHA_VIDEO}/capa-{CAPA_SHA2}.jpg"
    caminhos = [f"corrigido/{v}/{SHA_VIDEO}.mp4"] + [f"quadros/{v}/{SHA_VIDEO}/q{k}.jpg" for k in range(1, 5)] + [f"quadros/{v}/{SHA_VIDEO}/capa-{CAPA_SHA}.jpg"]
    status, ln = pedir({"acao": "links", "id": v, "tentativa": t, "gravar": caminhos}, cab=ROBO)
    assert status == 200 and set(ln["gravar"]) == set(caminhos)                              # o vídeo, os 4 quadros e a capa: 6
    assert subir(ln["gravar"][caminhos[0]]["url"], b"m" * 4000, "video/mp4") == 200
    for k in range(1, 5):
        assert subir(ln["gravar"][caminhos[k]]["url"], b"j" * 300, "image/jpeg") == 200
    guardar(capa_velha, 500, "image/jpeg")                                                      # a capa de outra montagem do mesmo vídeo
    fim = {"acao": "concluir", "id": v, "tentativa": t, "situacao": "pronto", "relatorio": {**RELATORIO, "capa": CAPA_REL},
           "sha256": SHA_VIDEO, "bytes": 4000, "duracao": 38.4}
    assert pedir(fim, cab=ROBO) == (409, {"message": "Falta a capa no armazenamento: suba de novo."})
    for ruim in ({k: x for k, x in CAPA_REL.items() if k != "sha256"}, {**CAPA_REL, "sha256": "C" * 64}, {**CAPA_REL, "sha256": "../q1"}):
        assert pedir({**fim, "relatorio": {**RELATORIO, "capa": ruim}}, cab=ROBO) == (400, {"message": "Informe o sha256 da capa."})
    assert subir(ln["gravar"][caminhos[5]]["url"], b"c" * 500, "image/jpeg") == 200
    assert pedir(fim, cab=ROBO) == (200, {"situacao": "pronto"})
    assert video(db, v, "relatorio")["capa"] == CAPA_REL


def test_previa_e_baixar_devolvem_o_link_da_capa(vid):
    """A prévia (600 s) e o baixar do vídeo aprovado (300 s, reel-<data>-capa.jpg) devolvem o link da capa do mesmo sha256 (a do
    relatório, pelo sha256 dela); sem a capa, null; o caminho fora do esperado que o banco devolvesse dá 502 (nunca um link de outro
    arquivo)."""
    db = vid
    pid, ana, v = na_fila_com_clipes(db)
    db.execute("update radar_videos set situacao = 'pronto', sha256 = %s, bytes = 4000, duracao_final = 38, relatorio = %s where id = %s",
               (SHA_VIDEO, json.dumps(RELATORIO), v))
    guardar(f"corrigido/{v}/{SHA_VIDEO}.mp4", 4000)
    for k in range(1, 5):
        guardar(f"quadros/{v}/{SHA_VIDEO}/q{k}.jpg", 300, "image/jpeg")
    status, p = pedir({"acao": "previa", "id": v})
    assert status == 200 and p["capa"] is None
    capa = f"quadros/{v}/{SHA_VIDEO}/capa-{CAPA_SHA}.jpg"
    db.execute("update radar_videos set relatorio = relatorio || %s where id = %s", (json.dumps({"capa": CAPA_REL}), v))
    guardar(capa, 500, "image/jpeg")
    guardar(f"quadros/{v}/{SHA_VIDEO}/capa-{CAPA_SHA2}.jpg", 500, "image/jpeg")               # a de outra montagem do mesmo vídeo: não
    ARM["assinaturas"].clear()
    status, p = pedir({"acao": "previa", "id": v})
    assert status == 200 and p["capa"].split("?")[0] == f"{PONTE}/storage/v1/object/sign/radar-videos/{capa}"
    assert (capa, 600) in ARM["assinaturas"] and len(ARM["assinaturas"]) == 6
    marcar_pronta(db, pid)
    aprovar_peca(db, pid, modo="manual", artes=[], conferencias=("pessoas", "video"), video=SHA_VIDEO)
    lido = db.execute("select atualizado_em from radar_pauta_pecas where id = %s", (pid,)).fetchone()[0].isoformat()
    status, r = pedir({"acao": "baixar", "peca": pid, "lido": lido})
    data = str(hoje(db) + __import__("datetime").timedelta(days=5))
    assert status == 200 and r["url"].endswith(f"&download=reel-{data}.mp4") and r["capa_url"].endswith(f"&download=reel-{data}-capa.jpg")
    assert ARM["assinaturas"][-1] == (capa, 300)
    # o banco que devolvesse a capa de outro caminho (de outro vídeo, ou o nome fixo de antes): a função recusa
    db.execute("alter function radar_video_para_previa(uuid) rename to radar_video_para_previa_ok")
    try:
        for ruim in ("'quadros/' || gen_random_uuid() || '/' || repeat('a', 64) || '/capa-' || repeat('c', 64) || '.jpg'",
                     f"'quadros/{v}/{SHA_VIDEO}/capa.jpg'", f"'quadros/{v}/{SHA_VIDEO}/capa-../q1.jpg'"):
            db.execute(f"""create or replace function radar_video_para_previa(p_id uuid) returns jsonb language sql security definer set search_path = public as $$
                            select radar_video_para_previa_ok(p_id) || jsonb_build_object('capa', {ruim}) $$""")
            db.execute("grant execute on function radar_video_para_previa(uuid) to authenticated")
            assert pedir({"acao": "previa", "id": v}) == (502, {"message": "O banco devolveu um caminho fora do esperado."}), ruim
    finally:
        db.execute("drop function if exists radar_video_para_previa(uuid)")
        db.execute("alter function radar_video_para_previa_ok(uuid) rename to radar_video_para_previa")
    texto = "\n".join(l for p in LOGS.values() for l in p.read_text().splitlines())
    assert "capa-" not in texto and "capa.jpg" not in texto and "token=" not in texto
