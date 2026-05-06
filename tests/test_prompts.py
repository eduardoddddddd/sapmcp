from __future__ import annotations

import asyncio

from sapmcp import prompts
from sapmcp.server import mcp


PROMPT_CASES = [
    (prompts.basis_triage_sistema, {"sid": "DEV"}, ["DEV", "sap://system/info", "sap_ping", "T000"]),
    (prompts.inspeccionar_pedido_venta, {"vbeln": "0000123456"}, ["0000123456", "BAPI_SALESORDER_GETDETAILBOS", "BAPISDORDER_GETDETAILEDLIST", "read-only"]),
    (prompts.seguimiento_idoc, {"docnum": "0000000000123456"}, ["0000000000123456", "IDOC_RECORD_READ", "EDIDS", "DOCNUM", "STATUS", "CRETIM"]),
    (prompts.revisar_jobs_largos, {"top_n": 5, "dias": 3}, ["top 5", "últimos 3 días", "BAPI_XBP_JOB_SELECT", "SM36"]),
    (prompts.informe_sociedad, {"bukrs": "1000", "gjahr": "2026"}, ["1000", "2026", "BKPF", "BSAK", "BSAD", "512"]),
    (prompts.pre_change_check, {"funcname": "Z_POST_CHANGE", "descripcion": "Actualizar indicador"}, ["Z_POST_CHANGE", "Actualizar indicador", "confirm_dangerous=true"]),
]


def _text(messages):
    return "\n".join(message["content"] for message in messages)


def test_each_prompt_returns_three_structured_messages_with_placeholders():
    for func, kwargs, expected_fragments in PROMPT_CASES:
        messages = func(**kwargs)

        assert len(messages) == 3
        assert [message["role"] for message in messages] == ["user", "user", "assistant"]
        assert messages[0]["content"].startswith("SYSTEM: Actúa como consultor SAP Basis senior")
        assert "español" in messages[0]["content"]
        assert "no inventes datos SAP" in messages[0]["content"]
        assert "Plan de ejecución" in messages[2]["content"] or "Checklist obligatorio" in messages[2]["content"]

        rendered = _text(messages)
        for fragment in expected_fragments:
            assert fragment in rendered


def test_pre_change_check_contains_complete_human_checklist():
    messages = prompts.pre_change_check("bapi_salesorder_createfromdat2", "Crear pedido de venta de prueba")
    content = _text(messages)

    required_items = [
        "Sistema destino confirmado",
        "Mandante confirmado",
        "Hora planificada y zona horaria",
        "Ventana de cambio autorizada",
        "Ticket/orden de cambio asociado",
        "Plan de rollback",
        "Backup/snapshot/export previo",
        "responsable funcional/Basis aprobador",
        "Parámetros exactos de la RFC",
        "autorizo ejecutar BAPI_SALESORDER_CREATEFROMDAT2 con confirm_dangerous=true",
    ]
    for item in required_items:
        assert item in content
    assert "No llames `sap_rfc_call`" in content


def test_prompts_are_registered_and_renderable_by_fastmcp():
    registered = set(mcp._prompt_manager._prompts)
    assert set(prompts.PROMPT_FUNCTIONS).issubset(registered)

    rendered = asyncio.run(
        mcp._prompt_manager.render_prompt(
            "inspeccionar_pedido_venta",
            {"vbeln": "4711"},
        )
    )

    assert len(rendered) == 3
    assert [message.role for message in rendered] == ["user", "user", "assistant"]
    assert "4711" in rendered[1].content.text
    assert "BAPI_SALESORDER_GETDETAILBOS" in rendered[2].content.text
