# Docker y demo local para sapmcp

**Objetivo:** documentar una forma reproducible de ejecutar `sapmcp` en contenedor sin redistribuir el SAP NetWeaver RFC SDK ni secretos.

> El SAP NetWeaver RFC SDK es software propietario de SAP. Este repositorio **no lo incluye**, no lo descarga y no debe empaquetarlo en imágenes públicas. El SDK debe montarse externamente en runtime desde una ubicación autorizada por la licencia del cliente.

---

## Qué incluye el repo

- `Dockerfile`: imagen Python de `sapmcp` sin SDK SAP embebido.
- `docker-compose.example.yml`: ejemplo de ejecución local con variables placeholder.
- `.dockerignore`: evita incluir `.env`, venvs, PDFs propietarios, SDKs y artefactos locales en el contexto de build.

---

## Requisito crítico del SDK

La imagen Docker es Linux. Por tanto, el montaje debe contener la versión **Linux x86_64** del SAP NetWeaver RFC SDK, no la librería de macOS (`.dylib`) ni Windows (`.dll`).

Debe existir, por ejemplo:

```text
/path/autorizado/nwrfcsdk/lib/libsapnwrfc.so
/path/autorizado/nwrfcsdk/lib/libsapucum.so
```

Variables dentro del contenedor:

```env
SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
LD_LIBRARY_PATH=/opt/sap/nwrfcsdk/lib
```

---

## Build local

```bash
cd /Users/eduardoariasbravo/Developer/sapmcp
docker build -t sapmcp:local .
```

El build no necesita el SDK porque solo instala el paquete Python.

---

## Ejecución con `docker run`

Crea un fichero local `.env.docker` no versionado:

```env
SAP_ASHOST=your_sap_host
SAP_SYSNR=00
SAP_CLIENT=100
SAP_USER=RFC_SAPMCP_DEV
SAP_PASS=********
SAP_LANG=EN
SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
SAPMCP_READ_ONLY=true
SAPMCP_ALLOW_DANGEROUS=false
SAPMCP_MAX_ROWS=200
SAPMCP_ALLOWED_RFC=RFC_PING,STFC_CONNECTION
```

Ejecuta montando el SDK como read-only:

```bash
docker run --rm -it \
  --env-file .env.docker \
  -e LD_LIBRARY_PATH=/opt/sap/nwrfcsdk/lib \
  -v /path/autorizado/nwrfcsdk/lib:/opt/sap/nwrfcsdk/lib:ro \
  -v sapmcp-audit:/home/sapmcp/.sapmcp \
  sapmcp:local
```

---

## Ejecución con docker compose

Copia el ejemplo y ajusta rutas locales:

```bash
cp docker-compose.example.yml docker-compose.yml
```

Crea `.env.docker` con placeholders reales en tu entorno local, nunca en Git.

Exporta la ruta host del SDK:

```bash
export SAP_NWRFC_SDK_LIB_DIR_HOST=/path/autorizado/nwrfcsdk/lib
```

Lanza una sesión:

```bash
docker compose run --rm sapmcp
```

Para integrarlo con un host MCP, configura el host para lanzar `docker compose run --rm sapmcp` como comando stdio, o crea un wrapper shell controlado por tu equipo.

---

## Seguridad para demos

- No montar `.env` real de PRD en una demo.
- No publicar la imagen si contiene capas con secretos o SDK copiado manualmente.
- No usar `SAP_ALL` ni usuarios personales.
- Para demos con datos reales, usar LLM local/on-prem/cloud privado aprobado.
- Mantener `SAPMCP_READ_ONLY=true` y `SAPMCP_ALLOW_DANGEROUS=false`.
- Preferir destinos DEV/QAS o ABAP trial con datos sintéticos.

---

## Troubleshooting rápido

| Síntoma | Causa probable | Acción |
| --- | --- | --- |
| `cannot open shared object file: libsapnwrfc.so` | El SDK no está montado o `LD_LIBRARY_PATH` no apunta al directorio correcto. | Verificar volumen y `SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib`. |
| Error de arquitectura | Se montó SDK macOS/Windows o ARM en contenedor Linux x86_64. | Usar SDK Linux x86_64 compatible. |
| `RFC_NO_AUTHORITY` | Usuario SAP sin permisos para la RFC. | Revisar `SU53`/`STAUTHTRACE` y matriz PFCG. |
| Timeout de conexión | Red, firewall, SAProuter o host no accesible desde Docker. | Probar conectividad desde contenedor y revisar ruta SAProuter. |
