"""Função radar-itc (v0.12.0) rodando de verdade no Deno, com o banco real (PostgREST), um Microsoft Graph de mentira
e uma IA Central de mentira. Sem o Deno instalado, o arquivo é pulado.

Confere: só o administrador (ou a agenda, com a chave do Vault) chama; cada boletim vira matérias na fonte itc-email;
o mesmo e-mail não é lido duas vezes; links saem do texto; e nada do conteúdo do boletim volta na resposta.
"""
from __future__ import annotations

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

from conftest import ADMIN, API, EDITOR, RAIZ, jwt, psql
from test_radar_banco import FONTES_NOVAS

PORTA_PONTE, PORTA_FUNCAO = 3992, 3991
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
CAIXA = "contato@artecon.test"
ESTADO = {"emails": [], "graph": [], "ia": [], "token_ok": True}

BOLETIM = """ITCNET Mail - 05/10/2026
Área Federal
SIMPLES NACIONAL: PRAZO DE OPÇÃO PARA 2027 É PRORROGADO
O prazo foi prorrogado até 15 de outubro. Leia mais: https://rastreio.itcnet.com.br/abc?u=123
Capacitação profissional
CURSO AO VIVO: REFORMA TRIBUTÁRIA"""


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST; /login → token do Graph; /graph → caixa de e-mail; /gw → IA Central (formato da Anthropic)."""
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

    def do_GET(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        if self.path.startswith(f"/graph/users/{CAIXA.replace('@', '%40')}/messages"):
            q = parse_qs(urlparse(self.path).query)
            ESTADO["graph"].append({"filtro": q["$filter"][0], "select": q["$select"][0], "prefer": self.headers.get("Prefer"),
                                    "auth": self.headers.get("Authorization")})
            return self._responder(200, {"value": ESTADO["emails"]})
        self._responder(404, {"error": {"code": "ResourceNotFound"}})

    def do_POST(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        tamanho = int(self.headers.get("Content-Length") or 0)
        if self.path.startswith("/login/"):
            corpo = parse_qs(self.rfile.read(tamanho).decode())
            if not ESTADO["token_ok"] or corpo.get("client_secret") != ["segredo-de-teste"]:
                return self._responder(401, {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret."})
            return self._responder(200, {"access_token": "token-graph", "expires_in": 3600})
        corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        ESTADO["ia"].append(corpo)
        materias = [{"titulo": "SIMPLES NACIONAL: PRAZO DE OPÇÃO PARA 2027 É PRORROGADO", "area": "Área Federal",
                     "texto": "O prazo foi prorrogado até 15 de outubro. Leia mais: https://rastreio.itcnet.com.br/abc?u=123"},
                    {"titulo": "x", "area": "", "texto": ""}]                       # título curto: descartado
        self._responder(200, {"type": "message", "model": corpo["model"], "stop_reason": "tool_use",
                              "usage": {"input_tokens": 3000, "output_tokens": 400},
                              "content": [{"type": "tool_use", "name": "materias", "input": {"materias": materias}}]})

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def funcao(api_postgrest):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), SUPABASE_SERVICE_ROLE_KEY=jwt("service_role"),
                    IA_GATEWAY_TOKEN="iagw_radar_teste", IA_GATEWAY_URL=PONTE + "/gw", GRAPH_LOGIN_URL=PONTE + "/login",
                    GRAPH_URL=PONTE + "/graph", GRAPH_TENANT_ID="tenant-teste", GRAPH_CLIENT_ID="cliente-teste",
                    GRAPH_CLIENT_SECRET="segredo-de-teste", ITC_CAIXA=CAIXA, RADAR_PORTA_LOCAL=str(PORTA_FUNCAO), NO_COLOR="1")
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                             str(RAIZ / "supabase" / "functions" / "radar-itc" / "index.ts")],
                            env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(150):
        try:
            requests.options(f"http://127.0.0.1:{PORTA_FUNCAO}/", timeout=1)
            break
        except requests.RequestException:
            time.sleep(0.2)
    yield
    proc.terminate()
    ponte.shutdown()


@pytest.fixture()
def itc(funcao, limpo):
    assert psql(FONTES_NOVAS).returncode == 0
    limpo.execute("truncate radar_itc_lidos")
    ESTADO.update(emails=[], graph=[], ia=[], token_ok=True)
    yield limpo
    limpo.execute("truncate radar_itc_lidos")
    limpo.execute("delete from radar_capturas where fonte_id in (select id from radar_fontes where slug in "
                  "('dou-destaques','econet-blog','portalcontabilsc-noticias','dou-inlabs','itc-email'))")
    limpo.execute("delete from radar_fontes where slug in ('dou-destaques','econet-blog','portalcontabilsc-noticias','dou-inlabs','itc-email')")


def pedir(corpo=None, uid=ADMIN, cab=None):
    cab = cab if cab is not None else {"Authorization": "Bearer " + jwt("authenticated", uid)}
    r = requests.post(f"http://127.0.0.1:{PORTA_FUNCAO}/", timeout=60, json=corpo or {"acao": "ler"}, headers=cab)
    return r.status_code, r.json()


def email(id_, quando="2026-10-05T10:30:00Z", assunto="ITCNET Mail"):
    return {"id": id_, "subject": assunto, "receivedDateTime": quando, "body": {"contentType": "text", "content": BOLETIM}}


def test_le_o_boletim_grava_as_materias_uma_vez_e_nao_devolve_o_conteudo(itc):
    ESTADO["emails"] = [email("AAMk-1")]
    status, r = pedir()
    assert status == 200, r
    assert (r["emails"], r["ja_lidos"], r["materias"], r["novas"], r["falhas"]) == (1, 0, 1, 1, [])
    assert "PRAZO" not in json.dumps(r, ensure_ascii=False)                       # a resposta só traz contagens
    g = ESTADO["graph"][-1]
    assert "from/emailAddress/address eq 'itc@itcnet.com.br'" in g["filtro"] and "receivedDateTime ge " in g["filtro"]
    assert g["prefer"] == 'outlook.body-content-type="text"' and g["auth"] == "Bearer token-graph"
    pedido = ESTADO["ia"][-1]
    assert pedido["model"] == "claude-haiku-4-5" and "Santa Catarina" in pedido["system"] and "<<<BOLETIM>>>" in pedido["messages"][0]["content"]
    titulo, texto, data, meta = itc.execute("""select c.titulo, c.texto, c.data_publicacao::text, c.metadados from radar_capturas c
                                               join radar_fontes f on f.id = c.fonte_id where f.slug = 'itc-email'""").fetchone()
    assert titulo.startswith("SIMPLES NACIONAL") and "http" not in texto and data == "2026-10-05"
    assert meta["assunto_email"] == "ITCNET Mail" and meta["origem"] == "email"
    assert itc.execute("select message_id, materias, novas from radar_itc_lidos").fetchall() == [("AAMk-1", 1, 1)]
    # de novo: o mesmo e-mail não vai à IA outra vez
    ESTADO["emails"].append(email("AAMk-2", "2026-10-05T19:00:00Z", "Edição Extra"))
    status, r = pedir()
    assert (r["emails"], r["ja_lidos"], r["materias"], r["novas"], r["ja_existiam"]) == (2, 1, 1, 0, 1)
    assert len(ESTADO["ia"]) == 2


def test_sem_boletim_registra_que_a_leitura_aconteceu(itc):
    status, r = pedir()
    assert status == 200 and (r["emails"], r["materias"]) == (0, 0)
    assert itc.execute("select ultimo_sucesso_em is not null from radar_fontes where slug = 'itc-email'").fetchone()[0]
    assert ESTADO["ia"] == []


def test_so_o_administrador_ou_a_agenda_com_a_chave_certa(itc):
    assert pedir(uid=EDITOR)[0] == 403
    assert pedir(cab={})[0] == 401
    # no banco de teste não há Vault: nenhuma chave confere
    assert pedir(cab={"x-radar-agenda": "a" * 64})[0] == 401
    assert ESTADO["graph"] == []


def test_diagnostico_mostra_o_que_falta_sem_ler_conteudo(itc):
    ESTADO["emails"] = [email("AAMk-9")]
    status, r = pedir({"acao": "diagnostico"})
    assert status == 200 and r["tudo_certo"] is True
    assert "1 boletim(ns)" in r["itens"][-1]["detalhe"] and "body" not in ESTADO["graph"][-1]["select"]
    assert ESTADO["ia"] == [] and itc.execute("select count(*) from radar_itc_lidos").fetchone()[0] == 0
    ESTADO["token_ok"] = False
    status, r = pedir({"acao": "diagnostico"})
    assert r["tudo_certo"] is False and "invalid_client" in json.dumps(r) and "segredo-de-teste" not in json.dumps(r)
    assert pedir({"acao": "diagnostico"}, uid=EDITOR)[0] == 403
