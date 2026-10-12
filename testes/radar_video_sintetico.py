"""Vídeos SINTÉTICOS para os testes do corretor de vídeo (v0.22.0). Nada de gravação real no repositório público.

A "voz" é um som harmônico (140 Hz e harmônicas, com vibrato e sílabas a 5 Hz) só nos intervalos das palavras, sobre um ruído de sala
fraco (~ -55 dBFS): o teste sabe exatamente onde cada palavra começa e acaba, e o silencedetect acha as pausas como numa gravação.
As palavras simuladas vêm na forma de exibição da transcrição (com pontuação e algarismos). A imagem é o testsrc2 do ffmpeg. O local
gravado nos metadados (como o celular faz) é sempre a coordenada 0,0 — nunca um lugar de verdade.
"""
from __future__ import annotations

import array
import math
import random
import shutil
import subprocess
import wave
from pathlib import Path

SR = 48000
GPS = "+00.0000+000.0000/"
F = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]

# Fixture principal: 1,2 s de silêncio no começo, uma pausa de 1,1 s dentro da 1ª frase, 0,9 s entre as frases e 1,6 s no fim
FRASES = [("Olá,", 1.20, 1.50), ("hoje", 1.60, 1.85), ("vamos", 1.95, 2.25), ("falar", 3.35, 3.65), ("do", 3.72, 3.85),
          ("prazo.", 3.95, 4.40), ("O", 5.30, 5.40), ("eSocial", 5.50, 6.00), ("vence", 6.10, 6.45), ("dia", 6.55, 6.80),
          ("15.", 6.90, 7.40)]
DURACAO = 9.0


def tem_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def ffmpeg_tem(*nomes: str) -> bool:
    """Os codificadores e filtros que o teste usa (o ffmpeg do Ubuntu tem todos)."""
    saida = subprocess.run([*F[:2], "-encoders"], capture_output=True, text=True).stdout + \
        subprocess.run([*F[:2], "-filters"], capture_output=True, text=True).stdout
    return all(f" {n} " in saida for n in nomes)


def voz(destino: Path, palavras: list[tuple[str, float, float]], duracao: float, ruido: float = 0.0018, semente: int = 7,
        volume: float = 0.22) -> Path:
    """WAV mono 48 kHz 16 bits: o som de "fala" em cada palavra, ruído de sala em tudo."""
    n = int(duracao * SR)
    rnd, y = random.Random(semente), 0.0
    a = array.array("h", bytes(2 * n))
    for i in range(n):
        y = 0.85 * y + 0.15 * rnd.gauss(0, 1)
        a[i] = int(y * ruido * 32767 * 2.5)
    for _, ini, fim in palavras:
        for i in range(int(ini * SR), min(n, int(fim * SR))):
            t = i / SR
            env = min(1.0, (t - ini) / 0.015, (fim - t) / 0.015) * (0.65 + 0.35 * math.sin(2 * math.pi * 5 * (t - ini)))
            f0 = 140 * (1 + 0.02 * math.sin(2 * math.pi * 6 * t))
            s = sum(amp * math.sin(2 * math.pi * f0 * h * t) for h, amp in ((1, 0.55), (2, 0.25), (3, 0.12), (5, 0.08)))
            a[i] = max(-32768, min(32767, a[i] + int(env * volume * s * 32767)))
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(a.tobytes())
    return destino


def video(destino: Path, fala: Path | None, w: int, h: int, fps: int, duracao: float, codec: str = "h264", hdr: str | None = None,
          rotacao: int = 0, gps: bool = True, atraso: float = 0.0, formato: str = "mp4", piscar: list[tuple[str, float, float]] = ()) -> Path:
    """MP4/MOV como o do celular: testsrc2 + a "voz" em AAC, com o local nos metadados. rotacao=90: o quadro é gravado deitado
    (h×w) com a rotação de exibição, como o iPhone; hdr: 'hlg' ou 'pq' (HEVC 10 bits BT.2020); atraso: o áudio começa depois do
    vídeo (a "voz" precisa ter sido gerada com as palavras adiantadas do mesmo tanto, para o clipe ficar sincronizado). piscar: o
    terço de cima da imagem fica branco durante cada palavra (no tempo do vídeo) — é o que o teste de sincronia compara com a voz."""
    larg, alt = (h, w) if rotacao else (w, h)
    if piscar:
        quando = "+".join(f"between(t,{a},{b})" for _, a, b in piscar)
        # deitado com rotação de 90° (anti-horário na exibição): o alto da imagem de pé é a direita do quadro gravado
        x, y, bw, bh = ("2*iw/3" if rotacao == 90 else "0", "0", "iw/3", "ih") if rotacao else ("0", "0", "iw", "ih/3")
        src = f"color=c=0x404040:s={larg}x{alt}:r={fps}:d={duracao},drawbox=x={x}:y={y}:w={bw}:h={bh}:color=white:t=fill:enable='{quando}'"
    else:
        src = f"testsrc2=s={larg}x{alt}:r={fps}:d={duracao}"
    src += ",format=yuv420p10le" if hdr else ""
    cmd = [*F, "-f", "lavfi", "-i", src]
    if fala is not None:
        cmd += [*(["-itsoffset", f"{atraso}"] if atraso else []), "-i", str(fala), "-map", "0:v", "-map", "1:a", "-c:a", "aac",
                "-b:a", "96k", "-shortest"]
    if codec == "hevc":
        trc = {"hlg": "arib-std-b67", "pq": "smpte2084"}.get(hdr or "", "bt709")
        prim, mat = ("bt2020", "bt2020nc") if hdr else ("bt709", "bt709")
        cmd += ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", f"log-level=error:colorprim={prim}:transfer={trc}:colormatrix={mat}",
                "-color_primaries", prim, "-color_trc", trc, "-colorspace", mat, "-tag:v", "hvc1"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p"]
    if gps:
        cmd += ["-metadata", f"location={GPS}", "-metadata", "make=Celular de Teste", "-metadata", "model=Modelo Ficticio"]
    tmp = destino.with_name(destino.name + "_tmp") if rotacao else destino
    subprocess.run([*cmd, "-f", formato, str(tmp)], check=True, capture_output=True)
    if rotacao:
        subprocess.run([*F, "-display_rotation", str(rotacao), "-f", formato, "-i", str(tmp), "-c", "copy",
                        *(["-metadata", f"location={GPS}"] if gps else []), "-f", formato, str(destino)], check=True, capture_output=True)
        tmp.unlink()
    return destino


def palavras(lista: list[tuple[str, float, float]], deslocamento: float = 0.0) -> list[dict]:
    """As palavras como a transcrição devolve (forma de exibição), na linha do tempo de fala48k.wav."""
    return [{"texto": t, "ini": round(a + deslocamento, 3), "fim": round(b + deslocamento, 3)} for t, a, b in lista]


def _amostras(arquivo: Path, sr: int = SR) -> array.array:
    bruto = subprocess.run([*F[:2], "-loglevel", "error", "-nostdin", "-i", str(arquivo), "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                            "-f", "s16le", "-"], check=True, capture_output=True).stdout
    a = array.array("h")
    a.frombytes(bruto[: len(bruto) // 2 * 2])
    return a


def nivel_db(arquivo: Path, ini: float, fim: float, sr: int = SR) -> float:
    """RMS (dBFS) do áudio entre ini e fim."""
    a = _amostras(arquivo, sr)[int(ini * sr):int(fim * sr)]
    return 20 * math.log10(max(1e-9, math.sqrt(sum(x * x for x in a) / max(1, len(a))) / 32768))


def inicio_da_voz(arquivo: Path, depois_de: float = 0.0, limiar_db: float = -30.0) -> float:
    """Primeiro instante (janelas de 1 ms) em que o pico passa do limiar."""
    a, n = _amostras(arquivo), SR // 1000
    for k in range(int(depois_de * SR), len(a) - n, n):
        w = a[k:k + n]
        if max(max(w), -min(w)) > 32768 * 10 ** (limiar_db / 20):
            return k / SR
    return math.inf


def voz_por_quadro(arquivo: Path, fps: int = 30, limiar_db: float = -40.0) -> list[bool]:
    """Para cada quadro (1/30 s) da saída: tem voz (RMS acima do limiar)? Na saída a -14 LUFS, a "voz" fica entre -12 e -33 dBFS
    (as sílabas) e o ruído das pausas perto de -49."""
    a, n = _amostras(arquivo), SR // fps
    return [math.sqrt(sum(x * x for x in a[k:k + n]) / n) > 32768 * 10 ** (limiar_db / 20) for k in range(0, len(a) - n + 1, n)]


def luz_do_alto(arquivo: Path) -> list[float]:
    """Para cada quadro: a luz média da faixa y 100..500 (acima do gancho e da legenda), onde o teste pisca o branco."""
    bruto = subprocess.run([*F[:2], "-loglevel", "error", "-nostdin", "-i", str(arquivo), "-map", "0:v:0",
                            "-vf", "crop=1080:400:0:100,scale=8:8,format=gray", "-f", "rawvideo", "-"], check=True, capture_output=True).stdout
    return [sum(bruto[k:k + 64]) / 64 for k in range(0, len(bruto) - 63, 64)]


def subidas(marcas: list[bool]) -> list[int]:
    """Os quadros em que a marca liga (de False para True)."""
    return [k for k in range(len(marcas)) if marcas[k] and (k == 0 or not marcas[k - 1])]
