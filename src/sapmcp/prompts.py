from __future__ import annotations

import json
from typing import Any

PromptPayload = list[dict[str, str]]

_SYSTEM_ROLE = (
    "SYSTEM: Actúa como consultor SAP Basis senior, conservador y orientado a operación. "
    "Prefiere lecturas idempotentes, Resources MCP cacheables y BAPIs/RFCs read-only. "
    "Trabaja en español, no inventes datos SAP y explica límites/riesgos antes de sugerir cambios. "
    "Nota MCP: este mensaje codifica la instrucción de sistema dentro de un mensaje user porque "
    "PromptMessage MCP solo admite roles user/assistant."
)


def _messages(task: str, skeleton: str) -> PromptPayload:
    return [
        {"role": "user", "content": _SYSTEM_ROLE},
        {"role": "user", "content": task.strip()},
        {"role": "assistant", "content": skeleton.strip()},
    ]


def basis_triage_sistema(sid: str | None = None) -> PromptPayload:
    """Playbook de triage Basis inicial de sistema SAP."""
    target = sid.strip().upper() if sid else "sistema SAP configurado en sapmcp"
    task = f"""
Realiza un triage Basis inicial para {target}. No ejecutes cambios; usa solo lecturas.
Secuencia obligatoria sugerida:
1. Leer resource `sap://system/info`.
2. Ejecutar tool `sap_ping`.
3. Ejecutar `sap_read_table` sobre `T000` para listar mandantes/clientes, por ejemplo campos `MANDT`, `MTEXT`, `CCCATEGORY`.
4. Resumir estado de conexión, mandante configurado, idioma configurado y fecha/hora del sistema si aparece en la respuesta; si no aparece, indica explícitamente que no está disponible con estas lecturas.
"""
    skeleton = """
Plan de ejecución:
- read_resource("sap://system/info")
- tool sap_ping({})
- tool sap_read_table({"table_name":"T000","fields":["MANDT","MTEXT","CCCATEGORY"],"rowcount":50})

Respuesta esperada al humano:
1. Estado de conexión RFC/STFC y ping.
2. Sistema objetivo solicitado y parámetros SAP sanitizados disponibles: host/cliente/usuario/idioma, sin credenciales.
3. Mandantes detectados en T000.
4. Idioma configurado y fecha/hora sistema si está disponible; si no, declarar limitación.
5. Riesgos o próximos checks read-only recomendados.
"""
    return _messages(task, skeleton)


def inspeccionar_pedido_venta(vbeln: str) -> PromptPayload:
    """Playbook read-only para inspeccionar un pedido de venta."""
    order = vbeln.strip().upper()
    task = f"""
Inspecciona el pedido de venta `{order}` de forma read-only. No requiere `confirm_dangerous`.
Guía:
1. Intenta describir `BAPI_SALESORDER_GETDETAILBOS` con `sap_describe_rfc` o resource `sap://function/BAPI_SALESORDER_GETDETAILBOS/interface`.
2. Si no existe/no está autorizado, prueba `BAPISDORDER_GETDETAILEDLIST`.
3. Llama la BAPI elegida con vista `I_BAPI_VIEW` adecuada para cabecera, posiciones, partners/particiones de entrega y status.
4. Devuelve cabecera, posiciones, particiones de entrega y estado global. Mantén la lectura como read-only y no uses `confirm_dangerous`.
"""
    skeleton = f"""
Plan de ejecución:
- read_resource("sap://function/BAPI_SALESORDER_GETDETAILBOS/interface") o tool sap_describe_rfc("BAPI_SALESORDER_GETDETAILBOS")
- fallback: sap_describe_rfc("BAPISDORDER_GETDETAILEDLIST")
- tool sap_rfc_call con function_name de la BAPI disponible, import_params que incluyan VBELN `{order}` y `I_BAPI_VIEW` para cabecera/posiciones/partners/status, output_tables según interfaz.

Respuesta esperada:
- Pedido: {order}
- Cabecera: sold-to/ship-to si existe, clase documento, organización ventas, fechas e importe si devuelto.
- Posiciones: material, descripción, cantidad, unidad, centro, status.
- Particiones de entrega/schedule lines: fecha, cantidad confirmada/pendiente.
- Estado: bloqueos, delivery/billing status, mensajes RETURN.
- Confirmar explícitamente: operación read-only, `confirm_dangerous` no usado.
"""
    return _messages(task, skeleton)


def seguimiento_idoc(docnum: str) -> PromptPayload:
    """Playbook read-only de seguimiento de IDoc."""
    doc = docnum.strip().upper()
    task = f"""
Haz seguimiento read-only del IDoc `{doc}`.
Guía:
1. Usar `IDOC_RECORD_READ` para leer control/data records del IDoc.
2. Leer `EDIDS` con `sap_read_table` filtrando `DOCNUM = '{doc}'` para estados/histórico.
3. Devolver campos mínimos: `DOCNUM`, `MESTYP`, `IDOCTP`, `STATUS`, `CRETIM` y mensajes de estado relevantes.
"""
    skeleton = f"""
Plan de ejecución:
- sap_describe_rfc("IDOC_RECORD_READ") si no conoces la interfaz.
- sap_rfc_call(function_name="IDOC_RECORD_READ", import_params={{"DOCUMENT_NUMBER":"{doc}"}}, output_tables=[...según interfaz...])
- sap_read_table(table_name="EDIDS", fields=["DOCNUM","STATUS","CREDAT","CRETIM","STAPA1","STAPA2","STAPA3","STAMQU"], where=["DOCNUM = '{doc}'"], rowcount=100)

Respuesta esperada:
- DOCNUM: {doc}
- MESTYP, IDOCTP desde control record si están disponibles.
- STATUS actual, fecha/hora CRETIM/CREDAT, histórico ordenado si se puede.
- Mensajes de error/estado y recomendación Basis/funcional de siguiente paso.
"""
    return _messages(task, skeleton)


def revisar_jobs_largos(top_n: int = 10, dias: int = 7) -> PromptPayload:
    """Playbook read-only para revisar jobs largos vía XBP."""
    task = f"""
Revisa jobs largos de los últimos {dias} días y devuelve el top {top_n} por duración descendente.
Guía:
1. Usar `BAPI_XBP_JOB_SELECT` con ventana temporal de {dias} días.
2. Ordenar por runtime/duración descendente y resumir top {top_n}.
3. Incluir `jobname`, `jobcount`, `status`, `runtime` y hora inicio/fin si está disponible.
4. Avisar que `BAPI_XBP_*` requiere permisos de external scheduler/XBP configurados en SM36/Basis.
"""
    skeleton = f"""
Plan de ejecución:
- read_resource("sap://function/BAPI_XBP_JOB_SELECT/interface") o sap_describe_rfc("BAPI_XBP_JOB_SELECT")
- sap_rfc_call(function_name="BAPI_XBP_JOB_SELECT", import_params={{ventana temporal últimos {dias} días según interfaz}}, output_tables=[tabla de jobs/RETURN según interfaz])
- Calcular duración si la BAPI devuelve inicio/fin; si ya devuelve runtime, normalizar.
- Ordenar desc y limitar a {top_n}.

Respuesta esperada:
- Aviso permisos: BAPI_XBP_* requiere external scheduler permission (SM36/XBP).
- Tabla top {top_n}: jobname, jobcount, status, runtime, start, end, usuario si disponible.
- Señalar jobs activos, cancelados o sin fin claro.
"""
    return _messages(task, skeleton)


def informe_sociedad(bukrs: str, gjahr: str) -> PromptPayload:
    """Playbook read-only de informe financiero básico por sociedad/ejercicio."""
    company = bukrs.strip().upper()
    year = gjahr.strip()
    task = f"""
Genera un informe read-only para sociedad `{company}` y ejercicio `{year}`.
Guía:
1. Leer `BKPF` con WHERE `BUKRS = '{company}'` y `GJAHR = '{year}'`.
2. Contar documentos por `BLART`.
3. Si están disponibles/autorizadas, obtener top 10 proveedores desde `BSAK` y top 10 clientes desde `BSAD`.
4. Recordar que `RFC_READ_TABLE` trunca `DATA-WA` a 512 caracteres; para producción o tablas anchas sugerir Z-RFC específico.
"""
    skeleton = f"""
Plan de ejecución:
- sap_read_table(table_name="BKPF", fields=["BUKRS","BELNR","GJAHR","BLART","BUDAT","CPUDT"], where=["BUKRS = '{company}'", "AND GJAHR = '{year}'"], rowcount=<límite seguro>)
- Agrupar por BLART y contar.
- Intentar BSAK: fields ["BUKRS","LIFNR","GJAHR","BELNR","DMBTR"] con el mismo filtro para top 10 proveedores si autorizado.
- Intentar BSAD: fields ["BUKRS","KUNNR","GJAHR","BELNR","DMBTR"] con el mismo filtro para top 10 clientes si autorizado.

Respuesta esperada:
- Sociedad/ejercicio: {company}/{year}
- Conteo por BLART.
- Top 10 proveedores y clientes si disponibles; si no, explicar limitación/autorización.
- Advertencia: RFC_READ_TABLE DATA-WA 512 chars; producción requiere Z-RFC/BAPI específico para exactitud y rendimiento.
"""
    return _messages(task, skeleton)


def pre_change_check(funcname: str, descripcion: str) -> PromptPayload:
    """Checklist obligatorio antes de cualquier RFC con confirm_dangerous=true."""
    function = funcname.strip().upper()
    desc = descripcion.strip()
    task = f"""
Antes de cualquier llamada potencialmente peligrosa con `confirm_dangerous=true`, prepara un pre-change check humano para `{function}`.
Descripción del cambio solicitado: {desc}
No ejecutes la RFC ni ninguna tool de cambio. El humano debe responder explícitamente al checklist antes de proceder.
"""
    skeleton = f"""
Checklist obligatorio antes de `confirm_dangerous=true` para {function}:
- Sistema destino confirmado (SID/entorno, sin credenciales en el chat).
- Mandante confirmado.
- Hora planificada y zona horaria.
- Ventana de cambio autorizada.
- Ticket/orden de cambio asociado.
- Descripción del cambio: {desc}
- Impacto esperado y usuarios/procesos afectados.
- Plan de rollback probado o, como mínimo, documentado.
- Backup/snapshot/export previo si aplica.
- Validación de autorizaciones y responsable funcional/Basis aprobador.
- Parámetros exactos de la RFC `{function}` que se ejecutarían.
- Confirmación explícita del humano: "autorizo ejecutar {function} con confirm_dangerous=true".

Respuesta esperada al humano:
Pide que complete cada punto. No llames `sap_rfc_call` con `confirm_dangerous=true` hasta recibir aprobación explícita y coherente.
"""
    return _messages(task, skeleton)


def health_check_response(health_json: dict[str, Any] | str) -> PromptPayload:
    """Prompt para redactar una respuesta humana a partir de sap_health_check."""
    if isinstance(health_json, str):
        payload = health_json.strip()
    else:
        payload = json.dumps(health_json, ensure_ascii=False, sort_keys=True, indent=2, default=str)
    task = f"""
Redacta en español un resumen operativo para humano a partir de este JSON de `sap_health_check`.
No inventes datos que no aparezcan. Respeta el verdict global y diferencia claramente checks `crit`, `warn` y `unknown`.
Si hay warn/crit, recomienda próximos checks read-only concretos usando las tools Basis disponibles; no recomiendes cambios ni `confirm_dangerous`.

JSON:
```json
{payload}
```
"""
    skeleton = """
Estructura de respuesta recomendada:
1. Semáforo global: OK / ÁMBAR / ROJO / DESCONOCIDO, con destino, SID, mandante, perfil y duración.
2. Hallazgos críticos primero: nombre del check, valor, umbral y por qué importa.
3. Avisos y desconocidos: separar problemas reales de falta de autorización/timeout/RFC no disponible.
4. Próximos checks read-only sugeridos:
   - dumps: sap_get_short_dumps con rango acotado y usuario si aplica.
   - jobs: sap_get_jobs(status="A", since_days=1).
   - updates: sap_get_update_requests(status="ERR").
   - locks: sap_get_locks(table=... o user=...).
   - workprocesses: sap_get_workprocesses(server=...).
5. Cierre: indicar explícitamente que no se ha ejecutado ninguna acción de cambio.
"""
    return _messages(task, skeleton)


PROMPT_FUNCTIONS: dict[str, Any] = {
    "basis_triage_sistema": basis_triage_sistema,
    "inspeccionar_pedido_venta": inspeccionar_pedido_venta,
    "seguimiento_idoc": seguimiento_idoc,
    "revisar_jobs_largos": revisar_jobs_largos,
    "informe_sociedad": informe_sociedad,
    "pre_change_check": pre_change_check,
    "health_check_response": health_check_response,
}
