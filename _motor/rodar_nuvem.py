# -*- coding: utf-8 -*-
"""Roda a coleta NA NUVEM (GitHub Actions) e grava direto na raiz do repo."""
import os, sys
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import gerar_dados
RAIZ = os.path.dirname(AQUI)                # raiz do repositorio (site)
gerar_dados.APP = RAIZ
gerar_dados.PASTA_DIAS = os.path.join(RAIZ, "dias")
gerar_dados.INDICE = os.path.join(RAIZ, "index.json")
raise SystemExit(gerar_dados.main())
