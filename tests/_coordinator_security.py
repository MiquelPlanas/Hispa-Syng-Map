"""Exercise the complete bilingual coordinator around synthetic child outputs."""
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "herramientas"))
import ejecutar_bilingue as coordinator
import hispa_security as sec


def main():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "project"
        for edition, entry, config in (("PYTHON_ESP", "ejecutar_hippodec.py", "configuracion.yaml"), ("PYTHON_ENGLISH", "run_hippodec.py", "config.yaml")):
            directory = root / edition
            directory.mkdir(parents=True)
            (directory / entry).write_text("# synthetic child", encoding="utf-8")
            (directory / config).write_text("# synthetic config", encoding="utf-8")
        data = root / "Datos_data"
        data.mkdir()
        (data / "Ingesta_provisional.xlsx").write_bytes(b"Synthetic observations")
        cfg, key = sec.create_security_config(root, "Coordinator-Password-123!")
        owner = sec.AccessContext(cfg["project_id"], key, "owner", owner_token=sec.unwrap_owner_token(cfg, "Coordinator-Password-123!"))
        sec.encrypt_project_input(root, cfg, key)
        paths = {name: None for name in ("grids", "gshhg", "demarcations", "logo", "protected_areas", "traits")}
        paths.update({"excel": data / "Ingesta_provisional.hse", "sheet": "data"})
        base_config = {"execution": {"interactive": False, "open_browser": False}, "analysis": {"permutations": 9}, "paths": {}}
        api = {"load_config": lambda _: base_config, "resolve_input_paths": lambda *_: paths,
               "read_and_clean_excel": lambda *_: (None, {})}
        child_count = 0
        canary = b"Synthetic private individual coordinates"
        def child(command, **kwargs):
            nonlocal child_count
            child_count += 1
            assert not list((root / "Resultados").glob("*")), "Premature shared result publication"
            run = Path(command[command.index("--run-root") + 1])
            assert run.parent != root / "Resultados"
            language = command[command.index("--language-code") + 1]
            publication = run / ("Publicacion_Web" if language == "ES" else "Web_Publication")
            maps = publication / ("mapas" if language == "ES" else "maps")
            maps.mkdir(parents=True)
            (maps / ("Mapa1_demo.html" if language == "ES" else "Map1_demo.html")).write_bytes(canary)
            (publication / "index.html").write_text("<html>Aggregate viewer</html>", encoding="utf-8")
            from output_policy import register_public_output
            register_public_output(publication / "index.html", "viewer")
            (run / "unanticipated.csv").write_bytes(canary)
            return SimpleNamespace(returncode=0)
        env = sec.export_access_environment(owner)
        env["LOCALAPPDATA"] = str(Path(temporary) / "private")
        with patch.dict(os.environ, env), patch.object(coordinator, "_load_spanish_api", return_value=api), \
             patch.object(coordinator, "_prompt_parameters", return_value=(2021, 2026, 10, "all", ("Species",), ())), \
             patch.object(coordinator.subprocess, "run", side_effect=child), contextlib.redirect_stdout(io.StringIO()):
            result = coordinator.main(["--project-root", str(root)])
        assert result == 0 and child_count == 2
        sec.verify_protected_tree(root / "Resultados", cfg, key)
        containers = list((root / "Resultados").rglob("*.hse"))
        assert containers
        assert all(sec.decrypt_bytes(p.read_bytes(), key, cfg["project_id"])[0] == canary for p in containers)
        assert len(list((root / "Resultados").glob("Publicacion_Web_Bilingue_*"))) == 1
        assert not list((sec.security_dir(root) / "pending").glob("*.json"))
    print("PASS protected bilingual coordinator with synthetic child outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
