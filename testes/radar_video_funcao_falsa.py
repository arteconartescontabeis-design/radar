"""v0.22.0 — a função radar-video SIMULADA para os testes do robô de ponta a ponta (robo/video/corrigir.py e conversa.py).

Um servidor local (127.0.0.1, porta livre) que responde como a função (supabase/functions/radar-video/index.ts) às ações do robô —
pegar, links, audio, parcial, concluir e falhar — e como o Supabase Storage aos links que ela assina: o GET do link de leitura
(…/object/sign/radar-videos/<caminho>?token=…) e o PUT do token de envio (…/object/upload/sign/radar-videos/<caminho>?token=…, sem
upsert: o caminho que já existe responde 400 com statusCode 409, "Duplicate"). As mesmas regras da função: só a chave do robô e a anon;
links só dos caminhos do pedido que está com o robô, nesta rodada (senão o RADAR316 sem o código, como a função devolve); o corrigido
que já existe não ganha token (409); o concluir confere o vídeo (tamanho e tipo) e os 4 quadros. As respostas podem ser roteirizadas
por ação (`falhas`). Guarda cada chamada (`chamadas`) e cada envio (com os cabeçalhos) para o teste conferir. Nada de dado real.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PERDIDO = ("este pedido não está mais com o robô nesta tentativa (foi substituído, descartado, ajustado ou passou do tempo)")
TRANSITORIOS = ("storage", "rede", "azure_fora", "github")
ROTA = "/functions/v1/radar-video"


def pedido(vid: str, partes: list[dict], fala: str, config: dict, modo: str = "completo", cartela=("Linha da cartela",),
           gancho: str | None = None, ajustes: dict | None = None, palavras_tentativa: int | None = None,
           restante_s: float = 3600.0) -> dict:
    """O pedido como radar_video_pegar devolve (a rodada é a função falsa que põe)."""
    return {"id": vid, "modo": modo, "partes": partes, "fala_roteiro": fala, "cartela_linhas": list(cartela), "gancho": gancho,
            "ajustes": ajustes or {}, "palavras_tentativa": palavras_tentativa, "restante_s": restante_s, "config": config}


class FuncaoFalsa:
    def __init__(self, chave: str, anon: str):
        self.chave, self.anon = chave, anon
        self.fila: list[dict] = []
        self.objetos: dict[str, dict] = {}              # caminho → {dados, tipo, cache, upsert}
        self.leituras: dict[str, str] = {}              # token de leitura → caminho
        self.envios: dict[str, str] = {}                # token de envio → caminho
        self.chamadas: list[tuple[str, dict]] = []
        self.puts: list[tuple[str, dict]] = []          # (caminho, cabeçalhos) de cada PUT, com ou sem sucesso
        self.gets: list[str] = []
        self.falhas: dict[str, list[tuple[int, str]]] = {}   # "pegar", "audio", …, "get:<prefixo>", "put:<prefixo>" → respostas
        self.em_curso: tuple[str, int] | None = None
        self.rodadas: dict[str, int] = {}
        self.guardada: dict[str, int] = {}
        self.segundos: dict[str, float] = {}
        self.audio_rodadas: set[tuple[str, int]] = set()
        self.final: dict[str, dict] = {}
        self.pedidos: dict[str, dict] = {}
        self.cabecalhos_ruins = 0
        f = self

        class Atende(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _responder(self, status, corpo=None, tipo="application/json"):
                dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode() if corpo is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def _roteiro(self, chave):
                for k, lista in f.falhas.items():
                    if lista and (k == chave or (":" in k and chave.startswith(k))):
                        status, msg = lista.pop(0)
                        self._responder(status, {"message": msg} if not k.startswith(("get:", "put:")) else
                                        {"statusCode": str(status), "error": "Simulado", "message": msg})
                        return True
                return False

            def do_POST(self):
                if self.path != ROTA:
                    return self._responder(404, {"message": "Not Found"})
                if self.headers.get("Authorization") != "Bearer " + f.anon or self.headers.get("x-radar-video-robo") != f.chave:
                    f.cabecalhos_ruins += 1
                    return self._responder(401, {"message": "Chave não confere."})
                corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                acao = corpo.get("acao")
                f.chamadas.append((acao, corpo))
                if self._roteiro(acao):
                    return
                status, r = f.acao(acao, corpo)
                self._responder(status, r)

            def do_GET(self):
                u = urlparse(self.path)
                caminho = u.path.removeprefix("/storage/v1/object/sign/radar-videos/")
                token = (parse_qs(u.query).get("token") or [""])[0]
                f.gets.append(caminho)
                if self._roteiro("get:" + caminho):
                    return
                if not u.path.startswith("/storage/v1/object/sign/radar-videos/") or f.leituras.get(token) != caminho \
                        or caminho not in f.objetos:
                    return self._responder(400, {"statusCode": "404", "error": "not_found", "message": "Object not found"})
                self._responder(200, f.objetos[caminho]["dados"], f.objetos[caminho]["tipo"])

            def do_PUT(self):
                u = urlparse(self.path)
                caminho = u.path.removeprefix("/storage/v1/object/upload/sign/radar-videos/")
                token = (parse_qs(u.query).get("token") or [""])[0]
                dados = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                f.puts.append((caminho, {k.lower(): v for k, v in self.headers.items()}))
                if self._roteiro("put:" + caminho):
                    return
                if not u.path.startswith("/storage/v1/object/upload/sign/radar-videos/") or f.envios.get(token) != caminho:
                    return self._responder(400, {"statusCode": "403", "error": "Unauthorized", "message": "invalid signature"})
                if caminho in f.objetos:
                    return self._responder(400, {"statusCode": "409", "error": "Duplicate", "message": "The resource already exists"})
                f.objetos[caminho] = {"dados": dados, "tipo": self.headers.get("Content-Type", ""),
                                      "cache": self.headers.get("cache-control"), "upsert": self.headers.get("x-upsert")}
                self._responder(200, {"Key": "radar-videos/" + caminho})

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Atende)
        self.porta = self.servidor.server_address[1]
        self.base = f"http://127.0.0.1:{self.porta}"
        self.url = self.base + ROTA
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()

    # ------------------------------------------------------------------ armazenamento
    def guardar(self, caminho: str, dados: bytes, tipo: str = "video/mp4") -> None:
        self.objetos[caminho] = {"dados": dados, "tipo": tipo, "cache": None, "upsert": None}

    def _ler(self, caminho: str) -> str:
        t = "assinado." + secrets.token_hex(8)
        self.leituras[t] = caminho
        return f"{self.base}/storage/v1/object/sign/radar-videos/{caminho}?token={t}"

    def _gravar(self, caminho: str) -> dict:
        t = "envio." + secrets.token_hex(8)
        self.envios[t] = caminho
        return {"caminho": caminho, "token": t, "url": f"{self.base}/storage/v1/object/upload/sign/radar-videos/{caminho}?token={t}"}

    # ------------------------------------------------------------------ ações
    def acao(self, acao: str, c: dict) -> tuple[int, object]:
        if acao == "pegar":
            if not self.fila:
                return 200, {"pedido": None}
            p = dict(self.fila.pop(0))
            vid = p["id"]
            t = self.rodadas[vid] = self.rodadas.get(vid, 0) + 1
            p["tentativa"] = t
            self.em_curso = (vid, t)
            g = p.get("palavras_tentativa")
            return 200, {"pedido": p, "links": {"partes": [{**x, "url": self._ler(f"bruto/{vid}/{x['n']}")} for x in p["partes"]],
                                                "palavras": self._ler(f"trabalho/{vid}/{g}/palavras.json") if g else None},
                         "envio_palavras": self._gravar(f"trabalho/{vid}/{t}/palavras.json") if p["modo"] == "completo" else None,
                         "expira_s": 600, "cache_s": 60}
        vid, t = c.get("id"), c.get("tentativa")
        if self.em_curso != (vid, t):
            return 400, {"message": PERDIDO}
        if acao == "links":
            n = len(self.pedido_atual()["partes"])
            g = self.guardada.get(vid)
            pode_ler = lambda k: bool(re.fullmatch(rf"bruto/{vid}/([1-9]|1[0-2])", k) and int(k.rsplit("/", 1)[1]) <= n) \
                or (g and k == f"trabalho/{vid}/{g}/palavras.json")
            pode_gravar = lambda k: k == f"trabalho/{vid}/{t}/palavras.json" or bool(re.fullmatch(rf"corrigido/{vid}/[0-9a-f]{{64}}\.mp4", k)) \
                or bool(re.fullmatch(rf"quadros/{vid}/[0-9a-f]{{64}}/q[1-4]\.jpg", k))
            ler, gravar = c.get("ler") or [], c.get("gravar") or []
            fora = [k for k in ler if not pode_ler(k)] + [k for k in gravar if not pode_gravar(k)]
            if fora:
                return 403, {"message": f"{len(fora)} caminho(s) fora do pedido."}
            if any(k.startswith("corrigido/") and k in self.objetos for k in gravar):
                return 409, {"message": "O vídeo corrigido com este sha256 já está no armazenamento: o caminho nunca se sobrescreve."}
            return 200, {"ler": {k: self._ler(k) for k in ler}, "gravar": {k: {"url": (e := self._gravar(k))["url"], "token": e["token"]}
                                                                          for k in gravar}, "expira_s": 600, "cache_s": 60}
        if acao == "audio":
            o = self.objetos.get(f"trabalho/{vid}/{t}/palavras.json")
            guardou = bool(o and o["dados"] and o["tipo"].startswith("application/json"))
            if (vid, t) not in self.audio_rodadas:          # como radar_video_registrar_audio: uma vez por rodada
                self.audio_rodadas.add((vid, t))
                self.segundos[vid] = self.segundos.get(vid, 0) + float(c["segundos"])
            if guardou:
                self.guardada[vid] = t
            return 200, {"palavras_guardadas": guardou, "restante_s": 3600 - self.segundos[vid]}
        if acao == "parcial":
            return 200, True
        if acao == "concluir":
            v = self.objetos.get(f"corrigido/{vid}/{c['sha256']}.mp4")
            if not v or len(v["dados"]) != c["bytes"] or v["tipo"] != "video/mp4":
                return 409, {"message": "O vídeo corrigido não está no armazenamento com o tamanho e o tipo informados: suba de novo."}
            if any(f"quadros/{vid}/{c['sha256']}/q{k}.jpg" not in self.objetos for k in range(1, 5)):
                return 409, {"message": "Faltam quadros no armazenamento: suba de novo."}
            situacao = c["situacao"]
            if any(d.get("regravar") and not d.get("transcricao_errou") for d in c["relatorio"].get("divergencias") or []):
                situacao = "regravar"                     # o banco decide de novo
            self.final[vid] = {"situacao": situacao, **c}
            self.em_curso = None
            return 200, {"situacao": situacao}
        if acao == "falhar":
            situacao = "na_fila" if c["codigo"] in TRANSITORIOS else "erro"
            self.final[vid] = {"situacao": situacao, "codigo": c["codigo"]}
            self.em_curso = None
            return 200, {"situacao": situacao}
        return 403, {"message": "O robô só pega o pedido, pede links e entrega o resultado."}

    def pedido_atual(self) -> dict:
        return self.pedidos[self.em_curso[0]]

    def enfileirar(self, p: dict) -> None:
        self.pedidos[p["id"]] = p
        self.fila.append(p)

    def acoes(self) -> list[str]:
        return [a for a, _ in self.chamadas]
