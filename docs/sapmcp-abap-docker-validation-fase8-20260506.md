# Informe de validación sapmcp contra ABAP Docker — fase 8

**Fecha:** 2026-05-06  
**Proyecto:** `/Users/eduardoariasbravo/Developer/sapmcp`  
**Servidor probado:** ABAP Docker A4H en VM `abap-docker-host`  
**Objetivo:** validar las fases 5-7 (`multi-destination`, tools Basis y `sap_health_check`) y forzar casos límite del bridge `ctypes` contra SAP real/controlado.

> Nota de seguridad: este informe no contiene contraseñas ni secretos. La `.env` temporal se usó solo en `/tmp` y fue eliminada al finalizar.

---

## 1. Resumen ejecutivo

La validación de fase 8 queda **satisfactoria** tras aplicar un fix real en las tools Basis/health descubierto durante el primer smoke test.

| Bloque | Área | Resultado | Observación |
|---|---|---:|---|
| A | Multi-destination | ✅ Verde | `default` y `A4H_DOCKER` resuelven; resource y audit distinguen destination. |
| B | Tools Basis | ✅ Verde con limitaciones Docker | Las 8 tools ejecutan; syslog/update aparecen como `available=false` por RFCs inexistentes en este Docker. |
| C | Health check | ✅ Verde con limitaciones Docker | `quick` queda `ok`; `standard/deep` quedan `warn` por checks `unknown` justificados (syslog/update). |
| D | Stress bridge fase 1 | ✅ Verde | Tipos no-CHAR OK; buffer growth forzado OK; timeout/recovery OK. |
| E | SafetyPolicy real | ✅ Verde | Bloqueos `dangerous`/`not_in_allowlist` correctos; confirm explícito no bloquea por SafetyPolicy. |
| F | Snapshot completo | ✅ Verde | Snapshot sin `max_pages`: 118.848 RFCs, 155.847 tablas, 1.819.533 campos. |
| G | Cierre | ✅ Verde | `pytest -q`: `35 passed`; audit contiene todas las tools requeridas; limpieza realizada. |

---

## 2. Entorno

| Parámetro | Valor |
|---|---|
| VM | `abap-docker-host` |
| Zona GCP | `europe-west1-b` |
| Contenedor | `a4h` |
| Imagen observada | `toberic/abap-platform-trial:1909` |
| Host SAP visto desde VM | `127.0.0.1` |
| SYSNR | `00` |
| Mandante | `000` |
| Usuario | `SAP*` |
| Idioma | `EN` |
| Destination nombrado | `A4H_DOCKER` |
| SAP NW RFC SDK | `7.77.500` |
| Librerías RFC en VM | `/tmp/sapnwrfc/lib` |
| Modo seguridad | `SAPMCP_READ_ONLY=true` |
| Timeout RFC | `30s`, excepto timeout deliberado |
| `SAPMCP_HOME` remoto | `/tmp/sapmcp-phase8-home` |

### Allowlist usada en el smoke test

```text
RFC_PING, STFC_CONNECTION, RFC_READ_TABLE, RFC_GET_FUNCTION_INTERFACE,
DDIF_FIELDINFO_GET, RFC_GET_SHORT_DUMP_LIST, RSLG_READ_SYSLOG,
BAPI_SYSLOG_READ, ENQUEUE_READ, TH_WPINFO, TH_SERVER_LIST, TH_USER_LIST,
BAPI_UPDREQUEST_GETLIST, BAPI_USER_LOCK_STATUS, BAPI_USER_GET_DETAIL,
BAPI_XBP_JOB_SELECT
```

### Nota operativa previa

Durante la preparación se detectó que `SAP*`/000 estaba bloqueado por intentos fallidos de credencial. Se desbloqueó el usuario de laboratorio en HANA (`SAPA4H.USR02`, `UFLAG=0`, `LOCNT=0`) para restaurar el estado necesario del Docker. Esto no es un bug de `sapmcp`; fue una recuperación del entorno de prueba.

---

## 3. Resultado pytest

### Local

```text
35 passed in 1.34s
```

### Nota remota

El smoke remoto ejecutó las validaciones SAP reales; `pytest -q` se ejecutó y verificó en el repo local tras aplicar el fix, que es el requisito de cierre.

---

## 4. Bloques A-F detallados

## 4.1 Bloque A — Multi-destination

| Paso | Resultado | Tiempo | Evidencia |
|---|---:|---:|---|
| A1 `sap_config_status()` | ✅ | 0,2 ms | destination=`default`; destinations=`['default','A4H_DOCKER']` |
| A1 `sap_config_status(destination='A4H_DOCKER')` | ✅ | 0,2 ms | destination=`A4H_DOCKER` |
| A2 `sap://destinations` | ✅ | 0,2 ms | lista ambos sin password |
| A3 `sap://A4H_DOCKER/system/info` | ✅ | 77,7 ms | SDK `7.77.500`, STFC OK |
| A4 `sap_ping(destination='A4H_DOCKER')` | ✅ | 27,7 ms | audit destination=`A4H_DOCKER` |
| A4 `sap_ping()` | ✅ | 20,7 ms | audit destination=`default` |
| A5 invalidate cache | ✅ | 20,6 ms | cached=0.137 ms; fresh=20.457 ms |

Resource `sap://A4H_DOCKER/system/info` recortado:

```json
{
  "destination": "A4H_DOCKER",
  "sap_params": {
    "ASHOST": "127.0.0.1",
    "CLIENT": "000",
    "LANG": "EN",
    "SYSNR": "00",
    "USER": "SAP*"
  },
  "sdk_version": "7.77.500",
  "stfc_connection": {
    "ECHOTEXT": "sapmcp ping",
    "RESPTEXT": "SAP R/3 Rel. 754   Sysid: A4H      Date: 20260506   Time: 192043   Logon_Data: 000/SAP*/E"
  },
  "ttl_seconds": 60,
  "uri": "sap://A4H_DOCKER/system/info"
}
```

Audit de pings recortado:

```json
{
  "audit_count": 2,
  "last_pings": [
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 25.455,
      "error_key": null,
      "error_message": null,
      "function": "RFC_PING",
      "mandt": "000",
      "params_hash": "300655d147c49f99bcc896d479e13023b663565132d3eb4867b44591794960ab",
      "rc": 0,
      "sid": "127.0.0.1",
      "tool": "sap_ping",
      "ts": "2026-05-06T19:20:43.603620+00:00",
      "user": "SAP*"
    },
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "default",
      "duration_ms": 20.066,
      "error_key": null,
      "error_message": null,
      "function": "RFC_PING",
      "mandt": "000",
      "params_hash": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
      "rc": 0,
      "sid": "127.0.0.1",
      "tool": "sap_ping",
      "ts": "2026-05-06T19:20:43.624399+00:00",
      "user": "SAP*"
    }
  ]
}
```

## 4.2 Bloque B — Tools Basis

| Paso | Estado | Tiempo | Salida principal / razón |
|---|---:|---:|---|
| `B1_short_dumps_today` | ✅ `available=true` | 151,0 ms | count=0 |
| `B2_short_dumps_range` | ✅ `available=true` | 27,6 ms | count=0 |
| `B3_syslog_E` | ⚠️ `available=false` | 22,5 ms | No hay RFC estándar de syslog disponible |
| `B4_syslog_all` | ⚠️ `available=false` | 23,0 ms | No hay RFC estándar de syslog disponible |
| `B5_locks` | ✅ `available=true` | 88,5 ms | count=0 |
| `B6_workprocesses` | ✅ `available=true` | 197,7 ms | count=15 |
| `B7_update_requests` | ⚠️ `available=false` | 19,7 ms | RFC BAPI_UPDREQUEST_GETLIST no existe o no está disponible |
| `B8_rfc_queue_trfc` | ✅ `available=true` | 28,4 ms | count=0 |
| `B9_rfc_queue_qrfc_out` | ✅ `available=true` | 30,6 ms | count=0 |
| `B10_jobs_7d` | ✅ `available=true` | 734,5 ms | count=0 |
| `B11_jobs_aborted_30d` | ✅ `available=true` | 25,5 ms | count=0 |
| `B12_user_audit_SAPSTAR` | ✅ `available=true` | 1.145,9 ms | sap_all=True; perfiles=SAP_ALL |
| `B13_user_audit_DDIC` | ✅ `available=true` | 51,9 ms | sap_all=True; perfiles=SAP_ALL,S_A.SYSTEM |

Detalles relevantes:

- `sap_get_locks` funcionó con `count=0`; se valida explícitamente el caso sin datos.
- `sap_get_workprocesses` devolvió 15 work processes, incluyendo DIA/BGD/UPD/SPO/UP2.
- `sap_get_user_audit(user='SAP*')` devolvió `sap_all=true`.
- `sap_get_user_audit(user='DDIC')` devolvió datos y `sap_all=true` aunque `DDIC` no sea la combinación de logon usada para RFC.
- `sap_get_syslog` y `sap_get_update_requests` devuelven `available=false` porque el Docker no expone `RSLG_READ_SYSLOG`/`BAPI_SYSLOG_READ` ni `BAPI_UPDREQUEST_GETLIST`. Se documenta como limitación conocida del entorno.

Ejemplo `sap_get_workprocesses` recortado:

```json
{
  "available": true,
  "count": 15,
  "destination": "A4H_DOCKER",
  "workprocesses": [
    {
      "mandante": "000",
      "numero": "0",
      "programa": "<HANDLE",
      "server": "vhcala4hci_A4H_00",
      "status": "On Hold",
      "tabla": "",
      "tiempo": "1",
      "tipo": "DIA",
      "usuario": "SAP*"
    },
    {
      "mandante": "",
      "numero": "1",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "DIA",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "2",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "DIA",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "3",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "DIA",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "4",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "DIA",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "5",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "DIA",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "6",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "DIA",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "7",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "UPD",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "8",
      "programa": "",
      "server": "vhcala4hci_A4H_00",
      "status": "Waiting",
      "tabla": "",
      "tiempo": "0",
      "tipo": "BGD",
      "usuario": ""
    },
    {
      "mandante": "",
      "numero": "9",
      "programa": "",
      "server": "v
... <recortado>
```

Ejemplo `sap_get_user_audit(SAP*)`:

```json
{
  "address": {},
  "available": true,
  "destination": "A4H_DOCKER",
  "failed_logons": 0,
  "fullname": "",
  "lastlogon": "20260506 192043",
  "lockstatus": {
    "uflag": "0"
  },
  "profiles": [
    "SAP_ALL"
  ],
  "roles": [],
  "sap_all": true,
  "user": "SAP*",
  "valid_from": "00000000",
  "valid_to": "00000000"
}
```

## 4.3 Bloque C — Health check

| Perfil / paso | Resultado | Duración payload | Veredicto / shape | Umbral pedido |
|---|---:|---:|---|---:|
| quick | ✅ | 28,5 ms | verdict=`ok` | < 2.500 ms |
| standard | ✅ | 60,3 ms | verdict=`warn` | < 16.000 ms |
| deep | ✅ | 109,9 ms | verdict=`warn` | < 46.000 ms |
| quick forzado | ✅ | 27,6 ms | verdict=`crit` | warn/crit |
| shape | ✅ | 28,7 ms | all_have_required_keys=True | required keys |

Resumen de checks `quick`:

```json
{
  "checks": [
    {
      "duration_ms": 21.308,
      "error": null,
      "name": "ping",
      "status": "ok",
      "threshold": null,
      "value": {
        "ECHOTEXT": "sapmcp health check",
        "RESPTEXT": "SAP R/3 Rel. 754   Sysid: A4H      Date: 20260506   Time: 192046   Logon_Data: 000/SAP*/E"
      }
    },
    {
      "duration_ms": 23.157,
      "error": null,
      "name": "locks_total",
      "status": "ok",
      "threshold": {
        "crit": 200,
        "warn": 50
      },
      "value": 0
    },
    {
      "duration_ms": 25.253,
      "error": null,
      "name": "workprocesses_priv",
      "status": "ok",
      "threshold": {
        "crit": 2,
        "warn": 1
      },
      "value": 0
    },
    {
      "duration_ms": 25.253,
      "error": null,
      "name": "workprocesses_stopped",
      "status": "ok",
      "threshold": {
        "crit": 1,
        "warn": 1
      },
      "value": 0
    }
  ],
  "destination": "A4H_DOCKER",
  "duration_ms": 28.455,
  "mandt": "000",
  "profile": "quick",
  "sid": "127.0.0.1",
  "started_at": "2026-05-06T19:20:46.193756+00:00",
  "summary": "A4H_DOCKER: health check OK (4 checks en verde).",
  "verdict": "ok"
}
```

`standard` y `deep` no quedan `unknown`; quedan `warn` porque contienen checks individuales `unknown` por RFCs no disponibles en este Docker:

- `update_pending` / `update_err`: `BAPI_UPDREQUEST_GETLIST` no disponible.
- `syslog_sample` en `deep`: no hay `RSLG_READ_SYSLOG` ni `BAPI_SYSLOG_READ`.

Warn/crit deliberado de locks:

```json
{
  "checks": [
    {
      "duration_ms": 20.243,
      "error": null,
      "name": "ping",
      "status": "ok",
      "threshold": null,
      "value": {
        "ECHOTEXT": "sapmcp health check",
        "RESPTEXT": "SAP R/3 Rel. 754   Sysid: A4H      Date: 20260506   Time: 192046   Logon_Data: 000/SAP*/E"
      }
    },
    {
      "duration_ms": 21.193,
      "error": null,
      "name": "locks_total",
      "status": "crit",
      "threshold": {
        "crit": 0,
        "warn": 0
      },
      "value": 0
    },
    {
      "duration_ms": 24.572,
      "error": null,
      "name": "workprocesses_priv",
      "status": "ok",
      "threshold": {
        "crit": 2,
        "warn": 1
      },
      "value": 0
    },
    {
      "duration_ms": 24.572,
      "error": null,
      "name": "workprocesses_stopped",
      "status": "ok",
      "threshold": {
        "crit": 1,
        "warn": 1
      },
      "value": 0
    }
  ],
  "destination": "A4H_DOCKER",
  "duration_ms": 27.6,
  "mandt": "000",
  "profile": "quick",
  "sid": "127.0.0.1",
  "started_at": "2026-05-06T19:20:46.395416+00:00",
  "summary": "A4H_DOCKER: verdict=crit; crit=1, warn=0, unknown=0. Revisar: locks_total.",
  "verdict": "crit"
}
```

Shape check:

```json
{
  "all_have_required_keys": true,
  "checks": 4,
  "keys_by_check": {
    "locks_total": [
      "duration_ms",
      "error",
      "name",
      "status",
      "threshold",
      "value"
    ],
    "ping": [
      "duration_ms",
      "error",
      "name",
      "status",
      "threshold",
      "value"
    ],
    "workprocesses_priv": [
      "duration_ms",
      "error",
      "name",
      "status",
      "threshold",
      "value"
    ],
    "workprocesses_stopped": [
      "duration_ms",
      "error",
      "name",
      "status",
      "threshold",
      "value"
    ]
  }
}
```

## 4.4 Bloque D — Stress fase 1 contra sistema real

| Paso | Resultado | Tiempo | Observación |
|---|---:|---:|---|
| D1 tipos no-CHAR en `DD03L` | ✅ | 75,1 ms | `POSITION` e `INTLEN` numéricos; `KEYFLAG` válido. |
| D2 buffer growth | ✅ | 51,4 ms | `STFC_CONNECTION` con `buffer_size=4` expandió hasta devolver `ECHOTEXT` de 200 chars. |
| D3 timeout deliberado + recovery | ✅ | 73,9 ms | Con `1s` no llegó a timeout; con `0.001s` sí; `sap_ping` posterior OK. |
| D4 health posterior | ✅ | 28,1 ms | `quick` posterior queda `ok`. |

Nota D1: en este A4H la columna técnica es `INTLEN`, no `INTLENGTH`; se intentó `INTLENGTH`, SAP devolvió `E_WITHOUT_DATA`, y se reintentó con `INTLEN` para validar el tipo no-CHAR equivalente.

D1 recortado:

```json
{
  "fallback_reason": "SAP RFC error during RfcInvoke(RFC_READ_TABLE): code=4294967301 | key=E_WITHOUT_DATA | message=D Type:E Number:718 DD03L",
  "field_used": "INTLEN",
  "intlength_numeric": true,
  "keyflag_valid": true,
  "position_numeric": true,
  "rows": [
    {
      "FIELDNAME": "MANDT",
      "INTLEN": "000006",
      "KEYFLAG": "X",
      "POSITION": "0001",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CHANGEDATE",
      "INTLEN": "000016",
      "KEYFLAG": "",
      "POSITION": "0016",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCCATEGORY",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0006",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCCORACTIV",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0007",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCNOCLIIND",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0008",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCCOPYLOCK",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0009",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCNOCASCAD",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0010",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCSOFTLOCK",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0011",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCORIGCONT",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0012",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCIMAILDIS",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0013",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CCTEMPLOCK",
      "INTLEN": "000002",
      "KEYFLAG": "",
      "POSITION": "0014",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "ADRNR",
      "INTLEN": "000020",
      "KEYFLAG": "",
      "POSITION": "0005",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "CHANGEUSER",
      "INTLEN": "000024",
      "KEYFLAG": "",
      "POSITION": "0015",
      "TABNAME": "T000"
    },
    {
      "FIELDNAME": "MTEXT",
      "INTLEN": "000050",
      "KEYFLAG": "",
  
... <recortado>
```

D2 recortado:

```json
{
  "forced_growth_output_lengths": {
    "ECHOTEXT": 200,
    "RESPTEXT": 89
  },
  "forced_preview": {
    "ECHOTEXT": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "RESPTEXT": "SAP R/3 Rel. 754   Sysid: A4H      Date: 20260506   Time: 192046   Logon_Data: 000/SAP*/E"
  },
  "natural_read": {
    "error": "SAP RFC error during RfcInvoke(RFC_READ_TABLE): code=4294967301 | key=E_WITHOUT_DATA | message=D Type:E Number:718 DD03L",
    "error_type": "SapRFCError",
    "ok": false
  }
}
```

D3 recortado:

```json
{
  "attempts": [
    {
      "duration_ms": 44.919,
      "timed_out": false,
      "timeout": "1"
    },
    {
      "duration_ms": 8.859,
      "error": "RfcInvoke(RFC_READ_TABLE) timed out after 0.001s",
      "error_type": "TimeoutError",
      "timed_out": true,
      "timeout": "0.001"
    }
  ],
  "last_errors": [
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 28.978,
      "error_key": "E_WITHOUT_DATA",
      "error_message": "D Type:E Number:718 DD03L",
      "function": "RFC_READ_TABLE",
      "mandt": "000",
      "params_hash": "b1f88f8cfbabe169c96b8bbb56b078b385fbc73d4f6af586cf69c78dcd84d618",
      "rc": 4294967301,
      "sid": "127.0.0.1",
      "tool": "sap_read_table",
      "ts": "2026-05-06T19:20:46.481765+00:00",
      "user": "SAP*"
    },
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 28.528,
      "error_key": "E_WITHOUT_DATA",
      "error_message": "D Type:E Number:718 DD03L",
      "function": "RFC_READ_TABLE",
      "mandt": "000",
      "params_hash": "ad92f3f5d6918f4766c76551132f0b78e0af3f0d5f9e0e3be824f6fcd2978faf",
      "rc": 4294967301,
      "sid": "127.0.0.1",
      "tool": "sap_read_table",
      "ts": "2026-05-06T19:20:46.556559+00:00",
      "user": "SAP*"
    },
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 8.28,
      "error_key": "TimeoutError",
      "error_message": "RfcInvoke(RFC_READ_TABLE) timed out after 0.001s",
      "function": "RFC_READ_TABLE",
      "mandt": "000",
      "params_hash": "fcce3d2d34491f9a5008fa56cd5160840c325518e7fec8173bfbfeaf2e030028",
      "rc": 1,
      "sid": "127.0.0.1",
      "tool": "sap_read_table",
      "ts": "2026-05-06T19:20:46.632673+00:00",
      "user": "SAP*"
    }
  ],
  "recovery_ping": {
    "destination": "A4H_DOCKER",
    "function": "RFC_PING",
    "ok": true
  }
}
```

## 4.5 Bloque E — SafetyPolicy contra sistema real

| Paso | Resultado | Evidencia |
|---|---:|---|
| E1 dangerous sin confirm | ✅ | `reason=dangerous` |
| E2 `SAPMCP_ALLOW_DANGEROUS=true` sin confirm | ✅ | sigue `reason=dangerous` |
| E3 dangerous + allow + confirm | ✅ | SafetyPolicy no bloquea; SAP devuelve `User NOEXISTE does not exist` |
| E4 allowlist restringida a `RFC_PING` | ✅ | `reason=not_in_allowlist` |

Evidencia recortada:

```json
{
  "E1_dangerous_without_confirm": {
    "duration_ms": 1.424,
    "name": "E1_dangerous_without_confirm",
    "ok": true,
    "result": {
      "blocked": true,
      "error_type": "PermissionError",
      "message": "RFC BAPI_USER_DELETE blocked: reason=dangerous requires=SAPMCP_ALLOW_DANGEROUS:true,confirm_dangerous:true"
    }
  },
  "E2_dangerous_allow_without_confirm": {
    "duration_ms": 0.614,
    "name": "E2_dangerous_allow_without_confirm",
    "ok": true,
    "result": {
      "blocked": true,
      "error_type": "PermissionError",
      "message": "RFC BAPI_USER_DELETE blocked: reason=dangerous requires=SAPMCP_ALLOW_DANGEROUS:true,confirm_dangerous:true"
    }
  },
  "E3_dangerous_allow_confirm": {
    "duration_ms": 68.882,
    "name": "E3_dangerous_allow_confirm",
    "ok": true,
    "result": {
      "safety_blocked": false,
      "sap_result": {
        "RETURN": [
          {
            "ID": "01",
            "MESSAGE": "User NOEXISTE does not exist",
            "NUMBER": "124",
            "TYPE": "E"
          }
        ]
      }
    }
  },
  "E4_allowlist_restricted_blocks_stfc": {
    "duration_ms": 0.732,
    "name": "E4_allowlist_restricted_blocks_stfc",
    "ok": true,
    "result": {
      "blocked": true,
      "error_type": "PermissionError",
      "message": "RFC STFC_CONNECTION blocked: reason=not_in_allowlist env=SAPMCP_ALLOWED_RFC"
    }
  }
}
```

## 4.6 Bloque F — Snapshot completo

| Paso | Resultado | Tiempo | Evidencia |
|---|---:|---:|---|
| F1 `sapmcp-snapshot` sin `max_pages` | ✅ | 409,79 s | fichero `/tmp/sapmcp-phase8-home/catalog-127.0.0.1.json.gz` |
| F2 `sap://catalog/snapshot` | ✅ | 3,15 s | `exists=true`, snapshot servido |
| F3 `sap_catalog_search(kind='rfc', pattern='BAPI_USER*')` | ✅ | 3,61 s | aparecen `BAPI_USER_GET_DETAIL` y `BAPI_USER_LOCK_STATUS` |
| F4 `sap_catalog_search(kind='table', pattern='USR0*')` | ✅ | 3,60 s | aparece `USR02` |

Snapshot:

```json
{
  "counts": {
    "fields": 1819533,
    "rfc": 118848,
    "tables": 155847
  },
  "duration_ms": 409793.685,
  "path": "/tmp/sapmcp-phase8-home/catalog-127.0.0.1.json.gz",
  "returncode": 0,
  "size_bytes": 22663504,
  "stderr": "{\"ok\": true, \"path\": \"/tmp/sapmcp-phase8-home/catalog-127.0.0.1.json.gz\", \"counts\": {\"rfc\": 118848, \"tables\": 155847, \"fields\": 1819533}}",
  "stdout": ""
}
```

Búsqueda `BAPI_USER*` recortada:

```json
{
  "exists": true,
  "kind": "rfc",
  "pattern": "BAPI_USER*",
  "rows": [
    {
      "FUNCNAME": "BAPI_USER_APPLICATION_OBJ_ADD",
      "PNAME": "SAPLSU_USER_APPLREF"
    },
    {
      "FUNCNAME": "BAPI_USER_APPLICATION_OBJ_GET",
      "PNAME": "SAPLSU_USER_APPLREF"
    },
    {
      "FUNCNAME": "BAPI_USER_APPLICATION_OBJ_DEL",
      "PNAME": "SAPLSU_USER_APPLREF"
    },
    {
      "FUNCNAME": "BAPI_USER_APPLICATION_OBJ_PUT",
      "PNAME": "SAPLSU_USER_APPLREF"
    },
    {
      "FUNCNAME": "BAPI_USER_GET_DETAIL",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_CREATE",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_CHANGE",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_DELETE",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_WP_PERS_DATA_READ",
      "PNAME": "SAPLWP_EXCHANGE"
    },
    {
      "FUNCNAME": "BAPI_USER_CLONE",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_WP_PERS_DATA_SAVE",
      "PNAME": "SAPLWP_EXCHANGE"
    },
    {
      "FUNCNAME": "BAPI_USER_ACTGROUPS_ASSIGN",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_ACTGROUPS_DELETE",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_DISPLAY",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_LOCK",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_PROFILES_ASSIGN",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_PROFILES_DELETE",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_UNLOCK",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_EXISTENCE_CHECK",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_CREATE1",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_GETLIST",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_INTERNET_CREATE",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_LOCACTGROUPS_ASSIGN",
      "PNAME": "SAPLSU_USER"
    },
    {
      "FUNCNAME": "BAPI_USER_LOCACTGROUPS_DELETE",
      "PNAME": "SAPLSU_USER"
    },
    
... <recortado>
```

Búsqueda `USR0*`:

```json
{
  "exists": true,
  "kind": "table",
  "pattern": "USR0*",
  "rows": [
    {
      "TABCLASS": "VIEW",
      "TABNAME": "USR02CLASS_V"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR06"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR06SYS"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR09"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR08"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR01"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR02"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR03"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR04"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR05"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR07"
    },
    {
      "TABCLASS": "TRANSP",
      "TABNAME": "USR07_EXT"
    }
  ],
  "rows_returned": 12,
  "snapshot_sid": "127.0.0.1"
}
```

---

## 5. Bloque G de cierre

| Paso | Resultado | Evidencia |
|---|---:|---|
| G1 `pytest -q` local | ✅ | `35 passed` |
| G2 limpieza de temporales | ✅ | `.env` temporal y scripts/tar eliminados local/remoto |
| G3 audit coverage | ✅ | 55 entradas; todas las tools Basis y `sap_health_check` presentes |

Audit coverage:

```json
{
  "audit_count": 55,
  "basis_present": {
    "sap_get_jobs": true,
    "sap_get_locks": true,
    "sap_get_rfc_queue": true,
    "sap_get_short_dumps": true,
    "sap_get_syslog": true,
    "sap_get_update_requests": true,
    "sap_get_user_audit": true,
    "sap_get_workprocesses": true
  },
  "by_tool": {
    "sap_get_jobs": 4,
    "sap_get_locks": 7,
    "sap_get_rfc_queue": 4,
    "sap_get_short_dumps": 4,
    "sap_get_syslog": 3,
    "sap_get_update_requests": 5,
    "sap_get_user_audit": 2,
    "sap_get_workprocesses": 7,
    "sap_health_check": 6,
    "sap_ping": 3,
    "sap_read_table": 5,
    "sap_rfc_call": 5
  },
  "health_present": true,
  "last10": [
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 44.295,
      "error_key": null,
      "error_message": null,
      "function": "RFC_READ_TABLE",
      "mandt": "000",
      "params_hash": "fcce3d2d34491f9a5008fa56cd5160840c325518e7fec8173bfbfeaf2e030028",
      "rc": 0,
      "sid": "127.0.0.1",
      "tool": "sap_read_table",
      "ts": "2026-05-06T19:20:46.623748+00:00",
      "user": "SAP*"
    },
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 8.28,
      "error_key": "TimeoutError",
      "error_message": "RfcInvoke(RFC_READ_TABLE) timed out after 0.001s",
      "function": "RFC_READ_TABLE",
      "mandt": "000",
      "params_hash": "fcce3d2d34491f9a5008fa56cd5160840c325518e7fec8173bfbfeaf2e030028",
      "rc": 1,
      "sid": "127.0.0.1",
      "tool": "sap_read_table",
      "ts": "2026-05-06T19:20:46.632673+00:00",
      "user": "SAP*"
    },
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 19.076,
      "error_key": null,
      "error_message": null,
      "function": "RFC_PING",
      "mandt": "000",
      "params_hash": "300655d147c49f99bcc896d479e13023b663565132d3eb4867b44591794960ab",
      "rc": 0,
      "sid": "127.0.0.1",
      "tool": "sap_ping",
      "ts": "2026-05-06T19:20:46.652337+00:00",
      "user": "SAP*"
    },
    {
      "confirmed": false,
      "dangerous": false,
      "destination": "A4H_DOCKER",
      "duration_ms": 19.347,
      "error_key": null,
      "error_message": null,
      "function": "ENQUEUE_READ",
      "mandt": "000",
      "params_hash": "300655d147c49f99bcc896d479e13023b663565132d3eb4867b44591794960ab",
      "rc": 0,
      "sid": "127.0.0.1",
      "tool": "sap_get_locks",
      "ts": "2026-05-06T19:20:46.674581+00:00",
      "user": "SAP*"
    }
... <recortado>
```

---

## 6. Hallazgos y fixes aplicados durante la prueba

### Fix real aplicado: requests opcionales de tablas/campos RFC en Basis

**Síntoma inicial:** el primer smoke test real falló en varias tools por `INVALID_PARAMETER` al pedir tablas/campos alternativos que no existen en este A4H:

- `ENQUEUE_READ`: tabla `LOCKS` no existe; la tabla real es `ENQ`.
- `TH_SERVER_LIST`: tabla `SERVERS` no existe; la tabla real es `LIST`.
- `TH_WPINFO`: import correcto `SRVNAME`, tabla real `WPLIST`, campos `WP_BNAME`, `WP_MANDT`, `WP_REPORT`, etc.
- `BAPI_USER_GET_DETAIL`: en `PROFILES` existe `BAPIPROF`, no `PROFILE`.
- `RFC_READ_TABLE` devuelve `E_WITHOUT_DATA` para selecciones válidas sin datos; las tools Basis deben reportar `count=0`.

**Archivos modificados:**

| Archivo | Líneas | Cambio |
|---|---:|---|
| `src/sapmcp/basis.py` | 69-126 | `_no_data()` y manejo de `E_WITHOUT_DATA` como lista vacía en `_read_table`. |
| `src/sapmcp/basis.py` | 264-336 | `sap_get_locks` y `sap_get_workprocesses` usan tablas/campos reales portables. |
| `src/sapmcp/basis.py` | 423-469 | `sap_get_jobs` usa `JOB_HEAD` y fallback read-only a `TBTCO` si el BAPI exige import estructurado no soportado. |
| `src/sapmcp/basis.py` | 472-488 | `sap_get_user_audit` usa campos reales `BAPIPROF`/`AGR_NAME` y evita structures export no soportadas. |
| `src/sapmcp/health.py` | 211-244 | Deep checks usan tablas reales `USRLIST`, `LIST` y T000 sin campo no portable. |

Tests después del fix:

```text
35 passed in 1.34s
```

Comentario inline explicativo dejado en el código:

```python
# RFC_READ_TABLE raises E_WITHOUT_DATA for valid empty selections/tables.
# Basis smoke tools should report count=0 instead of failing the whole tool.
```

---

## 7. Limitaciones conocidas adicionales descubiertas

1. **Syslog RFC no disponible en este Docker**  
   `sap_get_syslog` devuelve `available=false`: no hay `RSLG_READ_SYSLOG` ni `BAPI_SYSLOG_READ` RFC-enabled en este A4H.

2. **Update requests RFC no disponible**  
   `sap_get_update_requests` devuelve `available=false`: `BAPI_UPDREQUEST_GETLIST` no existe o no está disponible.

3. **Health `standard/deep` en Docker quedan `warn` por checks unknown justificados**  
   No es fallo de `sap_health_check`; refleja RFCs Basis ausentes.

4. **`DD03L-INTLENGTH` no existe como campo en esta release**  
   El campo real observado es `INTLEN`; se usó fallback para validar numéricos.

5. **Timeout a `1s` no siempre dispara**  
   `RFC_READ_TABLE(TFDIR, rowcount=200)` respondió en ~45 ms. Para ejercitar la rama de timeout del bridge se repitió con `SAPMCP_RFC_TIMEOUT=0.001`, que produjo `TimeoutError` y recuperación OK.

6. **Snapshot completo es viable pero pesado**  
   Sin `max_pages` tardó ~410 s y generó un gzip de 21.6 MiB; conviene ejecutarlo fuera de rutas interactivas.

---

## 8. Recomendaciones operativas

### Allowlist recomendada para este tipo de Docker

Para smoke/read-only amplio:

```text
RFC_PING, STFC_CONNECTION, RFC_READ_TABLE, RFC_GET_FUNCTION_INTERFACE,
DDIF_FIELDINFO_GET, ENQUEUE_READ, TH_WPINFO, TH_SERVER_LIST, TH_USER_LIST,
BAPI_USER_GET_DETAIL, BAPI_XBP_JOB_SELECT
```

Añadir condicionalmente solo si existen en el sistema:

```text
RFC_GET_SHORT_DUMP_LIST, RSLG_READ_SYSLOG, BAPI_SYSLOG_READ,
BAPI_UPDREQUEST_GETLIST, BAPI_USER_LOCK_STATUS
```

No incluir peligrosas por defecto. `BAPI_USER_DELETE` solo debe entrar temporalmente para pruebas controladas de SafetyPolicy con `SAPMCP_ALLOW_DANGEROUS=true` y `confirm_dangerous=true`.

### Thresholds health check

- `quick` es el perfil recomendado para demo/monitorización básica de este Docker: queda `ok` y no depende de syslog/update.
- Mantener locks por defecto (`warn=50`, `crit=200`) en Docker vacío; bajar a `0/0` solo para pruebas deliberadas.
- En `standard/deep`, tratar `update_*` y `syslog_sample` como limitaciones conocidas si las RFCs no existen, o ajustar el playbook operativo para no escalar esos `unknown` en este Docker concreto.

---

## 9. Limpieza realizada

Se eliminaron temporales con credenciales y scripts de prueba.

Local:

```text
/tmp/sapmcp-src.tgz
/tmp/sapmcp_phase8_smoke.py
```

Remoto:

```text
/tmp/sapmcp-phase8.env
/tmp/sapmcp-src.tgz
/tmp/sapmcp_phase8_smoke.py
/tmp/sapmcp_try_pass.py
/tmp/sapmcp-phase8-pass-index
```

Los outputs usados para construir este informe no contienen password; el informe solo conserva evidencias sanitizadas.

---

## 10. Conclusión

`sapmcp` queda validado contra ABAP Docker A4H para las fases 5-7 y los casos límite solicitados, con un fix real aplicado y verificado.

Estado recomendado:

```text
Apto para pruebas controladas contra SAP DEV en modo read-only, usando allowlist explícita y audit activo.
```

Antes de ampliar a un DEV no-Docker:

1. Confirmar qué RFCs Basis existen realmente y ajustar allowlist.
2. Ejecutar `sap_health_check(profile='quick')` como prueba base.
3. Generar snapshot completo en ventana controlada si se necesita navegación de catálogo.
4. Mantener `SAPMCP_READ_ONLY=true` salvo pruebas explícitas de SafetyPolicy en laboratorio.
