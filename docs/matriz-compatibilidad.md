# Matriz de compatibilidad SAP para sapmcp

**Objetivo:** documentar el estado de compatibilidad esperado/validado de `sapmcp` por plataforma SAP sin afirmar soporte no probado.

> `sapmcp` usa SAP NetWeaver RFC SDK y RFCs/BAPIs ABAP clásicas. La compatibilidad real depende de release SAP_BASIS, perfil de seguridad RFC, disponibilidad de funciones estándar, licencia, red, SAProuter/SNC, roles PFCG y configuración del cliente.

---

## Leyenda de estado

| Estado | Significado |
| --- | --- |
| **Validado** | Probado en un entorno concreto y documentado en este repositorio. |
| **Validado parcial** | Probado para un subconjunto de tools o con restricciones de laboratorio. |
| **Esperado** | Técnicamente razonable por uso de RFC/BAPI estándar, pero no probado aún en ese release cliente. |
| **Pendiente** | Requiere smoke test, permisos o diseño adicional antes de afirmarlo. |
| **No aplicable** | El modelo técnico actual no encaja directamente con esa plataforma o requiere otra integración. |

---

## Matriz resumida

| Plataforma | Estado | Conectividad RFC SDK | Tools Basis estándar | `RFC_READ_TABLE` | Z-RFC companion | Notas |
| --- | --- | --- | --- | --- | --- | --- |
| SAP ECC 6.0 | **Esperado / pendiente de validación cliente** | Esperado si el sistema acepta RFC externo y el SDK es compatible. | Esperado para funciones disponibles en el release, con posibles diferencias de interfaz. | Esperado, pero sujeto a autorización y restricciones de tabla. | Recomendado para PRD. | Requiere smoke test por SAP_BASIS/EHP y roles PFCG. |
| SAP S/4HANA 1909 | **Esperado / pendiente de validación cliente** | Esperado. | Esperado para Basis/monitorización clásica; validar cada BAPI/RFC. | Esperado con restricciones. | Recomendado. | No asumir que todos los fallbacks de tablas son aceptables en PRD. |
| SAP S/4HANA 2020+ | **Esperado / pendiente de validación cliente** | Esperado. | Esperado, con mayor probabilidad de hardening RFC/autorizaciones. | Posible, pero enterprise debe limitarlo. | Muy recomendado. | Validar `auth/rfc_authority_check`, SNC y restricciones de seguridad modernas. |
| ABAP Platform Trial / A4H | **Validado parcial** | Validado en laboratorio ABAP Docker/A4H según documentación del repo. | Validado parcial para smoke tests de multi-destination, Basis, health check, SafetyPolicy y snapshot. | Validado parcial para tablas de prueba/técnicas. | Pendiente. | No extrapolar permisos de laboratorio (`SAP*`, mandante `000`) a cliente. |
| BTP ABAP Environment | **No aplicable / pendiente de arquitectura alternativa** | El enfoque actual de SAP NetWeaver RFC SDK y RFCs clásicos no debe asumirse aplicable. | No aplicable sin rediseño. | No aplicable como patrón recomendado. | Requiere diseño específico. | Evaluar APIs liberadas, RAP/OData, Communication Arrangements y restricciones ABAP Cloud. |

---

## Smoke test mínimo por nueva plataforma

1. Verificar SAP NetWeaver RFC SDK correcto para el sistema operativo donde corre `sapmcp`.
2. Probar `sap_ping` (`RFC_PING`).
3. Probar `STFC_CONNECTION` mediante `sap_health_check(profile="quick")`.
4. Probar `sap_describe_rfc("STFC_CONNECTION")` si `RFC_GET_FUNCTION_INTERFACE` está autorizado.
5. Probar `DDIF_FIELDINFO_GET` con una tabla técnica no sensible.
6. Probar una lectura limitada de `T000` solo en DEV/QAS o con aprobación explícita.
7. Probar cada tool Basis incluida en alcance: dumps, syslog, locks, workprocesses, updates, jobs, usuario audit.
8. Capturar fallos con `SU53`/`ST01`/`STAUTHTRACE` y ajustar roles.
9. Documentar versión SAP_BASIS, SID/mandante no sensible, perfil de seguridad RFC y resultado.

---

## Criterios para cambiar estado a “Validado”

Un entorno solo debería marcarse como validado cuando exista evidencia de:

- versión SAP y SAP_BASIS;
- sistema operativo y versión del SAP NetWeaver RFC SDK;
- usuario técnico y rol PFCG revisado;
- listado de tools probadas;
- resultados de `pytest -q` local para el repo;
- smoke test real contra SAP;
- limitaciones conocidas;
- aprobación de Basis/Security para el alcance.

---

## Riesgos de compatibilidad conocidos

- Diferencias de interfaz o disponibilidad de RFC/BAPI por release.
- `RFC_READ_TABLE` limitado por ancho de línea, tipos de datos y políticas de seguridad.
- Autorizaciones RFC a nivel de grupo frente a función según configuración.
- SAProuter/SNC/firewalls entre contenedor/host MCP y SAP.
- Funciones Basis que devuelven estructuras diferentes en ECC frente a S/4HANA.
- BTP ABAP Environment orientado a APIs liberadas y modelo ABAP Cloud, no a RFC clásico genérico.

---

## Evidencia local existente

- [`docs/sapmcp-abap-docker-validation-2026-05-06.md`](sapmcp-abap-docker-validation-2026-05-06.md)
- [`docs/sapmcp-abap-docker-validation-fase8-20260506.md`](sapmcp-abap-docker-validation-fase8-20260506.md)
