"""Função radar-ia (v0.10.0) rodando de verdade no Deno, com o banco real (PostgREST) e uma IA Central de mentira.

Confere o que a v0.10.0 mudou: o "Gerar" guarda as outras opções de título e pede a escrita natural; a ação nova
"titulos" só sugere (não grava nada) e não repete o que já foi sugerido. Sem o Deno instalado, o arquivo é pulado.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from conftest import API, EDITOR, RAIZ, jwt
from test_radar_banco import cenario_publicavel

PORTA_PONTE, PORTA_FUNCAO = 3994, 3993
PONTE = f"http://127.0.0.1:{PORTA_PONTE}"
IA = {"pedidos": [], "respostas": {}}


class Ponte(BaseHTTPRequestHandler):
    """/rest/v1 → PostgREST; /auth/v1/user → e-mail de quem pede; /gw → IA Central de mentira (formato da Anthropic)."""
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
        if self.path == "/auth/v1/user":
            return self._responder(200, {"id": EDITOR, "email": "editora@artecon.test"})
        self._responder(404, {"message": "nao encontrado"})

    def do_PATCH(self):
        self._rest()

    def do_POST(self):
        if self.path.startswith("/rest/v1/"):
            return self._rest()
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        IA["pedidos"].append(corpo)
        nome = corpo["tools"][0]["name"]
        self._responder(200, {"type": "message", "model": corpo["model"], "stop_reason": "tool_use",
                              "usage": {"input_tokens": 1000, "output_tokens": 300},
                              "content": [{"type": "tool_use", "name": nome, "input": IA["respostas"][nome]}]})

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def funcao(api_postgrest):
    if shutil.which("deno") is None:
        pytest.skip("deno não instalado")
    ponte = ThreadingHTTPServer(("127.0.0.1", PORTA_PONTE), Ponte)
    threading.Thread(target=ponte.serve_forever, daemon=True).start()
    ambiente = dict(os.environ, SUPABASE_URL=PONTE, SUPABASE_ANON_KEY=jwt("anon"), IA_GATEWAY_TOKEN="iagw_radar_teste",
                    IA_GATEWAY_URL=PONTE + "/gw", RADAR_PORTA_LOCAL=str(PORTA_FUNCAO), NO_COLOR="1")
    proc = subprocess.Popen(["deno", "run", "--allow-net", "--allow-env", "--no-prompt",
                             str(RAIZ / "supabase" / "functions" / "radar-ia" / "index.ts")],
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


def pedir(acao, **extra):
    r = requests.post(f"http://127.0.0.1:{PORTA_FUNCAO}/", timeout=60, json={"acao": acao, **extra},
                      headers={"Authorization": "Bearer " + jwt("authenticated", EDITOR)})
    return r.status_code, r.json()


def test_gerar_guarda_as_opcoes_de_titulo_e_pede_escrita_natural(funcao, limpo):
    a, _ = cenario_publicavel(limpo)
    limpo.execute("insert into radar_assunto_capturas select %s, captura_id from radar_evidencias where assunto_id = %s on conflict do nothing", (a, a))
    IA["respostas"]["conteudo"] = {
        "titulo": "CBS terá alíquota de 0,9% na transição",
        "titulos": ["CBS: alíquota de 0,9% na fase de transição.", "CBS terá alíquota de 0,9% na transição", "CBS",
                    "O que muda com a CBS a 0,9%", "CBS: alíquota de 0,9% na fase de transição", "Quarto título que sobra"],
        "corpo": "A CBS será cobrada à alíquota de 0,9% (nove décimos por cento) no período de transição, conforme o texto oficial. " * 2}
    status, r = pedir("gerar", assunto_id=a, formato="flash")
    assert status == 200, r
    pedido = IA["pedidos"][-1]
    assert "ESCRITA NATURAL" in pedido["system"] and "'titulos'" in pedido["system"]
    assert pedido["tools"][0]["input_schema"]["required"] == ["titulo", "titulos", "corpo"]
    esperado = ["CBS: alíquota de 0,9% na fase de transição", "O que muda com a CBS a 0,9%", "Quarto título que sobra"]
    assert r["titulos"] == esperado
    assert limpo.execute("select titulos_sugeridos from radar_conteudos where id = %s", (r["conteudo_id"],)).fetchone()[0] == esperado
    assert limpo.execute("select acao from radar_ia_uso order by id desc limit 1").fetchone()[0] == "gerar"


def test_titulos_so_sugere_e_nao_repete(funcao, limpo):
    a, c = cenario_publicavel(limpo)
    antes = limpo.execute("select atualizado_em, titulo from radar_conteudos where id = %s", (c,)).fetchone()
    IA["respostas"]["titulos"] = {"titulos": ["Já sugerido antes", "Título novo e bem diferente", antes[1], "Outro título novo aqui"]}
    status, r = pedir("titulos", assunto_id=a, conteudo_id=c, evitar=["Já sugerido antes"])
    assert status == 200, r
    assert r["titulos"] == ["Título novo e bem diferente", "Outro título novo aqui"]
    pedido = IA["pedidos"][-1]
    assert pedido["model"] == "claude-haiku-4-5" and "Já sugerido antes" in pedido["messages"][0]["content"]
    assert limpo.execute("select atualizado_em, titulo from radar_conteudos where id = %s", (c,)).fetchone() == antes   # nada gravado
    assert limpo.execute("select acao from radar_ia_uso order by id desc limit 1").fetchone()[0] == "gerar"       # consumo registrado
    status, r = pedir("titulos", assunto_id=a, conteudo_id=999999)
    assert status == 404 and "não encontrado" in r["message"]
    status, r = pedir("titulos", assunto_id=a, conteudo_id="x")
    assert status == 400
