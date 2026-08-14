import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const failures = new Rate('academy_auth_failures');
const latency = new Trend('academy_auth_latency', true);

export const options = {
  scenarios: {
    sustained: { executor: 'constant-arrival-rate', rate: 50, timeUnit: '1s', duration: '5m', preAllocatedVUs: 100, maxVUs: 400 },
    burst: { executor: 'constant-arrival-rate', startTime: '5m15s', rate: 200, timeUnit: '1s', duration: '1m', preAllocatedVUs: 250, maxVUs: 800 },
  },
  thresholds: {
    academy_auth_failures: ['rate<0.01'],
    academy_auth_latency: ['p(95)<500', 'p(99)<1000'],
  },
};

export default function () {
  const base = __ENV.ACADEMY_BASE_URL;
  const media = __ENV.ACADEMY_MEDIA_ID;
  const token = __ENV.ACADEMY_BEARER_TOKEN;
  if (!base || !media || !token) throw new Error('ACADEMY_BASE_URL, ACADEMY_MEDIA_ID and ACADEMY_BEARER_TOKEN are required');
  const res = http.post(`${base}/v1/academy/media/${media}/playback-authorization`, null, { headers: { Authorization: `Bearer ${token}` } });
  latency.add(res.timings.duration);
  const ok = check(res, {
    'authorization 200': (r) => r.status === 200,
    'no origin bucket leak': (r) => !/s3:\/\/|storage_bucket|storage_key|private-origin/i.test(r.body || ''),
    'short lived grant': (r) => { try { const v = r.json().expires_in_seconds; return v >= 30 && v <= 300; } catch (_) { return false; } },
  });
  failures.add(!ok);
}
