# Manual básico de operación — sapmcp

**Idioma**: castellano  
**Audiencia**: operador Basis/DevOps, consultor SAP, administrador del servidor MCP  
**Objetivo**: instalar `sapmcp` desde cero, conectar uno o varios sistemas SAP, configurar usuarios técnicos y operar las tools MCP de forma segura.

---

## 1. Qué es sapmcp

`sapmcp` es un servidor MCP que permite a un cliente LLM consultar y operar sistemas SAP mediante RFC estándar. Internamente usa:

- Python.
- FastMCP.
- SAP NetWeaver RFC SDK vía `ctypes`.
- Variables de entorno / `.env` para configurar destinos.
- Auditoría JSONL local.
- SafetyPolicy para bloquear operaciones peligrosas por defecto.

No sustituye a SAP GUI, Solution Manager, Focused Run ni herramientas corporativas. Es una capa de automatización y asistencia para lecturas controladas y operación Basis diaria.

---

## 2. Principios de operación segura

1. **Lectura por defecto**: `SAPMCP_READ_ONLY=true`.
2. **Sin contraseñas en respuestas**: configuración y audit redactan secrets.
3. **Un destino por llamada**: usa `destination="DEV"`, `destination="QAS"`, etc.
4. **No mezclar entornos**: define usuarios separados por sistema.
5. **No tocar PRD sin política**: en producción, usa usuario específico y permisos mínimos.
6. **Auditar siempre**: todas las tools que tocan SAP dejan traza JSONL.
7. **Confirmación doble para cambios**: aunque existan tools genéricas, los cambios requieren flags explícitos y autorización humana.

---

## 3. Instalación desde cero

### 3.1 Preparar el directorio

```bash
cd /Users/eduardoariasbravo/Developer/sapmcp
```

Si partes de una copia nueva del proyecto, entra en su raíz.

### 3.2 Crear entorno Python

```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
```

Recomendado: Python 3.10, 3.11 o 3.12. El proyecto declara `>=3.10`.

### 3.3 Instalar sapmcp en editable

```bash
pip install -e .
```

Opcional, con soporte keyring:

```bash
pip install -e '.[keyring]'
```

### 3.4 Crear `.env`

```bash
cp .env.example .env
```

Edita `.env` con tus sistemas SAP y la ruta del RFC SDK.

### 3.5 Instalar SAP NetWeaver RFC SDK

Descarga el SDK desde SAP Software Downloads según licencia corporativa.

Ubicación típica macOS/Linux:

```text
/usr/local/sap/nwrfcsdk/lib
```

Comprueba que existe:

```bash
ls -la /usr/local/sap/nwrfcsdk/lib
```

Debe aparecer algo como:

```text
libsapnwrfc.dylib   # macOS
libsapnwrfc.so      # Linux
sapnwrfc.dll        # Windows
```

Configura en `.env`:

```env
SAP_NWRFC_LIB_DIR=/usr/local/sap/nwrfcsdk/lib
```

O fija el fichero exacto:

```env
SAP_NWRFC_LIB_PATH=/usr/local/sap/nwrfcsdk/lib/libsapnwrfc.dylib
```

### 3.6 Variables de librería dinámica

macOS:

```bash
export DYLD_LIBRARY_PATH=/usr/local/sap/nwrfcsdk/lib:$DYLD_LIBRARY_PATH
```

Linux:

```bash
export LD_LIBRARY_PATH=/usr/local/sap/nwrfcsdk/lib:$LD_LIBRARY_PATH
```

Si el MCP se arranca desde una app gráfica, puede que esas variables no entren desde el shell. En ese caso usa `SAP_NWRFC_LIB_PATH` en `.env` o configura `env` explícito en el cliente MCP.

---

## 4. Configurar el primer sistema SAP

El destino clásico se llama `default` y usa variables sin prefijo.

```env
SAP_ASHOST=host.sap.local
SAP_SYSNR=00
SAP_CLIENT=100
SAP_USER=RFC_SAPMCP
SAP_PASS=********
SAP_LANG=ES
SAP_NWRFC_LIB_DIR=/usr/local/sap/nwrfcsdk/lib
```

### 4.1 Conexión por application server

Usa:

```env
SAP_ASHOST=s4d-app01.company.local
SAP_SYSNR=00
SAP_CLIENT=100
```

### 4.2 Conexión por message server / logon group

Usa:

```env
SAP_MSHOST=s4d-msg.company.local
SAP_R3NAME=S4D
SAP_GROUP=PUBLIC
SAP_CLIENT=100
```

### 4.3 SAProuter

```env
SAP_SAPROUTER=/H/router.company.local/S/3299/H/
```

### 4.4 SNC

```env
SAP_SNC_MODE=1
SAP_SNC_LIB=/path/to/libsapcrypto.dylib
SAP_SNC_QOP=8
SAP_SNC_MYNAME=p:CN=sapmcp-client, OU=Basis, O=Company
SAP_SNC_PARTNERNAME=p:CN=sap/server, OU=SAP, O=Company
```

SNC requiere configuración Basis previa: PSE, certificados, trust y nombres SNC correctos.

---

## 5. Añadir varios sistemas SAP

### 5.1 Definir lista de destinos

```env
SAPMCP_DESTINATIONS=DEV,QAS,PRD
SAPMCP_DEFAULT_DESTINATION=DEV
```

- `SAPMCP_DESTINATIONS`: lista CSV de nombres lógicos.
- `SAPMCP_DEFAULT_DESTINATION`: destino usado cuando una tool omite `destination`.
- `default`: siempre existe y usa variables `SAP_*` sin prefijo.

### 5.2 Variables por destino

Para cada destino `N`, usa `SAP_{N}_...`.

Ejemplo DEV:

```env
SAP_DEV_ASHOST=dev-app.company.local
SAP_DEV_SYSNR=00
SAP_DEV_CLIENT=100
SAP_DEV_USER=RFC_SAPMCP_DEV
SAP_DEV_PASS=********
SAP_DEV_LANG=ES
```

Ejemplo QAS:

```env
SAP_QAS_ASHOST=qas-app.company.local
SAP_QAS_SYSNR=00
SAP_QAS_CLIENT=100
SAP_QAS_USER=RFC_SAPMCP_QAS
SAP_QAS_PASS=********
SAP_QAS_LANG=ES
```

Ejemplo PRD con message server:

```env
SAP_PRD_MSHOST=prd-msg.company.local
SAP_PRD_R3NAME=PRD
SAP_PRD_GROUP=PUBLIC
SAP_PRD_CLIENT=100
SAP_PRD_USER=RFC_SAPMCP_PRD
SAP_PRD_PASS=********
SAP_PRD_LANG=ES
```

### 5.3 Variables soportadas por destino

| Variable | Descripción |
| --- | --- |
| `SAP_{N}_ASHOST` | Application server. |
| `SAP_{N}_SYSNR` | Número de sistema. |
| `SAP_{N}_CLIENT` | Mandante. |
| `SAP_{N}_USER` | Usuario RFC. |
| `SAP_{N}_PASS` | Password. También se aceptan `PASSWD`/`PASSWORD`. |
| `SAP_{N}_LANG` | Idioma. |
| `SAP_{N}_MSHOST` | Message server. |
| `SAP_{N}_R3NAME` | SID para message server. |
| `SAP_{N}_GROUP` | Logon group. |
| `SAP_{N}_SAPROUTER` | SAProuter string. |
| `SAP_{N}_SNC_LIB` | Librería SNC. |
| `SAP_{N}_SNC_QOP` | Calidad SNC. |
| `SAP_{N}_SNC_MYNAME` | Nombre SNC cliente. |
| `SAP_{N}_SNC_PARTNERNAME` | Nombre SNC servidor. |
| `SAP_{N}_SNC_MODE` | Activa SNC. |

### 5.4 Comprobar destinos

Desde el cliente MCP:

```text
read_resource("sap://destinations")
```

O con tool:

```json
{
  "tool": "sap_config_status",
  "arguments": {"destination": "DEV"}
}
```

---

## 6. Configurar usuarios SAP

### 6.1 Crear usuario técnico

En cada SAP, coordina con Basis/Security la creación de un usuario técnico.

Ejemplo de naming:

| Sistema | Usuario |
| --- | --- |
| DEV | `RFC_SAPMCP_DEV` |
| QAS | `RFC_SAPMCP_QAS` |
| PRD | `RFC_SAPMCP_PRD` |

Recomendaciones:

- Usuario técnico por entorno.
- Password gestionada por vault/keyring si es posible.
- No reutilizar usuarios personales.
- Bloquear permisos de cambio salvo necesidad explícita.
- En PRD, permisos mínimos y revisión periódica.

### 6.2 Autorizaciones SAP habituales

Dependen de release y política, pero normalmente se revisan:

| Área | Posible autorización |
| --- | --- |
| RFC estándar | `S_RFC` para funciones/BAPIs permitidas. |
| Lectura tablas | `S_TABU_DIS`, `S_TABU_NAM` según configuración. |
| Jobs/XBP | Permisos para `BAPI_XBP_JOB_SELECT`. |
| Monitorización Basis | Permisos para `TH_WPINFO`, `TH_SERVER_LIST`, `TH_USER_LIST`, syslog, enqueue. |
| Usuario audit | Permisos para `BAPI_USER_GET_DETAIL`, `BAPI_USER_LOCK_STATUS`, lectura `USR02`. |

No des SAP_ALL salvo en entornos sandbox/controlados.

### 6.3 Password en `.env`

```env
SAP_DEV_USER=RFC_SAPMCP_DEV
SAP_DEV_PASS=********
```

Ventaja: simple.  
Desventaja: secreto en fichero local.

### 6.4 Password con keyring

Instala:

```bash
pip install -e '.[keyring]'
```

Activa:

```env
SAPMCP_USE_KEYRING=true
```

Para destino clásico:

```bash
export SAP_USER=RFC_SAPMCP
sapmcp-credentials set
```

Para destino nombrado específico:

```bash
python - <<'PY'
import getpass
import keyring
keyring.set_password("sapmcp", "DEV:RFC_SAPMCP_DEV", getpass.getpass("Password DEV: "))
PY
```

Resolución de password con keyring:

1. Para destino `DEV` y usuario `RFC_SAPMCP_DEV`, busca `DEV:RFC_SAPMCP_DEV`.
2. Si no existe, busca `RFC_SAPMCP_DEV`.
3. Si no existe, falla con error claro.

---

## 7. Configuración de seguridad

Bloque recomendado:

```env
SAPMCP_READ_ONLY=true
SAPMCP_ALLOW_DANGEROUS=false
SAPMCP_ALLOWED_RFC=
SAPMCP_MAX_ROWS=200
SAPMCP_RFC_TIMEOUT=60
```

### 7.1 READ_ONLY

```env
SAPMCP_READ_ONLY=true
```

Permite RFCs conocidas como lectura y bloquea llamadas desconocidas o sospechosas.

### 7.2 Allowlist

Si quieres restringir todavía más:

```env
SAPMCP_ALLOWED_RFC=RFC_PING,STFC_CONNECTION,RFC_READ_TABLE,RFC_GET_*,DDIF_*,BAPI_*_GET*,BAPI_XBP_JOB_SELECT
```

Cuando `SAPMCP_ALLOWED_RFC` no está vacío, cualquier RFC fuera de la lista se bloquea.

### 7.3 Peligrosas

Por defecto:

```env
SAPMCP_ALLOW_DANGEROUS=false
```

Las RFCs con patrones como `*CREATE*`, `*CHANGE*`, `*DELETE*`, `*UPDATE*`, `*POST*`, `*COMMIT*`, etc. se bloquean.

Para permitirlas en un laboratorio controlado:

```env
SAPMCP_READ_ONLY=false
SAPMCP_ALLOW_DANGEROUS=true
```

Y la llamada debe incluir:

```json
{"confirm_dangerous": true}
```

### 7.4 Límites

```env
SAPMCP_MAX_ROWS=200
SAPMCP_RFC_TIMEOUT=60
```

- `SAPMCP_MAX_ROWS`: limita wrappers de tabla y catálogos.
- `SAPMCP_RFC_TIMEOUT`: timeout por invocación RFC.

---

## 8. Configurar el cliente MCP

Ejemplo genérico:

```json
{
  "mcpServers": {
    "sapmcp": {
      "command": "/Users/eduardoariasbravo/Developer/sapmcp/.venv/bin/sapmcp",
      "cwd": "/Users/eduardoariasbravo/Developer/sapmcp"
    }
  }
}
```

Si el cliente necesita variables explícitas:

```json
{
  "mcpServers": {
    "sapmcp": {
      "command": "/Users/eduardoariasbravo/Developer/sapmcp/.venv/bin/sapmcp",
      "cwd": "/Users/eduardoariasbravo/Developer/sapmcp",
      "env": {
        "SAP_NWRFC_LIB_DIR": "/usr/local/sap/nwrfcsdk/lib"
      }
    }
  }
}
```

Normalmente `.env` se carga desde el `cwd` del proyecto.

---

## 9. Primera verificación tras instalar

Ejecuta en este orden desde el cliente MCP.

### 9.1 Estado de configuración

```json
{
  "tool": "sap_config_status",
  "arguments": {"destination": "DEV"}
}
```

Revisa:

- `destination` correcto.
- `sap_params` sin password expuesta.
- `resolved_library` apunta a SDK válido.
- `safety.read_only=true`.

### 9.2 Lista de destinos

```text
read_resource("sap://destinations")
```

### 9.3 Ping

```json
{
  "tool": "sap_ping",
  "arguments": {"destination": "DEV"}
}
```

### 9.4 System info

```text
read_resource("sap://DEV/system/info")
```

### 9.5 Health check quick

```json
{
  "tool": "sap_health_check",
  "arguments": {"destination": "DEV", "profile": "quick"}
}
```

Si estos pasos funcionan, el sistema está operativo.

---

## 10. Operación diaria básica

### 10.1 “Dime cómo está el sistema”

```json
{
  "tool": "sap_health_check",
  "arguments": {"destination": "DEV", "profile": "standard"}
}
```

Luego puedes usar el prompt:

```text
get_prompt("health_check_response", {"health_json": <JSON devuelto>})
```

### 10.2 Dumps ABAP de hoy

```json
{
  "tool": "sap_get_short_dumps",
  "arguments": {"destination": "DEV"}
}
```

Con rango y usuario:

```json
{
  "tool": "sap_get_short_dumps",
  "arguments": {
    "destination": "DEV",
    "date_from": "20260506",
    "date_to": "20260506",
    "user": "ALICE"
  }
}
```

### 10.3 Syslog de errores

```json
{
  "tool": "sap_get_syslog",
  "arguments": {
    "destination": "DEV",
    "date_from": "20260506",
    "date_to": "20260506",
    "severity": "E"
  }
}
```

Severity esperada:

| Valor | Significado orientativo |
| --- | --- |
| `K` | Kernel |
| `W` | Warning |
| `E` | Error |
| `A` | ABAP |

### 10.4 Locks

```json
{
  "tool": "sap_get_locks",
  "arguments": {"destination": "DEV"}
}
```

Por tabla:

```json
{
  "tool": "sap_get_locks",
  "arguments": {"destination": "DEV", "table": "BKPF"}
}
```

### 10.5 Workprocesses

```json
{
  "tool": "sap_get_workprocesses",
  "arguments": {"destination": "DEV"}
}
```

Por servidor:

```json
{
  "tool": "sap_get_workprocesses",
  "arguments": {"destination": "DEV", "server": "app1"}
}
```

### 10.6 Updates pendientes o erróneos

```json
{
  "tool": "sap_get_update_requests",
  "arguments": {"destination": "DEV", "status": "ERR"}
}
```

### 10.7 Colas RFC

```json
{
  "tool": "sap_get_rfc_queue",
  "arguments": {"destination": "DEV", "queue_type": "trfc"}
}
```

Valores:

- `trfc`
- `qrfc_out`
- `qrfc_in`

### 10.8 Jobs cancelados

```json
{
  "tool": "sap_get_jobs",
  "arguments": {"destination": "DEV", "status": "A", "since_days": 1}
}
```

Estados comunes:

| Estado | Significado |
| --- | --- |
| `R` | Running |
| `F` | Finished |
| `A` | Aborted |
| `S` | Scheduled |

### 10.9 Auditoría de usuario

```json
{
  "tool": "sap_get_user_audit",
  "arguments": {"destination": "DEV", "user": "ALICE"}
}
```

Devuelve perfiles, roles, bloqueo, vigencia, último logon, fallos y marca `sap_all=true` si detecta perfil `SAP_ALL`.

---

## 11. Health check en detalle

### 11.1 Perfiles

| Perfil | Uso recomendado |
| --- | --- |
| `quick` | Validación rápida al arrancar o tras cambios de red. |
| `standard` | Operación diaria. |
| `deep` | Diagnóstico más amplio cuando hay incidencia o revisión planificada. |

### 11.2 Umbrales configurables

```env
SAPMCP_HC_DUMPS_WARN=5
SAPMCP_HC_DUMPS_CRIT=20
SAPMCP_HC_LOCKS_WARN=50
SAPMCP_HC_LOCKS_CRIT=200
SAPMCP_HC_UPDATE_PENDING_WARN=1
SAPMCP_HC_UPDATE_PENDING_CRIT=10
SAPMCP_HC_UPDATE_ERR_WARN=1
SAPMCP_HC_UPDATE_ERR_CRIT=1
SAPMCP_HC_TRFC_WARN=20
SAPMCP_HC_TRFC_CRIT=100
SAPMCP_HC_JOBS_ABORTED_WARN=1
SAPMCP_HC_JOBS_ABORTED_CRIT=5
SAPMCP_HC_WP_PRIV_WARN=1
SAPMCP_HC_WP_PRIV_CRIT=2
SAPMCP_HC_WP_STOPPED_WARN=1
SAPMCP_HC_WP_STOPPED_CRIT=1
```

### 11.3 Interpretación del verdict

| Verdict | Significado |
| --- | --- |
| `ok` | No hay warnings, críticos ni unknown. |
| `warn` | Hay warnings o checks unknown junto a checks válidos. |
| `crit` | Al menos un check crítico. |
| `unknown` | Todos los checks fallaron, expiraron o no están autorizados. |

---

## 12. Resources y cache

El cache es en memoria del proceso y usa deduplicación **single-flight por clave**. Ante múltiples lecturas simultáneas del mismo resource no cacheado o expirado, un solo thread ejecuta la llamada SAP/RFC y los demás esperan el mismo resultado. Esto evita ráfagas duplicadas contra SAP sin bloquear resources de claves distintas.

Notas operativas:

- Los TTLs se aplican desde el fin de la carga exitosa.
- Si el loader falla, todos los callers concurrentes reciben la misma excepción y la clave queda disponible para reintento.
- La invalidación manual limpia entradas cacheadas y desacopla cargas en curso; peticiones posteriores vuelven a cargar.

Invalidar todo:

```json
{
  "tool": "sap_resources_invalidate",
  "arguments": {}
}
```

Invalidar por prefijo:

```json
{
  "tool": "sap_resources_invalidate",
  "arguments": {"prefix": "function/BAPI_USER"}
}
```

Resources útiles:

```text
read_resource("sap://DEV/system/info")
read_resource("sap://DEV/policy/allowlist")
read_resource("sap://DEV/function/BAPI_USER_GET_DETAIL/interface")
read_resource("sap://DEV/table/T000/schema")
read_resource("sap://DEV/catalog/rfc?prefix=BAPI_USER")
```

---

## 13. Auditoría

Ruta por defecto:

```text
~/.sapmcp/audit-YYYYMMDD.jsonl
```

Cambiar home:

```env
SAPMCP_HOME=/ruta/segura/sapmcp
```

Consultar últimas líneas:

```json
{
  "tool": "sap_audit_tail",
  "arguments": {"n": 50}
}
```

Campos principales:

| Campo | Descripción |
| --- | --- |
| `ts` | Timestamp UTC. |
| `tool` | Tool ejecutada. |
| `function` | RFC principal. |
| `destination` | Destino lógico. |
| `params_hash` | Hash de parámetros redactados. |
| `rc` | 0 si OK; distinto de 0 si error. |
| `duration_ms` | Duración. |
| `sid`, `mandt`, `user` | Contexto SAP sanitizado. |
| `dangerous`, `confirmed` | Contexto SafetyPolicy. |
| `error_key`, `error_message` | Error si lo hubo. |

---

## 14. Snapshot offline

Generar snapshot:

```bash
source .venv/bin/activate
sapmcp-snapshot --page-size 500
```

Buscar sin tocar SAP:

```json
{
  "tool": "sap_catalog_search",
  "arguments": {"kind": "rfc", "pattern": "BAPI_USER"}
}
```

```json
{
  "tool": "sap_catalog_search",
  "arguments": {"kind": "table", "pattern": "USR*"}
}
```

---

## 15. Troubleshooting

### 15.1 No encuentra librería SAP RFC SDK

Síntoma:

```text
cannot open shared object file
Library not loaded: libsapnwrfc.dylib
```

Revisar:

```env
SAP_NWRFC_LIB_DIR=/usr/local/sap/nwrfcsdk/lib
```

O usar:

```env
SAP_NWRFC_LIB_PATH=/usr/local/sap/nwrfcsdk/lib/libsapnwrfc.dylib
```

En Linux/macOS, exportar `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH`.

### 15.2 Login failed

Revisar:

- Usuario/password.
- Mandante `SAP_CLIENT`.
- Bloqueo de usuario en SAP.
- Tipo de usuario permite RFC.
- SNC/SAProuter si aplica.

### 15.3 RFC bloqueada por SafetyPolicy

Ejecuta:

```json
{
  "tool": "sap_safety_check",
  "arguments": {"function_name": "NOMBRE_RFC"}
}
```

Si usas allowlist, añade patrón:

```env
SAPMCP_ALLOWED_RFC=RFC_PING,STFC_CONNECTION,RFC_READ_TABLE,RFC_GET_*,BAPI_*_GET*,NOMBRE_RFC
```

### 15.4 RFC no existe o no autorizada

Las tools Basis intentan devolver:

```json
{"available": false, "reason": "..."}
```

Acciones:

- Confirmar que la RFC existe en la release SAP.
- Confirmar autorización `S_RFC`.
- Usar fallback si existe.
- Consultar `sap_describe_rfc`.

### 15.5 `RFC_READ_TABLE` trunca datos

Limitación SAP conocida: `DATA-WA` puede truncarse a 512 bytes según implementación estándar.

Recomendación:

- Pedir pocos campos.
- Usar filtros `where` estrictos.
- Para producción, crear Z-RFC/BAPI específico o usar alternativa autorizada como `/BODS/RFC_READ_TABLE2` si existe.

### 15.6 Health check queda `unknown`

Causas comunes:

- Sistema no responde.
- Timeout global del perfil.
- Falta autorización a RFCs Basis.
- SDK no cargó correctamente.

Pasos:

1. `sap_config_status(destination="...")`
2. `sap_ping(destination="...")`
3. `sap_health_check(profile="quick")`
4. Revisar audit con `sap_audit_tail`.

---

## 16. Procedimiento recomendado para añadir un sistema nuevo

1. Crear usuario técnico en SAP.
2. Validar login RFC con Basis.
3. Añadir destino al `.env`:

```env
SAPMCP_DESTINATIONS=DEV,QAS,NUEVO
SAP_NUEVO_ASHOST=nuevo-app.company.local
SAP_NUEVO_SYSNR=00
SAP_NUEVO_CLIENT=100
SAP_NUEVO_USER=RFC_SAPMCP_NUEVO
SAP_NUEVO_PASS=********
SAP_NUEVO_LANG=ES
```

4. Reiniciar el cliente MCP/servidor si ya estaba cargado.
5. Verificar configuración:

```json
{"tool": "sap_config_status", "arguments": {"destination": "NUEVO"}}
```

6. Probar ping:

```json
{"tool": "sap_ping", "arguments": {"destination": "NUEVO"}}
```

7. Probar resource:

```text
read_resource("sap://NUEVO/system/info")
```

8. Probar health check quick:

```json
{"tool": "sap_health_check", "arguments": {"destination": "NUEVO", "profile": "quick"}}
```

9. Ajustar autorizaciones si algún check devuelve `available=false` o `unknown`.
10. Documentar el destino y responsable operativo.

---

## 17. Procedimiento recomendado para añadir un usuario nuevo

1. Crear usuario en SAP con naming claro: `RFC_SAPMCP_<ENTORNO>`.
2. Asignar roles mínimos de lectura.
3. Probar login RFC fuera de producción si es posible.
4. Guardar password en `.env` o keyring.
5. Actualizar variables:

```env
SAP_DEV_USER=RFC_SAPMCP_DEV2
SAP_DEV_PASS=********
```

O keyring:

```bash
python - <<'PY'
import getpass, keyring
keyring.set_password("sapmcp", "DEV:RFC_SAPMCP_DEV2", getpass.getpass("Password: "))
PY
```

6. Ejecutar:

```json
{"tool": "sap_config_status", "arguments": {"destination": "DEV"}}
```

7. Ejecutar:

```json
{"tool": "sap_ping", "arguments": {"destination": "DEV"}}
```

8. Revisar audit y permisos.

---

## 18. Checklist de operación diaria

Inicio del día:

- [ ] `sap_health_check(destination="DEV", profile="standard")`
- [ ] `sap_health_check(destination="QAS", profile="standard")`
- [ ] En PRD, al menos `profile="quick"` o según política.
- [ ] Revisar checks `crit` y `warn`.
- [ ] Si hay dumps: `sap_get_short_dumps`.
- [ ] Si hay jobs abortados: `sap_get_jobs(status="A")`.
- [ ] Si hay updates ERR: `sap_get_update_requests(status="ERR")`.
- [ ] Si hay locks altos: `sap_get_locks` con tabla/usuario.
- [ ] Guardar resumen si procede en sistema documental externo.

Durante incidencia:

- [ ] Ejecutar `sap_health_check(profile="deep")` si el sistema responde.
- [ ] Revisar syslog con severity `E`.
- [ ] Revisar workprocesses.
- [ ] Revisar dumps y jobs cancelados.
- [ ] No ejecutar cambios desde `sapmcp` sin checklist `pre_change_check` y aprobación humana.

---

## 19. Comandos de desarrollo

Tests:

```bash
source .venv/bin/activate
pytest -q
```

Compilación sintáctica:

```bash
python -m compileall -q src/sapmcp tests
```

Arranque manual:

```bash
sapmcp
```

---

## 20. Anexos rápidos

### Variables mínimas

```env
SAP_ASHOST=host.sap.local
SAP_SYSNR=00
SAP_CLIENT=100
SAP_USER=RFC_USER
SAP_PASS=********
SAP_NWRFC_LIB_DIR=/usr/local/sap/nwrfcsdk/lib
```

### Variables multi-destination mínimas

```env
SAPMCP_DESTINATIONS=DEV,QAS
SAPMCP_DEFAULT_DESTINATION=DEV
SAP_DEV_ASHOST=dev.sap.local
SAP_DEV_SYSNR=00
SAP_DEV_CLIENT=100
SAP_DEV_USER=RFC_DEV
SAP_DEV_PASS=********
SAP_QAS_ASHOST=qas.sap.local
SAP_QAS_SYSNR=00
SAP_QAS_CLIENT=100
SAP_QAS_USER=RFC_QAS
SAP_QAS_PASS=********
```

### Prueba mínima MCP

```json
{"tool": "sap_ping", "arguments": {"destination": "DEV"}}
```

### Dashboard diario

```json
{"tool": "sap_health_check", "arguments": {"destination": "DEV", "profile": "standard"}}
```

---

## Snapshot offline — paginación robusta

`sapmcp-snapshot` pagina `RFC_READ_TABLE` con `ROWSKIPS` y `ROWCOUNT`, avanzando siempre `ROWSKIPS` por el número real de filas recibidas. No considera fin de tabla una página corta, porque SAP puede devolver menos filas que `--page-size` por límites internos de buffer.

Criterios de parada:

- `empty`: página vacía; fin normal de tabla.
- `stagnant`: la paginación no progresa o el SDK devuelve una página exacta repetida; se aborta con `warning` para evitar bucle infinito.
- `duplicate`: la página solo contiene filas ya devueltas en la página anterior; se aborta con `warning`.
- `max_pages`: se alcanzó el límite operativo `--max-pages`.

El resultado en memoria de `build_snapshot()` incluye `pagination`, por tabla, con `pages`, `rows` y `stopped_by`. El fichero `catalog-{SID}.json.gz` mantiene el formato de catálogo offline existente.
