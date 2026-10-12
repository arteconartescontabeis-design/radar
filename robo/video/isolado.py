"""Radar Artecon — corretor de vídeo (v0.22.0): todo ffmpeg e ffprobe roda isolado.

O clipe do celular é entrada NÃO confiável: o ffmpeg lê dezenas de formatos e, por padrão, aceita qualquer protocolo ("All
protocols are allowed by default", https://ffmpeg.org/ffmpeg-protocols.html). Por isso, em produção (o robô no repositório
privado radar-video), cada chamada roda num contêiner descartável da imagem radar-ffmpeg:local (robo/video/Dockerfile):
  * --network none: sem rede (um arquivo malicioso não alcança o Supabase, a Azure nem o GitHub);
  * nenhum -e/--env: o contêiner não recebe a chave do robô nem a da Azure (elas só existem no processo do robô, no passo do
    workflow que as recebe);
  * --read-only, com /tmp em memória (512 MB), --cap-drop ALL, no-new-privileges, usuário 1001 sem privilégio, 6 GB de memória
    (o runner privado tem 8) e até 256 processos;
  * só três pastas: /ent (os clipes baixados, só leitura), /sai (o trabalho e a saída) e /fontes (a DM Sans, só leitura).
Os módulos escrevem os comandos sempre com /ent, /sai e /fontes. Nos testes (RADAR_VIDEO_ISOLADO=local), o ffmpeg roda direto, com os
mesmos argumentos e essas três pastas trocadas pelas de verdade.

O stderr é só lido (para as medições: silencedetect, astats, loudnorm, ebur128, sempre sobre o WAV extraído sem metadados ou sobre
a saída) e nunca impresso, nem na falha: a falha vira ErroVideo com o código fixo e o nome da etapa.
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path

from segredo import ErroVideo

IMAGEM = "radar-ffmpeg:local"
USUARIO = (1001, 1001)                 # o "corretor" do Dockerfile; é também o usuário do runner do GitHub
TEMPO_SONDAR = 60                      # s: sondagem, extração do áudio e medições
TEMPO_MONTAR = 600                     # s: a montagem (mediu 50 a 110 s em 2 vCPU)
PREFIXO = ("docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=512m",
           "--user", f"{USUARIO[0]}:{USUARIO[1]}", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--memory", "6g", "--memory-swap", "6g", "--pids-limit", "256")
PROGRAMAS = ("ffmpeg", "ffprobe")
_CAMINHO_SEGURO = re.compile(r"^/[A-Za-z0-9_./-]+$")    # entra no -v do docker e no grafo de filtros (sem ':', aspas, vírgula)
_RAIZES = re.compile(r"(?<![\w./-])/(ent|sai|fontes)(?=/|'|:|,|;|$)")


@dataclass(frozen=True)
class Pastas:
    ent: Path                          # os clipes baixados (bruto/<id>/<n> → ent/<n>)
    sai: Path                          # o trabalho e a saída
    fontes: Path                       # robo/video/fontes (DM Sans)

    def conferir(self) -> None:
        for p in (self.ent, self.sai, self.fontes):
            if not _CAMINHO_SEGURO.match(str(p)) or ".." in p.parts or not p.is_dir():
                raise ErroVideo("pasta_invalida", "isolado")


def modo() -> str:
    """'docker' (produção, o padrão) ou 'local' (testes: RADAR_VIDEO_ISOLADO=local). Qualquer outro valor é erro, para um erro de
    digitação no workflow nunca rodar o ffmpeg fora do contêiner."""
    m = os.environ.get("RADAR_VIDEO_ISOLADO", "docker")
    if m not in ("docker", "local"):
        raise ErroVideo("isolado_invalido", "isolado")
    return m


def preparar(pastas: Pastas) -> None:
    """A pasta de saída precisa ser gravável pelo usuário 1001 do contêiner (no runner, o próprio robô já é o 1001)."""
    pastas.sai.mkdir(parents=True, exist_ok=True)
    if modo() == "docker":
        if os.getuid() == 0:
            os.chown(pastas.sai, *USUARIO)
        elif os.getuid() != USUARIO[0]:
            pastas.sai.chmod(0o777)
    pastas.conferir()


def comando(programa: str, args: list[str], pastas: Pastas, nome: str = "") -> list[str]:
    """O comando completo. Em produção, o prefixo do contêiner; nos testes, o programa direto com as pastas trocadas."""
    if programa not in PROGRAMAS:
        raise ErroVideo("programa_invalido", "isolado")
    pastas.conferir()
    if modo() == "local":
        mapa = {"ent": str(pastas.ent), "sai": str(pastas.sai), "fontes": str(pastas.fontes)}
        return [programa, *(_RAIZES.sub(lambda m: mapa[m.group(1)], a) for a in args)]
    return [*PREFIXO, *(["--name", nome] if nome else []),
            "-v", f"{pastas.ent}:/ent:ro", "-v", f"{pastas.sai}:/sai:rw", "-v", f"{pastas.fontes}:/fontes:ro",
            IMAGEM, programa, *args]


def _ambiente() -> dict[str, str]:
    """O ffmpeg (nos testes) e o cliente do docker não herdam o ambiente do robô (onde estão as chaves)."""
    amb = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "HOME": os.environ.get("HOME", "/tmp")}
    for k in ("DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR"):
        if os.environ.get(k):
            amb[k] = os.environ[k]
    return amb


def rodar(etapa: str, programa: str, args: list[str], pastas: Pastas, tempo: int = TEMPO_SONDAR, ler: str = "stdout"):
    """Roda e devolve o stdout como texto (ler="bytes": os bytes, para as amostras de áudio; ler="stderr": o stderr, para as
    medições). Nunca imprime nada; a falha vira ErroVideo."""
    nome = f"radar-ffmpeg-{secrets.token_hex(6)}" if modo() == "docker" else ""
    cmd = comando(programa, args, pastas, nome)
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=tempo, env=_ambiente())
    except subprocess.TimeoutExpired:
        if nome:                                       # o cliente morreu, mas o contêiner continuaria: mata pelo nome
            subprocess.run(["docker", "kill", nome], capture_output=True, timeout=30, env=_ambiente())
        raise ErroVideo("ffmpeg_tempo", etapa) from None
    except OSError:
        raise ErroVideo("ffmpeg_ausente", etapa) from None
    if r.returncode != 0:
        raise ErroVideo("ffmpeg_falhou", etapa)
    if ler == "bytes":
        return r.stdout
    return (r.stderr if ler == "stderr" else r.stdout).decode("utf-8", "replace")
