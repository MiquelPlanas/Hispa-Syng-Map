"""Tabular, graphical, and audit outputs for the analyses."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
from PIL import Image


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.text import Text  # noqa: E402

from .data import SPECIES_WITH_AUTHORITY
from .localization import (
    translate_column_name,
    translate_frame,
    translate_path,
    translate_text,
)



plt.rcParams.update(
    {
        "figure.dpi": 120,
        "savefig.dpi": 300,
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.2,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


_SPECIES_NAMES = tuple(sorted(SPECIES_WITH_AUTHORITY.keys(), key=len, reverse=True))
_SPECIES_ABBREVIATIONS = tuple(
    sorted(
        {f"{name.split()[0][0]}. {name.split()[1]}" for name in SPECIES_WITH_AUTHORITY},
        key=len,
        reverse=True,
    )
)
_SPECIES_LABELS = _SPECIES_NAMES + tuple(
    abbreviation
    for abbreviation in _SPECIES_ABBREVIATIONS
    if abbreviation not in SPECIES_WITH_AUTHORITY
)


def _math_italic_species(label: str) -> str:
    return "$\\it{" + label.replace(" ", r"\ ") + "}$"


def italicize_species_names(text: str) -> str:
    if not text or "$\\it{" in text:
        return text
    updated = str(text)
    for label in _SPECIES_LABELS:
        pattern = rf"(?<![A-Za-z]){re.escape(label)}(?![A-Za-z])"
        replacement = _math_italic_species(label)
        updated = re.sub(pattern, lambda _match, value=replacement: value, updated)
    return updated


def csv2(frame: pd.DataFrame | gpd.GeoDataFrame, path: Path) -> Path:
    path = translate_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = translate_frame(pd.DataFrame(frame.drop(columns="geometry", errors="ignore")))
    table.to_csv(
        path, sep=";", decimal=",", index=False, encoding="utf-8-sig", na_rep=""
    )
    return path


def excel_book(sheets: dict[str, pd.DataFrame], path: Path) -> Path:
    path = translate_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for raw_name, frame in sheets.items():
            name = re.sub(
                r"[\\/*?:\[\]]", "_", translate_column_name(raw_name)
            )[:31] or "Sheet"
            translate_frame(pd.DataFrame(frame.drop(columns="geometry", errors="ignore"))).to_excel(
                writer, sheet_name=name, index=False
            )
    return path


def table_pair(
    frame: pd.DataFrame | gpd.GeoDataFrame,
    base: Path,
    *,
    sheet_name: str = "data",
) -> tuple[Path, Path]:
    """Export one table to CSV2 and XLSX using the same base name."""

    csv_path = csv2(frame, base.with_suffix(".csv"))
    xlsx_path = excel_book({sheet_name: frame}, base.with_suffix(".xlsx"))
    return csv_path, xlsx_path


def text_file(text: str, path: Path) -> Path:
    path = translate_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(translate_text(text).rstrip() + "\n", encoding="utf-8")
    return path


def portable_output_base(base: Path, max_path_chars: int = 240) -> Path:
    """Shorten only the filename when the path would be fragile on Windows."""

    base = translate_path(Path(base))
    final_png = base.with_suffix(".png").absolute()
    if len(str(final_png)) <= max_path_chars:
        return base

    parent_length = len(str(base.parent.absolute()))
    max_stem_chars = max_path_chars - parent_length - 1 - len(".png")
    marker = "_" + hashlib.sha256(base.stem.encode("utf-8")).hexdigest()[:8] + "_"
    if max_stem_chars < len(marker) + 12:
        raise OSError(
            "The results folder is nested too deeply for Windows. "
            "Move Hispa-Syng to a shorter path, for example C:\\Hispa-Syng."
        )

    remaining = max_stem_chars - len(marker)
    head_chars = (remaining + 1) // 2
    tail_chars = remaining - head_chars
    shortened = base.stem[:head_chars] + marker + base.stem[-tail_chars:]
    return base.with_name(shortened)


def _short_temporary_file(parent: Path, kind: str) -> Path:
    """Create a short-named temporary file in the destination directory."""

    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{kind}_", suffix=".tmp", dir=parent
    )
    os.close(descriptor)
    return Path(raw_path)


def cleanup_figure_temporaries(root: Path) -> int:
    """Remove internal temporary remnants without touching other outputs."""

    removed = 0
    for pattern in (".png_*.tmp", ".pdf_*.tmp"):
        for candidate in Path(root).rglob(pattern):
            candidate.unlink(missing_ok=True)
            removed += 1
    return removed


def save_figure(figure: plt.Figure, base: Path, *, pdf: bool = True) -> list[Path]:
    for item in figure.findobj(match=Text):
        item.set_text(italicize_species_names(translate_text(item.get_text())))
    base = portable_output_base(base)
    base.parent.mkdir(parents=True, exist_ok=True)
    png = base.with_suffix(".png")
    last_error: Exception | None = None
    try:
        for _ in range(2):
            png_tmp = _short_temporary_file(base.parent, "png")
            try:
                figure.savefig(
                    png_tmp,
                    format="png",
                    bbox_inches="tight",
                    facecolor="white",
                )
                with Image.open(png_tmp) as image:
                    image.verify()
                png_tmp.replace(png)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
            finally:
                png_tmp.unlink(missing_ok=True)
        if last_error is not None:
            detail = f"{type(last_error).__name__}: {last_error}"
            raise OSError(
                f"A valid PNG could not be created: {png} ({detail})"
            ) from last_error

        outputs = [png]
        if pdf:
            pdf_path = base.with_suffix(".pdf")
            last_error = None
            for _ in range(2):
                pdf_tmp = _short_temporary_file(base.parent, "pdf")
                try:
                    figure.savefig(
                        pdf_tmp,
                        format="pdf",
                        bbox_inches="tight",
                        facecolor="white",
                    )
                    pdf_bytes = pdf_tmp.read_bytes()
                    if (
                        not pdf_bytes.startswith(b"%PDF-")
                        or b"%%EOF" not in pdf_bytes[-1024:]
                    ):
                        raise OSError("incomplete PDF header or trailer")
                    pdf_tmp.replace(pdf_path)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                finally:
                    pdf_tmp.unlink(missing_ok=True)
            if last_error is not None:
                detail = f"{type(last_error).__name__}: {last_error}"
                raise OSError(
                    f"A valid PDF could not be created: {pdf_path} ({detail})"
                ) from last_error
            outputs.append(pdf_path)
        return outputs
    finally:
        plt.close(figure)
        cleanup_figure_temporaries(base.parent)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_signature(path: Path) -> str:
    """Return a stable content signature, ignoring volatile Office metadata."""

    if path.suffix.lower() in {".docx", ".xlsx", ".xlsm", ".zip"}:
        try:
            digest = hashlib.sha256()
            with ZipFile(path) as archive:
                for info in sorted(archive.infolist(), key=lambda item: item.filename):
                    if info.is_dir() or info.filename.casefold() in {"docprops/core.xml"}:
                        continue
                    digest.update(info.filename.encode("utf-8"))
                    digest.update(b"\0")
                    digest.update(archive.read(info))
                    digest.update(b"\0")
            return f"zip:{digest.hexdigest()}"
        except (BadZipFile, OSError):
            pass
    return f"raw:{sha256(path)}"


def deduplicate_registered_outputs(
    registry: "OutputRegistry",
) -> list[dict[str, str]]:
    """Keep the first registered file for each content signature.

    The first output is the canonical name.  Later aliases are removed only
    when they are files inside the run folder and their bytes/content are
    equivalent.  The returned control rows are intended for the QA folder.
    """

    root = registry.run_root.resolve()
    signatures: dict[str, Path] = {}
    retained: list[dict[str, Any]] = []
    removed: list[dict[str, str]] = []
    for record in registry.records:
        if record.get("status") != "created" or not record.get("file"):
            retained.append(record)
            continue
        candidate = (root / str(record["file"])).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Registered output is outside the run folder: {candidate}") from exc
        if not candidate.is_file():
            retained.append(record)
            continue
        signature = _content_signature(candidate)
        canonical = signatures.get(signature)
        if canonical is not None and canonical != candidate:
            candidate.unlink()
            removed.append(
                {
                    "removed_file": str(candidate.relative_to(root)).replace("\\", "/"),
                    "canonical_file": str(canonical.relative_to(root)).replace("\\", "/"),
                    "content_signature": signature,
                    "reason": "byte-identical or Office-metadata-normalised duplicate",
                }
            )
            continue
        signatures[signature] = candidate
        record["bytes"] = candidate.stat().st_size
        record["sha256"] = sha256(candidate)
        retained.append(record)
    registry.records = retained
    return removed


def deduplicate_output_tree(
    root: Path,
    registry: "OutputRegistry",
    *,
    include_dirs: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """Remove duplicate files from a completed analytical output tree.

    Analytical products are registered through the output registry. Run the
    registry-first pass so its first registered name remains canonical, then
    scan the remaining tree and remove unregistered aliases as well.
    """

    root = root.resolve()
    removed = deduplicate_registered_outputs(registry)
    signatures: dict[str, Path] = {}
    registered_paths: set[Path] = set()
    for record in registry.records:
        if record.get("status") != "created" or not record.get("file"):
            continue
        candidate = (root / str(record["file"])).resolve()
        if candidate.is_file():
            registered_paths.add(candidate)
            signatures.setdefault(_content_signature(candidate), candidate)

    scan_roots = (
        [root / relative for relative in include_dirs]
        if include_dirs is not None
        else [root]
    )
    candidates = (
        path
        for scan_root in scan_roots
        if scan_root.exists()
        for path in scan_root.rglob("*")
        if path.is_file()
    )
    for candidate in sorted(
        candidates,
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    ):
        candidate = candidate.resolve()
        if candidate in registered_paths:
            continue
        signature = _content_signature(candidate)
        canonical = signatures.get(signature)
        if canonical is not None and canonical != candidate:
            candidate.unlink()
            removed.append(
                {
                    "removed_file": str(candidate.relative_to(root)).replace("\\", "/"),
                    "canonical_file": str(canonical.relative_to(root)).replace("\\", "/"),
                    "content_signature": signature,
                    "reason": "byte-identical or Office-metadata-normalised duplicate",
                }
            )
            continue
        signatures[signature] = candidate
    return removed


@dataclass
class OutputRegistry:
    run_root: Path
    records: list[dict[str, Any]] = field(default_factory=list)

    def add(
        self,
        path: Path,
        block: str,
        description: str,
        status: str = "created",
    ) -> Path:
        resolved_path = path.resolve()
        resolved_root = self.run_root.resolve()
        # ``Path.relative_to`` can reject an otherwise valid Windows child path
        # after a translated filename has been reconstructed. ``relpath`` is
        # robust to drive-letter casing, spaces, and normal Windows separators.
        relative_text = os.path.relpath(str(resolved_path), str(resolved_root))
        relative = Path(relative_text)
        if relative.is_absolute() or relative.parts[:1] == ("..",):
            raise ValueError(
                f"Output file is outside the run folder: {resolved_path}"
            )
        self.records.append(
            {
                "block": block,
                "file": str(relative).replace(os.sep, "/"),
                "description": translate_text(description),
                "status": status,
                "bytes": path.stat().st_size if path.exists() else 0,
                "sha256": sha256(path) if path.exists() and path.is_file() else "",
            }
        )
        return path

    def skip(self, block: str, description: str, reason: str) -> None:
        self.records.append(
            {
                "block": block,
                "file": "",
                "description": translate_text(description),
                "status": "skipped",
                "reason": translate_text(reason),
                "bytes": 0,
                "sha256": "",
            }
        )

    def write(self, path: Path, extra: dict[str, Any] | None = None) -> Path:
        created = sum(row["status"] == "created" for row in self.records)
        skipped = sum(row["status"] == "skipped" for row in self.records)
        payload = {
            "status": "passed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "created_files": created,
            "skipped_optional_outputs": skipped,
            "runtime": {
                "python": platform.python_version(),
                "pandas": pd.__version__,
                "geopandas": gpd.__version__,
                "numpy": np.__version__,
            },
            "outputs": self.records,
            **(extra or {}),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path


def mode_or_na(series: pd.Series) -> object:
    clean = series.dropna()
    if clean.empty:
        return pd.NA
    modes = clean.mode()
    return modes.iloc[0] if not modes.empty else clean.iloc[0]


def finite_quantile(
    series: pd.Series, probability: float, default: float = np.nan
) -> float:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    return float(np.quantile(values, probability)) if values.size else default
