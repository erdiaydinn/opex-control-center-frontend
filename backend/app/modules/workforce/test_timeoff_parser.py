from copy import deepcopy
import base64
from io import BytesIO
import os
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from app.main import app
from app.modules.workforce import service
from app.modules.workforce.timeoff_parser import TimeOffParseError, _safe_xml, parse_timeoff_bytes


ADMIN_HEADERS = {
    "X-OPEX-User": "timeoff-admin@example.com",
    "X-OPEX-Role": "super_admin",
    "X-OPEX-Permissions": "importTimeOff,manageEmployees",
}


def minimal_xlsx(headers, values, sheet_name="Time Off Used") -> bytes:
    def inline_cell(column, row, value):
        return f'<c r="{column}{row}" t="inlineStr"><is><t>{value}</t></is></c>'

    columns = [chr(ord("A") + index) for index in range(len(headers))]
    header_cells = "".join(inline_cell(column, 1, value) for column, value in zip(columns, headers))
    value_cells = "".join(inline_cell(column, 2, value) for column, value in zip(columns, values))
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1">{header_cells}</row><row r="2">{value_cells}</row></sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return stream.getvalue()


class TimeOffParserTests(unittest.TestCase):
    def setUp(self):
        self.people = deepcopy(service._PEOPLE)
        self.environment = patch.dict(os.environ, {
            "DOCKOS_ENV": "development",
            "OPEX_ALLOW_LEGACY_HEADERS": "true",
            "OPEX_PII_KEY": base64.urlsafe_b64encode(b"timeoff-parser-test-key-material!!"[:32]).decode(),
        }, clear=False)
        self.environment.start()
        self.client = TestClient(app, raise_server_exceptions=True)

    def tearDown(self):
        service._PEOPLE[:] = self.people
        self.environment.stop()

    def test_dm_xlsx_supports_time_off_date_worker_and_combined_category(self):
        payload = minimal_xlsx(
            ["TCKN", "Employee ID", "Worker", "Time off Type", "Time Off Date"],
            ["31987654310", "2021-11-0092", "Alper Sezen", "TUR Annual Leave - Yıllık İzin", "01.06.2026"],
        )
        parsed = parse_timeoff_bytes("dm-timeoff.xlsx", payload)
        self.assertEqual(parsed["source_count"], 1)
        self.assertEqual(parsed["invalid_count"], 0)
        self.assertEqual(len(parsed["rows"]), 1)
        self.assertEqual(parsed["rows"][0]["person_id"], "2021-11-0092")
        self.assertEqual(parsed["rows"][0]["person_name"], "Alper Sezen")
        self.assertEqual(parsed["rows"][0]["type_id"], "annual")
        self.assertEqual(parsed["rows"][0]["date"], "2026-06-01")
        self.assertEqual(parsed["rows"][0]["minutes"], 0)

    def test_xlsx_xml_dtd_and_entity_are_rejected_before_parsing(self):
        malicious = b'<!DOCTYPE x [<!ENTITY leak "boom">]><x>&leak;</x>'
        with self.assertRaises(TimeOffParseError):
            _safe_xml(malicious, "XLSX worksheet")

    def test_work_accident_wins_over_generic_sick_leave(self):
        csv_bytes = (
            "Employee Number;Name;Category;From;To\n"
            "28071;Test Person;Hastalık İzni (İş Kazası);08.07.2026;08.07.2026\n"
        ).encode("utf-8")
        parsed = parse_timeoff_bytes("timeoff.csv", csv_bytes)
        self.assertEqual(parsed["rows"][0]["type_id"], "work_accident")

    def test_router_uses_tckn_only_server_side_and_never_returns_it(self):
        service.upsert_people([{
            "employee_id": "EMP-TIMEOFF-1",
            "roster_ids": [],
            "full_name": "Secure Time Off Person",
            "tckn": "31987654310",
            "position": "Picker",
            "warehouse_id": "fulya",
            "active": True,
        }], "test")
        csv_bytes = (
            "TCKN;Worker;Time off Type;Time Off Date\n"
            "31987654310;Secure Time Off Person;TUR Annual Leave - Yıllık İzin;01.06.2026\n"
        ).encode("utf-8")
        response = self.client.post(
            "/api/workforce/time-off/parse",
            json={"file_name": "dm.csv", "content_base64": base64.b64encode(csv_bytes).decode()},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body["sensitive_data_exposed"])
        self.assertEqual(body["identity_resolved_count"], 1)
        self.assertEqual(body["rows"][0]["person_id"], "EMP-TIMEOFF-1")
        serialized = str(body)
        self.assertNotIn("31987654310", serialized)
        self.assertNotIn("national_id", serialized)
        self.assertNotIn("tckn", serialized.casefold())

    def test_unmatched_tckn_only_row_is_not_returned_to_browser(self):
        csv_bytes = (
            "TCKN;Worker;Time off Type;Time Off Date\n"
            "41987654310;Unknown Person;Yıllık İzin;01.06.2026\n"
        ).encode("utf-8")
        response = self.client.post(
            "/api/workforce/time-off/parse",
            json={"file_name": "dm.csv", "content_base64": base64.b64encode(csv_bytes).decode()},
            headers=ADMIN_HEADERS,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["rows"], [])
        self.assertEqual(response.json()["sensitive_only_unmatched_count"], 1)
        self.assertNotIn("41987654310", str(response.json()))

    def test_parse_endpoint_requires_import_timeoff_permission(self):
        csv_bytes = b"Employee ID;Worker;Time off Type;Time Off Date\nEMP-1;Test;Yillik Izin;01.06.2026\n"
        response = self.client.post(
            "/api/workforce/time-off/parse",
            json={"file_name": "dm.csv", "content_base64": base64.b64encode(csv_bytes).decode()},
            headers={"X-OPEX-User": "viewer@example.com", "X-OPEX-Role": "viewer"},
        )
        self.assertEqual(response.status_code, 403)

    def test_production_warehouse_scope_blocks_cross_warehouse_identity_discovery(self):
        service._PEOPLE[:] = [
            {"id": "EMP-FULYA", "employee_id": "EMP-FULYA", "full_name": "Fulya Person", "warehouse_id": "fulya", "active": True},
            {"id": "EMP-USK", "employee_id": "EMP-USK", "full_name": "Uskudar Person", "warehouse_id": "uskudar", "active": True},
        ]
        claims = {
            "sub": "fulya-manager", "name": "Fulya Manager", "roles": ["warehouse_manager"],
            "permissions": ["importTimeOff"], "warehouse_scope": ["fulya"],
        }
        csv_bytes = (
            "Employee ID;Worker;Time off Type;Time Off Date\n"
            "EMP-FULYA;Fulya Person;Yıllık İzin;01.06.2026\n"
            "EMP-USK;Uskudar Person;Yıllık İzin;01.06.2026\n"
        ).encode("utf-8")
        with (
            patch.dict(os.environ, {"DOCKOS_ENV": "production", "OPEX_ALLOW_LEGACY_HEADERS": "false"}, clear=False),
            patch("app.security._decode_bearer", return_value=claims),
        ):
            response = self.client.post(
                "/api/workforce/time-off/parse",
                json={"file_name": "dm.csv", "content_base64": base64.b64encode(csv_bytes).decode()},
                headers={"Authorization": "Bearer signed.manager.jwt"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual([row["person_id"] for row in body["rows"]], ["EMP-FULYA"])
        self.assertEqual(body["scope_blocked_count"], 1)
        self.assertNotIn("EMP-USK", str(body))


if __name__ == "__main__":
    unittest.main()
