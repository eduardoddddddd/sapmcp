# Gobierno LLM y AI compliance para sapmcp

**Audiencia:** CISO, SAP Security, arquitectura enterprise, Legal/Compliance, auditoría interna, Basis y responsables del piloto.  
**Fecha de referencia:** mayo de 2026.  
**Objetivo:** establecer controles mínimos para usar `sapmcp` con LLMs cuando la fuente de datos es SAP.

> Este documento no es asesoría legal. La clasificación regulatoria y contractual debe validarse con Legal/Compliance, especialmente si el piloto procesa datos personales, financieros, de empleados, seguridad o producción.

---

## Principio fundamental

Los datos SAP no deben salir a un LLM público no aprobado.

Aunque `sapmcp` sea read-only, sus respuestas pueden contener:

- datos personales de usuarios, empleados, clientes o proveedores;
- información financiera, logística o comercial;
- roles, perfiles, bloqueos, fallos de logon o señales de seguridad;
- nombres de sistemas, hosts, jobs, programas, dumps, tablas y objetos Z;
- errores internos útiles para un atacante.

La decisión de usar un LLM debe tratarse como una decisión de arquitectura y compliance, no como una preferencia de productividad.

---

## Modelos de despliegue recomendados

| Entorno | LLM recomendado | Condiciones mínimas |
| --- | --- | --- |
| Laboratorio sintético | Local o cloud controlado | Sin datos reales ni secretos. |
| ABAP Trial/A4H | Preferible local | Datos de demo; no exponer credenciales ni dumps reales. |
| DEV cliente | Local/on-prem o cloud privado aprobado | Aprobación Security, usuario técnico mínimo, auditoría. |
| QAS cliente | Local/on-prem o cloud privado aprobado | DLP, retención definida, allowlist de tools/RFCs. |
| PRD cliente | Solo plataforma aprobada formalmente | Contrato/DPA si aplica, trazabilidad, redacción, aprobación humana y mínimo privilegio. |

---

## Controles obligatorios para piloto enterprise

### 1. Clasificación de datos

Antes del piloto, clasificar qué puede devolver cada tool:

- Público / demo sintético.
- Interno técnico.
- Confidencial SAP.
- Datos personales.
- Datos regulados o sensibles.

La clasificación debe definir si la salida puede mostrarse al LLM, redactarse o bloquearse.

### 2. Separación de entornos

- Usuarios SAP separados por DEV/QAS/PRD.
- Roles PFCG separados por entorno.
- `.env`, logs y auditoría separados por entorno.
- No mezclar datos PRD con prompts de prueba o tuning.

### 3. Mínimo privilegio técnico

- `SAPMCP_READ_ONLY=true`.
- `SAPMCP_ALLOW_DANGEROUS=false`.
- `SAPMCP_ALLOWED_RFC` explícito en QAS/PRD.
- Evitar `RFC_READ_TABLE` libre en PRD.
- Preferir Z-RFCs read-only tipadas y auditadas.

### 4. Trazabilidad

Registrar como mínimo:

- usuario humano solicitante;
- host/cliente MCP usado;
- destino SAP;
- tool/RFC ejecutada;
- timestamp;
- hash de parámetros redactados;
- resultado técnico y duración;
- aprobación humana cuando aplique.

`sapmcp` ya registra auditoría JSONL local; en piloto enterprise debe definirse retención, protección, rotación y exportación a SIEM si aplica.

### 5. Aprobación humana

Para PRD o datos sensibles:

- El LLM puede proponer pasos, no aprobar cambios de control.
- Las acciones con impacto operativo requieren validación de Basis/Security.
- Los informes generados por LLM deben revisarse antes de enviarse a dirección o auditoría.

### 6. Redacción y minimización

- No devolver dumps completos si basta con conteos y top errores.
- No devolver roles/perfiles completos salvo caso de auditoría aprobado.
- Enmascarar usuarios, hosts o IDs cuando no sean necesarios.
- Limitar filas (`SAPMCP_MAX_ROWS`) y ventanas temporales.

---

## Prompt injection y abuso de tools

Un prompt puede intentar manipular al host LLM para:

- pedir `RFC_READ_TABLE` sobre tablas sensibles;
- solicitar RFCs peligrosas o no allowlisted;
- exfiltrar `.env`, credenciales, logs o rutas internas;
- convertir un hallazgo de ST22/SM21 en instrucciones maliciosas;
- ignorar políticas por destino.

Mitigaciones:

1. La seguridad debe residir en `sapmcp` y SAP, no solo en el prompt del LLM.
2. Mantener allowlist de RFCs y máximo de filas.
3. Redactar secretos antes de exponer configuración.
4. Separar tools de lectura y tools de cambio.
5. Requerir aprobación humana para decisiones PRD.
6. Tratar texto proveniente de SAP como datos no confiables: errores, jobs, descripciones Z y dumps no deben convertirse automáticamente en comandos.

---

## Auditoría y evidencias de compliance

Para un piloto cliente, preparar un paquete de evidencias:

- Diagrama de arquitectura y flujo de datos.
- Matriz de RFC/BAPI autorizadas.
- Roles PFCG y usuarios técnicos.
- Configuración sanitizada de `sapmcp`.
- Política de LLM aprobada.
- Extractos de auditoría JSONL.
- Procedimiento de revocación de credenciales.
- Registro de aprobaciones humanas.
- Criterios de exclusión: tablas, datos personales, PRD, dumps completos.

---

## Nota prudente sobre AI Act y regulación

Si el piloto opera en la Unión Europea o afecta a entidades europeas, debe revisarse el encaje del uso de LLMs bajo el marco regulatorio aplicable, incluyendo el AI Act cuando corresponda. La regulación se aplica de forma progresiva y las obligaciones dependen del rol de la organización, el tipo de sistema, el caso de uso, el nivel de riesgo y el proveedor/modelo utilizado.

Recomendación práctica:

- realizar clasificación de riesgo con Legal/Compliance;
- documentar finalidad y límites del sistema;
- conservar logs y controles humanos;
- confirmar que el proveedor LLM cumple las obligaciones contractuales y regulatorias aplicables;
- revisar periódicamente la normativa vigente antes de pasar de piloto a producción.

---

## Decisión recomendada para PRD

Para producción real, `sapmcp` debería operar bajo este patrón:

```text
SAP PRD -> sapmcp PRD -> LLM privado aprobado -> usuario humano autorizado
```

Con estas condiciones:

- RFCs certificadas o Z-RFCs read-only.
- Sin `RFC_READ_TABLE` libre.
- Auditoría protegida.
- Salida minimizada.
- Humano responsable de decisiones.
- Revisión Security antes de cambios de alcance.

---

## Referencias oficiales útiles

- European Commission — [AI Act timeline](https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act).
- European Commission — [AI Act Article 113: entry into force and application](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-113).
- European Commission — [General-purpose AI obligations under the AI Act](https://digital-strategy.ec.europa.eu/en/factpages/general-purpose-ai-obligations-under-ai-act).
