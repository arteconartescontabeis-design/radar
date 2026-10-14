"""v0.22.0 — corretor de vídeo, a receita de edição (robo/video/): sondagem e recusas, áudio de trabalho, cortes de começo, fim e
pausas, legenda e gancho na área livre do Reels, cartela, montagem, conferência da saída, logs sem dado pessoal e o isolamento do ffmpeg.

Só vídeos SINTÉTICOS (testes/radar_video_sintetico.py: testsrc2 ou um quadro que pisca durante cada palavra, uma "voz" harmônica e
ruído de sala), com o local 0,0 nos metadados. Os testes rodam o ffmpeg direto (RADAR_VIDEO_ISOLADO=local); o de contêiner monta a
imagem robo/video/Dockerfile e roda a mesma receita isolada (pulado sem o docker, ou se a imagem não puder ser montada — sem rede ou
o Docker Hub recusando por limite; RADAR_VIDEO_TESTE_BASE aponta um espelho da mesma imagem, pelo mesmo digest).
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from conftest import RAIZ

ROBO = RAIZ / "robo" / "video"
sys.path.insert(0, str(ROBO))

import radar_video_sintetico as sint  # noqa: E402

pytestmark = pytest.mark.skipif(not sint.tem_ffmpeg(), reason="ffmpeg e ffprobe não instalados (o CI instala pelo apt)")

import audio  # noqa: E402
import cartela  # noqa: E402
import conferir  # noqa: E402
import cortes  # noqa: E402
import isolado  # noqa: E402
import legenda  # noqa: E402
import montar  # noqa: E402
import segredo  # noqa: E402
import sondar  # noqa: E402
from segredo import ErroVideo  # noqa: E402

# o ffmpeg do Ubuntu tem todos; um ffmpeg mínimo sem o HEVC, o zscale (HDR) ou o VP8 pula só os testes que precisam deles
HEVC = pytest.mark.skipif(not sint.tem_ffmpeg() or not sint.ffmpeg_tem("libx265", "zscale"), reason="ffmpeg sem libx265 ou zscale")
CFG = {"pausa_max_s": 1.0, "pausa_bloco_s": 0.8, "lufs": -14, "cartela_s": 3}
GLOSSARIO = ["eSocial", "DCTFWeb", "IBS", "CBS", "Simples Nacional", "MEI", "CNPJ", "DAS", "DARF", "FGTS", "Cofins", "PIS", "PGDAS-D"]
CARTELA = ["Artecon Artes Contábeis · CNPJ 00.000.000/0001-00 · CRC-SC 000000/O-0", "Ana Teste, contadora · CRC-SC 000001/O-1"]
RAPIDO = "veryfast"                    # nos testes; a produção usa "medium" (o teste do contêiner também)
# um clipe da montagem com 4: duas frases com uma pausa de 1,0 s entre elas (fica com 0,40 s)
CURTAS = [("Bom", 0.50, 0.80), ("dia.", 1.00, 1.40), ("Prazo", 2.40, 2.80), ("certo.", 3.00, 3.30)]


@pytest.fixture(autouse=True)
def _local(monkeypatch):
    monkeypatch.setenv("RADAR_VIDEO_ISOLADO", "local")


@pytest.fixture()
def pastas(tmp_path) -> isolado.Pastas:
    (tmp_path / "ent").mkdir()
    p = isolado.Pastas(tmp_path / "ent", tmp_path / "sai", ROBO / "fontes")
    isolado.preparar(p)
    return p


@pytest.fixture(scope="module")
def acervo(tmp_path_factory):
    """Os clipes sintéticos, gerados uma vez por módulo (sob pedido)."""
    pasta = tmp_path_factory.mktemp("clipes")
    feitos: dict[str, Path] = {}

    def clipe(nome: str) -> Path:
        if nome in feitos:
            return feitos[nome]
        voz = lambda palavras, dur, atraso=0.0: sint.voz(pasta / f"{nome}.wav", [(t, a - atraso, b - atraso) for t, a, b in palavras],
                                                          dur - atraso)
        d = pasta / nome
        if nome == "vertical":                          # o celular comum: 1080×1920, 30 fps, H.264, com o local e a marca do aparelho
            sint.video(d, voz(sint.FRASES, sint.DURACAO), 1080, 1920, 30, sint.DURACAO, piscar=sint.FRASES)
        elif nome == "deitado":
            sint.video(d, voz(CURTAS, 3.8), 1920, 1080, 30, 3.8)
        elif nome == "sem_audio":
            sint.video(d, None, 1080, 1920, 30, 2.0)
        elif nome == "girado60":                        # gravado deitado com rotação de exibição (de pé depois do giro), 60 fps
            sint.video(d, voz(CURTAS, 3.8), 720, 1280, 60, 3.8, rotacao=90, piscar=CURTAS)
        elif nome == "hlg":                             # "iPhone": HEVC 10 bits HLG, MOV, com o áudio 0,478 s atrasado
            sint.video(d, voz(CURTAS, 3.8, 0.478), 720, 1280, 30, 3.8, codec="hevc", hdr="hlg", atraso=0.478, formato="mov",
                       piscar=CURTAS)
        elif nome == "pq":                              # HDR10 (PQ) 4:5: recorte para 9:16
            sint.video(d, voz(CURTAS, 3.8), 1080, 1350, 30, 3.8, codec="hevc", hdr="pq", piscar=CURTAS)
        elif nome == "curto_no_fim":                    # a última palavra acaba 0,1 s antes do fim do clipe
            fim = [("Olá.", 0.50, 1.00), ("Fim.", 1.50, 2.90)]
            sint.video(d, voz(fim, 3.0), 1080, 1920, 30, 3.0, piscar=fim)
        elif nome == "longo":                           # 61 s, pequeno (dois deles passam de 120 s)
            subprocess.run([*sint.F, "-f", "lavfi", "-i", "testsrc2=s=108x192:r=30:d=61", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                            "-t", "61", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-f", "mp4", str(d)], check=True)
        else:
            raise KeyError(nome)
        feitos[nome] = d
        return d
    return clipe


def _entrar(pastas: isolado.Pastas, *arquivos: Path) -> list[dict]:
    for n, a in enumerate(arquivos, 1):
        shutil.copy(a, pastas.ent / str(n))
    return [{"n": n, "tipo": "video/mp4", "bytes": (pastas.ent / str(n)).stat().st_size} for n in range(1, len(arquivos) + 1)]


def _silencios(pastas: isolado.Pastas) -> list[tuple[float, float]]:
    return audio.silencios("/sai/fala48k.wav", pastas, audio.limiar_silencio(audio.piso_ruido(audio.amostras("/sai/fala48k.wav", pastas))))


def _no_video(plano: dict, palavras: list[dict]) -> list[dict]:
    return [{"texto": w["texto"], "ini": cortes.remapear(plano, w["ini"])[0], "fim": cortes.remapear(plano, w["fim"])[0]} for w in palavras]


def _receita(pastas: isolado.Pastas, partes: list[dict], palavras_por_clipe: list[list[tuple]], gancho: str | None = None,
             preset: str = RAPIDO, estilo: str = "normal"):
    """sondar → áudio → silêncios → cortes → legenda → cartela → montagem → conferência (o que o robô faz, sem a transcrição: as
    palavras vêm prontas, na forma de exibição)."""
    infos = sondar.sondar_todas(partes, pastas)
    audio.extrair(infos, pastas)
    palavras = [w for i, ps in zip(infos, palavras_por_clipe) for w in sint.palavras(ps, i["inicio_q"] / sondar.FPS)]
    plano = cortes.planejar(infos, _silencios(pastas), CFG, palavras)
    legenda.gravar(pastas.sai / "legenda.ass", _no_video(plano, palavras), GLOSSARIO, estilo, gancho)
    cartela.desenhar(pastas.sai / "cartela.png", CARTELA)
    rel = montar.montar(infos, plano, pastas, CFG, preset=preset)
    rel["conferencia"] = conferir.conferir(pastas, CFG)
    return infos, palavras, plano, rel


# ------------------------------------------------------------------ entrada não confiável e recusas
def test_entrada_nao_confiavel_e_recusada_sem_abrir_rede(pastas, acervo, monkeypatch):
    chamadas = []
    rodar = isolado.rodar
    monkeypatch.setattr(isolado, "rodar", lambda *a, **k: chamadas.append(a[1]) or rodar(*a, **k))
    # uma playlist HLS renomeada para .mp4 (o ffmpeg seguiria os links): recusada no byte 4, sem nem chamar o ffprobe
    (pastas.ent / "1").write_text("#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:10,\nhttp://exemplo.invalid/a.ts\n#EXT-X-ENDLIST\n")
    with pytest.raises(ErroVideo) as e:
        sondar.sondar(1, pastas)
    assert e.value.codigo == "formato" and chamadas == []
    # começa com ftyp mas não é MP4: o ffprobe (com -f mov, sem adivinhar o formato) não abre
    (pastas.ent / "2").write_bytes(b"\x00\x00\x00\x18ftypisom" + b"lixo" * 400)
    with pytest.raises(ErroVideo) as e:
        sondar.sondar(2, pastas)
    assert e.value.codigo == "formato"
    # um Matroska (sem ftyp)
    subprocess.run([*sint.F, "-f", "lavfi", "-i", "testsrc2=s=108x192:d=1", "-c:v", "libx264", "-f", "matroska", str(pastas.ent / "3")],
                   check=True)
    with pytest.raises(ErroVideo) as e:
        sondar.sondar(3, pastas)
    assert e.value.codigo == "formato"
    # maior que o declarado no envio
    shutil.copy(acervo("vertical"), pastas.ent / "4")
    with pytest.raises(ErroVideo) as e:
        sondar.sondar(4, pastas, bytes_declarados=1000)
    assert e.value.codigo == "arquivo_grande"


def test_recusa_sem_audio_deitado_e_longo_demais(pastas, acervo):
    for n, (nome, codigo) in enumerate([("sem_audio", "sem_audio"), ("deitado", "deitado")], 1):
        shutil.copy(acervo(nome), pastas.ent / str(n))
        with pytest.raises(ErroVideo) as e:
            sondar.sondar(n, pastas)
        assert e.value.codigo == codigo
    partes = _entrar(pastas, acervo("longo"), acervo("longo"))
    assert sondar.sondar(1, pastas)["dur"] == pytest.approx(61, abs=0.1)                  # um sozinho passa
    with pytest.raises(ErroVideo) as e:
        sondar.sondar_todas(partes, pastas)
    assert e.value.codigo == "longo_demais"


@HEVC
def test_sondagem_de_girado_60fps_e_hdr_sem_dado_do_aparelho(pastas, acervo):
    partes = _entrar(pastas, acervo("vertical"), acervo("girado60"), acervo("hlg"), acervo("pq"))
    v, g, h, p = sondar.sondar_todas(partes, pastas)
    assert (v["w"], v["h"], v["girado"], v["hdr"], v["fps"]) == (1080, 1920, False, None, 30)
    assert (g["w"], g["h"], g["girado"], g["fps"]) == (720, 1280, True, 60)                # de pé depois do giro
    assert (h["hdr"], h["codec"], p["hdr"], p["w"], p["h"]) == ("hlg", "hevc", "pq", 1080, 1350)
    assert v["quadros"] == 270 and g["quadros"] == 114                                      # a 30 fps, para baixo
    assert "0000" not in json.dumps([v, g, h, p]) and "Teste" not in json.dumps([v, g, h, p])   # nada do local nem do aparelho
    assert sondar.resumo([v, g, h, p]) == {"clipes": 4, "duracao_s": 20.4, "resolucao": "1080x1920", "fps": 30, "hdr": "hlg", "girado": True}


# ------------------------------------------------------------------ áudio de trabalho e cortes
@HEVC
def test_audio_no_zero_do_video_preserva_o_atraso(pastas, acervo):
    """Clipe com o áudio começando 0,478 s depois do vídeo: o WAV de trabalho começa no zero do vídeo (silêncio no começo) e tem o
    tamanho exato do trecho de vídeo usado (quadros × 1600 amostras), para o corte valer igual para os dois."""
    infos = sondar.sondar_todas(_entrar(pastas, acervo("hlg"), acervo("vertical")), pastas)
    dur = audio.extrair(infos, pastas)
    assert (infos[0]["inicio_q"], infos[1]["inicio_q"]) == (0, 114)
    assert dur == pytest.approx((114 + 270) / 30)
    for wav, sr in (("fala48k.wav", 48000), ("fala16k.wav", 16000)):
        r = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(pastas.sai / wav)],
                                      capture_output=True, text=True, check=True).stdout)
        s = r["streams"][0]
        assert (int(s["sample_rate"]), s["channels"]) == (sr, 1) and float(s["duration"]) == pytest.approx(dur, abs=1e-3)
        assert set(r["format"].get("tags") or {}) <= {"encoder"}                             # sem metadados (só o "Lavf" do ffmpeg)
    # a 1ª palavra do clipe atrasado está no tempo do VÍDEO (0,50 s), e não no do arquivo de áudio (0,022 s)
    assert sint.inicio_da_voz(pastas.sai / "fala48k.wav", limiar_db=-35) == pytest.approx(0.50, abs=0.006)
    assert sint.inicio_da_voz(pastas.sai / "fala48k.wav", depois_de=3.8, limiar_db=-35) == pytest.approx(3.8 + 1.20, abs=0.006)


def test_cortes_de_comeco_fim_e_pausas(pastas, acervo):
    """1,2 s de silêncio no começo, pausa de 1,1 s dentro da frase (fica 0,30 s), de 0,9 s entre frases (fica 0,40 s) e 1,6 s no fim:
    fica de 0,12 s antes da 1ª palavra a 0,45 s depois da última, em quadros, e os cortes saem numerados no relatório."""
    infos = sondar.sondar_todas(_entrar(pastas, acervo("vertical")), pastas)
    audio.extrair(infos, pastas)
    sil = _silencios(pastas)
    esperado = [(0.0, 1.20), (2.25, 3.35), (4.40, 5.30), (7.40, 9.0)]
    assert len(sil) == 4 and all(abs(a - x) < 0.02 and abs(min(b, 9.0) - y) < 0.02 for (a, b), (x, y) in zip(sil, esperado))
    palavras = sint.palavras(sint.FRASES)
    plano = cortes.planejar(infos, sil, CFG, palavras)
    q = lambda t: t * 30
    (a1, b1), (a2, b2), (a3, b3) = plano["trechos"]
    assert a1 == 32 and b3 == 236                                                            # floor(1,08 × 30) e ceil(7,85 × 30)
    assert abs(b1 - q(2.40)) <= 1 and abs(a2 - q(3.20)) <= 1 and abs(b2 - q(4.60)) <= 1 and abs(a3 - q(5.10)) <= 1
    assert [c["tipo"] for c in plano["cortes"]] == ["inicio", "pausa", "pausa", "fim"] and [c["k"] for c in plano["cortes"]] == [0, 1, 2, 3]
    assert [c["dur_s"] for c in plano["cortes"][1:3]] == [pytest.approx(0.80, abs=0.03), pytest.approx(0.50, abs=0.03)]
    assert plano["cortes"][0]["ate_s"] == pytest.approx(1.08) and plano["cortes"][3]["de_s"] == pytest.approx(7.85)
    assert plano["pad_q"] == 0 and plano["ultima_s"] == pytest.approx(cortes.remapear(plano, 7.40)[0], abs=1e-3)
    # nenhuma palavra cai num corte
    assert all(cortes.remapear(plano, w["ini"])[1] and cortes.remapear(plano, w["fim"])[1] for w in palavras)
    # pausas abaixo dos limites das Configurações ficam inteiras
    inteiro = cortes.planejar(infos, sil, {"pausa_max_s": 1.2, "pausa_bloco_s": 1.0}, palavras)
    assert len(inteiro["trechos"]) == 1 and [c["tipo"] for c in inteiro["cortes"]] == ["inicio", "fim"]
    # "Manter este trecho" (ajustes.manter) pela chave do corte (o clipe e o quadro em que começa o silêncio cortado), e não pelo número
    assert [c.get("chave") for c in plano["cortes"]] == [None, f"1:{math.floor(2.25 * 30)}", f"1:{math.floor(4.40 * 30)}", None]
    mantido = cortes.planejar(infos, sil, CFG, palavras, manter=[plano["cortes"][1]["chave"], 2, "2"])
    assert [(c["k"], c.get("mantido")) for c in mantido["cortes"]] == [(0, None), (1, True), (2, False), (3, None)]
    assert len(mantido["trechos"]) == 2 and mantido["fala_q"] - plano["fala_q"] == pytest.approx(24, abs=1)
    # o que o alinhamento manda tirar (etapa 2): automático corta; não automático vira sugestão
    tirar = cortes.planejar(infos, sil, CFG, palavras, remover=[{"ini": 5.40, "fim": 5.50, "tipo": "voz_entre_palavras", "automatico": True},
                                                                {"ini": 6.45, "fim": 6.55, "tipo": "repeticao", "automatico": False}])
    assert [c["tipo"] for c in tirar["cortes"]] == ["inicio", "pausa", "pausa", "voz_entre_palavras", "fim"]
    assert tirar["sugestoes"] == [{"em_s": pytest.approx(cortes.remapear(tirar, 6.45)[0], abs=0.01), "dur_s": 0.1, "clipe": 1, "tipo": "repeticao"}]
    assert tirar["fala_q"] == plano["fala_q"] - 3
    # reserva sem transcrição: pelas vozes do silencedetect (toda pausa acima de 0,8 s fica com 0,40 s)
    sem = cortes.planejar(infos, sil, CFG)
    assert [c["tipo"] for c in sem["cortes"]] == ["inicio", "pausa", "pausa", "fim"]
    assert sem["trechos"][0][0] == 32 and sem["trechos"][-1][1] == 236 and abs(sem["trechos"][0][1] - q(2.45)) <= 1


def test_trecho_nunca_passa_de_um_clipe_para_o_outro():
    """A fala que vai até o fim de um clipe e a que começa logo no início do seguinte ficam em dois trechos (cada clipe tem o seu
    select), mesmo com os quadros encostados."""
    partes = [{"n": 1, "inicio_q": 0, "quadros": 90}, {"n": 2, "inicio_q": 90, "quadros": 60}]
    palavras = sint.palavras([("Até", 0.50, 1.00), ("o", 1.10, 1.20), ("fim.", 1.30, 2.95), ("Começo", 3.02, 3.60), ("já.", 3.70, 4.00)])
    plano = cortes.planejar(partes, [], CFG, palavras)
    assert plano["trechos"] == [[11, 90], [90, 134]]
    assert cortes.por_clipe(plano, partes) == {1: [(11, 90)], 2: [(0, 44)]}
    assert [c["tipo"] for c in plano["cortes"]] == ["inicio", "fim"] and plano["pad_q"] == 0


def test_clipe_sem_fala_sai_inteiro(pastas, acervo):
    infos = sondar.sondar_todas(_entrar(pastas, acervo("vertical"), acervo("curto_no_fim")), pastas)
    audio.extrair(infos, pastas)
    plano = cortes.planejar(infos, _silencios(pastas), CFG, sint.palavras(sint.FRASES))      # nenhuma palavra no 2º clipe
    assert plano["cortes"][-1] == {"clipe": 2, "de_s": 0.0, "ate_s": 3.0, "tipo": "clipe_sem_fala", "k": 4}
    assert set(cortes.por_clipe(plano, infos)) == {1}
    with pytest.raises(ErroVideo) as e:
        cortes.planejar(infos, _silencios(pastas), CFG, [])
    assert e.value.codigo == "sem_fala"


# ------------------------------------------------------------------ montagem e conferência
def test_montagem_vertical_no_padrao_das_redes_sem_metadados(pastas, acervo, capfd):
    infos, palavras, plano, rel = _receita(pastas, _entrar(pastas, acervo("vertical")), [sint.FRASES], gancho="Prazo do eSocial muda")
    saida = pastas.sai / "reel.mp4"
    c = rel["conferencia"]
    assert (c["codec"], c["fps"], c["audio"], c["moov_inicio"], c["sem_edit_list"], c["sem_gps"]) == \
        ("h264 high", 30, "aac 48 kHz 2 canais", True, True, True)
    # -14 LUFS no modo linear do loudnorm (o limitador antes dele deixa o pico caber): sem cair no modo dinâmico, que erra o alvo
    assert rel["audio"]["linear"] is True and c["lufs"] == pytest.approx(-14, abs=0.5) and c["pico_dbtp"] <= -1.5
    # duração = fala (cortada) + cartela − transição, medida pelo ffprobe; vídeo e áudio do mesmo tamanho
    assert rel["saida"]["fala_s"] == pytest.approx(plano["fala_q"] / 30, abs=0.01)
    assert rel["saida"]["duracao_s"] == pytest.approx(plano["fala_q"] / 30 + 2.6, abs=0.01)
    fluxos = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(saida)], capture_output=True, text=True).stdout)["streams"]
    assert [float(s["duration"]) for s in fluxos] == [pytest.approx(plano["fala_q"] / 30 + 2.6, abs=0.03)] * 2
    assert int(fluxos[0]["nb_frames"]) == plano["fala_q"] + 78                              # 30 fps constantes
    # nada do celular: nem o local (em texto ou na caixa ©xyz), nem a marca e o modelo, nem nos quadros
    for arq in [saida, *(pastas.sai / f"q{k}.jpg" for k in range(1, 5))]:
        dados = arq.read_bytes()
        assert sint.GPS.encode() not in dados and b"+00.0000" not in dados and b"Celular de Teste" not in dados and b"Modelo" not in dados
    assert [Image.open(pastas.sai / f"q{k}.jpg").size for k in range(1, 5)] == [(1080, 1920)] * 4
    assert rel["quadros_ms"] == [round(plano["fala_q"] / 30 * f * 1000) for f in (0.15, 0.40, 0.65, 0.90)]
    # cada quadro é do instante certo: claro se cai numa palavra, escuro numa pausa (longe das bordas das palavras)
    no_video = _no_video(plano, palavras)
    for k, ms in enumerate(rel["quadros_ms"], 1):
        t = ms / 1000
        if all(abs(t - w[x]) > 0.05 for w in no_video for x in ("ini", "fim")):
            claro = Image.open(pastas.sai / f"q{k}.jpg").convert("L").crop((0, 100, 1080, 500)).getextrema()[0] > 150
            assert claro == any(w["ini"] <= t <= w["fim"] for w in no_video), (k, t)
    # a voz no mesmo instante do vídeo: a 1ª palavra começa onde o plano diz (o atraso de 21 ms do AAC é descontado)
    assert sint.inicio_da_voz(saida) == pytest.approx(cortes.remapear(plano, 1.20)[0], abs=0.006)
    # cada palavra: o branco do quadro e a voz começam juntos (até 1 quadro), depois dos cortes
    luz, voz = sint.subidas([x > 150 for x in sint.luz_do_alto(saida)]), sint.subidas(sint.voz_por_quadro(saida))
    assert len(luz) == len(voz) == len(sint.FRASES) and all(abs(a - b) <= 1 for a, b in zip(luz, voz)), (luz, voz)
    # fim da fala intacto: os últimos 300 ms da última palavra ("15.", de 6,90 a 7,40 s) com a mesma energia, relativa ao começo da
    # mesma palavra, antes e depois (o esmaecer para a cartela não entra nela)
    fim = plano["ultima_s"]
    depois = sint.nivel_db(saida, fim - 0.30, fim) - sint.nivel_db(saida, fim - 0.48, fim - 0.30)
    antes = sint.nivel_db(pastas.sai / "fala48k.wav", 7.10, 7.40) - sint.nivel_db(pastas.sai / "fala48k.wav", 6.92, 7.10)
    assert abs(depois - antes) < 1.5, (antes, depois)
    # o log: nada (a receita não imprime; o stderr do ffmpeg nunca sai)
    saida_log = capfd.readouterr()
    assert saida_log.out == "" and saida_log.err == ""


@HEVC
def test_quatro_clipes_girado_60fps_hdr_e_atraso_ficam_sincronizados(pastas, acervo):
    """4 clipes (H.264 de pé; deitado com rotação a 60 fps; HEVC HLG com o áudio 0,478 s atrasado; HEVC PQ 4:5): uma saída só, no
    padrão, e a voz de cada palavra junto do branco que pisca no quadro (até 1 quadro), depois do giro, da troca de 60 para 30 fps,
    do HDR para SDR, do recorte e dos cortes."""
    partes = _entrar(pastas, acervo("vertical"), acervo("girado60"), acervo("hlg"), acervo("pq"))
    infos, palavras, plano, rel = _receita(pastas, partes, [sint.FRASES, CURTAS, CURTAS, CURTAS])
    assert [i["inicio_q"] for i in infos] == [0, 270, 384, 498]
    assert [c["tipo"] for c in plano["cortes"]].count("pausa") == 2 + 3                       # 2 no 1º clipe e 1 entre frases em cada outro
    saida = pastas.sai / "reel.mp4"
    luz, voz = sint.subidas([x > 120 for x in sint.luz_do_alto(saida)]), sint.subidas(sint.voz_por_quadro(saida))
    assert len(luz) == len(voz) == len(palavras) and all(abs(a - b) <= 1 for a, b in zip(luz, voz)), (luz, voz)
    assert len(plano["trechos"]) == 3 + 2 * 3 and rel["conferencia"]["duracao_s"] == pytest.approx(plano["fala_q"] / 30 + 2.6, abs=0.03)
    assert set(rel["imagem"]["luz"]) == {1, 2, 3, 4}
    assert rel["audio"]["linear"] is True and rel["conferencia"]["lufs"] == pytest.approx(-14, abs=0.5)


def test_fim_da_fala_que_acaba_com_o_clipe_nao_e_esmaecido(pastas, acervo):
    """A última palavra acaba 0,1 s antes do fim do clipe: o plano completa com o último quadro parado e silêncio (pad_q), e a
    transição para a cartela só começa 0,05 s depois da palavra — a palavra inteira com a mesma energia e o quadro ainda claro."""
    fim = [("Olá.", 0.50, 1.00), ("Fim.", 1.50, 2.90)]
    infos, palavras, plano, rel = _receita(pastas, _entrar(pastas, acervo("curto_no_fim")), [fim])
    assert plano["pad_q"] == 11
    saida, ultima = pastas.sai / "reel.mp4", plano["ultima_s"]
    assert (plano["fala_q"] + plano["pad_q"]) / 30 - 0.4 >= ultima + 0.05 - 1e-6
    assert abs(sint.nivel_db(saida, ultima - 0.30, ultima) - sint.nivel_db(saida, ultima - 1.0, ultima - 0.7)) < 1.5
    luz = sint.luz_do_alto(saida)
    assert luz[int(ultima * 30) - 1] > 150                                                   # ainda o branco da palavra, sem esmaecer


def test_ajuste_so_muda_a_legenda_nunca_o_audio(pastas, acervo):
    """Refazer a montagem com outra legenda (o ajuste do administrador) dá o MESMO áudio, byte a byte."""
    infos = sondar.sondar_todas(_entrar(pastas, acervo("curto_no_fim")), pastas)
    audio.extrair(infos, pastas)
    palavras = sint.palavras([("Olá.", 0.50, 1.00), ("Fim.", 1.50, 2.90)])
    plano = cortes.planejar(infos, _silencios(pastas), CFG, palavras)
    cartela.desenhar(pastas.sai / "cartela.png", CARTELA)
    hashes = []
    for texto, estilo in (("Olá.", "normal"), ("Oi, tudo bem.", "compacta")):
        legenda.gravar(pastas.sai / "legenda.ass", _no_video(plano, [{**palavras[0], "texto": texto}, palavras[1]]), [], estilo)
        montar.montar(infos, plano, pastas, CFG, preset="ultrafast")
        hashes.append([subprocess.run(["ffmpeg", "-v", "error", "-i", str(pastas.sai / "reel.mp4"), "-map", m, "-c", "copy", "-f", "md5", "-"],
                                      capture_output=True, text=True, check=True).stdout for m in ("0:a", "0:v")])
    assert hashes[0][0] == hashes[1][0] and hashes[0][1] != hashes[1][1]


def test_conferencia_recusa_saida_fora_do_padrao(pastas, acervo):
    """O MP4 padrão do ffmpeg (lista de edição por causa dos quadros B, moov no fim, 25 fps, 720×1280, local nos metadados) é
    recusado item por item, com nomes fixos."""
    subprocess.run([*sint.F, "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=25:d=4", "-f", "lavfi", "-i", "sine=f=300:sample_rate=44100:d=4",
                    "-c:v", "libx264", "-preset", "ultrafast", "-bf", "2", "-c:a", "aac", "-metadata", f"location={sint.GPS}",
                    "-f", "mp4", str(pastas.sai / "ruim.mp4")], check=True)
    with pytest.raises(ErroVideo) as e:
        conferir.conferir(pastas, CFG, "ruim.mp4")
    assert e.value.codigo == "conferencia_falhou"
    assert {"faststart", "fps", "resolucao", "audio", "gps", "metadados", "volume"} <= set(e.value.detalhe), e.value.detalhe
    assert sint.GPS not in str(e.value)
    caixas = conferir.bytes_mp4(pastas.sai / "ruim.mp4")
    assert caixas["topo"][-1] == "moov" and "edit_list" in caixas["proibidas"]


# ------------------------------------------------------------------ legenda, gancho e cartela
def _quadros_da_legenda(pastas: isolado.Pastas, ass: Path, dur: float, nome: str) -> list[Image.Image]:
    """Desenha o .ass sobre fundo preto (o libass com a DM Sans de robo/video/fontes), 4 quadros por segundo."""
    d = pastas.sai / nome
    d.mkdir()
    err = subprocess.run([*sint.F[:2], "-loglevel", "debug", "-nostdin", "-f", "lavfi", "-i", f"color=black:s=1080x1920:r=4:d={dur}",
                          "-vf", f"ass=filename={ass}:fontsdir={ROBO / 'fontes'}", str(d / "q%03d.png")], capture_output=True, text=True, check=True).stderr
    assert re.findall(r"fontselect: \(DM Sans, 700, 0\) -> (\S+?),", err) and set(re.findall(r"fontselect: \(DM Sans, 700, 0\) -> (\S+?),", err)) == {"DMSans-Bold"}
    return [Image.open(q).convert("L") for q in sorted(d.glob("q*.png"))]


def _caixa(im: Image.Image):
    return im.point(lambda v: 255 if v > 12 else 0).getbbox()


def test_legenda_e_gancho_na_area_livre_com_a_dm_sans(pastas):
    x0, y0, x1, y1 = legenda.AREA_LIVRE
    texto = ("Atenção: o prazo do eSocial e da DCTFWeb para o Simples Nacional vence no dia 15, e quem é MEI paga o DAS até "
             "o dia 20 sem multa. ANTICONSTITUCIONALISSIMAMENTE, confira! {\\an8}Fim.")
    palavras, t = [], 0.2
    for p in texto.split():
        palavras.append({"texto": p, "ini": t, "fim": t + 0.32})
        t += 0.42
    info = legenda.gravar(pastas.sai / "fala.ass", palavras, GLOSSARIO, "normal")
    ass = (pastas.sai / "fala.ass").read_text(encoding="utf-8")
    eventos = [l.split(",,0,0,0,,", 1)[1] for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert info["blocos"] == len(eventos) >= 5 and "\\an8" not in ass and "{\\an" not in ass        # o texto não vira comando do ASS
    assert any("Simples\\hNacional" in e for e in eventos)                                     # termo do glossário inteiro
    for e in eventos:
        e = re.sub(r"^\{\\fs\d+\}", "", e)
        assert len(e.split("\\N")) <= 2 and all(len(l.replace("\\h", " ")) <= 24 for l in e.split("\\N")) or "ANTICONST" in e
    blocos = legenda.blocos(palavras, GLOSSARIO)
    assert all(b["fim"] - b["ini"] <= 3.2 + 0.6 for b in blocos) and blocos[-1]["fim"] == pytest.approx(palavras[-1]["fim"])
    assert all(a["fim"] <= b["ini"] for a, b in zip(blocos, blocos[1:]))
    assert any(b["fonte"] < 70 for b in blocos)                                                 # a palavra larga demais: letra menor
    caixas = [c for c in map(_caixa, _quadros_da_legenda(pastas, pastas.sai / "fala.ass", t + 0.5, "fala")) if c]
    assert len(caixas) >= info["blocos"]
    for c in caixas:
        assert c[0] >= x0 and c[1] >= y0 and c[2] <= x1 and c[3] <= y1, c
    duas = max(c[3] - c[1] for c in caixas)
    # gancho (0 a 3 s) acima da caixa de duas linhas da legenda, sem encostar
    legenda.gravar(pastas.sai / "gancho.ass", [], [], "normal", "Prazo novo do eSocial para o MEI em 2027")
    (g,) = {c for c in map(_caixa, _quadros_da_legenda(pastas, pastas.sai / "gancho.ass", 2.0, "gancho")) if c}
    assert g[0] >= x0 and g[1] >= y0 and g[2] <= x1 and g[3] < min(c[1] for c in caixas) - 8, (g, caixas)
    # estilo compacto: uma linha só, mais baixa que a de duas
    legenda.gravar(pastas.sai / "compacta.ass", palavras[:12], GLOSSARIO, "compacta")
    compactas = [c for c in map(_caixa, _quadros_da_legenda(pastas, pastas.sai / "compacta.ass", 5.0, "compacta")) if c]
    assert compactas and max(c[3] - c[1] for c in compactas) < duas * 0.7 and all(c[0] >= x0 and c[2] <= x1 and c[3] <= y1 for c in compactas)
    # gancho comprido demais: fica de fora com aviso, nunca cortado
    r = legenda.gravar(pastas.sai / "x.ass", palavras[:3], [], "normal", "Um texto de gancho comprido demais para caber em duas linhas curtas")
    assert r["gancho"] is False and r["avisos"] == ["gancho_nao_cabe"] and "…" not in (pastas.sai / "x.ass").read_text(encoding="utf-8")


def test_cartela_com_a_dm_sans_do_repositorio_e_recusa_sem_reticencias(pastas):
    r = cartela.desenhar(pastas.sai / "c.png", CARTELA, "Desde 1984 · (48) 0000-0000 · artecon.cnt.br")
    im = Image.open(pastas.sai / "c.png")
    assert im.size == (1080, 1920) and im.mode == "RGB"
    assert r["altura_h"] >= 28 and 40 <= r["tamanho"] <= 52
    x0, y0, x1, y1 = r["caixa"]
    assert x0 >= 65 and x1 <= 1015 and y0 >= 820 and y1 <= 1240
    assert r["linhas"][0] == ["Artecon Artes Contábeis", "CNPJ 00.000.000/0001-00", "CRC-SC 000000/O-0"]   # quebra nos " · "
    assert not any("…" in l for q in r["linhas"] for l in q)
    # o texto é desenhado: a faixa das linhas tem pixels claros; acima da faixa (fora do logotipo) só o degradê
    assert im.crop((70, 830, 1010, 1230)).convert("L").getextrema()[1] > 200
    assert im.crop((70, 720, 1010, 800)).convert("L").getextrema()[1] < 120
    # linha curta: letra maior (52)
    assert cartela.desenhar(pastas.sai / "c2.png", ["Artecon Artes Contábeis"])["tamanho"] == 52
    # não cabe nem com a letra mínima: erro, nunca "…"
    for linhas in (["Palavraenormesemespacosnenhumquenaocabedejeitonenhumnalinhadacartelamesmocomaletramenor"], ["Linha comprida " * 12] * 4):
        with pytest.raises(ErroVideo) as e:
            cartela.desenhar(pastas.sai / "c3.png", linhas)
        assert e.value.codigo == "cartela_nao_cabe"
    assert cartela.altura_h(40) >= 28 > cartela.altura_h(38)


def test_fontes_e_licenca_no_repositorio():
    from PIL import ImageFont
    assert ImageFont.truetype(str(ROBO / "fontes" / "DMSans-Bold.ttf"), 20).getname() == ("DM Sans", "Bold")
    assert ImageFont.truetype(str(ROBO / "fontes" / "DMSans-Medium.ttf"), 20).getname() == ("DM Sans", "Medium")
    ofl = (ROBO / "fontes" / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE Version 1.1" in ofl and "DM Sans Project Authors" in ofl


# ------------------------------------------------------------------ logs e isolamento
def test_log_e_erros_sem_dado_pessoal(pastas, acervo, capfd, monkeypatch):
    monkeypatch.setenv("RADAR_VIDEO_ROBO_CHAVE", "chave-do-robo-de-teste-123")
    texto = ("Ana Teste em +00.1234+000.5678/ https://x.supabase.co/storage/v1/object/sign/radar-videos/bruto/1?token=eyJhbGciOiJIUzI1NiJ9."
             "eyJ1cmwiOiJ4In0.abcdefghijk x-signature: abc123 sb_secret_abcdef iagw_radar_xyz chave-do-robo-de-teste-123")
    limpo = segredo.sem_segredo(texto)
    for proibido in ("+00.1234", "https://", "token=", "eyJ", "abc123", "sb_secret_abcdef", "iagw_radar_xyz", "chave-do-robo"):
        assert proibido not in limpo, proibido
    segredo.log("montar", pedido="00000000-0000-0000-0000-000000000001", clipes=4, duracao=41.6, nome="Ana Teste", gps=sint.GPS, ok=True)
    assert capfd.readouterr().out == "corretor: montar pedido=00000000-0000-0000-0000-000000000001 clipes=4 duracao=41.60 nome=? gps=? ok=sim\n"
    assert str(ErroVideo("Ana Teste", "etapa com espaço", ["https://x", "gps"])) == "erro_interno: gps"
    # a falha do ffmpeg (aqui, um clipe truncado com o local nos metadados) não imprime nada e não leva o caminho nem o local
    dados = acervo("vertical").read_bytes()
    (pastas.ent / "1").write_bytes(dados[: len(dados) // 3])
    with pytest.raises(ErroVideo) as e:
        infos = sondar.sondar_todas([{"n": 1, "bytes": len(dados)}], pastas)
        audio.extrair(infos, pastas)
        montar.medir_luz(infos[0], pastas)
    assert str(pastas.ent) not in str(e.value) and "+00.0000" not in str(e.value) and e.value.__cause__ is None
    assert capfd.readouterr() == ("", "")
    # exceção não tratada: só a etapa, o uuid e o nome do tipo
    prog = ("import sys; sys.path.insert(0, %r); import segredo; segredo.instalar_excepthook(); "
            "segredo.etapa('montar', '00000000-0000-0000-0000-000000000002'); raise ValueError(%r)") % (str(ROBO), texto)
    r = subprocess.run([sys.executable, "-I", "-c", prog], capture_output=True, text=True,
                       env={**os.environ, "RADAR_VIDEO_ROBO_CHAVE": "chave-do-robo-de-teste-123"})
    assert r.stdout == "" and r.stderr == "corretor: erro inesperado na etapa montar do pedido 00000000-0000-0000-0000-000000000002 (ValueError)\n"


def test_ffmpeg_nao_recebe_o_ambiente_do_robo(pastas, monkeypatch):
    """O ffmpeg roda com um ambiente mínimo: a chave do robô e a da Azure (que o workflow põe no ambiente do passo) não chegam a ele."""
    monkeypatch.setenv("RADAR_VIDEO_ROBO_CHAVE", "chave-do-robo-de-teste-123")
    monkeypatch.setenv("AZURE_FALA_CHAVE", "chave-da-azure-de-teste-456")
    isolado.rodar("t", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "data", "-i", "/proc/self/environ",
                                  "-map", "0", "-c", "copy", "-f", "data", "/sai/amb.bin"], pastas)
    amb = (pastas.sai / "amb.bin").read_bytes()
    assert b"PATH=" in amb and b"chave-do-robo" not in amb and b"chave-da-azure" not in amb and b"RADAR_VIDEO" not in amb


def test_codigo_do_robo_isolado_e_sem_ia(monkeypatch):
    """Estático: só o isolado.py abre processos; todo clipe entra com -protocol_whitelist file -f mov; o prefixo do contêiner tem sem
    rede, só leitura, sem privilégio e nenhum -e; ninguém imprime o stderr; nada de síntese de voz, interpolação ou IA."""
    fontes = {p.name: p.read_text(encoding="utf-8") for p in ROBO.glob("*.py")}
    assert {"isolado.py", "sondar.py", "audio.py", "cortes.py", "legenda.py", "cartela.py", "montar.py", "conferir.py", "segredo.py",
            "alinhar.py", "numeros.py", "relatorio.py", "transcrever.py", "corrigir.py", "conversa.py"} <= set(fontes)
    for nome, codigo in fontes.items():
        if nome != "isolado.py":
            assert not re.search(r"\bsubprocess\b|os\.system|os\.popen|\bPopen\b|os\.exec|pty\.", codigo), nome
        if nome != "segredo.py":
            assert "print(" not in codigo, nome                                            # o log é só pelo segredo.log
        assert not re.search(r"SpeechSynthesizer|minterpolate|images/generations|ia-gateway|anthropic|openai|enable_audio_logging", codigo, re.I), nome
        for m in re.finditer(r'"-i", f"/ent/', codigo):                                     # todo clipe com o demuxer forçado e só arquivo
            assert "*ENTRADA" in codigo[max(0, m.start() - 60):m.start()], (nome, codigo[m.start() - 60:m.start()])
    assert sondar.ENTRADA == ["-protocol_whitelist", "file", "-f", "mov"]
    assert "*ENTRADA" in fontes["sondar.py"] and '"-show_streams"' in fontes["sondar.py"]
    p = isolado.PREFIXO
    for par in (("--network", "none"), ("--user", "1001:1001"), ("--cap-drop", "ALL"), ("--security-opt", "no-new-privileges"),
                ("--memory", "6g"), ("--pids-limit", "256"), ("--tmpfs", "/tmp:rw,size=512m")):
        assert p[p.index(par[0]) + 1] == par[1], par
    assert "--read-only" in p and "--rm" in p and not {"-e", "--env", "--env-file", "--privileged", "--network=host", "-t", "-it"} & set(p)
    monkeypatch.setenv("RADAR_VIDEO_ISOLADO", "docker")
    pastas = isolado.Pastas(ROBO, ROBO, ROBO / "fontes")
    cmd = isolado.comando("ffprobe", ["-v", "error", "-i", "/ent/1"], pastas, "radar-ffmpeg-x")
    assert cmd == [*p, "--name", "radar-ffmpeg-x", "-v", f"{ROBO}:/ent:ro", "-v", f"{ROBO}:/sai:rw", "-v", f"{ROBO / 'fontes'}:/fontes:ro",
                   "radar-ffmpeg:local", "ffprobe", "-v", "error", "-i", "/ent/1"]
    assert not any(a in ("-e", "--env") for a in cmd)
    monkeypatch.setenv("RADAR_VIDEO_ISOLADO", "locall")                                       # erro de digitação nunca roda fora do contêiner
    with pytest.raises(ErroVideo):
        isolado.comando("ffmpeg", [], pastas)
    monkeypatch.setenv("RADAR_VIDEO_ISOLADO", "local")
    with pytest.raises(ErroVideo):
        isolado.comando("sh", ["-c", "true"], pastas)
    with pytest.raises(ErroVideo):
        isolado.comando("ffmpeg", [], isolado.Pastas(ROBO, Path("/tmp/a:b"), ROBO))          # caminho que quebraria o -v e o grafo


def test_dockerfile_e_requirements_fixados():
    doc = (ROBO / "Dockerfile").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in doc.splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"^ARG BASE=ubuntu:24\.04@sha256:[0-9a-f]{64}$", codigo, re.M) and re.search(r"^FROM \$\{BASE\}$", codigo, re.M)
    assert re.search(r'^ARG FFMPEG_VERSAO=\d+:6\.1\.1-3ubuntu5$', codigo, re.M) and '"ffmpeg=${FFMPEG_VERSAO}"' in codigo
    # e as bibliotecas que fazem o trabalho (o pacote ffmpeg as pede só com ">="): todas as do mesmo pacote-fonte, na mesma versão
    for lib in ("libavcodec60", "libavdevice60", "libavfilter9", "libavformat60", "libavutil58", "libpostproc57", "libswresample4", "libswscale7"):
        assert f'"{lib}=${{FFMPEG_VERSAO}}"' in codigo, lib
    assert "--no-install-recommends" in codigo and re.search(r"^USER 1001:1001$", codigo, re.M)
    assert not re.search(r"CHAVE|TOKEN|SECRET|KEY|EXPOSE|ADD |COPY |curl|wget", codigo)
    req = [l for l in (ROBO / "requirements.txt").read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    pacotes = [l for l in req if not l.lstrip().startswith("--hash")]
    assert pacotes and all(re.match(r"^[a-z0-9-]+==[\d.]+ \\$", l) for l in pacotes), pacotes
    assert sum(l.strip().startswith("--hash=sha256:") for l in req) >= len(pacotes)


# ------------------------------------------------------------------ o ffmpeg no contêiner (produção)
@pytest.fixture(scope="module")
def imagem_docker():
    if shutil.which("docker") is None or subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        pytest.skip("docker indisponível")
    base = os.environ.get("RADAR_VIDEO_TESTE_BASE")
    r = subprocess.run(["docker", "build", "-q", "-t", isolado.IMAGEM, "-f", str(ROBO / "Dockerfile"),
                        *(["--build-arg", f"BASE={base}"] if base else []), str(ROBO)], capture_output=True, timeout=900)
    if r.returncode != 0:
        falhou_no_ci(r.returncode)
        pytest.skip("não foi possível montar a imagem do ffmpeg (sem rede, ou o Docker Hub recusou por limite)")
    return isolado.IMAGEM


def falhou_no_ci(codigo: int) -> None:
    """No GitHub Actions (com o docker), a imagem que não monta FALHA o teste: pulado, o CI ficaria verde sem a prova do contêiner.
    Só o código de saída (a saída do docker build pode citar caminhos)."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.fail(f"a imagem do ffmpeg não montou no CI (docker build saiu com {codigo}): a prova do contêiner sem rede não pode sumir",
                    pytrace=False)


def test_imagem_que_nao_monta_falha_no_ci_e_so_pula_fora_dele(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with pytest.raises(pytest.fail.Exception, match="docker build saiu com 1"):
        falhou_no_ci(1)
    monkeypatch.delenv("GITHUB_ACTIONS")
    falhou_no_ci(1)                                                                            # fora do CI: só pula (sem rede, limite)


@HEVC
def test_receita_no_conteiner_sem_rede(imagem_docker, pastas, acervo, monkeypatch):
    monkeypatch.setenv("RADAR_VIDEO_ISOLADO", "docker")
    monkeypatch.setenv("RADAR_VIDEO_ROBO_CHAVE", "chave-do-robo-de-teste-123")
    isolado.preparar(pastas)
    infos, palavras, plano, rel = _receita(pastas, _entrar(pastas, acervo("vertical"), acervo("hlg")), [sint.FRASES, CURTAS],
                                           gancho="Prazo do eSocial", preset="medium")
    assert rel["conferencia"]["sem_gps"] and -15 <= rel["conferencia"]["lufs"] <= -13
    assert sint.GPS.encode() not in (pastas.sai / "reel.mp4").read_bytes()
    # sem rede (nem para um IP direto) e sem o ambiente do robô
    with pytest.raises(ErroVideo):
        isolado.rodar("rede", "ffprobe", ["-v", "error", "-rw_timeout", "3000000", "-i", "http://1.1.1.1/x.mp4"], pastas, 30)
    isolado.rodar("t", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "data", "-i", "/proc/self/environ",
                                  "-map", "0", "-c", "copy", "-f", "data", "/sai/amb.bin"], pastas)
    amb = (pastas.sai / "amb.bin").read_bytes()
    assert b"chave-do-robo" not in amb and b"RADAR_VIDEO" not in amb
    # e só leitura fora do /sai e do /tmp
    with pytest.raises(ErroVideo):
        isolado.rodar("t", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "lavfi", "-i", "anullsrc", "-t", "0.1",
                                      "/ent/escrito.wav"], pastas)
    assert not (pastas.ent / "escrito.wav").exists()
