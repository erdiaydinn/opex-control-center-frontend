import http from 'k6/http';
import { check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const flowFailures = new Rate('academy_playback_flow_failures');
const manifestLatency = new Trend('academy_manifest_latency', true);
const segmentLatency = new Trend('academy_segment_latency', true);

export const options = {
  scenarios: {
    smoke: {
      executor: 'constant-vus',
      vus: 10,
      duration: '2m',
    },
  },
  thresholds: {
    academy_playback_flow_failures: ['rate<0.01'],
    academy_manifest_latency: ['p(95)<750'],
    academy_segment_latency: ['p(95)<500'],
  },
};

function firstMediaUri(body) {
  for (const raw of (body || '').split('\n')) {
    const line = raw.trim();
    if (line && !line.startsWith('#')) return line;
  }
  return null;
}

function resolveLikeBrowser(parentUrl, child) {
  if (/^https:\/\//i.test(child)) return child;
  const parent = new URL(parentUrl);
  if (child.startsWith('/')) return `${parent.protocol}//${parent.host}${child}`;
  const directory = parent.pathname.slice(0, parent.pathname.lastIndexOf('/') + 1);
  // Relative playlist/segment URLs do not inherit the parent's query string.
  return `${parent.protocol}//${parent.host}${directory}${child}`;
}

function getPlaylistOrSegment(url) {
  return http.get(url, { redirects: 0 });
}

export default function () {
  const api = __ENV.ACADEMY_BASE_URL;
  const mediaId = __ENV.ACADEMY_MEDIA_ID;
  const bearer = __ENV.ACADEMY_BEARER_TOKEN;
  if (!api || !mediaId || !bearer) {
    throw new Error('ACADEMY_BASE_URL, ACADEMY_MEDIA_ID and ACADEMY_BEARER_TOKEN are required');
  }

  const auth = http.post(`${api}/v1/academy/media/${mediaId}/playback-authorization`, null, {
    headers: { Authorization: `Bearer ${bearer}` },
  });
  let ok = check(auth, {
    'playback authorization 200': (r) => r.status === 200,
    'short-lived authorization': (r) => {
      try {
        const ttl = r.json().expires_in_seconds;
        return ttl >= 30 && ttl <= 300;
      } catch (_) {
        return false;
      }
    },
  });
  if (!ok) {
    flowFailures.add(true);
    return;
  }

  const manifestUrl = auth.json().playback_url;
  const manifest = getPlaylistOrSegment(manifestUrl);
  manifestLatency.add(manifest.timings.duration);
  ok = check(manifest, {
    'authorized manifest 2xx': (r) => r.status >= 200 && r.status < 300,
    'manifest looks like HLS': (r) => (r.body || '').includes('#EXTM3U'),
  });
  if (!ok) {
    flowFailures.add(true);
    return;
  }

  let child = firstMediaUri(manifest.body);
  if (!child) {
    flowFailures.add(true);
    return;
  }

  let childUrl = resolveLikeBrowser(manifestUrl, child);
  let response = getPlaylistOrSegment(childUrl);

  // Master playlists point to a variant playlist. Follow one level using the
  // browser-resolved URL so query-token inheritance bugs are exposed.
  if ((response.body || '').includes('#EXTM3U')) {
    const segmentRef = firstMediaUri(response.body);
    if (!segmentRef) {
      flowFailures.add(true);
      return;
    }
    childUrl = resolveLikeBrowser(childUrl, segmentRef);
    response = getPlaylistOrSegment(childUrl);
  }

  segmentLatency.add(response.timings.duration);
  ok = check(response, {
    'segment authorized after browser URL resolution': (r) => r.status >= 200 && r.status < 300,
    'segment served by CDN': (r) => Boolean(r.headers['Age'] || r.headers['X-Cache'] || r.headers['Cf-Cache-Status'] || r.headers['Via']),
  });
  flowFailures.add(!ok);
}
