import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    inventory_scans: {
      executor: "ramping-vus",
      stages: [
        { duration: "2m", target: Number(__ENV.TARGET_VUS || 400) },
        { duration: "10m", target: Number(__ENV.TARGET_VUS || 400) },
        { duration: "2m", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    checks: ["rate>0.99"],
  },
};

const base = __ENV.BASE_URL;
const token = __ENV.ACCESS_TOKEN;
const document = __ENV.DOCUMENT_ID;

export default function () {
  const payload = JSON.stringify({
    client_event_id: `${__VU}-${__ITER}-${Date.now()}`,
    device_id: `LOAD-${__VU}`,
    location: __ENV.LOCATION || "A-01-01",
    barcode: __ENV.BARCODE || "8690000000001",
    quantity: 1,
    source: "TERMINAL",
    symbology: "EAN13",
  });
  const response = http.post(`${base}/api/inventory/documents/${document}/scans`, payload, {
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
  });
  check(response, { "scan accepted or idempotent": (r) => r.status === 200 });
  sleep(0.2);
}
