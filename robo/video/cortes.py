"""Radar Artecon — corretor de vídeo (v0.22.0): o que fica de cada clipe.

A linha do tempo é a de fala48k.wav: os clipes em sequência, o clipe n nos quadros [inicio_q, inicio_q + quadros). O plano sai em
quadros de 1/30 s: o vídeo corta por select(n) e o áudio por atrim (amostra = quadro × 1600), no mesmo instante, sem deriva.

Só saem (desenho 4.1, item 4, e 1.4, decisão 6): silêncio confirmado, som de hesitação que não é palavra e voz entre duas palavras
SEGUIDAS do roteiro. Nenhuma palavra transcrita (fora os sons de hesitação) cai dentro de um corte automático — "um", "uma", "e" e
"é" nunca saem, nem palavra alinhada ao roteiro. Em ordem:
  1. começo e fim de cada clipe: fica de 0,12 s antes da 1ª palavra a 0,45 s depois da última (sem as palavras — reserva, sem
     transcrição — da 1ª à última voz que o silencedetect acha). Clipe sem fala sai inteiro;
  2. entre duas palavras seguidas da transcrição (os sons de hesitação não contam como palavra):
     * com som de hesitação ("hum", "ãh", "ééé"; e_hesitacao), as duas palavras alinhadas a fichas SEGUIDAS do roteiro e a voz do
       intervalo dentro do som de hesitação (com 0,1 s de folga; fora dele, menos de 0,15 s): sai (automático); senão — a voz que
       só encosta no "hum" pode ser a palavra do roteiro dita colada nele, que a transcrição perdeu — vira sugestão;
     * sem palavra, com voz (o que o silencedetect não marca como silêncio) num intervalo de 0,35 a 2,0 s — o "ééé" ou a repetição
       que a transcrição não escreveu: sai só se as duas palavras estão alinhadas a fichas SEGUIDAS do roteiro (`rot_de`/`rot_ate`,
       do alinhar.py: então nenhuma palavra do roteiro pode estar ali); senão — e acima de 2,0 s — vira sugestão;
       nos dois casos o intervalo fica com o mesmo silêncio que uma pausa longa deixaria (o colado em cada palavra) e o corte nunca
       chega a menos de 0,05 s de uma palavra;
     * pausa confirmada como silêncio (silencedetect): dentro da frase, acima de pausa_max_s (1,0) fica com 0,30 s; entre frases (a
       palavra antes da pausa fecha a frase: `fim_frase`, que o alinhamento tira da pontuação do roteiro, ou, sem ele, a pontuação
       da própria palavra), acima de pausa_bloco_s (0,8) fica com 0,40 s. Sem as palavras, toda pausa acima de pausa_bloco_s fica
       com 0,40 s. O corte é só a parte do silêncio que cai entre as duas palavras: nunca entra numa palavra;
  3. `remover` (do alinhamento): as sugestões de repetição e falso início, com o tipo e o texto ouvido; um pedido automático que
     cairia sobre uma palavra vira sugestão (nunca corta);
  4. `manter` (ajustes.manter): os números (k) dos cortes no meio da fala que o administrador mandou manter.
Os cortes são numerados (k) na ordem do tempo ANTES de aplicar o `manter`: o número de um corte não muda quando outro é mantido.

O fim da fala fica intacto: a transição para a cartela começa 0,05 s depois da última palavra; se o clipe acaba antes de 0,45 s depois
dela, o plano pede `pad_q` quadros a mais (o último quadro parado e silêncio), em vez de cortar a palavra com o esmaecer.
"""
from __future__ import annotations

import math
import re
import unicodedata

import numeros
from segredo import ErroVideo
from sondar import FPS

FOLGA_ANTES = 0.12                     # s antes da 1ª palavra do clipe
FOLGA_DEPOIS = 0.45                    # s depois da última (a transição começa em +0,05)
FICA_FRASE = 0.30                      # o que sobra de uma pausa longa dentro da frase
FICA_BLOCO = 0.40                      # e entre frases
VOZ_MINIMA = 0.08                      # "voz" mais curta que isso é estalo (ou a borda da palavra), não fala
VOZ_ENTRE = (0.35, 2.0)                # s: intervalo entre duas palavras em que a voz sem palavra pode sair
VOZ_TRECHO = 0.15                      # s: voz (somada) no intervalo para contar como "ééé" ou repetição não escrita
FOLGA_PALAVRA = 0.05                   # s: um corte no meio da fala nunca chega mais perto que isso de uma palavra (o tempo das
                                       # palavras da transcrição tem erro; calibrar no teste real 1)
COLADO = 0.06                          # s: silêncio que começa (acaba) até isso depois (antes) da palavra é o colado nela
FECHA_FRASE = re.compile(r"[.!?…;:][\"'”»)]*$")
PROTEGIDAS = frozenset({"um", "uma", "e", "é"})
_HESITACAO = re.compile(r"ã+h+|hã+|hu+m+|hm+|a+h+n+")


def e_hesitacao(texto: object) -> bool:
    """Som de hesitação que não é palavra: "ãh", "hã", "hum", "hm", "ahn" ou uma vogal repetida 3 vezes ou mais ("ééé", "eee").
    "um", "uma", "e" e "é" nunca; nem "há" (verbo), "ah" ou "éé"."""
    t = unicodedata.normalize("NFC", str(texto or "")).lower().strip(" .,;:!?…\"'“”()")
    if not t or t in PROTEGIDAS:
        return False
    return bool(_HESITACAO.fullmatch(t) or re.fullmatch(r"([aeiou])\1{2,}", numeros.letras(t)))


def _hesita(w: dict) -> bool:
    """Palavra da transcrição que é só som de hesitação (e não está alinhada ao roteiro: palavra do roteiro nunca sai)."""
    return w.get("rot_de") is None and e_hesitacao(w.get("texto"))


def _seguidas(w1: dict, w2: dict) -> bool:
    """As duas palavras estão alinhadas a fichas seguidas do roteiro (ou à mesma ficha, como "trinta" e "outubro" em "30/10")?"""
    a, b = w1.get("rot_ate"), w2.get("rot_de")
    return a is not None and b is not None and 0 <= b - a <= 1


def _sobre_palavra(c0: float, c1: float, ws: list[dict]) -> bool:
    return any(c0 < w["fim"] - 0.01 and c1 > w["ini"] + 0.01 for w in ws)


def _sobra(g0: float, g1: float, sil: list[tuple[float, float]], fica: float) -> tuple[float, float]:
    """O corte do intervalo (g0, g1) entre duas palavras que deixa até `fica` s de silêncio: o colado em cada palavra, metade de cada
    lado (o que faltar de um lado vem do outro); nunca a menos de FOLGA_PALAVRA de uma palavra."""
    antes = max((b - g0 for a, b in sil if a <= g0 + COLADO), default=0.0)
    depois = max((g1 - a for a, b in sil if b >= g1 - COLADO), default=0.0)
    ka, kb = min(fica / 2, antes), min(fica / 2, depois)
    kb = min(depois, fica - ka)
    ka = min(antes, fica - kb)
    return g0 + max(ka, FOLGA_PALAVRA), g1 - max(kb, FOLGA_PALAVRA)


def _entre(w1: dict, w2: dict, silencios: list[tuple[float, float]], todas: list[dict], limite: float,
           sobra: float) -> list[tuple]:
    """O que sai entre duas palavras seguidas da transcrição: [(ini, fim, tipo, automático, texto)]."""
    g0, g1 = w1["fim"], w2["ini"]
    if g1 <= g0:
        return []
    sil = [(max(s, g0), min(e, g1)) for s, e in silencios if e > g0 and s < g1]
    hes = [w for w in todas if _hesita(w) and g0 <= (w["ini"] + w["fim"]) / 2 <= g1]
    voz = [(a, b) for a, b in _menos((g0, g1), sil) if b - a >= VOZ_MINIMA]
    sugestao = []
    if hes or (g1 - g0 >= VOZ_ENTRE[0] and sum(b - a for a, b in voz) >= VOZ_TRECHO):
        tipo, texto = ("hesitacao", " ".join(w["texto"] for w in hes)[:40]) if hes else ("voz_entre_palavras", None)
        if hes:                                         # só entre palavras seguidas do roteiro (nenhuma palavra dele pode estar ali)
            # e com a voz do intervalo dentro dos sons de hesitação (0,1 s de folga; fora deles, menos de VOZ_TRECHO: o vão curto demais
            # para o silencedetect): a voz que só encosta no "hum" pode ser a palavra dita colada nele que a transcrição perdeu
            # ("você hum não precisa", sem o "não")
            fora = sum(b - a for v in voz for a, b in _menos(v, [(h["ini"] - 0.1, h["fim"] + 0.1) for h in hes]))
            auto = _seguidas(w1, w2) and fora < VOZ_TRECHO
        else:                                           # acima de 2,0 s pode ser fala que a transcrição perdeu: só sugestão
            auto = g1 - g0 <= VOZ_ENTRE[1] and _seguidas(w1, w2)
        if auto:
            a, b = _sobra(g0, g1, sil, sobra)
            return [(a, b, tipo, True, texto)] if b - a >= 1 / FPS else []
        sugestao = [(g0, g1, tipo, False, texto)]
    return sugestao + [(s + sobra / 2, e - sobra / 2, "pausa", True, None) for s, e in sil if e - s > limite]


def _q_ini(t: float) -> int:
    return math.floor(t * FPS + 1e-6)


def _q_fim(t: float) -> int:
    return math.ceil(t * FPS - 1e-6)


def _juntar(trechos: list[tuple[int, int]]) -> list[list[int]]:
    out: list[list[int]] = []
    for a, b in sorted(trechos):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _menos(base: tuple[float, float], tirar: list[tuple[float, float]]) -> list[tuple[float, float]]:
    fica = [base]
    for c0, c1 in sorted(tirar):
        nova = []
        for a, b in fica:
            if c1 <= a or c0 >= b:
                nova.append((a, b))
                continue
            if c0 > a:
                nova.append((a, c0))
            if c1 < b:
                nova.append((c1, b))
        fica = nova
    return fica


def _voz(silencios: list[tuple[float, float]], p0: float, p1: float) -> list[tuple[float, float]]:
    return [(a, b) for a, b in _menos((p0, p1), [(max(p0, s), min(p1, e)) for s, e in silencios if e > p0 and s < p1])
            if b - a >= VOZ_MINIMA]


def remapear(plano: dict, t: float) -> tuple[float, bool]:
    """O instante t (linha de fala48k.wav) no vídeo corrigido, e se ele ficou (False: caiu num corte e foi levado à emenda)."""
    acum = 0
    for qa, qb in plano["trechos"]:
        if t < qa / FPS:
            return acum / FPS, False
        if t <= qb / FPS:
            return acum / FPS + (t - qa / FPS), True
        acum += qb - qa
    return acum / FPS, False


def planejar(partes: list[dict], silencios: list[tuple[float, float]], cfg: dict, palavras: list[dict] | None = None,
             remover: list[dict] = (), manter=()) -> dict:
    """partes: as de sondar (com inicio_q de audio.extrair); palavras: [{texto, ini, fim, fim_frase?, rot_de?, rot_ate?}] na linha de
    fala48k.wav, em ordem (alinhar.alinhar → "palavras"); remover: [{ini, fim, tipo, automatico, texto?}]; manter: números k.
    Devolve {trechos, cortes, sugestoes, fala_q, pad_q, ultima_s}."""
    pausa_max, pausa_bloco = float(cfg.get("pausa_max_s", 1.0)), float(cfg.get("pausa_bloco_s", 0.8))
    manter = {int(k) for k in manter}
    cortes, sugestoes, fica, ultima = [], [], [], None
    for p in partes:
        p0, p1 = p["inicio_q"] / FPS, (p["inicio_q"] + p["quadros"]) / FPS
        meio: list[tuple[float, float, str, bool, str | None]] = []
        ws: list[dict] = []
        if palavras is not None:
            todas = [w for w in palavras if p0 <= (w["ini"] + w["fim"]) / 2 < p1]
            ws = [w for w in todas if not _hesita(w)]
            borda = (ws[0]["ini"], ws[-1]["fim"]) if ws else None
            for w1, w2 in zip(ws, ws[1:]):
                frase = w1.get("fim_frase")
                if frase is None:
                    frase = bool(FECHA_FRASE.search(str(w1.get("texto") or "").strip()))
                limite, sobra = (pausa_bloco, FICA_BLOCO) if frase else (pausa_max, FICA_FRASE)
                meio += _entre(w1, w2, silencios, todas, limite, sobra)
        else:
            voz = _voz(silencios, p0, p1)
            borda = (voz[0][0], voz[-1][1]) if voz else None
            for (_, v1), (v2, _) in zip(voz, voz[1:]):
                if v2 - v1 > pausa_bloco:
                    meio.append((v1 + FICA_BLOCO / 2, v2 - FICA_BLOCO / 2, "pausa", True, None))
        if borda is None:
            cortes.append({"clipe": p["n"], "de_s": 0.0, "ate_s": round(p1 - p0, 2), "tipo": "clipe_sem_fala"})
            continue
        a, b = max(p0, borda[0] - FOLGA_ANTES), min(p1, borda[1] + FOLGA_DEPOIS)
        for r in remover:
            r0, r1 = float(r["ini"]), float(r["fim"])
            if a < r0 < r1 < b and p0 <= (r0 + r1) / 2 < p1:
                texto = str(r["texto"])[:80] if r.get("texto") else None
                # nunca um corte automático sobre uma palavra (fora os sons de hesitação): vira sugestão
                meio.append((r0, r1, str(r.get("tipo") or "remover"), bool(r.get("automatico")) and not _sobre_palavra(r0, r1, ws),
                             texto))
        if a - p0 >= 1 / FPS:
            cortes.append({"clipe": p["n"], "de_s": 0.0, "ate_s": round(a - p0, 2), "tipo": "inicio"})
        for m0, m1, tipo, auto, texto in sorted(meio, key=lambda x: (x[0], x[1])):
            extra = {"texto": texto} if texto else {}
            if not auto:
                sugestoes.append({"ini": m0, "fim": m1, "clipe": p["n"], "tipo": tipo, **extra})
            elif m1 - m0 >= 1 / FPS:
                cortes.append({"clipe": p["n"], "ini": m0, "fim": m1, "tipo": tipo, "automatico": True, **extra})
        if p1 - b >= 1 / FPS:
            cortes.append({"clipe": p["n"], "de_s": round(b - p0, 2), "ate_s": round(p1 - p0, 2), "tipo": "fim"})
        fica.append((p, a, b))
        ultima = borda[1]
    if not fica:
        raise ErroVideo("sem_fala", "cortes")
    for k, c in enumerate(cortes):
        c["k"] = k
        if "ini" in c:
            c["mantido"] = k in manter
    trechos = []
    for p, a, b in fica:                                # juntados dentro do clipe: um trecho nunca passa de um clipe para o outro
        q0, q1 = p["inicio_q"], p["inicio_q"] + p["quadros"]
        tirar = [(c["ini"], c["fim"]) for c in cortes if c["clipe"] == p["n"] and "ini" in c and not c["mantido"]]
        trechos += _juntar([(max(q0, _q_ini(x)), min(q1, _q_fim(y))) for x, y in _menos((a, b), tirar)])
    plano = {"trechos": trechos}
    plano["fala_q"] = sum(qb - qa for qa, qb in plano["trechos"])
    for c in cortes:                                    # no relatório, o corte do meio aparece no tempo do vídeo corrigido
        if "ini" in c:
            ini, fim = c.pop("ini"), c.pop("fim")
            c["em_s"], c["dur_s"] = round(remapear(plano, ini)[0], 2), round(fim - ini, 2)
    ultima_s = remapear(plano, ultima)[0]
    precisa = ultima_s + FOLGA_DEPOIS
    plano.update(cortes=cortes, sugestoes=[{"em_s": round(remapear(plano, s["ini"])[0], 2), "dur_s": round(s["fim"] - s["ini"], 2),
                                            "clipe": s["clipe"], "tipo": s["tipo"], **({"texto": s["texto"]} if s.get("texto") else {})}
                                           for s in sugestoes],
                 ultima_s=round(ultima_s, 3), pad_q=max(0, _q_fim(precisa - plano["fala_q"] / FPS)))
    return plano


def no_video(plano: dict, unidades: list[dict]) -> list[dict]:
    """As unidades da legenda (alinhar.alinhar → "legenda": [{u, texto, ini, fim}] na linha de fala48k.wav) no tempo do vídeo
    corrigido, para legenda.gravar. A que caiu inteira num corte (só um som de hesitação poderia) fica de fora."""
    out = []
    for u in unidades:
        a, fica_a = remapear(plano, float(u["ini"]))
        b, fica_b = remapear(plano, float(u["fim"]))
        if not (fica_a or fica_b) and b - a < 0.02:
            continue
        out.append({**u, "ini": round(a, 3), "fim": round(max(b, a + 0.04), 3)})
    return out


def por_clipe(plano: dict, partes: list[dict]) -> dict[int, list[tuple[int, int]]]:
    """Os trechos de cada clipe, em quadros do próprio clipe (para o select do vídeo)."""
    out: dict[int, list[tuple[int, int]]] = {}
    for p in partes:
        q0, q1 = p["inicio_q"], p["inicio_q"] + p["quadros"]
        locais = [(qa - q0, qb - q0) for qa, qb in plano["trechos"] if q0 <= qa < q1]
        if locais:
            out[p["n"]] = locais
    return out
