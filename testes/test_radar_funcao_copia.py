"""Função radar-copia (v0.32.0) rodando de verdade no Deno, com o banco real (PostgREST) e um Microsoft Graph de mentira (o login, a
pasta do OneDrive, o envio direto e a sessão de envio em pedaços). Sem o Deno instalado, o arquivo é pulado.

Confere: sem os segredos, "não configurada" sem erro, sem registro e sem falar com a Microsoft; quem pode chamar (o administrador, ou a
agenda com a chave do Vault; a chave dos robôs sozinha não); o .zip conferido pelo Python (testzip, as 30 tabelas, as linhas e o sha256
de cada arquivo iguais ao banco, as imagens sem compactar); até 4 MiB um PUT só; acima, a sessão de envio em pedaços de 327 680 bytes,
sem o Authorization; 5xx repetido e a desistência; a sessão vencida (404); o endereço de envio de fora do OneDrive recusado sem mandar
nada; o tamanho diferente (o arquivo é apagado); o "Testar" (o 403 esperado na raiz do OneDrive, a permissão a mais, o consentimento
que falta, o login recusado); a cópia em andamento; o limite de tamanho; o segredo colado no banco sai mascarado; e nada vai para o log
nem para o armazenamento. Nomes de mentira ("Ana Teste", "Bruno Exemplo") e domínio .test.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import zipfile
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
import requests

from conftest import ADMIN, API, EDITOR, LEITOR, RAIZ, SECRETA, VAULT_SIMULADO, conectar, gateway, jwt
from test_radar_banco import TEXTO_OFICIAL, nova_captura

PORTA_PONTE, PORTA_A, PORTA_B, PORTA_C, PORTA_D = 3974, 3973, 3972, 3971, 3970
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
FUNCAO = RAIZ / "supabase" / "functions" / "radar-copia" / "index.ts"
DRIVE, PASTA, CLIENTE = "b!driveTeste0123456789abcdef", "PASTATESTE01", "8b3c1d2e-1111-4a2b-9c3d-0123456789ab"
ROLE = "Files.SelectedOperations.Selected"
CHAVE_AGENDA = "b" * 64
TABELAS = sorted(re.findall(r'"(radar_[a-z0-9_]+)"', re.search(r"(?m)^const TABELAS = \[(.*?)\] as const;",
                                                              FUNCAO.read_text(encoding="utf-8"), re.S).group(1)))
ESTADO: dict = {}
STORAGE: list = []                                    # todo pedido ao armazenamento, em todos os testes (tem de ficar vazio)


def novo_estado():
    ESTADO.clear()
    ESTADO.update(pedidos=[], arquivos={}, roles=[ROLE], segredo_ok=True, raiz=403, size_errado=False, upload_url=None,
                  falhar_em={}, sessoes={}, n_sessoes=0, tokens=set(), apagados=[])


novo_estado()


def token_falso(roles):
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return b({"typ": "JWT", "alg": "none"}) + "." + b({"aud": "https://graph.microsoft.com", "roles": roles}) + ".assinatura"


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST (com o gateway do Supabase); /login → o token do aplicativo; /graph → o OneDrive (a pasta liberada);
    /sessao → a sessão de envio (sem token); /storage → registrado (não pode haver nenhum)."""
    def _responder(self, status, corpo=b"", extras=None):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
        extras = {k.title(): v for k, v in (extras or {}).items()}
        self.send_response(status)
        self.send_header("Content-Type", extras.pop("Content-Type", "application/json"))
        self.send_header("Content-Length", str(len(dados)))
        for k, v in extras.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)

    def _corpo(self) -> bytes:
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            partes = []
            while True:
                n = int(self.rfile.readline().strip().split(b";")[0], 16)
                if not n:
                    self.rfile.readline()
                    break
                partes.append(self.rfile.read(n))
                self.rfile.readline()
            return b"".join(partes)
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def _anotar(self, corpo, **extra):
        u = urlsplit(self.path)
        ESTADO["pedidos"].append({"metodo": self.command, "caminho": unquote(u.path), "query": unquote(u.query),
                                  "auth": self.headers.get("Authorization"), "tipo": self.headers.get("Content-Type"),
                                  "faixa": self.headers.get("Content-Range"), "content_length": self.headers.get("Content-Length"),
                                  "tamanho": len(corpo), **extra})

    def _tratar(self):
        corpo = self._corpo()
        u = urlsplit(self.path)
        caminho = unquote(u.path)
        if caminho.startswith("/storage/"):
            STORAGE.append((self.command, caminho))
            return self._responder(404, {"message": "não"})
        if caminho.startswith("/rest/v1/"):
            apikey, auth = self.headers.get("apikey") or "", self.headers.get("Authorization") or ""
            self._anotar(b"", apikey=apikey[:10], auth_rest=auth.removeprefix("Bearer ")[:10], corpo_rest=corpo[:300].decode(errors="replace"))
            auth = gateway(self.headers)
            if auth is None:
                return self._responder(401, {"message": "Invalid Compact JWS"})
            cab = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "prefer", "accept-encoding")} | (
                {"Authorization": auth} if auth else {})
            r = requests.request(self.command, API + self.path.removeprefix("/rest/v1"), headers=cab, data=corpo or None, timeout=60)
            extras = {k: v for k, v in r.headers.items() if k.lower() in ("content-range", "content-type")}
            return self._responder(r.status_code, r.content, extras)
        self._anotar(corpo)
        if caminho.startswith("/login/"):
            dados = parse_qs(corpo.decode())
            if not ESTADO["segredo_ok"] or dados.get("client_secret") != ["segredo-de-teste"] or dados.get("client_id") != [CLIENTE] \
                    or dados.get("grant_type") != ["client_credentials"] or dados.get("scope") != ["https://graph.microsoft.com/.default"] \
                    or caminho != "/login/tenant-teste/oauth2/v2.0/token":
                return self._responder(401, {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret provided."})
            t = token_falso(ESTADO["roles"])
            ESTADO["tokens"].add(t)
            return self._responder(200, {"access_token": t, "token_type": "Bearer", "expires_in": 3599})
        if caminho.startswith("/sessao/"):
            return self._sessao(caminho, corpo)
        if not caminho.startswith("/graph/"):
            return self._responder(404, {})
        if (self.headers.get("Authorization") or "").removeprefix("Bearer ") not in ESTADO["tokens"]:
            return self._responder(401, {"error": {"code": "InvalidAuthenticationToken"}})
        q = parse_qs(u.query)
        m = re.fullmatch(r"/graph/drives/([^/]+)/(root|items/([^/:]+))(?::/([^/:]+):?(?:/(content|createUploadSession))?)?", caminho)
        if not m or m.group(1) != DRIVE:
            return self._responder(404, {"error": {"code": "itemNotFound"}})
        if m.group(2) == "root":
            return self._responder(ESTADO["raiz"], {"id": "raiz"} if ESTADO["raiz"] == 200 else {"error": {"code": "accessDenied"}})
        item, nome, acao = m.group(3), m.group(4), m.group(5)
        if self.command == "DELETE" and not nome:
            ESTADO["apagados"].append(item)
            ESTADO["arquivos"] = {k: v for k, v in ESTADO["arquivos"].items() if v["id"] != item}
            return self._responder(204, b"")
        if item != PASTA:
            return self._responder(404, {"error": {"code": "itemNotFound"}})
        if self.command == "GET" and not nome:
            return self._responder(200, {"id": PASTA, "name": "Cópias de segurança", "folder": {"childCount": len(ESTADO["arquivos"])}})
        if self.command == "GET" and not acao:                                    # o arquivo da pasta, pelo nome
            a = ESTADO["arquivos"].get(nome)
            if a is None:
                return self._responder(404, {"error": {"code": "itemNotFound"}})
            return self._responder(200, {"id": a["id"], "name": nome, "size": len(a["dados"]) + (1 if ESTADO["size_errado"] else 0)})
        if acao == "content" and self.command == "PUT":
            if q.get("@microsoft.graph.conflictBehavior") == ["fail"] and nome in ESTADO["arquivos"]:
                return self._responder(409, {"error": {"code": "nameAlreadyExists"}})
            return self._responder(201, self._guardar(nome, corpo))
        if acao == "createUploadSession" and self.command == "POST":
            pedido = json.loads(corpo or b"{}")
            ESTADO["pedidos"][-1]["corpo"] = pedido
            if pedido.get("item", {}).get("@microsoft.graph.conflictBehavior") == "fail" and nome in ESTADO["arquivos"]:
                return self._responder(409, {"error": {"code": "nameAlreadyExists"}})
            ESTADO["n_sessoes"] += 1
            n = ESTADO["n_sessoes"]
            ESTADO["sessoes"][n] = {"nome": nome, "dados": bytearray(), "erros": []}
            return self._responder(200, {"uploadUrl": ESTADO["upload_url"] or f"{PONTE}/sessao/{n}", "expirationDateTime": "2026-11-01T10:00:00Z"})
        return self._responder(400, {"error": {"code": "invalidRequest"}})

    def _guardar(self, nome, dados):
        ident = f"ITEM{len(ESTADO['arquivos']) + len(ESTADO['apagados']) + 1}"
        ESTADO["arquivos"][nome] = {"id": ident, "dados": bytes(dados)}
        return {"id": ident, "name": nome, "size": len(dados) + (1 if ESTADO["size_errado"] else 0)}

    def _sessao(self, caminho, corpo):
        n = int(caminho.rsplit("/", 1)[1])
        s = ESTADO["sessoes"].get(n)
        if s is None:
            return self._responder(404, {"error": {"code": "itemNotFound"}})
        if self.command == "DELETE":
            s["cancelada"] = True
            return self._responder(204, b"")
        if s.get("concluida"):                                                    # a sessão que já gravou o arquivo não existe mais
            return self._responder(404, {"error": {"code": "itemNotFound"}})
        if self.command == "GET":
            return self._responder(200, {"nextExpectedRanges": [f"{len(s['dados'])}-"]})
        m = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", self.headers.get("Content-Range") or "")
        if not m:
            s["erros"].append("sem Content-Range")
            return self._responder(400, {"error": {"code": "invalidRange"}})
        de, ate, total = map(int, m.groups())
        falhas = ESTADO["falhar_em"].get(de) or []
        if falhas:
            status = falhas.pop(0)
            if status == 404:
                del ESTADO["sessoes"][n]
            return self._responder(status, {"error": {"code": "serviceNotAvailable" if status >= 500 else "itemNotFound"}})
        if self.headers.get("Authorization"):
            s["erros"].append("Authorization na sessão")
        if de != len(s["dados"]) or ate - de + 1 != len(corpo) or (ate + 1 < total and len(corpo) % 327_680):
            s["erros"].append(f"pedaço errado {de}-{ate}/{total} ({len(corpo)})")
            return self._responder(416, {"error": {"code": "invalidRange"}})
        s["dados"] += corpo
        if ate + 1 < total:
            return self._responder(202, {"expirationDateTime": "2026-11-01T10:00:00Z", "nextExpectedRanges": [f"{ate + 1}-"]})
        s["concluida"] = True
        return self._responder(201, self._guardar(s["nome"], s["dados"]))

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _tratar

    def log_message(self, *a):
        pass


def _subir(porta, pasta, nome, **extra):
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), SUPABASE_SERVICE_ROLE_KEY=SECRETA,
                    SUPABASE_SECRET_KEYS=json.dumps({"default": SECRETA}), GRAPH_LOGIN_URL=PONTE + "/login", GRAPH_URL=PONTE + "/graph",
                    GRAPH_TENANT_ID="tenant-teste", COPIA_CLIENT_ID=CLIENTE, COPIA_CLIENT_SECRET="segredo-de-teste", COPIA_DRIVE_ID=DRIVE,
                    COPIA_PASTA_ID=PASTA, RADAR_PORTA_LOCAL=str(porta), NO_COLOR="1")
    for k in ("COPIA_PUT_MAX", "COPIA_PEDACO", "COPIA_PAGINA", "COPIA_COMPACTAR_MS", "COPIA_MAX_MB"):
        ambiente.pop(k, None)
    for k, v in extra.items():
        if v is None:
            ambiente.pop(k, None)
        else:
            ambiente[k] = v
    log = open(pasta / f"{nome}.log", "w")
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt", str(FUNCAO)], env=ambiente, stdout=log, stderr=log)
    for _ in range(150):
        try:
            requests.options(f"http://127.0.0.1:{porta}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.2)
    return proc, log


@pytest.fixture(scope="module")
def funcao(api_postgrest, tmp_path_factory):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    pasta = tmp_path_factory.mktemp("copia")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    procs = [_subir(PORTA_A, pasta, "a"),
             _subir(PORTA_B, pasta, "b", COPIA_PUT_MAX="0", COPIA_PEDACO="327680", COPIA_PAGINA="2", COPIA_COMPACTAR_MS="0"),
             _subir(PORTA_C, pasta, "c", COPIA_CLIENT_ID=None, COPIA_CLIENT_SECRET=None, COPIA_DRIVE_ID=None, COPIA_PASTA_ID=None),
             _subir(PORTA_D, pasta, "d", COPIA_MAX_MB="0.001")]
    yield pasta
    for proc, log in procs:
        proc.terminate()
        proc.wait(timeout=10)
        log.close()
    ponte.shutdown()
    ponte.server_close()


@pytest.fixture()
def copia(funcao, limpo):
    """O registro das cópias vazio, o Graph de mentira zerado e um banco com dados de mentira: uma pessoa ("Ana Teste"), uma captura
    que cita "Bruno Exemplo" e três imagens de ~400 KB (o .zip passa de 1 MB)."""
    novo_estado()
    limpo.execute("delete from radar_copias")
    limpo.execute("delete from radar_vencimentos")
    limpo.execute("insert into radar_pessoas (nome, nome_na_peca, area) values ('Ana Teste', 'Ana', 'Fiscal')")
    nova_captura(limpo, url="https://exemplo.test/bruno-exemplo", texto=TEXTO_OFICIAL + " Bruno Exemplo comenta a norma.")
    for k in range(3):
        dados = "data:image/jpeg;base64," + base64.b64encode(os.urandom(299_000) + bytes([k])).decode()
        limpo.execute("insert into radar_imagens (dados, largura, altura) values (%s, 1200, 800)", (dados,))
    limpo.execute("insert into radar_vencimentos (nome, vence_em) values ('Domínio de teste', '2027-01-10')")
    yield limpo
    limpo.execute("delete from radar_copias")
    limpo.execute("delete from radar_vencimentos")
    limpo.execute("delete from radar_config where chave = 'teste_copia'")


@pytest.fixture()
def com_vault(copia):
    """O Vault de mentira, só durante o teste, com a chave da agenda da cópia."""
    copia.execute(VAULT_SIMULADO)
    copia.execute("select vault.create_secret(%s, 'radar_copia_agenda', 'teste')", (CHAVE_AGENDA,))
    yield copia
    copia.execute("drop schema vault cascade")


def pedir(corpo, uid=ADMIN, cab=None, porta=PORTA_A, tempo=170):
    cab = cab if cab is not None else {"Authorization": "Bearer " + jwt("authenticated", uid)}
    r = requests.post(f"http://127.0.0.1:{porta}/", json=corpo, headers=cab, timeout=tempo)
    return r.status_code, r.json(), r.content


def graph(metodo=None, trecho=""):
    return [p for p in ESTADO["pedidos"] if p["caminho"].startswith("/graph/") and (metodo is None or p["metodo"] == metodo)
            and trecho in p["caminho"]]


def sessao_pedidos():
    return [p for p in ESTADO["pedidos"] if p["caminho"].startswith("/sessao/")]


def registro(db):
    return db.execute("select ok, arquivo, bytes, bytes_brutos, linhas, tabelas, sha256, erro, origem from radar_copias order by id").fetchall()


def copiar(porta=PORTA_A):
    """A cópia pelo administrador (o OneDrive de mentira sem arquivo: duas cópias no mesmo minuto teriam o mesmo nome)."""
    ESTADO["arquivos"].clear()
    return pedir({"acao": "copiar"}, porta=porta)


def zip_de(nome):
    return zipfile.ZipFile(io.BytesIO(ESTADO["arquivos"][nome]["dados"]))


def conferir_zip(db, z, arquivo):
    """O .zip contra o banco: as entradas, as linhas e o sha256 de cada tabela, e o conteúdo de algumas."""
    assert z.testzip() is None
    assert z.namelist() == ["LEIA-ME.txt", "manifesto.json"] + [f"tabelas/{t}.json" for t in TABELAS]
    man = json.loads(z.read("manifesto.json"))
    assert (man["radar"], man["arquivo"], man["versao_funcao"], man["versao_banco"]) == ("Radar Artecon", arquivo, "0.32.0", "v0.32.0")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}-03:00", man["gerado_em"]) and len(man["nao_inclui"]) == 3
    assert [t["tabela"] for t in man["tabelas"]] == TABELAS
    for t in man["tabelas"]:
        dados = z.read(t["arquivo"])
        assert hashlib.sha256(dados).hexdigest() == t["sha256"] and len(dados) == t["bytes"], t["tabela"]
        linhas = json.loads(dados)
        assert len(linhas) == t["linhas"] == db.execute(f"select count(*) from {t['tabela']}").fetchone()[0], t["tabela"]
    assert man["linhas"] == sum(t["linhas"] for t in man["tabelas"]) and man["bytes_brutos"] == sum(t["bytes"] for t in man["tabelas"])
    assert json.loads(z.read("tabelas/radar_config.json")) == [r for (r,) in db.execute("select row_to_json(t) from radar_config t order by chave")]
    assert [p["nome"] for p in json.loads(z.read("tabelas/radar_pessoas.json"))] == ["Ana Teste"]
    assert "Bruno Exemplo" in z.read("tabelas/radar_capturas.json").decode()
    leia = z.read("LEIA-ME.txt").decode()
    assert "Cópia de segurança do Radar Artecon" in leia and arquivo in leia and "não compartilhe" in leia
    return man


# ------------------------------------------------------------------------------------------------------------- os testes
def test_sem_segredos_responde_nao_configurada_sem_erro(copia):
    status, r, _ = pedir({"acao": "situacao"}, porta=PORTA_C)
    assert status == 200 and r == {"versao": "0.32.0", "configurada": False, "invalidos": [],
                                   "faltam": ["COPIA_CLIENT_ID", "COPIA_CLIENT_SECRET", "COPIA_DRIVE_ID", "COPIA_PASTA_ID"]}
    status, r, _ = pedir({"acao": "copiar"}, porta=PORTA_C)
    assert status == 200 and r["ok"] is False and r["configurada"] is False
    assert r["mensagem"].startswith("Cópia não configurada: faltam COPIA_CLIENT_ID, COPIA_CLIENT_SECRET, COPIA_DRIVE_ID, COPIA_PASTA_ID")
    status, r, _ = pedir({"acao": "testar"}, porta=PORTA_C)
    assert status == 200 and r["tudo_certo"] is False and r["configurada"] is False
    assert [(i["item"], i["ok"]) for i in r["itens"]] == [("Função radar-copia instalada", True), ("Segredos da cópia", False)]
    assert registro(copia) == []
    assert [p for p in ESTADO["pedidos"] if not p["caminho"].startswith("/rest/v1/")] == []      # nem o login, nem o Graph


def test_quem_pode_chamar(com_vault):
    db = com_vault
    for uid in (EDITOR, LEITOR):
        assert pedir({"acao": "copiar"}, uid=uid)[0] == 403
        assert pedir({"acao": "testar"}, uid=uid)[0] == 403
    assert pedir({"acao": "copiar"}, cab={})[0] == 401
    status, r, _ = pedir({"acao": "copiar"}, cab={"x-radar-agenda": "a" * 64})
    assert status == 401 and r["message"] == "Chave da agenda não confere."
    # a conferência chega ao banco com a chave interna só no apikey
    assert [(p["caminho"], p["apikey"], p["auth_rest"]) for p in ESTADO["pedidos"] if p["caminho"].endswith("radar_copia_conferir_agenda")] == [
        ("/rest/v1/rpc/radar_copia_conferir_agenda", SECRETA[:10], "")]
    assert graph() == [] and registro(db) == []
    agenda = {"x-radar-agenda": CHAVE_AGENDA}
    for acao in ("testar", "situacao"):
        assert pedir({"acao": acao}, cab=agenda)[0] == 403
    assert pedir({"acao": "agenda_teste"})[0] == 403                                             # o teste da agenda é só da agenda
    assert pedir({"acao": "agenda_teste"}, cab=agenda)[1] == {"ok": True, "versao": "0.32.0"}
    assert pedir({"acao": "outra"})[0:2] == (400, {"message": "Ação desconhecida."})
    ESTADO["arquivos"].clear()
    status, r, bruto = pedir({"acao": "copiar"}, cab=agenda)
    assert status == 200 and r == {"ok": True, "versao": "0.32.0"} and len(bruto) < 100            # à agenda, só isto
    [(ok, arquivo, *_resto, origem)] = registro(db)
    assert ok is True and origem == "agenda" and arquivo in ESTADO["arquivos"]
    # a agenda fala com o banco pela chave interna (no apikey) e a chave da agenda (p_chave); nunca com o token de alguém
    rpcs = [p for p in ESTADO["pedidos"] if p["caminho"].startswith("/rest/v1/rpc/radar_copias_")]
    assert rpcs and all(p["apikey"] == SECRETA[:10] and p["auth_rest"] == "" and CHAVE_AGENDA in p["corpo_rest"] for p in rpcs)


def test_copia_pequena_por_put_e_o_zip_confere(copia):
    db = copia
    status, r, _ = copiar()
    assert status == 200 and r["ok"] is True, r
    assert set(r) == {"ok", "arquivo", "bytes", "bytes_brutos", "linhas", "tabelas", "mascarados", "tempos", "versao"}
    assert set(r["tempos"]) == {"exportar_ms", "compactar_ms", "enviar_ms"} and r["tabelas"] == 30 and r["mascarados"] == {}
    arquivo = r["arquivo"]
    assert re.fullmatch(r"radar-copia-\d{4}-\d{2}-\d{2}-\d{4}\.zip", arquivo)
    [put] = graph("PUT")
    assert put["caminho"] == f"/graph/drives/{DRIVE}/items/{PASTA}:/{arquivo}:/content"
    assert put["query"] == "@microsoft.graph.conflictBehavior=fail" and put["tipo"] == "application/zip"
    assert put["auth"].removeprefix("Bearer ") in ESTADO["tokens"] and sessao_pedidos() == []
    z = zip_de(arquivo)
    man = conferir_zip(db, z, arquivo)
    tipos = {i.filename: i.compress_type for i in z.infolist()}
    assert tipos.pop("tabelas/radar_imagens.json") == zipfile.ZIP_STORED and set(tipos.values()) == {zipfile.ZIP_DEFLATED}
    assert all(i.flag_bits & 0x800 for i in z.infolist())                                       # nomes em UTF-8
    dados = ESTADO["arquivos"][arquivo]["dados"]
    assert 1_000_000 < len(dados) <= 4 * 1024 * 1024
    assert registro(db) == [(True, arquivo, len(dados), man["bytes_brutos"], man["linhas"], 30,
                             hashlib.sha256(z.read("manifesto.json")).hexdigest(), None, "admin")]
    assert (r["bytes"], r["bytes_brutos"], r["linhas"]) == (len(dados), man["bytes_brutos"], man["linhas"])


def test_copia_grande_em_pedacos_sem_authorization_no_upload(copia):
    db = copia
    status, ra, _ = copiar()
    assert status == 200, ra
    za = zip_de(ra["arquivo"])
    db.execute("delete from radar_copias")
    novo_estado()
    status, r, _ = copiar(PORTA_B)
    assert status == 200 and r["ok"] is True, r
    [sessao] = graph("POST", "createUploadSession")
    assert sessao["corpo"] == {"item": {"@microsoft.graph.conflictBehavior": "fail"}} and sessao["auth"].removeprefix("Bearer ") in ESTADO["tokens"]
    assert sessao["caminho"] == f"/graph/drives/{DRIVE}/items/{PASTA}:/{r['arquivo']}:/createUploadSession"
    pedacos = sessao_pedidos()
    total = len(ESTADO["arquivos"][r["arquivo"]]["dados"])
    assert len(pedacos) >= 4 and all(p["auth"] is None for p in pedacos)                       # o endereço da sessão não leva o token
    assert [p["faixa"] for p in pedacos] == [f"bytes {k * 327_680}-{min((k + 1) * 327_680, total) - 1}/{total}" for k in range(len(pedacos))]
    assert all(p["tamanho"] == 327_680 for p in pedacos[:-1]) and pedacos[-1]["tamanho"] == total - 327_680 * (len(pedacos) - 1)
    assert all(p["content_length"] == str(p["tamanho"]) for p in pedacos)
    assert ESTADO["sessoes"][1]["erros"] == [] and graph("PUT") == []
    z = zip_de(r["arquivo"])
    conferir_zip(db, z, r["arquivo"])
    assert {i.filename for i in z.infolist() if i.filename.startswith("tabelas/") and i.compress_type != zipfile.ZIP_STORED} == set()
    # páginas de 2 linhas: muitas chamadas; o conteúdo de cada tabela igual ao da cópia feita de uma vez (fora o próprio registro; o
    # espaço entre as linhas muda com o tamanho da página, o JSON não)
    paginas = [p for p in ESTADO["pedidos"] if p["caminho"] == "/rest/v1/rpc/radar_copias_exportar"]
    assert len(paginas) > 30 + db.execute("select count(*) from radar_config").fetchone()[0] // 2
    for t in TABELAS:
        if t != "radar_copias":
            assert json.loads(z.read(f"tabelas/{t}.json")) == json.loads(za.read(f"tabelas/{t}.json")), t


def test_5xx_repetido_e_desistencia(copia):
    db = copia
    ESTADO["falhar_em"] = {327_680: [503, 503]}                                                # o 2º pedaço: 503 duas vezes, depois vai
    status, r, _ = copiar(PORTA_B)
    assert status == 200 and r["ok"] is True, r
    assert [p["faixa"].split("/")[0] for p in sessao_pedidos()].count(f"bytes 327680-{2 * 327_680 - 1}") == 3
    db.execute("delete from radar_copias")
    novo_estado()
    ESTADO["falhar_em"] = {327_680: [503] * 4}                                                 # quatro vezes: desiste
    status, r, _ = copiar(PORTA_B)
    assert status == 502 and "O OneDrive não aceitou (HTTP 503" in r["message"], r
    [(ok, *_resto, erro, _origem)] = registro(db)
    assert ok is False and "O OneDrive não aceitou (HTTP 503" in erro
    assert ESTADO["sessoes"][1].get("cancelada") is True and ESTADO["arquivos"] == {}           # a sessão foi cancelada
    db.execute("delete from radar_copias")
    novo_estado()
    ESTADO["falhar_em"] = {327_680: [404]}                                                     # a sessão venceu: uma nova, do começo
    status, r, _ = copiar(PORTA_B)
    assert status == 200 and r["ok"] is True, r
    assert len(graph("POST", "createUploadSession")) == 2 and ESTADO["sessoes"][2]["erros"] == []
    assert [p["faixa"].split("-")[0] for p in sessao_pedidos()].count("bytes 0") == 2
    conferir_zip(db, zip_de(r["arquivo"]), r["arquivo"])


def test_upload_url_fora_do_onedrive_e_recusado(copia):
    db = copia
    for url in ("https://exemplo.test/up", "http://127.0.0.2:1/up", "https://contoso.sharepoint.com.exemplo.test/up",
                "https://usuario:senha@contoso.sharepoint.com/up"):
        db.execute("delete from radar_copias")
        novo_estado()
        ESTADO["upload_url"] = url
        status, r, _ = copiar(PORTA_B)
        assert status == 502 and r["message"] == "Endereço de envio inesperado (não é do OneDrive): nada foi enviado.", (url, r)
        assert sessao_pedidos() == [] and graph("PUT") == [] and ESTADO["arquivos"] == {}
        assert [x[0] for x in registro(db)] == [False]


def test_tamanho_diferente_e_erro(copia):
    db = copia
    ESTADO["size_errado"] = True
    status, r, _ = copiar()
    assert status == 502 and "O arquivo no OneDrive ficou com tamanho diferente do enviado" in r["message"], r
    assert ESTADO["apagados"] == ["ITEM1"] and ESTADO["arquivos"] == {}
    assert graph("DELETE") and graph("DELETE")[0]["caminho"] == f"/graph/drives/{DRIVE}/items/ITEM1"
    [(ok, *_resto, erro, _origem)] = registro(db)
    assert ok is False and "tamanho diferente" in erro


def test_testar_passo_a_passo(copia):
    status, r, _ = pedir({"acao": "testar"})
    assert status == 200 and r["tudo_certo"] is True and r["configurada"] is True, r
    assert [i["item"] for i in r["itens"]] == ["Função radar-copia instalada", "Segredos da cópia", "Login na Microsoft (aplicativo das cópias)",
                                               "Permissão do aplicativo", "Pasta liberada", "O resto do OneDrive fica fora do alcance",
                                               "Gravar um arquivo pequeno", "Gravar em pedaços (arquivo grande)"]
    assert r["itens"][4]["detalhe"] == "“Cópias de segurança”" and "como esperado" in r["itens"][5]["detalhe"]
    [put] = graph("PUT")
    assert put["caminho"].endswith(":/radar-teste-conexao.txt:/content") and put["query"] == "@microsoft.graph.conflictBehavior=replace"
    assert ESTADO["arquivos"]["radar-teste-conexao.txt"]["dados"].startswith(b"Teste do Radar em ")
    [sessao] = graph("POST", "createUploadSession")
    assert sessao["corpo"] == {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    assert [p["tamanho"] for p in sessao_pedidos()] == [327_680, 81_920] and len(ESTADO["arquivos"]["radar-teste-pedacos.bin"]["dados"]) == 409_600
    assert registro(copia) == []                                                                # o teste não é uma cópia
    status, r, _ = pedir({"acao": "testar"})                                                    # de novo: os arquivos de teste são trocados
    assert r["tudo_certo"] is True
    novo_estado()
    ESTADO["roles"] = [ROLE, "Files.ReadWrite.All"]
    ESTADO["raiz"] = 200
    r = pedir({"acao": "testar"})[1]
    assert r["tudo_certo"] is False and [i["ok"] for i in r["itens"]] == [True, True, True, False, True, False, True, True]
    assert r["itens"][3]["detalhe"].startswith("permissão a mais: Files.ReadWrite.All")
    assert r["itens"][5]["detalhe"] == "o aplicativo enxerga o OneDrive inteiro: a permissão está larga demais"
    novo_estado()
    ESTADO["roles"] = []
    r = pedir({"acao": "testar"})[1]
    assert not r["itens"][3]["ok"] and "falta o consentimento do administrador" in r["itens"][3]["detalhe"]
    novo_estado()
    ESTADO["segredo_ok"] = False
    r = pedir({"acao": "testar"})[1]
    assert [i["ok"] for i in r["itens"]] == [True, True, False] and "invalid_client" in r["itens"][2]["detalhe"]
    assert "segredo-de-teste" not in json.dumps(r) and graph() == []
    assert pedir({"acao": "testar"}, uid=EDITOR)[0] == 403


def test_login_recusado_fica_registrado(copia):
    ESTADO["segredo_ok"] = False
    status, r, _ = copiar()
    assert status == 503 and "A Microsoft recusou o login do aplicativo das cópias (invalid_client)" in r["message"]
    assert "segredo-de-teste" not in r["message"] and graph() == []
    [(ok, *_resto, erro, _origem)] = registro(copia)
    assert ok is False and "invalid_client" in erro and "segredo-de-teste" not in erro


def test_em_andamento_recusa_a_segunda(copia):
    db = copia
    db.execute("""insert into radar_copias (mes, origem, iniciado_em, arquivo)
                  values (date_trunc('month', now() at time zone 'America/Sao_Paulo')::date, 'agenda', now() - interval '2 minutes',
                          'radar-copia-2026-10-01-0410.zip')""")
    status, r, _ = copiar()
    assert status == 409 and r["message"].startswith("já há uma cópia em andamento (começou às "), r
    assert graph() == [] and [p for p in ESTADO["pedidos"] if p["caminho"].startswith("/login/")] == []
    db.execute("update radar_copias set iniciado_em = now() - interval '20 minutes'")
    status, r, _ = copiar()
    assert status == 200 and r["ok"] is True
    assert [x[0] for x in registro(db)] == [False, True]


def test_limite_de_tamanho(copia):
    status, r, _ = copiar(PORTA_D)
    assert status == 413 and r["message"].startswith("O banco passou de 0.001 MB de dados") and "Nada foi enviado." in r["message"], r
    assert graph() == [] and ESTADO["arquivos"] == {}
    [(ok, *_resto, erro, _origem)] = registro(copia)
    assert ok is False and erro.startswith("O banco passou de")


def test_segredo_colado_no_banco_sai_mascarado(copia):
    """Cada formato de chave que o quadro de vencimentos recusa sai "[mascarado]" na cópia (v0.32.0, revisão: antes passavam o token
    da Meta, a chave privada e os prefixos curtos); o JSON continua válido (a chave privada com aspas e barras escapadas); o base64 não
    é tocado; o "pedaço de 40+ caracteres" do quadro não vale na cópia (pegaria o base64 e os sha256): o LEIA-ME diz isso."""
    db = copia
    colados = {"ghp": "ghp_" + "a" * 36, "pat": "github_pat_" + "11ABCDEFG0" * 3, "pat_curto": "github_pat_x", "sb": "sb_secret_abc",
               "sb_pub": "sb_publishable_" + "x1" * 10, "iagw": "iagw_k", "azure": "abc8Q~" + "Ab1.-~_x" * 5, "jwt": jwt("anon"),
               "meta": "EAA" + "B7c" * 14, "pem": '-----BEGIN PRIVATE KEY-----\nMIIEvQ"aspas"\\barra\n-----END PRIVATE KEY-----'}
    sem_fim = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc"                                      # sem o END: até o fim do texto
    fica = {"base64": "data:image/png;base64," + "QUFB" * 5 + "EAA" + "Zq9x" * 10 + "+/==", "longo": "z" * 45}   # EAA no meio do base64
    valor = {k: "token " + v + " fim" for k, v in colados.items()} | {"sem_fim": "token " + sem_fim + " fim"} | fica
    db.execute("insert into radar_config (chave, valor) values ('teste_copia', %s)", (json.dumps(valor),))
    status, r, _ = copiar()
    n = len(colados) + 1
    assert status == 200 and r["mascarados"] == {"radar_auditoria": n, "radar_config": n}, r     # a trilha guardou a inclusão
    z = zip_de(r["arquivo"])
    config = {c["chave"]: c["valor"] for c in json.loads(z.read("tabelas/radar_config.json"))}   # o JSON continua válido
    assert config["teste_copia"] == {k: "token [mascarado] fim" for k in colados} | {"sem_fim": "token [mascarado]"} | fica
    for t in TABELAS:
        texto = z.read(f"tabelas/{t}.json").decode()
        json.loads(texto)
        for v in list(colados.values()) + [sem_fim]:
            assert json.dumps(v)[1:-1][:40] not in texto, (t, v[:20])
    assert json.loads(z.read("manifesto.json"))["mascarados"] == {"radar_auditoria": n, "radar_config": n}
    assert db.execute("select valor->>'meta' from radar_config where chave = 'teste_copia'").fetchone()[0] == "token " + colados["meta"] + " fim"
    # o base64 das imagens nunca é mascarado
    assert json.loads(z.read("tabelas/radar_imagens.json"))[0]["dados"].startswith("data:image/jpeg;base64,")
    assert "Chave com formato conhecido (Supabase, GitHub, IA Central, Meta, segredo de aplicativo do Azure, JWT," in z.read("LEIA-ME.txt").decode()


def test_apagar_no_meio_da_copia_nao_tira_outra_linha_do_zip(copia, monkeypatch):
    """v0.32.0 (revisão): a imagem apagada no meio da cópia (uma capa trocada, entre duas páginas) não faz a seguinte pular a fronteira
    da página: toda linha que existe do começo ao fim da cópia está no .zip (páginas de 2 linhas, na porta B). Com OFFSET, a imagem 3
    ficava fora e o manifesto não acusava nada."""
    db = copia
    for k in range(4):
        db.execute("insert into radar_imagens (dados, largura, altura) values (%s, 1, 1)", ("data:image/png;base64," + "QkJC" * 12 + f"Qk{k}A",))
    todos = [i for (i,) in db.execute("select id from radar_imagens order by id")]
    original = requests.request
    feito, vistas = [], []

    def request(metodo, url, **kw):
        corpo = kw.get("data") or b""
        if b'"p_tabela":"radar_imagens"' in corpo:
            vistas.append(1)
            if len(vistas) == 2:                                                   # antes da 2ª página das imagens
                with conectar() as c:
                    c.execute("delete from radar_imagens where id = %s", (todos[0],))
                feito.append(1)
        return original(metodo, url, **kw)

    monkeypatch.setattr(requests, "request", request)
    status, r, _ = copiar(PORTA_B)
    assert status == 200 and r["ok"] is True, r
    assert feito
    z = zip_de(r["arquivo"])
    na_copia = [x["id"] for x in json.loads(z.read("tabelas/radar_imagens.json"))]
    no_banco = [i for (i,) in db.execute("select id from radar_imagens order by id")]
    man = {t["tabela"]: t for t in json.loads(z.read("manifesto.json"))["tabelas"]}
    assert na_copia == todos and set(no_banco) <= set(na_copia)                     # a apagada já tinha sido lida; nenhuma pulou
    assert man["radar_imagens"]["linhas"] == len(na_copia) == 7
    # cada página das imagens começa depois da chave da última (o marcador), e nunca por número de página
    paginas = [json.loads(p["corpo_rest"]) for p in ESTADO["pedidos"]
               if p["caminho"] == "/rest/v1/rpc/radar_copias_exportar" and '"p_tabela":"radar_imagens"' in p["corpo_rest"]]
    assert [json.loads(bytes.fromhex(p["p_depois"])) if p["p_depois"] else None for p in paginas] == [
        None, {"id": todos[1]}, {"id": todos[3]}, {"id": todos[5]}]
    assert all("p_pagina" not in p for p in paginas)


def test_pagina_cortada_nao_vale(copia, monkeypatch):
    """O marcador vem no fim da página: se a página vier cortada (o "max rows" do Supabase abaixo do tamanho pedido), ele some e a cópia
    falha com recado, em vez de seguir com a tabela pela metade (com OFFSET, a página curta parecia o fim da tabela)."""
    db = copia
    original = requests.request

    def request(metodo, url, **kw):
        r = original(metodo, url, **kw)
        if b'"p_tabela":"radar_config"' in (kw.get("data") or b"") and r.status_code == 200:
            m = re.fullmatch(r"(\d+)-(\d+)/\*", r.headers.get("Content-Range", ""))
            r._content = r.content[:r.content.rindex(b",")] + b"]"                   # sem o último elemento (o marcador)
            r.headers["Content-Range"] = f"{m[1]}-{int(m[2]) - 1}/*"
        return r

    monkeypatch.setattr(requests, "request", request)
    status, r, _ = copiar()
    assert status == 502 and r["message"] == "Resposta inesperada do banco na tabela radar_config.", r
    assert graph("PUT") == [] and ESTADO["arquivos"] == {}
    assert [(x[0], x[7]) for x in registro(db)] == [(False, "Resposta inesperada do banco na tabela radar_config.")]


def test_sessao_perto_de_vencer_nao_comeca_a_copia(copia):
    """v0.32.0 (revisão): a cópia do administrador usa o token da sessão dele do começo ao fim. O token que vencia no meio deixava a
    cópia "em andamento" (o fim também era recusado) e a tela, que renova a sessão e repete, recebia "já há uma cópia em andamento"
    por 15 minutos. Agora, token valendo menos de 4 minutos: 401 antes de começar, nada registrado, nada na Microsoft; com o token
    novo (a tela renova sozinha no 401), a cópia sai."""
    db = copia
    for folga in (60, -15):                         # vale mais 1 minuto; venceu há 15 s (o PostgREST ainda aceita: 30 s de tolerância)
        token = jwt("authenticated", ADMIN, exp=int(time.time()) + folga)
        status, r, _ = pedir({"acao": "copiar"}, cab={"Authorization": "Bearer " + token})
        assert status == 401 and r["message"].startswith("A sua sessão está perto de vencer e a cópia não começou"), (folga, r)
    assert registro(db) == [] and graph() == [] and [p for p in ESTADO["pedidos"] if p["caminho"].startswith("/login/")] == []
    assert db.execute("select radar_copias_falta_mes()").fetchone()[0] is True                 # a agenda e o botão continuam livres
    token = jwt("authenticated", ADMIN, exp=int(time.time()) + 60)
    assert pedir({"acao": "situacao"}, cab={"Authorization": "Bearer " + token})[0] == 200      # só a cópia pede a folga
    status, r, _ = copiar()                                                                     # o token novo (1 hora)
    assert status == 200 and r["ok"] is True, r
    assert [x[0] for x in registro(db)] == [True]


def test_resposta_perdida_do_envio_nao_vira_falha(copia, monkeypatch):
    """v0.32.0 (revisão): o OneDrive gravou o arquivo e só a resposta se perdeu (5xx). A repetição, com conflictBehavior "fail", esbarrava
    no próprio arquivo (409) e a cópia virava falha com o .zip inteiro na pasta. Agora, depois de uma repetição, o arquivo da pasta com
    o tamanho enviado vale. No envio em pedaços, o mesmo com o último pedaço (a sessão já acabou: 404)."""
    db = copia
    original = Ponte._responder
    trocados = []

    def responder(self, status, corpo=b"", extras=None):
        if self.command == "PUT" and status == 201 and not trocados and (":/content" in self.path or "/sessao/" in self.path):
            trocados.append(self.path)                                           # gravou; a resposta se perde
            return original(self, 503, {"error": {"code": "serviceNotAvailable"}}, extras)
        return original(self, status, corpo, extras)

    monkeypatch.setattr(Ponte, "_responder", responder)
    status, r, _ = copiar()                                                      # .zip pequeno: um PUT só
    assert status == 200 and r["ok"] is True, r
    assert trocados and len(graph("PUT")) == 2 and list(ESTADO["arquivos"]) == [r["arquivo"]]
    assert [p["query"] for p in graph("GET", ":/" + r["arquivo"])] == ["$select=id,name,size"]
    conferir_zip(db, zip_de(r["arquivo"]), r["arquivo"])
    assert [x[0] for x in registro(db)] == [True]
    db.execute("delete from radar_copias")
    novo_estado()
    trocados.clear()
    status, r, _ = copiar(PORTA_B)                                               # em pedaços: o último se perde
    assert status == 200 and r["ok"] is True, r
    assert trocados and trocados[0].startswith("/sessao/") and len(graph("POST", "createUploadSession")) == 1
    assert list(ESTADO["arquivos"]) == [r["arquivo"]] and len(graph("GET", ":/" + r["arquivo"])) == 1
    conferir_zip(db, zip_de(r["arquivo"]), r["arquivo"])
    # sem repetição, o 409 continua falha (o nome já existe na pasta: outra cópia no mesmo minuto), e nada é perguntado ao OneDrive
    monkeypatch.setattr(Ponte, "_responder", original)
    db.execute("delete from radar_copias")
    novo_estado()
    m = re.fullmatch(r"radar-copia-(\d{4}-\d{2}-\d{2})-(\d{2})(\d{2})\.zip", r["arquivo"])
    depois = datetime.strptime(f"{m[1]} {m[2]}:{m[3]}", "%Y-%m-%d %H:%M") + timedelta(minutes=1)
    for nome in (r["arquivo"], f"radar-copia-{depois:%Y-%m-%d-%H%M}.zip"):                     # este minuto e o seguinte
        ESTADO["arquivos"][nome] = {"id": "OUTRO", "dados": b"x"}
    status, r2, _ = pedir({"acao": "copiar"})
    assert status == 409 and r2["message"].startswith("Já existe no OneDrive um arquivo com este nome"), r2
    assert len(graph("PUT")) == 1 and graph("GET", ":/radar-copia-") == []
    assert [x[0] for x in registro(db)] == [False]


def test_nada_vai_para_log_nem_storage(funcao):
    """Depois dos testes acima: o log das funções não tem nome, conteúdo, segredo, a chave da agenda nem o nome do arquivo; e nenhum
    pedido foi ao armazenamento do Supabase."""
    for nome in ("a", "b", "c", "d"):
        log = (funcao / f"{nome}.log").read_text()
        for proibido in ("Ana Teste", "Bruno Exemplo", "segredo-de-teste", CHAVE_AGENDA, "radar-copia-20", "ghp_", "data:image"):
            assert proibido not in log, (nome, proibido)
    assert re.search(r"radar-copia \(admin\): ok, 30 tabelas, \d+ linhas, [\d.]+ MB, \d+ ms", (funcao / "a.log").read_text())
    assert STORAGE == []


def test_tabelas_da_funcao_tem_versao_e_sem_import():
    codigo = FUNCAO.read_text(encoding="utf-8")
    assert re.search(r'(?m)^const VERSAO = "0\.32\.0";$', codigo)
    assert not re.search(r"(?m)^\s*import\b", codigo) and not re.search(r"\b(npm|jsr):|esm\.sh|deno\.land", codigo)
    codigo_sem_comentario = [l for l in codigo.splitlines() if not l.lstrip().startswith(("//", "/*", "*"))]
    usos = [l.strip() for l in codigo_sem_comentario if "RADAR_PORTA_LOCAL" in l]
    assert usos == ['return Boolean(Deno.env.get("RADAR_PORTA_LOCAL")) && url.protocol === "http:" && url.hostname === "127.0.0.1";',
                    'const portaLocal = Deno.env.get("RADAR_PORTA_LOCAL");       // só para rodar/testar fora do Supabase']
    assert len(TABELAS) == 30
