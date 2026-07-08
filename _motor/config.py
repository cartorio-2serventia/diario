# -*- coding: utf-8 -*-
"""
Configuracoes do Monitor do Diario de Justica do Piaui.
Edite SOMENTE os valores entre aspas. Nao mexa no resto.
"""

# ===================================================================
# 1) PARA ONDE ENVIAR NO WHATSAPP
# ===================================================================
# Opcao A (recomendada): seu numero com DDI 55 + DDD, so digitos.
#   Exemplo Bom Jesus-PI (DDD 89):  "5589912345678"
# Opcao B: nome EXATO de um contato ou grupo salvo no seu WhatsApp.
#   Exemplo: "Avisos Cartorio"
#
# Se preencher so digitos, ele entende como numero de telefone.
# Se preencher com letras, ele procura o contato/grupo pelo nome.
WHATSAPP_DESTINO = "5561996795745"   # numero do Tabeliao (55 + 61 + ...)

# ===================================================================
# 2) O QUE VOCE QUER MONITORAR (regra de 10/06: SO mundo dos cartorios)
# ===================================================================
# Uma publicacao ENTRA se:
#  A) PI INTEIRO: falar do OFICIO/DELEGACAO em si (serventia, tabelionato,
#     notarial, registrador, delegatario, Corregedoria do extrajudicial...);
#  B) SUA REGIAO (Bom Jesus, Currais, Redencao, Cristino Castro): qualquer
#     coisa que envolva cartorio/registro (averbacao, registro civil,
#     registro de imoveis, protesto etc.).
# O judicial comum (intimacoes/despachos sem cartorio) NAO entra.
COMARCA_PRINCIPAL = "Bom Jesus"

# FILTRO PRINCIPAL: a publicacao SO entra se contiver "serventia
# extrajudicial" ou "serventias extrajudiciais" (acentos/maiusculas nao
# importam). Decisao do usuario (11/06): foco exclusivo neste termo.
TERMOS_NUCLEO = [
    "serventia extrajudicial",
    "serventias extrajudiciais",
]

# Frases de praxe que NAO contam para a regra estadual (A) — apareceriam
# em sentencas de gratuidade do estado todo (na SUA REGIAO continuam valendo):
FRASES_IGNORADAS = [
    "atos notariais e registrais",
    "atos notariais e de registro",
    "emolumentos notariais e registrais",
]

# (B) Contexto cartorario p/ SUA REGIAO (cidade da regiao + um destes):
TERMOS_EXTRAJUDICIAL = [
    "serventia", "cartorio", "tabeli", "registro de imoveis",
    "registro civil", "registrador", "corregedor", "corregedoria",
    "fermojupi", "notarial", "tabelionato", "extrajudicial",
    "averbacao", "protesto",
]

# Cidades da SUA REGIAO: ativam a regra (B) e ganham destaque ⭐.
TERMOS_REGIAO = [
    "Bom Jesus",
    "Currais",
    "Redencao do Gurgueia",
    "Cristino Castro",
]

# ===================================================================
# 2.1) SEU CARTORIO — ALERTA GERAL 🚨
# ===================================================================
# Se a publicacao citar qualquer uma destas formas, vem com ALERTA no topo.
# (acentos/maiusculas nao importam; "2ª" vale como "2a")
MEU_CARTORIO = [
    "2a serventia extrajudicial de tabelionato de bom jesus",
    "segunda serventia extrajudicial de tabelionato de bom jesus",
    "2a serventia extrajudicial de bom jesus",
    "2a serventia de tabelionato de bom jesus",
    "2a serventia de bom jesus",
    "2o tabelionato de bom jesus",
    "segundo tabelionato de bom jesus",
    "cartorio de notas e protestos de bom jesus",
]

# ===================================================================
# 2.2) TIPOS QUE SO ENTRAM SE FOREM DA SUA REGIAO
# ===================================================================
# Editais (proclamas, citacao, leilao etc.) e interdicoes do resto do
# estado NAO entram; da sua regiao, entram normalmente.
SO_REGIAO_SE_CONTIVER = [
    "edital",
    "interdicao", "interditado", "interditada", "curatela",
]

# ===================================================================
# 2.3) RESUMO COM INTELIGENCIA ARTIFICIAL
# ===================================================================
# True  = em vez do texto inteiro, voce recebe um RESUMO de cada
#         publicacao (do que se trata, partes, o que aconteceu),
#         gerado pelo Google Gemini (chave no arquivo .env).
# False = manda o texto COMPLETO (escolha do usuario em 11/06).
RESUMIR_COM_IA = False

# ===================================================================
# 3) HORARIOS / JANELA (normalmente nao precisa mexer)
# ===================================================================
# Quantos dias para tras cada verificacao olha. 4 cobre fim de semana
# e eventuais dias em que o PC ficou desligado (nao perde publicacao).
DIAS_JANELA = 4

# Avisar no WhatsApp "nada novo hoje" quando nao houver publicacao nova?
# True = manda um bom-dia curto avisando que rodou e nao achou nada
#        (assim voce confia que o robo esta vivo).
# False = em dia sem novidade, nao manda nada.
AVISAR_QUANDO_VAZIO = True

# Limite de seguranca: maximo de publicacoes por envio (evita travar o
# WhatsApp num dia atipico). O excedente vira um resumo no final.
MAX_ITENS_POR_ENVIO = 25
