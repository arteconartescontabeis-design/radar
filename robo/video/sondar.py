"""Radar Artecon — corretor de vídeo (v0.22.0): sondagem e recusa dos clipes (entrada não confiável).

Cada clipe (bruto/<id>/<n>, baixado como ent/<n>, sem extensão) passa por, nesta ordem:
  1. tamanho: até o declarado no envio (radar_videos.partes[].bytes) — senão `arquivo_grande`;
  2. a assinatura do contêiner no começo do arquivo — `ftyp` no byte 4 (MP4 e MOV do celular começam assim) ou, v0.44.0, o EBML do
     WEBM nos bytes 0–3 (a gravação do teleprompter pelo navegador); uma playlist .m3u8 ou um HTML renomeado, não — `formato`;
  3. ffprobe com `-protocol_whitelist file -f <demuxer da assinatura>` (mov para MP4/MOV, matroska,webm para WEBM, à força: nada de
     adivinhar o formato pelo conteúdo, nada de protocolo de rede) e `format_name` igual ao do demuxer — `formato`;
  4. vídeo e áudio presentes (`formato` sem vídeo, `sem_audio` sem áudio), de pé depois do giro (`deitado`), e a soma de até 120 s
     (`longo_demais`). O WEBM do navegador sem a duração escrita (o MediaRecorder não grava; a tela conserta antes de subir) cai
     na mesma recusa `formato` da duração fora de 0,2–3600 s.
O JSON do ffprobe traz o local GPS (format.tags.location) e o modelo do celular: ele só é lido aqui, e só os campos técnicos saem
desta função. Usamos só o 1º vídeo e o 1º áudio (0:v:0, 0:a:0); faixas de dados e de legenda do celular ficam de fora (-dn -sn).
v0.44.0: cada clipe carrega o próprio demuxer ("cont") e as outras etapas (áudio, montagem, capa) pedem entrada(info) em vez do
ENTRADA fixo: o WEBM nunca é lido com o demuxer do MOV, nem o contrário.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import isolado
from segredo import ErroVideo

FPS = 30
FORMATO = "mov,mp4,m4a,3gp,3g2,mj2"
FORMATO_WEBM = "matroska,webm"         # v0.44.0: a gravação do teleprompter pelo navegador (Chrome/Android); o Safari grava MP4
TOTAL_MAX_S = 960.0                    # soma dos clipes (v0.33.0: o Instagram aceita reel de até 15 min — 900 s — pela API; 960 s dão folga)
ENTRADA = ["-protocol_whitelist", "file", "-f", "mov"]     # vem antes de todo "-i /ent/<n>" de MP4/MOV (o padrão de sempre)


def entrada(info: dict) -> list[str]:
    """v0.44.0: as opções de entrada do ffmpeg/ffprobe para ESTE clipe (o demuxer preso ao contêiner visto na sondagem)."""
    return ["-protocol_whitelist", "file", "-f", FORMATO_WEBM if info.get("cont") == "webm" else "mov"]


def _num(v, padrao: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return padrao
    return x if math.isfinite(x) else padrao


def _taxa(v: str | None) -> float:
    try:
        a, b = str(v or "0/1").split("/")
        return float(a) / float(b) if float(b) else 0.0
    except ValueError:
        return 0.0


def _rotacao(video: dict) -> int:
    for sd in video.get("side_data_list") or []:
        if isinstance(sd, dict) and "rotation" in sd:
            return int(_num(sd["rotation"]))
    return int(_num((video.get("tags") or {}).get("rotate")))


def sondar(n: int, pastas: isolado.Pastas, bytes_declarados: int | None = None) -> dict:
    """Confere um clipe e devolve só o técnico: {n, w, h (de pé, depois do giro), rot, girado, codec, hdr, fps, dur, quadros, bytes}."""
    arquivo = pastas.ent / str(n)
    try:
        tamanho = arquivo.stat().st_size
        with arquivo.open("rb") as f:
            cabeca = f.read(12)
    except OSError:
        raise ErroVideo("formato", "sondar") from None
    if bytes_declarados is not None and tamanho > bytes_declarados:
        raise ErroVideo("arquivo_grande", "sondar")
    # v0.44.0: a assinatura decide o contêiner (e o demuxer forçado): ftyp no byte 4 = MP4/MOV; EBML nos bytes 0–3 = WEBM do navegador
    if len(cabeca) >= 12 and cabeca[4:8] == b"ftyp":
        cont, esperado = "mov", FORMATO
    elif len(cabeca) >= 4 and cabeca[:4] == b"\x1a\x45\xdf\xa3":
        cont, esperado = "webm", FORMATO_WEBM
    else:
        raise ErroVideo("formato", "sondar")
    try:
        saida = isolado.rodar("sondar", "ffprobe", ["-v", "error", *entrada({"cont": cont}), "-show_streams", "-show_format", "-of", "json",
                                                    f"/ent/{n}"], pastas, isolado.TEMPO_SONDAR)
        d = json.loads(saida)
    except (ErroVideo, ValueError):
        raise ErroVideo("formato", "sondar") from None
    fmt = d.get("format") or {}
    if fmt.get("format_name") != esperado:
        raise ErroVideo("formato", "sondar")
    fluxos = [s for s in d.get("streams") or [] if isinstance(s, dict)]
    v = next((s for s in fluxos if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in fluxos if s.get("codec_type") == "audio"), None)
    if v is None:
        raise ErroVideo("formato", "sondar")
    if a is None:
        raise ErroVideo("sem_audio", "sondar")
    rot = _rotacao(v)
    w, h = int(_num(v.get("width"))), int(_num(v.get("height")))
    if not (16 <= w <= 8192 and 16 <= h <= 8192):
        raise ErroVideo("formato", "sondar")
    girado = abs(rot) % 180 == 90
    if girado:
        w, h = h, w                                     # o ffmpeg gira sozinho (autorotate): o filtro recebe o quadro já de pé
    if w > h:
        raise ErroVideo("deitado", "sondar")
    fps = _taxa(v.get("avg_frame_rate")) or _taxa(v.get("r_frame_rate"))
    dur_v = _num(v.get("duration")) or _num(fmt.get("duration"))
    if not (1 <= fps <= 240) or not (0.2 <= dur_v <= 3600):
        raise ErroVideo("formato", "sondar")
    trc = v.get("color_transfer") or ""
    return {"n": n, "w": w, "h": h, "cont": cont, "rot": rot, "girado": girado, "codec": str(v.get("codec_name") or "")[:20],
            "hdr": "pq" if trc == "smpte2084" else "hlg" if trc == "arib-std-b67" else None,
            "fps": round(fps, 3), "dur": round(dur_v, 3),
            # quadros a 30 fps que a montagem usa deste clipe: para baixo, para nunca pedir um quadro que o vídeo não tem (o áudio do
            # clipe é cortado ou completado no mesmo tamanho, em audio.extrair)
            "quadros": max(1, math.floor(dur_v * FPS + 1e-6)), "bytes": tamanho}


def sondar_todas(partes: list[dict], pastas: isolado.Pastas) -> list[dict]:
    """partes = radar_videos.partes ([{n, tipo, bytes}], na ordem). Recusa a soma acima de 120 s."""
    if not 1 <= len(partes) <= 12:
        raise ErroVideo("formato", "sondar")
    infos = [sondar(int(p["n"]), pastas, int(p["bytes"]) if p.get("bytes") is not None else None) for p in partes]
    if sum(i["dur"] for i in infos) > TOTAL_MAX_S:
        raise ErroVideo("longo_demais", "sondar")
    return infos


def resumo(infos: list[dict]) -> dict:
    """A parte "entrada" do relatório (só o técnico): clipes, duração bruta, resolução e taxa do 1º clipe, HDR e giro."""
    return {"clipes": len(infos), "duracao_s": round(sum(i["dur"] for i in infos), 1),
            "resolucao": f"{infos[0]['w']}x{infos[0]['h']}" if infos else None, "fps": round(infos[0]["fps"]) if infos else None,
            "hdr": next((i["hdr"] for i in infos if i["hdr"]), None), "girado": any(i["girado"] for i in infos)}
