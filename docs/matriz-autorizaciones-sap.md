# Matriz de autorizaciones SAP para sapmcp

**Audiencia:** SAP Basis, SAP Security, arquitectura de integración, auditoría interna y equipos de preventa técnica.  
**Objetivo:** ofrecer una primera matriz de análisis para construir roles PFCG de mínimo privilegio alrededor de las RFC/BAPI que usa `sapmcp`.

> **Importante:** esta matriz no es un rol SAP listo para transportar ni sustituye el análisis de autorizaciones del sistema cliente. Los objetos listados son **probables** y deben validarse en cada release, mandante y configuración mediante `SU53`, `ST01` o `STAUTHTRACE`, además de revisión en `PFCG`/`SU24`/`SU21`.

---

## Principios de lectura

1. `S_RFC` es el control base para ejecutar módulos de función remotos. Según release/parámetro de seguridad RFC, el valor puede mantenerse a nivel de **grupo de funciones** (`RFC_TYPE=FUGR`) o, en configuraciones más estrictas, a nivel de **módulo de función** (`RFC_TYPE=FUNC`). No usar comodines amplios sin aprobación de Security.
2. `S_RFC` rara vez es suficiente por sí solo: algunas funciones hacen comprobaciones adicionales de Basis, tablas, batch o administración de usuarios.
3. `RFC_READ_TABLE` merece tratamiento especial: aunque sea lectura, puede exponer datos técnicos, maestros o transaccionales. En PRD debe evitarse o sustituirse por Z-RFCs read-only tipadas.
4. Las recomendaciones DEV/QAS/PRD asumen `SAPMCP_READ_ONLY=true`, auditoría JSONL activa, usuarios técnicos separados por entorno y sin `SAP_ALL`/`SAP_NEW`.

---

## Matriz por RFC/BAPI

| Superficie sapmcp | RFC/BAPI usada | Transacción mental equivalente | Objeto de autorización probable | Riesgo principal | Recomendación DEV/QAS/PRD |
| --- | --- | --- | --- | --- | --- |
| `sap_ping` | `RFC_PING` | Test de conectividad RFC / SM59 | `S_RFC` con `ACTVT=16` para la función o grupo correspondiente, normalmente técnico/base (`SYST`/equivalente según sistema). | Bajo: confirma disponibilidad, SID/mandante indirectamente por auditoría. | **DEV:** permitir. **QAS:** permitir. **PRD:** permitir como smoke test controlado. |
| `sap_health_check` ping interno | `STFC_CONNECTION` | SM59 → Connection Test / prueba eco | `S_RFC` para la función o grupo de test estándar. | Bajo: eco técnico, puede revelar latencia y conectividad. | **DEV:** permitir. **QAS:** permitir. **PRD:** permitir si se acepta monitorización básica. |
| `sap_read_table`, catálogo, fallbacks Basis, snapshot | `RFC_READ_TABLE` | SE16/SE16N/SE17 mental, lectura genérica de tabla | `S_RFC` para `RFC_READ_TABLE`; además controles de tabla como `S_TABU_DIS`, `S_TABU_NAM`, `S_TABU_CLI` y `ACTVT=03` cuando apliquen. | Alto: lectura genérica de tablas; posible exposición de datos personales, financieros, usuarios, roles, custom Z, dumps, colas y jobs. | **DEV:** permitir con `SAPMCP_MAX_ROWS` bajo y tablas no sensibles. **QAS:** solo allowlist de tablas/casos. **PRD:** evitar; preferir Z-RFCs tipadas y certificadas. |
| `sap_describe_rfc`, resource de interfaz | `RFC_GET_FUNCTION_INTERFACE` | SE37 → Display interface | `S_RFC` para la función/grupo; posibles controles de diccionario/desarrollo según release y hardening. | Medio: expone nombres de módulos, parámetros, estructuras y superficie técnica. | **DEV:** permitir para exploración. **QAS:** permitir con allowlist. **PRD:** limitar a RFCs certificadas o usar snapshot offline. |
| resource `sap://table/{name}/schema` | `DDIF_FIELDINFO_GET` | SE11/SE12 → Display fields | `S_RFC`; posibles controles DDIC/display según configuración; revisar trazas. | Medio: expone modelo de datos, campos sensibles y objetos Z. | **DEV:** permitir. **QAS:** limitar a tablas necesarias. **PRD:** usar cache/snapshot aprobado o Z-RFCs que devuelvan solo metadata necesaria. |
| `sap_get_short_dumps` | `RFC_GET_SHORT_DUMP_LIST` | ST22 | `S_RFC`; posibles objetos Basis/administración de sistema según release, por ejemplo familias de autorización de monitorización/admin. | Alto: dumps pueden contener usuarios, programas, select-options, mensajes de error, datos de negocio o trazas técnicas. | **DEV:** permitir. **QAS:** permitir a Basis. **PRD:** restringir a Basis/SRE; devolver resúmenes y no dumps completos salvo incidente aprobado. |
| `sap_get_syslog` | `RSLG_READ_SYSLOG` / `BAPI_SYSLOG_READ` | SM21 | `S_RFC`; posibles objetos de administración/monitorización de sistema. Validar con `STAUTHTRACE`. | Alto: syslog revela hosts, usuarios, mandantes, errores de seguridad, rutas e infraestructura. | **DEV:** permitir. **QAS:** permitir con ventana temporal. **PRD:** restringir; usar ventana corta, filtros de severidad y auditoría. |
| `sap_get_locks` | `ENQUEUE_READ` | SM12 | `S_RFC`; posibles autorizaciones de monitorización/enqueue según release. | Medio: expone objetos bloqueados, usuarios, transacciones y patrones operativos. | **DEV:** permitir. **QAS:** permitir. **PRD:** permitir solo como diagnóstico Basis con límites y filtros. |
| `sap_get_workprocesses` | `TH_WPINFO` | SM50/SM66 | `S_RFC`; posibles autorizaciones de administración/monitorización técnica. | Medio/alto: usuarios activos, programas, tiempos, tablas y estado de workprocesses. | **DEV:** permitir. **QAS:** permitir a Basis. **PRD:** restringir; considerar redacción/agrupación para dirección. |
| `sap_get_workprocesses`, health `deep` | `TH_SERVER_LIST` | SM51 / lista de instancias | `S_RFC`; posibles permisos de monitorización técnica. | Medio: revela landscape, nombres de instancia/host y topología. | **DEV:** permitir. **QAS:** permitir. **PRD:** permitir solo si arquitectura acepta exposición controlada. |
| health `deep`, auditoría operativa | `TH_USER_LIST` | SM04/AL08 mental | `S_RFC`; posibles permisos de monitorización de usuarios/sesiones. | Alto: usuarios conectados, mandantes, terminales, transacciones. Puede ser dato personal/operativo. | **DEV:** permitir. **QAS:** restringir. **PRD:** evitar detalle por defecto; preferir conteos agregados o aprobación Security. |
| `sap_get_update_requests` | `BAPI_UPDREQUEST_GETLIST` | SM13 | `S_RFC`; posibles objetos Basis para update requests/monitorización. | Alto: programas de negocio, usuarios, módulos update, errores pendientes. | **DEV:** permitir. **QAS:** permitir para smoke y pre-go-live. **PRD:** restringir a Basis con ventanas y filtros. |
| `sap_get_jobs` | `BAPI_XBP_JOB_SELECT` | SM37 / XBP | `S_RFC` para XBP/SXBP; objetos batch como `S_BTCH_JOB` (`SHOW`, `LIST`, `PROT` según necesidad), evitar `S_BTCH_ADM=Y` salvo rol admin; revisar `S_BTCH_NAM` si se consulta por usuarios. | Medio/alto: nombres de jobs, usuarios, horarios, estado de procesos críticos. | **DEV:** permitir. **QAS:** permitir con filtros. **PRD:** mínimo privilegio, sin administración batch, solo display/listado aprobado. |
| `sap_get_user_audit` | `BAPI_USER_GET_DETAIL` | SU01/SUIM display | `S_RFC`; objetos de administración de usuarios como `S_USER_GRP`, `S_USER_AGR`, `S_USER_PRO` o equivalentes según checks reales. | Muy alto: roles, perfiles, vigencia, grupos de usuarios, presencia de `SAP_ALL`. | **DEV:** permitir a Security/Basis. **QAS:** restringir a usuarios de prueba o auditoría. **PRD:** solo Security, caso auditado y con aprobación humana. |
| `sap_get_user_audit` | `BAPI_USER_LOCK_STATUS` | SU01 → estado de bloqueo | `S_RFC`; posibles checks de usuario/grupo similares a `BAPI_USER_GET_DETAIL`. | Medio/alto: estado de seguridad de cuentas, bloqueos y fallos de logon. | **DEV:** permitir. **QAS:** restringir. **PRD:** solo Security/Basis y salida mínima necesaria. |

---

## Reglas de oro para Security

- No conceder `S_RFC` con `RFC_NAME=*` a usuarios técnicos de `sapmcp` en QAS/PRD.
- Evitar que `RFC_READ_TABLE` sea el mecanismo principal en PRD. Si se permite temporalmente, limitar por usuario, tabla, actividad `03`, filas y ventana de uso.
- Preferir `S_TABU_NAM` para control por tabla cuando el release/proceso del cliente lo soporte; usar `S_TABU_DIS` solo con grupos acotados.
- No usar `SAP_ALL`, `SAP_NEW`, `S_BTCH_ADM=Y` ni roles Basis amplios salvo laboratorio aislado.
- Separar usuarios y roles por entorno: `RFC_SAPMCP_DEV`, `RFC_SAPMCP_QAS`, `RFC_SAPMCP_PRD`.
- Activar trazas de autorización durante smoke tests y documentar cada ampliación de rol con evidencia.

---

## Validación recomendada

1. Crear usuario técnico por entorno sin roles amplios.
2. Asignar solo `S_RFC` para `RFC_PING`/`STFC_CONNECTION`.
3. Ejecutar smoke test mínimo desde `sapmcp`.
4. Activar `STAUTHTRACE` o `ST01` para el usuario técnico.
5. Ejecutar cada tool candidata con datos no sensibles.
6. Revisar fallos `SU53` y trazas, no inferir autorizaciones por nombre.
7. Ajustar rol en `PFCG`, regenerar perfil y repetir.
8. Aprobar con SAP Security antes de QAS/PRD.

---

## Referencias oficiales útiles

- SAP Help — [Authorization Object S_RFC](https://help.sap.com/saphelp_em900/helpdata/en/48/8d1bd1ae444e6ee10000000a421937/content.htm).
- SAP Help — [RFC Authorizations](https://help.sap.com/doc/saphelp_nw74/7.4.16/en-US/48/95128d94cc73eae10000000a42189b/content.htm).
- SAP Help — [Table Maintenance: S_TABU_DIS, S_TABU_NAM, S_TABU_CLI](https://help.sap.com/docs/PRODUCT_ID/fd3c83ed48684640a18ac05c8ae4d016/e50e0edcd9c54144b5b614c4ba27204d.html).
- SAP Help — [Authorization Trace in ST01](https://help.sap.com/docs/SUPPORT_CONTENT/sapdms/3363505806.html).
- SAP Help — [STAUTHTRACE, SU53 and SLG1](https://help.sap.com/docs/SUPPORT_CONTENT/datasphere/4518522125.html).
