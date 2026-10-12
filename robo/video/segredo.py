"""Radar Artecon — corretor de vídeo (v0.22.0): o que o robô pode escrever no log.

O log do GitHub Actions (do repositório privado radar-video) só recebe o uuid do pedido, a etapa, durações, contagens e códigos
fixos. Nunca: fala, roteiro, nomes, e-mails, metadados do vídeo (o GPS e o modelo do celular vêm no ffprobe e no cabeçalho que o
ffmpeg imprime), links assinados, tokens de envio e chaves. Por isso:
  * o stderr do ffmpeg e do ffprobe nunca é impresso (isolado.py só o lê para as medições, sobre o WAV ou a saída sem metadados);
  * todo erro vira ErroVideo com um código fixo (`^[a-z_]{3,40}$`, o mesmo formato de radar_videos.erro_codigo);
  * log() só aceita número, booleano e código curto; o resto vira "?";
  * o excepthook imprime só a etapa e o NOME do tipo da exceção (a mensagem pode ter um nome, um link ou um trecho da fala);
  * sem_segredo() é a última barreira para qualquer texto que precise sair (tira link, token=, x-signature, o cabeçalho da chave da
    Azure, Bearer, sb_secret_, iagw_ e o valor das chaves do ambiente: a do robô e a da Azure, AZURE_FALA_CHAVE, que transcrever.py
    lê no passo do workflow).
"""
from __future__ import annotations

import os
import re
import sys
import threading

CODIGO = re.compile(r"^[a-z_]{3,40}$")
# as chaves que o workflow põe no ambiente do robô: o valor delas nunca sai, nem por engano
CHAVES_DO_AMBIENTE = ("RADAR_VIDEO_ROBO_CHAVE", "AZURE_FALA_CHAVE")
_PADROES = [
    (re.compile(r"https?://\S+", re.I), "[link]"),
    (re.compile(r"[?&](token|sig|signature|apikey|key)=\S+", re.I), "[token]"),
    (re.compile(r"x-signature\W{0,3}\s*\S+", re.I), "[token]"),
    (re.compile(r"(ocp-apim-subscription-key|authorization)\W{0,3}\s*(?:(?:bearer|oauth)\s+)?\S+", re.I), "[token]"),
    (re.compile(r"\b(bearer|oauth)\s+[A-Za-z0-9._~+/=-]{8,}", re.I), "[token]"),
    (re.compile(r"sb_(secret|publishable)_\S+"), "sb_***"),
    (re.compile(r"iagw_\S+"), "iagw_***"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]+"), "[jwt]"),
    # coordenadas no formato ISO 6709, como o celular grava (+DD.DDDD-DDD.DDDD/)
    (re.compile(r"[+-]\d{1,3}\.\d+[+-]\d{1,3}\.\d+(?:[+-]\d+(?:\.\d+)?)?/?"), "[local]"),
]


class ErroVideo(Exception):
    """Falha do corretor com código fixo. `codigo` vai para radar_videos.erro_codigo; `detalhe` só leva nomes fixos (por exemplo, o
    item da conferência que não passou), nunca dado do vídeo."""

    def __init__(self, codigo: str, etapa: str = "", detalhe: tuple[str, ...] | list[str] = ()):
        if not CODIGO.match(codigo):
            codigo = "erro_interno"
        self.codigo = codigo
        self.etapa = etapa if etapa and CODIGO.match(etapa) else ""
        self.detalhe = tuple(d for d in detalhe if CODIGO.match(str(d)))
        super().__init__(codigo)

    def __str__(self) -> str:
        return self.codigo + (f" ({self.etapa})" if self.etapa else "") + (f": {', '.join(self.detalhe)}" if self.detalhe else "")


def sem_segredo(texto: object, *segredos: str) -> str:
    """Tira de um texto os links, tokens e chaves (os do ambiente e os passados aqui)."""
    t = str(texto or "")
    for s in [*segredos, *(os.environ.get(c, "") for c in CHAVES_DO_AMBIENTE)]:
        if s and len(s) >= 6:
            t = t.replace(s, "***")
    for padrao, troca in _PADROES:
        t = padrao.sub(troca, t)
    return t


def _valor(v: object) -> str:
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.2f}"
    if isinstance(v, str) and CODIGO.match(v):
        return v
    if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", v):
        return v                                       # o uuid do pedido (radar_videos.id): não é dado pessoal
    return "?"


def log(etapa: str, **campos: object) -> None:
    """Uma linha no log: a etapa e só números, booleanos, códigos e o uuid do pedido."""
    nome = etapa if CODIGO.match(etapa) else "?"
    print("corretor: " + " ".join([nome, *(f"{k}={_valor(v)}" for k, v in campos.items() if re.fullmatch(r"[a-z_]{2,40}", k))]),
          flush=True)


_contexto = {"pedido": "", "etapa": "inicio"}


def etapa(nome: str, pedido: str | None = None) -> None:
    """Marca a etapa em curso (é o que o excepthook mostra, junto do uuid)."""
    _contexto["etapa"] = nome if CODIGO.match(nome) else "?"
    if pedido is not None:
        _contexto["pedido"] = _valor(pedido)


def _gancho(tipo, valor, rastro) -> None:               # noqa: ARG001 — a mensagem e o rastro nunca saem
    pedido = _contexto["pedido"]
    print(f"corretor: erro inesperado na etapa {_contexto['etapa']}" + (f" do pedido {pedido}" if pedido else "")
          + f" ({getattr(tipo, '__name__', 'Exception')})", file=sys.stderr, flush=True)


def instalar_excepthook() -> None:
    """Exceção não tratada imprime só a etapa, o uuid e o nome do tipo (nem a mensagem, nem o rastro, que mostra variáveis em
    alguns ambientes e linhas do código com dados). Vale também para a linha de outra thread (o SDK da Azure chama o robô das linhas
    dele) e para a exceção "ignorada" que o Python imprime sozinho (num __del__ ou numa chamada de volta do ctypes)."""
    sys.excepthook = _gancho
    threading.excepthook = lambda a: _gancho(a.exc_type, a.exc_value, a.exc_traceback)
    sys.unraisablehook = lambda u: _gancho(u.exc_type, u.exc_value, u.exc_traceback)
