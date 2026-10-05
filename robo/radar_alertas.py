"""Radar Artecon — avisos por e-mail: fonte com falha e link publicado fora do ar ou com texto diferente (v0.8.0).

Depois da coleta, abre um aviso (issue) no repositório do GitHub para cada fonte ativa que falhou
3 vezes seguidas. O GitHub manda e-mail ao dono do repositório quando um aviso é aberto, então não
é preciso serviço de e-mail. Um aviso por fonte: enquanto ele estiver aberto, nada novo é criado.
Quando a fonte volta a funcionar (ou é desligada na aba Fontes), o aviso é fechado com um comentário.

Também confere os links registrados em "Publicações no site": o que responder 404 ou 410 (página
que não existe mais) abre um aviso; quando o link volta a abrir, ou o registro é corrigido ou
excluído, o aviso fecha. Erro de rede ou do site (tempo esgotado, 5xx) não conta: pode ser passageiro.

Fonte ativa que ficou mais de 3 ciclos sem rodar ("atrasada") também abre aviso (v0.9.0). É o vigia da
rotina diária do boletim da ITC, que não passa pelo robô: se ela parar, o aviso chega em até 3 dias.

E confere, nas notícias do próprio site da Artecon, se a página ainda traz o texto que foi aprovado e
registrado (v0.8.0): se mais da metade das palavras sumiu, abre o aviso "texto do site diferente do
aprovado"; ele fecha quando o texto volta, ou o registro é corrigido ou excluído.

Uso (no workflow, depois da coleta):
    python radar_alertas.py
Variáveis: SUPABASE_URL, SUPABASE_SERVICE_KEY, GITHUB_TOKEN e GITHUB_REPOSITORY (o Actions preenche
as duas últimas). Sem elas, não faz nada. Nunca deixa a coleta vermelha: erros só vão para o log.
"""
from __future__ import annotations

import os
import sys

import requests

import radar_site
from radar_banco import Banco, ErroBanco
from radar_util import ErroDownload, baixar

PREFIXO = "Radar: fonte com falha — "
PREFIXO_LINK = "Radar: link publicado fora do ar — "
PREFIXO_TEXTO = "Radar: texto do site diferente do aprovado — "
PREFIXO_PARADA = "Radar: fonte parada — "
PREFIXOS_PADRAO = (PREFIXO, PREFIXO_LINK, PREFIXO_TEXTO, PREFIXO_PARADA)   # os avisos que o executar() abre e fecha
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


def corpo_parada(f: dict) -> str:
    sucesso = f.get("ultimo_sucesso_em") or "nunca"
    if (f.get("config") or {}).get("origem") == "email":
        oque = ("A rotina diária que lê o boletim no e-mail e grava no Radar não rodou nos últimos dias.\n\n"
                "O que fazer: peça ao Claude, na conversa do Radar, para conferir a rotina do boletim "
                "(Outlook e Supabase conectados, rotina ligada).")
    else:
        oque = ("O robô não conseguiu passar por ela no prazo esperado.\n\n"
                "O que fazer: GitHub → Actions → \"Radar — coleta\": confira se as coletas estão rodando.")
    return (f"A fonte **{f.get('nome') or f['slug']}** (`{f['slug']}`) está parada: último funcionamento em {sucesso}.\n\n"
            f"{oque}\n\nEste aviso fecha sozinho quando a fonte voltar a funcionar ou for desligada.")


def decidir_paradas(saude: list[dict], abertos: dict[str, int]) -> tuple[list[dict], list[tuple[int, str]]]:
    """Fonte ativa "atrasada" (passou de 3 ciclos sem funcionar): abre um aviso; fecha quando volta ou é desligada."""
    abrir, fechar = [], []
    por_slug = {f["slug"]: f for f in saude}
    for f in saude:
        if f.get("ativo") and f.get("saude") == "atrasada" and PREFIXO_PARADA + f["slug"] not in abertos:
            abrir.append(f)
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO_PARADA):
            continue
        f = por_slug.get(t[len(PREFIXO_PARADA):])
        if f is None:
            fechar.append((numero, "A fonte não existe mais no Radar."))
        elif not f.get("ativo"):
            fechar.append((numero, "A fonte foi desligada na aba Fontes."))
        elif f.get("saude") != "atrasada":
            fechar.append((numero, f"A fonte voltou a funcionar (último sucesso: {f.get('ultimo_sucesso_em')})."
                           if f.get("saude") != "falhando" else
                           "A fonte voltou a rodar, mas com falhas: o aviso de fonte com falha cuida dela daqui em diante."))
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


def titulo_texto(url: str) -> str:
    return (PREFIXO_TEXTO + url)[:250]


def corpo_texto(reg: dict) -> str:
    return (f"A notícia publicada no site para \"{reg.get('titulo') or '—'}\" não traz mais a maior parte do texto "
            f"que foi aprovado e registrado no Radar:\n\n{reg['url']}\n\n"
            "O que fazer: compare a página com o conteúdo aprovado (aba **Publicações**). Se a mudança no site foi "
            "de propósito, aprove o texto novo no Radar e registre de novo; se não foi, corrija a notícia no site."
            "\n\nEste aviso fecha sozinho quando o texto do site voltar a corresponder ao registrado, ou o registro "
            "for corrigido ou excluído.")


def conferir_textos(registros: list[dict], cfg: dict, pagina_de) -> tuple[dict[str, dict], set[str]]:
    """({link: registro mais novo} das notícias do site da Artecon cujo texto mudou, {links que não abriram}).
    `pagina_de(url)` devolve o HTML ou None (erro de rede: o link fica sem conferir, o aviso não muda)."""
    por_url: dict[str, dict] = {}
    for r in registros:
        url = r.get("url") or ""
        if url.startswith(("http://", "https://")) and radar_site.no_site(url, cfg) and (url not in por_url or r["id"] > por_url[url]["id"]):
            por_url[url] = r
    alterados, sem_conferir = {}, set()
    for url, reg in por_url.items():
        html = pagina_de(url)
        if html is None:
            sem_conferir.add(url)
        elif radar_site.texto_alterado(reg.get("corpo"), html):
            alterados[url] = reg
    return alterados, sem_conferir


def decidir_textos(registros: list[dict], alterados: dict[str, dict], abertos: dict[str, int], sem_conferir: set[str]):
    """Um aviso por link. Link que não pôde ser conferido (fora do ar, erro de rede) não abre nem fecha aviso."""
    abrir = [reg for url, reg in alterados.items() if titulo_texto(url) not in abertos]
    em_uso = {titulo_texto(r["url"]) for r in registros if r.get("url")}
    manter = {titulo_texto(url) for url in alterados} | {titulo_texto(url) for url in sem_conferir}
    fechar = []
    for t, numero in abertos.items():
        if not t.startswith(PREFIXO_TEXTO) or t in manter:
            continue
        fechar.append((numero, "O texto do site voltou a corresponder ao registrado." if t in em_uso
                       else "O link não está mais registrado no Radar (corrigido ou excluído)."))
    return abrir, fechar


def html_ou_nada(url: str) -> str | None:
    try:
        return baixar(url, tentativas=2)[1]
    except ErroDownload:
        return None


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

    def avisos_abertos(self, *prefixos: str) -> dict[str, int]:
        prefixos = prefixos or PREFIXOS_PADRAO
        abertos, pagina = {}, 1
        while True:
            lote = self._pedir("GET", "/issues", params={"state": "open", "per_page": 100, "page": pagina})
            for i in lote:
                if "pull_request" not in i and str(i.get("title", "")).startswith(prefixos):
                    abertos[i["title"]] = i["number"]
            if len(lote) < 100:
                return abertos
            pagina += 1

    def abrir_aviso(self, titulo_aviso: str, corpo: str) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo_aviso[:250], "body": corpo})["number"]

    def abrir(self, f: dict) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo(f["slug"]), "body": corpo_aviso(f)})["number"]

    def abrir_parada(self, f: dict) -> int:
        return self.abrir_aviso(PREFIXO_PARADA + f["slug"], corpo_parada(f))

    def abrir_link(self, reg: dict, status: int) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo_link(reg["url"]), "body": corpo_link(reg, status)})["number"]

    def abrir_texto(self, reg: dict) -> int:
        return self._pedir("POST", "/issues", json={"title": titulo_texto(reg["url"]), "body": corpo_texto(reg)})["number"]

    def fechar(self, numero: int, motivo: str) -> None:
        self._pedir("POST", f"/issues/{numero}/comments", json={"body": motivo})
        self._pedir("PATCH", f"/issues/{numero}", json={"state": "closed", "state_reason": "completed"})


def executar(banco: Banco, github: GitHub, status_de=status_http, pagina_de=html_ou_nada) -> list[str]:
    abertos = github.avisos_abertos()
    saude = banco.saude_fontes()
    abrir, fechar = decidir(saude, abertos)
    feito = []
    for f in abrir:
        feito.append(f"aviso #{github.abrir(f)} aberto: {f['slug']} ({f.get('falhas_consecutivas')} falhas seguidas)")
    abrir_p, fechar_p = decidir_paradas(saude, abertos)
    for f in abrir_p:
        feito.append(f"aviso #{github.abrir_parada(f)} aberto: {f['slug']} parada")
    fechar += fechar_p
    registros = banco.links_publicados()
    fora = conferir_links(registros, status_de)
    abrir_l, fechar_l = decidir_links(registros, fora, abertos)
    for reg, st in abrir_l:
        feito.append(f"aviso #{github.abrir_link(reg, st)} aberto: {reg['url']} responde {st}")
    fechar += fechar_l
    alterados, sem_conferir = conferir_textos([r for r in registros if r.get("url") not in fora],
                                              radar_site.configuracao(banco), pagina_de)
    abrir_t, fechar_t = decidir_textos(registros, alterados, abertos, sem_conferir | set(fora))
    for reg in abrir_t:
        feito.append(f"aviso #{github.abrir_texto(reg)} aberto: texto diferente em {reg['url']}")
    fechar += fechar_t
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
