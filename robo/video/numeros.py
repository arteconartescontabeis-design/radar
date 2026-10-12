"""Radar Artecon — corretor de vídeo (v0.22.0): números, datas, valores e termos em pt-BR, do roteiro para palavras e de volta.

A transcrição do F0 (Speech SDK, forma léxica) vem em minúsculas, sem pontuação e com os números por extenso ("dois mil e vinte e
sete", "trinta de outubro", "cinquenta mil reais"); o roteiro vem na grafia da equipe ("2027", "30/10", "R$ 50.000,00"). Para
comparar, os dois lados passam pelo MESMO caminho:
  1. expandir(): cada pedaço (token) do texto vira palavras léxicas, presas ao pedaço de onde vieram: "2027" → "dois mil e vinte e
     sete"; "30/10" → "trinta de outubro"; "1º/01/2027" → "primeiro de janeiro de dois mil e vinte e sete"; "R$ 50 mil" e
     "R$ 50.000,00" → "cinquenta mil reais"; "10%" → "dez por cento"; "0,1%" → "zero vírgula um por cento"; "13º" → "décimo
     terceiro"; "março/2027" → "março de dois mil e vinte e sete"; "15.270/2025" → "quinze mil duzentos e setenta de dois mil e
     vinte e cinco". Palavra com hífen ou barra se separa ("pró-labore", "PIS/Cofins", "NR-1");
  2. fichas(): as palavras léxicas viram fichas, nesta ordem:
     * TERMO do glossário: até 6 palavras seguidas cujas letras, juntas, são as do termo ("e social", "é social" e "esocial" são
       eSocial; "dctf web" é DCTFWeb; "simples nacional"). Termo de uma palavra que também é palavra comum ("DAS" e "das") só vira
       termo escrito em maiúsculas — no roteiro e na forma de exibição; na forma léxica fica palavra, com a mesma chave;
     * de SENTIDO, pelo VALOR e não pela grafia: NUM, ANO (inteiro de 1900 a 2100), DATA (dia — ou "primeiro" — "de" mês ["de"
       ano]), MES (["de" ano]), VALOR (reais e centavos), PCT ("por cento") e ORD ("décimo terceiro", "segunda", "primeira").
       "trinta de outubro" e "30/10" dão a mesma ficha; "duas semanas" e "2 semanas" também;
     * "um" e "uma" só começam um número antes de mil, milhão, bilhão, real, reais, "por cento", "vírgula", centavos ou "de <mês>";
       fora disso são artigo e ficam palavra ("um salário mínimo", "a um mesmo sócio") — dos dois lados;
     * PALAVRA: as letras sem acento, como radar_pauta_normalizar.
     A chave de comparação é a das letras para PALAVRA e TERMO (assim o "DAS" do roteiro e o "das" da transcrição casam) e
     "#tipo:valor" para as de sentido;
  3. exibir(): o contrário — a ficha de sentido volta a algarismos ("15", "30/10", "R$ 50.000", "10%", "13º"), para o relatório e
     para a legenda fora dos trechos alinhados.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

# ------------------------------------------------------------------ por extenso (algarismo → palavra)
_UNID = ("zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze", "treze", "catorze",
         "quinze", "dezesseis", "dezessete", "dezoito", "dezenove")
_DEZ = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa")
_CENT = ("", "cento", "duzentos", "trezentos", "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos", "novecentos")
_ORD_U = ("", "primeiro", "segundo", "terceiro", "quarto", "quinto", "sexto", "sétimo", "oitavo", "nono")
_ORD_D = ("", "décimo", "vigésimo", "trigésimo", "quadragésimo", "quinquagésimo", "sexagésimo", "septuagésimo", "octogésimo",
          "nonagésimo")
_ORD_C = ("", "centésimo", "ducentésimo", "trecentésimo", "quadringentésimo", "quingentésimo", "sexcentésimo", "septingentésimo",
          "octingentésimo", "nongentésimo")
MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
_FEM = {"um": "uma", "dois": "duas"}

SENTIDO = frozenset({"num", "ano", "data", "mes", "valor", "pct", "ord", "termo"})
COMUNS = frozenset({"das", "dar", "mas"})   # termo de uma palavra que também é palavra do dia a dia: só em maiúsculas
FECHA_FRASE = re.compile(r"[.!?…;:][\"'”’»)\]]*$")


def letras(t: object) -> str:
    """Minúsculas, sem acento, só a-z e 0-9 (como radar_pauta_normalizar, sem os espaços)."""
    d = unicodedata.normalize("NFKD", str(t or "").lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in d if not unicodedata.combining(c)))


def _ate_999(n: int, fem: bool) -> str:
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    ps = [(_CENT[c][:-2] + "as") if fem and c > 1 else _CENT[c]] if c else []
    if r:
        d, u = (0, r) if r < 20 else divmod(r, 10)
        if d:
            ps.append(_DEZ[d])
        if u or not d:
            ps.append(_FEM.get(_UNID[u], _UNID[u]) if fem else _UNID[u])
    return " e ".join(ps)


def por_extenso(n: int, feminino: bool = False) -> str:
    """O inteiro por extenso, em pt-BR ("dois mil e vinte e sete", "mil setecentos e quarenta e um", "dois milhões e quinhentos
    mil"). feminino: "uma", "duas", "duzentas" (milhão e bilhão são sempre masculinos)."""
    n = int(n)
    if n < 0:
        return "menos " + por_extenso(-n, feminino)
    if n == 0:
        return "zero"
    if n >= 10 ** 12:
        return " ".join(_UNID[int(c)] for c in str(n))
    grupos = []                                         # (texto, valor do grupo)
    for base, um, varios in ((10 ** 9, "bilhão", "bilhões"), (10 ** 6, "milhão", "milhões")):
        q, n = divmod(n, base)
        if q:
            grupos.append((_ate_999(q, False) + " " + (um if q == 1 else varios), q))
    q, n = divmod(n, 1000)
    if q:
        grupos.append(("mil" if q == 1 else _ate_999(q, feminino) + " mil", q))
    if n:
        grupos.append((_ate_999(n, feminino), n))
    texto = grupos[0][0]
    for t, v in grupos[1:]:                             # "mil e vinte", "mil e cem", mas "mil setecentos e quarenta"
        texto += (" e " if v < 100 or v % 100 == 0 else " ") + t
    return texto


def ordinal(n: int, feminino: bool = False) -> str:
    """O ordinal por extenso (1 a 999): "décimo terceiro", "primeira", "vigésimo quinto"."""
    n = int(n)
    if not 1 <= n <= 999:
        return por_extenso(n, feminino)
    c, r = divmod(n, 100)
    d, u = divmod(r, 10)
    ps = [x for x in (_ORD_C[c], _ORD_D[d], _ORD_U[u]) if x]
    return " ".join(p[:-1] + "a" for p in ps) if feminino else " ".join(ps)


# ------------------------------------------------------------------ palavra → número (as tabelas são das letras sem acento)
_V_UNID = {**{letras(w): k for k, w in enumerate(_UNID)}, "uma": 1, "duas": 2, "quatorze": 14, "dezasseis": 16, "dezassete": 17,
           "dezanove": 19}
_V_DEZ = {**{w: k * 10 for k, w in enumerate(_DEZ) if w}, "cincoenta": 50}
_V_CENT = {**{w: k * 100 for k, w in enumerate(_CENT) if w}, **{w[:-2] + "as": k * 100 for k, w in enumerate(_CENT) if k > 1},
           "cem": 100}
_V_MULT = {"mil": 10 ** 3, "milhao": 10 ** 6, "milhoes": 10 ** 6, "bilhao": 10 ** 9, "bilhoes": 10 ** 9}
_V_ORD = {**{letras(w): (k, 1) for k, w in enumerate(_ORD_U) if w}, **{letras(w): (k * 10, 10) for k, w in enumerate(_ORD_D) if w},
          **{letras(w): (k * 100, 100) for k, w in enumerate(_ORD_C) if w}, "setuagesimo": (70, 10)}
_V_MES = {letras(m): k for k, m in enumerate(MESES, 1)}
_UM_ANTES = {"mil", "milhao", "milhoes", "bilhao", "bilhoes", "real", "reais", "virgula", "centavo", "centavos"}
_SEGUNDO_PREP = {"a", "o", "as", "os", "ele", "ela", "eles", "elas"}       # "segundo a lei": é preposição, não ordinal


def _classe(w: str) -> tuple[int, int] | None:
    """(valor, classe) de uma palavra de número: 3 centena, 2 dezena, 1 unidade (inclui 10 a 19), 0 "cem" (nada vem depois)."""
    if w in _V_CENT:
        return _V_CENT[w], 0 if w == "cem" else 3
    if w in _V_DEZ:
        return _V_DEZ[w], 2
    if w in _V_UNID:
        return _V_UNID[w], 1
    return None


def _um_comeca(ws: list[str], k: int) -> bool:
    """"um"/"uma" na posição k começa um número?"""
    prox = ws[k + 1] if k + 1 < len(ws) else ""
    return (prox in _UM_ANTES or ws[k + 1:k + 3] == ["por", "cento"]
            or (prox == "de" and k + 2 < len(ws) and ws[k + 2] in _V_MES))


def _inteiro(ws: list[str], i: int, um_livre: bool = False) -> tuple[int, int] | None:
    """Um inteiro por extenso a partir de ws[i]: (valor, posição depois dele). Dentro de um grupo (até 999) as partes vêm em ordem
    decrescente ligadas por "e" ("cento e vinte e sete"); depois de mil/milhão o grupo seguinte vem com ou sem "e". "vinte e um e
    trinta" são dois números; "quinze vinte" também."""
    total, grupo, classe, mult, j, lido = 0, 0, 9, 10 ** 12, i, False
    while j < len(ws):
        e = ws[j] == "e" and lido
        k = j + 1 if e else j
        if k >= len(ws):
            break
        w = ws[k]
        if w in _V_MULT:
            m = _V_MULT[w]
            if e or m >= mult or (not lido and w != "mil"):
                break
            total += (grupo or 1) * m
            grupo, classe, mult, lido, j = 0, 9, m, True, k + 1
            continue
        c = _classe(w)
        if c is None:
            break
        v, cl = c
        if grupo:                                       # dentro do grupo: menor e ligado por "e"
            if cl >= classe or classe == 0 or not e:
                break
        elif lido and mult == 10 ** 12:
            break                                       # um grupo já fechado ("quinze" "vinte")
        if not lido and w in ("um", "uma") and not um_livre and not _um_comeca(ws, k):
            break
        if not lido and w == "zero" and k + 1 < len(ws) and ws[k + 1] != "virgula":
            grupo, classe, lido, j = 0, 0, True, k + 1  # "zero" sozinho
            break
        grupo += v
        classe, lido, j = cl, True, k + 1
    if not lido:
        return None
    return total + grupo, j


def _numero(ws: list[str], i: int, um_livre: bool = False) -> tuple[Decimal, int] | None:
    """Inteiro com decimais ("zero vírgula um", "dois vírgula cinco") e "e meio" depois de mil/milhão."""
    r = _inteiro(ws, i, um_livre)
    if r is None:
        return None
    v, j = Decimal(r[0]), r[1]
    if j + 1 < len(ws) and ws[j] == "virgula":
        casas, k = "", j + 1
        while k < len(ws):
            if ws[k] == "zero":
                casas, k = casas + "0", k + 1
                continue
            d = _inteiro(ws, k, um_livre=True)
            if d is None or ws[k] == "e":
                break
            casas, k = casas + str(d[0]), d[1]
        if casas:
            v, j = Decimal(f"{r[0]}.{casas}"), k
    elif j + 1 < len(ws) and ws[j] == "e" and ws[j + 1] in ("meio", "meia") and ws[j - 1] in _V_MULT:
        v, j = v + Decimal(_V_MULT[ws[j - 1]]) / 2, j + 2
    return v, j


def _ord_base(w: str) -> str:
    for fim, troca in (("as", "o"), ("os", "o"), ("a", "o")):
        if w.endswith(fim) and len(w) > 3:
            return w[: -len(fim)] + troca
    return w


def _ordinal(ws: list[str], i: int) -> tuple[int, int, bool] | None:
    """"décimo terceiro" → (13, fim, masculino); "primeira" → (1, fim, feminino)."""
    total, ultima, j, fem = 0, 10 ** 4, i, None
    while j < len(ws):
        w = ws[j]
        x = _V_ORD.get(_ord_base(w))
        if x is None or x[1] >= ultima:
            break
        if w == "segundo" and j == i and j + 1 < len(ws) and ws[j + 1] in _SEGUNDO_PREP:
            break
        total, ultima, j = total + x[0], x[1], j + 1
        fem = w.endswith(("a", "as")) if fem is None else fem
    return (total, j, bool(fem)) if j > i else None


def _ano(ws: list[str], k: int) -> tuple[int, int] | None:
    """"de" + ano (1900 a 2100) a partir de ws[k] (k aponta o "de")."""
    if k + 1 < len(ws) and ws[k] == "de":
        r = _inteiro(ws, k + 1)
        if r and 1900 <= r[0] <= 2100:
            return r
    return None


def _sentido(ws: list[str], i: int) -> dict | None:
    """A ficha de sentido que começa em ws[i] (sem a chave): {tipo, valor, fim}."""
    o = _ordinal(ws, i)
    if o:
        v, j, fem = o
        if v == 1 and j + 1 < len(ws) and ws[j] == "de" and ws[j + 1] in _V_MES:     # "primeiro de janeiro"
            a = _ano(ws, j + 2)
            return {"tipo": "data", "valor": (1, _V_MES[ws[j + 1]], a[0] if a else None), "fim": a[1] if a else j + 2}
        return {"tipo": "ord", "valor": v, "fem": fem, "fim": j}
    n = _numero(ws, i)
    if n:
        v, j = n
        if ws[j:j + 2] == ["por", "cento"]:
            return {"tipo": "pct", "valor": v, "fim": j + 2}
        k = j + 1 if ws[j:j + 1] == ["de"] and ws[j + 1:j + 2] and ws[j + 1] in ("reais", "real") else j
        if k < len(ws) and ws[k] in ("reais", "real"):
            k += 1
            if k + 1 < len(ws) and ws[k] == "e":
                c = _inteiro(ws, k + 1, um_livre=True)
                if c and c[1] < len(ws) and ws[c[1]] in ("centavos", "centavo"):
                    v, k = v + Decimal(c[0]) / 100, c[1] + 1
            return {"tipo": "valor", "valor": v, "fim": k}
        if j < len(ws) and ws[j] in ("centavos", "centavo"):
            return {"tipo": "valor", "valor": v / 100, "fim": j + 1}
        inteiro = v == v.to_integral_value()
        if inteiro and 1 <= v <= 31 and j + 1 < len(ws) and ws[j] == "de" and ws[j + 1] in _V_MES:
            a = _ano(ws, j + 2)
            return {"tipo": "data", "valor": (int(v), _V_MES[ws[j + 1]], a[0] if a else None), "fim": a[1] if a else j + 2}
        if inteiro and 1900 <= v <= 2100:
            return {"tipo": "ano", "valor": int(v), "fim": j}
        return {"tipo": "num", "valor": v, "fim": j}
    if ws[i] in _V_MES:
        a = _ano(ws, i + 1)
        return {"tipo": "mes", "valor": (_V_MES[ws[i]], a[0] if a else None), "fim": a[1] if a else i + 1}
    return None


def _k(v: Decimal | int) -> str:
    return format(Decimal(v).normalize(), "f")


def _chave(f: dict) -> str:
    t, v = f["tipo"], f["valor"]
    if t == "data":
        return f"#data:{v[0]}/{v[1]}" + (f"/{v[2]}" if v[2] else "")
    if t == "mes":
        return f"#mes:{v[0]}" + (f"/{v[1]}" if v[1] else "")
    return f"#{t}:{_k(v)}"


# ------------------------------------------------------------------ texto → palavras léxicas
_N = r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?"
_NUM = re.compile(rf"^{_N}$")
_PCT = re.compile(rf"^({_N})\s?%$")
_MOEDA = re.compile(rf"^R\$({_N})?$")
_DATA = re.compile(r"^(\d{1,2})[º°ª]?/(\d{1,2})(?:/(\d{4}|\d{2}))?$")
_MES_ANO = re.compile(r"^([^\W\d_]+)/(\d{4})$")
_NORMA = re.compile(r"^(\d[\d.]*)/(\d{4})$")
_ORDINAL = re.compile(r"^(\d{1,3})\.?([º°ª])$")
_HORA = re.compile(r"^(\d{1,2})h(\d{2})?$", re.I)
_PEDACOS = re.compile(r"\d+|[^\W\d_]+")
_ABREV = {"art.": "artigo", "arts.": "artigos", "nº": "número", "n°": "número", "n.º": "número", "§": "parágrafo",
          "§§": "parágrafos", "&": "e", "+": "mais"}
_ESQ = "\"'“”‘’«»([{¿¡"
_DIR = ".,;:!?…\"'“”‘’«»)]}"


def _nucleo(token: str) -> str:
    return token.lstrip(_ESQ).rstrip(_DIR)


def _abrev(token: str) -> str | None:
    return _ABREV.get(re.sub(r"[,;:!?…\"'”’»)]+$", "", token.lstrip(_ESQ)).lower())


def _numero_palavras(s: str, fem: bool = False) -> list[str]:
    inteiro, _, dec = s.replace(".", "").partition(",")
    ws = por_extenso(int(inteiro), fem and not dec).split()
    if dec:
        zeros = len(dec) - len(dec.lstrip("0"))
        ws += ["vírgula"] + ["zero"] * zeros + (por_extenso(int(dec)).split() if dec.lstrip("0") else [])
    return ws


def _moeda(s: str, mult: str | None) -> tuple[list[str], list[str], list[str]]:
    """(palavras do número, palavras da moeda, palavras dos centavos) de "R$ <s> [mil|milhão…]"."""
    inteiro, _, dec = s.replace(".", "").partition(",")
    i, cents = int(inteiro or 0), int((dec + "00")[:2]) if dec else 0
    if mult:                                            # "R$ 50 mil", "R$ 1 milhão" ("um milhão de reais")
        return _numero_palavras(s) + [mult.lower()], (["de"] if letras(mult) != "mil" else []) + ["reais"], []
    num =por_extenso(i).split() if i or not cents else []
    moeda = ((["de"] if i and i % 10 ** 6 == 0 else []) + (["real"] if i == 1 else ["reais"])) if i or not cents else []
    cent = ((["e"] if i else []) + por_extenso(cents).split() + (["centavo"] if cents == 1 else ["centavos"])) if cents else []
    return num, moeda, cent


def expandir(tokens: list[str]) -> list[tuple[str, int, bool]]:
    """As palavras léxicas de uma sequência de pedaços (tokens, o texto partido nos espaços): [(palavra, índice do pedaço, tinha
    maiúscula)]. A pontuação das pontas do pedaço não vira palavra (ela fica na grafia, para a legenda)."""
    out: list[tuple[str, int, bool]] = []
    t, n = 0, len(tokens)
    while t < n:
        nuc = _nucleo(tokens[t])
        prox = _nucleo(tokens[t + 1]) if t + 1 < n else ""
        m = _MOEDA.match(nuc)
        if m and (m.group(1) or _NUM.match(prox)):     # "R$ 50.000,00", "R$50 mil", "R$ 1 milhão"
            tn = t if m.group(1) else t + 1
            s = m.group(1) or prox
            seg = _nucleo(tokens[tn + 1]) if tn + 1 < n else ""
            tm = tn + 1 if letras(seg) in _V_MULT else None
            num, moeda, cent = _moeda(s, seg if tm is not None else None)
            k = len(num) - (1 if tm is not None else 0)
            out += [(w, tn, False) for w in num[:k]] + [(w, tm, False) for w in num[k:]]
            out += [(w, t, False) for w in moeda] + [(w, tn if moeda or x + 1 < len(cent) else t, False) for x, w in enumerate(cent)]
            t = (tm if tm is not None else tn) + 1
            continue
        m = _PCT.match(nuc)
        if m or (_NUM.match(nuc) and prox == "%"):
            out += [(w, t, False) for w in _numero_palavras(m.group(1) if m else nuc)]
            tp = t if m else t + 1
            out += [("por", tp, False), ("cento", tp, False)]
            t = tp + 1
            continue
        a = _abrev(tokens[t])
        if a or nuc in ("R$", "%"):
            out += [(w, t, False) for w in (a or "").split()]
            t += 1
            continue
        out += [(w, t, mai) for w, mai in _palavras_do_pedaco(nuc)]
        t += 1
    return out


def _palavras_do_pedaco(nuc: str) -> list[tuple[str, bool]]:
    m = _DATA.match(nuc)
    if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
        d, mes, ano = int(m.group(1)), int(m.group(2)), m.group(3)
        ws = (["primeiro"] if d == 1 else por_extenso(d).split()) + ["de", MESES[mes - 1]]
        if ano:
            ws += ["de"] + por_extenso(int(ano) + (2000 if len(ano) == 2 else 0)).split()
        return [(w, False) for w in ws]
    m = _MES_ANO.match(nuc)
    if m and letras(m.group(1)) in _V_MES:
        return [(m.group(1).lower(), False), ("de", False)] + [(w, False) for w in por_extenso(int(m.group(2))).split()]
    m = _NORMA.match(nuc)
    if m and re.fullmatch(r"\d{1,3}(?:\.\d{3})*|\d+", m.group(1)):
        return [(w, False) for w in por_extenso(int(m.group(1).replace(".", ""))).split() + ["de"] + por_extenso(int(m.group(2))).split()]
    m = _ORDINAL.match(nuc)
    if m and int(m.group(1)) >= 1:
        return [(w, False) for w in ordinal(int(m.group(1)), m.group(2) == "ª").split()]
    m = _HORA.match(nuc)
    if m:
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        ws = por_extenso(h, True).split() + (["hora"] if h == 1 else ["horas"])
        if mi:
            ws += ["e"] + por_extenso(mi).split() + (["minuto"] if mi == 1 else ["minutos"])
        return [(w, False) for w in ws]
    if _NUM.match(nuc):
        return [(w, False) for w in _numero_palavras(nuc)]
    out = []
    for parte in re.split(r"[-/–—]", nuc):
        for p in _PEDACOS.findall(parte):
            if p.isdigit():
                out += [(w, False) for w in por_extenso(int(p)).split()]
            else:
                out.append((p.lower(), any(c.isupper() for c in p)))
    return out


# ------------------------------------------------------------------ fichas
def glossario(termos=(), variantes: dict | None = None) -> dict:
    """{"termos": {chave: grafia}, "variantes": {chave do termo: {chaves das variantes}}} a partir das Configurações
    (corretor_video.glossario e .variantes). A chave de um termo são as letras da forma léxica dele ("NR-1" → "nrum")."""
    gl = {"termos": {}, "variantes": {}}
    for g in list(termos or [])[:200]:
        g = " ".join(str(g or "").split())[:40]
        k = chave_texto(g)
        if len(k) >= 2:
            gl["termos"].setdefault(k, g)
    for g, vs in (variantes or {}).items() if isinstance(variantes, dict) else ():
        k = chave_texto(str(g))
        if k in gl["termos"] and isinstance(vs, (list, tuple)):
            gl["variantes"][k] = {c for c in (chave_texto(str(v)[:40]) for v in vs[:20]) if c and c != k}
    return gl


def chave_texto(texto: str) -> str:
    return "".join(letras(w) for w, _, _ in expandir(str(texto or "").split()))


def fichas(ps: list[tuple[str, int, bool]], gl: dict | None = None) -> list[dict]:
    """As fichas das palavras léxicas ps (de expandir): [{tipo, chave, valor, palavras, w0, w1, t0, t1}] (w: índices em ps; t: os
    pedaços do texto de onde vieram)."""
    termos = (gl or {}).get("termos") or {}
    ws = [letras(p) for p, _, _ in ps]
    out, i = [], 0
    while i < len(ps):
        if not ws[i]:
            i += 1
            continue
        f = None
        for tam in range(min(6, len(ps) - i), 0, -1):  # termo do glossário (o mais longo primeiro)
            k = "".join(ws[i:i + tam])
            if k in termos and (tam > 1 or k not in COMUNS or ps[i][2]):
                f = {"tipo": "termo", "valor": termos[k], "chave": k, "fim": i + tam}
                break
        if f is None:
            f = _sentido(ws, i)
            if f is not None:
                f["chave"] = _chave(f)
        if f is None:
            f = {"tipo": "palavra", "valor": ps[i][0], "chave": ws[i], "fim": i + 1}
        fim = f.pop("fim")
        f.update(palavras=[p for p, _, _ in ps[i:fim]], w0=i, w1=fim - 1,
                 t0=min(t for _, t, _ in ps[i:fim]), t1=max(t for _, t, _ in ps[i:fim]))
        out.append(f)
        i = fim
    return out


def analisar(tokens: list[str], gl: dict | None = None) -> list[dict]:
    """As fichas de um texto já partido em pedaços (o roteiro, a forma de exibição ou as palavras da transcrição), com `fim_frase`
    (a última ficha do pedaço que fecha a frase com . ! ? … ; :)."""
    fs = fichas(expandir(tokens), gl)
    for k, f in enumerate(fs):
        ultima = k + 1 == len(fs) or fs[k + 1]["t0"] > f["t1"]
        f["fim_frase"] = bool(ultima and FECHA_FRASE.search(tokens[f["t1"]]) and not _abrev(tokens[f["t1"]]))
    return fs


def sentido(texto: str, gl: dict | None = None) -> list[str]:
    """As chaves das fichas de sentido (números, datas, meses, valores, termos) de um texto, na ordem."""
    return [f["chave"] for f in analisar(str(texto or "").split(), gl) if f["tipo"] in SENTIDO]


# ------------------------------------------------------------------ número → algarismos
def _fmt(v: Decimal | int, casas: int | None = None) -> str:
    v = Decimal(v)
    if casas is not None:
        v = v.quantize(Decimal(1).scaleb(-casas))
    s = format(v.normalize() if casas is None else v, "f")
    inteiro, _, dec = s.partition(".")
    neg = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    inteiro = f"{int(inteiro):,}".replace(",", ".") if len(inteiro) > 3 else inteiro
    return ("-" if neg else "") + inteiro + ("," + dec if dec else "")


def exibir(f: dict) -> str:
    """A ficha em algarismos ("15", "30/10", "R$ 50.000", "10%", "13º", "março de 2027"); termo na grafia do glossário; palavra
    como veio."""
    t, v = f["tipo"], f["valor"]
    if t == "num":
        return _fmt(v)
    if t == "ano":
        return str(v)
    if t == "data":
        return f"{v[0]:02d}/{v[1]:02d}" + (f"/{v[2]}" if v[2] else "")
    if t == "mes":
        return MESES[v[0] - 1] + (f" de {v[1]}" if v[1] else "")
    if t == "valor":
        return "R$ " + _fmt(v, None if v == v.to_integral_value() else 2)
    if t == "pct":
        return _fmt(v) + "%"
    if t == "ord":
        return f"{v}{'ª' if f.get('fem') else 'º'}"
    return str(v)
