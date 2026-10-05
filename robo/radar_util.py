"""Radar Artecon — utilidades do robô (download, texto, datas e hashes)."""
from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

VERSAO = "0.9.0"
AGENTE = f"ArteconRadar/{VERSAO} (+https://www.artecon.cnt.br; monitoramento de fontes oficiais)"

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
MESES.update({"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
              "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12})
RE_DATA_BR = re.compile(r"\b(\d{1,2})º?[/.](\d{1,2})[/.](\d{4})\b")
RE_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?)?")
RE_DATA_EXTENSO = re.compile(r"\b(\d{1,2})º?\s+(?:de\s+)?([a-zç]{3,9})\.?\s+(?:de\s+)?(\d{4})\b", re.I)
BRASILIA = timezone(timedelta(hours=-3))


def hoje_brasilia() -> date:
    """O dia em Brasília (o robô roda no GitHub, em UTC: às 21h de Brasília já é o dia seguinte lá)."""
    return datetime.now(BRASILIA).date()


class ErroDownload(Exception):
    def __init__(self, mensagem: str, http_status: int | None = None):
        super().__init__(mensagem)
        self.http_status = http_status


def sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def hash_conteudo(texto: str) -> str:
    """SHA-256 do texto com espaços normalizados (mudança de formatação não conta)."""
    return hashlib.sha256(normalizar_espacos(texto).encode("utf-8")).hexdigest()


def hash_titulo(titulo: str) -> str:
    """Hash tolerante a caixa, acentos e pontuação — usado para achar duplicatas."""
    base = re.sub(r"[^a-z0-9 ]+", " ", sem_acentos(titulo or "").lower())
    return hashlib.sha256(normalizar_espacos(base).encode("utf-8")).hexdigest()


def _data_valida(ano: int, mes: int, dia: int) -> date | None:
    if not 1990 <= ano <= date.today().year + 1:   # "Lei 9999-12-31" não é data
        return None
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def interpretar_data(texto: str | None) -> date | None:
    """Entende 30/09/2026, 2026-09-30T..., '8 de setembro de 2026' e datas RFC 822."""
    if not texto:
        return None
    texto = texto.strip()
    m = RE_DATA_ISO.search(texto)
    if m:
        d = _data_valida(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d and m.group(4) and m.group(7):
            # carimbo completo com fuso (ex.: 02:30Z): o dia que vale é o de Brasília
            fuso = "+00:00" if m.group(7) == "Z" else (m.group(7) if ":" in m.group(7) else m.group(7)[:3] + ":" + m.group(7)[3:])
            try:
                instante = datetime.fromisoformat(
                    f"{d.isoformat()}T{m.group(4)}:{m.group(5)}:{m.group(6) or '00'}{fuso}")
                return instante.astimezone(BRASILIA).date()
            except ValueError:
                pass
        if d:
            return d
    m = RE_DATA_BR.search(texto)
    if m:
        d = _data_valida(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            return d
    m = RE_DATA_EXTENSO.search(texto)
    if m:
        mes = MESES.get(sem_acentos(m.group(2)).lower())
        if mes:
            d = _data_valida(int(m.group(3)), mes, int(m.group(1)))
            if d:
                return d
    try:
        instante = parsedate_to_datetime(texto)
        return (instante.astimezone(BRASILIA) if instante.tzinfo else instante).date()
    except (TypeError, ValueError, IndexError):
        return None


RE_PARAMETRO_RASTREIO = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid)$", re.I)


def canonizar_url(url: str) -> str:
    """Mesmo endereço, mesma captura: tira âncora, barra final e parâmetros de rastreio.
    Os demais parâmetros ficam exatamente como vieram (sem recodificar)."""
    p = urlsplit(url.strip())
    partes = [x for x in p.query.split("&") if x and not RE_PARAMETRO_RASTREIO.match(x.split("=", 1)[0])]
    caminho = p.path.rstrip("/") if p.path not in ("", "/") else p.path
    return urlunsplit((p.scheme, p.netloc, caminho, "&".join(partes), ""))


def extrair_texto(html: str, seletores: str | None = None) -> str:
    """Texto principal da página, sem menus, scripts e rodapés.

    `seletores` é uma lista CSS separada por vírgula, em ordem de preferência;
    vale o primeiro que trouxer conteúdo de verdade. Sem acerto, usa o <body>.
    """
    sopa = BeautifulSoup(html or "", "lxml")
    # <form> não é removido: em sites ASP.NET a página inteira fica dentro de um formulário
    for lixo in sopa(["script", "style", "noscript", "nav", "header", "footer", "aside", "iframe", "svg"]):
        lixo.decompose()
    candidatos = [s.strip() for s in (seletores or "").split(",") if s.strip()]
    for seletor in candidatos + ["body"]:
        try:
            no = sopa.select_one(seletor)
        except Exception:
            no = None
        if no is None:
            continue
        texto = normalizar_espacos(no.get_text(" ", strip=True))
        if len(texto) >= 200 or seletor == "body":
            return texto
    return normalizar_espacos(sopa.get_text(" ", strip=True))


def baixar(url: str, sessao: requests.Session | None = None, tentativas: int = 3,
           espera: float = 2.0, limite: int = 40) -> tuple[int, str]:
    """Baixa a URL com novas tentativas. Devolve (status HTTP, conteúdo em texto).

    Levanta ErroDownload em falha — o chamador registra o erro; uma falha de
    download nunca é tratada como "não há novidades".
    """
    sessao = sessao or requests.Session()
    ultimo = None
    for n in range(1, tentativas + 1):
        try:
            r = sessao.get(url, timeout=limite, headers={
                "User-Agent": AGENTE,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9",
            })
            if r.status_code == 200:
                declarado = (r.headers.get("content-type") or "").lower()
                if "charset" not in declarado:
                    r.encoding = r.apparent_encoding or "utf-8"
                return r.status_code, r.text
            ultimo = ErroDownload(f"HTTP {r.status_code} em {url}", r.status_code)
            if r.status_code in (400, 401, 403, 404, 410):
                break
        except requests.RequestException as e:
            ultimo = ErroDownload(f"{type(e).__name__}: {e}")
        if n < tentativas:
            time.sleep(espera * n)
    raise ultimo or ErroDownload(f"falha ao baixar {url}")


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
