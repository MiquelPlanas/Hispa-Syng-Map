"""Failure and interrupted-process tests for protected result lifecycles."""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "herramientas"))
import hispa_security as sec
import secure_execution as lifecycle


def main():
    checks = []
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        root = base / "project"
        (root / "Datos_data").mkdir(parents=True)
        payload = b"Observation-Private-Canary-42.123456-8.654321"
        (root / "Datos_data" / "Ingesta_provisional.xlsx").write_bytes(payload)
        cfg, key = sec.create_security_config(root, "Lifecycle-Password-123!")
        owner = sec.AccessContext(cfg["project_id"], key, "owner", owner_token=sec.unwrap_owner_token(cfg, "Lifecycle-Password-123!"))
        sec.encrypt_project_input(root, cfg, key)
        with patch.dict(os.environ, {"LOCALAPPDATA": str(base / "private")}, clear=False):
            results = lifecycle.begin_protected_execution(root, "isolated", owner)
            run = results / "ejecucion_isolated_ESP"
            run.mkdir()
            for name in ("unexpected.csv", "extra.xlsx", "unknown.html", "secret.geojson", "run.log"):
                (run / name).write_bytes(payload)
            assert not (root / "Resultados").exists()
            assert results.parent.stat().st_mode & 0o077 == 0 if os.name != "nt" else True
            checks.append("private generation outside shared results")
            # An access-bearing environment can never convey owner authority.
            with patch.dict(os.environ, sec.export_access_environment(owner)):
                assert sec.access_from_environment(root).role == "access"
                lifecycle.guard_child_execution(root, run, results, "isolated")
                try:
                    lifecycle.guard_child_execution(root, root / "Resultados" / run.name, root / "Resultados", "isolated")
                except sec.SecurityError:
                    pass
                else:
                    raise AssertionError("Protected direct CLI allowed shared output")
            checks.append("direct CLI staging guard and owner-role isolation")
            # A verification failure must publish nothing and retain recovery.
            with patch.object(lifecycle, "verify_protected_tree", side_effect=sec.SecurityError("injected verification failure")):
                try:
                    lifecycle.finish_protected_execution(root, "isolated", owner)
                except sec.SecurityError:
                    pass
                else:
                    raise AssertionError("Verification failure ignored")
            assert not (root / "Resultados" / run.name).exists()
            assert (sec.security_dir(root) / "pending" / "isolated.json").exists()
            checks.append("verification failure blocks publication")
            assert lifecycle.recover_pending_executions(root, owner) == 1
            final = root / "Resultados" / ("incompleta_" + run.name)
            assert final.is_dir()
            sec.verify_protected_tree(final, cfg, key)
            for name in ("unexpected.csv", "extra.xlsx", "unknown.html", "secret.geojson", "run.log"):
                restored, _ = sec.decrypt_bytes((final / (name + ".hse")).read_bytes(), key, cfg["project_id"])
                assert restored == payload
            sec.protect_all_existing_outputs(root, owner)
            sec.protect_all_existing_outputs(root, owner)
            restored, _ = sec.decrypt_bytes((final / "unknown.html.hse").read_bytes(), key, cfg["project_id"])
            assert restored == payload
            checks.append("automatic recovery and idempotent protection")
            results = lifecycle.begin_protected_execution(root, "complete", owner)
            run = results / "run_complete_EN"
            run.mkdir()
            (run / "Map1_private.html").write_bytes(payload)
            lifecycle.finish_protected_execution(root, "complete", owner)
            final = root / "Resultados" / run.name
            assert final.is_dir() and (final / "Map1_private.html.hse").is_file()
            assert not list((sec.security_dir(root) / "pending").glob("*.json"))
            checks.append("verified successful publication")
        # A low-level migration call must itself require the actual password.
        schema_one = dict(cfg)
        schema_one["schema_version"] = 1
        schema_one.pop("owner_token_hash")
        schema_one.pop("owner_password_wrap")
        try:
            sec.upgrade_owner_authority(root, schema_one, key, "Wrong-Password-123!")
        except sec.SecurityError:
            pass
        else:
            raise AssertionError("Migration accepted data key without owner password")
        assert not sec._owner_context_valid(schema_one, sec.AccessContext(cfg["project_id"], key, "owner"))
        checks.append("owner migration requires password authentication")

        # Write failures before and during commit must leave the old key usable.
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*.hse")}
        real_write = sec._atomic_write
        for failure_phase in ("staging", "active"):
            def fail_write(path, data):
                path = Path(path)
                if failure_phase == "staging" and path.name == "0.new":
                    raise OSError(28, "injected full disk")
                if failure_phase == "active" and path.suffix == ".hse" and sec.SECURITY_DIRNAME not in path.parts:
                    raise PermissionError("injected locked destination")
                real_write(path, data)
            with patch.object(sec, "_atomic_write", side_effect=fail_write):
                try:
                    sec.rotate_project_key(root, owner, "Rotated-Lifecycle-456!", base / "failed_recovery.hsk")
                except (OSError, sec.SecurityError):
                    pass
                else:
                    raise AssertionError("Write failure ignored")
            # A rollback whose destination remains locked is retried next access.
            assert sec.load_security_config(root)["key_fingerprint"] == cfg["key_fingerprint"]
            assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*.hse")} == before
        checks.append("full disk and locked-file failures preserve recoverable old state")

        # Abrupt termination bypasses exception cleanup and tests disk journal.
        code = r'''
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import hispa_security as s
root=Path(sys.argv[2]); phase=sys.argv[3]
cfg=s.load_security_config(root)
key=s.unwrap_project_key(cfg,'Lifecycle-Password-123!')
ctx=s.AccessContext(cfg['project_id'],key,'owner',owner_token=s.unwrap_owner_token(cfg,'Lifecycle-Password-123!'))
original=s._atomic_write
def crash(path,data):
    original(path,data)
    if phase=='active' and Path(path).suffix=='.hse' and s.SECURITY_DIRNAME not in Path(path).parts:
        os._exit(73)
    if phase=='committed' and Path(path).name=='COMMITTED':
        os._exit(74)
s._atomic_write=crash
s.rotate_project_key(root,ctx,'Rotated-Lifecycle-456!',Path(sys.argv[4]))
'''
        recovery = base / "rotation_recovery.hsk"
        for phase, expected_code in (("active", 73), ("committed", 74)):
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*.hse")}
            result = subprocess.run([sys.executable, "-c", code, str(ROOT / "herramientas"), str(root), phase, str(recovery)], check=False)
            assert result.returncode == expected_code
            recovered_cfg = sec.load_security_config(root)
            assert not (sec.security_dir(root) / "rotation").exists()
            if phase == "active":
                assert recovered_cfg["key_fingerprint"] == cfg["key_fingerprint"]
                assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*.hse")} == before
                assert not recovery.exists()
                checks.append("abrupt rotation interruption rolls back all files")
            else:
                new_key = sec.unwrap_project_key(recovered_cfg, "Rotated-Lifecycle-456!")
                assert new_key != key
                assert sec.read_credential(recovery, recovered_cfg).project_key == new_key
                sec.verify_protected_tree(root / "Resultados", recovered_cfg, new_key)
                restored, _ = sec.decrypt_bytes((root / "Datos_data" / "Ingesta_provisional.hse").read_bytes(), new_key, cfg["project_id"])
                assert restored == payload
                old_blob = before[Path("Datos_data/Ingesta_provisional.hse")]
                assert sec.decrypt_bytes(old_blob, key, cfg["project_id"])[0] == payload
                checks.append("committed rotation survives termination; old copies stay readable")
    for check in checks:
        print("PASS", check)
    print("PASS security lifecycle", len(checks), "scenario groups")
    if os.name != "nt":
        print("NOT EXECUTED: native Windows DPAPI and cross-Windows-user isolation")
    else:
        sample = b"DPAPI-user-scope-regression"
        entropy = b"Hispa-Syng-test-entropy"
        assert sec._dpapi_unprotect(sec._dpapi_protect(sample, entropy), entropy) == sample
        print("PASS native current-user Windows DPAPI roundtrip")
        print("NOT EXECUTED: cross-Windows-user isolation (requires a second Windows account)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
