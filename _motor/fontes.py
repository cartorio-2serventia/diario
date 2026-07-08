# -*- coding: utf-8 -*-
"""
Coletor das publicacoes do Diario de Justica do Piaui.

Duas fontes:
  1) DJEN (comunica.pje.jus.br) - comunicacoes JUDICIAIS (API JSON).
  2) Diario Administrativo do TJPI (transparencia/diarios) - atos da
     Corregedoria sobre serventias extrajudiciais (busca HTML).

Para cada publicacao devolve um dicionario padronizado:
  {
    "id": str,            # identificador unico (para nao repetir envio)
    "fonte": str,         # "DJEN" ou "TJPI-ADM"
    "data": str,          # AAAA-MM-DD
    "orgao": str,         # vara/comarca/orgao
    "tipo": str,          # Edital, Intimacao, Diario NNNN...
    "link": str,          # link da publicacao / PDF
    "texto": str,         # texto completo (DJEN) ou trecho (TJPI)
    "recorte": str,       # trecho legivel ao redor do termo
    "regiao": [str],      # cidades da regiao citadas (pode ser vazio)
  }
"""
import re
import json
import html
import hashlib
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, timedelta

import config

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MonitorDiario/1.0",
      "Accept": "application/json, text/html"}


# ---------------------------------------------------------------- util
def normalizar(s: str) -> str:
    """minusculas, sem acento, espacos colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


NUCLEO_N = [normalizar(t) for t in config.TERMOS_NUCLEO]
REGIAO_N = [(t, normalizar(t)) for t in config.TERMOS_REGIAO]
COMARCA_N = normalizar(config.COMARCA_PRINCIPAL)
EXTRAJ_N = [normalizar(t) for t in getattr(config, "TERMOS_EXTRAJUDICIAL", [])]
IGNORADAS_N = [normalizar(t) for t in getattr(config, "FRASES_IGNORADAS", [])]
MEU_CARTORIO_N = [normalizar(t) for t in getattr(config, "MEU_CARTORIO", [])]


def cita_meu_cartorio(texto_norm: str) -> bool:
    return any(t in texto_norm for t in MEU_CARTORIO_N)


def restrito_a_regiao(tipo: str, texto_norm: str) -> bool:
    """True para EDITAIS (proclamas, citacao, leilao...) e INTERDICOES/
    curatelas — estes so entram quando forem da regiao do usuario."""
    if "edital" in normalizar(tipo):
        return True
    t = texto_norm.lstrip()
    if t.startswith("edital"):
        return True
    if "proclamas" in texto_norm:
        return True
    for w in ("interdicao", "interditado", "interditada", "curatela"):
        if w in texto_norm:
            return True
    return False

# Termos-ancora das BUSCAS (a API/portal devolvem resultado "solto"; o
# refino fino e' feito por avaliar() = contem 'serventia extrajudicial').
# "serventia" pega o singular; "extrajudicial" garante o plural tambem.
ANCORAS_BUSCA = ["serventia", "extrajudicial"]


# Na NUVEM (GitHub Actions) o portal do TJPI responde muito devagar e faz a
# coleta travar. Estas variaveis deixam o HTTP mais curto e permitem um
# ORCAMENTO DE TEMPO global (setado por quem chama) — passou do prazo, cada
# GET desiste na hora e a coleta segue com o que ja tem (merge preserva o resto).
LIMITE_TEMPO = None          # time.monotonic() maximo; None = sem limite


def _http_get(url: str, timeout: int = 25) -> bytes:
    """GET com poucas tentativas rapidas + respeito ao ORCAMENTO de tempo."""
    import time as _t
    if LIMITE_TEMPO is not None and _t.monotonic() > LIMITE_TEMPO:
        raise TimeoutError("orcamento de tempo esgotado")
    ultimo_erro = None
    for tentativa in range(2):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                dados = r.read()
            _t.sleep(0.3)
            return dados
        except Exception as e:
            ultimo_erro = e
            if LIMITE_TEMPO is not None and _t.monotonic() > LIMITE_TEMPO:
                break
            _t.sleep(3 * (tentativa + 1))
    raise ultimo_erro


def tem_nucleo(texto_norm: str) -> bool:
    return any(t in texto_norm for t in NUCLEO_N)


def regiao_citada(texto_norm: str):
    achados = []
    for original, n in REGIAO_N:
        if n in texto_norm:
            achados.append(original)
    return achados


def avaliar(texto_norm: str, orgao_norm: str):
    """Regra UNICA (11/06): entra se contiver 'serventia extrajudicial' ou
    'serventias extrajudiciais' (no texto, orgao ou destinatario)."""
    if tem_nucleo(texto_norm + " " + orgao_norm):
        return True, "serventia extrajudicial"
    return False, ""


# Termos que identificam um CARTORIO no nome do destinatario de uma
# comunicacao do DJEN (a comunicacao foi DIRIGIDA ao cartorio):
DEST_CARTORIO_N = [
    "serventia", "cartorio", "tabeli", "registrador",
    "registro de imoveis", "registro civil", "registro geral",
    "oficio de notas", "oficio unico", "unico oficio", "oficio de registro",
    "notas e protesto", "tabelionato",
]


def destinatario_cartorario(item_djen: dict):
    """Se a comunicacao do DJEN e' DIRIGIDA a um cartorio/serventia,
    devolve o nome do destinatario; senao, None. (Regra de 10/06: no DJEN
    so entram comunicacoes endereçadas a cartorios — processo judicial que
    apenas MENCIONA cartorio nao entra.)"""
    dests = item_djen.get("destinatarios") or []
    for d in dests:
        if not isinstance(d, dict):
            continue
        nome = normalizar(d.get("nome", ""))
        if nome and any(t in nome for t in DEST_CARTORIO_N):
            return (d.get("nome") or "").strip()
    return None


def fazer_recorte(texto: str, max_chars: int = 320) -> str:
    """Pega um trecho legivel ao redor da 1a ocorrencia de um termo nucleo."""
    if not texto:
        return ""
    tn = normalizar(texto)
    pos = -1
    for t in NUCLEO_N:
        p = tn.find(t)
        if p != -1 and (pos == -1 or p < pos):
            pos = p
    if pos == -1:
        trecho = texto.strip()[:max_chars]
    else:
        # mapear posicao aprox. no texto original (normalizar mantem ordem)
        ini = max(0, pos - max_chars // 2)
        fim = min(len(texto), pos + max_chars // 2)
        trecho = texto[ini:fim].strip()
        if ini > 0:
            trecho = "..." + trecho
        if fim < len(texto):
            trecho = trecho + "..."
    return re.sub(r"\s+", " ", trecho)


# ---------------------------------------------------------------- DJEN
def buscar_djen(dt_ini: date, dt_fim: date) -> list:
    """Comunicacoes do TJPI no DJEN DIRIGIDAS a cartorios/serventias
    (campo destinatarios). Processo judicial que so menciona cartorio
    NAO entra (decisao do usuario, 10/06)."""
    achados = {}
    for termo in ANCORAS_BUSCA:
        pagina = 1
        while True:
            url = ("https://comunicaapi.pje.jus.br/api/v1/comunicacao"
                   f"?siglaTribunal=TJPI"
                   f"&dataDisponibilizacaoInicio={dt_ini.isoformat()}"
                   f"&dataDisponibilizacaoFim={dt_fim.isoformat()}"
                   f"&texto={urllib.parse.quote(termo)}"
                   f"&itensPorPagina=100&pagina={pagina}")
            try:
                dados = json.loads(_http_get(url))
            except Exception as e:
                print(f"  [DJEN] erro pagina {pagina} termo '{termo}': {e}")
                break
            itens = dados.get("items") or []
            if not itens:
                break
            for it in itens:
                ident = f"DJEN-{it.get('id')}"
                if ident in achados:
                    continue
                texto = it.get("texto", "") or ""
                orgao = (it.get("nomeOrgao") or "").strip()
                tn = normalizar(texto)
                on = normalizar(orgao)
                incluir, motivo = avaliar(tn, on)
                if not incluir:
                    continue
                # se a comunicacao tambem foi dirigida a um cartorio, mostra
                dest = destinatario_cartorario(it) or ""
                achados[ident] = {
                    "id": ident,
                    "fonte": "DJEN",
                    "data": it.get("data_disponibilizacao", ""),
                    "orgao": orgao,
                    "tipo": it.get("tipoComunicacao") or "Comunicacao",
                    "link": it.get("link") or "",
                    "texto": texto,
                    "recorte": fazer_recorte(texto),
                    "regiao": regiao_citada(tn + " " + on + " " + normalizar(dest)),
                    "motivo": motivo,
                    "destinatario": dest,
                }
            if len(itens) < 100:
                break
            pagina += 1
            if pagina > 40:                     # trava de seguranca
                break
    return list(achados.values())


# ----------------------------------------------------------- TJPI ADM
_CARD_RE = re.compile(r'<div class="card">(.*?)</div>\s*</div>\s*</div>', re.S)
_PDF_RE = re.compile(r'href="(https://www\.tjpi\.jus\.br/diarioeletronico/public/[^"]+\.pdf)"')
_NUM_RE = re.compile(r'Di[^\d<]*?(\d{4,6})')
_DISP_RE = re.compile(r'Disponibilizado em\s*</strong>\s*([\d/]+)')
_TAG_RE = re.compile(r"<[^>]+>")


def _limpar_html(fragmento: str) -> str:
    txt = html.unescape(_TAG_RE.sub(" ", fragmento))
    return re.sub(r"\s+", " ", txt).strip()


def buscar_tjpi_adm(dt_ini: date, dt_fim: date) -> list:
    """Atos do Diario Administrativo do TJPI com os termos nucleo."""
    achados = {}
    # gt/lt sao exclusivos -> alargar 1 dia de cada lado para incluir a janela
    gt = (dt_ini - timedelta(days=1)).isoformat()
    lt = (dt_fim + timedelta(days=1)).isoformat()
    for termo in ANCORAS_BUSCA:
        pagina = 1
        while True:
            url = ("https://www.tjpi.jus.br/transparencia/diarios?"
                   + urllib.parse.urlencode({
                       "page": pagina,
                       "q[terms]": termo,
                       "q[disponibilization_gt]": gt,
                       "q[disponibilization_lt]": lt,
                   }))
            try:
                pagina_html = _http_get(url).decode("utf-8", "replace")
            except Exception as e:
                print(f"  [TJPI] erro pagina {pagina} termo '{termo}': {e}")
                break
            cards = _CARD_RE.findall(pagina_html)
            if not cards:
                break
            novos_na_pagina = 0
            for c in cards:
                mpdf = _PDF_RE.search(c)
                if not mpdf:
                    continue
                link = mpdf.group(1)
                # numero da edicao do nome do arquivo: djYYMMDD_NNNNN.pdf
                arq = link.rsplit("/", 1)[-1]
                mnum = re.search(r"dj(\d{6})_(\d+)\.pdf", arq)
                num_edicao = mnum.group(2) if mnum else arq
                data_iso = ""
                if mnum:
                    aa, mm, dd = mnum.group(1)[0:2], mnum.group(1)[2:4], mnum.group(1)[4:6]
                    data_iso = f"20{aa}-{mm}-{dd}"
                mdisp = _DISP_RE.search(c)
                if mdisp:
                    d, m, y = mdisp.group(1).split("/")
                    data_iso = f"{y}-{m}-{d}"
                # recorte = texto do card sem os botoes/metadados
                corpo = c
                corpo = re.sub(r'<h5 class="card-title">.*?</h5>', " ", corpo, flags=re.S)
                corpo = re.sub(r'Disponibilizado em.*?Publicado em\s*</strong>\s*[\d/]+', " ", corpo, flags=re.S)
                trecho = _limpar_html(corpo)
                tn = normalizar(trecho)
                # no diario administrativo o orgao e' sempre a Corregedoria;
                # entra se for serventia extrajudicial OU citar Bom Jesus.
                incluir, motivo = avaliar(tn, "")
                if not incluir:
                    continue
                h = hashlib.md5(trecho.encode("utf-8")).hexdigest()[:8]
                ident = f"TJPI-{num_edicao}-{h}"
                if ident in achados:
                    continue
                achados[ident] = {
                    "id": ident,
                    "fonte": "TJPI-ADM",
                    "data": data_iso,
                    "orgao": "Corregedoria/TJPI - Diario Administrativo",
                    "tipo": f"Diario {num_edicao}",
                    "link": link,
                    "texto": trecho,
                    "recorte": fazer_recorte(trecho) if len(trecho) > 360 else trecho,
                    "regiao": regiao_citada(tn),
                    "motivo": motivo,
                }
                novos_na_pagina += 1
            # proxima pagina?
            if f"page={pagina + 1}&" not in pagina_html.replace("&amp;", "&"):
                break
            pagina += 1
            if pagina > 20:
                break
    return list(achados.values())


# ---------------------------------------------------------------- API
def coletar(dias_janela: int = None) -> list:
    """Coleta das duas fontes na janela de dias e devolve lista unica."""
    dias = dias_janela if dias_janela is not None else config.DIAS_JANELA
    hoje = date.today()
    ini = hoje - timedelta(days=dias)
    print(f"Coletando de {ini} ate {hoje} ...")
    itens = []
    print("  -> DJEN (judicial)...")
    try:
        itens += buscar_djen(ini, hoje)
    except Exception as e:
        print(f"  [DJEN] FALHOU: {e}")
    print("  -> TJPI Administrativo (Corregedoria)...")
    try:
        itens += buscar_tjpi_adm(ini, hoje)
    except Exception as e:
        print(f"  [TJPI] FALHOU: {e}")
    # DEDUPLICAR por conteudo: o mesmo edital sai varias vezes no DJEN
    # (um registro por destinatario, cada um com id proprio)
    unicos, vistos = [], set()
    for it in itens:
        chave = hashlib.md5(normalizar(it.get("texto", ""))[:4000].encode()).hexdigest()
        if chave in vistos:
            continue
        vistos.add(chave)
        it["hash_conteudo"] = chave   # usado p/ nao reenviar o mesmo conteudo
        unicos.append(it)
    if len(unicos) < len(itens):
        print(f"  ({len(itens) - len(unicos)} duplicada(s) removida(s))")
    itens = unicos

    # ALERTA do cartorio do usuario + restricao de editais/interdicoes
    finais, cortados = [], 0
    for it in itens:
        tn = normalizar(" ".join([it.get("texto", ""), it.get("destinatario", ""),
                                  it.get("orgao", "")]))
        it["alerta"] = cita_meu_cartorio(tn)
        if it["alerta"]:
            finais.append(it)          # o cartorio dele SEMPRE entra
            continue
        if restrito_a_regiao(it.get("tipo", ""), tn) and not it.get("regiao"):
            cortados += 1              # edital/interdicao de fora da regiao
            continue
        finais.append(it)
    if cortados:
        print(f"  ({cortados} edital(is)/interdicao(oes) de fora da regiao descartado(s))")
    itens = finais
    # ordenar: regiao primeiro, depois data desc
    itens.sort(key=lambda x: (len(x["regiao"]) == 0, x.get("data", "")), reverse=False)
    itens.sort(key=lambda x: x.get("data", ""), reverse=True)
    itens.sort(key=lambda x: len(x["regiao"]) > 0, reverse=True)
    print(f"Total encontrado: {len(itens)} publicacao(oes).")
    return itens


if __name__ == "__main__":
    # teste rapido: python fontes.py
    res = coletar()
    for it in res:
        estrela = " *REGIAO:" + ",".join(it["regiao"]) if it["regiao"] else ""
        print(f"\n[{it['fonte']}] {it['data']} | {it['tipo']} | {it['orgao']}{estrela}")
        print(f"  {it['recorte'][:200]}")
        print(f"  {it['link']}")
