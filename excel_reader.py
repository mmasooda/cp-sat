"""Utility module for reading XLSX files without external dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional
import zipfile
from xml.etree import ElementTree as ET

# Namespaces used in XLSX XML files
XL_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
# Workbook relationship files use the generic OPC package namespace rather than
# the officeDocument relationships namespace.
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _column_index(column_ref: str) -> int:
    """Convert an Excel column reference (e.g. 'AA') to a 1-based index."""
    index = 0
    for char in column_ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - 64)
    return index


@dataclass
class SheetData:
    """Represents a sheet within an XLSX workbook."""

    name: str
    rows: List[List[str]]

    def records(self, *, header: bool = True) -> List[Dict[str, str]]:
        """Return the sheet rows as a list of dictionaries."""
        if not self.rows:
            return []
        if not header:
            return [dict(enumerate(row)) for row in self.rows]

        headers = [cell.strip() for cell in self.rows[0]]
        records: List[Dict[str, str]] = []
        for row in self.rows[1:]:
            record: Dict[str, str] = {}
            for idx, header_name in enumerate(headers):
                if not header_name:
                    continue
                if idx < len(row):
                    record[header_name] = row[idx]
                else:
                    record[header_name] = ""
            # Skip completely empty rows
            if any(value.strip() for value in record.values()):
                records.append(record)
        return records


class XLSXReader:
    """Lightweight XLSX reader implemented with the standard library."""

    def __init__(self, workbook_path: str) -> None:
        self.workbook_path = workbook_path
        self._shared_strings: List[str] = []
        self._sheet_files: Dict[str, str] = {}
        self._load_workbook_metadata()

    # ------------------------------------------------------------------
    # Metadata loading helpers
    # ------------------------------------------------------------------
    def _load_workbook_metadata(self) -> None:
        with zipfile.ZipFile(self.workbook_path) as archive:
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_tree = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for si in shared_tree.iter(f"{XL_NS}si"):
                    text = "".join(t.text or "" for t in si.iter(f"{XL_NS}t"))
                    self._shared_strings.append(text)

            workbook_tree = ET.fromstring(archive.read("xl/workbook.xml"))
            sheet_elements = list(workbook_tree.iter(f"{XL_NS}sheet"))

            rels_tree = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relationships = {
                rel.get("Id"): rel.get("Target")
                for rel in rels_tree.iter(f"{PKG_REL_NS}Relationship")
            }

            for sheet in sheet_elements:
                name = sheet.get("name") or "Sheet1"
                rel_id = sheet.get(f"{REL_NS}id")
                if rel_id and rel_id in relationships:
                    target = relationships[rel_id]
                    if not target.startswith("/"):
                        target = "xl/" + target
                    self._sheet_files[name] = target

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def sheet_names(self) -> List[str]:
        return list(self._sheet_files.keys())

    def read_sheet(self, name: Optional[str] = None) -> SheetData:
        if name is None:
            if not self._sheet_files:
                raise ValueError("Workbook contains no sheets")
            name = next(iter(self._sheet_files))
        if name not in self._sheet_files:
            raise KeyError(f"Sheet '{name}' not found in {self.workbook_path}")

        sheet_path = self._sheet_files[name]
        with zipfile.ZipFile(self.workbook_path) as archive:
            sheet_tree = ET.fromstring(archive.read(sheet_path))
            raw_rows: List[Dict[int, str]] = []
            max_column = 0
            for row in sheet_tree.iter(f"{XL_NS}row"):
                row_values: Dict[int, str] = {}
                for cell in row.iter(f"{XL_NS}c"):
                    ref = cell.get("r", "A1")
                    column_ref = "".join(ch for ch in ref if ch.isalpha())
                    column_index = _column_index(column_ref)
                    max_column = max(max_column, column_index)

                    cell_type = cell.get("t")
                    value_element = cell.find(f"{XL_NS}v")
                    value: str
                    if value_element is None:
                        inline = cell.find(f"{XL_NS}is")
                        if inline is not None:
                            value = "".join(
                                t.text or "" for t in inline.iter(f"{XL_NS}t")
                            )
                        else:
                            value = ""
                    elif cell_type == "s":
                        value = self._shared_strings[int(value_element.text or "0")]
                    else:
                        value = value_element.text or ""
                    row_values[column_index] = value
                raw_rows.append(row_values)

            rows: List[List[str]] = []
            for row_values in raw_rows:
                row_list = ["" for _ in range(max_column)]
                for idx, value in row_values.items():
                    row_list[idx - 1] = value
                rows.append(row_list)

        return SheetData(name=name, rows=rows)

    def iter_sheets(self) -> Iterable[SheetData]:
        for name in self.sheet_names():
            yield self.read_sheet(name)
