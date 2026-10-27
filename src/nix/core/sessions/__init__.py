"""Sessões dos agentes: eventos crus em `sessions.db`, nota legível no vault.

Este pacote usa só a biblioteca padrão nos módulos que o hook importa
(`sanitize`, `events`, `limits`, `store`, `hook_entry`). Importar Pydantic, a
CLI ou o índice aqui estoura o orçamento de 300 ms do hook.
"""
