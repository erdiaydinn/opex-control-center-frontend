"""Safe server-side parser for Workforce Time Off imports.

The browser never needs to unzip an XLSX and raw national identifiers are kept
inside the server parsing boundary. The parser intentionally uses only Python
stdlib ZIP/XML/CSV primitives so production does not depend on a spreadsheet
runtime for untrusted uploads.
"""

from __future__ import annotations

import base64
import csv
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
import re
import unicodedata
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_ZIP_MEMBERS = 250
MAX_MEMBER_BYTES = 12 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 40 * 1024 * 1024
MAX_SOURCE_ROWS = 20_000
MAX_EXPANDED_ROWS = 100_000


class TimeOffParseError(ValueError):
    """Raised when a Time Off upload is unsupported or unsafe to parse."""


def _safe_xml(payload: bytes, label: str) -> ET.Element:
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise TimeOffParseError(f"{label} DTD/entity içermemelidir.")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as error:
        raise TimeOffParseError(f"{label} XML yapısı okunamadı.") from error


def _fold(value: object) -> str:
    text = str(value or "").strip().replace("I", "ı").replace("İ", "i").casefold()
    text = text.translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _header_key(value: object) -> str:
    return _fold(value).replace(" ", "")


def _cell(row: dict[str, object], *aliases: str) -> object:
    normalized = {_header_key(key): value for key, value in row.items()}
    for alias in aliases:
        key = _header_key(alias)
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    return ""


def _national_id(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "".join(char for char in str(value or "") if char.isdigit())


def _excel_date(value: float) -> str:
    if value <= 0 or value > 200_000:
        return ""
    converted = date(1899, 12, 30) + timedelta(days=int(value))
    return converted.isoformat()


def _date_iso(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return _excel_date(float(value))
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        numeric = float(text.replace(",", "."))
        if numeric > 20_000:
            parsed = _excel_date(numeric)
            if parsed:
                return parsed
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], pattern).date().isoformat()
        except ValueError:
            continue
    return ""


def _enumerate_dates(start: str, end: str) -> list[str]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if end_date < start_date:
        raise TimeOffParseError("İzin bitiş tarihi başlangıç tarihinden önce olamaz.")
    days = (end_date - start_date).days + 1
    if days > 366:
        raise TimeOffParseError("Tek bir izin kaydı 366 günden uzun olamaz.")
    return [(start_date + timedelta(days=offset)).isoformat() for offset in range(days)]


_CATEGORY_ALIASES = (
    ("hastalik izni is kazasi", "work_accident"),
    ("is kazasi", "work_accident"),
    ("work accident", "work_accident"),
    ("annual leave", "annual"),
    ("yillik izin", "annual"),
    ("unpaid leave", "unpaid"),
    ("ucretsiz izin", "unpaid"),
    ("paternity leave", "paternity"),
    ("babalik izni", "paternity"),
    ("marriage leave", "marriage"),
    ("evlilik izni", "marriage"),
    ("bereavement leave", "bereavement"),
    ("yas izni", "bereavement"),
    ("sick leave", "report"),
    ("hastalik izni", "report"),
    ("raporlu", "report"),
    ("menstrual leave", "menstrual"),
    ("regl izni", "menstrual"),
    ("absence", "absence"),
    ("devamsizlik", "absence"),
    ("administrative leave", "administrative"),
    ("idari izin", "administrative"),
    ("relocation leave", "relocation"),
    ("tasinma izni", "relocation"),
    ("saha kahramanlari gunu", "fieldhero"),
)


def _leave_type(category: str) -> str:
    normalized = _fold(category)
    for alias, type_id in _CATEGORY_ALIASES:
        if alias in normalized:
            return type_id
    custom = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return f"custom_{custom}" if custom else "custom_unknown"


def _number(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


def _duration_minutes(row: dict[str, object]) -> int:
    minutes = _number(_cell(row, "leave minutes", "time off minutes", "izin dakika", "süre dakika"))
    if minutes > 0:
        return min(1440, round(minutes))
    hours = _number(_cell(row, "leave hours", "time off hours", "izin saati", "izin saat"))
    if hours > 0:
        return min(1440, round(hours * 60))
    amount = _number(_cell(row, "time off", "amount", "quantity", "miktar"))
    units = _fold(_cell(row, "units", "unit", "birim"))
    if amount > 0 and any(token in units for token in ("hour", "saat")):
        return min(1440, round(amount * 60))
    if amount > 0 and any(token in units for token in ("minute", "dakika")):
        return min(1440, round(amount))
    # Day-based values are intentionally not converted to a synthetic 7.5/8h.
    # The import service derives credit from the authoritative planned shift.
    return 0


def _column_index(reference: str) -> int:
    letters = "".join(char for char in reference if char.isalpha()).upper()
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - 64
    return max(0, value - 1)


def _shared_strings(archive: ZipFile) -> list[str]:
    name = "xl/sharedStrings.xml"
    if name not in archive.namelist():
        return []
    root = _safe_xml(archive.read(name), "XLSX sharedStrings")
    result = []
    for item in root:
        result.append("".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")))
    return result


def _sheet_path(archive: ZipFile, preferred_sheet: str = "Time Off Used") -> str:
    workbook = _safe_xml(archive.read("xl/workbook.xml"), "XLSX workbook")
    relations = _safe_xml(archive.read("xl/_rels/workbook.xml.rels"), "XLSX relationships")
    relationship_targets = {
        item.attrib.get("Id", ""): item.attrib.get("Target", "")
        for item in relations
        if str(item.attrib.get("TargetMode", "Internal")).lower() != "external"
    }
    sheets = []
    archive_names = set(archive.namelist())
    for element in workbook.iter():
        if not element.tag.endswith("}sheet"):
            continue
        relationship_id = next((value for key, value in element.attrib.items() if key.endswith("}id")), "")
        target = relationship_targets.get(relationship_id, "")
        if not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = target if target.startswith("xl/") else f"xl/{target.lstrip('./')}"
        if ".." in path.split("/") or path not in archive_names:
            raise TimeOffParseError("XLSX çalışma sayfası ilişkisi güvenli paket sınırının dışında.")
        sheets.append((element.attrib.get("name", ""), path))
    if not sheets:
        raise TimeOffParseError("XLSX içinde çalışma sayfası bulunamadı.")
    preferred = next((path for name, path in sheets if _fold(name) == _fold(preferred_sheet)), None)
    return preferred or sheets[0][1]


def _xlsx_rows(data: bytes) -> list[dict[str, object]]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise TimeOffParseError("XLSX güvenlik limiti aşıldı: çok fazla ZIP üyesi.")
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES or any(info.file_size > MAX_MEMBER_BYTES for info in infos):
                raise TimeOffParseError("XLSX güvenlik limiti aşıldı: sıkıştırılmış içerik çok büyük.")
            required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
            if not required.issubset(set(archive.namelist())):
                raise TimeOffParseError("Dosya geçerli bir XLSX çalışma kitabı değil.")
            shared = _shared_strings(archive)
            root = _safe_xml(archive.read(_sheet_path(archive)), "XLSX worksheet")
            matrix: list[list[object]] = []
            for row_node in (node for node in root.iter() if node.tag.endswith("}row")):
                values: dict[int, object] = {}
                for cell_node in (node for node in row_node if node.tag.endswith("}c")):
                    index = _column_index(cell_node.attrib.get("r", "A1"))
                    cell_type = cell_node.attrib.get("t", "")
                    value_node = next((node for node in cell_node if node.tag.endswith("}v")), None)
                    if cell_type == "inlineStr":
                        value: object = "".join(node.text or "" for node in cell_node.iter() if node.tag.endswith("}t"))
                    elif value_node is None:
                        value = ""
                    elif cell_type == "s":
                        try:
                            value = shared[int(value_node.text or "0")]
                        except (IndexError, ValueError):
                            value = ""
                    elif cell_type == "b":
                        value = (value_node.text or "0") == "1"
                    elif cell_type in {"str", "e"}:
                        value = value_node.text or ""
                    else:
                        raw = value_node.text or ""
                        try:
                            numeric = float(raw)
                            value = int(numeric) if numeric.is_integer() else numeric
                        except ValueError:
                            value = raw
                    values[index] = value
                if values:
                    width = max(values) + 1
                    matrix.append([values.get(index, "") for index in range(width)])
            if not matrix:
                return []
            headers = [str(value or "").strip() for value in matrix[0]]
            rows = []
            for values in matrix[1:MAX_SOURCE_ROWS + 1]:
                row = {header: values[index] if index < len(values) else "" for index, header in enumerate(headers) if header}
                if any(value not in (None, "") for value in row.values()):
                    rows.append(row)
            if len(matrix) - 1 > MAX_SOURCE_ROWS:
                raise TimeOffParseError(f"Time Off dosyası {MAX_SOURCE_ROWS} satır limitini aşıyor.")
            return rows
    except BadZipFile as error:
        raise TimeOffParseError("Dosya geçerli bir XLSX ZIP paketi değil.") from error


def _csv_rows(data: bytes) -> list[dict[str, object]]:
    text = None
    for encoding in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise TimeOffParseError("CSV karakter kodlaması okunamadı.")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    rows = []
    for index, row in enumerate(reader):
        if index >= MAX_SOURCE_ROWS:
            raise TimeOffParseError(f"Time Off dosyası {MAX_SOURCE_ROWS} satır limitini aşıyor.")
        rows.append({str(key or "").strip(): value for key, value in row.items() if key is not None})
    return rows


def parse_timeoff_bytes(file_name: str, data: bytes) -> dict:
    if not data:
        raise TimeOffParseError("Time Off dosyası boş.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise TimeOffParseError("Time Off dosyası 12 MB güvenlik limitini aşıyor.")
    lowered = str(file_name or "").lower()
    if lowered.endswith(".xlsx"):
        source_rows = _xlsx_rows(data)
    elif lowered.endswith((".csv", ".txt")):
        source_rows = _csv_rows(data)
    elif lowered.endswith(".xls"):
        raise TimeOffParseError("Eski .xls biçimi desteklenmiyor; dosyayı .xlsx veya .csv olarak kaydedin.")
    else:
        raise TimeOffParseError("Time Off için yalnız .xlsx ve .csv dosyaları kabul edilir.")

    rows = []
    invalid_count = 0
    sensitive_only_count = 0
    for index, source in enumerate(source_rows):
        person_id = str(_cell(source, "employee number", "employee no", "employee id", "hr employee id", "personel id", "sicil no", "sicil numarası", "sap id") or "").strip()
        national_id = _national_id(_cell(source, "tc", "tck", "tckn", "tc no", "tc kimlik", "tc kimlik no", "tc kimlik numarası", "kimlik no", "kimlik numarası", "national id", "national identity number"))
        raw_name = str(_cell(source, "name", "worker", "employee name", "ad soyad", "personel adı", "personel adi") or "").strip()
        person_name = " ".join(reversed([part.strip() for part in raw_name.split(",", 1)])) if "," in raw_name else raw_name
        category = str(_cell(source, "category", "leave category", "izin türü", "izin tipi", "time off type") or "").strip()
        single_date = _date_iso(_cell(source, "time off date", "leave date", "izin tarihi"))
        start = single_date or _date_iso(_cell(source, "from", "start", "start date", "başlangıç", "başlangıç tarihi", "izin başlangıç"))
        end = single_date or _date_iso(_cell(source, "to", "end", "end date", "bitiş", "bitiş tarihi", "izin bitiş")) or start
        if not start or not category or (not person_id and len(national_id) != 11):
            invalid_count += 1
            continue
        if not person_id and len(national_id) == 11:
            sensitive_only_count += 1
        leave_minutes = _duration_minutes(source)
        for leave_date in _enumerate_dates(start, end):
            if len(rows) >= MAX_EXPANDED_ROWS:
                raise TimeOffParseError(f"Genişletilmiş izin satırları {MAX_EXPANDED_ROWS} limitini aşıyor.")
            rows.append({
                "id": f"TO-{person_id or 'TC'}-{leave_date}-{index}",
                "person_id": person_id,
                "source_person_id": person_id,
                "national_id": national_id if len(national_id) == 11 else "",
                "person_name": person_name,
                "category": category,
                "type_id": _leave_type(category),
                "date": leave_date,
                "minutes": leave_minutes,
                "approval": "Onaylandı",
                "note": str(_cell(source, "notes", "note", "not", "açıklama") or category),
                "requested_at": _date_iso(_cell(source, "requested", "request date", "talep tarihi")),
                "approved_at": _date_iso(_cell(source, "approved", "approval date", "onay tarihi")),
                "source": "DM Time Off" if single_date and person_id else "Time Off Used",
                "source_key": f"{person_id or 'TC'}|{leave_date}",
            })
    return {
        "rows": rows,
        "source_count": len(source_rows),
        "invalid_count": invalid_count,
        "sensitive_only_count": sensitive_only_count,
        "parser": "secure-server-timeoff-v1",
    }


def parse_timeoff_payload(file_name: str, content_base64: str) -> dict:
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (ValueError, TypeError) as error:
        raise TimeOffParseError("Time Off dosyası base64 olarak çözülemedi.") from error
    return parse_timeoff_bytes(file_name, data)
