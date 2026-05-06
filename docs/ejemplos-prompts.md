# Ejemplos oficiales de prompts para sapmcp

**Audiencia:** demos comerciales, consultores SAP funcionales, Basis, ABAPers y equipos técnicos que quieran ver `sapmcp` operando sobre SAP real desde un cliente MCP/LLM como Claude Desktop, Codex u otros hosts compatibles.

**Objetivo:** demostrar que `sapmcp` convierte SAP en una interfaz conversacional segura, auditable y potente, **sin depender de `pyrfc`**. El proyecto usa SAP NetWeaver RFC SDK vía `ctypes`, por lo que evita el bloqueo típico de librerías Python abandonadas o difíciles de mantener.

> Estos prompts están escritos para copiar y pegar. Están endurecidos para demos reales: hacen preflight, trabajan en modo lectura, limitan lecturas grandes, declaran limitaciones y buscan alternativas cuando una tabla/RFC no está disponible.

---

## 1. Reglas de oro para una demo que no falle

Antes de enseñar `sapmcp` en directo:

1. Arranca el servidor MCP con `SAPMCP_READ_ONLY=true`.
2. Ten configurado `destination=default` o un destino nombrado estable (`DEV`, `A4H_DOCKER`, etc.).
3. Ejecuta antes de la demo:
   - `sap_config_status`
   - `sap_ping`
   - `sap_health_check(profile="quick")`
4. Preselecciona 2-3 objetos reales del sistema: un pedido, un cliente, un material, una sociedad, un usuario y, si existe, algún objeto `Z*`.
5. No vendas magia falsa: si una RFC/tabla no existe o no está autorizada, deja que el MCP lo diga. Eso también demuestra seguridad y honestidad operativa.

### Bloque común recomendado

Puedes pegar este bloque al principio de cualquier prompt de demo:

```text
Contexto: estás usando sapmcp contra un sistema SAP real/controlado.

Reglas obligatorias:
- Usa destination=default salvo que yo indique otro destino.
- Solo lectura. No ejecutes cambios ni uses confirm_dangerous.
- Primero valida conexión con sap_config_status y sap_ping.
- Si aplica, ejecuta sap_health_check(profile="quick") para saber si el sistema responde bien.
- Si una tabla, RFC o campo no existe/no está autorizado, no inventes: indícalo y continúa con una alternativa razonable.
- Usa rowcount bajo o razonable en lecturas exploratorias.
- No expongas secretos, passwords ni payload sensible.
- Devuelve siempre: datos encontrados, tools usadas, limitaciones y veredicto.
```

---

## 2. Prompt cero — preparar datos reales para una demo

Este prompt sirve para no depender de ejemplos inventados como `Acme S.A.` o pedidos que quizá no existan en A4H.

```text
Quiero preparar una demo en directo de sapmcp. Busca objetos reales que existan en este sistema para usarlos en prompts posteriores.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Usa rowcount bajo y tablas estándar.
- Si una tabla no existe o no tiene datos, dilo y prueba una alternativa.

Necesito que encuentres y me devuelvas:
1. 3 pedidos de venta recientes desde VBAK, con VBELN, AUART, KUNNR, VKORG, ERDAT y NETWR si está disponible.
2. 3 clientes con datos básicos desde KNA1, con KUNNR, NAME1, LAND1 y ORT01.
3. 3 materiales desde MARA, con MATNR, MTART, MATKL y MEINS.
4. 3 sociedades desde T001, con BUKRS, BUTXT, LAND1 y WAERS.
5. 3 usuarios dialog o técnicos desde USR02, con BNAME, TRDAT, UFLAG y GLTGB.
6. Si existen objetos custom, busca algunos nombres Z* o Y* en TADIR/TFDIR/DD02L con rowcount bajo.

Devuélveme una tabla "objetos buenos para demo" y recomienda cuáles usar para SD, MM, FI, Basis y ABAP.
```

---

# BLOQUE A — Prompts para consultores funcionales SD/MM/FI

## A.1. El pedido que no factura

```text
Tengo un cliente que se queja de que un pedido de venta no se ha facturado. Si no te doy número de pedido, localiza primero un pedido real en VBAK con datos suficientes para investigarlo.

Reglas:
- Usa destination=default.
- Solo lectura. No ejecutes cambios.
- Primero ejecuta sap_config_status y sap_ping.
- Si una tabla no existe o no está autorizada, márcalo y continúa con alternativa.
- Limita cada lectura con rowcount razonable.

Investigación:
1. Localiza cabecera y posiciones del pedido en VBAK y VBAP.
2. Consulta estado global y por posición en VBUK/VBUP si existen; si no existen, usa campos de status disponibles en VBAK/VBAP o BAPIs de detalle SD.
3. Sigue el flujo documental con VBFA: pedido → entrega → factura → documento contable si existe.
4. Si hay entrega, consulta LIKP/LIPS y estado de facturación/entrega.
5. Si hay factura, consulta VBRK/VBRP y su documento contable asociado si está disponible.
6. Revisa bloqueos de facturación en VBAK, VBKD o campos equivalentes como FAKSK/FAKSP si existen.
7. Si llegó a FI, consulta BKPF con el documento contable encontrado.

Devuélveme:
- Timeline del flujo documental en texto plano.
- Tabla con pedido, entrega, factura y contabilización si existen.
- Veredicto en 5 líneas: "el pedido no factura porque X; acción recomendada Y".
- Lista de tablas/tools usadas y limitaciones.
```

## A.2. Radiografía 360 de un cliente

```text
Hazme una ficha 360 de un cliente real. Si no te doy KUNNR, busca un cliente con actividad reciente en VBAK o VBRK y úsalo.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- No inventes datos. Si una tabla no existe, indícalo y sigue.
- No truncar importes ni identificadores; pide campos concretos.

Quiero:
1. Datos básicos del cliente desde KNA1.
2. Datos por sociedad desde KNB1 si existe.
3. Pedidos de venta recientes desde VBAK, últimos 90 días si el sistema tiene fechas útiles.
4. Facturas recientes desde VBRK, últimos 90 días si hay datos.
5. Partidas abiertas de cliente desde BSID y compensadas/históricas desde BSAD si están disponibles.
6. Riesgo crediticio desde KNKK si existe y está autorizado.

Devuélveme:
- Tabla resumen del cliente.
- Situación financiera.
- Actividad comercial.
- Alertas o anomalías.
- Tres bullets ejecutivos, como para una reunión con dirección.
```

## A.3. Material problemático

```text
Quiero saberlo todo sobre un material real del sistema. Si no te doy MATNR, busca primero un material existente en MARA que tenga datos en MARC o MARD.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Si MSEG no existe o es demasiado pesada en S/4HANA, usa MATDOC o limita mucho la lectura.
- No uses SELECTs amplios: rowcount razonable y campos concretos.

Investiga:
1. Datos generales en MARA.
2. Centros donde está extendido en MARC.
3. Stock por centro y almacén en MARD.
4. Movimientos recientes en MSEG o MATDOC, últimos 30 días si es viable.
5. Listas de materiales en STKO/STPO si existen datos.
6. Valoración/precios en MBEW.

Devuélveme:
- Tabla resumen por centro/almacén.
- Movimientos recientes más relevantes.
- Precio estándar o medio si existe.
- Párrafo en español natural: "qué pasa con este material".
```

---

# BLOQUE B — Prompts para consultores Basis / DevOps SAP

## B.1. Aterrizaje en sistema cliente desconocido

```text
Acabo de aterrizar en este sistema SAP y no sé nada de él. Hazme un informe técnico de aterrizaje en 2 minutos.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Después ejecuta sap_health_check(profile="standard").
- Si una tool devuelve available=false o unknown, no lo ocultes: explica la causa probable.

Quiero:
1. Identificación: destino, SID si aparece, mandante, usuario técnico sanitizado, idioma, host/configuración sanitizada.
2. Salud actual: resumen de sap_health_check con verdict global.
3. Inventario operativo: workprocesses, jobs recientes, dumps últimas 24h, locks, tRFC/qRFC pendiente.
4. Usuarios sospechosos: usuarios con SAP_ALL distintos de SAP*, DDIC y usuarios técnicos esperables si puedes obtenerlo con lecturas seguras.
5. Top señales de uso del día si puedes inferirlas con tablas estándar disponibles; si no, dilo.
6. Bandera roja/amarilla/verde por área.

Devuélveme máximo 15 líneas, tono email a jefe de proyecto: "estado del sistema, riesgos y primer siguiente paso recomendado".
```

## B.2. Auditoría de un usuario antes de darlo de baja

```text
Voy a dar de baja a un usuario y quiero asegurarme de que no rompo nada importante. Si no te doy usuario, busca un usuario real reciente en USR02 y úsalo como ejemplo.

Reglas:
- Usa destination=default.
- Solo lectura. No bloquees, no modifiques, no cambies roles.
- Primero ejecuta sap_config_status y sap_ping.
- Si alguna consulta no está autorizada, dilo y sigue.

Investiga:
1. Ejecuta sap_get_user_audit para el usuario.
2. Revisa USR02: último logon, estado de bloqueo, vigencia y fallos de logon.
3. Revisa roles/perfiles devueltos por la auditoría; marca SAP_ALL/SAP_NEW u otros perfiles críticos.
4. Busca jobs programados o recientes a su nombre con sap_get_jobs y/o TBTCO filtrando usuario si hace falta.
5. Revisa si aparece como usuario técnico en destinos RFC con RFCDES si está autorizado.
6. Si hay objetos batch, RFC o jobs dependientes del usuario, identifícalos.

Devuélveme:
- GO / NO-GO para darlo de baja.
- Razones.
- Qué migrar antes si es NO-GO.
- A quién pedir confirmación: Basis, funcional, seguridad o propietario del proceso.
```

## B.3. El sistema va lento, dime por qué

```text
El cliente reporta lentitud generalizada esta mañana. Investiga como compañero Basis senior.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status, sap_ping y sap_health_check(profile="standard").
- Sé directo. No ejecutes cambios.
- Si una fuente no existe, dilo y usa otra.

Investiga:
1. sap_get_workprocesses: busca workprocesses en PRIV, stopped, on hold o todos ocupados.
2. sap_get_locks: identifica locks largos o sospechosos si hay fecha/hora disponible.
3. sap_get_rfc_queue: revisa tRFC y, si procede, qRFC out/in.
4. sap_get_short_dumps de hoy: mira si hay patrón por usuario, programa o mensaje.
5. sap_get_jobs status="R" y status="A" de las últimas horas: jobs largos, activos o abortados.
6. sap_get_update_requests status="ERR" y pendientes; si no está disponible, indica limitación.
7. Si hay syslog disponible, sap_get_syslog de hoy para errores relevantes.

Devuélveme:
- Causa más probable de la lentitud en una frase.
- Evidencias en 5 bullets.
- Siguiente paso de diagnóstico read-only.
- Qué NO tocaría todavía.
```

---

# BLOQUE C — Prompts para ABAPers

## C.1. Reverse engineering de una RFC desconocida

```text
Tengo que llamar a una RFC desde un proceso externo y nadie me sabe decir exactamente qué hace ni qué espera. Si no te doy nombre, busca primero una RFC estándar interesante tipo BAPI_*_GET* o una Z*/Y* si existe.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Empieza por sap_describe_rfc.
- No ejecutes RFCs de cambio ni RFCs con nombres CREATE/CHANGE/DELETE/POST/COMMIT.
- Si la lectura de código fuente no está disponible o no está allowlisted, no fuerces: documenta la limitación.

Investiga:
1. Describe la interfaz completa con sap_describe_rfc.
2. Si está permitido, intenta obtener documentación/código fuente con RFCs estándar de lectura como RPY_FUNCTIONMODULE_READ o RFC_READ_REPORT; si no, usa solo interfaz y DDIC.
3. Identifica parámetros obligatorios, tablas de entrada/salida y estructuras DDIC.
4. Busca señales de side effects por nombre, documentación o código: COMMIT WORK, ROLLBACK, IN UPDATE TASK, llamadas BAPI de modificación, escritura en tablas.
5. Si es una BAPI estándar de lectura, confirma que parece segura; si no puedes confirmarlo, dilo.

Devuélveme:
- Firma legible en formato tabla: parámetro, tipo, dirección, estructura/tipo y obligatoriedad si se puede inferir.
- Resumen funcional en 5 líneas.
- Riesgo de side effects: bajo/medio/alto con justificación.
- Snippet Python conceptual de cómo invocarla con sap_rfc_call desde un cliente MCP.
```

## C.2. Where-used inverso de una tabla custom

```text
Quiero saber dónde se usa una tabla custom. Si no te doy tabla, busca primero una tabla Z*/Y* en DD02L o TADIR y usa la más prometedora.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Limita búsquedas amplias con rowcount razonable.
- Si no hay objetos Z*/Y*, haz la demo con una tabla estándar pequeña y dilo.
- Si no puedes leer source ABAP por autorización/allowlist, usa TADIR, DD03L, DD12L y catálogo como alternativa.

Búscame:
1. Definición de la tabla en DD02L/DD03L.
2. Índices secundarios en DD12L/DD17S si están disponibles.
3. Programas Z/Y que potencialmente la usen, buscando en TADIR y, si está permitido, en includes/source.
4. Function modules que la puedan tocar, desde TFDIR/TADIR y source si está disponible.
5. Estructuras DDIC dependientes o includes vía DD03L.

Devuélveme:
- Grafo en texto: "ZTABLA ← ZPROG ← Z_RFC_API" cuando puedas inferirlo.
- Tabla de objetos relacionados con tipo de evidencia: DDIC, source, RFC, índice.
- Riesgo de modificar la tabla: bajo/medio/alto.
- Limitaciones exactas de la búsqueda.
```

## C.3. Análisis de impacto antes de modificar una estructura DDIC

```text
Voy a modificar una estructura DDIC añadiendo un campo nuevo. Antes de tocar nada, dime el impacto. Si no te doy estructura, busca una estructura Z*/Y*; si no hay, usa una estructura estándar pequeña solo para demostrar el método.

Reglas:
- Usa destination=default.
- Solo lectura.
- No modifiques DDIC ni actives objetos.
- Primero ejecuta sap_config_status y sap_ping.
- Si no puedes leer source, documenta la limitación y trabaja con DDIC/catálogo.

Investiga:
1. Campos actuales de la estructura en DD03L/DD04T si aplica.
2. Tablas que la incluyan vía .INCLUDE o estructuras dependientes.
3. Function modules/BAPIs custom que la usen como parámetro, si se puede inferir desde interfaces o source.
4. Programas Z/Y que la usen como TYPE, LIKE o DATA reference, si source está disponible.
5. Vistas/CDS relacionadas si hay metadata accesible.
6. Puntos donde MOVE-CORRESPONDING, SELECT INTO CORRESPONDING FIELDS o serializaciones externas podrían cambiar comportamiento.
7. Objetos a regenerar/recompilar tras la modificación.

Devuélveme:
- Nivel de riesgo: BAJO / MEDIO / ALTO.
- Objetos afectados agrupados por tipo.
- Checklist previo para el ABAPer.
- Recomendación de transporte y pruebas.
```

---

# BLOQUE D — Demos cortas de "ver para creer"

## D.1. Habla con la base de datos SAP en español

```text
Sin que yo tenga que decirte tablas SAP, dame la lista de los 10 documentos contables más grandes por importe absoluto registrados en este sistema en el periodo más reciente con datos.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Descubre tú las tablas estándar razonables.
- Evita lecturas enormes de BSEG; usa campos concretos, rowcount limitado y alternativas como BSID/BSAD/BSIK/BSAK/ACDOCA si aplica.
- Si no hay datos FI suficientes, dilo y devuelve la mejor aproximación con lo que exista.

Quiero:
- Documento, sociedad, ejercicio, fecha, moneda, importe, proveedor/cliente si se puede cruzar.
- Nombre del proveedor desde LFA1 o cliente desde KNA1 cuando aplique.
- Explicación breve de cómo lo dedujiste.
```

## D.2. Detector de raros

```text
Encuéntrame 5 cosas raras que un consultor SAP experto miraría al aterrizar en este sistema.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status, sap_ping y sap_health_check(profile="standard").
- No inventes anomalías: cada hallazgo debe apoyarse en una lectura.
- Si algo no se puede comprobar, no lo cuentes como hallazgo.

Busca señales como:
1. Usuarios con SAP_ALL o muchos fallos de logon.
2. Dumps repetidos por programa/usuario.
3. Jobs abortados o activos sospechosos.
4. Locks o colas RFC pendientes.
5. Tablas custom grandes o muchos objetos Z/Y si puedes inferirlo con seguridad.
6. Configuración por defecto o datos de mandante llamativos en T000/T001.

Devuélveme 5 hallazgos máximo, una frase por hallazgo y por qué llama la atención.
```

## D.3. El recorrido del dinero

```text
Coge un pedido de venta real reciente con valor significativo y sigue su ciclo end-to-end: pedido → entrega → factura → contabilización → cobro si hay datos.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Si no encuentras pedido con valor, usa el primer pedido reciente con flujo documental disponible.
- Usa VBFA para seguir el flujo cuando sea posible.
- Si una etapa no existe, marca "no encontrado" y explica si parece pendiente o simplemente sin datos en el sistema de demo.

Para cada paso dime:
- Fecha.
- Documento.
- Tipo de documento.
- Importe/moneda si está disponible.
- Estado.

Devuélveme un timeline en texto plano de 5-6 líneas y una conclusión: "el dinero está en qué punto del proceso".
```

---

# BLOQUE E — Wow factor para cerrar una charla

## E.1. Dictado en lenguaje natural para keyuser

```text
Soy un keyuser sin acceso a SAP GUI. Necesito saber cuántos pedidos abiertos tiene un cliente real y cuál es su saldo deudor actual. Si no te doy nombre de cliente, busca un cliente con actividad reciente y úsalo.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Responde sin jerga SAP, como si me llamaras por teléfono.
- Si el saldo no se puede calcular con las tablas disponibles, di exactamente qué falta.

Investiga:
1. Identifica cliente en KNA1.
2. Pedidos abiertos o recientes en VBAK/VBAP/status si está disponible.
3. Partidas abiertas en BSID.
4. Histórico compensado en BSAD si ayuda.

Respuesta final:
- Máximo 6 frases.
- Sin nombres técnicos de tablas salvo en una nota final "fuentes consultadas".
```

## E.2. Pregunta del CFO

```text
Pregunta del CFO: "¿estamos cobrando peor este trimestre que el anterior?". Investiga con datos reales de este SAP y responde como analista financiero.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- Si no hay suficientes datos reales para comparar trimestres, dilo y ofrece la mejor aproximación posible.
- No inventes KPIs: calcula solo lo que puedas sostener con tablas consultadas.

Intenta calcular:
1. Importe de facturación/cobros o partidas compensadas por periodo con BSID/BSAD/VBRK/BKPF según disponibilidad.
2. Evolución de partidas abiertas vencidas si hay fechas de vencimiento accesibles.
3. Comparativa trimestre actual vs trimestre anterior.
4. Señal simple: mejor / igual / peor, con números.

Responde en 4 frases máximo, sin paja, tono CFO.
```

## E.3. Genera un Z-report en 30 segundos

```text
Necesito un report ABAP para SE38 que liste, por sociedad, los 10 proveedores con más volumen de facturación pendiente. Yo no voy a escribir el código ABAP, pero quiero que tú me dejes el trabajo medio hecho.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.
- No modifiques SAP, no generes objetos, no actives nada.
- Si BSIK/BSAK no existen o no tienen datos, usa alternativa documentada.

Haz:
1. Investiga qué tablas usarías: BSIK para partidas abiertas de proveedor, LFA1 para nombre, T001 para sociedad; considera BSAK solo para histórico si hace falta.
2. Ejecuta la consulta con sap_read_table usando campos concretos y rowcount razonable.
3. Agrupa por sociedad/proveedor y calcula total pendiente si los datos lo permiten.
4. Devuelve el resultado real en tabla.
5. Genera un draft de SELECT ABAP para SE38 que un ABAPer pueda adaptar.

Salida:
- Tabla top 10 por sociedad/proveedor.
- Supuestos y limitaciones.
- Código ABAP draft, claramente marcado como borrador.
```

---

## 3. Prompts técnicos para demostrar que no dependemos de PyRFC

Estos prompts son útiles cuando alguien cuestiona la viabilidad técnica porque `pyrfc` no le funciona o no quiere depender de él.

## T.1. Demostración técnica del bridge RFC

```text
Quiero demostrar técnicamente que sapmcp está hablando con SAP sin usar pyrfc.

Reglas:
- Usa destination=default.
- Solo lectura.
- Primero ejecuta sap_config_status y sap_ping.

Demuestra:
1. Configuración activa sanitizada: destino, cliente, usuario, idioma y ruta de SDK si se muestra sin secretos.
2. Resultado de sap_ping.
3. Descripción de una RFC estándar con sap_describe_rfc("STFC_CONNECTION") o RFC_GET_FUNCTION_INTERFACE.
4. Lectura pequeña de T000 con sap_read_table.
5. Auditoría reciente con sap_audit_tail.

Devuélveme una explicación ejecutiva: "esto funciona porque sapmcp invoca SAP NetWeaver RFC SDK vía ctypes; no depende de pyrfc".
```

## T.2. Prueba de seguridad read-only

```text
Quiero demostrar que sapmcp no es una puerta trasera peligrosa y que bloquea operaciones no permitidas.

Reglas:
- Usa destination=default.
- No ejecutes cambios.
- No uses confirm_dangerous.

Haz:
1. Ejecuta sap_safety_check para RFC_PING.
2. Ejecuta sap_safety_check para BAPI_TRANSACTION_COMMIT.
3. Ejecuta sap_safety_check para una RFC con CREATE o CHANGE en el nombre, sin llamarla.
4. Explica qué pasaría si intentáramos ejecutarla con SAPMCP_READ_ONLY=true.
5. Lee sap_audit_tail para mostrar que hay trazabilidad.

Devuélveme una conclusión corta para un responsable de seguridad.
```

---

## 4. Orden recomendado para una demo de 15 minutos

### Si el público es técnico/Basis

1. **T.1 — Demostración técnica del bridge RFC**: prueba que no hay `pyrfc`.
2. **B.1 — Aterrizaje en sistema desconocido**: valor operativo inmediato.
3. **B.3 — El sistema va lento**: caso realista de guardia Basis.
4. **D.2 — Detector de raros**: juicio contextual del LLM.
5. **T.2 — Seguridad read-only**: cierre defensivo.

### Si el público es funcional/management

1. **D.1 — Habla con SAP en español**.
2. **A.1 — Pedido que no factura**.
3. **D.3 — Recorrido del dinero**.
4. **E.1 — Dictado para keyuser**.
5. **E.2 — Pregunta del CFO**.

### Si el público incluye ABAPers

1. **T.1 — Demostración técnica del bridge RFC**.
2. **C.1 — Reverse engineering de una RFC**.
3. **C.2 — Where-used inverso**.
4. **C.3 — Impacto DDIC**.
5. **E.3 — Z-report en 30 segundos**.

---

## 5. Mensajes de cierre para la demo

Puedes usar alguno de estos cierres:

```text
La idea no es sustituir SAP GUI ni a los consultores. La idea es que un experto pueda cruzar en segundos lo que antes requería 5 transacciones, 6 tablas y media hora de contexto.
```

```text
sapmcp no necesita pyrfc: habla con el SDK oficial de SAP mediante ctypes, expone tools MCP auditadas y aplica una política read-only por defecto.
```

```text
Lo importante no es que el LLM haga un SELECT. Lo importante es que entiende la pregunta SAP, elige las fuentes, cruza el flujo documental y devuelve un veredicto operativo.
```

---

## 6. Checklist antes de enseñar el repositorio

- [ ] README actualizado.
- [ ] `docs/operation.md` disponible como manual de operación.
- [ ] `docs/architecture.md` disponible para revisión técnica.
- [ ] `docs/ejemplos-prompts.md` disponible para demos.
- [ ] `.env.example` sin secretos reales.
- [ ] Tests verdes con `pytest -q`.
- [ ] `SAPMCP_READ_ONLY=true` en entornos de demo.
- [ ] Un destino SAP de demo verificado con `sap_ping`.
- [ ] 2-3 objetos reales preseleccionados con el Prompt cero.
