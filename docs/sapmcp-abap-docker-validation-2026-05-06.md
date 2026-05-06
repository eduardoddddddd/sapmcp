# Informe de validación sapmcp contra ABAP Docker

**Fecha:** 2026-05-06  
**Proyecto:** `/Users/eduardoariasbravo/Developer/sapmcp`  
**Servidor probado:** ABAP Docker A4H en VM `abap-docker-host`  
**Objetivo:** validar el MCP `sapmcp` contra un SAP real/controlado antes de usarlo en un entorno DEV.

> Nota de seguridad: este informe no contiene contraseñas ni secretos. Las credenciales temporales usadas para la prueba fueron eliminadas al finalizar.

---

## 1. Resumen ejecutivo

La validación fue **satisfactoria**.

Se probaron las capas principales implementadas en `sapmcp`:

- Bridge RFC basado en `ctypes` y SAP NetWeaver RFC SDK.
- Tools MCP.
- Resources MCP cacheables.
- Prompts MCP operativos.
- SafetyPolicy.
- Audit log JSONL.
- Configuración opcional SNC.
- Snapshot offline del catálogo SAP.
- Suite de tests local.

### Resultado global

| Entorno | Resultado |
|---|---:|
| Tests locales `pytest -q` | ✅ `20 passed` |
| Validación real contra SAP ABAP Docker con `SAP*` / mandante `000` | ✅ OK |
| Limpieza de credenciales temporales | ✅ OK |

---

## 2. Entorno de conexión probado

| Parámetro | Valor |
|---|---|
| VM | `abap-docker-host` |
| Zona GCP | `europe-west1-b` |
| Host SAP visto desde la VM | `127.0.0.1` |
| SYSNR | `00` |
| Mandante | `000` |
| Usuario | `SAP*` |
| Idioma | `EN` |
| Sistema SAP respondido | `A4H` |
| SAP NW RFC SDK | `7.77.500` |
| Librerías RFC en VM | `/tmp/sapnwrfc/lib` |
| Modo seguridad | `SAPMCP_READ_ONLY=true` |
| Timeout RFC | `30s` en prueba remota |

### Allowlist usada

```text
RFC_PING
STFC_CONNECTION
RFC_READ_TABLE
RFC_GET_FUNCTION_INTERFACE
DDIF_FIELDINFO_GET
```

---

## 3. Observaciones de login/licencia

Durante las pruebas previas se confirmó:

| Usuario / mandante | Resultado |
|---|---|
| `DEVELOPER` / `001` | ❌ `LOGON_FAILURE` por license check |
| `DDIC` / `000` | ❌ `LOGON_FAILURE` por license check |
| `SAP*` / `000` | ✅ Login RFC funcional |

Error observado en los usuarios afectados por licencia:

```text
LOGON_FAILURE | Logon not possible (error in license check)
```

Con `SAP*` en mandante `000` sí funcionaron las RFCs básicas necesarias para validar `sapmcp`.

---

## 4. Resultado de tests locales

Comando ejecutado en local:

```bash
cd /Users/eduardoariasbravo/Developer/sapmcp
. .venv/bin/activate
pytest -q
```

Resultado:

```text
....................                                                     [100%]
20 passed in 0.21s
```

---

## 5. Pruebas realizadas contra SAP real

### 5.1 Configuración y SafetyPolicy

| Check | Resultado |
|---|---:|
| `sap_config_status` sin secretos | ✅ OK |
| `sap_safety_check("RFC_PING")` | ✅ read-only conocido |
| `sap_safety_check("BAPI_CREATE")` | ✅ detectado como dangerous |
| Orden de errores `assert_allowed` | ✅ dangerous → allowlist → read_only |

Mensajes de bloqueo verificados:

```text
RFC BAPI_CREATE blocked: reason=dangerous requires=SAPMCP_ALLOW_DANGEROUS:true,confirm_dangerous:true
RFC STFC_CONNECTION blocked: reason=not_in_allowlist env=SAPMCP_ALLOWED_RFC
RFC Z_CUSTOM_READ blocked: reason=read_only_unknown_read env=SAPMCP_READ_ONLY:true
```

---

### 5.2 Bridge RFC de bajo nivel

Se abrió conexión RFC real mediante `SapRFCConnector` y se invocó:

- `RFC_PING`
- `STFC_CONNECTION`

Resultado:

```text
RFC_PING + STFC_CONNECTION OK
```

Respuesta STFC resumida:

```text
SAP R/3 Rel. 754   Sysid: A4H      Date: 20260506   Logon_Data: 000/SAP*/E
```

---

### 5.3 Tools MCP

| Tool | Prueba | Resultado |
|---|---|---:|
| `sap_ping` | Invoca `RFC_PING` | ✅ OK |
| `sap_rfc_call` | `STFC_CONNECTION` con `REQUTEXT=tool-rfc-call` | ✅ OK |
| `sap_read_table` | Tabla `T000`, campos `MANDT`, `MTEXT` | ✅ OK |
| `sap_search_rfc` | Prefix `RFC`, limit `5` | ✅ OK |
| `sap_describe_rfc` | Interfaz de `STFC_CONNECTION` | ✅ OK |
| `sap_prompt_protocol` | Protocolo sobre prompt humano | ✅ OK |
| `sap_resources_invalidate` | Invalidación por prefijo | ✅ OK |
| `sap_audit_tail` | Últimos registros JSONL | ✅ OK |
| `sap_catalog_search` | Búsqueda offline en snapshot | ✅ OK |

#### Resultado `sap_read_table("T000")`

```json
[
  {
    "MANDT": "000",
    "MTEXT": "SAP SE"
  },
  {
    "MANDT": "001",
    "MTEXT": "SAP SE"
  }
]
```

#### Resultado `sap_search_rfc("RFC", limit=5)`

```text
RFC_REGISTER
RFC_UNREGISTER
RFC_BL_ENTRY
RFC_CALCULATE_TAXES_DOC_TMPLT
RFC_DESTINATION_FINDER
```

#### Resultado `sap_describe_rfc("STFC_CONNECTION")`

`RFC_GET_FUNCTION_INTERFACE` devolvió **3 parámetros**:

| Parámetro | Clase | Tipo |
|---|---|---|
| `ECHOTEXT` | `E` | `C` |
| `RESPTEXT` | `E` | `C` |
| `REQUTEXT` | `I` | `C` |

---

## 6. Resources MCP validados

| Resource | TTL | Resultado |
|---|---:|---:|
| `sap://system/info` | 60s | ✅ OK |
| `sap://policy/allowlist` | infinito hasta invalidación | ✅ OK |
| `sap://function/STFC_CONNECTION/interface` | 600s | ✅ OK |
| `sap://table/T000/schema` | 600s | ✅ OK |
| `sap://catalog/rfc?prefix=RFC` | 300s | ✅ OK |
| `sap://catalog/snapshot` | snapshot local | ✅ OK |

### 6.1 `sap://system/info`

Validado:

- Ejecuta `STFC_CONNECTION` con `REQUTEXT="sapmcp ping"`.
- Devuelve versión SDK: `7.77.500`.
- Devuelve parámetros SAP sanitizados.
- No expone password.
- No expone path del SDK.

Resumen:

```json
{
  "stfc_echo": "sapmcp ping",
  "sdk_version": "7.77.500",
  "sap_params": {
    "ASHOST": "127.0.0.1",
    "SYSNR": "00",
    "CLIENT": "000",
    "USER": "SAP*",
    "LANG": "EN"
  }
}
```

### 6.2 `sap://table/T000/schema`

`DDIF_FIELDINFO_GET` devolvió **17 campos** para `T000`.

Primeros campos:

| Campo | Tipo | Key | Texto |
|---|---|---:|---|
| `MANDT` | `CLNT` | ✅ | Client |
| `MTEXT` | `CHAR` | ❌ | Client name |
| `ORT01` | `CHAR` | ❌ | City |
| `MWAER` | `CUKY` | ❌ | Standard Currency in Client |
| `ADRNR` | `CHAR` | ❌ | Character Field with Length 10 |

### 6.3 `sap://catalog/rfc?prefix=RFC`

La búsqueda cacheada en `TFDIR` devolvió **100 funciones** por el límite de policy.

Primeras funciones:

```text
RFC_REGISTER
RFC_UNREGISTER
RFC_BL_ENTRY
RFC_CALCULATE_TAXES_DOC_TMPLT
RFC_DESTINATION_FINDER
RFCDEST_GET_FOR_LOGICAL_SYSTEM
RFC_CALLBACK_REJECTED
RFC_DATA_DETERMINE_FOR_CHECKS
```

---

## 7. Prompts MCP validados

Se validaron los 6 prompts operativos:

| Prompt | Resultado |
|---|---:|
| `basis_triage_sistema` | ✅ OK |
| `inspeccionar_pedido_venta` | ✅ OK |
| `seguimiento_idoc` | ✅ OK |
| `revisar_jobs_largos` | ✅ OK |
| `informe_sociedad` | ✅ OK |
| `pre_change_check` | ✅ OK |

Cada prompt devuelve 3 mensajes estructurados:

```text
user      -> rol/instrucción tipo SYSTEM codificada para MCP
user      -> tarea concreta con placeholders sustituidos
assistant -> esqueleto de ejecución/respuesta esperada
```

> Nota técnica: en esta versión de FastMCP los mensajes renderizados admiten roles `user` y `assistant`; por eso el rol de sistema se codifica como contenido `SYSTEM:` dentro del primer mensaje `user`. Esto está cubierto por tests.

El prompt `pre_change_check` incluye checklist completo:

- Sistema destino.
- Mandante.
- Hora y zona horaria.
- Ventana de cambio autorizada.
- Ticket/orden de cambio.
- Impacto esperado.
- Plan de rollback.
- Backup/snapshot/export previo si aplica.
- Responsable aprobador.
- Parámetros exactos de RFC.
- Confirmación humana explícita antes de `confirm_dangerous=true`.

---

## 8. Audit log JSONL

Validado:

- Se escriben registros JSONL diarios en `SAPMCP_HOME` / `~/.sapmcp`.
- `sap_audit_tail` recupera últimas líneas.
- Registra `tool`, `function`, `rc`, `sid`, `mandt`, `user`, `dangerous`, `confirmed`, `error_key`.
- No registra contraseña.
- No muestra `PASSWD` en tail.

Ejemplo sanitizado de campos auditados:

```json
{
  "tool": "sap_rfc_call",
  "function": "STFC_CONNECTION",
  "rc": 0,
  "sid": "127.0.0.1",
  "mandt": "000",
  "user": "SAP*",
  "dangerous": false,
  "confirmed": false,
  "error_key": null
}
```

Durante la prueba final se verificaron **13 registros** y el resultado fue:

```text
audit records=13 clean=True
```

---

## 9. SNC opcional

Se validó que `SapConnectionConfig.from_env` acepta variables SNC si están definidas:

```text
SAP_SNC_LIB
SAP_SNC_QOP
SAP_SNC_MYNAME
SAP_SNC_PARTNERNAME
SAP_SNC_MODE
```

Resultado:

```json
{
  "SNC_LIB": "/opt/sap/snclib.so",
  "SNC_QOP": "9",
  "SNC_MYNAME": "p:me",
  "SNC_PARTNERNAME": "p:sap",
  "SNC_MODE": "1"
}
```

No se probó autenticación SNC real porque el ABAP Docker de prueba no está configurado con SNC.

---

## 10. Keyring opcional

Verificado a nivel de proyecto/configuración:

- Script registrado: `sapmcp-credentials = "sapmcp.credentials:main"`.
- Extra opcional definido:

```toml
[project.optional-dependencies]
keyring = ["keyring>=24"]
```

La dependencia `keyring` no es obligatoria en runtime, como se pidió.

No se guardó una contraseña real en keyring durante esta validación para evitar persistir credenciales innecesarias.

---

## 11. Snapshot offline del catálogo SAP

Se ejecutó un snapshot pequeño y controlado para validar el flujo sin cargar el sistema:

```text
page_size=20
max_pages=1
```

Tablas leídas vía `RFC_READ_TABLE`:

- `TFDIR`: funciones RFC.
- `DD02L`: tablas SAP.
- `DD03L`: campos SAP.

Resultado:

```json
{
  "counts": {
    "rfc": 20,
    "tables": 20,
    "fields": 20
  },
  "sid": "127.0.0.1"
}
```

Resource validado:

```text
sap://catalog/snapshot
```

Tool validada:

```text
sap_catalog_search(kind="rfc", pattern="*RFC*")
```

Resultado ejemplo:

```json
[
  {
    "FUNCNAME": "/SAPSLL/DOC_CATS_GET_SPI_RFC",
    "PNAME": "/SAPSLL/SAPLDOC_TYPES_SPI_RFC"
  }
]
```

> Nota: el snapshot completo debe ejecutarse sin `max_pages` cuando se quiera generar el catálogo real completo. La prueba fue intencionadamente pequeña.

---

## 12. Corrección aplicada durante la validación

Durante la prueba real se detectó una incompatibilidad con `RFC_GET_FUNCTION_INTERFACE`.

### Problema

En este sistema SAP, pedir la tabla `EXCEPTION_LIST` provocaba:

```text
INVALID_PARAMETER: EXCEPTION_LIST not found
```

### Causa

Algunas releases/sistemas SAP no exponen `EXCEPTION_LIST` en `RFC_GET_FUNCTION_INTERFACE`, o no la exponen con ese nombre para el SDK en esta ruta.

### Corrección

Archivo modificado:

```text
/Users/eduardoariasbravo/Developer/sapmcp/src/sapmcp/resources.py
```

Cambio aplicado:

- `describe_rfc_interface` ahora pide solo `PARAMS`.
- Si no viene `EXCEPTION_LIST`, añade `EXCEPTION_LIST: []` al resultado para mantener shape estable.

Resultado después del cambio:

```text
sap_describe_rfc("STFC_CONNECTION") OK
PARAMS=3
```

Tests locales después del cambio:

```text
20 passed
```

---

## 13. Limpieza realizada

Se eliminaron temporales con credenciales y scripts de prueba:

Local:

```text
/tmp/sapmcp-abap-docker-fulltest.env
/tmp/sapmcp-src.tgz
/tmp/sapmcp_fulltest.py
```

Remoto:

```text
/tmp/sapmcp-test/.env
/tmp/sapmcp-src.tgz
/tmp/sapmcp_fulltest.py
```

---

## 14. Limitaciones conocidas

1. **SDK RFC local macOS no encontrado**  
   El Mac local no tiene configurado `libsapnwrfc.dylib`, por lo que las pruebas RFC reales se ejecutaron en la VM Linux.

2. **Snapshot completo no ejecutado**  
   Solo se generó snapshot pequeño para validar el mecanismo. Para producción/DEV conviene ejecutar el snapshot completo en ventana controlada.

3. **SNC no probado end-to-end**  
   La config SNC acepta variables, pero el ABAP Docker de prueba no está configurado con SNC real.

4. **`RFC_READ_TABLE` mantiene límites SAP**  
   Sigue aplicando truncamiento server-side de `DATA-WA` a 512 bytes. Para tablas anchas o uso productivo se recomienda Z-RFC/BAPI específico o `/BODS/RFC_READ_TABLE2` si existe.

---

## 15. Conclusión

`sapmcp` queda validado en modo lectura contra un SAP real/controlado usando ABAP Docker y `SAP*` en mandante `000`.

Estado recomendado:

```text
Apto para pruebas controladas contra SAP DEV en modo read-only.
```

Antes de usarlo para operaciones de cambio:

1. Mantener `SAPMCP_READ_ONLY=true` por defecto.
2. Revisar allowlist por sistema/mandante.
3. Usar `pre_change_check` antes de cualquier `confirm_dangerous=true`.
4. Activar auditoría y conservar JSONL.
5. Generar snapshot offline completo si el cliente LLM va a navegar catálogos con frecuencia.
