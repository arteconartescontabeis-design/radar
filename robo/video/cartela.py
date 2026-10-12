"""Radar Artecon — corretor de vídeo (v0.22.0): a cartela final, desenhada pelo robô (Pillow e a DM Sans do repositório).

No padrão da arte do Radar (desenharArte, index.html): 1080×1920, degradê marinho #011F48 → #0D3B73 → #1B5E9B, a faixa de três cores
no alto, as curvas do papel timbrado no canto de baixo e o logotipo sobre cartão branco. As linhas — radar_videos.cartela_linhas (a
tela monta com linhaIdentificacao() e a linha do responsável; o banco confere) mais o cartela_extra das Configurações — ficam
centralizadas entre y 820 e 1240, dentro da área livre do Reels (y 269..1248, x 65..1015). Todas no mesmo tamanho: de 52 px para
baixo, até o menor em que a altura do "H" ainda tem 28 px (texto legal legível no celular), em DM Sans Medium (a 1ª linha em branco,
as outras em azul-claro, como a faixa legal da arte). Cada linha quebra em linhas de no máximo 950 px: nos " · " (até 3) ou nas
palavras (até 2). Não cabendo, erro `cartela_nao_cabe` — nunca "…" nem texto espremido. A fonte do canvas da tela caía para Arial quando demorava a
carregar; aqui a fonte é o arquivo do repositório, sempre.
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from segredo import ErroVideo

AQUI = Path(__file__).resolve().parent
FONTE_NEGRITO = AQUI / "fontes" / "DMSans-Bold.ttf"
FONTE_MEDIA = AQUI / "fontes" / "DMSans-Medium.ttf"
LOGO = AQUI.parent.parent / "radar-logo-artecon.png"
L, A = 1080, 1920
TOPO, BASE = 820, 1240                 # faixa das linhas
LARGURA_MAX = 950                      # = área livre (65..1015)
FONTE_INICIAL, ALTURA_H_MIN = 52, 28
CORES = [(0.0, (0x01, 0x1F, 0x48)), (0.6, (0x0D, 0x3B, 0x73)), (1.0, (0x1B, 0x5E, 0x9B))]


def _cor(t: float) -> tuple[int, int, int]:
    for (t0, c0), (t1, c1) in zip(CORES, CORES[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * f) for a, b in zip(c0, c1))
    return CORES[-1][1]


def _fundo() -> Image.Image:
    """Degradê na diagonal (0,0)→(L,A), como o createLinearGradient da arte: t = a·x/L + b·y/A, com a + b = 1."""
    gx = Image.linear_gradient("L").rotate(90, expand=True).resize((L, A))      # 0 à esquerda, 255 à direita
    gy = Image.linear_gradient("L").resize((L, A))
    t = Image.blend(gx, gy, A * A / (L * L + A * A))
    rgb = [t.point([_cor(i / 255)[c] for i in range(256)]) for c in range(3)]
    return Image.merge("RGB", rgb)


def _limpar(texto: str) -> str:
    return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", str(texto or "")).split())


def _quebrar(texto: str, fonte: ImageFont.FreeTypeFont) -> list[str] | None:
    """Linhas de até 950 px. Com " · " (a linha de identificação: empresa · CNPJ · CRC), os pedaços se juntam como na faixa legal da
    arte, em até 3 linhas (o "CRC-SC 000000/O-0" nunca se separa); sem eles, ou com um pedaço maior que a linha, em até 2 linhas
    quebradas nas palavras, as mais equilibradas. None: não cabe."""
    cabe = lambda t: fonte.getlength(t) <= LARGURA_MAX
    if cabe(texto):
        return [texto]
    pedacos = texto.split(" · ")
    if len(pedacos) > 1 and all(cabe(p) for p in pedacos):
        linhas = [pedacos[0]]
        for p in pedacos[1:]:
            if cabe(linhas[-1] + " · " + p):
                linhas[-1] += " · " + p
            else:
                linhas.append(p)
        if len(linhas) <= 3:
            return linhas
    palavras, melhor = texto.split(" "), None
    for k in range(1, len(palavras)):
        a, b = " ".join(palavras[:k]), " ".join(palavras[k:])
        if cabe(a) and cabe(b) and (melhor is None or abs(fonte.getlength(a) - fonte.getlength(b)) < melhor[0]):
            melhor = (abs(fonte.getlength(a) - fonte.getlength(b)), [a, b])
    return melhor[1] if melhor else None


def altura_h(px: int) -> int:
    caixa = ImageFont.truetype(str(FONTE_MEDIA), px).getbbox("H")
    return caixa[3] - caixa[1]


def desenhar(destino: Path, linhas: list[str], extra: str = "") -> dict:
    """Grava a cartela (PNG 1080×1920). Devolve {tamanho, altura_h, linhas, caixa} (caixa: x0, y0, x1, y1 do texto)."""
    itens = [t for t in (_limpar(x) for x in [*linhas, extra]) if t]
    if not itens or len(itens) > 5:
        raise ErroVideo("cartela_nao_cabe", "cartela")
    escolha = None
    for px in range(FONTE_INICIAL, 0, -2):
        if altura_h(px) < ALTURA_H_MIN:
            break
        fontes = [ImageFont.truetype(str(FONTE_MEDIA), px)] * len(itens)
        quebradas = [_quebrar(t, f) for t, f in zip(itens, fontes)]
        if any(q is None for q in quebradas):
            continue
        passo, entre = round(px * 1.3), round(px * 0.6)
        altura = sum(len(q) for q in quebradas) * passo + entre * (len(itens) - 1)
        if altura <= BASE - TOPO:
            escolha = (px, fontes, quebradas, passo, entre, altura)
            break
    if escolha is None:
        raise ErroVideo("cartela_nao_cabe", "cartela")
    px, fontes, quebradas, passo, entre, altura = escolha
    im = _fundo()
    camada = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    for raio, alfa in ((380, 77), (290, 115), (200, 191)):          # as curvas do papel timbrado, no canto de baixo (fora da área livre)
        d.ellipse((L + 60 - raio, 1820 - raio, L + 60 + raio, 1820 + raio), fill=(86, 157, 204, alfa))
    im = Image.alpha_composite(im.convert("RGBA"), camada).convert("RGB")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, round(L * .68), 13), fill="#BC151B")
    d.rectangle((round(L * .68), 0, round(L * .9), 13), fill="#00AEEF")
    d.rectangle((round(L * .9), 0, L, 13), fill="#FFD700")
    cartao = (L // 2 - 260, 440, L // 2 + 260, 680)
    d.rounded_rectangle(cartao, radius=24, fill="#FFFFFF")
    try:
        logo = Image.open(LOGO).convert("RGBA")
        f = min(440 / logo.width, 180 / logo.height)
        logo = logo.resize((round(logo.width * f), round(logo.height * f)), Image.Resampling.LANCZOS)
        im.paste(logo, ((L - logo.width) // 2, 560 - logo.height // 2), logo)
    except OSError:
        d.text((L // 2, 560), "Artecon", font=ImageFont.truetype(str(FONTE_NEGRITO), 72), fill="#011F48", anchor="mm")
    y = TOPO + (BASE - TOPO - altura) / 2
    caixa = [L, A, 0, 0]
    for k, (q, fonte) in enumerate(zip(quebradas, fontes)):
        for linha in q:
            x = (L - fonte.getlength(linha)) / 2
            d.text((x, y + passo / 2), linha, font=fonte, fill="#FFFFFF" if k == 0 else "#DCEBF7", anchor="lm")
            b = d.textbbox((x, y + passo / 2), linha, font=fonte, anchor="lm")
            caixa = [min(caixa[0], b[0]), min(caixa[1], b[1]), max(caixa[2], b[2]), max(caixa[3], b[3])]
            y += passo
        y += entre
    im.save(destino, "PNG", optimize=False)
    return {"tamanho": px, "altura_h": altura_h(px), "linhas": quebradas, "caixa": tuple(round(c) for c in caixa)}
