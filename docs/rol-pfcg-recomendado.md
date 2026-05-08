# Rol PFCG recomendado para sapmcp

**Audiencia:** SAP Security, Basis, GRC, propietarios de plataforma y responsables de piloto cliente.  
**Objetivo:** definir una estrategia prudente para construir roles PFCG de `sapmcp` por entorno sin convertir esta guía en una receta dogmática de objetos exactos.

> Esta guía propone un punto de partida. En SAP, los checks reales dependen de release, componentes instalados, parámetros de seguridad RFC, exits/enhancements, notas aplicadas y configuración cliente. Todo debe validarse con `SU53`, `ST01`, `STAUTHTRACE`, revisión de `PFCG` y aprobación de Security.

---

## Roles propuestos

| Rol | Uso previsto | Postura de seguridad |
| --- | --- | --- |
| `Z_SAPMCP_READ_DEV` | Desarrollo, laboratorio, demos técnicas con datos no productivos. | Más flexible, permite exploración controlada de RFCs y tablas técnicas. |
| `Z_SAPMCP_READ_QAS` | Pruebas integradas, validación pre-piloto, smoke tests de operación. | Allowlist explícita de RFCs/tablas y límites de lectura. |
| `Z_SAPMCP_READ_PRD` | Producción o piloto con datos reales. | Mínimo estricto: RFCs certificadas, preferencia por Z-RFCs read-only, sin lectura genérica libre. |

Usuarios técnicos sugeridos:

| Entorno | Usuario técnico sugerido | Rol sugerido |
| --- | --- | --- |
| DEV | `RFC_SAPMCP_DEV` | `Z_SAPMCP_READ_DEV` |
| QAS | `RFC_SAPMCP_QAS` | `Z_SAPMCP_READ_QAS` |
| PRD | `RFC_SAPMCP_PRD` | `Z_SAPMCP_READ_PRD` |

---

## Principio de mínimo privilegio

1. **Separación por entorno:** no reutilizar el mismo usuario ni el mismo rol entre DEV, QAS y PRD.
2. **Sin privilegios globales:** no usar `SAP_ALL`, `SAP_NEW`, `S_RFC=*`, `S_TABU_DIS=*` ni permisos batch/admin amplios.
3. **Solo lectura:** mantener `SAPMCP_READ_ONLY=true` y `SAPMCP_ALLOW_DANGEROUS=false`.
4. **Allowlist defensiva:** usar `SAPMCP_ALLOWED_RFC` en QAS/PRD para reducir la superficie expuesta aunque SAP autorizase más de lo necesario.
5. **Control de tablas:** para `RFC_READ_TABLE`, preferir `S_TABU_NAM` por tabla cuando sea viable, con `ACTVT=03`, y evitar tablas de negocio o seguridad no justificadas.
6. **Evidencia de autorizaciones:** cada ampliación del rol debe tener trazabilidad: tool ejecutada, error recibido, objeto fallido, justificación y aprobador.

---

## Contenido orientativo por rol

### `Z_SAPMCP_READ_DEV`

Objetivo: permitir que Basis/DevOps explore el sistema sin bloquear el diseño del piloto.

- `S_RFC` para conectividad y metadata: `RFC_PING`, `STFC_CONNECTION`, `RFC_GET_FUNCTION_INTERFACE`, `DDIF_FIELDINFO_GET`.
- `S_RFC` para Basis read-only usadas por sapmcp: dumps, syslog, enqueue, task handler, updates, XBP jobs y BAPIs de usuario según necesidad.
- Acceso de tabla display (`ACTVT=03`) solo a tablas técnicas necesarias para demos: por ejemplo catálogo RFC/DDIC, `T000`, colas RFC y tablas Basis usadas por fallbacks.
- Puede permitir `RFC_READ_TABLE` con límites bajos y datos no sensibles.
- Debe seguir sin permisos de cambio ni administración amplia.

### `Z_SAPMCP_READ_QAS`

Objetivo: validar el piloto en condiciones parecidas a cliente sin abrir lectura genérica.

- `S_RFC` solo para RFC/BAPI aprobadas en la matriz de autorizaciones.
- `RFC_READ_TABLE` solo si hay casos de uso aprobados y tablas allowlisted.
- Jobs: permisos display/list/protocol estrictamente necesarios; evitar permisos de scheduling/release/delete.
- Usuario audit: limitar a usuarios de prueba o casos de auditoría aprobados.
- Ejecutar smoke tests documentados y adjuntar trazas de autorización.

### `Z_SAPMCP_READ_PRD`

Objetivo: operación consultiva y monitorización segura con datos reales.

- Preferir Z-RFCs read-only tipadas (`Z_SAPMCP_*`) revisadas por ABAP/Security.
- Allowlist de RFCs productivas mínima: conectividad, health check y monitorización aprobada.
- Evitar `RFC_READ_TABLE` libre. Si se aprueba una excepción temporal, debe tener caducidad, tabla/uso concreto, logging y owner de negocio.
- No exponer detalle de usuarios activos, roles o dumps completos a LLMs no aprobados.
- Requerir aprobación humana para cualquier operación que pueda influir decisiones productivas.

---

## Proceso recomendado para construir el rol

1. **Crear usuario técnico sin roles amplios.**
   - Tipo comunicación/sistema según política interna.
   - Password en vault/keyring, no en documentación ni repositorio.
2. **Asignar permisos mínimos iniciales.**
   - Conectividad: `RFC_PING`, `STFC_CONNECTION`.
   - Sin `RFC_READ_TABLE` al inicio salvo DEV.
3. **Configurar sapmcp en modo restrictivo.**
   - `SAPMCP_READ_ONLY=true`.
   - `SAPMCP_ALLOW_DANGEROUS=false`.
   - `SAPMCP_MAX_ROWS` bajo.
   - `SAPMCP_ALLOWED_RFC` explícito en QAS/PRD.
4. **Ejecutar smoke tests controlados.**
   - `sap_ping(destination=...)`.
   - `sap_describe_rfc("STFC_CONNECTION")` si procede.
   - `sap_health_check(profile="quick")`.
   - Una tool Basis cada vez: locks, jobs, syslog, dumps, usuario audit, según alcance aprobado.
5. **Capturar fallos de autorización.**
   - `SU53` inmediatamente tras el fallo.
   - `ST01` o `STAUTHTRACE` para trazas por usuario y todos los application servers.
   - Registrar objeto, campo, valor, tool y justificación funcional.
6. **Ajustar en PFCG.**
   - Añadir solo el objeto/valor necesario.
   - Regenerar perfil.
   - Repetir smoke test.
7. **Aprobar con Security.**
   - Adjuntar matriz de autorización final.
   - Adjuntar logs de smoke test.
   - Definir owner, caducidad de excepciones y revisión periódica.

---

## Smoke tests sugeridos por entorno

| Entorno | Smoke test mínimo | Criterio de aceptación |
| --- | --- | --- |
| DEV | Ping, describe RFC, schema DDIC, lectura `T000`, health `quick`, una tool Basis por categoría. | Sin permisos de cambio; errores de autorización documentados y resueltos. |
| QAS | Ping, health `quick/standard`, jobs o syslog si están en alcance, una Z-RFC de ejemplo. | Todas las RFC en allowlist; ninguna lectura libre no justificada. |
| PRD | Ping, health `quick`, Z-RFCs certificadas, audit tail local. | Cero comodines amplios; output mínimo; aprobado por Security/Basis. |

---

## Evidencia mínima para aprobación

- Nombre del usuario técnico y mandante.
- Rol PFCG asignado y versión.
- Lista final de RFC/BAPI autorizadas.
- Lista final de tablas autorizadas, si existe `RFC_READ_TABLE`.
- Extracto de `STAUTHTRACE`/`ST01` que muestre checks relevantes.
- Configuración `sapmcp` sanitizada (`sap_config_status`, sin secretos).
- Confirmación de que `SAPMCP_ALLOW_DANGEROUS=false` en QAS/PRD.
- Decisión formal sobre uso de LLM local/on-prem/cloud privado aprobado.
