"""Test the real JSON presentation boundaries without geospatial processing.

Load localization normally. Compile the source definitions of the two JSON
boundary functions and their localization imports, without importing unrelated
GIS/plotting modules. This is a focused test, not a complete pipeline run.
"""
from __future__ import annotations

import ast
import __future__
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EDITION = ROOT / "PYTHON_ENGLISH"
sys.path.insert(0, str(EDITION / "src"))
from hippodec_maps import localization


def load_boundary(name):
    path = EDITION / "src" / "hippodec_maps" / name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    selected = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "localization":
            selected.append(ast.ImportFrom(module="hippodec_maps.localization", names=node.names, level=0))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_presentation_json":
            selected.append(node)
    assert sum(isinstance(node, ast.FunctionDef) for node in selected) == 1
    namespace = {}
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, str(path), "exec", flags=__future__.annotations.compiler_flag), namespace)
    return namespace["_presentation_json"]


BOUNDARIES = {name: load_boundary(name) for name in ("pipeline.py", "analysis_pipeline.py")}


class JsonReferenceIntegrity(unittest.TestCase):
    def check_presented(self, source, expected):
        before = copy.deepcopy(source)
        for name, present in BOUNDARIES.items():
            with self.subTest(boundary=name):
                self.assertEqual(present(source), expected)
                self.assertEqual(source, before)

    def test_windows_paths_under_observed_qa_keys(self):
        base = r"C:\Proyectos\Resultados\run_EN\07_quality_control"
        fields = (
            "region_assignment_quality_control", "qa", "manifest",
            "regional_data_quality_control", "runtime_warning_control",
            "duplicate_output_control", "marine_area_cache_file", "file", "source",
        )
        source = {field: base + r"\Control_Observaciones.csv" for field in fields}
        self.check_presented(source, source)

    def test_unc_and_windows_forward_slashes(self):
        paths = [r"\\servidor\Resultados\Observaciones.csv", "C:/Resultados/Mapa.html"]
        self.check_presented({"references": paths}, {"references": paths})

    def test_posix_and_relative_references(self):
        paths = ["/tmp/Resultados/Observaciones.csv", "./Resultados/Mapa.html",
                 "../Resultados/Control.json", "Resultados/run_EN/Mapa.html",
                 "capas/Observaciones.shp", r"Resultados\run_EN\Control.json"]
        self.check_presented({"references": paths}, {"references": paths})

    def test_path_fields_preserve_basenames_and_directories(self):
        source = {"file": "Observaciones.csv", "manifest": "Resultados.json",
                  "directory": "Resultados", "output_path": "Observaciones",
                  "paths": ["Resultados", "Observaciones.csv"]}
        self.check_presented(source, source)

    def test_urls_are_references(self):
        source = {"source": "https://example.org/Resultados/Observaciones.csv?region=Alta"}
        self.check_presented(source, source)

    def test_metadata_is_preserved_in_both_boundaries(self):
        source = {"Comments": "Alta abundancia en praderas marinas", "Observer": "Alta Mar",
                  "source_file": "Observaciones.csv", "Species": "Hippocampus guttulatus"}
        self.check_presented(source, source)

    def test_translation_of_labels_and_habitats_continues(self):
        source = {"label": "Resultados", "priority": "Alta", "Habitat": "Pradera marina/Rocas"}
        expected = {"label": "Results", "priority": "High", "Habitat": "Seagrass/Macroalgae/Rock"}
        self.check_presented(source, expected)

    def test_nested_numerical_values_and_input_immutability(self):
        source = {"analysis": {"qa": r"C:\Resultados\Control.json", "status": "Alta"},
                  "metrics": [1, 0, 2828.0, 1.234567890123, None, True],
                  "items": ({"label": "Resultados"},)}
        expected = copy.deepcopy(source)
        expected["analysis"]["status"] = "High"
        expected["items"] = [{"label": "Results"}]
        self.check_presented(source, expected)

    def test_written_json_references_resolve_to_original_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "Resultados" / "Observaciones"
            directory.mkdir(parents=True)
            referenced = directory / "Control_Observaciones.csv"
            referenced.write_text("id;value\n1;2\n", encoding="utf-8")
            for name, present in BOUNDARIES.items():
                report = Path(temporary) / (name + ".json")
                report.write_text(json.dumps(present({"file": str(referenced)})), encoding="utf-8")
                recorded = json.loads(report.read_text(encoding="utf-8"))["file"]
                self.assertEqual(recorded, str(referenced))
                self.assertEqual(Path(recorded).read_bytes(), referenced.read_bytes())

    def test_generated_filename_translation_remains_available(self):
        original = Path("Resultados") / "Mapa_Observaciones.html"
        translated = localization.translate_path(original)
        self.assertEqual(translated.parent, original.parent)
        self.assertEqual(translated.name, "Map_Observations.html")


if __name__ == "__main__":
    unittest.main(verbosity=2)
