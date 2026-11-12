from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import threading
from functools import wraps
import csv
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from contextlib import contextmanager
from output_policy import is_public_output, public_product, register_public_output, REGISTRY_NAME

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

SECURITY_DIRNAME = ".hispa_security"
SECURITY_CONFIG_NAME = "security.json"
HSE_MAGIC = b"HISPA-HSE1\n"
HSK_MAGIC = "HISPA-HSK1"
PBKDF2_ITERATIONS = 600_000
PROJECT_KEY_BYTES = 32
OWNER_TOKEN_BYTES = 32
SECURITY_SCHEMA_VERSION = 2
ENV_KEY = "HISPA_SYNG_PROJECT_KEY_B64"
ENV_MODE = "HISPA_SYNG_SECURITY_MODE"
ENV_PROJECT_ID = "HISPA_SYNG_PROJECT_ID"
ENV_ROLE = "HISPA_SYNG_SECURITY_ROLE"


class SecurityError(RuntimeError):
    pass


_activity_registry_guard = threading.Lock()
_activity_locks = {}
_activity_depth = threading.local()


@contextmanager
def _project_activity_lock(project_root: Path):
    """Hold one reentrant, process-lifetime operation lock per project."""
    root = Path(project_root).resolve()
    key = str(root)
    with _activity_registry_guard:
        local_lock = _activity_locks.setdefault(key, threading.RLock())
    if not local_lock.acquire(blocking=False):
        raise SecurityError("Hay otra operación activa en este proyecto / Another project operation is active.")
    depths = getattr(_activity_depth, "projects", None)
    if depths is None:
        depths = _activity_depth.projects = {}
    try:
        if depths.get(key, 0):
            depths[key] += 1
            try:
                yield
            finally:
                depths[key] -= 1
            return
        directory = root / ".ejecuciones"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Never unlink the lock: all processes must lock the same inode.
        with (directory / "project.lock").open("a+b") as handle:
            try:
                if os.fstat(handle.fileno()).st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise SecurityError("Hay otra operación activa en este proyecto / Another project operation is active.") from exc
            depths[key] = 1
            try:
                yield
            finally:
                del depths[key]
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        local_lock.release()


def _exclusive_project_operation(function):
    @wraps(function)
    def locked(project_root, *args, **kwargs):
        with _project_activity_lock(project_root):
            return function(project_root, *args, **kwargs)
    return locked


@dataclass(frozen=True)
class AccessContext:
    project_id: str
    project_key: bytes
    role: str
    remembered: bool = False
    owner_token: bytes | None = None


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _private_directory(path: Path) -> Path:
    """Restrict private working material to the current operating-system user."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise SecurityError("El área privada no puede ser un enlace simbólico.")
    if os.name == "nt":
        identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                                  capture_output=True, text=True, check=True)
        sid = next(csv.reader(identity.stdout.strip().splitlines()))[1]
        result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                                capture_output=True, text=True)
        if result.returncode:
            raise SecurityError("No se pudo restringir el acceso al área privada de Windows.")
    else:
        path.chmod(0o700)
    return path


def _atomic_write(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name != "nt":
            path.chmod(0o600)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def _rotation_lock(project_root: Path):
    directory = security_dir(project_root)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "rotation.lock").open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SecurityError("Hay una rotación o recuperación de claves en curso.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))


def security_dir(project_root: Path) -> Path:
    return Path(project_root).resolve() / SECURITY_DIRNAME


def security_config_path(project_root: Path) -> Path:
    return security_dir(project_root) / SECURITY_CONFIG_NAME


def load_security_config(project_root: Path) -> dict | None:
    recover_interrupted_rotation(project_root)
    path = security_config_path(project_root)
    if not path.is_file():
        return None
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SecurityError(f"No se puede leer la configuración de seguridad: {exc}") from exc
    if config.get("schema_version") not in {1, SECURITY_SCHEMA_VERSION} or not config.get("project_id"):
        raise SecurityError("La configuración de seguridad del proyecto no es válida.")
    return config


def project_is_protected(project_root: Path) -> bool:
    cfg = load_security_config(project_root)
    return bool(cfg and cfg.get("mode") == "protected")


def _derive_password_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    if not isinstance(password, str) or not password:
        raise SecurityError("La contraseña no puede estar vacía.")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=int(iterations),
    )
    return kdf.derive(password.encode("utf-8"))


def _fingerprint(project_key: bytes) -> str:
    return hashlib.sha256(project_key).hexdigest()[:24]


def _owner_token_hash(owner_token: bytes) -> str:
    return hashlib.sha256(owner_token).hexdigest()


def _wrap_owner_token(project_id: str, owner_token: bytes, password: str) -> dict:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    kek = _derive_password_key(password, salt)
    aad = f"Hispa-Syng|owner-token|{project_id}|v2".encode("utf-8")
    wrapped = AESGCM(kek).encrypt(nonce, owner_token, aad)
    return {
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": PBKDF2_ITERATIONS,
        "salt_b64": _b64(salt),
        "nonce_b64": _b64(nonce),
        "wrapped_token_b64": _b64(wrapped),
    }


def unwrap_owner_token(config: dict, password: str) -> bytes | None:
    wrap = config.get("owner_password_wrap")
    if not wrap:
        return None
    try:
        salt = _unb64(wrap["salt_b64"])
        nonce = _unb64(wrap["nonce_b64"])
        wrapped = _unb64(wrap["wrapped_token_b64"])
        kek = _derive_password_key(password, salt, int(wrap["iterations"]))
        aad = f"Hispa-Syng|owner-token|{config['project_id']}|v2".encode("utf-8")
        token = AESGCM(kek).decrypt(nonce, wrapped, aad)
    except Exception as exc:
        raise SecurityError("No se ha podido validar la autoridad del propietario.") from exc
    if _owner_token_hash(token) != config.get("owner_token_hash"):
        raise SecurityError("La autoridad del propietario no corresponde a este proyecto.")
    return token


def _owner_context_valid(config: dict, context: AccessContext | None) -> bool:
    if context is None or context.role not in {"owner", "owner_recovery"}:
        return False
    if context.project_id != config.get("project_id") or _fingerprint(context.project_key) != config.get("key_fingerprint"):
        return False
    expected = config.get("owner_token_hash")
    if not expected:
        # Schema v1: owner authority is accepted only through password
        # authentication in the coordinator, never from a bearer credential.
        return False
    return bool(context.owner_token and hmac.compare_digest(_owner_token_hash(context.owner_token), expected))


def upgrade_owner_authority(project_root: Path, config: dict, project_key: bytes, password: str) -> tuple[dict, bytes]:
    """Upgrade a schema-v1 project after successful owner-password authentication.

    Schema-v1 .hsk files remain valid for data access but can no longer assert owner
    privileges. A fresh recovery credential must be created after migration.
    """
    authenticated_key = unwrap_project_key(config, password)
    if not hmac.compare_digest(authenticated_key, project_key):
        raise SecurityError("La contraseña no autentica la clave del propietario.")
    if int(config.get("schema_version", 1)) >= SECURITY_SCHEMA_VERSION and config.get("owner_token_hash"):
        token = unwrap_owner_token(config, password)
        if token is None:
            raise SecurityError("Falta la autoridad del propietario en la configuración protegida.")
        return config, token
    if _fingerprint(project_key) != config.get("key_fingerprint"):
        raise SecurityError("La clave de acceso no corresponde a este proyecto.")
    token = secrets.token_bytes(OWNER_TOKEN_BYTES)
    updated = dict(config)
    updated["schema_version"] = SECURITY_SCHEMA_VERSION
    updated["owner_token_hash"] = _owner_token_hash(token)
    updated["owner_password_wrap"] = _wrap_owner_token(config["project_id"], token, password)
    updated["updated_at"] = _now()
    path = security_config_path(project_root)
    _atomic_write(path, json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8"))
    return updated, token


def _wrap_project_key(project_id: str, project_key: bytes, password: str) -> dict:
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    kek = _derive_password_key(password, salt)
    aad = f"Hispa-Syng|project-key|{project_id}|v1".encode("utf-8")
    wrapped = AESGCM(kek).encrypt(nonce, project_key, aad)
    return {
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": PBKDF2_ITERATIONS,
        "salt_b64": _b64(salt),
        "nonce_b64": _b64(nonce),
        "wrapped_key_b64": _b64(wrapped),
    }


def unwrap_project_key(config: dict, password: str) -> bytes:
    try:
        wrap = config["password_wrap"]
        salt = _unb64(wrap["salt_b64"])
        nonce = _unb64(wrap["nonce_b64"])
        wrapped = _unb64(wrap["wrapped_key_b64"])
        kek = _derive_password_key(password, salt, int(wrap["iterations"]))
        aad = f"Hispa-Syng|project-key|{config['project_id']}|v1".encode("utf-8")
        key = AESGCM(kek).decrypt(nonce, wrapped, aad)
    except Exception as exc:
        raise SecurityError("Contraseña incorrecta o configuración de seguridad dañada.") from exc
    if _fingerprint(key) != config.get("key_fingerprint"):
        raise SecurityError("La clave obtenida no corresponde a este proyecto.")
    return key


def create_security_config(project_root: Path, password: str, *, project_key: bytes | None = None) -> tuple[dict, bytes]:
    root = Path(project_root).resolve()
    if load_security_config(root) is not None:
        raise SecurityError("Este proyecto ya tiene seguridad configurada.")
    if len(password) < 12:
        raise SecurityError("La contraseña debe tener al menos 12 caracteres.")
    project_id = str(uuid.uuid4())
    key = project_key or secrets.token_bytes(PROJECT_KEY_BYTES)
    owner_token = secrets.token_bytes(OWNER_TOKEN_BYTES)
    cfg = {
        "schema_version": SECURITY_SCHEMA_VERSION,
        "product": "Hispa-Syng v1.0",
        "project_id": project_id,
        "mode": "protected",
        "created_at": _now(),
        "updated_at": _now(),
        "key_fingerprint": _fingerprint(key),
        "password_wrap": _wrap_project_key(project_id, key, password),
        "owner_token_hash": _owner_token_hash(owner_token),
        "owner_password_wrap": _wrap_owner_token(project_id, owner_token, password),
        "encrypted_input": "Datos_data/Ingesta_provisional.hse",
        "remembered_access": "Windows DPAPI, current Windows user",
        "notes": "The password is never stored. Access .hsk files grant data access; owner authority requires an independent owner token.",
    }
    secdir = security_dir(root)
    _private_directory(secdir)
    path = security_config_path(root)
    _atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"))
    return cfg, key


@_exclusive_project_operation
def change_password(project_root: Path, project_key: bytes, new_password: str, *, owner_token: bytes | None = None) -> None:
    if len(new_password) < 12:
        raise SecurityError("La contraseña debe tener al menos 12 caracteres.")
    cfg = load_security_config(project_root)
    if not cfg:
        raise SecurityError("El proyecto no está protegido.")
    if _fingerprint(project_key) != cfg.get("key_fingerprint"):
        raise SecurityError("La clave de acceso no corresponde a este proyecto.")
    if cfg.get("owner_token_hash"):
        if not owner_token or not hmac.compare_digest(_owner_token_hash(owner_token), cfg["owner_token_hash"]):
            raise SecurityError("Esta operación requiere autoridad válida del propietario.")
    else:
        # Schema v1 must first be migrated through owner-password authentication.
        raise SecurityError("El proyecto usa un esquema de seguridad antiguo. Autentíquese con la contraseña del propietario para migrarlo antes de cambiarla.")
    cfg["password_wrap"] = _wrap_project_key(cfg["project_id"], project_key, new_password)
    cfg["owner_password_wrap"] = _wrap_owner_token(cfg["project_id"], owner_token, new_password)
    cfg["schema_version"] = SECURITY_SCHEMA_VERSION
    cfg["updated_at"] = _now()
    path = security_config_path(project_root)
    _atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"))


def _credential_payload(project_id: str, project_key: bytes, role: str, label: str, owner_token: bytes | None = None) -> dict:
    body = {
        "format": HSK_MAGIC,
        "schema_version": SECURITY_SCHEMA_VERSION,
        "project_id": project_id,
        "project_key_b64": _b64(project_key),
        "role": role,
        "label": label,
        "created_at": _now(),
        "key_fingerprint": _fingerprint(project_key),
    }
    if role == "owner_recovery":
        if owner_token is None:
            raise SecurityError("Falta la autoridad independiente del propietario para crear la recuperación.")
        body["owner_token_b64"] = _b64(owner_token)
        body["owner_token_hash"] = _owner_token_hash(owner_token)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body["integrity_hmac_sha256"] = hmac.new(project_key, canonical, hashlib.sha256).hexdigest()
    return body


def write_credential(path: Path, config: dict, project_key: bytes, *, role: str, label: str, owner_token: bytes | None = None) -> Path:
    if role not in {"access", "owner_recovery"}:
        raise SecurityError("Rol de credencial no válido.")
    if _fingerprint(project_key) != config.get("key_fingerprint"):
        raise SecurityError("La clave no corresponde al proyecto.")
    if role == "owner_recovery":
        expected = config.get("owner_token_hash")
        if not expected or owner_token is None or not hmac.compare_digest(_owner_token_hash(owner_token), expected):
            raise SecurityError("No existe autoridad válida del propietario para crear esta recuperación.")
    payload = _credential_payload(config["project_id"], project_key, role, label, owner_token)
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    return path


def read_credential(path: Path, config: dict) -> AccessContext:
    path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SecurityError(f"No se puede leer la credencial .hsk: {exc}") from exc
    if payload.get("format") != HSK_MAGIC or payload.get("schema_version") not in {1, SECURITY_SCHEMA_VERSION}:
        raise SecurityError("El archivo no es una credencial Hispa-Syng válida.")
    if payload.get("project_id") != config.get("project_id"):
        raise SecurityError("La credencial pertenece a otro proyecto Hispa-Syng.")
    try:
        key = _unb64(payload["project_key_b64"])
    except Exception as exc:
        raise SecurityError("La credencial no contiene una clave válida.") from exc
    if _fingerprint(key) != config.get("key_fingerprint"):
        raise SecurityError("La credencial no corresponde a la clave activa del proyecto.")
    check = dict(payload)
    expected = check.pop("integrity_hmac_sha256", "")
    canonical = json.dumps(check, sort_keys=True, separators=(",", ":")).encode("utf-8")
    actual = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, actual):
        raise SecurityError("La credencial está dañada o ha sido modificada.")
    requested_role = payload.get("role", "access")
    owner_token = None
    role = "access"
    if requested_role == "owner_recovery":
        # Owner privilege is deliberately independent from the project data key.
        # Schema-v1 recovery credentials are downgraded to data access because
        # their role could be forged by anyone holding an access credential.
        if int(config.get("schema_version", 1)) >= SECURITY_SCHEMA_VERSION and int(payload.get("schema_version", 1)) >= SECURITY_SCHEMA_VERSION:
            try:
                owner_token = _unb64(payload["owner_token_b64"])
            except Exception as exc:
                raise SecurityError("La credencial de recuperación no contiene autoridad válida del propietario.") from exc
            expected_owner = config.get("owner_token_hash")
            if not expected_owner or not hmac.compare_digest(_owner_token_hash(owner_token), expected_owner):
                raise SecurityError("La credencial no tiene autoridad de propietario válida para este proyecto.")
            role = "owner_recovery"
    return AccessContext(config["project_id"], key, role, remembered=False, owner_token=owner_token)


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_libraries():
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.POINTER(_DATA_BLOB)
    crypt32.CryptProtectData.argtypes = [pointer, wintypes.LPCWSTR, pointer, ctypes.c_void_p,
                                        ctypes.c_void_p, wintypes.DWORD, pointer]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [pointer, ctypes.c_void_p, pointer, ctypes.c_void_p,
                                          ctypes.c_void_p, wintypes.DWORD, pointer]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _dpapi_protect(data: bytes, entropy: bytes) -> bytes:
    if os.name != "nt":
        raise SecurityError("Recordar el acceso mediante DPAPI solo está disponible en Windows.")
    crypt32, kernel32 = _dpapi_libraries()
    inbuf = ctypes.create_string_buffer(data)
    entbuf = ctypes.create_string_buffer(entropy)
    in_blob = _DATA_BLOB(len(data), ctypes.cast(inbuf, ctypes.POINTER(ctypes.c_byte)))
    ent_blob = _DATA_BLOB(len(entropy), ctypes.cast(entbuf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(in_blob), "Hispa-Syng", ctypes.byref(ent_blob), None, None, 1, ctypes.byref(out_blob)):
        raise SecurityError("Windows no pudo proteger la credencial local.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes, entropy: bytes) -> bytes:
    if os.name != "nt":
        raise SecurityError("El acceso recordado con DPAPI solo puede abrirse en Windows.")
    crypt32, kernel32 = _dpapi_libraries()
    inbuf = ctypes.create_string_buffer(data)
    entbuf = ctypes.create_string_buffer(entropy)
    in_blob = _DATA_BLOB(len(data), ctypes.cast(inbuf, ctypes.POINTER(ctypes.c_byte)))
    ent_blob = _DATA_BLOB(len(entropy), ctypes.cast(entbuf, ctypes.POINTER(ctypes.c_byte)))
    out_blob = _DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, ctypes.byref(ent_blob), None, None, 1, ctypes.byref(out_blob)):
        raise SecurityError("Windows no pudo abrir la credencial local recordada.")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _local_access_path(project_id: str) -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path.home() / ".local" / "share"
    return base / "Hispa-Syng" / "credentials" / f"{project_id}.dpapi"


def remember_access(context: AccessContext) -> Path:
    if os.name != "nt":
        raise SecurityError("La opción 'Recordar acceso' está disponible únicamente en Windows.")
    payload = json.dumps(
        {
            "schema_version": 1,
            "project_id": context.project_id,
            "project_key_b64": _b64(context.project_key),
            "role": context.role,
            "owner_token_b64": _b64(context.owner_token) if context.owner_token else None,
            "created_at": _now(),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    entropy = hashlib.sha256(("Hispa-Syng|" + context.project_id).encode("utf-8")).digest()
    protected = _dpapi_protect(payload, entropy)
    path = _local_access_path(context.project_id)
    _private_directory(path.parent)
    _atomic_write(path, protected)
    return path


def load_remembered_access(config: dict) -> AccessContext | None:
    path = _local_access_path(config["project_id"])
    if not path.is_file() or os.name != "nt":
        return None
    try:
        entropy = hashlib.sha256(("Hispa-Syng|" + config["project_id"]).encode("utf-8")).digest()
        payload = json.loads(_dpapi_unprotect(path.read_bytes(), entropy).decode("utf-8"))
        key = _unb64(payload["project_key_b64"])
        if payload.get("project_id") != config["project_id"] or _fingerprint(key) != config.get("key_fingerprint"):
            return None
        role = payload.get("role", "access")
        owner_token = None
        if role in {"owner", "owner_recovery"}:
            raw_owner = payload.get("owner_token_b64")
            expected_owner = config.get("owner_token_hash")
            if not raw_owner or not expected_owner:
                return None
            owner_token = _unb64(raw_owner)
            if not hmac.compare_digest(_owner_token_hash(owner_token), expected_owner):
                return None
        else:
            role = "access"
        return AccessContext(config["project_id"], key, role, remembered=True, owner_token=owner_token)
    except Exception:
        return None


def forget_remembered_access(project_id: str) -> bool:
    path = _local_access_path(project_id)
    if path.exists():
        path.unlink()
        return True
    return False


def access_from_environment(project_root: Path) -> AccessContext | None:
    cfg = load_security_config(project_root)
    if not cfg or cfg.get("mode") != "protected":
        return None
    raw = os.environ.get(ENV_KEY)
    if not raw:
        return None
    try:
        key = _unb64(raw)
    except Exception:
        return None
    if _fingerprint(key) != cfg.get("key_fingerprint"):
        return None
    if os.environ.get(ENV_PROJECT_ID) != cfg["project_id"]:
        return None
    # Children receive data access only. An environment role is not owner proof.
    return AccessContext(cfg["project_id"], key, "access", remembered=False)


def export_access_environment(context: AccessContext) -> dict[str, str]:
    env = os.environ.copy()
    env[ENV_KEY] = _b64(context.project_key)
    env[ENV_MODE] = "protected"
    env[ENV_PROJECT_ID] = context.project_id
    env[ENV_ROLE] = context.role
    return env


def open_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.pop(ENV_KEY, None)
    env[ENV_MODE] = "open"
    env.pop(ENV_PROJECT_ID, None)
    env.pop(ENV_ROLE, None)
    return env


def encrypt_bytes(plaintext: bytes, project_key: bytes, project_id: str, original_name: str, mime_type: str | None = None) -> bytes:
    nonce = secrets.token_bytes(12)
    aad = f"Hispa-Syng|file|{project_id}|v1|{original_name}".encode("utf-8")
    ciphertext = AESGCM(project_key).encrypt(nonce, plaintext, aad)
    header = {
        "schema_version": 1,
        "project_id": project_id,
        "original_name": original_name,
        "mime_type": mime_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
        "nonce_b64": _b64(nonce),
        "sha256": hashlib.sha256(plaintext).hexdigest(),
        "size_bytes": len(plaintext),
        "created_at": _now(),
    }
    header_bytes = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return HSE_MAGIC + struct.pack(">I", len(header_bytes)) + header_bytes + ciphertext


def decrypt_bytes(blob: bytes, project_key: bytes, expected_project_id: str | None = None) -> tuple[bytes, dict]:
    if not blob.startswith(HSE_MAGIC):
        raise SecurityError("El archivo no es un contenedor cifrado Hispa-Syng válido.")
    offset = len(HSE_MAGIC)
    if len(blob) < offset + 4:
        raise SecurityError("El contenedor cifrado está truncado.")
    header_len = struct.unpack(">I", blob[offset:offset + 4])[0]
    start = offset + 4
    end = start + header_len
    if end > len(blob) or header_len > 1024 * 1024:
        raise SecurityError("La cabecera del archivo cifrado está truncada o excede el límite permitido.")
    try:
        header = json.loads(blob[start:end].decode("utf-8"))
    except Exception as exc:
        raise SecurityError("La cabecera del archivo cifrado está dañada.") from exc
    if not isinstance(header, dict):
        raise SecurityError("La cabecera del archivo cifrado no es válida.")
    if expected_project_id and header.get("project_id") != expected_project_id:
        raise SecurityError("El archivo cifrado pertenece a otro proyecto.")
    try:
        nonce = _unb64(header["nonce_b64"])
        aad = f"Hispa-Syng|file|{header['project_id']}|v1|{header['original_name']}".encode("utf-8")
        plaintext = AESGCM(project_key).decrypt(nonce, blob[end:], aad)
    except Exception as exc:
        raise SecurityError("No se ha podido descifrar el archivo: credencial incorrecta o archivo dañado.") from exc
    if hashlib.sha256(plaintext).hexdigest() != header.get("sha256"):
        raise SecurityError("La verificación de integridad del archivo descifrado ha fallado.")
    return plaintext, header


def encrypt_file(source: Path, destination: Path, config: dict, project_key: bytes, *, remove_source: bool = False) -> Path:
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    plaintext = source.read_bytes()
    blob = encrypt_bytes(plaintext, project_key, config["project_id"], source.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    _atomic_write(tmp, blob)
    check, _ = decrypt_bytes(tmp.read_bytes(), project_key, config["project_id"])
    if hashlib.sha256(check).digest() != hashlib.sha256(plaintext).digest():
        tmp.unlink(missing_ok=True)
        raise SecurityError(f"No se pudo verificar el cifrado de {source.name}.")
    os.replace(tmp, destination)
    if remove_source and source != destination:
        source.unlink()
    return destination


def decrypt_file(source: Path, destination: Path, config: dict, project_key: bytes) -> Path:
    plaintext, header = decrypt_bytes(Path(source).read_bytes(), project_key, config["project_id"])
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    tmp.write_bytes(plaintext)
    os.replace(tmp, destination)
    return destination


def encrypt_project_input(project_root: Path, config: dict, project_key: bytes) -> Path | None:
    data_dir = Path(project_root).resolve() / "Datos_data"
    plain = data_dir / "Ingesta_provisional.xlsx"
    encrypted = data_dir / "Ingesta_provisional.hse"
    if encrypted.exists() and not plain.exists():
        return encrypted
    if not plain.exists():
        return encrypted if encrypted.exists() else None
    return encrypt_file(plain, encrypted, config, project_key, remove_source=True)


def decrypt_project_input(project_root: Path, config: dict, project_key: bytes, *, remove_encrypted: bool = False) -> Path | None:
    data_dir = Path(project_root).resolve() / "Datos_data"
    encrypted = data_dir / "Ingesta_provisional.hse"
    plain = data_dir / "Ingesta_provisional.xlsx"
    if plain.exists() and not encrypted.exists():
        return plain
    if not encrypted.exists():
        return plain if plain.exists() else None
    decrypt_file(encrypted, plain, config, project_key)
    if remove_encrypted:
        encrypted.unlink(missing_ok=True)
    return plain


def _locked_html(original_name: str, encrypted_name: str, language: str) -> str:
    if language == "EN":
        title = "Protected Hispa-Syng content"
        body = (
            "This file contains sensitive information and is encrypted. "
            "Open Hispa-Syng.bat, choose Security and access, then Open protected file, "
            f"and select {encrypted_name}."
        )
    else:
        title = "Contenido protegido de Hispa-Syng"
        body = (
            "Este archivo contiene información sensible y está cifrado. "
            "Abra Hispa-Syng.bat, seleccione Seguridad y accesos y después Abrir archivo protegido; "
            f"seleccione {encrypted_name}."
        )
    original_label = "Original file" if language == "EN" else "Archivo original"
    encrypted_label = "Encrypted container" if language == "EN" else "Contenedor cifrado"
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{title}</title><style>body{{font-family:Arial,sans-serif;max-width:720px;margin:10vh auto;padding:28px;color:#17313b;background:#f5f8fa}}.card{{background:white;border-radius:12px;padding:26px;box-shadow:0 10px 30px rgba(0,0,0,.12)}}code{{word-break:break-all}}</style></head><body><div class=\"card\"><h1>{title}</h1><p>{body}</p><p><b>{original_label}:</b> <code>{original_name}</code></p><p><b>{encrypted_label}:</b> <code>{encrypted_name}</code></p></div></body></html>"""


def _sensitive_output_candidates(run_root: Path) -> list[Path]:
    root = Path(run_root)
    candidates: set[Path] = set()
    if not root.is_dir():
        return []
    # Map 1 in every distributed location plus the assignment QC map.
    for pattern in (
        "03_mapas/Mapa1_*.html",
        "03_maps/Map1_*.html",
        "Publicacion_Web/mapas/Mapa1_*.html",
        "Web_Publication/maps/Map1_*.html",
        "07_control_calidad/Mapa_QC_Asignacion_Espacial.html",
        "07_quality_control/Spatial_Assignment_QC_Map.html",
    ):
        candidates.update(root.glob(pattern))
    # Observation-level spatial tables contain the original records and/or
    # coordinates. Aggregate cell/species metrics remain available.
    for pattern in (
        "04_tablas/base_espacial/observaciones_asignadas.csv",
        "04_tablas/base_espacial/Base_Maestra_Filtrada.csv",
        "04_tables/spatial_base/assigned_observations.csv",
        "04_tables/spatial_base/Filtered_Master_Database.csv",
    ):
        candidates.update(root.glob(pattern))
    # All intermediate outputs can contain observation-level or coordinate-level data.
    for dirname in ("02_intermedios", "02_intermediate"):
        directory = root / dirname
        if directory.is_dir():
            candidates.update(path for path in directory.rglob("*") if path.is_file())
    # Selected coordinate-level QA products, while leaving summary/manifests available.
    qa_patterns = (
        "*asignacion*espacial*", "*spatial*assignment*", "*coordenad*", "*coordinate*",
        "*puntos_fuera*", "*outside_grid*", "*canonical*", "*nearest*", "*region_assignment*",
        "*asignacion_regional*",
    )
    for dirname in ("07_control_calidad", "07_quality_control"):
        directory = root / dirname
        if directory.is_dir():
            for path in directory.rglob("*"):
                if path.is_file() and any(path.match(pat) or pat.strip("*").casefold() in path.name.casefold() for pat in qa_patterns):
                    candidates.add(path)
    # All web download bundles are access-controlled products.
    for dirname in ("Publicacion_Web/descargas", "Web_Publication/downloads"):
        directory = root / dirname
        if directory.is_dir():
            candidates.update(path for path in directory.rglob("*") if path.is_file())
    # Priority-area downloadable/report products requested as sensitive.
    for dirname in ("09_zonas_prioritarias_conservacion", "09_priority_conservation_areas"):
        directory = root / dirname
        if directory.is_dir():
            for path in directory.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".docx", ".xlsx", ".zip"}:
                    candidates.add(path)
    # All data/document formats, including unexpected names, are private by
    # default. HTML pages exposing only aggregate map products remain usable.
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() == ".hse":
            continue
        if _requires_encryption(path):
            candidates.add(path)
    return sorted(candidates)


def _requires_encryption(path: Path) -> bool:
    return path.suffix.lower() != ".hse" and not is_public_output(path)


def _is_locked_html(path: Path) -> bool:
    if path.suffix.lower() != ".html":
        return False
    content = path.read_text(encoding="utf-8", errors="replace")
    english = _locked_html(path.name, path.name + ".hse", "EN")
    previous_english = english.replace("<b>Original file:</b>", "<b>Archivo original:</b>").replace("<b>Encrypted container:</b>", "<b>Contenedor cifrado:</b>")
    return content in {_locked_html(path.name, path.name + ".hse", "ES"), english, previous_english}


def verify_protected_tree(root: Path, config: dict, project_key: bytes) -> dict:
    checked = 0
    inventory = []
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            raise SecurityError("Los resultados protegidos no pueden contener enlaces simbólicos.")
        if not path.is_file():
            continue
        if path.suffix.lower() == ".hse":
            decrypt_bytes(path.read_bytes(), project_key, config["project_id"])
            checked += 1
        elif _requires_encryption(path):
            if not _is_locked_html(path) or not path.with_name(path.name + ".hse").is_file():
                raise SecurityError(f"Producto sensible sin proteger: {path.name}")
        product = public_product(path)
        classification = "encrypted" if path.suffix.lower() == ".hse" else "locked_placeholder" if _is_locked_html(path) else "public"
        inventory.append({"file": path.relative_to(root).as_posix(), "classification": classification,
                          "reason": product or ("authenticated encrypted container" if classification == "encrypted" else "placeholder backed by authenticated container"),
                          "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {"verified_containers": checked, "inventory": inventory}


def _bilingual_sensitive_candidates(bundle: Path) -> list[Path]:
    candidates: set[Path] = set()
    if not bundle.is_dir():
        return []
    for path in bundle.rglob("*"):
        if not path.is_file():
            continue
        low = path.name.casefold()
        parts = {p.casefold() for p in path.parts}
        if "descargas" in parts or "downloads" in parts or _requires_encryption(path):
            candidates.add(path)
        elif path.suffix.lower() == ".html" and (low.startswith("mapa1_") or low.startswith("map1_")):
            candidates.add(path)
    return sorted(candidates)


def _protect_file_in_place(path: Path, config: dict, project_key: bytes, language: str) -> Path:
    if path.suffix.lower() == ".hse" or not path.exists():
        return path
    encrypted = path.with_name(path.name + ".hse")
    if _is_locked_html(path) and encrypted.exists():
        decrypt_bytes(encrypted.read_bytes(), project_key, config["project_id"])
        return encrypted
    encrypt_file(path, encrypted, config, project_key, remove_source=True)
    if path.suffix.lower() == ".html":
        _atomic_write(path, _locked_html(path.name, encrypted.name, language).encode("utf-8"))
    return encrypted


def _refresh_publication_manifest(publication_root: Path) -> None:
    """Refresh a static-publication integrity manifest after encryption.

    Encryption changes filenames and replaces protected HTML pages with locked
    placeholders. Keeping the manifest synchronized avoids stale hashes that
    could otherwise be mistaken for corruption.
    """
    root = Path(publication_root)
    if not root.is_dir():
        return
    manifest = None
    for name in ("manifiesto.json", "manifest.json"):
        candidate = root / name
        if candidate.is_file():
            manifest = candidate
            break
    if manifest is None:
        return
    payload = {"product": "Hispa-Syng v1.0"}
    records = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p != manifest and p.name != REGISTRY_NAME):
        records.append({
            "file": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    payload["files"] = records
    payload["security_refreshed_at"] = _now()
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    register_public_output(manifest, "integrity_manifest", payload)


def protect_generated_outputs(project_root: Path, execution_id: str, context: AccessContext, *, results_root: Path | None = None) -> dict:
    root = Path(project_root).resolve()
    cfg = load_security_config(root)
    if not cfg or cfg.get("mode") != "protected":
        return {"protected": False, "files": 0}
    if context.project_id != cfg["project_id"] or _fingerprint(context.project_key) != cfg.get("key_fingerprint"):
        raise SecurityError("No existe una clave válida para proteger las salidas.")
    result_root = Path(results_root) if results_root is not None else root / "Resultados"
    run_roots = [result_root / f"ejecucion_{execution_id}_ESP", result_root / f"run_{execution_id}_EN"]
    count = 0
    records = []
    for run, lang in zip(run_roots, ("ES", "EN")):
        for path in _sensitive_output_candidates(run):
            try:
                encrypted = _protect_file_in_place(path, cfg, context.project_key, lang)
                count += 1
                records.append({"original": str(path.relative_to(result_root)), "encrypted": str(encrypted.relative_to(result_root))})
            except FileNotFoundError:
                pass
    bundle = result_root / f"Publicacion_Web_Bilingue_{execution_id}"
    for path in _bilingual_sensitive_candidates(bundle):
        lang = "EN" if "EN" in path.parts else "ES"
        try:
            encrypted = _protect_file_in_place(path, cfg, context.project_key, lang)
            count += 1
            records.append({"original": str(path.relative_to(result_root)), "encrypted": str(encrypted.relative_to(result_root))})
        except FileNotFoundError:
            pass
    # Refresh publication manifests after filenames/hashes changed through encryption.
    for run in run_roots:
        _refresh_publication_manifest(run / "Publicacion_Web")
        _refresh_publication_manifest(run / "Web_Publication")
    _refresh_publication_manifest(bundle / "ES")
    _refresh_publication_manifest(bundle / "EN")
    audit_dir = security_dir(root) / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit = audit_dir / f"protected_outputs_{execution_id}.json"
    verification = verify_protected_tree(result_root, cfg, context.project_key)
    _atomic_write(audit, json.dumps({"execution_id": execution_id, "protected_at": _now(), "files": records, "inventory": verification["inventory"]}, ensure_ascii=False, indent=2).encode("utf-8"))
    return {"protected": True, "files": count, "audit": str(audit)}


def _powershell_dialog(save: bool, title: str, filter_text: str, default_name: str = "") -> Path | None:
    if os.name != "nt":
        return None
    cls = "SaveFileDialog" if save else "OpenFileDialog"
    code = [
        "Add-Type -AssemblyName System.Windows.Forms",
        f"$d = New-Object System.Windows.Forms.{cls}",
        f"$d.Title = {json.dumps(title)}",
        f"$d.Filter = {json.dumps(filter_text)}",
    ]
    if default_name:
        code.append(f"$d.FileName = {json.dumps(default_name)}")
    code += ["if ($d.ShowDialog() -eq 'OK') { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Write-Output $d.FileName }"]
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", ";".join(code)], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    value = result.stdout.strip()
    return Path(value).expanduser().resolve() if value else None


def choose_open_file(title: str, filter_text: str) -> Path | None:
    return _powershell_dialog(False, title, filter_text)


def choose_save_file(title: str, filter_text: str, default_name: str) -> Path | None:
    return _powershell_dialog(True, title, filter_text, default_name)


def choose_folder(title: str) -> Path | None:
    if os.name != "nt":
        return None
    code = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
        f"$d.Description={json.dumps(title)};"
        "if($d.ShowDialog()-eq 'OK'){[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;Write-Output $d.SelectedPath}"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", code], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    value = result.stdout.strip()
    return Path(value).expanduser().resolve() if value else None


def decrypt_to_temp_and_open(encrypted_path: Path, config: dict, context: AccessContext) -> Path:
    encrypted_path = Path(encrypted_path).resolve()
    plaintext, header = decrypt_bytes(encrypted_path.read_bytes(), context.project_key, config["project_id"])
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Hispa-Syng" / "decrypted-temp" / config["project_id"]
    _private_directory(base)
    name = str(header.get("original_name", encrypted_path.stem))
    if Path(name).name != name or "\\" in name or name in {"", ".", ".."}:
        raise SecurityError("Nombre de archivo original no válido.")
    destination = base / name
    _atomic_write(destination, plaintext)
    if os.name == "nt":
        os.startfile(str(destination))
    else:
        try:
            subprocess.Popen(["xdg-open", str(destination)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    return destination


def cleanup_decrypted_temp(config: dict) -> None:
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Hispa-Syng" / "decrypted-temp" / config["project_id"]
    if base.is_dir():
        shutil.rmtree(base, ignore_errors=True)


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {".venv", ".git", ".cache", ".ejecuciones", "Resultados", "__pycache__"}
    return {name for name in names if name in ignored or name.endswith((".pyc", ".pyo", ".hsk", ".dpapi"))}



def decrypt_all_project_files(project_root: Path, config: dict, project_key: bytes, *, remove_encrypted: bool = True) -> int:
    """Decrypt every Hispa-Syng .hse container in a project tree.

    This is used only for an explicitly requested fully open copy or for a
    transactional rollback. Existing locked HTML placeholders are overwritten
    by their authentic decrypted HTML.
    """
    root = Path(project_root).resolve()
    if _fingerprint(project_key) != config.get("key_fingerprint"):
        raise SecurityError("La clave de acceso no corresponde a este proyecto.")
    count = 0
    for source in sorted(p for p in root.rglob("*.hse") if SECURITY_DIRNAME not in p.parts):
        plaintext, header = decrypt_bytes(source.read_bytes(), project_key, config["project_id"])
        original_name = Path(str(header.get("original_name") or source.name[:-4])).name
        destination = source.parent / original_name
        tmp = destination.with_name(destination.name + ".decrypting")
        tmp.write_bytes(plaintext)
        if hashlib.sha256(plaintext).hexdigest() != header.get("sha256"):
            tmp.unlink(missing_ok=True)
            raise SecurityError(f"Falló la verificación al abrir {source.name}.")
        os.replace(tmp, destination)
        if remove_encrypted:
            source.unlink(missing_ok=True)
        count += 1
    return count


@_exclusive_project_operation
def protect_all_existing_outputs(project_root: Path, context: AccessContext) -> dict:
    """Recover private runs and protect all existing output data by default."""
    root = Path(project_root).resolve()
    cfg = load_security_config(root)
    if not cfg or cfg.get("mode") != "protected":
        raise SecurityError("El proyecto no está protegido.")
    if context.project_id != cfg["project_id"] or _fingerprint(context.project_key) != cfg.get("key_fingerprint"):
        raise SecurityError("No existe una clave válida para proteger las salidas.")
    from secure_execution import recover_pending_executions
    recovered = recover_pending_executions(root, context)
    result_root = root / "Resultados"
    records = []
    for path in _sensitive_output_candidates(result_root):
        if path.suffix.lower() == ".hse" or _is_locked_html(path):
            continue
        language = "EN" if any(part.endswith("_EN") or part == "EN" for part in path.parts) else "ES"
        encrypted = _protect_file_in_place(path, cfg, context.project_key, language)
        records.append({"original": str(path.relative_to(root)), "encrypted": str(encrypted.relative_to(root))})
    for name in ("manifiesto.json", "manifest.json"):
        for manifest in result_root.rglob(name):
            _refresh_publication_manifest(manifest.parent)
    verification = verify_protected_tree(result_root, cfg, context.project_key)
    audit = security_dir(root) / "audits" / ("protected_existing_outputs_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")
    _atomic_write(audit, json.dumps({"protected_at": _now(), "files": records, "recovered_executions": recovered, "inventory": verification["inventory"]}, ensure_ascii=False, indent=2).encode("utf-8"))
    return {"protected": True, "files": len(records), "audit": str(audit), "recovered_executions": recovered}


def _prepare_project_distribution(project_root: Path, context: AccessContext | None) -> None:
    """Authenticate and recover the source before creating any distributable copy."""
    cfg = load_security_config(project_root)
    if cfg is None:
        return
    if not _owner_context_valid(cfg, context):
        raise SecurityError("Se necesita autoridad válida del propietario para preparar una copia.")
    # Recovery failures propagate before a destination or credential is created.
    protect_all_existing_outputs(project_root, context)


@_exclusive_project_operation
def create_open_copy(project_root: Path, destination: Path, context: AccessContext | None) -> Path:
    source = Path(project_root).resolve()
    destination = Path(destination).expanduser().resolve()
    if destination.is_relative_to(source):
        raise SecurityError("La copia debe crearse fuera de la carpeta de origen.")
    if destination.exists():
        raise SecurityError("La carpeta de destino ya existe.")
    _prepare_project_distribution(source, context)
    shutil.copytree(source, destination, ignore=_copy_ignore)
    try:
        cfg = load_security_config(destination)
        if cfg:
            if context is None or context.project_id != cfg["project_id"] or not _owner_context_valid(cfg, context):
                raise SecurityError("Se necesita autoridad del propietario para crear una copia abierta.")
            decrypt_all_project_files(destination, cfg, context.project_key, remove_encrypted=True)
            shutil.rmtree(security_dir(destination), ignore_errors=True)
        return destination
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


@_exclusive_project_operation
def create_protected_copy(
    project_root: Path,
    destination: Path,
    password: str,
    recovery_path: Path,
    source_context: AccessContext | None = None,
) -> tuple[Path, Path]:
    source = Path(project_root).resolve()
    destination = Path(destination).expanduser().resolve()
    recovery_path = Path(recovery_path).expanduser().resolve()
    if destination.is_relative_to(source):
        raise SecurityError("La copia debe crearse fuera de la carpeta de origen.")
    if recovery_path.is_relative_to(destination) or recovery_path.is_relative_to(source):
        raise SecurityError("Guarde la recuperación fuera de ambos proyectos.")
    if destination.exists():
        raise SecurityError("La carpeta de destino ya existe.")
    _prepare_project_distribution(source, source_context)
    shutil.copytree(source, destination, ignore=_copy_ignore)
    try:
        # Normalize the copied tree to plaintext first. This prevents outputs
        # encrypted with the source key from becoming orphaned in the new copy.
        copied_cfg = load_security_config(destination)
        if copied_cfg:
            if source_context is None or source_context.project_id != copied_cfg["project_id"] or not _owner_context_valid(copied_cfg, source_context):
                raise SecurityError("Se necesita autoridad del propietario del proyecto de origen para crear una nueva copia protegida.")
            decrypt_all_project_files(destination, copied_cfg, source_context.project_key, remove_encrypted=True)
            shutil.rmtree(security_dir(destination), ignore_errors=True)
        plain = destination / "Datos_data" / "Ingesta_provisional.xlsx"
        if not plain.exists():
            raise SecurityError("No se encontró Ingesta_provisional.xlsx para preparar la copia protegida.")
        cfg, key = create_security_config(destination, password)
        owner_token = unwrap_owner_token(cfg, password)
        encrypt_project_input(destination, cfg, key)
        ctx = AccessContext(cfg["project_id"], key, "owner", remembered=False, owner_token=owner_token)
        protect_all_existing_outputs(destination, ctx)
        rec = write_credential(recovery_path, cfg, key, role="owner_recovery", label="Recuperación del propietario", owner_token=owner_token)
        return destination, rec
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def recover_interrupted_rotation(project_root: Path) -> bool:
    if not (security_dir(project_root) / "rotation" / "journal.json").exists():
        return False
    with _project_activity_lock(project_root), _rotation_lock(project_root):
        return _recover_rotation_unlocked(project_root)


def _recover_rotation_unlocked(project_root: Path) -> bool:
    """Roll back an uncommitted rotation or finish cleanup after durable commit."""
    root = Path(project_root).resolve()
    transaction = security_dir(root) / "rotation"
    journal_path = transaction / "journal.json"
    if not journal_path.exists():
        return False
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    committed = (transaction / "COMMITTED").exists()
    if not committed:
        # Backups are complete before the first active replacement. Never delete
        # them until recovery has succeeded, even if rollback itself is interrupted.
        for record in journal["files"]:
            target = root / record["path"]
            if not target.resolve().is_relative_to(root):
                raise SecurityError("Ruta de recuperación de rotación no válida.")
            backup = transaction / record["backup"]
            if not backup.exists():
                raise SecurityError("Falta una copia necesaria para recuperar la rotación.")
            _atomic_write(target, backup.read_bytes())
        _atomic_write(security_config_path(root), (transaction / "old_security.json").read_bytes())
        recovery = Path(journal["recovery_path"])
        backup = transaction / "old_recovery.hsk"
        if backup.exists():
            _atomic_write(recovery, backup.read_bytes())
        else:
            recovery.unlink(missing_ok=True)
    else:
        # Ciphertext hashes changed; update the informational manifests too.
        result_root = root / "Resultados"
        for name in ("manifiesto.json", "manifest.json"):
            for manifest in result_root.rglob(name):
                _refresh_publication_manifest(manifest.parent)
        forget_remembered_access(journal["project_id"])
    shutil.rmtree(transaction)
    return True


@_exclusive_project_operation
def rotate_project_key(project_root: Path, old_context: AccessContext, new_password: str, recovery_path: Path) -> AccessContext:
    recover_interrupted_rotation(project_root)
    with _rotation_lock(project_root):
        return _rotate_project_key_unlocked(project_root, old_context, new_password, recovery_path)


def _rotate_project_key_unlocked(project_root: Path, old_context: AccessContext, new_password: str, recovery_path: Path) -> AccessContext:
    """Recoverable key rotation for the active project; old copies stay readable."""
    root = Path(project_root).resolve()
    cfg = load_security_config(root)
    if not cfg or not _owner_context_valid(cfg, old_context):
        raise SecurityError("Solo el propietario con autoridad válida puede rotar la clave.")
    if len(new_password) < 12:
        raise SecurityError("La contraseña debe tener al menos 12 caracteres.")
    pending = security_dir(root) / "pending"
    if pending.exists() and any(pending.glob("*.json")):
        raise SecurityError("Recupere las ejecuciones pendientes antes de rotar la clave.")
    recovery_path = Path(recovery_path).expanduser().resolve()
    if recovery_path.is_relative_to(root):
        raise SecurityError("Guarde la recuperación fuera del proyecto.")
    new_key = secrets.token_bytes(PROJECT_KEY_BYTES)
    new_owner_token = secrets.token_bytes(OWNER_TOKEN_BYTES)
    transaction = security_dir(root) / "rotation"
    if transaction.exists():
        shutil.rmtree(transaction)
    _private_directory(transaction)
    journal = {"project_id": cfg["project_id"], "recovery_path": str(recovery_path), "files": []}
    try:
        _atomic_write(transaction / "old_security.json", security_config_path(root).read_bytes())
        if recovery_path.exists():
            _atomic_write(transaction / "old_recovery.hsk", recovery_path.read_bytes())
        files = sorted(p for p in root.rglob("*.hse") if SECURITY_DIRNAME not in p.parts)
        for index, path in enumerate(files):
            blob = path.read_bytes()
            plain, header = decrypt_bytes(blob, old_context.project_key, cfg["project_id"])
            backup = f"{index}.old"
            staged = f"{index}.new"
            _atomic_write(transaction / backup, blob)
            new_blob = encrypt_bytes(plain, new_key, cfg["project_id"], header["original_name"], header.get("mime_type"))
            _atomic_write(transaction / staged, new_blob)
            restored, _ = decrypt_bytes((transaction / staged).read_bytes(), new_key, cfg["project_id"])
            if restored != plain:
                raise SecurityError("Falló la verificación del archivo recifrado.")
            journal["files"].append({"path": path.relative_to(root).as_posix(), "backup": backup, "staged": staged})
        new_cfg = dict(cfg)
        new_cfg.update({"key_fingerprint": _fingerprint(new_key), "schema_version": SECURITY_SCHEMA_VERSION,
                        "password_wrap": _wrap_project_key(cfg["project_id"], new_key, new_password),
                        "owner_token_hash": _owner_token_hash(new_owner_token),
                        "owner_password_wrap": _wrap_owner_token(cfg["project_id"], new_owner_token, new_password),
                        "updated_at": _now(), "key_rotated_at": _now()})
        _atomic_write(transaction / "new_security.json", json.dumps(new_cfg, ensure_ascii=False, indent=2).encode("utf-8"))
        write_credential(transaction / "new_recovery.hsk", new_cfg, new_key, role="owner_recovery", label="Recuperación del propietario", owner_token=new_owner_token)
        read_credential(transaction / "new_recovery.hsk", new_cfg)
        # Durable journal precedes every change to an active file.
        _atomic_write(transaction / "journal.json", json.dumps(journal).encode("utf-8"))
        for record in journal["files"]:
            _atomic_write(root / record["path"], (transaction / record["staged"]).read_bytes())
        _atomic_write(recovery_path, (transaction / "new_recovery.hsk").read_bytes())
        _atomic_write(security_config_path(root), (transaction / "new_security.json").read_bytes())
        _atomic_write(transaction / "COMMITTED", b"committed")
    except Exception:
        if (transaction / "journal.json").exists():
            _recover_rotation_unlocked(root)
        else:
            shutil.rmtree(transaction)
        raise
    _recover_rotation_unlocked(root)
    return AccessContext(cfg["project_id"], new_key, "owner_recovery", owner_token=new_owner_token)
