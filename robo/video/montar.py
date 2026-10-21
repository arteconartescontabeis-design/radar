"""Radar Artecon — corretor de vídeo (v0.22.0): a montagem do reel (comandos testados com o ffmpeg 6.1.1 do Ubuntu 24.04).

Entra: os clipes (ent/<n>), o plano de cortes (cortes.planejar), sai/fala48k.wav (audio.extrair), sai/legenda.ass (legenda.gravar)
e sai/cartela.png (cartela.desenhar). Sai: sai/reel.mp4 e os 4 quadros sai/q1..q4.jpg.

  * áudio: os trechos do plano por amostra (atrim, quadro × 1600), 12 ms de esmaecer em cada emenda, highpass 80 Hz, afftdn
    (redução de ruído; o atraso dele, 25 ms, é descontado) e compressor leve; a fala a -24 LUFS com os picos limitados (para o
    loudnorm caber no modo linear) e o loudnorm em duas passadas (a 2ª com linear=true) para o volume das Configurações (-14 LUFS,
    pico de -1,5 dBTP); as 1024 amostras de atraso do AAC também são descontadas: a voz fica no instante da boca;
    nada de crossfade na voz: depois da última palavra ela só esmaece sobre o ruído de fundo e entra o silêncio da cartela;
  * imagem, por clipe: 30 quadros por segundo constantes a partir do zero (o mesmo zero do áudio), os quadros do plano (select),
    recorte para 9:16 sem distorcer, 1080×1920 em BT.709 (HLG convertido direto, sem mapeamento de tons; PQ com tonemap hable) e cor
    leve (eq), limitada pela luz medida no próprio clipe (signalstats, só nos quadros-chave); depois os clipes em sequência, a
    legenda e o gancho (libass, DM Sans) e a transição de 0,4 s para a cartela, que começa 0,05 s depois da última palavra;
  * saída: H.264 High 4.1, 30/1, GOP de 2 s, AAC 48 kHz estéreo 128 kb/s, sem metadados (-map_metadata -1: o GPS e o modelo do celular
    não passam), moov no começo (faststart) e sem lista de edição (-use_editlist 0 com +negative_cts_offsets, para vídeo e áudio
    começarem no zero) — "no edit lists, moov atom at the front" (Instagram) e GOP de 2 a 5 s (Facebook). Passando de ~250 MB,
    refaz com taxa menor.
  * v0.33.0, a capa (a aba Vídeo): o quadro que o administrador escolheu (ajustes.capa_q, na linha original) vira sai/capa.jpg,
    1080×1920, com o mesmo recorte, a mesma cor e o mesmo eq do vídeo, mas sem a legenda e sem o gancho (a cadeia de _render sem o
    ass). Caiu num trecho cortado (um corte automático que mudou desde a escolha): vai para o quadro que ficou mais perto, com o aviso
    capa_movida. em_ms é o instante dele no vídeo (o thumb_offset da API do Instagram, para quando a publicação do reel for automática).
"""
from __future__ import annotations

import re

import audio
import cortes
import isolado
from segredo import ErroVideo
from sondar import FPS, entrada

LARG, ALT = 1080, 1920
TRANSICAO = 0.4
EQ = {"contrast": 1.04, "brightness": 0.01, "saturation": 1.08}
LIMITE_BYTES = 250 * 1024 * 1024
TAXAS = (("12M", "24M"), ("8M", "16M"))
AAC_AQUECIMENTO = 1024                 # amostras de atraso do codificador AAC do ffmpeg
PRE_NIVEL = -24.0                      # LUFS da fala antes do loudnorm (com os picos limitados)
PICO_ALVO = -1.5                       # dBTP


def _corte_9x16(w: int, h: int) -> str:
    """Recorte central para 9:16 (no quadro já de pé), sem distorcer; vazio se já é 9:16."""
    if w * 16 > h * 9:
        cw, ch = (h * 9 // 16) // 2 * 2, h
    else:
        cw, ch = w, (w * 16 // 9) // 2 * 2
    return f"crop={cw}:{ch}" if abs(cw - w) > 2 or abs(ch - h) > 2 else ""


def _conversao(info: dict, w: int = LARG, h: int = ALT) -> str:
    """Escala e cor para SDR BT.709 em w×h."""
    if info["hdr"] == "hlg":
        # o HLG foi feito para ser compatível com o SDR: conversão direta, sem mapeamento de tons (com hable o tom médio caía de 119
        # para 78 na pesquisa)
        return (f"zscale=w={w}:h={h}:filter=lanczos:tin=arib-std-b67:pin=bt2020:min=bt2020nc:t=bt709:p=bt709:m=bt709:r=tv,"
                "format=yuv420p")
    if info["hdr"] == "pq":
        return (f"zscale=w={w}:h={h}:filter=lanczos:tin=smpte2084:pin=bt2020:min=bt2020nc:t=linear:npl=100,format=gbrpf32le,"
                "zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")
    return f"scale={w}:{h}:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p"


def medir_luz(info: dict, pastas: isolado.Pastas) -> dict:
    """Luz média (YAVG) e alta (YHIGH) do clipe já convertido, nos quadros-chave, em escala pequena. O resultado vai para um arquivo
    (metadata=print:file), não para o stderr: nada do cabeçalho do clipe é lido."""
    n = info["n"]
    cadeia = ",".join(x for x in [_corte_9x16(info["w"], info["h"]), _conversao(info, 270, 480), "signalstats",
                                  f"metadata=mode=print:file=/sai/luz{n}.txt"] if x)
    isolado.rodar("luz", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-skip_frame", "nokey", *entrada(info),
                                    "-i", f"/ent/{n}", "-map", "0:v:0", "-an", "-dn", "-sn", "-vf", cadeia, "-f", "null", "-"],
                  pastas, isolado.TEMPO_SONDAR)
    texto = (pastas.sai / f"luz{n}.txt").read_text(encoding="utf-8", errors="replace")
    media = lambda nome: (lambda xs: sum(xs) / len(xs) if xs else None)(
        [float(x) for x in re.findall(rf"lavfi\.signalstats\.{nome}=(\d+(?:\.\d+)?)", texto)])
    return {"yavg": media("YAVG"), "yhigh": media("YHIGH")}


def ajuste_cor(luz: dict) -> str:
    """eq leve; escuro demais ganha gama 1,15, claro demais 0,92; com o alto já perto do branco (YHIGH > 230), sem contraste extra."""
    eq = dict(EQ)
    if luz.get("yavg") is not None and luz["yavg"] < 85:
        eq["gamma"] = 1.15
    elif luz.get("yavg") is not None and luz["yavg"] > 150:
        eq["gamma"] = 0.92
    if luz.get("yhigh") is not None and luz["yhigh"] > 230:
        eq["contrast"] = 1.0
    return "eq=" + ":".join(f"{k}={v}" for k, v in eq.items())


def audio_limpo(plano: dict, pastas: isolado.Pastas, lufs: float) -> tuple[float, dict]:
    """sai/audio_limpo.wav: os trechos do plano, limpos, com o silêncio do fim (pad_q), em ponto flutuante (o makeup do compressor,
    ×2, nunca satura). Depois, o nível: a fala vai a -24 LUFS e os picos a no máximo 1 dB abaixo do que o alvo permite (pico real
    de -1,5 dBTP menos o volume das Configurações: 12,5 dB de folga para -14 LUFS), num limitador com antecipação e atraso descontado.
    Sem isso, a voz com picos mais de 12,5 dB acima do volume (comum na fala) faria o loudnorm desistir do modo linear e cair no
    dinâmico, que erra o alvo (-14,8 LUFS medidos num teste sintético de 8 s). Devolve a duração e a 1ª passada do loudnorm."""
    ts = plano["trechos"]
    atraso = audio.atraso_amostras(audio.LIMPEZA, pastas)
    ramos = [f"[s{k}]atrim=start_sample={a * audio.AMOSTRAS_POR_QUADRO}:end_sample={b * audio.AMOSTRAS_POR_QUADRO},asetpts=N/SR/TB,"
             f"afade=t=in:d=0.012,afade=t=out:st={(b - a) / FPS - 0.012:.4f}:d=0.012[a{k}]" for k, (a, b) in enumerate(ts)]
    grafo = (f"[0:a]asplit={len(ts)}" + "".join(f"[s{k}]" for k in range(len(ts))) + ";" + ";".join(ramos) + ";"
             + "".join(f"[a{k}]" for k in range(len(ts))) + f"concat=n={len(ts)}:v=0:a=1,"
             # o atraso da redução de ruído (afftdn: 25 ms) é descontado: completa o fim e tira o mesmo tanto do começo
             + (f"apad=pad_len={atraso}," if atraso else "") + audio.LIMPEZA
             + (f",atrim=start_sample={atraso},asetpts=N/SR/TB" if atraso else "") + "," + audio.COMPRESSOR
             + (f",apad=pad_len={plano['pad_q'] * audio.AMOSTRAS_POR_QUADRO}" if plano.get("pad_q") else "") + "[a]")
    isolado.rodar("audio_limpo", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", "/sai/fala48k.wav",
                                            "-filter_complex", grafo, "-map", "[a]", "-map_metadata", "-1", "-c:a", "pcm_f32le",
                                            "-ar", str(audio.SR), "/sai/audio_comp.wav"], pastas, isolado.TEMPO_SONDAR * 2)
    ganho = min(30.0, PRE_NIVEL - audio.ebur128("/sai/audio_comp.wav", pastas)["lufs"])
    folga, margem = PICO_ALVO - lufs, 1.0
    for _ in range(4):                                  # limitar baixa um pouco o volume: confere e aperta o teto até caber
        teto = 10 ** ((PRE_NIVEL + folga - margem) / 20)
        isolado.rodar("nivel", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", "/sai/audio_comp.wav",
                                          "-af", f"volume={ganho:.2f}dB,alimiter=limit={min(1.0, max(0.0625, teto)):.5f}:attack=5:"
                                          "release=50:level=false:latency=true", "-map_metadata", "-1", "-c:a", "pcm_f32le",
                                          "-ar", str(audio.SR), "/sai/audio_limpo.wav"], pastas, isolado.TEMPO_SONDAR)
        medida = audio.loudnorm_medir("/sai/audio_limpo.wav", pastas, f"I={lufs:g}:TP={PICO_ALVO:g}:LRA=11")
        if medida["linear"]:
            break
        margem += (medida["input_tp"] - medida["input_i"]) - folga + 0.3
    return (plano["fala_q"] + plano.get("pad_q", 0)) / FPS, medida


def _render(infos: list[dict], plano: dict, pastas: isolado.Pastas, cfg: dict, medida: dict, cores: dict, preset: str,
            taxa: tuple[str, str]) -> None:
    locais = cortes.por_clipe(plano, infos)
    usados = [i for i in infos if i["n"] in locais]
    fala = (plano["fala_q"] + plano.get("pad_q", 0)) / FPS
    cartela_s = float(cfg.get("cartela_s", 3))
    entradas, grafo = [], []
    for k, i in enumerate(usados):
        entradas += [*entrada(i), "-i", f"/ent/{i['n']}"]      # v0.44.0: o demuxer do contêiner deste clipe
        sel = "+".join(f"between(n,{a},{b - 1})" for a, b in locais[i["n"]])
        grafo.append(f"[{k}:v:0]fps=fps={FPS}:start_time=0,select='{sel}',setpts=N/({FPS}*TB),"
                     + ",".join(x for x in [_corte_9x16(i["w"], i["h"]), _conversao(i), "setsar=1", cores[i["n"]]] if x) + f"[v{k}]")
    ka, kc = len(usados), len(usados) + 1
    entradas += ["-i", "/sai/audio_limpo.wav", "-loop", "1", "-framerate", str(FPS), "-t", f"{cartela_s:.3f}", "-i", "/sai/cartela.png"]
    alvo = f"I={float(cfg.get('lufs', -14)):g}:TP={PICO_ALVO:g}:LRA=11"
    grafo += [
        "".join(f"[v{k}]" for k in range(len(usados))) + f"concat=n={len(usados)}:v=1:a=0"
        + (f",tpad=stop_mode=clone:stop_duration={plano['pad_q'] / FPS:.4f}" if plano.get("pad_q") else "")
        + f",ass=filename='/sai/legenda.ass':fontsdir='/fontes',settb=1/{FPS}[fala]",
        f"[{kc}:v]scale={LARG}:{ALT}:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p,setsar=1,fps={FPS},"
        f"settb=1/{FPS}[cart]",
        f"[fala][cart]xfade=transition=fade:duration={TRANSICAO}:offset={fala - TRANSICAO:.4f},format=yuv420p[v]",
        f"[{ka}:a]loudnorm={alvo}:measured_I={medida['input_i']}:measured_TP={medida['input_tp']}:measured_LRA={medida['input_lra']}:"
        f"measured_thresh={medida['input_thresh']}:offset={medida['target_offset']}:linear=true,aresample={audio.SR},"
        f"apad=whole_len={round(fala * audio.SR)},atrim=end_sample={round(fala * audio.SR)},"
        f"afade=t=out:st={fala - TRANSICAO:.4f}:d={TRANSICAO},aformat=sample_fmts=fltp:sample_rates={audio.SR}:channel_layouts=stereo[voz]",
        f"anullsrc=r={audio.SR}:cl=stereo,atrim=duration={cartela_s - TRANSICAO:.4f}[mudo]",
        # o AAC do ffmpeg põe 1024 amostras de "aquecimento" no começo (initial_padding); sem a lista de edição, que as descontaria,
        # o som atrasaria 21 ms em relação à imagem: tiramos as mesmas 1024 amostras do começo (é a folga antes da 1ª palavra)
        f"[voz][mudo]concat=n=2:v=0:a=1,atrim=start_sample={AAC_AQUECIMENTO},asetpts=N/SR/TB[a]",
    ]
    isolado.rodar("montar", "ffmpeg", [
        "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *entradas, "-filter_complex", ";".join(grafo),
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", preset, "-crf", "20", "-profile:v", "high", "-level:v", "4.1",
        "-maxrate", taxa[0], "-bufsize", taxa[1], "-g", str(2 * FPS), "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(audio.SR), "-ac", "2",
        "-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart+negative_cts_offsets", "-use_editlist", "0",
        "/sai/reel.mp4"], pastas, isolado.TEMPO_MONTAR)


def quadros(fala_s: float, pastas: isolado.Pastas) -> list[int]:
    """Os 4 quadros do relatório (a 15, 40, 65 e 90% da fala), tirados da saída (que já não tem metadados)."""
    tempos = [round(fala_s * f, 3) for f in (0.15, 0.40, 0.65, 0.90)]
    args = ["-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for t in tempos:
        args += ["-ss", f"{t:.3f}", "-i", "/sai/reel.mp4"]
    for k in range(len(tempos)):                        # um comando só (no robô, cada comando é um contêiner)
        args += ["-map", f"{k}:v:0", "-frames:v", "1", "-q:v", "3", "-map_metadata", "-1", f"/sai/q{k + 1}.jpg"]
    isolado.rodar("quadros", "ffmpeg", args, pastas, isolado.TEMPO_SONDAR)
    return [round(t * 1000) for t in tempos]


def capa(infos: list[dict], plano: dict, capa_q: int, pastas: isolado.Pastas, cores: dict) -> dict:
    """Grava sai/capa.jpg: o quadro capa_q da linha original (ou o que ficou mais perto dele no vídeo), sem a legenda. Devolve {q,
    em_ms, movida}."""
    q = int(capa_q)
    ficam = [(qa, qb) for qa, qb in plano["trechos"]]
    if not any(qa <= q < qb for qa, qb in ficam):
        q = min((x for qa, qb in ficam for x in (qa, qb - 1)), key=lambda x: (abs(x - q), x))
        movida = True
    else:
        movida = False
    info = next(i for i in infos if i["inicio_q"] <= q < i["inicio_q"] + i["quadros"])
    local = q - info["inicio_q"]
    cadeia = ",".join(x for x in [f"fps=fps={FPS}:start_time=0", f"select='eq(n,{local})'", _corte_9x16(info["w"], info["h"]),
                                  _conversao(info), "setsar=1", cores.get(info["n"], "")] if x)
    isolado.rodar("capa", "ffmpeg", ["-hide_banner", "-loglevel", "error", "-nostdin", "-y", *entrada(info), "-i", f"/ent/{info['n']}",
                                     "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", cadeia, "-frames:v", "1", "-q:v", "2",
                                     "-map_metadata", "-1", "/sai/capa.jpg"], pastas, isolado.TEMPO_SONDAR)
    if not (pastas.sai / "capa.jpg").is_file():
        raise ErroVideo("conferencia_falhou", "montar", ["capa"])
    return {"q": q, "em_ms": round(cortes.video_de(plano, q)[0] * 1000), "movida": movida}


def montar(infos: list[dict], plano: dict, pastas: isolado.Pastas, cfg: dict, preset: str = "medium", capa_q: int | None = None) -> dict:
    """Monta sai/reel.mp4 e os quadros (e, com capa_q, a capa). Devolve o pedaço do relatório: {saida, imagem, audio, quadros_ms,
    capa?}."""
    if not plano.get("trechos"):
        raise ErroVideo("sem_fala", "montar")
    lufs = float(cfg.get("lufs", -14))
    fala, medida = audio_limpo(plano, pastas, lufs)
    if fala <= TRANSICAO + 0.1:
        raise ErroVideo("sem_fala", "montar")
    usados = cortes.por_clipe(plano, infos)
    luzes = {i["n"]: medir_luz(i, pastas) for i in infos if i["n"] in usados}
    cores = {n: ajuste_cor(l) for n, l in luzes.items()}
    for taxa in TAXAS:
        _render(infos, plano, pastas, cfg, medida, cores, preset, taxa)
        tamanho = (pastas.sai / "reel.mp4").stat().st_size
        if tamanho <= LIMITE_BYTES:
            break
    cartela_s = float(cfg.get("cartela_s", 3))
    extra = {"capa": capa(infos, plano, capa_q, pastas, cores)} if isinstance(capa_q, int) and not isinstance(capa_q, bool) else {}
    return {**extra, "saida": {"duracao_s": round(fala + cartela_s - TRANSICAO, 2), "fala_s": round(fala, 2), "cartela_s": cartela_s,
                      "transicao_s": TRANSICAO, "mb": round(tamanho / 1024 / 1024, 1), "taxa": taxa[0]},
            "imagem": {"luz": {n: {k: (round(v, 1) if v is not None else None) for k, v in l.items()} for n, l in luzes.items()}},
            "audio": {"ruido_antes_db": ruido_relativo("/sai/fala48k.wav", pastas),
                      "ruido_depois_db": ruido_relativo("/sai/audio_limpo.wav", pastas), "linear": medida["linear"]},
            "quadros_ms": quadros(fala, pastas)}


def ruido_relativo(wav: str, pastas: isolado.Pastas) -> float:
    """O ruído de fundo em relação à voz (piso de ruído menos o volume integrado, em dB; mais negativo = mais limpo). Relativo porque
    o volume final vem do loudnorm, que sobe a voz e o ruído juntos."""
    return round(audio.piso_ruido(audio.amostras(wav, pastas)) - audio.ebur128(wav, pastas)["lufs"], 1)

