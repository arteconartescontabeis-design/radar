"""Radar Artecon — corretor de vídeo (v0.22.0): a legenda gravada e o texto do gancho (ASS, desenhados pelo libass com a DM Sans).

A legenda só tem palavra que foi dita, no tempo em que foi dita (o texto de cada palavra vem do alinhamento: a grafia do roteiro nos
trechos alinhados). Formato (desenho 4.1, item 7):
  * `Fala`: DM Sans 70 (negrito), branca sobre caixa marinho #011F48 (20% transparente), embaixo e no centro, com a base em y=1220. A
    área livre do Reels em 1080×1920 é x 65..1015 e y 269..1248 (a Meta pede livres 14% do topo, 35% da base e 6% de cada lado); a
    caixa (16 px em volta do texto) fica dentro dela. Blocos de até 2 linhas de 24 caracteres e até 3,2 s, fechados na pontuação, com
    as linhas equilibradas (sem artigo ou preposição no fim da 1ª, sem palavra curta ou número sozinho na 2ª);
  * estilo "compacta" (ajustes.estilo): 1 linha de até 30 caracteres, fonte 58 — cobre menos o rosto;
  * termos do glossário com espaço fixo (`\\h`): "Simples Nacional" nunca se quebra;
  * `Gancho`: o texto da chamada da peça de 0 a 3 s, DM Sans 64, a mesma caixa, acima da legenda (base em y=1010), até 2 linhas de 22
    caracteres. Não cabendo, sai com aviso (nunca cortado com "…");
  * o último bloco termina na última palavra (a transição para a cartela começa 0,05 s depois dela);
  * uma unidade do alinhamento com espaço ("30 de outubro", "R$ 50.000,00", "Simples Nacional") nunca se quebra; cada bloco leva o
    número `u` da sua 1ª unidade e quantas palavras tem — é por ele que o editor de legenda do administrador (ajustes.legenda,
    alinhar.py) diz qual trecho mudou — e as palavras do roteiro perto dele (`perto`, as letras: a tela recusa a palavra nova que o
    robô recusaria, sem rodar a montagem à toa).
v0.33.0 (a aba Vídeo): a aparência da legenda (ajustes.legenda_tamanho, legenda_posicao e legenda_cor; aparencia()) — o tamanho P, M
ou G (a fonte e os caracteres por linha), a posição (embaixo, como antes; no meio, centrada em y=960; em cima, com o topo em y=300) e a
cor, só da paleta da Artecon (CORES: o texto sobre a caixa, a mesma de radar_video_paleta() no banco, conferida por teste). O gancho
segue a cor da legenda e fica sempre longe dela (38 px entre as caixas); o tamanho dele não muda. Sem a aparência (ou com a padrão: M,
embaixo, marinho), o .ass sai igual ao de antes. Dois blocos nunca juntam unidades que não são seguidas (um corte do editor tirou a do
meio): o editor de legenda (alinhar._edicao) troca as palavras a partir da 1ª unidade do bloco, em sequência.
Além do limite de caracteres, cada linha é medida em pixels com a mesma fonte (o libass dimensiona a fonte pela altura
usWinAscent + usWinDescent: 1012 + 310 para 1000 unidades na DM Sans) e precisa caber entre as margens (x 100 a 980); uma palavra
que sozinha passa disso leva o bloco para uma fonte menor ({\\fs}), nunca para fora da área livre.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import ImageFont

FONTES = Path(__file__).resolve().parent / "fontes"
FONTE_LEGENDA = FONTES / "DMSans-Bold.ttf"
ESCALA_ASS = 1000 / (1012 + 310)       # tamanho no ASS → tamanho do eme (em px), como o libass faz com a DM Sans
LARGURA, ALTURA = 1080, 1920
AREA_LIVRE = (65, 269, 1015, 1248)     # x0, y0, x1, y1
MARGEM_H = 100                         # MarginL/MarginR: o texto vai de x 100 a 980
LARGURA_TEXTO = LARGURA - 2 * MARGEM_H
BASE_FALA, BASE_GANCHO = 1220, 1010
ESTILOS = {"normal": {"fonte": 70, "linhas": 2, "car": 24}, "compacta": {"fonte": 58, "linhas": 1, "car": 30}}
# v0.33.0: a aparência (a aba Vídeo). A paleta é a de radar_video_paleta() (texto, caixa: RRGGBB); o 1º de cada um é o padrão
CORES = {"marinho": ("FFFFFF", "011F48"), "branco": ("011F48", "FFFFFF"), "vermelho": ("FFFFFF", "BC151B"), "azul": ("011F48", "569DCC"),
         "amarelo": ("011F48", "FFD700")}
TAMANHOS = {"P": .85, "M": 1.0, "G": 1.15}
POSICOES = ("cima", "meio", "baixo")
# a fonte e os caracteres por linha de cada tamanho (a fonte é a base × o fator, arredondada para um número par de px; os caracteres,
# a base ÷ o fator)
FONTES_TAMANHO = {"normal": {"P": 60, "M": 70, "G": 80}, "compacta": {"P": 50, "M": 58, "G": 66}}
CAR_TAMANHO = {"normal": {"P": 28, "M": 24, "G": 21}, "compacta": {"P": 35, "M": 30, "G": 26}}
TOPO_CIMA, CENTRO_MEIO = 300, 960      # y: o topo do texto "em cima" (a caixa começa 16 px antes: 284, dentro da área livre) e o centro "no meio"
VAO_GANCHO = 38                        # px entre a caixa do gancho e a da legenda
CAIXA = 16                             # a caixa em volta do texto (Outline do BorderStyle 3)
APARENCIA_PADRAO = {"tamanho": "M", "posicao": "baixo", "cor": "marinho"}
GANCHO = {"fonte": 64, "linhas": 2, "car": 22, "ate_s": 3.0}
BLOCO_MAX_S = 3.2
FRACAS = {"a", "o", "as", "os", "da", "de", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "para", "pra", "com", "por",
          "pelo", "pela", "um", "uma", "é", "que", "ao", "aos", "à", "às", "se", "sem", "seu", "sua"}
_ESTILO = ("Style: {nome},DM Sans,{fonte},&H00{texto},&H00{texto},&H33{caixa},&H66000000,-1,0,0,0,100,100,0,0,3,16,0,{alinhamento},"
           f"{MARGEM_H},{MARGEM_H},{{margem}},1")
_cache_fontes: dict[int, ImageFont.FreeTypeFont] = {}


def _fonte(tamanho_ass: float) -> ImageFont.FreeTypeFont:
    px = max(8, round(tamanho_ass * ESCALA_ASS))
    if px not in _cache_fontes:
        _cache_fontes[px] = ImageFont.truetype(str(FONTE_LEGENDA), px)
    return _cache_fontes[px]


def aparencia(ajustes: dict | None) -> dict:
    """A aparência pedida nos ajustes (o editor da aba Vídeo): o que não estiver na tabela vale o padrão (M, embaixo, marinho)."""
    a = ajustes if isinstance(ajustes, dict) else {}
    pega = lambda chave, validos, padrao: a.get(chave) if isinstance(a.get(chave), str) and a.get(chave) in validos else padrao
    return {"tamanho": pega("legenda_tamanho", TAMANHOS, "M"), "posicao": pega("legenda_posicao", POSICOES, "baixo"),
            "cor": pega("legenda_cor", CORES, "marinho")}


def _bgr(rgb: str) -> str:
    """RRGGBB → BBGGRR (a ordem das cores no ASS)."""
    return rgb[4:6] + rgb[2:4] + rgb[0:2]


def _medidas(estilo: str, ap: dict) -> dict:
    """A fonte e os caracteres por linha do estilo no tamanho pedido."""
    return {**ESTILOS[estilo], "fonte": FONTES_TAMANHO[estilo][ap["tamanho"]], "car": CAR_TAMANHO[estilo][ap["tamanho"]]}


def _posicoes(e: dict, ap: dict) -> dict:
    """O alinhamento (numpad do ASS) e a margem vertical da legenda (Fala) e do gancho. Embaixo (como antes): a base da legenda em
    y=1220 e a do gancho acima da caixa de duas linhas dela (1010 em M, como antes; mais alta com a letra G); no meio: a legenda
    centrada em y=960 e o gancho com o topo em y=300; em cima: a legenda com o topo em y=300 e o gancho logo abaixo da caixa dela."""
    caixa = e["linhas"] * e["fonte"] + 2 * CAIXA                       # a altura da caixa da legenda com todas as linhas
    if ap["posicao"] == "meio":
        return {"fala": (5, 0), "gancho": (8, TOPO_CIMA)}
    if ap["posicao"] == "cima":
        return {"fala": (8, TOPO_CIMA), "gancho": (8, TOPO_CIMA + caixa + VAO_GANCHO)}
    base_gancho = min(BASE_GANCHO, BASE_FALA - caixa - VAO_GANCHO)
    return {"fala": (2, ALTURA - BASE_FALA), "gancho": (2, ALTURA - base_gancho)}


def largura(texto: str, tamanho_ass: float) -> float:
    """Largura em px do texto (com \\h como espaço), na fonte do libass."""
    return _fonte(tamanho_ass).getlength(texto.replace("\\h", " "))


def limpar(texto: str) -> str:
    """Texto que vai para dentro do ASS: sem barra invertida (\\N, \\fs… são comandos do ASS) e sem chaves ({…} são blocos de
    comando); quebras e espaços repetidos viram um espaço."""
    return " ".join(str(texto or "").replace("\\", "").replace("{", "(").replace("}", ")").split())


def _norm(t: str) -> str:
    return re.sub(r"[^\w$%]", "", t.lower())


def _unidades(palavras: list[dict], glossario: list[str]) -> list[dict]:
    """Junta as palavras de um termo do glossário com várias palavras numa unidade só (espaço fixo \\h)."""
    termos = sorted({tuple(_norm(x) for x in g.split()) for g in glossario if len(g.split()) > 1}, key=len, reverse=True)
    out, k = [], 0
    while k < len(palavras):
        for t in termos:
            pedaco = palavras[k:k + len(t)]
            if len(pedaco) == len(t) and tuple(_norm(p["texto"]) for p in pedaco) == t:
                out.append({"texto": "\\h".join(p["texto"] for p in pedaco), "ini": pedaco[0]["ini"], "fim": pedaco[-1]["fim"],
                            **({"u": pedaco[0]["u"]} if "u" in pedaco[0] else {}),
                            "perto": sorted({w for p in pedaco for w in p.get("perto") or ()})})
                k += len(t)
                break
        else:
            out.append({**palavras[k], "texto": palavras[k]["texto"].replace(" ", "\\h")})
            k += 1
    return out


def _texto(us: list[dict]) -> str:
    return " ".join(u["texto"] for u in us)


def _tam(us: list[dict]) -> int:
    return len(_texto(us).replace("\\h", " "))


def arranjar(us: list[dict], linhas: int, car: int, fonte: float) -> list[str] | None:
    """As linhas de um bloco (até `linhas`, cada uma até `car` caracteres e até a largura entre as margens), as mais equilibradas;
    None se não couber."""
    cabe = lambda xs: _tam(xs) <= car and largura(_texto(xs), fonte) <= LARGURA_TEXTO
    if cabe(us):
        return [_texto(us)]
    if linhas < 2:
        return None
    melhor = None
    for k in range(1, len(us)):
        a, b = us[:k], us[k:]
        if not (cabe(a) and cabe(b)):
            continue
        custo = max(_tam(a), _tam(b))
        custo += 12 if a[-1]["texto"].lower().strip(".,;:!?") in FRACAS else 0
        custo += 12 if len(b) == 1 and (len(b[0]["texto"]) <= 4 or any(c.isdigit() for c in b[0]["texto"])) else 0
        if melhor is None or custo < melhor[0]:
            melhor = (custo, [_texto(a), _texto(b)])
    return melhor[1] if melhor else None


def _ts(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _seguidas(a: dict, b: dict) -> bool:
    """As duas unidades são seguidas no alinhamento (sem o número u, como nos testes, contam como seguidas)?"""
    return not (isinstance(a.get("u"), int) and isinstance(b.get("u"), int)) or b["u"] == a["u"] + 1


def blocos(palavras: list[dict], glossario: list[str] = (), estilo: str = "normal", aparencia: dict | None = None) -> list[dict]:
    """Os blocos da legenda: [{ini, fim, linhas, fonte}], no tempo do vídeo corrigido."""
    e = _medidas(estilo, aparencia or APARENCIA_PADRAO)
    us = [u for u in _unidades([{**p, "texto": limpar(p["texto"])} for p in palavras], list(glossario)) if u["texto"]]
    grupos, atual = [], []
    for u in us:
        if atual and (u["fim"] - atual[0]["ini"] > BLOCO_MAX_S or not _seguidas(atual[-1], u)
                      or arranjar(atual + [u], e["linhas"], e["car"], e["fonte"]) is None):
            grupos.append(atual)
            atual = []
        atual.append(u)
        fim_t = u["texto"].replace("\\h", " ")[-1:]
        if fim_t in ".!?…" or (fim_t in ",;:" and _tam(atual) >= e["car"]):
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    out = []
    for k, g in enumerate(grupos):
        fonte = e["fonte"]
        # uma palavra sozinha com mais caracteres que o limite fica, se couber na largura; mais larga que a linha: letra menor, nunca "…"
        linhas = arranjar(g, e["linhas"], e["car"], fonte) or arranjar(g, e["linhas"], 99, fonte)
        while linhas is None and fonte > 30:
            fonte -= 4
            linhas = arranjar(g, e["linhas"], 99, fonte)
        if linhas is None:
            linhas, fonte = [_texto(g)], 30
        prox = grupos[k + 1][0]["ini"] if k + 1 < len(grupos) else None
        fim = (prox if prox - g[-1]["fim"] < 0.6 else g[-1]["fim"] + 0.25) if prox is not None else g[-1]["fim"]
        if prox is not None:
            fim = min(max(fim, g[0]["ini"] + 0.7), prox)
        out.append({"ini": g[0]["ini"], "fim": fim, "linhas": linhas, "fonte": fonte, "u": g[0].get("u"),
                    "palavras": sum(len(x["texto"].replace("\\h", " ").split()) for x in g),
                    "perto": sorted({w for x in g for w in x.get("perto") or ()})})
    return out


def gancho_linhas(texto: str) -> list[str] | None:
    us = [{"texto": w} for w in limpar(texto).split()]
    return arranjar(us, GANCHO["linhas"], GANCHO["car"], GANCHO["fonte"]) if us else None


def gravar(destino: Path, palavras: list[dict], glossario: list[str] = (), estilo: str = "normal", gancho: str | None = None,
           aparencia: dict | None = None) -> dict:
    """Grava o .ass. palavras: [{texto, ini, fim, u?}] no tempo do vídeo corrigido (cortes.no_video); aparencia: {tamanho, posicao,
    cor} (aparencia(ajustes); sem ela, a padrão). Devolve o resumo para o relatório, com a lista dos blocos ({u, em_s, palavras, texto,
    perto}) para o editor de legenda."""
    if estilo not in ESTILOS:
        estilo = "normal"
    ap = aparencia if isinstance(aparencia, dict) and aparencia.get("tamanho") in TAMANHOS and aparencia.get("posicao") in POSICOES \
        and aparencia.get("cor") in CORES else APARENCIA_PADRAO
    medidas = _medidas(estilo, ap)
    pos = _posicoes(medidas, ap)
    texto_cor, caixa_cor = (_bgr(c) for c in CORES[ap["cor"]])
    bs = blocos(palavras, glossario, estilo, ap)
    avisos, eventos = [], []
    g = gancho_linhas(gancho) if gancho else None
    if gancho and g is None:
        avisos.append("gancho_nao_cabe")
    if g:
        eventos.append(f"Dialogue: 1,{_ts(0)},{_ts(GANCHO['ate_s'])},Gancho,,0,0,0,," + "\\N".join(g))
    padrao = medidas["fonte"]
    for b in bs:
        tag = f"{{\\fs{b['fonte']}}}" if b["fonte"] != padrao else ""
        eventos.append(f"Dialogue: 0,{_ts(b['ini'])},{_ts(b['fim'])},Fala,,0,0,0,,{tag}" + "\\N".join(b["linhas"]))
    cab = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
           "YCbCr Matrix: TV.709\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
           "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding\n"
           + _ESTILO.format(nome="Fala", fonte=padrao, texto=texto_cor, caixa=caixa_cor, alinhamento=pos["fala"][0], margem=pos["fala"][1]) + "\n"
           + _ESTILO.format(nome="Gancho", fonte=GANCHO["fonte"], texto=texto_cor, caixa=caixa_cor, alinhamento=pos["gancho"][0],
                            margem=pos["gancho"][1]) + "\n\n"
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    destino.write_text(cab + "".join(e + "\n" for e in eventos), encoding="utf-8")
    return {"blocos": len(bs), "estilo": estilo, "gancho": bool(g), "avisos": avisos, **ap,
            "lista": [{"u": b["u"], "em_s": round(b["ini"], 2), "palavras": b["palavras"],
                       "texto": " ".join(b["linhas"]).replace("\\h", " "), "perto": b["perto"]} for b in bs]}
