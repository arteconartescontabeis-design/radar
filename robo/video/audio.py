"""Radar Artecon — corretor de vídeo (v0.22.0): o áudio de trabalho e as medições.

extrair(): o áudio de cada clipe, num comando só, vira um WAV de 48 kHz mono sem metadados (`-map_metadata -1`), no mesmo zero do
vídeo (`aresample=async=1:first_pts=0`: o atraso do áudio em relação ao vídeo vira silêncio no começo; a pesquisa mediu 0,478 s
preservados) e do MESMO tamanho que o trecho de vídeo usado (quadros a 30 fps × 1600 amostras: completado com silêncio ou cortado).
Os clipes se juntam em fala48k.wav, em que o clipe n começa no quadro `inicio_q` — assim um corte em quadros vale igual para o vídeo
(select) e para o áudio (atrim por amostra), sem deriva. fala16k.wav (16 kHz, 16 bits) é o que vai para a transcrição.

As medições (piso de ruído, silêncios, loudnorm, ebur128) rodam só sobre esses WAV ou sobre a saída, que não têm metadados: o stderr
delas é lido aqui e nunca impresso (isolado.py).
"""
from __future__ import annotations

import json
import math
import re
from array import array

import isolado
from segredo import ErroVideo
from sondar import FPS, entrada

SR = 48000
AMOSTRAS_POR_QUADRO = SR // FPS        # 1600
SR_MEDIDA = 8000                       # amostras para as contas do robô (energia por janela)
LIMPEZA = "highpass=f=80,afftdn=nr=12:nf=-50:tn=1"          # grave abaixo de 80 Hz e redução de ruído
COMPRESSOR = "acompressor=threshold=-24dB:ratio=2.5:attack=15:release=250:makeup=2"


def extrair(infos: list[dict], pastas: isolado.Pastas) -> float:
    """Grava sai/fala48k.wav (24 bits) e sai/fala16k.wav (16 bits); marca infos[i]["inicio_q"]. Devolve a duração, em segundos."""
    entradas, ramos, rotulos, q = [], [], [], 0
    for k, i in enumerate(infos):
        n_amostras = i["quadros"] * AMOSTRAS_POR_QUADRO
        entradas += [*entrada(i), "-i", f"/ent/{i['n']}"]      # v0.44.0: o demuxer do contêiner deste clipe
        ramos.append(f"[{k}:a:0]aresample={SR}:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=mono,"
                     f"apad=whole_len={n_amostras},atrim=end_sample={n_amostras},asetpts=N/SR/TB[a{k}]")
        rotulos.append(f"[a{k}]")
        i["inicio_q"] = q
        q += i["quadros"]
    grafo = ";".join(ramos) + ";" + "".join(rotulos) + f"concat=n={len(infos)}:v=0:a=1[a]"
    isolado.rodar("audio", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", *entradas, "-filter_complex", grafo,
                                      "-map", "[a]", "-vn", "-dn", "-sn", "-map_metadata", "-1", "-map_chapters", "-1",
                                      "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s24le", "/sai/fala48k.wav"],
                  pastas, isolado.TEMPO_SONDAR * 2)
    isolado.rodar("audio16k", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", "/sai/fala48k.wav",
                                         "-map_metadata", "-1", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "/sai/fala16k.wav"],
                  pastas, isolado.TEMPO_SONDAR)
    return q / FPS


def amostras(wav: str, pastas: isolado.Pastas, sr: int = SR_MEDIDA, etapa: str = "medir") -> array:
    """As amostras (16 bits, mono, `sr` Hz) de um WAV do trabalho ou da saída, para as contas de energia."""
    bruto = isolado.rodar(etapa, "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-i", wav, "-map", "0:a:0",
                                            "-ac", "1", "-ar", str(sr), "-f", "s16le", "-c:a", "pcm_s16le", "-"],
                          pastas, isolado.TEMPO_SONDAR, ler="bytes")
    a = array("h")
    a.frombytes(bruto[: len(bruto) // 2 * 2])
    return a


def _db(x: float) -> float:
    return 20 * math.log10(x / 32768) if x > 0 else -120.0


def janelas_db(a: array, sr: int = SR_MEDIDA, janela_s: float = 0.05, pico: bool = True) -> list[float]:
    """Nível por janela (pico ou RMS), em dBFS."""
    n = max(1, int(sr * janela_s))
    out = []
    for k in range(0, len(a) - n + 1, n):
        w = a[k:k + n]
        out.append(_db(max(max(w), -min(w))) if pico else _db(math.sqrt(sum(x * x for x in w) / n)))
    return out


def piso_ruido(a: array) -> float:
    """Piso de ruído (o pico das janelas de 50 ms mais baixas, sem o silêncio digital do atraso do áudio), como o Noise_floor do
    astats, mas sem ir a -inf quando o começo foi completado com zeros."""
    niveis = sorted(x for x in janelas_db(a) if x > -119)
    return niveis[len(niveis) // 20] if niveis else -90.0


def silencios(wav: str, pastas: isolado.Pastas, limiar_db: float, minimo_s: float = 0.25) -> list[tuple[float, float]]:
    """Trechos sem voz (silencedetect, depois de tirar o grave abaixo de 80 Hz). O último vai até o fim, se o arquivo acaba em silêncio."""
    err = isolado.rodar("silencios", "ffmpeg", ["-hide_banner", "-nostats", "-nostdin", "-loglevel", "info", "-i", wav,
                                                "-af", f"highpass=f=80,silencedetect=noise={limiar_db:.1f}dB:duration={minimo_s}",
                                                "-f", "null", "-"], pastas, isolado.TEMPO_SONDAR, ler="stderr")
    ini = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    fim = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", err)]
    if len(fim) < len(ini):
        fim.append(math.inf)
    return [(max(0.0, a), b) for a, b in zip(ini, fim)]


def limiar_silencio(piso_db: float) -> float:
    """Silêncio = até 12 dB acima do piso de ruído medido, entre -50 e -30 dBFS (pesquisa, receita.py)."""
    return min(-30.0, max(-50.0, piso_db + 12))


def loudnorm_medir(wav: str, pastas: isolado.Pastas, alvo: str) -> dict:
    """1ª passada do loudnorm (a 2ª, com linear=true, vai dentro da montagem)."""
    err = isolado.rodar("loudnorm", "ffmpeg", ["-hide_banner", "-nostats", "-nostdin", "-loglevel", "info", "-i", wav,
                                               "-af", f"loudnorm={alvo}:print_format=json", "-f", "null", "-"],
                        pastas, isolado.TEMPO_SONDAR, ler="stderr")
    try:
        d = json.loads(err[err.rindex("{"): err.rindex("}") + 1])
        m = {k: float(d[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, KeyError):
        raise ErroVideo("medida_falhou", "loudnorm") from None
    # a 2ª passada só fica no modo linear (o volume inteiro sobe por igual, sem mexer na dinâmica) se o pico couber no alvo
    alvo_i, alvo_tp = (float(re.search(rf"{k}=(-?[\d.]+)", alvo).group(1)) for k in ("I", "TP"))
    m["linear"] = m["input_tp"] + (alvo_i - m["input_i"]) <= alvo_tp
    return m


def ebur128(arquivo: str, pastas: isolado.Pastas) -> dict:
    """Volume integrado (LUFS) e pico real (dBTP) de um arquivo sem metadados (a saída ou um WAV do trabalho)."""
    err = isolado.rodar("ebur128", "ffmpeg", ["-hide_banner", "-nostats", "-nostdin", "-loglevel", "info", "-i", arquivo, "-map", "0:a:0",
                                              "-af", "ebur128=peak=true", "-f", "null", "-"], pastas, isolado.TEMPO_SONDAR, ler="stderr")
    resumo = err[err.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", resumo)
    p = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", resumo)
    if not i:
        raise ErroVideo("medida_falhou", "ebur128")
    return {"lufs": float(i.group(1)), "pico_dbtp": float(p.group(1)) if p and p.group(1) != "-inf" else -120.0}


def atraso_amostras(cadeia: str, pastas: isolado.Pastas) -> int:
    """Quantas amostras (a 48 kHz) a cadeia de filtros atrasa o som. O afftdn trabalha em janelas e devolve a voz 1200 amostras (25 ms)
    depois no ffmpeg 6.1: sem descontar, a voz ficaria atrás da boca. Medido na hora (silêncio com ruído fraco e um tom que começa em
    0,5 s, antes e depois da cadeia, lado a lado), para valer com o ffmpeg que estiver instalado."""
    grafo = (f"aevalsrc=exprs='if(gte(t,0.5),0.5*sin(2*PI*440*(t-0.5)),0)+0.002*(random(1)-0.5)':s={SR}:d=1.2,asplit[a][b];"
             f"[b]{cadeia}[c];[a][c]join=inputs=2:channel_layout=stereo[o]")
    bruto = isolado.rodar("atraso", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-filter_complex", grafo, "-map", "[o]",
                                               "-f", "s16le", "-c:a", "pcm_s16le", "-"], pastas, isolado.TEMPO_SONDAR, ler="bytes")
    a = array("h")
    a.frombytes(bruto[: len(bruto) // 4 * 4])
    limiar = 0.1 * 32768
    antes = next((k for k, v in enumerate(a[0::2]) if abs(v) > limiar), None)
    depois = next((k for k, v in enumerate(a[1::2]) if abs(v) > limiar), None)
    if antes is None or depois is None or not 0 <= depois - antes <= SR // 5:
        raise ErroVideo("medida_falhou", "atraso")
    return depois - antes
