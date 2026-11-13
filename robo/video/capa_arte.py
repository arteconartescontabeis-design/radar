"""Radar Artecon — corretor de vídeo (v0.46.0): a CAPA-ARTE automática do reel, no molde aprovado pelo dono em 10/11/2026.

O molde (fixo; só a pessoa, a categoria, o título e o subtítulo mudam de um reel para outro):
  * fundo de ESTÚDIO marinho (gradiente com luz suave atrás da pessoa e sombra projetada);
  * a PESSOA do quadro escolhido, recortada por segmentação (ISNet, ONNX local — a foto de ninguém sai para serviço
    externo e nenhuma IA generativa toca o rosto), tratada (luz, cor, nitidez) e com a borda suavizada;
  * painel DIAGONAL marinho à esquerda com o friso AMARELO na borda e um painel secundário na base;
  * cartão BRANCO no topo com o LOGOTIPO oficial colorido (radar-logo-artecon.png, sem modificação);
  * faixa VERMELHA arredondada com a CATEGORIA; o TÍTULO em bloco (caixa alta, DM Sans), última linha em AMARELO;
    o traço AZUL CLARO e o SUBTÍTULO.

Quem dá a categoria, as linhas do título e o subtítulo é a tela no envio (ajustes.capa, escrito por radar_video_criar:
a IA Central escreve e o administrador pode trocar na aba Vídeo). O quadro é o capa_q do editor ou o ESCOLHIDO SOZINHO
pelo mais nítido (escolher_q). Sem ajustes.capa, nada muda: a capa (se houver capa_q) continua o quadro cru, como antes.

O modelo de recorte (isnet-general-use.onnx, 176 MB, do projeto rembg) é baixado UMA vez por execução do runner para
/tmp e conferido por sha256 fixo; RADAR_CAPA_MODELO aponta um arquivo local (os testes usam). Sem o modelo, sem o
onnxruntime ou sem rede, a capa NUNCA falha: sai o plano B — o próprio quadro com um véu marinho e os mesmos textos.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

AQUI = Path(__file__).resolve().parent
FONTE_B = AQUI / "fontes" / "DMSans-Bold.ttf"
FONTE_M = AQUI / "fontes" / "DMSans-Medium.ttf"
LOGO = AQUI.parent.parent / "radar-logo-artecon.png"

L, A = 1080, 1920
MARINHO = (1, 31, 72)
MARINHO2 = (10, 49, 94)
AMARELO = (255, 215, 0)
AZULCLARO = (86, 157, 204)
VERMELHO = (188, 21, 27)
BRANCO = (255, 255, 255)

MODELO_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
MODELO_SHA256 = "60920e99c45464f2ba57bee2ad08c919a52bbf852739e96947fbb4358c0d964a"
_sessao_onnx = None          # a sessão fica na execução (o runner morre ao fim; nada persiste)

# os limites dos textos (os mesmos de radar_video_ajustes_falta no banco)
MAX_LINHAS, MAX_LINHA, MAX_CATEGORIA, MAX_SUBTITULO = 3, 18, 24, 48


def dados_de(ajustes: dict | None) -> dict | None:
    """O ajustes.capa saneado: {linhas: [até 3, caixa alta], categoria, subtitulo} ou None (sem capa-arte)."""
    c = (ajustes or {}).get("capa")
    if not isinstance(c, dict):
        return None
    linhas = [str(x).strip().upper()[:MAX_LINHA] for x in (c.get("linhas") or []) if str(x).strip()][:MAX_LINHAS]
    if not linhas:
        return None
    return {"linhas": linhas, "categoria": str(c.get("categoria") or "").strip().upper()[:MAX_CATEGORIA],
            "subtitulo": str(c.get("subtitulo") or "").strip().upper()[:MAX_SUBTITULO]}


# ------------------------------------------------------------------ o recorte da pessoa (ISNet, local)
def _modelo() -> Path | None:
    proprio = os.environ.get("RADAR_CAPA_MODELO", "")
    if proprio:
        p = Path(proprio)
        return p if p.is_file() else None
    p = Path(tempfile.gettempdir()) / "radar-isnet-general-use.onnx"
    if not p.is_file():
        try:
            tmp = p.with_suffix(".baixando")
            urllib.request.urlretrieve(MODELO_URL, tmp)          # noqa: S310 — URL fixa deste módulo
            tmp.replace(p)
        except Exception:
            return None
    try:
        if hashlib.sha256(p.read_bytes()).hexdigest() != MODELO_SHA256:
            p.unlink(missing_ok=True)
            return None
    except OSError:
        return None
    return p


def recortar(im: Image.Image) -> Image.Image | None:
    """A pessoa recortada (RGBA, mesmo tamanho de `im`) ou None (sem modelo/onnxruntime: o plano B assume)."""
    global _sessao_onnx
    try:
        import numpy as np
        import onnxruntime as ort
        if _sessao_onnx is None:
            caminho = _modelo()
            if caminho is None:
                return None
            _sessao_onnx = ort.InferenceSession(str(caminho), providers=["CPUExecutionProvider"])
        ent = im.convert("RGB").resize((1024, 1024), Image.Resampling.BILINEAR)
        x = (np.asarray(ent, dtype=np.float32) / 255.0 - 0.5).transpose(2, 0, 1)[None, ...]
        y = _sessao_onnx.run(None, {_sessao_onnx.get_inputs()[0].name: x})[0][0][0]
        y = (y - y.min()) / (y.max() - y.min() + 1e-8)
        masc = Image.fromarray((y * 255).astype("uint8")).resize(im.size, Image.Resampling.BILINEAR)
        saida = im.convert("RGBA")
        saida.putalpha(masc)
        return saida
    except Exception:
        return None


def nitidez(im: Image.Image) -> float:
    """A nitidez do quadro (variância do laplaciano, em tons de cinza reduzidos): maior = mais nítido."""
    g = im.convert("L").resize((270, 480), Image.Resampling.BILINEAR)
    try:
        import numpy as np
        a = np.asarray(g, dtype=np.float32)
        lap = a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:] - 4 * a[1:-1, 1:-1]
        return float(lap.var())
    except Exception:
        # sem numpy: a soma do que o desfoque apagou (mais detalhe apagado = quadro mais nítido)
        from PIL import ImageChops
        dif = ImageChops.difference(g, g.filter(ImageFilter.GaussianBlur(2)))
        return float(sum(n * v for v, n in enumerate(dif.histogram())))


def candidatos_q(plano: dict, maximo: int = 5) -> list[int]:
    """Os quadros candidatos à capa (na linha original): o meio de cada trecho que fica, dos maiores para os menores."""
    trechos = sorted((qa, qb) for qa, qb in plano.get("trechos") or [] if qb - qa >= 6)
    meios = [(qb - qa, (qa + qb) // 2) for qa, qb in trechos]
    extras = [(qb - qa, qa + (qb - qa) // 4) for qa, qb in trechos if qb - qa >= 60]
    extras += [(qb - qa, qa + 3 * (qb - qa) // 4) for qa, qb in trechos if qb - qa >= 60]
    vistos, saida = set(), []
    for _, q in sorted(meios + extras, reverse=True):
        if q not in vistos:
            vistos.add(q)
            saida.append(q)
    return saida[:maximo] or [qa for qa, _ in trechos[:1]]


def candidatos_quietos(plano: dict, energia: list, maximo: int = 6, margem_q: int = 2, janela_q: int = 5) -> list[int]:
    """v0.47.0: os quadros candidatos à capa nas PAUSAS (áudio baixo = boca fechada, não no meio da fala). O mais quieto de
    cada trecho e, depois, os mais quietos no geral — espaçados, para variar. Sem energia (ou nenhum trecho com interior),
    cai no candidatos_q (o modo antigo: o meio dos trechos). Depois, quem escolhe entre estes é a nitidez, no montar."""
    trechos = sorted((qa, qb) for qa, qb in (plano.get("trechos") or []) if qb - qa >= 2 * margem_q + 1)
    n = len(energia or [])
    if not n or not trechos:
        return candidatos_q(plano, maximo)
    w = max(0, janela_q // 2)
    def suave(q: int) -> float:                                   # energia média numa janelinha: pausa SUSTENTADA, não um vão de uma palavra
        faixa = energia[max(0, q - w): min(n, q + w + 1)]
        return sum(faixa) / len(faixa) if faixa else 0.0
    por_trecho, todos = [], []
    for qa, qb in trechos:
        interior = [q for q in range(qa + margem_q, qb - margem_q) if q < n]
        if not interior:
            continue
        pares = [(suave(q), q) for q in interior]
        por_trecho.append(min(pares))                            # o quadro mais quieto deste trecho
        todos.extend(pares)
    if not todos:
        return candidatos_q(plano, maximo)
    min_gap, saida = 15, []                                       # 0,5 s: não amontoar candidatos na mesma pausa
    longe = lambda q: all(abs(q - x) >= min_gap for x in saida)
    for _, q in sorted(por_trecho):                              # variedade primeiro: um por trecho, do mais quieto
        if q not in saida and longe(q):
            saida.append(q)
        if len(saida) >= maximo:
            return saida
    for _, q in sorted(todos):                                   # completa com os mais quietos no geral, espaçados
        if q not in saida and longe(q):
            saida.append(q)
        if len(saida) >= maximo:
            break
    return saida or candidatos_q(plano, maximo)


# ------------------------------------------------------------------ o desenho do molde
def _fonte(caminho: Path, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(caminho), tam)


def _encher(dr: ImageDraw.ImageDraw, texto: str, alvo: float, teto: int, caminho: Path = FONTE_B) -> ImageFont.FreeTypeFont:
    tam = 30
    while tam < teto and dr.textlength(texto, font=_fonte(caminho, tam + 2)) <= alvo:
        tam += 2
    return _fonte(caminho, tam)


def _poligono(base: Image.Image, pts: list, cor: tuple, alfa: int = 255) -> Image.Image:
    cam = Image.new("RGBA", (L, A), (0, 0, 0, 0))
    ImageDraw.Draw(cam).polygon(pts, fill=cor + (alfa,))
    return Image.alpha_composite(base, cam)


def _estudio() -> Image.Image:
    fundo = Image.new("RGB", (L, A))
    d = ImageDraw.Draw(fundo)
    for y in range(A):
        t = 1 - abs(y / A - 0.35) * 2
        d.line([(0, y), (L, y)], fill=(round(8 + 10 * t), round(26 + 22 * t), round(52 + 38 * t)))
    luz = Image.new("L", (L, A), 0)
    ImageDraw.Draw(luz).ellipse([430, 220, 1150, 1000], fill=120)
    luz = luz.filter(ImageFilter.GaussianBlur(150))
    return Image.composite(Image.new("RGB", (L, A), (56, 104, 160)), fundo, luz)


def _tratada(rgb: Image.Image) -> Image.Image:
    rgb = ImageEnhance.Brightness(rgb).enhance(1.08)
    rgb = ImageEnhance.Color(rgb).enhance(0.88)
    rgb = ImageEnhance.Contrast(rgb).enhance(1.05)
    return rgb.filter(ImageFilter.UnsharpMask(radius=3, percent=80, threshold=2))


def desenhar(caminho: Path, dados: dict) -> dict:
    """Transforma o quadro em `caminho` (o sai/capa.jpg, 1080×1920) na capa-arte do molde e o regrava. Devolve o
    resumo para o relatório: {recorte: true|false (false = o plano B, sem o modelo), linhas, categoria, subtitulo}."""
    quadro = Image.open(caminho).convert("RGB")
    if quadro.size != (L, A):
        quadro = quadro.resize((L, A), Image.Resampling.LANCZOS)
    pessoa = recortar(quadro)
    if pessoa is not None:
        alfa = pessoa.getchannel("A").filter(ImageFilter.GaussianBlur(1.2))
        caixa = alfa.getbbox()
        if caixa is None or (caixa[3] - caixa[1]) < A // 4:      # o recorte não achou gente: plano B
            pessoa = None
    if pessoa is not None:
        rgb = _tratada(pessoa.convert("RGB"))
        pessoa = rgb.convert("RGBA")
        pessoa.putalpha(alfa)
        recortada = pessoa.crop(caixa)
        alvo_h = min(A, max(1200, round((caixa[3] - caixa[1]) * 1.02)))
        fp = alvo_h / recortada.height
        recortada = recortada.resize((round(recortada.width * fp), alvo_h), Image.Resampling.LANCZOS)
        px, py = 710 - recortada.width // 2, A - alvo_h
        im = _estudio().convert("RGBA")
        sa = Image.new("L", (L, A), 0)
        sa.paste(recortada.getchannel("A"), (px + 26, py + 30))
        sa = sa.filter(ImageFilter.GaussianBlur(28)).point(lambda v: round(v * 0.45))
        sombra = Image.new("RGBA", (L, A), (0, 0, 0, 0))
        sombra.putalpha(sa)
        im = Image.alpha_composite(im, sombra)
        im.alpha_composite(recortada, (px, py))
    else:
        # plano B: o quadro tratado com um véu marinho (a capa nunca falha por falta do modelo)
        im = _tratada(quadro).convert("RGBA")
        im = Image.alpha_composite(im, Image.new("RGBA", (L, A), MARINHO + (96,)))

    borda_topo, borda_base = 600, 430
    borda = lambda y: borda_topo - (borda_topo - borda_base) * y / A      # noqa: E731
    im = _poligono(im, [(0, 0), (borda_topo, 0), (borda_base, A), (0, A)], MARINHO, 236)
    im = _poligono(im, [(borda_topo, 0), (borda_topo + 14, 0), (borda_base + 14, A), (borda_base, A)], AMARELO)
    im = _poligono(im, [(0, 1500), (360, 1430), (300, 1920), (0, 1920)], MARINHO2, 150)
    im = _poligono(im, [(0, 90), (540, 90), (480, 330), (0, 330)], BRANCO)
    dr = ImageDraw.Draw(im)
    try:
        logo = Image.open(LOGO).convert("RGBA")
        fl = min(380 / logo.width, 170 / logo.height)
        logo = logo.resize((round(logo.width * fl), round(logo.height * fl)), Image.Resampling.LANCZOS)
        im.paste(logo, (70, 90 + (240 - logo.height) // 2), logo)
        dr = ImageDraw.Draw(im)
    except OSError:
        pass                                                   # sem o logo no checkout: a capa sai sem ele

    X = 80
    if dados["categoria"]:
        fb = _encher(dr, dados["categoria"], 340, 46)
        lb = dr.textlength(dados["categoria"], font=fb)
        dr.rounded_rectangle([X, 560, X + lb + 56, 646], radius=10, fill=VERMELHO)
        dr.text((X + 28, 560 + (86 - fb.size) / 2 - 4), dados["categoria"], font=fb, fill=BRANCO)
    y = 742
    for i, t in enumerate(dados["linhas"]):
        cor = AMARELO if i == len(dados["linhas"]) - 1 else BRANCO
        f1 = _encher(dr, t, min(borda(y + 130) - X - 60, 400), 132)
        dr.text((X, y), t, font=f1, fill=cor)
        y += round(f1.size * 1.14)
    dr.rectangle([X, y + 28, X + 230, y + 42], fill=AZULCLARO)
    if dados["subtitulo"]:
        fs = _encher(dr, dados["subtitulo"], min(borda(y + 120) - X - 60, 360), 44, FONTE_M)
        dr.text((X, y + 88), dados["subtitulo"], font=fs, fill=BRANCO)

    im.convert("RGB").save(caminho, quality=92)
    return {"recorte": pessoa is not None, **dados}
