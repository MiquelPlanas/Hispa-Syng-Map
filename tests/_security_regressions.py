from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "herramientas"
sys.path.insert(0, str(TOOLS))

from hispa_security import (  # noqa: E402
    AccessContext,
    HSE_MAGIC,
    SecurityError,
    change_password,
    create_open_copy,
    create_protected_copy,
    create_security_config,
    decrypt_all_project_files,
    decrypt_bytes,
    encrypt_bytes,
    encrypt_project_input,
    export_access_environment,
    load_security_config,
    protect_all_existing_outputs,
    read_credential,
    rotate_project_key,
    unwrap_owner_token,
    unwrap_project_key,
    write_credential,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hispa_security_test_") as temp:
        root = Path(temp) / "project"
        data = root / "Datos_data"
        data.mkdir(parents=True)
        payload = b"Hispa-Syng security regression payload"
        (data / "Ingesta_provisional.xlsx").write_bytes(payload)

        cfg, key = create_security_config(root, "RegressionPassword-12345!")
        owner_token = unwrap_owner_token(cfg, "RegressionPassword-12345!")
        assert owner_token is not None
        encrypted_input = encrypt_project_input(root, cfg, key)
        assert encrypted_input and encrypted_input.is_file()
        assert not (data / "Ingesta_provisional.xlsx").exists()
        plain, header = decrypt_bytes(encrypted_input.read_bytes(), key, cfg["project_id"])
        assert plain == payload
        assert header["original_name"] == "Ingesta_provisional.xlsx"

        credential = Path(temp) / "access.hsk"
        write_credential(credential, cfg, key, role="access", label="Regression")
        access = read_credential(credential, cfg)
        assert access.project_key == key and access.role == "access"
        assert access.owner_token is None

        # An access credential holder knows the project data key but must not be
        # able to promote that bearer file to owner/recovery authority.
        import json, hmac, hashlib
        forged = Path(temp) / "forged_owner.hsk"
        payload_cred = json.loads(credential.read_text(encoding="utf-8"))
        payload_cred["role"] = "owner_recovery"
        payload_cred.pop("owner_token_b64", None)
        payload_cred.pop("owner_token_hash", None)
        body = dict(payload_cred)
        body.pop("integrity_hmac_sha256", None)
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_cred["integrity_hmac_sha256"] = hmac.new(key, canonical, hashlib.sha256).hexdigest()
        forged.write_text(json.dumps(payload_cred), encoding="utf-8")
        try:
            forged_ctx = read_credential(forged, cfg)
        except SecurityError:
            forged_ctx = None
        assert forged_ctx is None or forged_ctx.role == "access", "Access credential escalated to owner authority"

        owner_recovery = Path(temp) / "owner_recovery.hsk"
        write_credential(owner_recovery, cfg, key, role="owner_recovery", label="Owner", owner_token=owner_token)
        recovery_ctx = read_credential(owner_recovery, cfg)
        assert recovery_ctx.role == "owner_recovery" and recovery_ctx.owner_token == owner_token

        change_password(root, key, "ChangedRegression-67890!", owner_token=owner_token)
        changed = load_security_config(root)
        assert unwrap_project_key(changed, "ChangedRegression-67890!") == key
        assert unwrap_owner_token(changed, "ChangedRegression-67890!") == owner_token
        try:
            unwrap_project_key(changed, "RegressionPassword-12345!")
        except SecurityError:
            pass
        else:
            raise AssertionError("Old password still unlocks after password change")

        blob = encrypt_bytes(b"sensitive", key, cfg["project_id"], "secret.csv")
        restored, meta = decrypt_bytes(blob, key, cfg["project_id"])
        assert restored == b"sensitive" and meta["original_name"] == "secret.csv"

        import struct
        malformed_headers = (b"[]", b"null", b"{", b"0")
        malformed_blobs = [HSE_MAGIC + struct.pack(">I", len(h)) + h for h in malformed_headers]
        malformed_blobs.append(HSE_MAGIC + struct.pack(">I", 1024 * 1024 + 1))
        for malformed in malformed_blobs:
            try:
                decrypt_bytes(malformed, key, cfg["project_id"])
            except SecurityError:
                pass
            else:
                raise AssertionError("Malformed encrypted container was accepted")

        env = export_access_environment(AccessContext(cfg["project_id"], key, "owner"))
        assert env.get("HISPA_SYNG_SECURITY_MODE") == "protected"
        assert env.get("HISPA_SYNG_PROJECT_ID") == cfg["project_id"]

        # Existing sensitive outputs can be protected and later restored in a
        # deliberately open copy without changing their bytes.
        run = root / "Resultados" / "ejecucion_demo_ESP"
        map1 = run / "03_mapas" / "Mapa1_demo.html"
        map1.parent.mkdir(parents=True)
        map1_payload = b"<html><body>secret coordinates</body></html>"
        map1.write_bytes(map1_payload)
        download = run / "Publicacion_Web" / "descargas" / "datos.xlsx"
        download.parent.mkdir(parents=True)
        download_payload = b"sensitive workbook"
        download.write_bytes(download_payload)
        publication_map1 = run / "Publicacion_Web" / "mapas" / "Mapa1_demo.html"
        publication_map1.parent.mkdir(parents=True, exist_ok=True)
        publication_map1.write_bytes(map1_payload)
        spatial_table = run / "04_tablas" / "base_espacial" / "Base_Maestra_Filtrada.csv"
        spatial_table.parent.mkdir(parents=True, exist_ok=True)
        spatial_payload = b"Latitude;Longitude\n42.0;-8.0\n"
        spatial_table.write_bytes(spatial_payload)
        manifest = run / "Publicacion_Web" / "manifiesto.json"
        manifest.write_text('{"product":"test","files":[]}', encoding="utf-8")
        from output_policy import register_public_output
        register_public_output(manifest, "integrity_manifest")
        owner = AccessContext(cfg["project_id"], key, "owner", owner_token=owner_token)
        protected = protect_all_existing_outputs(root, owner)
        assert protected["files"] == 4
        assert (map1.parent / (map1.name + ".hse")).exists()
        assert map1.exists() and b"Contenido protegido" in map1.read_bytes()
        assert (publication_map1.parent / (publication_map1.name + ".hse")).exists()
        assert publication_map1.exists() and b"Contenido protegido" in publication_map1.read_bytes()
        assert not spatial_table.exists() and (spatial_table.parent / (spatial_table.name + ".hse")).exists()
        assert not download.exists() and (download.parent / (download.name + ".hse")).exists()
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        manifest_files = {row["file"] for row in manifest_payload.get("files", [])}
        assert "mapas/Mapa1_demo.html.hse" in manifest_files and "descargas/datos.xlsx.hse" in manifest_files

        open_copy = Path(temp) / "open_copy"
        create_open_copy(root, open_copy, owner)
        assert (open_copy / "Datos_data" / "Ingesta_provisional.xlsx").read_bytes() == payload
        assert not (open_copy / ".hispa_security").exists()
        assert not list(open_copy.rglob("*.hse"))
        assert not (open_copy / "Resultados").exists(), "Project copies intentionally exclude generated Results"

        protected_copy = Path(temp) / "protected_copy"
        recovery_copy = Path(temp) / "protected_copy_recovery.hsk"
        create_protected_copy(root, protected_copy, "ProtectedCopy-12345!", recovery_copy, owner)
        new_cfg = load_security_config(protected_copy)
        new_key = unwrap_project_key(new_cfg, "ProtectedCopy-12345!")
        assert new_cfg["project_id"] != cfg["project_id"]
        assert not (protected_copy / "Datos_data" / "Ingesta_provisional.xlsx").exists()
        assert (protected_copy / "Datos_data" / "Ingesta_provisional.hse").exists()
        assert not (protected_copy / "Resultados").exists(), "Project copies intentionally exclude generated Results"

        # Key rotation must invalidate the old key while preserving plaintext.
        rotation_recovery = Path(temp) / "rotation_recovery.hsk"
        rotated = rotate_project_key(root, owner, "RotatedPassword-24680!", rotation_recovery)
        rotated_cfg = load_security_config(root)
        assert rotated.project_key != key
        assert unwrap_project_key(rotated_cfg, "RotatedPassword-24680!") == rotated.project_key
        rotated_input = root / "Datos_data" / "Ingesta_provisional.hse"
        recovered_input, _ = decrypt_bytes(rotated_input.read_bytes(), rotated.project_key, rotated_cfg["project_id"])
        assert recovered_input == payload
        try:
            decrypt_bytes(rotated_input.read_bytes(), key, rotated_cfg["project_id"])
        except SecurityError:
            pass
        else:
            raise AssertionError("Old project key still decrypts after rotation")

    # Static regression: fixed plaintext-interface password material must not be distributed.
    forbidden = [
        ROOT / "CONTRASENA_DESCARGAS.txt",
        ROOT / "DOWNLOAD_PASSWORD.txt",
    ]
    assert not any(path.exists() for path in forbidden), "Plaintext password files must not be distributed"
    for edition in ("PYTHON_ESP", "PYTHON_ENGLISH"):
        templates = ROOT / edition / "src" / "hippodec_maps" / "templates"
        text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in templates.glob("*.html"))
        assert "PASSWORD_SHA256" not in text
        assert "window.prompt('Introduzca la contraseña" not in text
        assert "window.prompt('Enter the" not in text or "password" not in text.lower()

    print("PASS security regressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
