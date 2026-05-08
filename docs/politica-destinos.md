# Política recomendada por destino DEV/QAS/PRD

**Objetivo:** definir el modelo de gobierno por entorno para `sapmcp` sin cambiar todavía la lógica runtime crítica del servidor.

> Estado actual del código: `sapmcp` dispone de `SafetyPolicy` global basada en variables como `SAPMCP_READ_ONLY`, `SAPMCP_ALLOWED_RFC`, `SAPMCP_ALLOW_DANGEROUS` y `SAPMCP_MAX_ROWS`. Este documento propone la convención futura por destino; no implementa aún enforcement por destino.

---

## Modelo operativo recomendado

| Entorno | Perfil | Uso permitido | Política recomendada |
| --- | --- | --- | --- |
| DEV | Flexible controlado | Exploración, desarrollo de prompts, diseño de Z-RFCs, pruebas con datos no productivos. | `READ_ONLY=true`, `MAX_ROWS` bajo/medio, `RFC_READ_TABLE` permitido con cuidado, allowlist amplia pero revisada. |
| QAS | Allowlist | Validación de piloto, pruebas integradas, smoke tests con datos representativos. | `READ_ONLY=true`, `ALLOWED_RFC` explícito, tablas allowlisted, trazas de autorización, sin peligrosas. |
| PRD | Certificado | Operación consultiva y monitorización aprobada. | Solo RFCs certificadas y/o Z-RFCs read-only; evitar `RFC_READ_TABLE`; outputs mínimos; auditoría y aprobación humana. |

---

## Convención futura de variables por destino

Estas variables **no están implementadas todavía**. Sirven como diseño para un Sprint posterior si se decide añadir enforcement por destino sin romper compatibilidad:

```env
# Perfil lógico por destino
SAPMCP_DEV_POLICY_PROFILE=flexible
SAPMCP_QAS_POLICY_PROFILE=allowlist
SAPMCP_PRD_POLICY_PROFILE=certified

# Allowlist RFC por destino
SAPMCP_DEV_ALLOWED_RFC=RFC_PING,STFC_CONNECTION,RFC_READ_TABLE,RFC_GET_*,DDIF_*,BAPI_*_GET*,BAPI_*_LIST*,TH_*,ENQUEUE_READ
SAPMCP_QAS_ALLOWED_RFC=RFC_PING,STFC_CONNECTION,RFC_GET_FUNCTION_INTERFACE,DDIF_FIELDINFO_GET,ENQUEUE_READ,TH_SERVER_LIST,TH_WPINFO,BAPI_XBP_JOB_SELECT
SAPMCP_PRD_ALLOWED_RFC=RFC_PING,STFC_CONNECTION,Z_SAPMCP_HEALTH_CHECK,Z_SAPMCP_GET_USER_AUDIT

# Límites de lectura por destino
SAPMCP_DEV_MAX_ROWS=500
SAPMCP_QAS_MAX_ROWS=200
SAPMCP_PRD_MAX_ROWS=50

# Flags explícitos de lectura genérica
SAPMCP_DEV_ALLOW_RFC_READ_TABLE=true
SAPMCP_QAS_ALLOW_RFC_READ_TABLE=allowlisted_tables
SAPMCP_PRD_ALLOW_RFC_READ_TABLE=false

# Tablas allowlisted si se acepta RFC_READ_TABLE fuera de DEV
SAPMCP_QAS_ALLOWED_TABLES=T000,TFDIR,DD02L,DD03L,TBTCO
SAPMCP_PRD_ALLOWED_TABLES=
```

### Reglas de compatibilidad futura

- Si no existe variable por destino, caer a la `SafetyPolicy` global actual.
- Los nombres de destino deben coincidir con `SAPMCP_DESTINATIONS`.
- PRD debe poder configurarse como deny-by-default aunque DEV sea flexible.
- Las decisiones deben aparecer en `sap_config_status` sin secretos.
- La auditoría debe registrar `destination`, perfil efectivo y motivo de bloqueo.

---

## Recomendación práctica antes de implementar enforcement por destino

Mientras la política siga siendo global, hay dos patrones seguros:

### Patrón A — Un proceso MCP por entorno

Ejecutar instancias separadas de `sapmcp`, cada una con su `.env`:

```text
sapmcp-dev  -> .env.dev  -> SAPMCP_ALLOWED_RFC amplio controlado
sapmcp-qas  -> .env.qas  -> SAPMCP_ALLOWED_RFC explícito
sapmcp-prd  -> .env.prd  -> solo RFCs certificadas/Z-RFCs
```

Ventajas:

- Aislamiento fuerte de configuración.
- Menor riesgo de que una allowlist DEV afecte a PRD.
- Auditoría y permisos por proceso.

### Patrón B — Una instancia multi-destination con política más restrictiva

Usar una sola instancia con `SAPMCP_DESTINATIONS=DEV,QAS,PRD`, pero configurar la allowlist global como si todo fuera PRD.

Ventajas:

- Menos procesos.
- Más sencillo para demo.

Limitación:

- DEV queda innecesariamente limitado.
- No permite expresar diferencias finas por destino.

Para piloto enterprise, se recomienda **Patrón A** hasta que exista enforcement por destino en código.

---

## Política de salida de datos por entorno

| Entorno | Datos devueltos al LLM | Redacción recomendada |
| --- | --- | --- |
| DEV | Datos técnicos y muestras no sensibles. | Redactar contraseñas, rutas sensibles y tokens; tolerancia mayor a metadata. |
| QAS | Datos representativos con control. | Reducir PII, limitar filas, evitar dumps completos si contienen datos reales. |
| PRD | Solo mínimo necesario. | Agregados, conteos, ventanas cortas, redacción de usuarios/hosts si no son necesarios. |

---

## Checklist de aprobación para PRD

- [ ] Usuario técnico `RFC_SAPMCP_PRD` separado y sin roles amplios.
- [ ] `SAPMCP_READ_ONLY=true`.
- [ ] `SAPMCP_ALLOW_DANGEROUS=false`.
- [ ] Allowlist RFC explícita y revisada por Security.
- [ ] Decisión formal sobre `RFC_READ_TABLE` en PRD: preferentemente denegado.
- [ ] Z-RFCs productivas revisadas por ABAP/Security si existen.
- [ ] LLM aprobado: local, on-prem o cloud privado contractual.
- [ ] Auditoría local protegida y retención definida.
- [ ] Procedimiento de incidente y revocación de credenciales.
