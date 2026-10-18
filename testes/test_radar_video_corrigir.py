"""v0.22.0 — corretor de vídeo, o robô de ponta a ponta (robo/video/corrigir.py, conversa.py e o modelo do workflow do repositório
privado, robo/video/workflow/radar-video.yml).

A radar-video e o armazenamento são SIMULADOS (testes/radar_video_funcao_falsa.py: as mesmas regras da função), a Azure também
(o SDK falso de testes/radar_video_fala_falsa.py, pelo passo transcrever.py) e os vídeos são SINTÉTICOS (testes/radar_video_sintetico.py:
uma "voz" harmônica, o alto da imagem piscando durante cada palavra, o local 0,0). O ffmpeg roda direto (RADAR_VIDEO_ISOLADO=local);
o contêiner é testado em test_radar_video_robo.py. As fases rodam na ordem dos passos do workflow, cada uma com a sua saída
($GITHUB_OUTPUT) — as que têm a chave do robô também como `python -I` de verdade, conferindo que só carregam a biblioteca padrão.
O último teste roda o robô contra a função radar-video DE VERDADE (Deno, com o banco real e o armazenamento de mentira de
test_radar_funcao_video.py), pulado sem o Deno. Nomes fictícios ("Ana Teste"); nada de gravação, transcrição ou roteiro real.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import RAIZ

ROBO = RAIZ / "robo" / "video"
sys.path.insert(0, str(ROBO))

import radar_video_fala_falsa as falsa  # noqa: E402
import radar_video_sintetico as sint  # noqa: E402
from radar_video_fala_falsa import frase_sdk  # noqa: E402
from radar_video_funcao_falsa import PERDIDO, FuncaoFalsa, pedido  # noqa: E402
# a função de verdade (Deno, banco real, armazenamento de mentira) para o último teste
from test_radar_banco import pauta  # noqa: E402,F401
from test_radar_funcao_video import ARM, CHAVE_ROBO, LOGS, PORTA_FUNCAO, funcao, guardar, vid  # noqa: E402,F401
from test_radar_video_banco import FALA as FALA_BANCO, corretor, na_fila, reel, video  # noqa: E402,F401
from test_radar_video_robo import imagem_docker  # noqa: E402,F401 — a imagem radar-ffmpeg:local (pulado sem o docker)

import conversa  # noqa: E402
import corrigir  # noqa: E402
import cortes  # noqa: E402
import segredo  # noqa: E402
import transcrever  # noqa: E402
from segredo import ErroVideo  # noqa: E402

FFMPEG = pytest.mark.skipif(not sint.tem_ffmpeg(), reason="ffmpeg e ffprobe não instalados (o CI instala pelo apt)")
CHAVE = "r0b0" * 16                                  # a forma do token do Vault (64 letras e algarismos); não é um
CHAVE_AZURE = "ChaveFalsaDaAzure0123456789abcdefXYZ"
ANON, REF = conversa.anon_do_config()
VID = "0b1c2d3e-0000-4000-8000-00000000c0de"
GLOSSARIO = ["eSocial", "DCTFWeb", "IBS", "CBS", "Simples Nacional", "MEI", "CNPJ", "DAS", "DARF", "FGTS", "Cofins", "PIS", "PGDAS-D"]
CFG = {"glossario": GLOSSARIO, "variantes": {"eSocial": ["e social", "é social"]}, "pausa_max_s": 1.0, "pausa_bloco_s": 0.8,
       "lufs": -14, "cartela_s": 3, "cartela_extra": "Desde 2000 · (00) 0000-0000", "duracao_max_s": 45}
CARTELA = ["Artecon Artes Contábeis · CNPJ 00.000.000/0001-00 · CRC-SC 000000/O-0", "Ana Teste, contadora · CRC-SC 000001/O-1"]
FALA = "O prazo do eSocial vence em 30/10. Fale com a gente."
GANCHO = "O prazo do eSocial muda"
# clipe 1 (5,6 s): a fala na forma léxica do F0, com um "ééé" (voz sem palavra) entre "vence" e "em"; clipe 2 (3,4 s)
CLIPE1 = [("o", 0.50, 0.62), ("prazo", 0.75, 1.10), ("do", 1.22, 1.35), ("e", 1.48, 1.60), ("social", 1.72, 2.10),
          ("vence", 2.22, 2.55), ("em", 3.65, 3.80), ("trinta", 3.92, 4.25), ("de", 4.37, 4.50), ("outubro", 4.62, 5.10)]
EEE = ("ééé", 2.85, 3.25)
CLIPE2 = [("fale", 0.60, 0.95), ("com", 1.07, 1.25), ("a", 1.40, 1.52), ("gente", 1.65, 2.15)]
DUR1, DUR2 = 5.6, 3.4
PALAVRAS_TODAS = len(CLIPE1) + len(CLIPE2)


def _sdk_ok() -> list[tuple]:
    """A transcrição simulada do F0: as duas frases, com os tempos na linha de fala16k.wav (o clipe 2 começa em 5,6 s)."""
    desloca = int(DUR1 * 30) / 30
    return [("ok", [frase_sdk("O prazo do eSocial vence em 30/10.", [(p, a, b, 0.92) for p, a, b in CLIPE1]),
                    frase_sdk("Fale com a gente.", [(p, round(a + desloca, 3), round(b + desloca, 3), 0.9) for p, a, b in CLIPE2])])]


@pytest.fixture(scope="module")
def clipes(tmp_path_factory):
    """Os dois clipes sintéticos (o 2º em MOV, como o iPhone), gerados uma vez; e um sem áudio."""
    if not sint.tem_ffmpeg():
        pytest.skip("ffmpeg e ffprobe não instalados (o CI instala pelo apt)")
    pasta = tmp_path_factory.mktemp("corrigir_clipes")
    c1 = sint.video(pasta / "c1.mp4", sint.voz(pasta / "v1.wav", CLIPE1 + [EEE], DUR1), 1080, 1920, 30, DUR1, piscar=CLIPE1)
    c2 = sint.video(pasta / "c2.mov", sint.voz(pasta / "v2.wav", CLIPE2, DUR2, semente=11), 1080, 1920, 30, DUR2, formato="mov",
                    piscar=CLIPE2)
    mudo = sint.video(pasta / "mudo.mp4", None, 1080, 1920, 30, 2.0)
    return SimpleNamespace(c1=c1.read_bytes(), c2=c2.read_bytes(), mudo=mudo.read_bytes())


def _partes(*dados: bytes, tipos=("video/mp4", "video/quicktime")) -> list[dict]:
    return [{"n": n, "tipo": tipos[(n - 1) % len(tipos)], "bytes": len(d)} for n, d in enumerate(dados, 1)]


def _no_ar(funcao: FuncaoFalsa, vid: str, *dados: bytes, **kw) -> dict:
    """Os clipes no armazenamento (bruto/<id>/<n>) e o pedido na fila."""
    for n, d in enumerate(dados, 1):
        funcao.guardar(f"bruto/{vid}/{n}", d, "video/mp4")
    p = pedido(vid, kw.pop("partes", None) or _partes(*dados), kw.pop("fala", FALA), CFG, cartela=CARTELA, **kw)
    funcao.enfileirar(p)
    return p


@contextlib.contextmanager
def _ambiente(funcao: FuncaoFalsa | str, sdk_passos=None, chave: str = CHAVE, **extra):
    """O ambiente das fases (no CI cada passo só tem o seu; aqui, um processo só: o isolamento é conferido nos testes do workflow e
    do `python -I`), com a radar-video simulada (ou o endereço da de verdade). Devolve o SDK falso."""
    with pytest.MonkeyPatch.context() as mp:
        for alvo, nome in ((sys, "excepthook"), (sys, "unraisablehook"), (threading, "excepthook")):
            mp.setattr(alvo, nome, getattr(alvo, nome))     # main() instala os do robô; o teste devolve os do pytest
        mp.setenv("RADAR_VIDEO_URL", funcao if isinstance(funcao, str) else funcao.url)
        mp.setenv("RADAR_VIDEO_ROBO_CHAVE", chave)
        mp.setenv("RADAR_VIDEO_ISOLADO", "local")
        mp.setenv("AZURE_FALA_CHAVE", CHAVE_AZURE)
        mp.setenv("AZURE_FALA_REGIAO", "brazilsouth")
        for k in ("AZURE_FALA_MODO", "AZURE_FALA_ENDPOINT", "RADAR_VIDEO_JOB", "GITHUB_OUTPUT"):
            mp.delenv(k, raising=False)
        for k, v in extra.items():
            mp.setenv(k, v)
        mp.setattr(corrigir, "PRESET", "veryfast")
        mp.setattr(conversa, "_dormir", lambda s: None)
        mp.setattr(transcrever, "_dormir", lambda s: None)
        sdk = falsa.sdk_falso(sdk_passos if sdk_passos is not None else _sdk_ok())
        mp.setitem(sys.modules, "azure.cognitiveservices.speech", sdk)
        yield SimpleNamespace(sdk=sdk, mp=mp)


def _passo(fase: str, trab: Path, saida_dir: Path, *args) -> tuple[int, dict]:
    """Um passo do workflow: a fase com um $GITHUB_OUTPUT novo; devolve o código de saída e as saídas do passo."""
    out = saida_dir / f"out_{fase}_{len(list(saida_dir.glob('out_*')))}.txt"
    out.write_text("", encoding="utf-8")
    os.environ["GITHUB_OUTPUT"] = str(out)
    try:
        rc = (transcrever.main([str(trab / "fala")]) if fase == "transcrever" else corrigir.main([fase, str(trab), *args]))
    finally:
        os.environ.pop("GITHUB_OUTPUT", None)
    linhas = [l.split("=", 1) for l in out.read_text(encoding="utf-8").splitlines() if l]
    assert len({k for k, _ in linhas}) == len(linhas), linhas              # cada saída uma vez só no passo
    return rc, dict(linhas)


def _workflow(trab: Path, saida_dir: Path) -> dict:
    """Os passos na ordem do radar-video.yml, com as mesmas condições (if:) e o continue-on-error da transcrição."""
    saida_dir.mkdir(exist_ok=True)
    r = {}
    r["pegar"] = _passo("pegar", trab, saida_dir)
    pegar = r["pegar"][1]
    if pegar.get("seguir") == "sim":
        r["preparar"] = _passo("preparar", trab, saida_dir)
        if r["preparar"][0] == 0 and r["preparar"][1].get("transcrever") == "sim":
            r["transcrever"] = _passo("transcrever", trab, saida_dir)
        if r["preparar"][0] == 0:
            r["alinhar"] = _passo("alinhar", trab, saida_dir)
            if r["alinhar"][0] == 0:
                r["montar"] = _passo("montar", trab, saida_dir)
    if pegar.get("pedido") == "sim":
        r["entregar"] = _passo("entregar", trab, saida_dir)
    return r


def _log_limpo(texto: str, *extra: str) -> None:
    """Só as linhas do robô (fase, uuid, números e códigos): nada da fala, do roteiro, da cartela, de link, token ou chave."""
    for linha in texto.splitlines():
        assert re.fullmatch(r"corretor: [a-z_]+( [a-z_]+=[^ ]+)*", linha), linha
    for proibido in ("prazo", "eSocial", "social", "gente", "outubro", "Ana", "Artecon", "CNPJ", "http", "token", "assinado.", "envio.",
                     CHAVE, CHAVE_AZURE, ANON[:20], "+00.0000", "Celular", *extra):
        assert proibido not in texto, proibido


# ------------------------------------------------------------------ de ponta a ponta: completo e depois o ajuste (montagem)
@pytest.fixture(scope="module")
def completo(clipes, tmp_path_factory):
    """Um pedido completo, do pegar ao entregar, com a radar-video e a Azure simuladas (um vez por módulo: os testes abaixo olham o
    resultado)."""
    pasta = tmp_path_factory.mktemp("corrigir_completo")
    funcao = FuncaoFalsa(CHAVE, ANON)
    _no_ar(funcao, VID, clipes.c1, clipes.c2, gancho=GANCHO)
    log = io.StringIO()
    try:
        with _ambiente(funcao) as amb, contextlib.redirect_stdout(log):
            passos = _workflow(pasta / "trabalho", pasta / "saidas")
        yield SimpleNamespace(funcao=funcao, trab=pasta / "trabalho", passos=passos, log=log.getvalue(), sdk=amb.sdk, pasta=pasta)
    finally:
        funcao.fechar()


@FFMPEG
def test_completo_do_pegar_ao_entregar(completo):
    f, trab, passos = completo.funcao, completo.trab, completo.passos
    assert {k: v[0] for k, v in passos.items()} == {"pegar": 0, "preparar": 0, "transcrever": 0, "alinhar": 0, "montar": 0, "entregar": 0}
    assert passos["pegar"][1] == {"pedido": "sim", "seguir": "sim", "modo": "completo"} and passos["preparar"][1] == {"transcrever": "sim"}
    # a conversa: pegar, guardar a transcrição (links + PUT), contar os segundos (uma vez), o parcial, os links do vídeo e concluir
    assert f.acoes() == ["pegar", "links", "audio", "parcial", "links", "concluir"]
    chamadas = dict(f.chamadas[1:4])
    assert chamadas["links"] == {"acao": "links", "id": VID, "tentativa": 1, "ler": [], "gravar": [f"trabalho/{VID}/1/palavras.json"]}
    assert chamadas["audio"] == {"acao": "audio", "id": VID, "tentativa": 1, "segundos": round(DUR1 + DUR2, 1)}
    assert f.segundos[VID] == round(DUR1 + DUR2, 1) and f.guardada[VID] == 1
    # a transcrição guardada é a do passo (o ajuste monta com ela, sem transcrever de novo)
    guardada = transcrever.de_json(f.objetos[f"trabalho/{VID}/1/palavras.json"]["dados"])
    assert [w["texto"] for w in guardada["palavras"]] == [p for p, _, _ in CLIPE1 + CLIPE2]
    assert guardada["transcricao"] == {"servico": "azure_f0", "segundos_audio": DUR1 + DUR2, "palavras": PALAVRAS_TODAS}
    # o parcial veio antes da montagem, sem divergência; o final, pronto
    parcial = chamadas["parcial"]["relatorio"]
    assert parcial["parcial"] is True and parcial["divergencias"] == [] and parcial["omitido"] == [] and parcial["fora_do_roteiro"] == []
    fim = f.final[VID]
    rel = fim["relatorio"]
    assert fim["situacao"] == "pronto" and rel["parcial"] is False and rel["texto_final"] == FALA and rel["modo"] == "completo"
    assert rel["transcricao"] == {"servico": "azure_f0", "segundos_audio": DUR1 + DUR2, "palavras": PALAVRAS_TODAS}
    assert rel["entrada"]["clipes"] == 2 and rel["legenda"]["gancho"] is True and rel["conferencia"]["sem_gps"] is True
    assert ("voz_entre_palavras", True) in [(c["tipo"], c.get("automatico")) for c in rel["cortes"]]       # o "ééé" saiu
    # o vídeo no caminho imutável corrigido/<id>/<sha256>.mp4, o sha256 e o tamanho conferidos, e os 4 quadros
    sha = fim["sha256"]
    video = f.objetos[f"corrigido/{VID}/{sha}.mp4"]
    assert hashlib.sha256(video["dados"]).hexdigest() == sha and fim["bytes"] == len(video["dados"]) and video["tipo"] == "video/mp4"
    assert all(f.objetos[f"quadros/{VID}/{sha}/q{k}.jpg"]["tipo"] == "image/jpeg" for k in range(1, 5))
    assert fim["duracao"] == pytest.approx(rel["saida"]["duracao_s"], abs=0.05) and rel["saida"]["lufs"] == pytest.approx(-14, abs=1)
    # todo envio como o uploadToSignedUrl: o tipo, cache de 60 s, sem upsert
    assert len(f.puts) == 6 and all(h["cache-control"] == "max-age=60" and h["x-upsert"] == "false" for _, h in f.puts)
    assert {c: h["content-type"] for c, h in f.puts} == {f"trabalho/{VID}/1/palavras.json": "application/json",
                                                         f"corrigido/{VID}/{sha}.mp4": "video/mp4",
                                                         **{f"quadros/{VID}/{sha}/q{k}.jpg": "image/jpeg" for k in range(1, 5)}}
    assert f.gets == [f"bruto/{VID}/1", f"bruto/{VID}/2"] and f.cabecalhos_ruins == 0
    # a saída no ar: sem o local do celular; cada palavra dos dois clipes com o branco e a voz juntos (até 1 quadro), sem o "ééé"
    (completo.pasta / "no_ar.mp4").write_bytes(video["dados"])
    assert sint.GPS.encode() not in video["dados"] and b"Celular de Teste" not in video["dados"]
    luz = sint.subidas([x > 150 for x in sint.luz_do_alto(completo.pasta / "no_ar.mp4")])
    voz = sint.subidas(sint.voz_por_quadro(completo.pasta / "no_ar.mp4"))
    assert len(luz) == len(voz) == PALAVRAS_TODAS and all(abs(a - b) <= 1 for a, b in zip(luz, voz)), (luz, voz)
    # a Azure simulada: uma transcrição, com a lista de frases (o glossário) e o WAV fora do sai/ (que o ffmpeg alcança)
    assert len(completo.sdk.feitos) == 1 and completo.sdk.feitos[0]["audio"].filename == str(trab / "fala" / "fala16k.wav")
    assert completo.sdk.feitos[0]["frases"][:len(GLOSSARIO)] == GLOSSARIO
    assert not list((trab / "sai").glob("palavras*")) and not (trab / "sai" / "fala16k.wav").exists() and not (trab / "erro.json").exists()


@FFMPEG
def test_completo_log_so_com_fase_uuid_numeros_e_codigos(completo):
    _log_limpo(completo.log)
    fases = [l.split()[1] for l in completo.log.splitlines()]
    assert fases == ["pegar", "preparar", "transcrever", "alinhar", "montar", "entregar"], completo.log
    assert f"corretor: entregar pedido={VID} situacao=pronto" in completo.log.splitlines()


@FFMPEG
def test_ajuste_monta_com_a_transcricao_guardada_sem_azure_e_com_o_mesmo_audio(completo, tmp_path):
    """O ajuste do administrador (modo montagem): a transcrição guardada (trabalho/<id>/1/palavras.json) volta pelo link, o passo da
    transcrição não roda, os segundos não são contados de novo; muda a legenda (compacta, sem o gancho), o áudio é o mesmo, byte a
    byte, e o vídeo novo vai para outro caminho (outro sha256): o anterior nunca é sobrescrito."""
    f = completo.funcao
    antes = f.final[VID]
    f.chamadas.clear()
    f.puts.clear()
    f.gets.clear()
    f.enfileirar(pedido(VID, _partes(f.objetos[f"bruto/{VID}/1"]["dados"], f.objetos[f"bruto/{VID}/2"]["dados"]), FALA, CFG,
                        modo="montagem", cartela=CARTELA, gancho=GANCHO, ajustes={"estilo": "compacta", "sem_gancho": True},
                        palavras_tentativa=1))
    log = io.StringIO()
    with _ambiente(f, sdk_passos=[("erro", "AuthenticationFailure", "não pode ser chamada")]) as amb, contextlib.redirect_stdout(log):
        passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
    assert "transcrever" not in passos and passos["preparar"][1] == {"transcrever": "nao"} and amb.sdk.feitos == []
    assert passos["pegar"][1] == {"pedido": "sim", "seguir": "sim", "modo": "montagem"}
    assert f.acoes() == ["pegar", "parcial", "links", "concluir"] and f.segundos[VID] == round(DUR1 + DUR2, 1)
    assert f.gets == [f"bruto/{VID}/1", f"bruto/{VID}/2", f"trabalho/{VID}/1/palavras.json"]
    novo = f.final[VID]
    assert novo["situacao"] == "pronto" and novo["sha256"] != antes["sha256"] and novo["relatorio"]["modo"] == "montagem"
    assert novo["relatorio"]["legenda"]["estilo"] == "compacta" and novo["relatorio"]["legenda"]["gancho"] is False
    assert f"corrigido/{VID}/{antes['sha256']}.mp4" in f.objetos and f"corrigido/{VID}/{novo['sha256']}.mp4" in f.objetos
    md5 = []
    for sha in (antes["sha256"], novo["sha256"]):
        (tmp_path / f"{sha}.mp4").write_bytes(f.objetos[f"corrigido/{VID}/{sha}.mp4"]["dados"])
        md5.append(subprocess.run(["ffmpeg", "-v", "error", "-i", str(tmp_path / f"{sha}.mp4"), "-map", "0:a", "-c", "copy", "-f", "md5", "-"],
                                  capture_output=True, text=True, check=True).stdout)
    assert md5[0] == md5[1]
    _log_limpo(log.getvalue())


def _montagem_do_editor(f: FuncaoFalsa, ajustes: dict) -> dict:
    """O pedido "montagem" com as mudanças do editor da aba Vídeo (a transcrição guardada da rodada 1)."""
    f.chamadas.clear()
    f.puts.clear()
    f.gets.clear()
    p = pedido(VID, _partes(f.objetos[f"bruto/{VID}/1"]["dados"], f.objetos[f"bruto/{VID}/2"]["dados"]), FALA, CFG, modo="montagem",
               cartela=CARTELA, gancho=GANCHO, ajustes=ajustes, palavras_tentativa=1)
    f.enfileirar(p)
    return p


@FFMPEG
def test_editor_monta_sem_transcrever_com_cortes_capa_estilo_e_cartela_propria(completo, tmp_path):
    """v0.33.0, a aba Vídeo: o administrador corta "do e social" (do meio do vão antes ao meio do vão depois, em quadros da linha
    original), termina antes de "gente", escolhe a capa e a legenda grande, em cima e amarela, e um texto extra só desta cartela. O
    robô monta com a transcrição guardada (a Azure não é chamada, os segundos não mudam), sobe a capa ao lado dos quadros, e o
    relatório leva o mapa, as unidades, a edição e a capa; no vídeo, cada palavra que ficou com o branco e a voz juntos (sem as
    cortadas) e a duração bate com a estimativa da tela e do banco."""
    f = completo.funcao
    q = lambda s: round(s * 30)
    desloca = int(DUR1 * 30)                                     # o clipe 2 na linha original (fala48k.wav)
    corte = [math.floor((1.10 + 1.22) / 2 * 30) + 1, math.ceil((2.10 + 2.22) / 2 * 30) - 1]       # [35, 64]: "do", "e", "social"
    fim_q = desloca + math.floor((1.52 + 1.65) / 2 * 30)         # entre "a" e "gente"
    ajustes = {"cortar": [corte], "fim_q": fim_q, "capa_q": q(0.9), "legenda_tamanho": "G", "legenda_posicao": "cima",
               "legenda_cor": "amarelo", "cartela_extra": "Texto extra de teste"}
    mapa = f.final[VID]["relatorio"]["mapa"]
    estimada = cortes.duracao_estimada(mapa, ajustes, CFG["cartela_s"])
    _montagem_do_editor(f, ajustes)
    log = io.StringIO()
    with _ambiente(f, sdk_passos=[("erro", "AuthenticationFailure", "não pode ser chamada")]) as amb, contextlib.redirect_stdout(log):
        passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
    assert "transcrever" not in passos and amb.sdk.feitos == [] and passos["pegar"][1]["modo"] == "montagem"
    assert f.acoes() == ["pegar", "parcial", "links", "concluir"] and f.segundos[VID] == round(DUR1 + DUR2, 1)
    fim = f.final[VID]
    rel, sha = fim["relatorio"], fim["sha256"]
    assert fim["situacao"] == "pronto" and rel["modo"] == "montagem"
    capa = f"quadros/{VID}/{sha}/capa-{rel['capa']['sha256']}.jpg"                     # o sha256 da capa no nome
    assert capa in [c for c, _ in f.puts] and f.objetos[capa]["tipo"] == "image/jpeg"
    assert hashlib.sha256(f.objetos[capa]["dados"]).hexdigest() == rel["capa"]["sha256"]
    assert rel["edicao"] == {"versao": 1, "cortes": 1, "inicio_cortado_s": 0, "fim_cortado_s": rel["edicao"]["fim_cortado_s"], "tamanho": "G",
                             "posicao": "cima", "cor": "amarelo", "cartela_extra_propria": True} and rel["edicao"]["fim_cortado_s"] > 0.5
    assert rel["capa"] == {"q": q(0.9), "em_ms": rel["capa"]["em_ms"], "movida": False, "sha256": rel["capa"]["sha256"]} and 0 < rel["capa"]["em_ms"] < 1000
    assert rel["cartela_extra"] == "Texto extra de teste" and rel["legenda"]["blocos"] >= 1
    assert rel["mapa"]["linha_q"] == mapa["linha_q"] and rel["mapa"]["faixas"] == mapa["faixas"]
    assert [c["chave"] for c in rel["cortes"] if c["tipo"] == "editor"] == [f"e:{corte[0]}"]
    assert "eSocial" not in rel["texto_final"] and "gente" not in rel["texto_final"] and rel["texto_final"].startswith("O prazo vence")
    assert [u["t"] for u in rel["unidades"]][:3] == ["O", "prazo", "vence"]
    # o vídeo: as palavras que ficaram (7 do clipe 1 e 3 do clipe 2), cada uma com o branco e a voz juntos; a duração estimada
    (tmp_path / "editado.mp4").write_bytes(f.objetos[f"corrigido/{VID}/{sha}.mp4"]["dados"])
    luz = sint.subidas([x > 150 for x in sint.luz_do_alto(tmp_path / "editado.mp4")])
    voz = sint.subidas(sint.voz_por_quadro(tmp_path / "editado.mp4"))
    assert len(luz) == len(voz) == 10 and all(abs(a - b) <= 1 for a, b in zip(luz, voz)), (luz, voz)
    assert fim["duracao"] == pytest.approx(estimada, abs=1 / 30 + 0.05)                     # a estimativa (arredondada a 0,1 s) é a real
    ass = (tmp_path / "trabalho" / "sai" / "legenda.ass").read_text(encoding="utf-8")
    assert "Style: Fala,DM Sans,80,&H00481F01,&H00481F01,&H3300D7FF," in ass and ",8,100,100,300,1" in ass
    # a capa: o quadro do "prazo" (o alto branco), sem a legenda
    (tmp_path / "capa.jpg").write_bytes(f.objetos[capa]["dados"])
    from PIL import Image
    im = Image.open(tmp_path / "capa.jpg").convert("L")
    assert im.size == (1080, 1920) and sum(im.crop((0, 100, 1080, 500)).resize((8, 8)).tobytes()) / 64 > 150
    _log_limpo(log.getvalue(), "Texto extra")
    assert " cortes_editor=1" in log.getvalue() and " capa=sim" in log.getvalue()


SQL_DURACAO = """select radar_video_edicao_duracao(v, %s::jsonb), radar_video_edicao_falta(v, %s::jsonb)
                   from jsonb_populate_record(null::radar_videos, jsonb_build_object('relatorio', %s::jsonb)) v"""


@FFMPEG
def test_duracao_estimada_e_a_do_video_montado(completo, db, tmp_path):
    """A duração que o banco (e a tela e o robô: a mesma conta) estima e confere entre 5 e 45 s é a do vídeo que o robô monta de
    verdade: sem o fim marcado (a faixa já tem a folga depois da última palavra: nada de somar 0,45 s), com o começo marcado no 2º clipe
    (o vídeo de 4,7 s é recusado antes de montar) e com o fim no meio do "gente" (o último quadro parado: o pad). Até 1 quadro."""
    f = completo.funcao
    mapa = f.final[VID]["relatorio"]["mapa"]                     # a linha, as faixas, os automáticos e as palavras não mudam com a edição
    assert len(mapa["palavras"]) == PALAVRAS_TODAS
    desloca = int(DUR1 * 30)
    rel = json.dumps({"mapa": mapa})
    for k, (aj, falta) in enumerate([({}, None), ({"inicio_q": desloca}, "o vídeo ficaria com cerca de 4,7 s: o mínimo é 5 s"),
                                     ({"fim_q": desloca + round(1.9 * 30)}, None)]):
        banco, motivo = db.execute(SQL_DURACAO, (json.dumps(aj), json.dumps(aj), rel)).fetchone()
        assert float(banco) == cortes.duracao_estimada(mapa, aj, CFG["cartela_s"]) and motivo == falta, (aj, banco, motivo)
        _montagem_do_editor(f, aj)
        with _ambiente(f, sdk_passos=[]), contextlib.redirect_stdout(io.StringIO()):
            _workflow(tmp_path / f"t{k}", tmp_path / f"s{k}")
        fim = f.final[VID]
        assert fim["situacao"] == "pronto", fim
        real = fim["duracao"]
        assert real == pytest.approx(cortes.estimada_q(mapa, aj) / 30 + CFG["cartela_s"] - 0.4, abs=1 / 30 + 0.005), (aj, real)
        assert float(banco) == pytest.approx(real, abs=0.05 + 1 / 30), (aj, banco, real)
        assert (fim["relatorio"]["mapa"]["pad_q"] == 0) == (k < 2), (aj, fim["relatorio"]["mapa"]["pad_q"])


@FFMPEG
def test_trocar_so_a_capa_sobe_a_capa_nova_do_mesmo_video(completo, tmp_path):
    """Trocar SÓ a capa monta o mesmo vídeo (o mesmo sha256): o vídeo já está no armazenamento ("ja_existe") e o armazenamento nunca
    sobrescreve. A capa sobe com o sha256 dela no nome: a nova fica ao lado da de antes, o relatório aponta a nova e o concluir confere
    a nova (a de antes não passa por ela). Voltar à capa de antes reaproveita o arquivo que já está lá (o mesmo conteúdo)."""
    f = completo.funcao
    feitas = []
    for k, capa_q in enumerate((27, 65, 27)):
        _montagem_do_editor(f, {"capa_q": capa_q})
        with _ambiente(f, sdk_passos=[]), contextlib.redirect_stdout(io.StringIO()):
            _workflow(tmp_path / f"t{k}", tmp_path / f"s{k}")
        fim = f.final[VID]
        assert fim["situacao"] == "pronto" and fim["relatorio"]["capa"]["q"] == capa_q
        local = (tmp_path / f"t{k}" / "sai" / "capa.jpg").read_bytes()
        nome = f"quadros/{VID}/{fim['sha256']}/capa-{fim['relatorio']['capa']['sha256']}.jpg"
        assert hashlib.sha256(local).hexdigest() == fim["relatorio"]["capa"]["sha256"]
        assert f.objetos[nome]["dados"] == local                                   # a capa guardada é a que o robô fez agora
        feitas.append((fim["sha256"], nome, [c for c, _ in f.puts]))
    (sha_a, capa_a, _), (sha_b, capa_b, puts_b), (sha_c, capa_c, puts_c) = feitas
    assert sha_a == sha_b == sha_c and capa_a != capa_b and capa_c == capa_a       # o mesmo vídeo; a capa nova, depois a de antes de volta
    assert capa_b in puts_b and f"corrigido/{VID}/{sha_b}.mp4" not in puts_b       # o vídeo não sobe de novo; a capa nova, sim
    assert capa_a in puts_c and capa_a in f.objetos and capa_b in f.objetos         # a de antes: o PUT encontra o mesmo arquivo (não sobrescreve)


@FFMPEG
def test_corte_do_editor_que_deixa_menos_de_2_s_para_com_edicao_curta(completo, tmp_path):
    f = completo.funcao
    _montagem_do_editor(f, {"inicio_q": 20, "fim_q": 60})
    with _ambiente(f, sdk_passos=[]):
        passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
    assert passos["alinhar"][0] == 0 and f.acoes() == ["pegar", "falhar"] and f.puts == []
    assert f.final[VID] == {"situacao": "erro", "codigo": "edicao_curta"}


@FFMPEG
def test_de_ponta_a_ponta_com_o_ffmpeg_no_conteiner(imagem_docker, tmp_path, clipes):
    """Como no runner: todo ffmpeg no contêiner (sem rede, sem ambiente, só leitura, usuário 1001). O WAV que o contêiner gravou em sai/
    vai para fala/ (fora do alcance dele) antes da transcrição, e o vídeo que ele montou é conferido, sobe e conclui."""
    f = _funcao()
    try:
        _no_ar(f, VID, clipes.c2, partes=_partes(clipes.c2, tipos=("video/quicktime",)), fala="Fale com a gente.")
        sdk = [("ok", [frase_sdk("Fale com a gente.", [(p, a, b, 0.9) for p, a, b in CLIPE2])])]
        with _ambiente(f, sdk_passos=sdk, RADAR_VIDEO_ISOLADO="docker") as amb:
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert {k: x[0] for k, x in passos.items()} == {"pegar": 0, "preparar": 0, "transcrever": 0, "alinhar": 0, "montar": 0, "entregar": 0}
        fim = f.final[VID]
        assert fim["situacao"] == "pronto" and fim["relatorio"]["texto_final"] == "Fale com a gente." and len(amb.sdk.feitos) == 1
        assert hashlib.sha256(f.objetos[f"corrigido/{VID}/{fim['sha256']}.mp4"]["dados"]).hexdigest() == fim["sha256"]
        assert (tmp_path / "trabalho" / "fala" / "fala16k.wav").is_file() and not (tmp_path / "trabalho" / "sai" / "fala16k.wav").exists()
    finally:
        f.fechar()


# ------------------------------------------------------------------ recusas e falhas: o código fixo vai pelo entregar
def _funcao():
    return FuncaoFalsa(CHAVE, ANON)


@FFMPEG
def test_sem_pedido_e_chave_recusada(tmp_path, capfd):
    f = _funcao()
    try:
        with _ambiente(f):
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert passos == {"pegar": (0, {"pedido": "nao", "seguir": "nao"})} and f.acoes() == ["pegar"]
        assert not (tmp_path / "trabalho").exists()
        assert capfd.readouterr() == ("corretor: pegar fila=vazia\n", "")
        _no_ar(f, VID, b"\x00" * 10)
        with _ambiente(f, RADAR_VIDEO_ROBO_CHAVE="outra" + "0" * 40):
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        # a chave errada: o job fica vermelho (configuração), nada é baixado e o entregar não roda
        assert passos == {"pegar": (1, {"pedido": "nao", "seguir": "nao"})} and f.cabecalhos_ruins == 1 and f.fila
        assert capfd.readouterr() == ("corretor: pegar erro=robo_chave\n", "")
        with _ambiente(f, RADAR_VIDEO_ROBO_CHAVE="chave com espaço e quebra\nx-outro: 1" + "0" * 30):
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert passos["pegar"][0] == 1 and f.cabecalhos_ruins == 1                      # nem chega a chamar
        assert capfd.readouterr() == ("corretor: pegar erro=robo_sem_chave\n", "")
    finally:
        f.fechar()


@FFMPEG
def test_clipe_sem_audio_e_link_vencido(tmp_path, clipes, capfd):
    """O 1º link de leitura falha (venceu): o robô pede outro e baixa. O clipe sem áudio é recusado no preparar: nada vai para a Azure,
    os segundos não contam, e o entregar manda o código sem_audio."""
    f = _funcao()
    try:
        _no_ar(f, VID, clipes.mudo)
        f.falhas[f"get:bruto/{VID}/1"] = [(400, "expirado")]
        with _ambiente(f) as amb:
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert passos["preparar"] == (0, {"transcrever": "nao"}) and "transcrever" not in passos
        assert passos["alinhar"][0] == passos["montar"][0] == passos["entregar"][0] == 0
        assert f.acoes() == ["pegar", "links", "falhar"] and f.chamadas[1][1]["ler"] == [f"bruto/{VID}/1"]
        assert f.final[VID] == {"situacao": "erro", "codigo": "sem_audio"} and amb.sdk.feitos == [] and VID not in f.segundos
        log = capfd.readouterr()
        assert log.err == "" and f"corretor: preparar pedido={VID} erro=sem_audio em=sondar" in log.out.splitlines()
        assert f"corretor: entregar pedido={VID} erro=sem_audio situacao=erro" in log.out.splitlines()
        _log_limpo(log.out)
    finally:
        f.fechar()


@FFMPEG
def test_clipe_maior_que_o_declarado_nao_e_baixado_inteiro(tmp_path, clipes):
    f = _funcao()
    try:
        _no_ar(f, VID, clipes.c1, partes=[{"n": 1, "tipo": "video/mp4", "bytes": len(clipes.c1) - 1}])
        with _ambiente(f):
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert passos["pegar"] == (0, {"pedido": "sim", "seguir": "nao"}) and set(passos) == {"pegar", "entregar"}
        assert f.final[VID]["codigo"] == "arquivo_grande" and f.acoes() == ["pegar", "falhar"]
        assert not (tmp_path / "trabalho" / "ent" / "1").exists()
    finally:
        f.fechar()


@FFMPEG
def test_erro_da_transcricao_vai_pelo_entregar_sem_contar_segundos(tmp_path, clipes, capfd):
    f = _funcao()
    try:
        _no_ar(f, VID, clipes.c2, partes=_partes(clipes.c2, tipos=("video/quicktime",)))
        d401 = "WebSocket upgrade failed: Authentication error (401). SessionId: x"
        with _ambiente(f, sdk_passos=[("erro", "AuthenticationFailure", d401)]) as amb:
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert passos["transcrever"][0] == 1 and passos["alinhar"][0] == passos["montar"][0] == passos["entregar"][0] == 0
        assert len(amb.sdk.feitos) == 1 and f.acoes() == ["pegar", "falhar"] and f.final[VID]["codigo"] == "azure_chave"
        assert VID not in f.segundos and not any(k.startswith("trabalho/") for k in f.objetos)
        _log_limpo(capfd.readouterr().out, d401)
    finally:
        f.fechar()


@FFMPEG
def test_transcricao_vazia_corta_so_pelos_silencios_e_pede_regravar(tmp_path, clipes):
    """A Azure não devolveu nenhuma palavra (o áudio tinha voz): o robô não para com sem_fala — corta só pelos silêncios (a reserva),
    monta e entrega; a legenda fica vazia, o relatório avisa transcricao_vazia e o roteiro inteiro sai como divergência (regravar)."""
    f = _funcao()
    try:
        _no_ar(f, VID, clipes.c2, partes=_partes(clipes.c2, tipos=("video/quicktime",)))
        with _ambiente(f, sdk_passos=[("ok", [])]):
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert {k: x[0] for k, x in passos.items()} == {"pegar": 0, "preparar": 0, "transcrever": 0, "alinhar": 0, "montar": 0, "entregar": 0}
        assert f.acoes() == ["pegar", "links", "audio", "parcial", "links", "concluir"]
        fim = f.final[VID]
        rel = fim["relatorio"]
        assert fim["situacao"] == "regravar" and "transcricao_vazia" in rel["avisos"] and rel["texto_final"] == ""
        assert rel["divergencias"] and rel["legenda"]["blocos"] == 0 and rel["transcricao"]["palavras"] == 0
        assert [c["tipo"] for c in rel["cortes"]] == ["inicio", "fim"] and rel["saida"]["fala_s"] < DUR2       # pelos silêncios
    finally:
        f.fechar()


@FFMPEG
def test_pedido_que_nao_e_mais_do_robo_para_sem_registrar(tmp_path, clipes):
    """O ajuste ou a nova gravação chegou durante o trabalho (RADAR316): o robô para sem montar e não manda falhar (não é mais dele)."""
    f = _funcao()
    try:
        _no_ar(f, VID, clipes.c2, partes=_partes(clipes.c2, tipos=("video/quicktime",)))
        f.falhas["parcial"] = [(400, PERDIDO)]
        with _ambiente(f):
            passos = _workflow(tmp_path / "trabalho", tmp_path / "saidas")
        assert passos["alinhar"][0] == passos["montar"][0] == passos["entregar"][0] == 0
        assert f.acoes() == ["pegar", "links", "audio", "parcial"] and VID not in f.final
        assert json.loads((tmp_path / "trabalho" / "erro.json").read_text())["codigo"] == "pedido_perdido"
        assert not (tmp_path / "trabalho" / "sai" / "reel.mp4").exists()
    finally:
        f.fechar()


def _entregar_de_novo(completo, tmp_path, f: FuncaoFalsa, **extra):
    """Só o passo entregar, sobre uma cópia do trabalho já montado (o pedido de novo com o robô, na rodada 1)."""
    trab = tmp_path / "trabalho"
    shutil.copytree(completo.trab, trab)
    f.pedidos[VID] = completo.funcao.pedidos[VID]
    f.rodadas[VID] = 1
    f.em_curso = (VID, 1)
    with _ambiente(f, **extra):
        return _passo("entregar", trab, tmp_path), trab


@FFMPEG
def test_entregar_falha_do_armazenamento_volta_a_fila(completo, tmp_path):
    f = _funcao()
    try:
        f.falhas["put:corrigido/"] = [(500, "fora")] * 3
        (rc, _), _ = _entregar_de_novo(completo, tmp_path, f)
        assert rc == 0 and f.acoes() == ["links", "falhar"] and f.final[VID] == {"situacao": "na_fila", "codigo": "storage"}
        assert len([c for c, _ in f.puts if c.startswith("corrigido/")]) == 3                  # 3 tentativas, depois o código
    finally:
        f.fechar()


@FFMPEG
def test_entregar_video_acima_do_limite_do_armazenamento_para_com_o_codigo_proprio(completo, tmp_path):
    """O vídeo corrigido maior que o limite de arquivo do projeto (no Free do Supabase, 50 MB): o armazenamento responde 413. Tentar de
    novo não adianta: o robô para com "limite_armazenamento" na primeira (um aviso só, que cita o limite do plano), em vez de "storage",
    que voltaria à fila três vezes, montaria o mesmo arquivo e pararia com "o armazenamento não respondeu"."""
    f = _funcao()
    try:
        f.falhas["put:corrigido/"] = [(413, "The object exceeded the maximum allowed size")] * 3
        (rc, _), _ = _entregar_de_novo(completo, tmp_path, f)
        assert rc == 0 and f.acoes() == ["links", "falhar"] and f.final[VID] == {"situacao": "erro", "codigo": "limite_armazenamento"}
        assert len([c for c, _ in f.puts if c.startswith("corrigido/")]) == 1
    finally:
        f.fechar()
    assert conversa._grande_demais(400, b'{"statusCode": "413", "error": "Payload too large"}')
    assert not conversa._grande_demais(400, b'{"statusCode": "409", "error": "Duplicate"}') and not conversa._grande_demais(500, b"")


@FFMPEG
def test_entregar_de_novo_com_o_mesmo_video_ja_no_armazenamento(completo, tmp_path):
    """Uma rodada anterior subiu o vídeo (o mesmo sha256) e parou antes de concluir: os links recusam o corrigido (nunca se
    sobrescreve), sobem só os quadros (o que já estava lá fica) e o concluir confere o que está no armazenamento."""
    f = _funcao()
    try:
        r = json.loads((completo.trab / "resultado.json").read_text())
        sha = r["sha256"]
        f.guardar(f"corrigido/{VID}/{sha}.mp4", (completo.trab / "sai" / "reel.mp4").read_bytes())
        f.guardar(f"quadros/{VID}/{sha}/q1.jpg", (completo.trab / "sai" / "q1.jpg").read_bytes(), "image/jpeg")
        (rc, _), _ = _entregar_de_novo(completo, tmp_path, f)
        assert rc == 0 and f.acoes() == ["links", "links", "concluir"] and f.final[VID]["situacao"] == "pronto"
        assert f.chamadas[1][1]["gravar"] == [f"quadros/{VID}/{sha}/q{k}.jpg" for k in range(1, 5)]
        assert [c for c, _ in f.puts] == [f"quadros/{VID}/{sha}/q{k}.jpg" for k in range(1, 5)]
    finally:
        f.fechar()


@FFMPEG
def test_entregar_sem_resultado_cancelado_ou_runner_e_video_mexido(completo, tmp_path):
    """Sem resultado e sem código: o job cancelado (tempo esgotado) dá tempo_esgotado; o runner que falhou fora do robô (a imagem do
    ffmpeg, o pip) dá github, que volta à fila; o vídeo que mudou depois da conferência não sobe (erro_interno)."""
    for n, (job, codigo, situacao) in enumerate((("cancelled", "tempo_esgotado", "erro"), ("failure", "github", "na_fila"))):
        f = _funcao()
        try:
            trab = tmp_path / str(n) / "trabalho"
            shutil.copytree(completo.trab, trab)
            (trab / "resultado.json").unlink()
            f.pedidos[VID], f.rodadas[VID], f.em_curso = completo.funcao.pedidos[VID], 1, (VID, 1)
            with _ambiente(f, RADAR_VIDEO_JOB=job):
                rc, _ = _passo("entregar", trab, tmp_path / str(n))
            assert rc == 0 and f.acoes() == ["falhar"] and f.final[VID] == {"situacao": situacao, "codigo": codigo}
        finally:
            f.fechar()
    f = _funcao()
    try:
        trab = tmp_path / "mexido" / "trabalho"
        shutil.copytree(completo.trab, trab)
        with (trab / "sai" / "reel.mp4").open("ab") as v:
            v.write(b"\x00")
        f.pedidos[VID], f.rodadas[VID], f.em_curso = completo.funcao.pedidos[VID], 1, (VID, 1)
        with _ambiente(f):
            rc, _ = _passo("entregar", trab, tmp_path / "mexido")
        assert rc == 0 and f.acoes() == ["falhar"] and f.final[VID]["codigo"] == "erro_interno" and f.puts == []
    finally:
        f.fechar()


# ------------------------------------------------------------------ conversa.py: só a radar-video, só os links do pedido
def test_conversa_so_fala_com_a_radar_video_do_projeto():
    assert REF == "jhxlsvzvqvufyhkjnmeq" and conversa._jwt(ANON)["role"] == "anon"
    certo = f"https://{REF}.supabase.co/functions/v1/radar-video"
    conversa.Conversa(certo, CHAVE, ANON, REF)
    for url in ("http://jhxlsvzvqvufyhkjnmeq.supabase.co/functions/v1/radar-video", f"https://{REF}.supabase.co/functions/v1/radar-redes",
                f"https://{REF}.supabase.co.exemplo.com/functions/v1/radar-video", "https://abcdefghijabcdefghij.supabase.co/functions/v1/radar-video",
                f"https://{REF}.supabase.co/functions/v1/radar-video?x=1", "http://localhost:3000/", "http://127.0.0.1.exemplo.com:80/", ""):
        with pytest.raises(ErroVideo) as e:
            conversa.Conversa(url, CHAVE, ANON, REF)
        assert e.value.codigo == "robo_config", url
    for chave in ("", "curta", CHAVE + "\n", "a b" * 20, CHAVE[:-1] + "-"):
        with pytest.raises(ErroVideo) as e:
            conversa.Conversa(certo, chave, ANON, REF)
        assert e.value.codigo == "robo_sem_chave"
    servico = ANON.split(".")
    papel = conversa.base64.urlsafe_b64encode(json.dumps({"role": "service_role", "ref": REF}).encode()).decode().rstrip("=")
    with pytest.raises(ErroVideo):
        conversa.Conversa(certo, CHAVE, f"{servico[0]}.{papel}.{servico[2]}", REF)
    c = conversa.Conversa(certo, CHAVE, ANON, REF)
    assert CHAVE not in repr(c) and CHAVE not in str(c)
    with pytest.raises(ErroVideo):
        conversa.anon_do_config(Path("/nao/existe/radar-config.js"))


def test_conversa_aceita_a_chave_publica_nova_so_no_apikey(tmp_path):
    """Rodada 2 da varredura geral: o Supabase desliga a chave anon antiga (JWT) até o fim de 2026. A nova (sb_publishable_…) vale no
    radar-config.js e vai só no apikey (no Authorization o Supabase recusa: não é JWT); o projeto é o de SUPABASE_URL. A anon antiga
    continua indo nos dois cabeçalhos. A chave interna (sb_secret_… ou o JWT service_role) nunca vale."""
    nova = "sb_publishable_" + "AbC9_-" * 6
    certo = f"https://{REF}.supabase.co/functions/v1/radar-video"
    assert conversa.cabecalhos_publicos(nova) == {"apikey": nova}
    assert conversa.cabecalhos_publicos(ANON) == {"apikey": ANON, "Authorization": "Bearer " + ANON}
    conversa.Conversa(certo, CHAVE, nova, REF)
    for ruim in ("sb_secret_" + "x" * 30, "sb_publishable_curta", "sb_publishable_" + "x" * 20 + "\n", "qualquer-coisa"):
        with pytest.raises(ErroVideo):
            conversa.Conversa(certo, CHAVE, ruim, REF)
    config = tmp_path / "radar-config.js"
    config.write_text(f'window.RADAR_CONFIG = {{SUPABASE_URL: "https://{REF}.supabase.co", SUPABASE_ANON_KEY: "{nova}"}};')
    assert conversa.anon_do_config(config) == (nova, REF)
    outro = conversa.base64.urlsafe_b64encode(json.dumps({"role": "anon", "ref": "abcdefghijabcdefghij"}).encode()).decode().rstrip("=")
    config.write_text(f'window.RADAR_CONFIG = {{SUPABASE_URL: "https://{REF}.supabase.co", SUPABASE_ANON_KEY: "x.{outro}.y"}};')
    with pytest.raises(ErroVideo):                                                    # a anon antiga de outro projeto, não
        conversa.anon_do_config(config)


class _Outro(BaseHTTPRequestHandler):
    """Um servidor que não deveria receber nada (o destino de um redirecionamento ou de um link adulterado)."""
    recebidos: list = []

    def do_GET(self):
        _Outro.recebidos.append((self.command, self.path, dict(self.headers)))
        self.send_response(200)
        self.end_headers()

    do_POST = do_PUT = do_GET

    def log_message(self, *a):
        pass


class _Redireciona(BaseHTTPRequestHandler):
    destino = ""

    def do_POST(self):
        self.send_response(307)
        self.send_header("Location", _Redireciona.destino)
        self.end_headers()

    do_GET = do_PUT = do_POST

    def log_message(self, *a):
        pass


@pytest.fixture()
def outros():
    servidores = [ThreadingHTTPServer(("127.0.0.1", 0), h) for h in (_Outro, _Redireciona)]
    for s in servidores:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    _Outro.recebidos = []
    _Redireciona.destino = f"http://127.0.0.1:{servidores[0].server_address[1]}/roubar"
    yield SimpleNamespace(outro=f"http://127.0.0.1:{servidores[0].server_address[1]}",
                          redireciona=f"http://127.0.0.1:{servidores[1].server_address[1]}")
    for s in servidores:
        s.shutdown()
        s.server_close()


def test_conversa_nao_segue_redirecionamento_nem_proxy_nem_link_de_fora(monkeypatch, outros, tmp_path):
    monkeypatch.setattr(conversa, "_dormir", lambda s: None)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(k, "http://127.0.0.1:9")         # um proxy morto: a conversa não pode usar o do ambiente
    for k in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(k, raising=False)
    # a função redireciona (307 repete o POST com o corpo): a chave nunca vai ao outro endereço
    with pytest.raises(ErroVideo) as e:
        conversa.Conversa(outros.redireciona + "/functions/v1/radar-video", CHAVE, ANON).pegar()
    assert e.value.codigo == "robo_recusado" and _Outro.recebidos == []
    f = _funcao()
    try:
        c = conversa.Conversa(f.url, CHAVE, ANON)
        assert c.pegar() is None                                # passa sem o proxy morto
        # links de fora do pedido ou de outro lugar: recusados antes de abrir
        p = pedido(VID, [{"n": 1, "tipo": "video/mp4", "bytes": 10}], FALA, CFG)
        f.enfileirar(p)
        f.guardar(f"bruto/{VID}/1", b"0123456789")
        r = c.pegar()
        assert r["partes"][0]["url"].startswith(f.base + f"/storage/v1/object/sign/radar-videos/bruto/{VID}/1?token=")
        token = r["partes"][0]["url"].split("token=")[1]
        for url, caminho in ((f"{outros.outro}/storage/v1/object/sign/radar-videos/bruto/{VID}/1?token={token}".replace("127.0.0.1", "localhost"),
                              f"bruto/{VID}/1"),
                             (f"{f.base}/storage/v1/object/sign/radar-videos/bruto/{VID}/2?token={token}", f"bruto/{VID}/1"),
                             (f"{f.base}/storage/v1/object/sign/radar-videos/bruto/{VID}/1?token={token}&redirect=http://x", f"bruto/{VID}/1"),
                             (f"{f.base}/storage/v1/object/sign/radar-videos/bruto/{VID}/1", f"bruto/{VID}/1"),
                             (f"{f.base}/storage/v1/object/sign/outro-bucket/bruto/{VID}/1?token={token}", f"bruto/{VID}/1"),
                             (f"{f.base}/storage/v1/object/sign/radar-videos/bruto/{VID}/1?token={token}", f"bruto/{VID}/../1")):
            with pytest.raises(ErroVideo) as e:
                c._link(url, caminho)
            assert e.value.codigo == "resposta_invalida", url
        with pytest.raises(ErroVideo):
            c._link(r["partes"][0]["url"], f"bruto/{VID}/1", gravar=True)       # um link de ler não serve para gravar
        assert c.baixar(r["partes"][0]["url"], tmp_path / "1", 10) == 10 and (tmp_path / "1").read_bytes() == b"0123456789"
        # o armazenamento que redireciona: o arquivo não é baixado de outro lugar
        with pytest.raises(ErroVideo) as e:
            c.baixar(outros.redireciona + "/x", tmp_path / "2", 10)
        assert e.value.codigo == "storage" and not (tmp_path / "2").exists() and _Outro.recebidos == []
        with pytest.raises(ErroVideo) as e:
            c.baixar(r["partes"][0]["url"], tmp_path / "3", 9)                     # maior que o declarado
        assert e.value.codigo == "arquivo_grande" and not (tmp_path / "3").exists()
        # a função responde de um jeito estranho: nada de exceção encadeada, nem a mensagem dela
        f.falhas["falhar"] = [(500, "Erro com " + CHAVE)] * 3
        with pytest.raises(ErroVideo) as e:
            c.falhar(VID, 1, "sem_audio")
        assert e.value.codigo == "storage" and e.value.__cause__ is None and e.value.__context__ is None and CHAVE not in str(e.value)
        assert f.acoes()[-3:] == ["falhar"] * 3                                     # tentou 3 vezes
        # o audio que falhou no caminho repete (o banco soma uma vez por rodada): o áudio já foi para a Azure e conta na cota do mês
        f.falhas["audio"] = [(502, "fora")]
        antes = f.segundos.get(VID, 0)
        assert c.audio(VID, 1, 9.0)["restante_s"] == 3600 - antes - 9.0
        assert f.acoes()[-2:] == ["audio", "audio"] and f.segundos[VID] == antes + 9.0
        assert c.audio(VID, 1, 9.0) and f.segundos[VID] == antes + 9.0                  # a mesma rodada não conta de novo
    finally:
        f.fechar()


# ------------------------------------------------------------------ os passos com a chave: python -I, só a biblioteca padrão
def _modulos(stderr: str) -> set[str]:
    """Os módulos carregados (python -X importtime escreve um por linha no stderr, depois do cabeçalho). A tentativa que a própria
    biblioteca padrão faz de um módulo que não existe (o copy procura org.python.core, do Jython) não conta."""
    nomes = {l.split("|")[-1].strip().split(".")[0] for l in stderr.splitlines() if re.match(r"import time:\s+\d+ \|", l)}
    return {n for n in nomes if importlib.util.find_spec(n) is not None}


@FFMPEG
def test_passos_com_a_chave_rodam_com_python_I_so_com_a_biblioteca_padrao(tmp_path, clipes):
    """pegar, alinhar e entregar rodam como no workflow (python -I, só com RADAR_VIDEO_URL e a chave no ambiente) e não carregam o
    Pillow, o SDK da Azure nem outra biblioteca de fora; a saída é só a linha do robô."""
    f = _funcao()
    trab = tmp_path / "trabalho"
    # a biblioteca padrão, o código daqui e o que o próprio Python carrega ao abrir (os .pth do site-packages dele)
    abrir = subprocess.run([sys.executable, "-I", "-X", "importtime", "-c", "pass"], capture_output=True, text=True).stderr
    padrao = set(sys.stdlib_module_names) | set(sys.builtin_module_names) | _modulos(abrir) | {
        "segredo", "conversa", "corrigir", "alinhar", "cortes", "numeros", "relatorio", "sondar", "isolado", "transcrever"}

    def com_a_chave(fase, **amb):
        out = tmp_path / f"out_{fase}"
        out.write_text("")
        r = subprocess.run([sys.executable, "-I", "-X", "importtime", str(ROBO / "corrigir.py"), fase, str(trab)], capture_output=True,
                           text=True, timeout=120, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "RADAR_VIDEO_URL": f.url,
                                                        "RADAR_VIDEO_ROBO_CHAVE": CHAVE, "GITHUB_OUTPUT": str(out), **amb})
        fora = _modulos(r.stderr) - padrao
        assert fora == set(), (fase, fora)
        assert [l for l in r.stderr.splitlines() if not l.startswith("import time:")] == [], fase
        return r.returncode, r.stdout, out.read_text()

    try:
        _no_ar(f, VID, clipes.c2, partes=_partes(clipes.c2, tipos=("video/quicktime",)))
        rc, saida, out = com_a_chave("pegar")
        assert rc == 0 and out == "pedido=sim\nseguir=sim\nmodo=completo\n"
        assert re.fullmatch(rf"corretor: pegar pedido={VID} modo=completo rodada=1 clipes=1 mb=0\.\d\d\n", saida), saida
        with _ambiente(f, sdk_passos=[("ok", [frase_sdk("Fale com a gente.", [(p, a, b, 0.9) for p, a, b in CLIPE2])])]):
            assert _passo("preparar", trab, tmp_path)[0] == 0 and _passo("transcrever", trab, tmp_path)[0] == 0
        rc, saida, _ = com_a_chave("alinhar")
        assert rc == 0 and f.acoes() == ["pegar", "links", "audio", "parcial"] and saida.startswith(f"corretor: alinhar pedido={VID} ")
        rc, saida, _ = com_a_chave("entregar", RADAR_VIDEO_JOB="failure")              # o montar não rodou (o runner falhou)
        assert rc == 0 and f.final[VID] == {"situacao": "na_fila", "codigo": "github"}
        assert saida == f"corretor: entregar pedido={VID} erro=github situacao=na_fila\n"
    finally:
        f.fechar()


def test_uso_errado_e_pasta_que_nao_e_vazia(tmp_path, capfd, monkeypatch):
    for alvo, nome in ((sys, "excepthook"), (sys, "unraisablehook"), (threading, "excepthook")):
        monkeypatch.setattr(alvo, nome, getattr(alvo, nome))
    assert corrigir.main([]) == 2 and corrigir.main(["apagar", str(tmp_path)]) == 2 and corrigir.main(["pegar", "/tmp/a b"]) == 2
    (tmp_path / "sobra.txt").write_text("de outra execução")
    monkeypatch.setenv("RADAR_VIDEO_URL", "http://127.0.0.1:9/")
    monkeypatch.setenv("RADAR_VIDEO_ROBO_CHAVE", CHAVE)
    assert corrigir.main(["pegar", str(tmp_path)]) == 1
    assert capfd.readouterr() == ("corretor: corrigir erro=uso\ncorretor: corrigir erro=uso\ncorretor: pegar erro=pasta_invalida\n"
                                  "corretor: pegar erro=pasta_invalida\n", "")


# ------------------------------------------------------------------ o modelo do workflow do repositório privado
WORKFLOW = ROBO / "workflow" / "radar-video.yml"


def test_workflow_do_repositorio_privado():
    """Disparo manual e agenda de reserva, um de cada vez sem cancelar; o código do repositório público num commit conferido; ações
    fixadas por SHA; pip com hash; a chave da Azure só no passo da transcrição e a do robô só nos passos que falam com a radar-video;
    nada de upload-artifact, set -x, segredo dentro de um run, nem o ffmpeg fora do contêiner."""
    yaml = pytest.importorskip("yaml")
    texto = WORKFLOW.read_text(encoding="utf-8")
    codigo = "\n".join(re.sub(r"\s+#.*$", "", l) for l in texto.splitlines() if not l.lstrip().startswith("#"))   # sem os comentários
    w = yaml.safe_load(texto)
    gatilhos = w.get("on", w.get(True))
    assert set(gatilhos) == {"workflow_dispatch", "schedule"} and gatilhos["workflow_dispatch"] is None
    assert [c["cron"] for c in gatilhos["schedule"]] == ["47 13,19 * * 1-5"]
    assert w["permissions"] == {"contents": "read"} and w["concurrency"] == {"group": "radar-video", "queue": "max"}
    assert "env" not in w and list(w["jobs"]) == ["corrigir"]
    job = w["jobs"]["corrigir"]
    # v0.33.0: 60 minutos (o vídeo longo: a transcrição do F0 leva ~1 min por minuto de fala, mais a espera da vaga)
    assert job["runs-on"] == "ubuntu-24.04" and 45 <= job["timeout-minutes"] <= 90 and job["env"] == {"RADAR_VIDEO_ISOLADO": "docker"}
    passos = job["steps"]
    usos = [p["uses"] for p in passos if "uses" in p]
    assert usos and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in usos), usos
    assert passos[0]["with"] == {"repository": "arteconartescontabeis-design/radar", "ref": "${{ vars.RADAR_VIDEO_COMMIT }}",
                                 "persist-credentials": False}
    assert "git rev-parse HEAD" in passos[1]["run"] and passos[1]["env"] == {"COMMIT": "${{ vars.RADAR_VIDEO_COMMIT }}"}
    por_id = {p.get("id"): p for p in passos}
    chave_robo = {"RADAR_VIDEO_URL": "${{ vars.RADAR_VIDEO_URL }}", "RADAR_VIDEO_ROBO_CHAVE": "${{ secrets.RADAR_VIDEO_ROBO_CHAVE }}"}
    rodam = [(p.get("env") or {}, p.get("run", ""), p.get("if", "")) for p in passos[2:]]
    fases = []
    for env, run, se in rodam:
        m = re.search(r"robo/video/(corrigir|transcrever)\.py (\w+)?", run)
        if not m:
            assert not env, run                                                       # os passos sem o robô não têm segredo
            continue
        fase = m.group(2) if m.group(1) == "corrigir" else "transcrever"
        fases.append(fase)
        assert re.search(r'(^|\s)(python3|"\$RUNNER_TEMP/v/bin/python") -I robo/video/', run), run
        if fase in ("pegar", "alinhar", "entregar"):
            # a chave do robô: python3 do sistema (só a biblioteca padrão; nada do Pillow nem do SDK no processo com ela)
            assert run.startswith("python3 -I ") and {k: v for k, v in env.items() if k != "RADAR_VIDEO_JOB"} == chave_robo, fase
        elif fase == "transcrever":
            assert env == {k: "${{ secrets.%s }}" % k for k in ("AZURE_FALA_CHAVE", "AZURE_FALA_REGIAO", "AZURE_FALA_MODO", "AZURE_FALA_ENDPOINT")}
        else:
            assert env == {}, fase
    assert fases == ["pegar", "preparar", "transcrever", "alinhar", "montar", "entregar"]
    assert por_id["pegar"].get("if") is None and por_id["preparar"]["if"] == "steps.pegar.outputs.seguir == 'sim'"
    transc = next(p for p in passos if "transcrever.py" in p.get("run", ""))
    assert transc["if"] == "steps.preparar.outputs.transcrever == 'sim'" and transc["continue-on-error"] is True
    entregar = passos[-1]
    assert entregar["if"] == "always() && steps.pegar.outputs.pedido == 'sim'" and entregar["env"]["RADAR_VIDEO_JOB"] == "${{ job.status }}"
    assert all(p.get("if") == "steps.pegar.outputs.seguir == 'sim'" for p in passos[3:-1] if p is not transc and p is not por_id["preparar"])
    pip = next(p["run"] for p in passos if "pip" in p.get("run", ""))
    assert "--require-hashes" in pip and "--no-deps" in pip and "-r robo/video/requirements.txt" in pip
    assert "docker build -q -t radar-ffmpeg:local -f robo/video/Dockerfile robo/video" in codigo
    # nunca: artefato, cache, set -x, segredo dentro de um run, ffmpeg solto, pull_request, permissão de escrita
    for proibido in ("upload-artifact", "actions/cache", "set -x", "set -o xtrace", "pull_request", "RADAR_VIDEO_ISOLADO: local",
                     "write", "ACTIONS_STEP_DEBUG", "::add-mask::", "cancel-in-progress"):
        assert proibido not in codigo, proibido
    assert all("${{" not in p.get("run", "") for p in passos), "expressão dentro de um run"
    assert codigo.count("secrets.") == 7                                    # 3 da chave do robô e 4 da Azure, só nos env
    assert job["env"]["RADAR_VIDEO_ISOLADO"] == "docker" and all("RADAR_VIDEO_ISOLADO" not in (p.get("env") or {}) for p in passos)


def test_workflow_nao_esta_nos_workflows_deste_repositorio():
    """O modelo só roda no repositório privado: neste (público) não há workflow do corretor (o log seria aberto)."""
    publicos = [p.read_text(encoding="utf-8") for p in (RAIZ / ".github" / "workflows").glob("*.yml")]
    assert not any("corrigir.py" in t or "RADAR_VIDEO_ROBO_CHAVE" in t or "AZURE_FALA_CHAVE" in t for t in publicos)


# ------------------------------------------------------------------ o robô contra a função radar-video DE VERDADE
def _fala_banco() -> list[tuple[str, float, float]]:
    """A fala do roteiro do banco de teste (test_radar_video_banco.FALA), na forma léxica, com tempos: uma pausa entre as frases."""
    lexico = ("o prazo do simples vence no dia vinte confira com a gente antes do vencimento para não pagar multa nem juros").split()
    t, out = 0.5, []
    for w in lexico:
        d = min(0.45, 0.16 + 0.035 * len(w))
        out.append((w, round(t, 2), round(t + d, 2)))
        t += d + 0.12 + (0.7 if w == "vinte" else 0)
    return out


@FFMPEG
def test_robo_contra_a_funcao_radar_video_de_verdade(vid, tmp_path):
    """O robô inteiro (as fases, como no workflow) contra a supabase/functions/radar-video/index.ts rodando no Deno, com o banco de
    verdade (radar_video_pegar, _em_curso, _registrar_audio, _parcial, _concluir) e o armazenamento de mentira: a gravação na fila
    sai pronta, com o palavras.json guardado e os segundos na cota; o ajuste do administrador (legenda compacta) monta de novo com a
    transcrição guardada, sem contar os segundos de novo, num caminho novo. Os registros da função ficam sem link, token, chave e fala."""
    db = vid
    palavras = _fala_banco()
    dur = palavras[-1][2] + 0.8
    sint.video(tmp_path / "clipe.mp4", sint.voz(tmp_path / "voz.wav", palavras, dur), 1080, 1920, 30, dur)
    dados = (tmp_path / "clipe.mp4").read_bytes()
    pid, ana = reel(db)
    v = na_fila(db, pid, ana, partes=[{"n": 1, "tipo": "video/mp4", "bytes": len(dados)}])
    guardar(f"bruto/{v}/1", tipo="video/mp4", dados=dados)
    sdk = [("ok", [frase_sdk("O prazo do Simples vence no dia 20.", [(p, a, b, 0.9) for p, a, b in palavras[:8]]),
                   frase_sdk("Confira com a gente antes do vencimento para não pagar multa nem juros.",
                             [(p, a, b, 0.9) for p, a, b in palavras[8:]])])]
    url = f"http://127.0.0.1:{PORTA_FUNCAO}/"
    log = io.StringIO()
    with _ambiente(url, sdk_passos=sdk, chave=CHAVE_ROBO) as amb, contextlib.redirect_stdout(log):
        passos = _workflow(tmp_path / "t1", tmp_path / "s1")
    assert {k: x[0] for k, x in passos.items()} == {"pegar": 0, "preparar": 0, "transcrever": 0, "alinhar": 0, "montar": 0, "entregar": 0}
    assert len(amb.sdk.feitos) == 1 and f"corretor: entregar pedido={v} situacao=pronto" in log.getvalue().splitlines(), log.getvalue()
    sha, tamanho, situacao, guardada, segundos = video(db, v, "sha256, bytes, situacao, palavras_tentativa, segundos_audio")
    rel = video(db, v, "relatorio")
    assert situacao == "pronto" and guardada == 1 and segundos == round(dur, 1) and rel["texto_final"] == FALA_BANCO
    assert rel["parcial"] is False and rel["divergencias"] == [] and rel["transcricao"]["servico"] == "azure_f0"
    assert ARM["objetos"][f"corrigido/{v}/{sha}.mp4"]["bytes"] == tamanho and ARM["objetos"][f"corrigido/{v}/{sha}.mp4"]["tipo"] == "video/mp4"
    assert hashlib.sha256(ARM["objetos"][f"corrigido/{v}/{sha}.mp4"]["dados"]).hexdigest() == sha
    assert all(ARM["objetos"][f"quadros/{v}/{sha}/q{k}.jpg"]["tipo"] == "image/jpeg" for k in range(1, 5))
    assert ARM["objetos"][f"trabalho/{v}/1/palavras.json"]["tipo"] == "application/json"
    assert {e for _, e in ARM["assinaturas"]} == {600} and all(u is None for _, u in ARM["envios"])
    # o ajuste do administrador: monta de novo (sem transcrever, sem contar os segundos), num caminho novo
    from conftest import ADMIN, como
    with como("authenticated", ADMIN) as c:
        assert c.execute("select radar_video_ajustar(%s, %s, null)", (v, json.dumps({"estilo": "compacta"}))).fetchone()[0]["modo"] == "montagem"
    with _ambiente(url, sdk_passos=[], chave=CHAVE_ROBO) as amb, contextlib.redirect_stdout(log):
        passos = _workflow(tmp_path / "t2", tmp_path / "s2")
    assert passos["pegar"][1]["modo"] == "montagem" and "transcrever" not in passos and amb.sdk.feitos == []
    sha2, situacao, guardada, segundos2, rel = video(db, v, "sha256, situacao, palavras_tentativa, segundos_audio, relatorio")
    assert situacao == "pronto" and sha2 != sha and guardada == 1 and segundos2 == segundos and rel["legenda"]["estilo"] == "compacta"
    assert f"corrigido/{v}/{sha}.mp4" in ARM["objetos"] and f"corrigido/{v}/{sha2}.mp4" in ARM["objetos"]
    _log_limpo(log.getvalue(), "Simples", "multa")
    registros = "\n".join(l for l in LOGS[PORTA_FUNCAO].read_text().splitlines() if not l.startswith("Listening on "))
    assert f"radar-video: concluir {v} → pronto (robo)" in registros
    for proibido in ("token=", "assinado.", "envio.", "http", CHAVE_ROBO, "Ana", FALA_BANCO[:20], "eyJ"):
        assert proibido not in registros, proibido
