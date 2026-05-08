# Plantillas ABAP companion para sapmcp

Esta carpeta contiene plantillas conceptuales de Z-RFCs read-only para convertir `sapmcp` en una propuesta enterprise más segura, especialmente para QAS/PRD.

> **No son transportes listos para producción.** Son bases de diseño para que un equipo ABAP/Basis/Security las adapte, tipifique, revise, pruebe y transporte siguiendo el ciclo del cliente.

---

## Estrategia

`sapmcp` puede usar RFCs/BAPIs estándar para demos y DEV, pero en entornos productivos conviene reducir la dependencia de lectura genérica:

1. **Evitar `RFC_READ_TABLE` libre en PRD.**
   - Es potente, pero demasiado genérico.
   - Puede exponer tablas no previstas si el rol SAP es amplio.
   - Tiene limitaciones técnicas de ancho/tipos y semántica.
2. **Crear Z-RFCs read-only tipadas.**
   - Contratos explícitos de entrada/salida.
   - Tablas y campos allowlisted por diseño.
   - Límites de filas y ventanas temporales.
   - Salida agregada cuando baste.
3. **Añadir logs en SAP.**
   - Application Log (`SLG1`) o tabla Z de auditoría, según política.
   - Registrar usuario RFC, timestamp, caso de uso, filtros y volumen.
4. **Usar autorizaciones propias.**
   - Objeto Z, por ejemplo `Z_SAPMCP`, con actividades display/execute.
   - Campos sugeridos: entorno, caso de uso, tabla/recurso, nivel de detalle.
   - Validar siempre con SAP Security.

---

## Plantillas incluidas

| Archivo | Propósito |
| --- | --- |
| `Z_SAPMCP_HEALTH_CHECK.abap` | Health check técnico read-only con salida resumida. |
| `Z_SAPMCP_READ_TABLE_SAFE.abap` | Patrón de lectura de tabla con allowlist, campos tipados y filtros seguros. |
| `Z_SAPMCP_GET_USER_AUDIT.abap` | Auditoría controlada de usuario sin exponer más datos de los necesarios. |

---

## Requisitos antes de producción

- Crear DDIC types/tablas `Z*` reales para imports/exports/tables.
- Sustituir pseudocódigo por ABAP compilable según release.
- Revisar `AUTHORITY-CHECK` con Security.
- Añadir logging SAP conforme a política interna.
- Escribir ABAP Unit o pruebas manuales documentadas.
- Probar en DEV, transportar a QAS, ejecutar `STAUTHTRACE`, aprobar y solo entonces considerar PRD.
- Documentar versión exacta de la interfaz para `sapmcp`.

---

## Convención de nombres sugerida

```text
Objeto de autorización: Z_SAPMCP
Clase de mensajes:      ZSAPMCP
Objeto SLG1:            ZSAPMCP
Subobjetos SLG1:        HEALTH, READ_TABLE, USER_AUDIT
Paquete ABAP:           ZSAPMCP_RFC
Grupo de funciones:     ZSAPMCP_RFC
```
