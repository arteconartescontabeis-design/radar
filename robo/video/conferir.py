"""Radar Artecon — corretor de vídeo (v0.22.0): a conferência automática da saída, antes de liberar para o administrador.

  * ffprobe: só um vídeo H.264 High 1080×1920 a 30/1 (taxa fixa, exigência do Facebook) em yuv420p, só um áudio AAC 48 kHz em 2
    canais, começando no zero; duração de 3 a 960 s (v0.33.0: o Instagram aceita reel de até 15 min pela API; acima de 90 s o
    Facebook não aceita, e a tela avisa que sai só no Instagram); sem marcas do celular nos metadados;
  * ebur128 sobre a saída: volume integrado a até 1 LU do alvo das Configurações (-14 LUFS: de -15 a -13);
  * os bytes do MP4, caixa por caixa (sem ler o mdat): `moov` antes do `mdat` (faststart), nenhuma lista de edição (`elst`) e nada de
    local — nem a caixa ©xyz/loci, nem as chaves de local da Apple, nem uma coordenada ISO 6709 no moov ("no edit lists, moov atom at
    the front", Instagram);
  * até 300 MB (o máximo do reel pela API do Instagram; a tela limita o bruto a 500 MB, e o corrigido de uns minutos fica bem abaixo).
Uma falha vira ErroVideo("conferencia_falhou") com o nome fixo de cada item que não passou (nunca um valor lido do arquivo).
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

import audio
import isolado
from segredo import ErroVideo

DURACAO = (3.0, 960.0)                 # v0.33.0: o teto acompanha a entrada bruta (sondar.TOTAL_MAX_S)
BYTES_MAX = 300 * 1024 * 1024
CONTEINERES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"udta", b"dinf", b"mvex", b"meta", b"ilst", b"tref"}
PROIBIDAS = {b"elst": "edit_list", b"\xa9xyz": "gps", b"loci": "gps"}
ETIQUETAS_OK = {"major_brand", "minor_version", "compatible_brands", "encoder", "handler_name", "vendor_id", "language"}
ISO6709 = re.compile(rb"[+-]\d{1,3}\.\d{2,}[+-]\d{1,3}\.\d{2,}")


def _caixas(dados: bytes, ini: int, fim: int):
    """As caixas de um trecho (tipo, início do conteúdo, fim), descendo nos contêineres."""
    k = ini
    while k + 8 <= fim:
        tam, tipo = struct.unpack(">I4s", dados[k:k + 8])
        cab = 8
        if tam == 1 and k + 16 <= fim:
            tam, cab = struct.unpack(">Q", dados[k + 8:k + 16])[0], 16
        elif tam == 0:
            tam = fim - k
        if tam < cab or k + tam > fim:
            yield b"?bad", k, fim
            return
        yield tipo, k + cab, k + tam
        if tipo in CONTEINERES:
            filhos = k + cab
            if tipo == b"meta" and dados[filhos + 4:filhos + 8] not in (b"hdlr", b"keys", b"ilst"):
                filhos += 4                              # o meta do ISO tem versão e flags antes das caixas; o do QuickTime, não
            yield from _caixas(dados, filhos, k + tam)
        k += tam


def bytes_mp4(arquivo: Path) -> dict:
    """Ordem das caixas do topo e o que há dentro do moov (lido inteiro; o mdat só é pulado)."""
    topo, moov = [], b""
    with arquivo.open("rb") as f:
        total, k = arquivo.stat().st_size, 0
        while k + 8 <= total:
            f.seek(k)
            cab = f.read(16)
            tam, tipo = struct.unpack(">I4s", cab[:8])
            if tam == 1:
                tam = struct.unpack(">Q", cab[8:16])[0]
            elif tam == 0:
                tam = total - k
            if tam < 8:
                topo.append(b"?bad")
                break
            topo.append(tipo)
            if tipo == b"moov" and tam <= 64 * 1024 * 1024:
                f.seek(k)
                moov = f.read(tam)
            k += tam
    achadas = {t for t, _, _ in _caixas(moov, 0, len(moov))}
    return {"topo": [t.decode("latin-1") for t in topo], "moov_antes": b"moov" in topo and b"mdat" in topo
            and topo.index(b"moov") < topo.index(b"mdat"),
            "proibidas": sorted({PROIBIDAS[t] for t in achadas if t in PROIBIDAS}),
            "local_no_moov": bool(ISO6709.search(moov)) or any(x in moov.lower() for x in (b"iso6709", b"location", b"com.apple")),
            "invalido": b"?bad" in achadas or b"?bad" in topo or not moov}


def conferir(pastas: isolado.Pastas, cfg: dict, saida: str = "reel.mp4") -> dict:
    """Confere sai/<saida>. Devolve a parte "conferencia" do relatório; se algo não passou, ErroVideo com os itens."""
    arquivo = pastas.sai / saida
    falhas: list[str] = []
    try:
        d = json.loads(isolado.rodar("conferir", "ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json",
                                                             f"/sai/{saida}"], pastas, isolado.TEMPO_SONDAR))
    except (ErroVideo, ValueError):
        raise ErroVideo("conferencia_falhou", "conferir", ["leitura"]) from None
    fluxos = d.get("streams") or []
    fmt = d.get("format") or {}
    vs = [s for s in fluxos if s.get("codec_type") == "video"]
    as_ = [s for s in fluxos if s.get("codec_type") == "audio"]
    v, a = (vs[0] if vs else {}), (as_[0] if as_ else {})
    if len(vs) != 1 or len(as_) != 1 or len(fluxos) != 2:
        falhas.append("faixas")
    if v.get("codec_name") != "h264" or v.get("profile") != "High" or v.get("pix_fmt") != "yuv420p":
        falhas.append("codec")
    if (v.get("width"), v.get("height")) != (1080, 1920):
        falhas.append("resolucao")
    if v.get("r_frame_rate") != "30/1" or v.get("avg_frame_rate") != "30/1":
        falhas.append("fps")
    if a.get("codec_name") != "aac" or a.get("sample_rate") != "48000" or a.get("channels") != 2:
        falhas.append("audio")
    inicio = [abs(float(s.get("start_time") or 0)) for s in (v, a)] + [abs(float(fmt.get("start_time") or 0))]
    if max(inicio) > 0.05:
        falhas.append("inicio")
    dur = float(fmt.get("duration") or 0)
    if not DURACAO[0] <= dur <= DURACAO[1]:
        falhas.append("duracao")
    etiquetas = {k.lower() for s in (fmt, v, a) for k in (s.get("tags") or {})}
    if etiquetas - ETIQUETAS_OK:
        falhas.append("metadados")
    tamanho = arquivo.stat().st_size
    if tamanho > BYTES_MAX:
        falhas.append("tamanho")
    caixas = bytes_mp4(arquivo)
    if not caixas["moov_antes"]:
        falhas.append("faststart")
    falhas += caixas["proibidas"]
    if caixas["local_no_moov"] and "gps" not in falhas:
        falhas.append("gps")
    if caixas["invalido"]:
        falhas.append("caixas")
    volume = audio.ebur128(f"/sai/{saida}", pastas)
    alvo = float(cfg.get("lufs", -14))
    if abs(volume["lufs"] - alvo) > 1.0:
        falhas.append("volume")
    if falhas:
        raise ErroVideo("conferencia_falhou", "conferir", sorted(set(falhas)))
    return {"moov_inicio": True, "sem_edit_list": True, "sem_gps": True, "codec": "h264 high", "fps": 30,
            "audio": "aac 48 kHz 2 canais", "lufs": round(volume["lufs"], 1), "pico_dbtp": round(volume["pico_dbtp"], 1),
            "duracao_s": round(dur, 2), "bytes": tamanho}
