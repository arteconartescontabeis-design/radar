"""Radar Artecon — avisos por e-mail: fonte com falha e link publicado fora do ar (v0.7.1).

Depois da coleta, abre um aviso (issue) no repositório do GitHub para cada fonte ativa que falhou
3 vezes seguidas. O GitHub manda e-mail ao dono do repositório quando um aviso é aberto, então não
é preciso serviço de e-mail. Um aviso por fonte: enquanto ele estiver aberto, nada novo é criado.
Quando a fonte volta a funcionar (ou é desligada na aba Fontes), o aviso é fechado com um comentário.

Também confere os links registrados em "Publicações no site": o que responder 404 ou 410 (página
que não existe mais) abre um aviso; quando o link volta a abrir, ou o registro é corrigido ou
excluído, o aviso fecha. Erro de rede ou do site (tempo esgotado, 5xx) não conta: pode ser passageiro.

Uso (no workflow, depois da coleta):
    python radar_alertas.py
Variáveis: SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_TOKEN e GITHUB_REPOSITORY (o Actions preenche
as duas últimas). Sem elas, não faz nada. Nunca deixa a coleta vermelha: erros só vão para o log.
"""
from __future__ import annotations

import os
import sys

import requests

from radar_banco import Banco, ErroBanco

PREFIXO = "Radar: fonte com falha — "
PREFIXO_LINK = "Radar: link publicado fora do ar — "
FORA_DO_AR = (404, 410)
FALHAS_PARA_AVISAR = 3
API = "https://api.github.com"


def titulo(slug: str) -> str:
    return PREFIXO + slug


def corpo_aviso(f: dict) -> str:
    sucesso = f.get("ultimo_sucesso_em") or "nunca"
    return (f"A fonte **{f.get('nome') or f['slug']}** (`{f['slug']}`) falhou nas últimas "
            f"**{f.get('falhas_consecutivas')}** coletas seguidas.\n\n"
            f"- Último erro: {str(f.get('ultimo_erro') or '—')[:500]}\n"
            f"- Último sucesso: {sucesso}\n\n"
            "O que fazer:\n"
            "1. No Radar, aba **Fontes**: veja a observação da fonte em \"Últimas execuções do robô\".\n"
            "2. GitHub → Actions → \"Radar — diagnóstico das fontes\" → Run workflow: o relatório mostra "
            "como a página está montada hoje.\n"
            "3. Se o site mudou, ajuste em Fontes → Configurar; se a fonte não serve mais, desmarque "
            "\"Fonte ativa\".\n\n"
            "Este aviso fecha sozinho quando a fonte voltar a funcionar ou for desligada.")


def decidir(saude: list[dict], abertos: dict[str, int]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Devolve (fontes para abrir aviso, [(número do aviso, motivo do fechamento)])."""
    abrir, fechar = [], []
    por_slug = {f["slug"]: f for f in saude}
    for f in saude:
        if f.get("ativo") and (f.get("falhas_consecutivas") or 0) >= FALHAS_PARA_AVISAR and titulo(f["slug"]) not in abertos:
            abrir.append(f)
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO):
            continue
        slug = t[len(PREFIXO):]
        f = por_slug.get(slug)
        if f is None:
            fechar.append((numero, "A fonte não existe mais no Radar."))
        elif not f.get("ativo"):
            fechar.append((numero, "A fonte foi desligada na aba Fontes."))
        elif (f.get("falhas_consecutivas") or 0) == 0:
            fechar.append((numero, f"A fonte voltou a funcionar (último sucesso: {f.get('ultimo_sucesso_em')})."))
    return abrir, fechar


def titulo_link(url: str) -> str:
    return (PREFIXO_LINK + url)[:250]


def corpo_link(reg: dict, status: int) -> str:
    return (f"O link registrado em **Publicações no site** para \"{reg.get('titulo') or '—'}\" "
            f"respondeu **HTTP {status}** (página não encontrada):\n\n{reg['url']}\n\n"
            "O que fazer: confira se a notícia foi retirada ou mudou de endereço no site da Artecon. "
            "No Radar, aba **Publicações**, use \"Corrigir link\" (ou exclua o registro, se a notícia saiu do ar "
            "de propósito).\n\nEste aviso fecha sozinho quando o link voltar a abrir ou o registro for corrigido.")


def conferir_links(registros: list[dict], status_de) -> dict[str, tuple[dict, int]]:
    """{link: (registro mais novo com ele, status HTTP)} só dos links fora do ar. Cada link é acessado uma vez;
    `status_de(url)` devolve o status ou None (erro de rede, que não conta)."""
    por_url: dict[str, dict] = {}
    for r in registros:
        url = r.get("url") or ""
        if url.startswith(("http://", "https://")) and (url not in por_url or r["id"] > por_url[url]["id"]):
            por_url[url] = r
    fora = {}
    for url, reg in por_url.items():
        st = status_de(url)
        if st in FORA_DO_AR:
            fora[url] = (reg, st)
    return fora


def decidir_links(registros: list[dict], fora: dict[str, tuple[dict, int]], abertos: dict[str, int]):
    """Um aviso por link. Devolve ([(registro, status) para abrir], [(número, motivo) para fechar])."""
    abrir = [(reg, st) for url, (reg, st) in fora.items() if titulo_link(url) not in abertos]
    em_uso = {titulo_link(r["url"]) for r in registros if r.get("url")}
    fora_titulos = {titulo_link(url) for url in fora}
    fechar = []
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO_LINK) or t in fora_titulos:
            continue
        fechar.append((numero, "O link voltou a abrir." if t in em_uso else "O link não está mais registrado no Radar (corrigido ou excluído)."))
    return abrir, fechar


def status_http(url: str, sessao: requests.Session | None = None) -> int | None:
    try:
        r = (sessao or requests).get(url, timeout=20, allow_redirects=True, stream=True,
                                     headers={"User-Agent": "Mozilla/5.0 (RadarArtecon; conferencia de links)"})
        r.close()
        return r.status_code
    except requests.RequestException:
        return None


class GitHub:
    def __init__(self, repositorio: str, token: str, sessao: requests.Session | None = None):
        self.base = f"{API}/repos/{repositorio}"
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                    "X-GitHub-Api-Version": "2022-11-28"})

    def _pedir(self, metodo: str, caminho: str, **kw):
        r = self.sessao.request(metodo, self.base + caminho, timeout=30, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"GitHub {metodo} {caminho}: HTTP {r.status_code} — {r.text[:300]}")
        return r.json() if r.text else None

    def avisos_abertos(self) -> dict[str, int]:
        abertos, pagina = {}, 1
        while True:
            lote = self._pedir("GET", "/issues", params={"state": "open", "per_page": 100, "page": pagina})
            for i in lote:
                if "pull_request" not in i and str(i.get("title", "")).startswith((PREFIXO, PREFIXO_LINK)):
                    abertos[i["title"]] = i["number"]
            if len(lote) < 100:
                return abertos
            pagina += 1

    def abrir(self, f: dict) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo(f["slug"]), "body": corpo_aviso(f)})["number"]

    def abrir_link(self, reg: dict, status: int) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo_link(reg["url"]), "body": corpo_link(reg, status)})["number"]

    def fechar(self, numero: int, motivo: str) -> None:
        self._pedir("POST", f"/issues/{numero}/comments", json={"body": motivo})
        self._pedir("PATCH", f"/issues/{numero}", json={"state": "closed", "state_reason": "completed"})


def executar(banco: Banco, github: GitHub, status_de=status_http) -> list[str]:
    abertos = github.avisos_abertos()
    abrir, fechar = decidir(banco.saude_fontes(), abertos)
    feito = []
    for f in abrir:
        feito.append(f"aviso #{github.abrir(f)} aberto: {f['slug']} ({f.get('falhas_consecutivas')} falhas seguidas)")
    registros = banco.links_publicados()
    abrir_l, fechar_l = decidir_links(registros, conferir_links(registros, status_de), abertos)
    for reg, st in abrir_l:
        feito.append(f"aviso #{github.abrir_link(reg, st)} aberto: {reg['url']} responde {st}")
    fechar += fechar_l
    for numero, motivo in fechar:
        github.fechar(numero, motivo)
        feito.append(f"aviso #{numero} fechado: {motivo}")
    return feito


def main() -> int:
    url, chave = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (url and chave and token and repo):
        print("Avisos de fonte com falha: sem as variáveis necessárias; nada a fazer.")
        return 0
    try:
        feito = executar(Banco(url, chave), GitHub(repo, token))
    except (ErroBanco, RuntimeError, requests.RequestException) as e:
        print(f"! avisos de fonte com falha não foram atualizados: {e}", file=sys.stderr)
        return 0
    print("Avisos de fonte com falha: " + ("; ".join(feito) if feito else "nada a abrir nem fechar."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
