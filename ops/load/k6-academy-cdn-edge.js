import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const failures = new Rate('academy_edge_failures');
const latency = new Trend('academy_edge_latency', true);

export const options = {
  scenarios: {
    edge: { executor: 'constant-arrival-rate', rate: 400, timeUnit: '1s', duration: '10m', preAllocatedVUs: 250, maxVUs: 1000 },
  },
  thresholds: {
    academy_edge_failures: ['rate<0.01'],
    academy_edge_latency: ['p(95)<250', 'p(99)<500'],
  },
};

export default function () {
  const url = __ENV.ACADEMY_CDN_SEGMENT_URL;
  if (!url) throw new Error('ACADEMY_CDN_SEGMENT_URL is required; use a representative immutable HLS/DASH segment through the real CDN');
  const res = http.get(url);
  latency.add(res.timings.duration);
  const ok = check(res, {
    'edge 2xx': (r) => r.status >= 200 && r.status < 300,
    'cache telemetry present': (r) => Boolean(r.headers['Age'] || r.headers['X-Cache'] || r.headers['Cf-Cache-Status']),
  });
  failures.add(!ok);
}
