"""Radar Artecon — corretor de vídeo (v0.22.0): o que fica de cada clipe.

A linha do tempo é a de fala48k.wav: os clipes em sequência, o clipe n nos quadros [inicio_q, inicio_q + quadros). O plano sai em
quadros de 1/30 s: o vídeo corta por select(n) e o áudio por atrim (amostra = quadro × 1600), no mesmo instante, sem deriva.

Só saem (desenho 4.1, item 4, e 1.4, decisão 6; v0.33.0: o pedido do dono — "o aplicativo não corrigiu nada" — fez as muletas
faladas e a voz entre palavras saírem POR PADRÃO, cada corte com a chave e "Manter este trecho" para desfazer): silêncio confirmado,
som de hesitação que não é palavra, muleta falada fora do roteiro ("né", "tipo", "é" solto; e_muleta) e voz entre duas palavras.
Nenhuma OUTRA palavra transcrita cai dentro de um corte automático — palavra alinhada ao roteiro nunca sai, e o falado fora do
roteiro que não é muleta fica (a aba Vídeo o marca para cortar com um clique: pode mudar o sentido). Em ordem:
  1. começo e fim de cada clipe: fica de 0,12 s antes da 1ª palavra a 0,45 s depois da última (sem as palavras — reserva, sem
     transcrição — da 1ª à última voz que o silencedetect acha). Clipe sem fala sai inteiro;
  2. entre duas palavras seguidas da transcrição (os sons de hesitação e as muletas não contam como palavra):
     * com som de hesitação ("hum", "ãh", "ééé"; e_hesitacao) ou muleta fora do roteiro ("né", "tipo", "é" solto; e_muleta), as duas
       palavras alinhadas a fichas SEGUIDAS do roteiro e a voz do intervalo dentro deles (com 0,1 s de folga; fora deles, menos de
       0,15 s): sai (automático; tipo "muleta" quando há muleta); senão — a voz que só encosta no "hum" pode ser a palavra do
       roteiro dita colada nele, que a transcrição perdeu — vira sugestão;
     * sem palavra, com voz (o que o silencedetect não marca como silêncio) num intervalo de 0,35 a 2,0 s — o "ééé" ou a repetição
       que a transcrição não escreveu: sai POR PADRÃO (v0.33.0; antes pedia palavras seguidas do roteiro) — "Manter este trecho"
       desfaz, e o que do roteiro não foi dito continua em "omitido": nada some em silêncio; acima de 2,0 s vira sugestão (pode ser
       fala que a transcrição perdeu);
       nos dois casos o intervalo fica com o mesmo silêncio que uma pausa longa deixaria (o colado em cada palavra) e o corte nunca
       chega a menos de 0,05 s de uma palavra;
     * pausa confirmada como silêncio (silencedetect): dentro da frase, acima de pausa_max_s (1,0) fica com 0,30 s; entre frases (a
       palavra antes da pausa fecha a frase: `fim_frase`, que o alinhamento tira da pontuação do roteiro, ou, sem ele, a pontuação
       da própria palavra), acima de pausa_bloco_s (0,8) fica com 0,40 s. Sem as palavras, toda pausa acima de pausa_bloco_s fica
       com 0,40 s. O corte é só a parte do silêncio que cai entre as duas palavras: nunca entra numa palavra;
  3. `remover` (do alinhamento): as repetições ("a a", "devem devem") e os falsos inícios ("pra- prazo"), cortados POR PADRÃO
     (v0.33.0; antes eram só sugestão) — a palavra repetida, que não está no roteiro, sai inteira; um pedido que cortaria uma
     palavra pela metade, ou uma palavra alinhada ao roteiro, vira sugestão (nunca corta);
  4. `manter` (ajustes.manter): as chaves dos cortes no meio da fala que o administrador mandou manter.
Os cortes são numerados (k) na ordem do tempo, para o relatório; o do meio da fala leva também a `chave` "<clipe>:<quadro>", o quadro
(1/30 s, na linha de fala48k.wav) em que começa o que ele corta — o silêncio da pausa, o vão entre as duas palavras (hesitação, voz
entre palavras) ou o trecho pedido —, que não depende do resto da lista. É por ela que o `manter` aponta: o alinhamento é refeito a
cada rodada ("A transcrição errou" muda a pontuação que fecha a frase, e com ela o limite da pausa; as Configurações podem ter mudado),
um corte pode entrar ou sair e o número k dos outros muda; a chave de um corte nunca vira a de outro. A que não confere não mantém nada.

O fim da fala fica intacto: a transição para a cartela começa 0,05 s depois da última palavra; se o clipe acaba antes de 0,45 s depois
dela, o plano pede `pad_q` quadros a mais (o último quadro parado e silêncio), em vez de cortar a palavra com o esmaecer.

v0.33.0 (a aba Vídeo): as mudanças do editor (ajustes.cortar, inicio_q e fim_q, em QUADROS da linha original — edicao_de) entram no
plano: o começo e o fim marcados encolhem a faixa de cada clipe (o clipe que fica sem nada sai inteiro: "editor_fora"), e cada trecho
de "cortar" sai como um corte do meio da fala (tipo "editor", chave "e:<q0>"), que PODE passar por cima de uma palavra (é o
administrador que pede, ouvindo a prévia); o "manter" não vale para ele. A última palavra passa a ser a última que ficou, e a fala
com menos de 2 s para com o código `edicao_curta`. O plano ganha o que o relatório leva no "mapa" (relatorio.py) — a faixa de cada
clipe antes do editor, os cortes automáticos no meio da fala (com a chave e os quadros que tiram), a linha inteira (linha_q) e a
edição aplicada e as palavras (ini e fim em ms: o pad do fim depende da última que fica) —, que a tela e o banco usam para converter
o tempo do vídeo em quadros da linha original e estimar a duração depois de montar (duracao_estimada: a mesma conta de
radar_video_edicao_duracao e da tela, que segue o plano: a fala que fica mais o pad_q). Sem as mudanças do editor, o plano é o de antes.
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
CHAVE = re.compile(r"\d{1,2}:\d{1,6}b{0,3}")       # a chave de um corte no meio da fala (ajustes.manter)
CORTE_MIN_Q = 3                        # v0.33.0: o corte do editor tem 3 quadros (0,1 s) ou mais
FALA_MIN_Q = 60                        # e a fala que fica, 2 s ou mais
FOLGA_FIM_S, TRANSICAO_S = 0.45, 0.4   # a estimativa da duração (radar_video_paleta: folga_fim_s = FOLGA_DEPOIS, transicao_s)
PROTEGIDAS = frozenset({"um", "uma", "e", "é"})
_HESITACAO = re.compile(r"ã+h+|hã+|hu+m+|hm+|a+h+n+")
# v0.33.0: as muletas faladas que saem por padrão quando NÃO estão alinhadas ao roteiro ("né", "tipo" e o "é" solto; o pedido do
# dono). "tipo" e "é" do roteiro ("o tipo de empresa", "o prazo é dia 20") se alinham e nunca saem; o "Manter este trecho" desfaz.
MULETAS = frozenset({"né", "ne", "tipo", "é"})


def e_hesitacao(texto: object) -> bool:
    """Som de hesitação que não é palavra: "ãh", "hã", "hum", "hm", "ahn" ou uma vogal repetida 3 vezes ou mais ("ééé", "eee").
    "um", "uma", "e" e "é" nunca; nem "há" (verbo), "ah" ou "éé"."""
    t = unicodedata.normalize("NFC", str(texto or "")).lower().strip(" .,;:!?…\"'“”()")
    if not t or t in PROTEGIDAS:
        return False
    return bool(_HESITACAO.fullmatch(t) or re.fullmatch(r"([aeiou])\1{2,}", numeros.letras(t)))


def e_muleta(texto: object) -> bool:
    """Muleta falada ("né", "tipo", "é" solto), que sai do vídeo quando não está alinhada ao roteiro (v0.33.0)."""
    t = unicodedata.normalize("NFC", str(texto or "")).lower().strip(" .,;:!?…\"'“”()")
    return t in MULETAS


def _hesita(w: dict) -> bool:
    """Palavra da transcrição que é só som de hesitação ou muleta (e não está alinhada ao roteiro: palavra do roteiro nunca sai)."""
    return w.get("rot_de") is None and (e_hesitacao(w.get("texto")) or e_muleta(w.get("texto")))


def _seguidas(w1: dict, w2: dict) -> bool:
    """As duas palavras estão alinhadas a fichas seguidas do roteiro (ou à mesma ficha, como "trinta" e "outubro" em "30/10")?"""
    a, b = w1.get("rot_ate"), w2.get("rot_de")
    return a is not None and b is not None and 0 <= b - a <= 1


def _sobre_palavra(c0: float, c1: float, ws: list[dict]) -> bool:
    """O corte [c0, c1] pegaria palavra que tem de ficar? A alinhada ao roteiro, sempre; a fora do roteiro, só se o corte a pegasse
    pela metade (inteira dentro dele, ela É o que o pedido tira: a repetição e o falso início saem por padrão desde a v0.33.0)."""
    return any(c0 < w["fim"] - 0.01 and c1 > w["ini"] + 0.01
               and (w.get("rot_de") is not None or not (c0 - 0.01 <= w["ini"] and w["fim"] <= c1 + 0.01)) for w in ws)


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
    """O que sai entre duas palavras seguidas da transcrição: [(ini, fim, tipo, automático, texto, base)] — base: onde começa o que é
    cortado (o vão entre as palavras ou o silêncio), para a chave do corte."""
    g0, g1 = w1["fim"], w2["ini"]
    if g1 <= g0:
        return []
    sil = [(max(s, g0), min(e, g1)) for s, e in silencios if e > g0 and s < g1]
    hes = [w for w in todas if _hesita(w) and g0 <= (w["ini"] + w["fim"]) / 2 <= g1]
    voz = [(a, b) for a, b in _menos((g0, g1), sil) if b - a >= VOZ_MINIMA]
    sugestao = []
    if hes or (g1 - g0 >= VOZ_ENTRE[0] and sum(b - a for a, b in voz) >= VOZ_TRECHO):
        tipo = ("muleta" if any(e_muleta(w.get("texto")) for w in hes) else "hesitacao") if hes else "voz_entre_palavras"
        texto = " ".join(w["texto"] for w in hes)[:40] if hes else None
        if hes:                                         # só entre palavras seguidas do roteiro (nenhuma palavra dele pode estar ali)
            # e com a voz do intervalo dentro dos sons (0,1 s de folga; fora deles, menos de VOZ_TRECHO: o vão curto demais para o
            # silencedetect): a voz que só encosta no "hum" pode ser a palavra dita colada nele que a transcrição perdeu
            # ("você hum não precisa", sem o "não") — essa continua sugestão
            fora = sum(b - a for v in voz for a, b in _menos(v, [(h["ini"] - 0.1, h["fim"] + 0.1) for h in hes]))
            auto = _seguidas(w1, w2) and fora < VOZ_TRECHO
        else:
            # v0.33.0 (pedido do dono: "aplicar as sugestões por padrão"): a voz sem palavra num intervalo de até 2,0 s sai POR
            # PADRÃO, mesmo entre palavras que não são seguidas do roteiro — o que do roteiro não foi dito continua em "omitido"
            # (nada some em silêncio) e "Manter este trecho" desfaz. Acima de 2,0 s pode ser fala que a transcrição perdeu: sugestão
            auto = g1 - g0 <= VOZ_ENTRE[1]
        if auto:
            a, b = _sobra(g0, g1, sil, sobra)
            return [(a, b, tipo, True, texto, g0)] if b - a >= 1 / FPS else []
        sugestao = [(g0, g1, tipo, False, texto, g0)]
    return sugestao + [(s + sobra / 2, e - sobra / 2, "pausa", True, None, s) for s, e in sil if e - s > limite]


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


def _inteiro(x) -> int | None:
    return x if isinstance(x, int) and not isinstance(x, bool) else None


def edicao_de(ajustes: dict | None, linha_q: int) -> dict | None:
    """As mudanças de corte do editor da aba Vídeo (ajustes.cortar, inicio_q e fim_q; quadros da linha original), só os inteiros,
    dentro de [0, linha_q]: os cortes ordenados e juntos (os de menos de 3 quadros saem), e o começo e o fim (o começo depois do fim
    faz cair os dois). None: nenhuma (o plano é o de antes)."""
    a = ajustes if isinstance(ajustes, dict) else {}
    dentro = lambda q: max(0, min(int(linha_q), q))
    cortar = []
    for c in (a.get("cortar") if isinstance(a.get("cortar"), list) else [])[:30]:
        if isinstance(c, (list, tuple)) and len(c) == 2 and _inteiro(c[0]) is not None and _inteiro(c[1]) is not None:
            q0, q1 = dentro(c[0]), dentro(c[1])
            if q1 - q0 >= CORTE_MIN_Q:
                cortar.append((q0, q1))
    cortar = [(a0, b0) for a0, b0 in _juntar(cortar)]
    ini = dentro(a["inicio_q"]) if _inteiro(a.get("inicio_q")) is not None else None
    fim = dentro(a["fim_q"]) if _inteiro(a.get("fim_q")) is not None else None
    if ini is not None and fim is not None and ini >= fim:
        ini = fim = None
    if not cortar and ini is None and fim is None:
        return None
    return {"cortar": cortar, "inicio_q": ini, "fim_q": fim}


def _tirado_pelo_editor(edicao: dict | None, q0: int, q1: int) -> bool:
    """Os quadros [q0, q1) da linha original saem todos pelo editor (antes do começo, depois do fim ou nos cortes)?"""
    if not edicao or q1 <= q0:
        return False
    tirar = [(int(c0), int(c1)) for c0, c1 in edicao.get("cortar") or []]
    if edicao.get("inicio_q") is not None:
        tirar.append((0, int(edicao["inicio_q"])))
    if edicao.get("fim_q") is not None:
        tirar.append((int(edicao["fim_q"]), 10 ** 9))
    return not _menos((q0, q1), tirar)


def planejar(partes: list[dict], silencios: list[tuple[float, float]], cfg: dict, palavras: list[dict] | None = None,
             remover: list[dict] = (), manter=(), edicao: dict | None = None) -> dict:
    """partes: as de sondar (com inicio_q de audio.extrair); palavras: [{texto, ini, fim, fim_frase?, rot_de?, rot_ate?}] na linha de
    fala48k.wav, em ordem (alinhar.alinhar → "palavras"); remover: [{ini, fim, tipo, automatico, texto?}]; manter: as chaves
    ("<clipe>:<quadro>") dos cortes a manter; edicao: edicao_de(ajustes) (v0.33.0). Devolve {trechos, cortes, sugestoes, fala_q, pad_q,
    ultima_s} e, para o mapa do relatório, {faixas, automaticos, linha_q, edicao, palavras}."""
    pausa_max, pausa_bloco = float(cfg.get("pausa_max_s", 1.0)), float(cfg.get("pausa_bloco_s", 0.8))
    manter = {k for k in manter if isinstance(k, str) and CHAVE.fullmatch(k)}
    cortes, sugestoes, fica, ultima, chaves = [], [], [], None, set()
    faixas, automaticos, ws_todas = [], [], []
    linha_q = (partes[-1]["inicio_q"] + partes[-1]["quadros"]) if partes else 0
    for p in partes:
        p0, p1 = p["inicio_q"] / FPS, (p["inicio_q"] + p["quadros"]) / FPS
        meio: list[tuple[float, float, str, bool, str | None, float]] = []
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
            ws_fim = [{"ini": a, "fim": b} for a, b in voz]   # sem a transcrição, a voz faz o papel das palavras no fim do vídeo
            for (_, v1), (v2, _) in zip(voz, voz[1:]):
                if v2 - v1 > pausa_bloco:
                    meio.append((v1 + FICA_BLOCO / 2, v2 - FICA_BLOCO / 2, "pausa", True, None, v1))
        if borda is None:
            cortes.append({"clipe": p["n"], "de_s": 0.0, "ate_s": round(p1 - p0, 2), "tipo": "clipe_sem_fala"})
            continue
        a, b = max(p0, borda[0] - FOLGA_ANTES), min(p1, borda[1] + FOLGA_DEPOIS)
        if palavras is not None:                        # v0.33.0: a muleta colada na borda ("…até sexta né") sai com o começo ou o fim
            soltas = [w for w in todas if _hesita(w)]
            fim_solto = min((w["ini"] for w in soltas if w["ini"] >= borda[1]), default=None)
            if fim_solto is not None:
                b = min(b, max(borda[1] + FOLGA_PALAVRA, fim_solto - FOLGA_PALAVRA))
            ini_solto = max((w["fim"] for w in soltas if w["fim"] <= borda[0]), default=None)
            if ini_solto is not None:
                a = max(a, min(borda[0] - FOLGA_PALAVRA, ini_solto + FOLGA_PALAVRA))
        q0c, q1c = p["inicio_q"], p["inicio_q"] + p["quadros"]
        faixas.append([max(q0c, _q_ini(a)), min(q1c, _q_fim(b))])
        ws_todas += ws if palavras is not None else ws_fim
        if edicao:                                       # v0.33.0: o começo e o fim marcados no editor
            a0, b0 = a, b
            if edicao.get("inicio_q") is not None:
                a = max(a, edicao["inicio_q"] / FPS)
            if edicao.get("fim_q") is not None:
                b = min(b, edicao["fim_q"] / FPS)
            if b - a < 1 / FPS:
                cortes.append({"clipe": p["n"], "de_s": round(a0 - p0, 2), "ate_s": round(b0 - p0, 2), "tipo": "editor_fora"})
                continue
        for r in remover:
            r0, r1 = float(r["ini"]), float(r["fim"])
            if a < r0 < r1 < b and p0 <= (r0 + r1) / 2 < p1:
                texto = str(r["texto"])[:80] if r.get("texto") else None
                # nunca um corte automático sobre uma palavra (fora os sons de hesitação): vira sugestão
                meio.append((r0, r1, str(r.get("tipo") or "remover"), bool(r.get("automatico")) and not _sobre_palavra(r0, r1, ws),
                             texto, r0))
        if a - p0 >= 1 / FPS:
            cortes.append({"clipe": p["n"], "de_s": 0.0, "ate_s": round(a - p0, 2), "tipo": "inicio"})
        for m0, m1, tipo, auto, texto, base in sorted(meio, key=lambda x: (x[0], x[1])):
            extra = {"texto": texto} if texto else {}
            if not auto:
                if not _tirado_pelo_editor(edicao, _q_ini(m0), max(_q_fim(m1), _q_ini(m0) + 1)):
                    sugestoes.append({"ini": m0, "fim": m1, "clipe": p["n"], "tipo": tipo, **extra})
            elif m1 - m0 >= 1 / FPS:
                chave = f"{p['n']}:{_q_ini(base)}"
                while chave in chaves:                  # dois cortes no mesmo quadro (só um pedido de fora poderia): o 2º leva "b"
                    chave += "b"
                chaves.add(chave)
                cortes.append({"clipe": p["n"], "ini": m0, "fim": m1, "tipo": tipo, "automatico": True, "chave": chave, **extra})
                # para o mapa: os quadros que este corte tira (o que fica dos dois lados vai até o quadro que encosta nele)
                automaticos.append({"chave": chave, "de": max(q0c, _q_fim(m0)), "ate": min(q1c, _q_ini(m1))})
        for e0, e1 in (edicao or {}).get("cortar") or []:    # v0.33.0: os cortes do editor neste clipe (podem passar por uma palavra)
            c0, c1 = max(e0, q0c, _q_ini(a)), min(e1, q1c, _q_fim(b))
            if c1 - c0 < 1:
                continue
            dentro = [w["texto"] for w in ws if w["ini"] < c1 / FPS and w["fim"] > c0 / FPS]
            chave = f"e:{e0}" + ("" if c0 == e0 else f"b{p['n']}")
            cortes.append({"clipe": p["n"], "ini": c0 / FPS, "fim": c1 / FPS, "tipo": "editor", "automatico": True, "chave": chave,
                           **({"texto": " ".join(dentro)[:80]} if dentro else {})})
        if p1 - b >= 1 / FPS:
            cortes.append({"clipe": p["n"], "de_s": round(b - p0, 2), "ate_s": round(p1 - p0, 2), "tipo": "fim"})
        fica.append((p, a, b))
        ultima = borda[1]
    if not fica:
        raise ErroVideo("edicao_curta" if edicao else "sem_fala", "cortes")
    if edicao:                                           # os cortes do editor entram na ordem do tempo, com os outros
        cortes.sort(key=lambda c: (c["clipe"], c.get("ini", -1 if c["tipo"] == "inicio" else 10 ** 6 if c["tipo"] in ("fim", "editor_fora",
                                                                                                                  "clipe_sem_fala") else 0)))
    for k, c in enumerate(cortes):
        c["k"] = k
        if "ini" in c:
            c["mantido"] = c["tipo"] != "editor" and c["chave"] in manter
    trechos = []
    for p, a, b in fica:                                # juntados dentro do clipe: um trecho nunca passa de um clipe para o outro
        q0, q1 = p["inicio_q"], p["inicio_q"] + p["quadros"]
        tirar = [(c["ini"], c["fim"]) for c in cortes if c["clipe"] == p["n"] and "ini" in c and not c["mantido"]]
        trechos += _juntar([(max(q0, _q_ini(x)), min(q1, _q_fim(y))) for x, y in _menos((a, b), tirar)])
    plano = {"trechos": trechos}
    plano["fala_q"] = sum(qb - qa for qa, qb in plano["trechos"])
    if edicao:
        if plano["fala_q"] < FALA_MIN_Q:                # o editor deixou menos de 2 s de fala
            raise ErroVideo("edicao_curta", "cortes")
        # a última palavra é a última que ficou (no último trecho; a cortada no meio termina onde o trecho termina)
        qa, qb = plano["trechos"][-1]
        dentro = [w["fim"] for w in ws_todas if w["ini"] < qb / FPS and w["fim"] > qa / FPS]
        ultima = min(max(dentro), qb / FPS) if dentro else qa / FPS
    for c in cortes:                                    # no relatório, o corte do meio aparece no tempo do vídeo corrigido
        if "ini" in c:
            ini, fim = c.pop("ini"), c.pop("fim")
            c["em_s"], c["dur_s"] = round(remapear(plano, ini)[0], 2), round(fim - ini, 2)
    ultima_s = remapear(plano, ultima)[0]
    precisa = ultima_s + FOLGA_DEPOIS
    plano.update(cortes=cortes, sugestoes=[{"em_s": round(remapear(plano, s["ini"])[0], 2), "dur_s": round(s["fim"] - s["ini"], 2),
                                            "clipe": s["clipe"], "tipo": s["tipo"], **({"texto": s["texto"]} if s.get("texto") else {})}
                                           for s in sugestoes],
                 ultima_s=round(ultima_s, 3), pad_q=max(0, _q_fim(precisa - plano["fala_q"] / FPS)),
                 faixas=faixas, automaticos=[x for x in automaticos if x["ate"] > x["de"]], linha_q=linha_q,
                 palavras=[[round(w["ini"] * 1000), round(w["fim"] * 1000)] for w in ws_todas],
                 edicao={"cortar": [list(c) for c in edicao["cortar"]], "inicio_q": edicao["inicio_q"], "fim_q": edicao["fim_q"]}
                 if edicao else None)
    return plano


def _fica(mapa: dict, ajustes: dict | None, q: int) -> bool:
    """O quadro q da linha original fica no vídeo, pelo mapa e pelos ajustes (a regra de radar_video_edicao_duracao)?"""
    a = ajustes if isinstance(ajustes, dict) else {}
    manter = set(x for x in (a.get("manter") or []) if isinstance(x, str))
    ini, fim = _inteiro(a.get("inicio_q")), _inteiro(a.get("fim_q"))
    cortar = [c for c in (a.get("cortar") or []) if isinstance(c, (list, tuple)) and len(c) == 2]
    return (any(f0 <= q < f1 for f0, f1 in mapa.get("faixas") or [])
            and not any(x["de"] <= q < x["ate"] and x["chave"] not in manter for x in mapa.get("automaticos") or [])
            and not any(c0 <= q < c1 for c0, c1 in cortar)
            and (ini is None or q >= ini) and (fim is None or q < fim))


LINHA_MAX_Q = 29000                    # v0.33.0: 960 s (sondar.TOTAL_MAX_S) × 30 + folga (era 4000, quando o bruto parava em 120 s)


def _ficam(mapa: dict, ajustes: dict | None) -> list[int]:
    return [q for q in range(min(int(mapa.get("linha_q") or 0), LINHA_MAX_Q)) if _fica(mapa, ajustes, q)]


def fala_estimada_q(mapa: dict, ajustes: dict | None) -> int:
    """Os quadros de fala que ficam depois de montar com estes ajustes (a mesma conta do banco e da tela)."""
    return len(_ficam(mapa, ajustes))


def _pad_estimado_q(mapa: dict, ficam: list[int]) -> int:
    """O pad_q do plano (o último quadro parado e silêncio no fim) pelo mapa: o último trecho que fica é [qa, qb) (a última sequência de
    quadros, dentro da faixa do clipe); a última palavra é a que termina mais tarde entre as que passam por ele (cortada no meio, termina
    onde o trecho termina; nenhuma, o começo do trecho); o vídeo precisa de FOLGA_DEPOIS depois dela — o que o trecho não tiver, o pad
    dá. A mesma conta do planejar (precisa − fala), em quadros."""
    if not ficam:
        return 0
    qb = ficam[-1] + 1
    f0 = min((int(f[0]) for f in mapa.get("faixas") or [] if f[0] <= qb - 1 < f[1]), default=ficam[-1])
    i = len(ficam) - 1
    while i > 0 and ficam[i - 1] == ficam[i] - 1 and ficam[i - 1] >= f0:
        i -= 1
    qa = ficam[i]
    fins = [w[1] for w in mapa.get("palavras") or [] if isinstance(w, (list, tuple)) and len(w) == 2
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in w) and w[0] * 3 < qb * 100 and w[1] * 3 > qa * 100]
    u = min(max(fins) * 3 / 100, qb) if fins else qa         # em quadros (ms × 30 / 1000)
    return max(0, math.ceil(u - qb + FOLGA_DEPOIS * FPS - 1e-6))


def estimada_q(mapa: dict, ajustes: dict | None) -> int:
    """Os quadros da fala no vídeo montado com estes ajustes: a fala que fica mais o pad do fim (= fala_q + pad_q do plano)."""
    ficam = _ficam(mapa, ajustes)
    return len(ficam) + _pad_estimado_q(mapa, ficam)


def duracao_estimada(mapa: dict, ajustes: dict | None, cartela_s: float) -> float:
    """A duração do vídeo depois de montar (radar_video_edicao_duracao no banco, duracaoEstimadaVideo na tela), como o montar: a fala
    que fica e o pad do fim (estimada_q), a cartela e menos a transição. Arredondada como o numeric do Postgres (meio para cima)."""
    from decimal import ROUND_HALF_UP, Decimal
    s = Decimal(estimada_q(mapa, ajustes)) / Decimal(30) + Decimal(str(cartela_s)) - Decimal(str(TRANSICAO_S))
    return float(s.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def original(plano_ou_mapa: dict, t: float) -> int | None:
    """O quadro da linha original do instante t do vídeo corrigido (None: depois da fala, na cartela)."""
    q, acum = math.floor(float(t) * FPS + 1e-6), 0
    for qa, qb in plano_ou_mapa["trechos"]:
        if q < acum + (qb - qa):
            return qa + (q - acum)
        acum += qb - qa
    return None


def video_de(plano_ou_mapa: dict, q: int) -> tuple[float, bool]:
    """O instante no vídeo corrigido do quadro q da linha original, e se ele ficou (False: caiu num corte e foi levado à emenda)."""
    acum = 0
    for qa, qb in plano_ou_mapa["trechos"]:
        if q < qa:
            return acum / FPS, False
        if q < qb:
            return (acum + q - qa) / FPS, True
        acum += qb - qa
    return acum / FPS, False


def no_video(plano: dict, unidades: list[dict]) -> list[dict]:
    """As unidades da legenda (alinhar.alinhar → "legenda": [{u, texto, ini, fim}] na linha de fala48k.wav) no tempo do vídeo
    corrigido, para legenda.gravar. A que caiu inteira num corte (um som de hesitação; v0.33.0: ou um corte do editor) fica de fora —
    também a que só encosta no que ficou (termina bem onde o corte começa)."""
    out = []
    for u in unidades:
        a, fica_a = remapear(plano, float(u["ini"]))
        b, fica_b = remapear(plano, float(u["fim"]))
        if not (fica_a and fica_b) and b - a < 0.02:
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
