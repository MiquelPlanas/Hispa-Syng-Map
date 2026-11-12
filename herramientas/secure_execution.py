"""Private generation and recoverable publication of protected results."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from hispa_security import (
    _exclusive_project_operation, SecurityError, _atomic_write, _now, _private_directory,
    load_security_config, protect_generated_outputs, security_dir, access_from_environment,
    verify_protected_tree, _rotation_lock, recover_interrupted_rotation, _fingerprint,
)


def _journal_path(root: Path, execution_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", execution_id):
        raise SecurityError("Identificador de ejecución no válido.")
    return security_dir(root) / "pending" / f"{execution_id}.json"


def _sync_tree(root: Path) -> None:
    for path in Path(root).rglob("*"):
        if path.is_file():
            with path.open("r+b") as stream:
                os.fsync(stream.fileno())
    if os.name != "nt":
        for path in sorted([Path(root)] + [p for p in Path(root).rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True):
            fd = os.open(path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


@_exclusive_project_operation
def begin_protected_execution(root: Path, execution_id: str, context) -> Path:
    recover_interrupted_rotation(root)
    with _rotation_lock(root):
        return _begin_protected_execution(root, execution_id, context)


def _begin_protected_execution(root: Path, execution_id: str, context) -> Path:
    cfg = load_security_config(root)
    if not cfg or context.project_id != cfg["project_id"] or _fingerprint(context.project_key) != cfg["key_fingerprint"]:
        raise SecurityError("No existe autorización para preparar resultados protegidos.")
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Hispa-Syng-private" / cfg["project_id"]
    _private_directory(base)
    stage = Path(tempfile.mkdtemp(prefix=execution_id + "_", dir=base))
    _private_directory(stage)
    (stage / "results").mkdir(mode=0o700)
    journal = {
        "execution_id": execution_id, "project_id": cfg["project_id"],
        "key_fingerprint": cfg["key_fingerprint"], "created_at": _now(),
        "stage": str(stage), "state": "generating",
    }
    path = _journal_path(root, execution_id)
    if path.exists():
        raise SecurityError("La ejecución ya tiene una recuperación pendiente.")
    _atomic_write(path, json.dumps(journal).encode("utf-8"))
    return stage / "results"


def _tree_inventory(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _verify_publication(target: Path, record: dict, cfg: dict, key: bytes) -> None:
    if not target.is_dir():
        raise SecurityError("No existe el resultado publicado registrado.")
    verify_protected_tree(target, cfg, key)
    if _tree_inventory(target) != record["sha256"]:
        raise SecurityError("El resultado publicado no coincide con su registro verificado.")


@_exclusive_project_operation
def finish_protected_execution(root: Path, execution_id: str, context, *, publish: bool = True) -> dict:
    path = _journal_path(root, execution_id)
    journal = json.loads(path.read_text(encoding="utf-8"))
    cfg = load_security_config(root)
    if not cfg or journal["project_id"] != cfg["project_id"] or journal["key_fingerprint"] != cfg["key_fingerprint"]:
        raise SecurityError("La recuperación pendiente no corresponde a la clave activa.")
    stage = Path(journal["stage"])
    # Journal paths are confined to the private application staging directory.
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "Hispa-Syng-private" / cfg["project_id"]
    if stage.resolve().parent != base.resolve() or stage.is_symlink():
        raise SecurityError("Ruta de recuperación no válida.")
    destination = Path(root) / "Resultados"
    results = stage / "results"
    result = {"protected": True, "files": journal.get("protected_files", 0)}
    if journal["state"] != "published":
        if not results.is_dir():
            raise SecurityError("Falta el área de recuperación y no consta una publicación confirmada.")
        if journal["state"] == "generating":
            journal["publish_complete"] = publish
            result = protect_generated_outputs(root, execution_id, context, results_root=results)
            verify_protected_tree(results, cfg, context.project_key)
            _sync_tree(results)
            journal["protected_files"] = result["files"]
        else:
            publish = bool(journal.get("publish_complete", False))
            verify_protected_tree(results, cfg, context.project_key)
        if "publication_targets" not in journal:
            names = [f"ejecucion_{execution_id}_ESP", f"run_{execution_id}_EN"]
            if publish:
                names.append(f"Publicacion_Web_Bilingue_{execution_id}")
            journal["publication_targets"] = [
                {"source": name, "target": name if publish else "incompleta_" + name,
                 "sha256": _tree_inventory(results / name)}
                for name in names if (results / name).is_dir()
            ]
        journal["state"] = "verified"
        _atomic_write(path, json.dumps(journal).encode("utf-8"))
        destination.mkdir(parents=True, exist_ok=True)
        for record in journal["publication_targets"]:
            source = results / record["source"]
            target = destination / record["target"]
            incoming = destination / (".incoming_" + target.name)
            if target.exists():
                _verify_publication(target, record, cfg, context.project_key)
            else:
                if not source.is_dir():
                    raise SecurityError("Falta un resultado pendiente de publicación.")
                if incoming.exists():
                    shutil.rmtree(incoming)
                shutil.copytree(source, incoming)
                _verify_publication(incoming, record, cfg, context.project_key)
                _sync_tree(incoming)
                os.replace(incoming, target)
                if os.name != "nt":
                    fd = os.open(destination, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            if source.exists():
                shutil.rmtree(source)
        journal["state"] = "published"
        _atomic_write(path, json.dumps(journal).encode("utf-8"))
    # A crash after deleting staging leaves a durable, verifiable commit record.
    for record in journal["publication_targets"]:
        _verify_publication(destination / record["target"], record, cfg, context.project_key)
    if stage.exists():
        shutil.rmtree(stage)
    path.unlink(missing_ok=True)
    return result


@_exclusive_project_operation
def recover_pending_executions(root: Path, context) -> int:
    pending = security_dir(root) / "pending"
    if not pending.exists():
        return 0
    count = 0
    for path in sorted(pending.glob("*.json")):
        journal = json.loads(path.read_text(encoding="utf-8"))
        # Only already-verified publication may resume as a completed run.
        finish_protected_execution(root, journal["execution_id"], context,
                                   publish=journal.get("state") in {"verified", "published"} and journal.get("publish_complete", False))
        count += 1
    return count


def guard_child_execution(root: Path, run_root: Path | None, results_root: Path, execution_id: str | None) -> None:
    """Prevent a protected direct CLI run from writing outside its staging area."""
    cfg = load_security_config(root)
    if not cfg:
        return
    if access_from_environment(root) is None:
        raise SecurityError("No existe una clave autorizada para la ejecución protegida.")
    if not execution_id or run_root is None:
        raise SecurityError("Ejecute el proyecto protegido desde Hispa-Syng.bat.")
    journal = json.loads(_journal_path(root, execution_id).read_text(encoding="utf-8"))
    expected = (Path(journal["stage"]) / "results").resolve()
    allowed = {expected / f"ejecucion_{execution_id}_ESP", expected / f"run_{execution_id}_EN"}
    if results_root.resolve() != expected or run_root.resolve() not in allowed:
        raise SecurityError("Los resultados protegidos deben generarse en el área privada autorizada.")
