from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # permite tests/uso básico antes de instalar dependencias
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "si", "sí"}


DEFAULT_DESTINATION_NAME = "default"


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _csv_preserve(name: str) -> list[str]:
    raw = os.getenv(name, "")
    values: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        key = value.upper()
        if key in seen or key == DEFAULT_DESTINATION_NAME.upper():
            continue
        seen.add(key)
        values.append(value)
    return values


def list_destinations() -> list[str]:
    """Return configured logical SAP destinations.

    ``default`` is the classic, unprefixed SAP_* connection kept for backwards
    compatibility. Additional names come from SAPMCP_DESTINATIONS.
    """

    return [DEFAULT_DESTINATION_NAME, *_csv_preserve("SAPMCP_DESTINATIONS")]


def _canonical_destination(name: str | None) -> str:
    requested = (name or "").strip()
    if not requested:
        requested = os.getenv("SAPMCP_DEFAULT_DESTINATION", "").strip()
    if not requested or requested.lower() == DEFAULT_DESTINATION_NAME:
        return DEFAULT_DESTINATION_NAME
    for configured in _csv_preserve("SAPMCP_DESTINATIONS"):
        if configured.upper() == requested.upper():
            return configured
    return requested


def _env_first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return default


def _destination_env(prefix: str, suffix: str) -> str | None:
    # Prefer the exact destination spelling from SAPMCP_DESTINATIONS, but accept
    # upper-case names as the common shell convention (cliente_X -> CLIENTE_X).
    return _env_first(f"SAP_{prefix}_{suffix}", f"SAP_{prefix.upper()}_{suffix}")


def _sap_password(user: str | None, *, destination: str = DEFAULT_DESTINATION_NAME) -> str | None:
    if _env_bool("SAPMCP_USE_KEYRING", False):
        if not user:
            raise RuntimeError("SAPMCP_USE_KEYRING=true requiere SAP_USER para buscar la credencial")
        try:
            import keyring  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("SAPMCP_USE_KEYRING=true pero el módulo opcional keyring no está instalado. Instala sapmcp[keyring].") from exc
        password = None
        if destination != DEFAULT_DESTINATION_NAME:
            password = keyring.get_password("sapmcp", f"{destination}:{user}")
        if not password:
            password = keyring.get_password("sapmcp", user)
        if not password:
            keyring_user = f"{destination}:{user}" if destination != DEFAULT_DESTINATION_NAME else user
            raise RuntimeError(f"No hay password en keyring para service='sapmcp' user='{keyring_user}'")
        return password
    return os.getenv("SAP_PASS") or os.getenv("SAP_PASSWD") or os.getenv("SAP_PASSWORD")


def _sap_destination_password(destination: str, user: str | None) -> str | None:
    if _env_bool("SAPMCP_USE_KEYRING", False) and user:
        try:
            import keyring  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("SAPMCP_USE_KEYRING=true pero el módulo opcional keyring no está instalado. Instala sapmcp[keyring].") from exc
        password = keyring.get_password("sapmcp", f"{destination}:{user}")
        if not password:
            password = keyring.get_password("sapmcp", user)
        if not password:
            raise RuntimeError(f"No hay password en keyring para service='sapmcp' user='{destination}:{user}'")
        return password
    return _destination_env(destination, "PASS") or _destination_env(destination, "PASSWD") or _destination_env(destination, "PASSWORD")


@dataclass(frozen=True)
class SapConnectionConfig:
    """Connection parameters for SAP NetWeaver RFC SDK."""

    params: dict[str, str]
    nwrfc_lib_dir: str | None = None
    nwrfc_lib_path: str | None = None
    destination: str = DEFAULT_DESTINATION_NAME

    @classmethod
    def from_env(cls) -> "SapConnectionConfig":
        return cls.from_destination(None)

    @classmethod
    def from_destination(cls, name: str | None) -> "SapConnectionConfig":
        destination = _canonical_destination(name)
        if destination != DEFAULT_DESTINATION_NAME:
            return cls._from_named_destination(destination)
        return cls._from_classic_env()

    @classmethod
    def _from_classic_env(cls) -> "SapConnectionConfig":
        # SAP SDK parameter names. We accept common aliases for convenience.
        user = os.getenv("SAP_USER")
        mapping = {
            "ASHOST": os.getenv("SAP_ASHOST") or os.getenv("SAP_HOST"),
            "SYSNR": os.getenv("SAP_SYSNR"),
            "CLIENT": os.getenv("SAP_CLIENT"),
            "USER": user,
            "PASSWD": _sap_password(user, destination=DEFAULT_DESTINATION_NAME),
            "LANG": os.getenv("SAP_LANG", "EN"),
            "MSHOST": os.getenv("SAP_MSHOST"),
            "R3NAME": os.getenv("SAP_R3NAME"),
            "GROUP": os.getenv("SAP_GROUP"),
            "SAPROUTER": os.getenv("SAP_SAPROUTER"),
            "PCS": os.getenv("SAP_PCS"),
            "TRACE": os.getenv("SAP_TRACE"),
            "SNC_LIB": os.getenv("SAP_SNC_LIB"),
            "SNC_QOP": os.getenv("SAP_SNC_QOP"),
            "SNC_MYNAME": os.getenv("SAP_SNC_MYNAME"),
            "SNC_PARTNERNAME": os.getenv("SAP_SNC_PARTNERNAME"),
            "SNC_MODE": os.getenv("SAP_SNC_MODE"),
        }
        params = {key: value for key, value in mapping.items() if value not in (None, "")}
        return cls(
            params=params,
            nwrfc_lib_dir=os.getenv("SAP_NWRFC_LIB_DIR") or None,
            nwrfc_lib_path=os.getenv("SAP_NWRFC_LIB_PATH") or None,
            destination=DEFAULT_DESTINATION_NAME,
        )

    @classmethod
    def _from_named_destination(cls, destination: str) -> "SapConnectionConfig":
        user = _destination_env(destination, "USER")
        mapping = {
            "ASHOST": _destination_env(destination, "ASHOST") or _destination_env(destination, "HOST"),
            "SYSNR": _destination_env(destination, "SYSNR"),
            "CLIENT": _destination_env(destination, "CLIENT"),
            "USER": user,
            "PASSWD": _sap_destination_password(destination, user),
            "LANG": _destination_env(destination, "LANG") or os.getenv("SAP_LANG", "EN"),
            "MSHOST": _destination_env(destination, "MSHOST"),
            "R3NAME": _destination_env(destination, "R3NAME"),
            "GROUP": _destination_env(destination, "GROUP"),
            "SAPROUTER": _destination_env(destination, "SAPROUTER"),
            "PCS": _destination_env(destination, "PCS"),
            "TRACE": _destination_env(destination, "TRACE"),
            "SNC_LIB": _destination_env(destination, "SNC_LIB"),
            "SNC_QOP": _destination_env(destination, "SNC_QOP"),
            "SNC_MYNAME": _destination_env(destination, "SNC_MYNAME"),
            "SNC_PARTNERNAME": _destination_env(destination, "SNC_PARTNERNAME"),
            "SNC_MODE": _destination_env(destination, "SNC_MODE"),
        }
        params = {key: value for key, value in mapping.items() if value not in (None, "")}
        return cls(
            params=params,
            nwrfc_lib_dir=os.getenv("SAP_NWRFC_LIB_DIR") or None,
            nwrfc_lib_path=os.getenv("SAP_NWRFC_LIB_PATH") or None,
            destination=destination,
        )

    def sanitized(self) -> dict[str, str]:
        sanitized = dict(self.params)
        if "PASSWD" in sanitized:
            sanitized["PASSWD"] = "********"
        return sanitized

    def validate(self) -> None:
        if not self.params.get("USER") or not self.params.get("PASSWD") or not self.params.get("CLIENT"):
            prefix = "SAP" if self.destination == DEFAULT_DESTINATION_NAME else f"SAP_{self.destination}"
            raise ValueError(f"Faltan {prefix}_USER/{prefix}_PASS/{prefix}_CLIENT en .env")
        direct = self.params.get("ASHOST") and self.params.get("SYSNR")
        message_server = self.params.get("MSHOST") and self.params.get("R3NAME") and self.params.get("GROUP")
        if not direct and not message_server:
            prefix = "SAP" if self.destination == DEFAULT_DESTINATION_NAME else f"SAP_{self.destination}"
            raise ValueError(f"Configura {prefix}_ASHOST + {prefix}_SYSNR, o {prefix}_MSHOST + {prefix}_R3NAME + {prefix}_GROUP")


def default_library_name() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "sapnwrfc.dll"
    if system == "darwin":
        return "libsapnwrfc.dylib"
    return "libsapnwrfc.so"


def find_nwrfc_library(config: SapConnectionConfig) -> str:
    if config.nwrfc_lib_path:
        return str(Path(config.nwrfc_lib_path).expanduser())
    lib_name = default_library_name()
    candidates: list[Path] = []
    if config.nwrfc_lib_dir:
        candidates.append(Path(config.nwrfc_lib_dir).expanduser() / lib_name)
    candidates.extend(
        [
            Path("/usr/local/sap/nwrfcsdk/lib") / lib_name,
            Path("/opt/sap/nwrfcsdk/lib") / lib_name,
            Path.home() / "nwrfcsdk" / "lib" / lib_name,
            Path("C:/nwrfcsdk/lib") / lib_name,
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    # Return first configured/default candidate for a useful error from ctypes if not found.
    return str(candidates[0]) if candidates else lib_name


READ_ONLY_PATTERNS = [
    "RFC_PING",
    "STFC_CONNECTION",
    "RFC_READ_TABLE",
    "RFC_GET_SHORT_DUMP_LIST",
    "RSLG_READ_SYSLOG",
    "BAPI_SYSLOG_READ",
    "ENQUEUE_READ",
    "TH_WPINFO",
    "TH_SERVER_LIST",
    "TH_USER_LIST",
    "BAPI_UPDREQUEST_GETLIST",
    "BAPI_USER_LOCK_STATUS",
    "BAPI_XBP_JOB_SELECT",
    "RFC_GET_*",
    "DDIF_*",
    "BAPI_*_GET*",
    "BAPI_*_DISPLAY*",
    "BAPI_*_EXIST*",
    "BAPI_*_SEARCH*",
    "BAPI_*_LIST*",
    "BAPI_USER_GET*",
]

DANGEROUS_PATTERNS = [
    "*COMMIT*",
    "*ROLLBACK*",
    "*CREATE*",
    "*CHANGE*",
    "*DELETE*",
    "*UPDATE*",
    "*POST*",
    "*CANCEL*",
    "*RELEASE*",
    "RFC_ABAP_INSTALL_AND_RUN",
    "RFC_REMOTE_PIPE",
    "SXPG_*",
]


@dataclass(frozen=True)
class SafetyPolicy:
    """Runtime guardrails for LLM-triggered SAP actions."""

    read_only: bool = True
    allow_dangerous: bool = False
    allowed_rfc: list[str] = field(default_factory=list)
    max_rows: int = 200

    @classmethod
    def from_env(cls) -> "SafetyPolicy":
        return cls(
            read_only=_env_bool("SAPMCP_READ_ONLY", True),
            allow_dangerous=_env_bool("SAPMCP_ALLOW_DANGEROUS", False),
            allowed_rfc=_csv("SAPMCP_ALLOWED_RFC"),
            max_rows=int(os.getenv("SAPMCP_MAX_ROWS", "200")),
        )

    def _matches(self, function_name: str, patterns: list[str]) -> bool:
        upper = function_name.strip().upper()
        return any(fnmatchcase(upper, pattern.upper()) for pattern in patterns)

    def classify(self, function_name: str) -> dict[str, object]:
        upper = function_name.strip().upper()
        explicitly_allowed = self._matches(upper, self.allowed_rfc) if self.allowed_rfc else False
        read_only_known = self._matches(upper, READ_ONLY_PATTERNS)
        dangerous = self._matches(upper, DANGEROUS_PATTERNS)
        return {
            "function": upper,
            "explicitly_allowed": explicitly_allowed,
            "read_only_known": read_only_known,
            "dangerous": dangerous,
            "read_only_mode": self.read_only,
            "allow_dangerous": self.allow_dangerous,
        }

    def assert_allowed(self, function_name: str, *, confirm_dangerous: bool = False) -> None:
        info = self.classify(function_name)
        name = str(info["function"])
        if info["dangerous"] and (not self.allow_dangerous or not confirm_dangerous):
            raise PermissionError(
                f"RFC {name} blocked: reason=dangerous requires=SAPMCP_ALLOW_DANGEROUS:true,confirm_dangerous:true"
            )
        if self.allowed_rfc and not info["explicitly_allowed"]:
            raise PermissionError(f"RFC {name} blocked: reason=not_in_allowlist env=SAPMCP_ALLOWED_RFC")
        if self.read_only and not info["read_only_known"] and not info["explicitly_allowed"]:
            raise PermissionError(f"RFC {name} blocked: reason=read_only_unknown_read env=SAPMCP_READ_ONLY:true")


def runtime_status(config: SapConnectionConfig, policy: SafetyPolicy) -> dict[str, object]:
    return {
        "sap_params": config.sanitized(),
        "nwrfc_lib_dir": config.nwrfc_lib_dir,
        "nwrfc_lib_path": config.nwrfc_lib_path,
        "resolved_library": find_nwrfc_library(config),
        "safety": {
            "read_only": policy.read_only,
            "allow_dangerous": policy.allow_dangerous,
            "allowed_rfc": policy.allowed_rfc,
            "max_rows": policy.max_rows,
        },
    }
