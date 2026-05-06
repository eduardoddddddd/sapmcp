# Instalación del SAP NetWeaver RFC SDK para sapmcp

**Audiencia:** usuarios que quieran instalar `sapmcp` desde cero, equipos Basis/DevOps, revisores técnicos y responsables de empaquetado/Docker.

**Objetivo:** dejar claro qué librería nativa necesita `sapmcp`, de dónde se obtiene, por qué no se incluye en GitHub y cómo instalarla/verificarla en macOS, Linux, Windows y contenedores.

---

## 1. Punto clave

`sapmcp` no usa `pyrfc`. El bridge Python llama directamente al **SAP NetWeaver RFC SDK** mediante `ctypes`.

Eso significa que, además de instalar el paquete Python, la máquina donde corre `sapmcp` debe tener disponible la librería nativa de SAP:

| Sistema | Librería principal |
|---|---|
| macOS | `libsapnwrfc.dylib` |
| Linux | `libsapnwrfc.so` |
| Windows | `sapnwrfc.dll` |

Sin esta librería, `sapmcp` puede instalarse, pero **no podrá abrir conexiones RFC contra SAP**.

---

## 2. ¿Se puede subir el SDK a GitHub?

**No. No debemos subir el SAP NetWeaver RFC SDK al repositorio.**

Motivos:

1. SAP distribuye el SDK desde canales oficiales de SAP, no como dependencia pública libre en PyPI/npm/GitHub.
2. La descarga está asociada a SAP Support Portal / SAP for Me y normalmente requiere un **S-user** con autorización de descarga de software.
3. Al ser software propietario de SAP, no se debe redistribuir en un repositorio público o privado salvo que la licencia SAP aplicable lo permita explícitamente.
4. Incluir binarios SAP en GitHub puede generar problemas legales y de compliance para el proyecto y para quien clone el repo.

Por eso `sapmcp` documenta cómo instalarlo, pero **no lo vendorizamos**.

### Qué sí puede contener el repo

- Documentación de instalación.
- Variables de entorno de ejemplo.
- Scripts de verificación.
- Dockerfiles que esperen el SDK montado o copiado localmente durante build privado.
- `.gitignore` para evitar subir accidentalmente `nwrfcsdk/`, `.SAR`, `.ZIP`, `.dll`, `.so` o `.dylib` del SDK.

### Qué no debe contener el repo

- `nwrfcsdk/` completo.
- `libsapnwrfc.so`.
- `libsapnwrfc.dylib`.
- `sapnwrfc.dll`.
- ZIP/SAR descargados desde SAP.
- `sapnwrfc.ini` real si contiene destinos internos.
- Credenciales SAP o SNC.

---

## 3. Enlaces oficiales

Página oficial de SAP:

- [SAP NetWeaver Remote Function Call (RFC) Software Development Kit](https://support.sap.com/en/product/connectors/nwrfcsdk.html)

SAP indica en esa página que el SDK ofrece una interfaz C/C++ para conectar con sistemas SAP desde R/3 4.6C hasta S/4HANA, y que la información de descarga de la versión 7.50 está en la **SAP Note 2573790**.

Notas SAP relevantes:

- [SAP Note 2573790 — Installation, Support, and Availability of the SAP NetWeaver RFC Library 7.50](https://me.sap.com/notes/2573790)
- [SAP Note 2573881 — Release notes / new features](https://me.sap.com/notes/2573881)
- [SAP Note 2573953 — Compile/link instructions](https://me.sap.com/notes/2573953)

> Estas notas pueden requerir login en SAP for Me y autorización asociada al S-user.

Referencia externa que confirma el requisito habitual de S-user:

- [IBM Support — Required SAP SDK libraries](https://www.ibm.com/support/pages/prerequisite-patches-libraries-and-user-permissions-ibm-infosphere-information-server-pack-sap-bw-433-44)

---

## 4. Cómo descargar el SDK

El flujo exacto de SAP for Me puede cambiar, pero el procedimiento habitual es:

1. Entrar en [SAP for Me](https://me.sap.com/) o SAP Support Portal con un S-user autorizado.
2. Abrir la [SAP Note 2573790](https://me.sap.com/notes/2573790).
3. Seguir el enlace oficial de descarga indicado en la nota.
4. Descargar **SAP NetWeaver RFC SDK 7.50** para la plataforma correcta:
   - Linux x86_64.
   - macOS si está disponible para tu arquitectura/versión.
   - Windows x64.
   - AIX u otras plataformas soportadas si aplica.
5. Extraer el archivo descargado en una ruta local controlada.
6. Configurar `SAP_NWRFC_LIB_DIR` apuntando al subdirectorio `nwrfcsdk/lib`.

Ejemplo de estructura esperada:

```text
/opt/sap/nwrfcsdk/
├── bin/
├── demo/
├── include/
└── lib/
    ├── libsapnwrfc.so        # Linux
    ├── libsapucum.so
    └── libicudecnumber.so
```

En Windows:

```text
C:\nwrfcsdk\
├── bin\
├── demo\
├── include\
└── lib\
    ├── sapnwrfc.dll
    ├── libsapucum.dll
    └── libicudecnumber.dll
```

---

## 5. Instalación en macOS

Ejemplo recomendado:

```bash
sudo mkdir -p /usr/local/sap
sudo cp -R /ruta/donde/extrajiste/nwrfcsdk /usr/local/sap/nwrfcsdk
```

Configurar entorno:

```bash
export SAP_NWRFC_LIB_DIR=/usr/local/sap/nwrfcsdk/lib
export DYLD_LIBRARY_PATH=/usr/local/sap/nwrfcsdk/lib:$DYLD_LIBRARY_PATH
```

En `.env` de `sapmcp`:

```env
SAP_NWRFC_LIB_DIR=/usr/local/sap/nwrfcsdk/lib
```

Verificación:

```bash
ls -la /usr/local/sap/nwrfcsdk/lib
python - <<'PY'
import ctypes
ctypes.CDLL('/usr/local/sap/nwrfcsdk/lib/libsapnwrfc.dylib')
print('OK: libsapnwrfc.dylib cargada')
PY
```

Notas macOS:

- En algunas versiones de macOS, `DYLD_LIBRARY_PATH` puede no propagarse desde apps GUI.
- Si usas Claude Desktop, LM Studio u otra app gráfica, puede ser más fiable definir `SAP_NWRFC_LIB_DIR` en la configuración MCP `env`.
- En Apple Silicon puede haber diferencias de arquitectura. Python, el SDK y el proceso host deben ser compatibles.

---

## 6. Instalación en Linux

Ejemplo recomendado:

```bash
sudo mkdir -p /opt/sap
sudo cp -R /ruta/donde/extrajiste/nwrfcsdk /opt/sap/nwrfcsdk
sudo chmod -R a+rX /opt/sap/nwrfcsdk
```

Configurar entorno:

```bash
export SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
export LD_LIBRARY_PATH=/opt/sap/nwrfcsdk/lib:$LD_LIBRARY_PATH
```

En `.env` de `sapmcp`:

```env
SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
```

Verificación:

```bash
ls -la /opt/sap/nwrfcsdk/lib
ldd /opt/sap/nwrfcsdk/lib/libsapnwrfc.so || true
python - <<'PY'
import ctypes
ctypes.CDLL('/opt/sap/nwrfcsdk/lib/libsapnwrfc.so')
print('OK: libsapnwrfc.so cargada')
PY
```

Si `ldd` muestra dependencias no resueltas, revisar:

- permisos;
- arquitectura 64-bit;
- `LD_LIBRARY_PATH`;
- paquetes del sistema requeridos por la distribución;
- compatibilidad glibc/plataforma.

---

## 7. Instalación en Windows

Ejemplo de ruta:

```text
C:\nwrfcsdk\lib
```

Configurar variables:

```powershell
setx SAP_NWRFC_LIB_DIR "C:\nwrfcsdk\lib"
```

Añadir al `PATH` del usuario o del sistema:

```text
C:\nwrfcsdk\lib
```

En `.env` de `sapmcp`:

```env
SAP_NWRFC_LIB_DIR=C:\nwrfcsdk\lib
```

Verificación en PowerShell:

```powershell
python - <<'PY'
import ctypes
ctypes.WinDLL(r'C:\nwrfcsdk\lib\sapnwrfc.dll')
print('OK: sapnwrfc.dll cargada')
PY
```

Notas Windows:

- Puede requerir Microsoft Visual C++ Redistributable compatible.
- La arquitectura debe coincidir: Python 64-bit con SDK 64-bit.
- Reiniciar terminal o sesión después de modificar `PATH`.

---

## 8. Configuración en sapmcp

`sapmcp` busca la librería usando configuración y rutas estándar. La forma más explícita es definir:

```env
SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
```

o en macOS:

```env
SAP_NWRFC_LIB_DIR=/usr/local/sap/nwrfcsdk/lib
```

También se puede definir por destino si fuese necesario, aunque normalmente el SDK es común para todos los destinos SAP:

```env
SAP_DEV_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
SAP_QAS_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
SAP_PRD_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
```

Comprobar desde MCP:

```json
{
  "tool": "sap_config_status",
  "arguments": {}
}
```

La salida debe mostrar información sanitizada de configuración y la librería resuelta, sin exponer contraseñas.

---

## 9. Uso con LM Studio, Claude Desktop o Codex

Cuando el host MCP es una app gráfica, no siempre hereda variables del shell. Por eso conviene pasar `SAP_NWRFC_LIB_DIR` directamente en la configuración MCP.

Ejemplo:

```json
{
  "mcpServers": {
    "sapmcp": {
      "command": "/Users/eduardoariasbravo/Developer/sapmcp/.venv/bin/sapmcp",
      "args": [],
      "cwd": "/Users/eduardoariasbravo/Developer/sapmcp",
      "env": {
        "SAP_NWRFC_LIB_DIR": "/usr/local/sap/nwrfcsdk/lib",
        "SAPMCP_READ_ONLY": "true",
        "SAPMCP_ALLOW_DANGEROUS": "false"
      }
    }
  }
}
```

Si se usa `.env`, asegurarse de que el `cwd` del MCP es la raíz del repo y de que el host carga ese archivo.

---

## 10. Docker y contenedores

### Recomendación principal

No construir una imagen pública que incluya el SAP NetWeaver RFC SDK.

En Docker hay dos patrones seguros:

1. **Montar el SDK en runtime** desde el host.
2. **Construir una imagen privada interna** copiando el SDK durante build, sin publicarla en registros públicos.

### Patrón A — Montaje en runtime

Ejemplo conceptual:

```bash
docker run --rm \
  -v /opt/sap/nwrfcsdk:/opt/sap/nwrfcsdk:ro \
  -e SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib \
  -e LD_LIBRARY_PATH=/opt/sap/nwrfcsdk/lib \
  -e SAPMCP_READ_ONLY=true \
  sapmcp:local
```

Ventajas:

- La imagen no contiene binarios SAP.
- El SDK queda gestionado por el host/empresa.
- Menor riesgo de redistribución accidental.

### Patrón B — Imagen privada interna

Ejemplo conceptual de Dockerfile privado:

```dockerfile
# No publicar esta imagen si contiene SDK propietario de SAP.
FROM python:3.11-slim

WORKDIR /app
COPY . /app
RUN pip install -e .

# Copia local durante build privado. No commitear nwrfcsdk al repo.
COPY nwrfcsdk /opt/sap/nwrfcsdk
ENV SAP_NWRFC_LIB_DIR=/opt/sap/nwrfcsdk/lib
ENV LD_LIBRARY_PATH=/opt/sap/nwrfcsdk/lib

CMD ["sapmcp"]
```

Este patrón solo debe usarse en CI/CD privado y con controles de licencia.

---

## 11. Verificación end-to-end

Una vez instalado el SDK y configurado SAP:

```bash
source .venv/bin/activate
python -m sapmcp.server
```

Desde el host MCP o cliente:

```json
{
  "tool": "sap_config_status",
  "arguments": {}
}
```

Luego:

```json
{
  "tool": "sap_ping",
  "arguments": {"destination": "default"}
}
```

Resultado esperado:

```json
{
  "ok": true,
  "function": "RFC_PING",
  "destination": "default"
}
```

Si `sap_ping` falla, diferenciar:

| Error | Causa probable |
|---|---|
| No se carga `libsapnwrfc` / `sapnwrfc.dll` | SDK no instalado, ruta mal configurada, librerías dependientes no visibles. |
| `LOGON_FAILURE` | Usuario/password/mandante/licencia SAP. |
| `LOCATION CPIC` / timeout | Host, puerto, SAProuter, firewall, message server. |
| `Name or password is incorrect` | Credenciales. |
| `partner not reached` | Red, `ASHOST`, `SYSNR`, SAProuter. |

---

## 12. Checklist rápido

- [ ] Tengo acceso legal al SAP NetWeaver RFC SDK.
- [ ] Descargué el SDK desde SAP Support Portal / SAP for Me siguiendo SAP Note 2573790.
- [ ] No he copiado el SDK al repo.
- [ ] No he subido `.SAR`, `.ZIP`, `.dll`, `.so` o `.dylib` de SAP a GitHub.
- [ ] `SAP_NWRFC_LIB_DIR` apunta a `nwrfcsdk/lib`.
- [ ] `LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH` o `PATH` incluyen la carpeta `lib` si hace falta.
- [ ] Python y SDK tienen la misma arquitectura.
- [ ] `ctypes.CDLL` / `ctypes.WinDLL` carga la librería.
- [ ] `sap_config_status` muestra librería resuelta.
- [ ] `sap_ping` responde `ok=true`.

---

## 13. Resumen ejecutivo

La librería crítica es **SAP NetWeaver RFC SDK 7.50**. Se descarga desde canales oficiales de SAP, normalmente siguiendo la **SAP Note 2573790** con un S-user autorizado.

No debe subirse a GitHub. `sapmcp` debe documentar y verificar su presencia, pero cada organización debe instalar el SDK conforme a su licencia SAP.

Con el SDK instalado y `SAP_NWRFC_LIB_DIR` configurado, `sapmcp` puede hablar con SAP mediante RFC nativo sin depender de `pyrfc`.
