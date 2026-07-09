# -*- coding: utf-8 -*-
"""
Gera os dados do APP de acompanhamento (PJE-TJPI) a partir do Diario de
Justica do PI. Classifica cada publicacao nos 4 botoes do app:

  - extrajudicial      : caderno administrativo / Corregedoria do foro
                         extrajudicial (serventias, tabelionatos, registros).
  - fermojupi          : tudo que envolve o FERMOJUPI.
  - judicial_serventia : judicial (DJEN) que cita "serventia(s)
                         extrajudicial(is)" - regiao (Bom Jesus, Currais,
                         Redencao do Gurgueia) vem primeiro na ordenacao.
  - judicial_bomjesus / judicial_currais / judicial_redencao : destaques por
                         cidade (subconjuntos do feed judicial_serventia).

Marca tambem: regiao (Bom Jesus, Currais, Redencao, Cristino Castro) e
alerta do cartorio do usuario (2a Serventia de Bom Jesus).

Saida (pasta app/):
  - app/dias/AAAA-MM-DD.json   : publicacoes daquele dia (texto completo)
  - app/index.json            : indice leve (datas + contagens por botao)

Roda todo dia. Cada execucao regrava os dias da janela e reconstroi o indice.
"""
import os
import re
import json
import html
import hashlib
import urllib.parse
from datetime import date, datetime, timedelta

import config
import fontes

norm = fontes.normalizar

PASTA = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(PASTA, "app")
PASTA_DIAS = os.path.join(APP, "dias")
INDICE = os.path.join(APP, "index.json")

DIAS_JANELA = 4         # quantos dias para tras coletar a cada execucao
DIAS_HISTORICO = 60     # quantos dias manter no app

DIAS_SEMANA = ["segunda-feira", "terca-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sabado", "domingo"]

SERV_N = [norm("serventia extrajudicial"), norm("serventias extrajudiciais")]
# Corregedoria DO FORO EXTRAJUDICIAL (CorExtra) — unica Corregedoria que entra
# sem o termo exato (pedido do usuario, 04/07). Corregedoria-Geral comum: fora.
COREXTRA_N = [norm(t) for t in [
    "corextra",                              # sigla PJPI/COREXTRA/ADMCOREXTRA
    "corregedoria do foro extrajudicial",
    "corregedoria geral do foro extrajudicial",
]]


def _tem(termos, txt):
    return any(t in txt for t in termos)


# ------------------------------------------------------------ classificacao
def classificar(fonte, orgao_n, texto_n):
    """Botoes em que a publicacao entra. REGRA (09/07/2026):
      - ABAS DE CIDADE (Bom Jesus/Currais/Redencao): QUALQUER fonte
        (extrajudicial OU judicial), desde que tenha o termo
        'serventia(s) extrajudicial(is)' + a cidade. NAO existe feed
        judicial geral — judicial so entra se for de uma dessas 3 cidades.
      - extrajudicial : SO administrativo (termo OU CorExtra).
      - fermojupi     : SO administrativo (FERMOJUPI + termo).
    (Chaves mantem 'judicial_' por compatibilidade do indice.)"""
    tem_serv = _tem(SERV_N, texto_n)
    cats = []
    # abas de cidade — admin OU judicial, com termo + cidade
    if tem_serv:
        if "bom jesus" in texto_n or "bom jesus" in orgao_n:
            cats.append("judicial_bomjesus")
        if "currais" in texto_n or "currais" in orgao_n:
            cats.append("judicial_currais")
        if "gurgueia" in texto_n or "gurgueia" in orgao_n:
            cats.append("judicial_redencao")
    # cadernos administrativos: SO do Diario Administrativo (nunca judicial)
    if fonte == "TJPI-ADM":
        if tem_serv or _tem(COREXTRA_N, texto_n):
            cats.append("extrajudicial")
        if tem_serv and "fermojupi" in texto_n:
            cats.append("fermojupi")
    return cats


def _registro(fonte, data_iso, orgao, tipo, link, texto, dest=""):
    tn = norm(texto)
    on = norm(orgao)
    dn = norm(dest)
    # o termo vale se estiver no texto OU no destinatario (serventia intimada)
    cats = classificar(fonte, on, tn + " " + dn)
    if not cats:
        return None
    reg = fontes.regiao_citada(tn + " " + on + " " + norm(dest))
    cart = fontes.cita_meu_cartorio(tn + " " + norm(dest) + " " + on)
    return {
        "id": hashlib.md5((fonte + data_iso + texto).encode("utf-8")).hexdigest()[:12],
        "fonte": fonte,
        "data": data_iso,
        "orgao": orgao,
        "tipo": tipo,
        "link": link,
        "texto": texto,
        "regiao": reg,
        "categorias": cats,
        "fermojupi": "fermojupi" in tn,
        "cartorio": bool(cart),
        "hash": hashlib.md5(tn[:4000].encode("utf-8")).hexdigest(),
    }


# ------------------------------------------------------------------- DJEN
def coletar_djen(dt_ini, dt_fim):
    achados = {}
    # Do DJEN so interessa o que for das 3 CIDADES (o judicial geral nao entra).
    # Buscamos por cidade; classificar() exige tambem o termo serventia extrajud.
    ancoras = ["Bom Jesus", "Currais", "Redenção do Gurguéia", "Redencao do Gurgueia"]
    for termo in ancoras:
        pagina = 1
        while True:
            url = ("https://comunicaapi.pje.jus.br/api/v1/comunicacao"
                   f"?siglaTribunal=TJPI"
                   f"&dataDisponibilizacaoInicio={dt_ini.isoformat()}"
                   f"&dataDisponibilizacaoFim={dt_fim.isoformat()}"
                   f"&texto={urllib.parse.quote(termo)}"
                   f"&itensPorPagina=100&pagina={pagina}")
            try:
                dados = json.loads(fontes._http_get(url))
            except Exception as e:
                print(f"  [DJEN] erro '{termo}' pag {pagina}: {e}")
                break
            itens = dados.get("items") or []
            if not itens:
                break
            for it in itens:
                ident = it.get("id")
                if ident in achados:
                    continue
                dest = fontes.destinatario_cartorario(it) or ""
                reg = _registro("DJEN", it.get("data_disponibilizacao", ""),
                                (it.get("nomeOrgao") or "").strip(),
                                it.get("tipoComunicacao") or "Comunicacao",
                                it.get("link") or "", it.get("texto", "") or "", dest)
                if reg:
                    reg["destinatario"] = dest
                    achados[ident] = reg
            if len(itens) < 100:
                break
            pagina += 1
            if pagina > 40:
                break
    return list(achados.values())


# ------------------------------------------------------------- TJPI ADM
# NOVO (30/06/2026): o TJPI redesenhou a pagina de diarios. A busca por termo
# (q[terms]) + range de datas parou de retornar resultados; agora a "Pesquisa
# Basica" exige DATA EXATA (q[disponibilization_eq]) e devolve a EDICAO do dia
# em PDF (.../diarioeletronico/public/dj######_#####.pdf). Como as publicacoes
# judiciais migraram para o DJEN (a partir de 16/03/2025), esse Diario passou a
# ser 100% administrativo / Corregedoria do Foro Extrajudicial -> tudo dele
# interessa ao botao "extrajudicial". Coletamos a edicao de cada dia da janela.
_EDICAO_RE = re.compile(
    r'href="(https?://[^"]+/diarioeletronico/public/dj(\d{2})(\d{2})(\d{2})_(\d+)\.pdf)"',
    re.I)


# identificador oficial do ato dentro do diario (p/ dedup entre buscas,
# ja que o portal devolve um RECORTE diferente para cada termo pesquisado)
_ATO_RE = re.compile(
    r"(publicacao|portaria|notificacao|aviso|edital|provimento|decisao|despacho|"
    r"instrucao normativa|termo)\s*(?:n[o.\s]*)?\s*([\d]{1,6}/\d{4}|\d{2,6})", re.I)


def coletar_tjpi(dt_ini, dt_fim):
    achados = {}

    # ---- 1) cartao da EDICAO do dia (link p/ o PDF completo) ----
    d = dt_ini
    while d <= dt_fim:
        url = ("https://www.tjpi.jus.br/transparencia/diarios?"
               + urllib.parse.urlencode({"q[disponibilization_eq]": d.isoformat()}))
        try:
            pag_html = fontes._http_get(url).decode("utf-8", "replace")
        except Exception as e:
            print(f"  [TJPI] erro {d}: {e}")
            d += timedelta(days=1)
            continue
        for m in _EDICAO_RE.finditer(pag_html):
            link, num = m.group(1), m.group(5)
            data_iso = f"20{m.group(2)}-{m.group(3)}-{m.group(4)}"
            if ("ed", num) in achados:
                continue
            texto = (
                f"Diario da Justica Estadual n. {num} - Caderno Administrativo / "
                "Corregedoria do Foro Extrajudicial (TJPI). Edicao completa em PDF: "
                "toque em Abrir para ler o inteiro teor oficial.")
            reg = _registro("TJPI-ADM", data_iso,
                            "Corregedoria/TJPI - Diario Administrativo",
                            f"Diario {num} (edicao completa)", link, texto)
            if reg:
                achados[("ed", num)] = reg
        d += timedelta(days=1)

    # ---- 2) ATOS individuais via busca por termo (recortes) ----
    # A busca q[terms]+periodo voltou a funcionar (auditoria 04/07). Cada termo
    # devolve o recorte ao redor da ocorrencia; dedup pelo numero oficial do ato.
    gt = (dt_ini - timedelta(days=1)).isoformat()
    lt = (dt_fim + timedelta(days=1)).isoformat()
    # so o que pode passar no filtro: termo (sing/plural) + CorExtra + fermojupi
    ancoras = ["serventia", "serventias", "extrajudicial", "extrajudiciais",
               "corextra", "fermojupi"]
    for termo in ancoras:
        pagina = 1
        while True:
            url = ("https://www.tjpi.jus.br/transparencia/diarios?"
                   + urllib.parse.urlencode({
                       "page": pagina, "q[terms]": termo,
                       "q[disponibilization_gt]": gt,
                       "q[disponibilization_lt]": lt}))
            try:
                pag_html = fontes._http_get(url).decode("utf-8", "replace")
            except Exception as e:
                print(f"  [TJPI] erro busca '{termo}' pag {pagina}: {e}")
                break
            cards = fontes._CARD_RE.findall(pag_html)
            if not cards:
                break
            for c in cards:
                mpdf = fontes._PDF_RE.search(c)
                if not mpdf:
                    continue
                link = mpdf.group(1)
                arq = link.rsplit("/", 1)[-1]
                mnum = re.search(r"dj(\d{2})(\d{2})(\d{2})_(\d+)\.pdf", arq)
                if not mnum:
                    continue
                data_iso = f"20{mnum.group(1)}-{mnum.group(2)}-{mnum.group(3)}"
                edicao = mnum.group(4)
                corpo = re.sub(r'<h5 class="card-title">.*?</h5>', " ", c, flags=re.S)
                corpo = re.sub(r'Disponibilizado em.*?Publicado em\s*</strong>\s*[\d/]+',
                               " ", corpo, flags=re.S)
                trecho = fontes._limpar_html(corpo)
                trecho = re.sub(r"^\s*\d{2}:\d{2}\s*", "", trecho)   # tira hora solta
                # identificador do ato p/ dedup (ou hash do recorte se nao achar)
                mato = _ATO_RE.search(fontes.normalizar(trecho))
                if mato:
                    chave = ("ato", edicao, mato.group(1), mato.group(2))
                    titulo = f"{mato.group(1).title()} n. {mato.group(2)} (Diario {edicao})"
                else:
                    chave = ("txt", hashlib.md5(fontes.normalizar(trecho)[:600].encode()).hexdigest())
                    titulo = f"Ato do Diario {edicao}"
                if chave in achados:
                    continue
                texto = trecho + "\n\n(Recorte da busca oficial; o inteiro teor esta no PDF da edicao - toque em Abrir.)"
                reg = _registro("TJPI-ADM", data_iso,
                                "Corregedoria/TJPI - Diario Administrativo",
                                titulo, link, texto)
                if reg:
                    achados[chave] = reg
            if f"page={pagina + 1}&" not in pag_html.replace("&amp;", "&"):
                break
            pagina += 1
            if pagina > 30:
                break
    return list(achados.values())


# ------------------------------------------------------------------- ordenacao
def _peso_regiao(reg):
    """Ordem do usuario: Bom Jesus, Currais, Redencao do Gurgueia,
    Cristino Castro, depois o resto."""
    if not reg.get("regiao"):
        return 9
    ordem = {"Bom Jesus": 0, "Currais": 1, "Redencao do Gurgueia": 2, "Cristino Castro": 3}
    return min(ordem.get(c, 8) for c in reg["regiao"])


def ordenar(pubs):
    # cartorio primeiro, depois regiao (Bom Jesus -> demais), depois orgao
    return sorted(pubs, key=lambda p: (not p["cartorio"], _peso_regiao(p),
                                       p.get("orgao", "")))


# ------------------------------------------------------------------- gravacao
def gravar_dia(data_iso, pubs):
    """Grava o dia MESCLANDO com o que ja existe (uniao por hash). Motivo: a API
    do DJEN as vezes responde 504/timeout e devolve coleta PARCIAL; sem o merge,
    uma coleta parcial sobrescreveria e apagaria publicacoes ja salvas. Com o
    merge, coleta parcial so ACRESCENTA - nunca perde o que ja estava no dia."""
    os.makedirs(PASTA_DIAS, exist_ok=True)
    caminho = os.path.join(PASTA_DIAS, data_iso + ".json")
    por_hash = {}
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                antigo = json.load(f)
            for p in antigo.get("publicacoes", []):
                por_hash[p.get("hash")] = p
        except Exception:
            pass
    for p in pubs:                       # coleta nova atualiza/insere por hash
        por_hash[p.get("hash")] = p
    pubs = ordenar(list(por_hash.values()))
    d = date.fromisoformat(data_iso)
    obj = {
        "data": data_iso,
        "dia_semana": DIAS_SEMANA[d.weekday()],
        "publicacoes": pubs,
    }
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def reconstruir_indice():
    """Le todos os dias salvos e monta o index.json leve."""
    os.makedirs(PASTA_DIAS, exist_ok=True)
    limite = (date.today() - timedelta(days=DIAS_HISTORICO)).isoformat()
    dias = []
    for arq in sorted(os.listdir(PASTA_DIAS), reverse=True):
        if not arq.endswith(".json"):
            continue
        data_iso = arq[:-5]
        if data_iso < limite:
            os.remove(os.path.join(PASTA_DIAS, arq))   # poda historico antigo
            continue
        try:
            with open(os.path.join(PASTA_DIAS, arq), encoding="utf-8") as f:
                obj = json.load(f)
        except Exception:
            continue
        cont = {"extrajudicial": 0, "fermojupi": 0, "judicial_bomjesus": 0,
                "judicial_currais": 0, "judicial_redencao": 0,
                "judicial_serventia": 0}
        cart = 0
        for p in obj["publicacoes"]:
            for c in p["categorias"]:
                if c in cont:
                    cont[c] += 1
            if p.get("cartorio"):
                cart += 1
        dias.append({"data": data_iso, "dia_semana": obj.get("dia_semana", ""),
                     "contagem": cont, "cartorio": cart})
    indice = {
        "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "cartorio_nome": "2a Serventia Extrajudicial de Tabelionato de Bom Jesus/PI",
        "dias": dias,
    }
    with open(INDICE, "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=1)
    return indice


def main():
    import time as _t
    # ORCAMENTO de tempo: na nuvem (TJPI lento) a coleta nunca pode travar.
    # Ajustavel por env MINUTOS_LIMITE (o workflow usa 6 min). 0 = sem limite.
    minutos = float(os.environ.get("MINUTOS_LIMITE", "0") or "0")
    fontes.LIMITE_TEMPO = (_t.monotonic() + minutos * 60) if minutos > 0 else None

    hoje = date.today()
    ini = hoje - timedelta(days=DIAS_JANELA)
    print(f"Coletando para o app de {ini} ate {hoje} "
          f"(limite {minutos or 'sem'} min) ...", flush=True)
    pubs = []
    print("  -> DJEN (so das 3 cidades, com o termo) ...", flush=True)
    try:
        pubs += coletar_djen(ini, hoje)
    except Exception as e:
        print(f"  [DJEN] interrompido: {e}", flush=True)
    print(f"  -> Diario Administrativo / Corregedoria ... ({len(pubs)} ate aqui)", flush=True)
    try:
        pubs += coletar_tjpi(ini, hoje)
    except Exception as e:
        print(f"  [TJPI] interrompido: {e}", flush=True)

    # dedup por conteudo
    vistos, unicos = set(), []
    for p in pubs:
        if p["hash"] in vistos:
            continue
        vistos.add(p["hash"])
        unicos.append(p)
    print(f"  {len(unicos)} publicacoes (apos dedup)")

    # agrupar por dia (somente dias da janela) e gravar
    por_dia = {}
    for p in unicos:
        if p.get("data"):
            por_dia.setdefault(p["data"], []).append(p)
    for data_iso, lista in por_dia.items():
        gravar_dia(data_iso, lista)
        print(f"    {data_iso}: {len(lista)} publicacao(oes)")

    indice = reconstruir_indice()
    print(f"Indice reconstruido: {len(indice['dias'])} dia(s) no app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
