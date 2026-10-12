"""Radar Artecon — corretor de vídeo (v0.22.0): a fala transcrita contra o roteiro, só por código, sem IA (desenho 4.2).

Entra a fala para conferência (radar_videos.fala_roteiro: o que a tela tirou do roteiro com a mesma regra de extrair_fala, e o banco
conferiu que está no roteiro) e a transcrição (transcrever(): palavras {texto, inicio, fim, confianca}, em segundos na linha do tempo
de fala48k.wav, e frases {display, inicio, fim}). No F0 (Speech SDK) as palavras vêm na forma LÉXICA — minúsculas, sem pontuação,
números por extenso —, e a frase traz a forma de exibição (Display), com pontuação e algarismos.

  1. fichas (numeros.py): o roteiro e a transcrição viram a mesma sequência de fichas — palavra, termo do glossário e as de sentido
     (número, ano, data, mês, valor, por cento, ordinal), comparadas pelo valor: "trinta de outubro" casa com "30/10";
  2. alinhamento: difflib.SequenceMatcher sobre as chaves; cada trecho diferente é refinado — a mesma sequência de letras partida de
     outro jeito ("pró-labore"/"prolabore"), a VARIANTE do termo (Configurações: "ips" é IBS, só onde o roteiro tem IBS naquela
     posição) e a GRAFIA (palavra comum com semelhança ≥ 0,75, sem número nem termo). O resto fica "fora";
  3. legenda: a palavra alinhada sai na grafia e com a pontuação do roteiro ("e social" → "eSocial", "trinta de outubro" →
     "30/10"); a falada fora do roteiro sai na forma de exibição da frase (Display) ou, sem ela, com os números em algarismos, e
     entra em fora_do_roteiro; a do roteiro que não foi dita não entra (omitido). A legenda nunca tem palavra que não foi dita;
  4. divergência (regravar): qualquer diferença de número, data, mês, ano, valor, por cento, ordinal ou termo num trecho fora —
     troca, falta ou sobra. "A transcrição errou (vale o roteiro)" (ajustes.transcricao_errou, pelo número k da divergência) põe o
     roteiro na legenda daquele trecho; o áudio não muda;
  5. para os cortes (cortes.planejar): as palavras com `fim_frase` (da pontuação do roteiro) e `rot_de`/`rot_ate` (as fichas do
     roteiro a que cada uma se alinhou: o corte de "voz entre palavras" só é automático entre palavras SEGUIDAS do roteiro) e, em
     `remover`, as sugestões de repetição e de falso início (nunca automáticas). Os sons de hesitação ("hum", "ééé") ficam fora do
     alinhamento: quem os corta é cortes.py, pela regra dele;
  6. editor de legenda do administrador (ajustes.legenda: {"<u>:<n>": "texto novo"}, u = a 1ª unidade do bloco e n as palavras
     dele, da lista do relatório): troca palavra a palavra, com o mesmo número de palavras, cada uma igual à do roteiro naquele
     trecho ou parecida (≥ 0,6) com a que estava; nunca muda número, mês ou termo. O recusado vai para legenda.recusados.
Nada daqui vai para log: a fala, o roteiro e os nomes só saem no relatório (radar_videos.relatorio, que só admin e editor leem).
"""
from __future__ import annotations

import difflib
import math
import re

import cortes
import numeros

SEMELHANCA_GRAFIA = 0.75
SEMELHANCA_EDITOR = 0.6
JANELA = 4                             # fichas de cada lado na junção e na variante
REFINO_MAX = 2500                      # trecho diferente maior que isso (fichas × fichas) fica "fora" inteiro
PALAVRAS_MAX = 3000
FRASES_MAX = 500
TEXTO_MAX = 6000                       # radar_videos.fala_roteiro
LISTA_MAX = 100
EDICOES_MAX = 200
COBERTURA_MIN = 0.6                    # abaixo disso: aviso fala_diferente_do_roteiro
_MARCACAO = re.compile(r"[{}\\<>]")
_ASPAS = "\"'“”‘’«»"


# ------------------------------------------------------------------ a fala do roteiro
def _sem_aspas(c: str) -> str:
    c = c.strip()
    return c[1:-1].strip() if len(c) >= 2 and c[0] in _ASPAS and c[-1] in _ASPAS else c


def extrair_fala(roteiro: str) -> tuple[str, str]:
    """A fala para conferência (desenho 2.5, extrairFala; a tela usa a mesma regra): (fala, formato).
      * "kit": as linhas "… — Fala: X | Na tela: …" do roteiro do kit (roteiroDoKit, index.html): pega o X;
      * "tabela": a tabela do plano (Tempo | Fala | Texto na tela): a coluna "Fala" de cada linha, sem as aspas;
      * "texto": sem marcador, o texto inteiro (a tela avisa "Formato não reconhecido").
    "Na tela", "Tarja", "Gancho" e "Chamada final" nunca entram."""
    linhas = str(roteiro or "").replace("\r\n", "\n").split("\n")
    kit = [m.group(1) for m in (re.match(r"^.*?\s[—–]\s*Fala:\s*(.+?)(?:\s+\|\s*Na tela:.*)?$", l.strip()) for l in linhas) if m]
    if kit:
        return " ".join(" ".join(k.split()) for k in kit)[:TEXTO_MAX], "kit"
    falas, col = [], None
    for l in linhas:
        s = l.strip()
        if not s.startswith("|"):
            col = None
            continue
        cel = [c.strip() for c in s.strip("|").split("|")]
        if col is None:                                 # o cabeçalho da tabela: a coluna "Fala"
            nomes = [numeros.letras(c) for c in cel]
            col = nomes.index("fala") if "fala" in nomes else None
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cel if c):
            continue
        if col < len(cel) and _sem_aspas(cel[col]):
            falas.append(" ".join(_sem_aspas(cel[col]).split()))
    if falas:
        return " ".join(falas)[:TEXTO_MAX], "tabela"
    return " ".join(str(roteiro or "").split())[:TEXTO_MAX], "texto"


# ------------------------------------------------------------------ entrada (a transcrição é dado de fora: conferida)
def _seg(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and 0 <= v <= 3600 else None


def _transcricao(palavras) -> list[dict]:
    out = []
    for w in list(palavras or [])[:PALAVRAS_MAX]:
        if not isinstance(w, dict):
            continue
        texto = " ".join(str(w.get("texto") or "").split())[:40]
        ini, fim = _seg(w.get("inicio", w.get("ini"))), _seg(w.get("fim"))
        if not texto or ini is None or fim is None or fim < ini:
            continue
        c = _seg(w.get("confianca"))
        out.append({"texto": texto, "ini": ini, "fim": fim, "confianca": c if c is not None and c <= 1 else None})
    out.sort(key=lambda w: (w["ini"], w["fim"]))
    return out


def _inteiros(x) -> set[int]:
    return {int(k) for k in (x if isinstance(x, (list, tuple)) else [])[:EDICOES_MAX]
            if isinstance(k, int) and not isinstance(k, bool) and 0 <= k < 10000}


# ------------------------------------------------------------------ alinhamento das fichas
def _palavrais(xs: list[dict]) -> bool:
    return all(x["tipo"] in ("palavra", "termo") for x in xs)


def _casar(R: list[dict], i: int, i2: int, F: list[dict], j: int, j2: int, gl: dict) -> tuple[int, int, str] | None:
    """(a, b, tipo) se R[i:i+a] e F[j:j+b] são a mesma fala com outra grafia."""
    if i >= i2 or j >= j2:
        return None
    if R[i]["chave"] == F[j]["chave"]:
        return 1, 1, "igual"
    for soma in range(3, 2 * JANELA + 1):              # as mesmas letras, partidas de outro jeito
        for a in range(1, min(soma, JANELA + 1)):
            b = soma - a
            if b > JANELA or i + a > i2 or j + b > j2:
                continue
            ra, fb = R[i:i + a], F[j:j + b]
            if _palavrais(ra) and _palavrais(fb) and "".join(x["chave"] for x in ra) == "".join(x["chave"] for x in fb):
                return a, b, "juncao"
    if R[i]["tipo"] == "termo":                         # variante do termo, só onde o roteiro tem o termo
        var = gl["variantes"].get(R[i]["chave"]) or ()
        for b in range(1, JANELA + 1):
            fb = F[j:j + b]
            if j + b <= j2 and all(x["tipo"] == "palavra" for x in fb) and "".join(x["chave"] for x in fb) in var:
                return 1, b, "variante"
    if (R[i]["tipo"] == "palavra" and F[j]["tipo"] == "palavra"
            and difflib.SequenceMatcher(None, R[i]["chave"], F[j]["chave"]).ratio() >= SEMELHANCA_GRAFIA):
        return 1, 1, "grafia"
    return None


def _refinar(R, F, i1, i2, j1, j2, gl) -> list[dict]:
    if (i2 - i1) * (j2 - j1) > REFINO_MAX:
        return [{"r": list(range(i1, i2)), "f": list(range(j1, j2)), "tipo": "fora"}]
    out, i, j = [], i1, j1
    while i < i2 or j < j2:
        m = _casar(R, i, i2, F, j, j2, gl)
        if m:
            a, b, tipo = m
            out.append({"r": list(range(i, i + a)), "f": list(range(j, j + b)), "tipo": tipo})
            i, j = i + a, j + b
            continue
        prox = min(((di + dj, di, dj) for di in range(i2 - i + 1) for dj in range(j2 - j + 1)
                    if (di or dj) and _casar(R, i + di, i2, F, j + dj, j2, gl)), default=None)
        di, dj = (prox[1], prox[2]) if prox else (i2 - i, j2 - j)
        out.append({"r": list(range(i, i + di)), "f": list(range(j, j + dj)), "tipo": "fora"})
        i, j = i + di, j + dj
    return out


def _grupos(R: list[dict], F: list[dict], gl: dict) -> list[dict]:
    """O alinhamento, em ordem: [{r: fichas do roteiro, f: fichas faladas, tipo}], tipo igual, juncao, variante, grafia ou fora
    (os "fora" vizinhos juntos num trecho só)."""
    out = []
    sm = difflib.SequenceMatcher(None, [x["chave"] for x in R], [x["chave"] for x in F], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out += [{"r": [i1 + k], "f": [j1 + k], "tipo": "igual"} for k in range(i2 - i1)]
        else:
            out += _refinar(R, F, i1, i2, j1, j2, gl)
    junto = []
    for g in out:
        if g["tipo"] == "fora" and junto and junto[-1]["tipo"] == "fora":
            junto[-1]["r"] += g["r"]
            junto[-1]["f"] += g["f"]
        elif g["r"] or g["f"]:
            junto.append(g)
    return junto


# ------------------------------------------------------------------ textos
def _grafia(tokens: list[str], fs: list[dict]) -> str:
    """O pedaço do texto de onde vieram as fichas, sem a pontuação das pontas (para o relatório)."""
    if not fs:
        return ""
    return numeros._nucleo(" ".join(tokens[min(f["t0"] for f in fs):max(f["t1"] for f in fs) + 1]))


def _canon(f: dict) -> str:
    return numeros.exibir(f)


def _exibicao(frases, F: list[dict], gl: dict) -> list[tuple[set[int], str]]:
    """A forma de exibição (Display) de cada frase, alinhada às fichas faladas dela: [(fichas faladas, texto)]."""
    out = []
    for fr in list(frases or [])[:FRASES_MAX]:
        if not isinstance(fr, dict):
            continue
        disp = " ".join(str(fr.get("display") or "").split())[:2000]
        a, b = _seg(fr.get("inicio", fr.get("ini"))), _seg(fr.get("fim"))
        if not disp or a is None or b is None:
            continue
        js = [j for j, f in enumerate(F) if a - 0.05 <= (f["ini"] + f["fim"]) / 2 <= b + 0.05]
        if not js:
            continue
        dtok = disp.split()
        D = numeros.analisar(dtok, gl)
        for g in _grupos(D, [F[j] for j in js], gl):
            if g["tipo"] == "fora" or not g["r"] or not g["f"]:
                continue
            t0, t1 = min(D[i]["t0"] for i in g["r"]), max(D[i]["t1"] for i in g["r"])
            if {i for i, x in enumerate(D) if x["t0"] <= t1 and x["t1"] >= t0} <= set(g["r"]):
                out.append(({js[k] for k in g["f"]}, " ".join(dtok[t0:t1 + 1])))
    return out


def _unidades(grupos, R, F, rtok, ftok, exib, errou) -> list[dict]:
    """As unidades da legenda, na ordem da fala: [{texto, f (fichas faladas), perto (letras das palavras do roteiro ali)}]."""
    uns = []
    for g in grupos:
        alinhado = g["tipo"] != "fora"
        if alinhado or g.get("k") in errou:
            if g["r"]:                                  # sobra na transcrição com "vale o roteiro": não entra
                uns.append({"fonte": "roteiro", "r": list(g["r"]), "f": list(g["f"])})
        else:
            uns += [{"fonte": "fala", "r": [], "f": [j], "perto_r": list(g["r"])} for j in g["f"]]
    # as do roteiro que dividem um pedaço do texto ("PIS/Cofins", "R$ 50 mil") viram uma só
    juntas = []
    for u in uns:
        if u["fonte"] == "roteiro":
            u["t0"], u["t1"] = min(R[i]["t0"] for i in u["r"]), max(R[i]["t1"] for i in u["r"])
            p = juntas[-1] if juntas else None
            if p and p["fonte"] == "roteiro" and u["t0"] <= p["t1"]:
                p["r"] += u["r"]
                p["f"] += u["f"]
                p["t1"] = max(p["t1"], u["t1"])
                continue
        juntas.append(u)
    # as faladas que vêm do mesmo pedaço da transcrição ou da mesma palavra da exibição também
    grupo_exib = {j: k for k, (js, _) in enumerate(exib) for j in js}
    final = []
    for u in juntas:
        if u["fonte"] == "fala" and final and final[-1]["fonte"] == "fala":
            j, p = u["f"][0], final[-1]
            ult = p["f"][-1]
            if F[j]["t0"] <= F[ult]["t1"] or (grupo_exib.get(j) is not None and grupo_exib.get(j) == grupo_exib.get(ult)):
                p["f"].append(j)
                p["perto_r"] += u["perto_r"]
                continue
        final.append(u)
    for u in final:
        if u["fonte"] == "roteiro":
            # o pedaço inteiro do roteiro só se todas as fichas dele estão aqui (senão uma palavra não dita entraria)
            cobre = {i for i, x in enumerate(R) if x["t0"] <= u["t1"] and x["t1"] >= u["t0"]}
            u["texto"] = (" ".join(rtok[u["t0"]:u["t1"] + 1]) if cobre <= set(u["r"])
                          else " ".join(_canon(R[i]) for i in sorted(set(u["r"]))))
            u["perto"] = {numeros.letras(x) for x in rtok[u["t0"]:u["t1"] + 1]}
        else:
            js = u["f"]
            ks = {grupo_exib.get(j) for j in js}
            k = ks.pop() if len(ks) == 1 else None
            if k is not None and exib[k][0] == set(js):
                u["texto"] = exib[k][1]
            elif all(F[j]["tipo"] == "palavra" for j in js):
                u["texto"] = " ".join(ftok[F[js[0]]["t0"]:F[js[-1]]["t1"] + 1])
            else:
                u["texto"] = " ".join(_canon(F[j]) for j in js)
            perto = [R[i] for i in u.pop("perto_r")]
            u["perto"] = ({numeros.letras(x) for x in rtok[min(f["t0"] for f in perto):max(f["t1"] for f in perto) + 1]}
                          if perto else set())
    # a falta marcada "vale o roteiro" (sem fala ali) vai junto da unidade de antes (ou da seguinte)
    out = []
    for u in final:
        if not u["f"]:
            if out:
                out[-1]["texto"] += " " + u["texto"]
                out[-1]["perto"] |= u["perto"]
            else:
                u["pendente"] = True
                out.append(u)
            continue
        if out and out[-1].get("pendente"):
            pend = out.pop()
            u["texto"], u["perto"] = pend["texto"] + " " + u["texto"], u["perto"] | pend["perto"]
        u["ini"], u["fim"] = min(F[j]["ini"] for j in u["f"]), max(F[j]["fim"] for j in u["f"])
        out.append(u)
    return [u for u in out if not u.get("pendente")]


# ------------------------------------------------------------------ editor de legenda
def _edicao(unidades: list[dict], chave, novo, gl: dict) -> str | None:
    """Aplica o texto novo do bloco que começa na unidade u. A chave é "u:n" (n: as palavras do bloco, da lista do relatório) ou
    só "u" (as palavras novas, da unidade u em diante, têm de fechar unidades inteiras). Devolve o motivo da recusa (código fixo)
    ou None."""
    m = re.fullmatch(r"(\d{1,4})(?::(\d{1,3}))?", str(chave))
    if not m or not 0 <= int(m.group(1)) < len(unidades):
        return "bloco_inexistente"
    u = int(m.group(1))
    novo = " ".join(str(novo or "").split())
    if not novo or len(novo) > 120 or _MARCACAO.search(novo):
        return "texto_invalido"
    novas = novo.split()
    if m.group(2) is not None and len(novas) != int(m.group(2)):
        return "numero_de_palavras"
    velhas, k = [], u
    while k < len(unidades) and len(velhas) < len(novas):
        velhas += [(k, w) for w in unidades[k]["texto"].split()]
        k += 1
    if len(velhas) != len(novas):
        return "numero_de_palavras"
    if numeros.sentido(" ".join(w for _, w in velhas), gl) != numeros.sentido(novo, gl):
        return "numero_ou_termo"
    for (k, velha), nova in zip(velhas, novas):
        if numeros.sentido(velha, gl) != numeros.sentido(nova, gl):
            return "numero_ou_termo"
        lv, ln = numeros.letras(velha), numeros.letras(nova)
        if ln != lv and ln not in unidades[k]["perto"] and difflib.SequenceMatcher(None, lv, ln).ratio() < SEMELHANCA_EDITOR:
            return "palavra_diferente"
    resto = iter(novas)
    for k in sorted({k for k, _ in velhas}):
        unidades[k]["texto"] = " ".join(next(resto) for _ in unidades[k]["texto"].split())
    return None


# ------------------------------------------------------------------ o alinhamento
def _repeticao(g: dict, F: list[dict]) -> dict | None:
    """Trecho só da fala que repete as fichas logo antes ou logo depois ("devem devem"), ou começo de palavra que a seguinte
    completa ("pra- prazo"): sugestão de corte, nunca automática."""
    if g["r"] or not g["f"]:
        return None
    js, n = g["f"], len(g["f"])
    j0, j1 = js[0], js[-1]
    ks = [F[j]["chave"] for j in js]
    texto = lambda a, b: " ".join(_canon(F[j]) for j in range(a, b + 1))[:80]
    if ks == [F[j]["chave"] for j in range(j1 + 1, min(len(F), j1 + 1 + n))]:
        return {"ini": F[j0]["ini"], "fim": F[j1 + 1]["ini"], "tipo": "repeticao", "automatico": False, "texto": texto(j0, j1 + n)}
    if j0 >= n and ks == [F[j]["chave"] for j in range(j0 - n, j0)]:
        return {"ini": F[j0 - 1]["fim"], "fim": F[j1]["fim"], "tipo": "repeticao", "automatico": False, "texto": texto(j0 - n, j1)}
    if (n == 1 and F[j0]["tipo"] == "palavra" and j1 + 1 < len(F) and len(ks[0]) >= 2
            and F[j1 + 1]["chave"].startswith(ks[0]) and F[j1 + 1]["chave"] != ks[0]):
        return {"ini": F[j0]["ini"], "fim": F[j1 + 1]["ini"], "tipo": "falso_inicio", "automatico": False, "texto": texto(j0, j1 + 1)}
    return None


def _tipo_divergencia(xs: list[dict]) -> str:
    tipos = {x["tipo"] for x in xs}
    return "termo" if "termo" in tipos else "data" if tipos & {"data", "mes", "ano"} else "numero"


def alinhar(fala_roteiro: str, palavras: list[dict], frases: list[dict] = (), cfg: dict | None = None,
            ajustes: dict | None = None) -> dict:
    """Devolve:
      * palavras: [{texto, ini, fim, fim_frase, rot_de, rot_ate}] — todas as da transcrição, para cortes.planejar;
      * remover: as sugestões de repetição e falso início, para cortes.planejar;
      * legenda: [{u, texto, ini, fim}] na linha de fala48k.wav (cortes.no_video leva ao tempo do vídeo corrigido);
      * texto_final (a legenda inteira, que o banco confere: boletim pago, nomes, termos de publicidade), trocas, divergencias,
        fora_do_roteiro, omitido (com `t`, o instante na linha de fala48k.wav; relatorio.py leva ao vídeo corrigido),
        legenda_ajustes {editados, recusados}, cobertura (fração das fichas do roteiro que foram ditas) e avisos (códigos)."""
    cfg, ajustes = cfg or {}, ajustes or {}
    gl = numeros.glossario(cfg.get("glossario") or (), cfg.get("variantes") or {})
    ws = _transcricao(palavras)
    rtok = str(fala_roteiro or "")[:TEXTO_MAX].split()
    R = numeros.analisar(rtok, gl)
    do_roteiro = {f["chave"] for f in R}
    # os sons de hesitação ficam fora do alinhamento (se o próprio roteiro não os tem)
    fal = [k for k, w in enumerate(ws) if not (cortes.e_hesitacao(w["texto"]) and numeros.letras(w["texto"]) not in do_roteiro)]
    ftok = [ws[k]["texto"] for k in fal]
    F = numeros.analisar(ftok, gl)
    for f in F:
        f["ini"], f["fim"] = ws[fal[f["t0"]]]["ini"], ws[fal[f["t1"]]]["fim"]
        cs = [ws[fal[t]]["confianca"] for t in range(f["t0"], f["t1"] + 1) if ws[fal[t]]["confianca"] is not None]
        f["confianca"] = min(cs) if cs else None
    grupos = _grupos(R, F, gl)
    errou = _inteiros(ajustes.get("transcricao_errou"))

    divergencias, fora, omitido, remover, trocas = [], [], [], [], []
    ultimo_fim = 0.0
    for gi, g in enumerate(grupos):
        rs, fs = [R[i] for i in g["r"]], [F[j] for j in g["f"]]
        if g["tipo"] != "fora":
            if g["tipo"] in ("variante", "grafia") or any(x["tipo"] == "termo" for x in rs):
                de = " ".join(ftok[fs[0]["t0"]:fs[-1]["t1"] + 1])
                para = _grafia(rtok, rs)
                if re.sub(r"[^\w ]", "", de.lower()) != re.sub(r"[^\w ]", "", para.lower()):
                    trocas.append({"t": fs[0]["ini"], "de": de[:80], "para": para[:80],
                                   "motivo": g["tipo"] if g["tipo"] in ("variante", "grafia") else "termo"})
            ultimo_fim = fs[-1]["fim"]
            continue
        t = fs[0]["ini"] if fs else ultimo_fim
        rep = _repeticao(g, F)
        if rep:
            remover.append(rep)
        elif any(x["tipo"] in numeros.SENTIDO for x in rs + fs):
            g["k"] = len(divergencias)
            antes = grupos[gi - 1] if gi and grupos[gi - 1]["tipo"] != "fora" else None
            ctx = (_grafia(rtok, [R[i] for i in antes["r"]]) + " ") if antes else ""
            cs = [f["confianca"] for f in fs if f["confianca"] is not None]
            divergencias.append({"k": g["k"], "t": t, "falado": (ctx + " ".join(_canon(f) for f in fs)).strip()[:120],
                                 "roteiro": (ctx + _grafia(rtok, rs)).strip()[:120], "tipo": _tipo_divergencia(rs + fs),
                                 "regravar": True, "transcricao_errou": g["k"] in errou,
                                 **({"confianca": round(min(cs), 2)} if cs else {})})
        else:
            if fs:
                fora.append({"t": t, "texto": " ".join(_canon(f) for f in fs)[:120]})
            if rs:
                omitido.append({"t": t, "texto": _grafia(rtok, rs)[:120]})
        if fs:
            ultimo_fim = fs[-1]["fim"]

    unidades = _unidades(grupos, R, F, rtok, ftok, _exibicao(frases, F, gl), errou)
    edicoes = ajustes.get("legenda") if isinstance(ajustes.get("legenda"), dict) else {}
    recusados = []
    for chave, novo in list(edicoes.items())[:EDICOES_MAX]:
        motivo = _edicao(unidades, chave, novo, gl)
        if motivo:
            recusados.append({"bloco": str(chave)[:12], "motivo": motivo})

    # para os cortes: o roteiro a que cada palavra se alinhou e onde a frase fecha (pontuação da legenda, que vem do roteiro)
    rot: dict[int, list[tuple[int, int] | None]] = {}
    for g in grupos:
        for j in g["f"]:
            for t in range(F[j]["t0"], F[j]["t1"] + 1):
                rot.setdefault(fal[t], []).append((min(g["r"]), max(g["r"])) if g["tipo"] != "fora" else None)
    fecha = {fal[F[u["f"][-1]]["t1"]] for u in unidades if numeros.FECHA_FRASE.search(u["texto"])}
    saida = []
    for k, w in enumerate(ws):
        rs = rot.get(k) or [None]
        ok = None not in rs
        saida.append({"texto": w["texto"], "ini": w["ini"], "fim": w["fim"], "fim_frase": k in fecha,
                      "rot_de": min(a for a, _ in rs) if ok else None, "rot_ate": max(b for _, b in rs) if ok else None})

    alinhados = sum(len(g["r"]) for g in grupos if g["tipo"] != "fora")
    cobertura = alinhados / len(R) if R else 0.0
    avisos = []
    if not ws:
        avisos.append("transcricao_vazia")
    elif R and cobertura < COBERTURA_MIN:
        avisos.append("fala_diferente_do_roteiro")
    if recusados:
        avisos.append("legenda_recusada")
    if max(len(fora), len(omitido), len(trocas), len(remover)) > LISTA_MAX:
        avisos.append("lista_resumida")
    return {"palavras": saida, "remover": remover[:LISTA_MAX],
            "legenda": [{"u": k, "texto": u["texto"], "ini": u["ini"], "fim": u["fim"]} for k, u in enumerate(unidades)],
            "texto_final": " ".join(u["texto"] for u in unidades), "trocas": trocas[:LISTA_MAX], "divergencias": divergencias,
            "fora_do_roteiro": fora[:LISTA_MAX], "omitido": omitido[:LISTA_MAX],
            "legenda_ajustes": {"editados": min(len(edicoes), EDICOES_MAX) - len(recusados), "recusados": recusados},
            "cobertura": round(cobertura, 3), "avisos": avisos, "palavras_transcritas": len(ws)}
