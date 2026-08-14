import http from "k6/http";
import { check } from "k6";
import { Rate, Trend } from "k6/metrics";

const isolationFailures = new Rate("tenant_isolation_failures");
const contextLatency = new Trend("platform_context_latency", true);
const memberLatency = new Trend("platform_member_latency", true);

const loadProfile = (__ENV.LOAD_PROFILE || "burst").trim().toLowerCase();
const isLatencyProfile = loadProfile === "latency";
const targetVus = Number(
  __ENV.TARGET_VUS || (isLatencyProfile ? 50 : 1000),
);
const iterationsPerVu = Number(
  __ENV.ITERATIONS_PER_VU || (isLatencyProfile ? 2 : 1),
);

if (!Number.isInteger(targetVus) || targetVus < 1) {
  throw new Error("TARGET_VUS must be a positive integer");
}
if (!Number.isInteger(iterationsPerVu) || iterationsPerVu < 1) {
  throw new Error("ITERATIONS_PER_VU must be a positive integer");
}
if (!new Set(["burst", "latency"]).has(loadProfile)) {
  throw new Error("LOAD_PROFILE must be burst or latency");
}

const latencyThresholds = isLatencyProfile
  ? {
      platform_context_latency: ["p(95)<2000", "p(99)<3000"],
      platform_member_latency: ["p(95)<2000", "p(99)<3000"],
    }
  : {
      // A 1000-VU all-at-once burst intentionally saturates the small
      // GitHub-hosted runner and its default PostgreSQL connection ceiling.
      // These are catastrophic-queueing guards, not production SLOs.
      platform_context_latency: ["p(95)<12000", "p(99)<15000"],
      platform_member_latency: ["p(95)<12000", "p(99)<15000"],
    };

export const options = {
  scenarios: {
    tenant_isolation: {
      executor: "per-vu-iterations",
      vus: targetVus,
      iterations: iterationsPerVu,
      maxDuration: __ENV.MAX_DURATION || "90s",
    },
  },
  thresholds: {
    // Correctness and isolation remain hard gates in every profile.
    http_req_failed: ["rate==0"],
    checks: ["rate==1"],
    tenant_isolation_failures: ["rate==0"],
    ...latencyThresholds,
  },
};

const base = (__ENV.BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const tenantA = __ENV.TENANT_A_ID;
const tenantB = __ENV.TENANT_B_ID;
const tokenA = __ENV.TOKEN_A;
const tokenB = __ENV.TOKEN_B;
const subjectA = __ENV.SUBJECT_A || "load-a";
const subjectB = __ENV.SUBJECT_B || "load-b";

function required(name, value) {
  if (!value) throw new Error(`${name} is required`);
  return value;
}

required("TENANT_A_ID", tenantA);
required("TENANT_B_ID", tenantB);
required("TOKEN_A", tokenA);
required("TOKEN_B", tokenB);

function jsonOrNull(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

export default function () {
  const useA = __VU % 2 === 1;
  const expectedTenant = useA ? tenantA : tenantB;
  const foreignTenant = useA ? tenantB : tenantA;
  const ownSubject = useA ? subjectA : subjectB;
  const foreignSubject = useA ? subjectB : subjectA;
  const token = useA ? tokenA : tokenB;
  const headers = {
    Authorization: `Bearer ${token}`,
    "X-Request-ID": `${loadProfile}-${__VU}-${__ITER}-context`,
  };

  const context = http.get(`${base}/v1/context`, {
    headers,
    tags: { route: "context", profile: loadProfile },
  });
  contextLatency.add(context.timings.duration);
  const contextBody = jsonOrNull(context);
  const contextOk = check(context, {
    "context returns 200": (r) => r.status === 200,
    "context is server-scoped to expected tenant": () =>
      contextBody?.tenant_id === expectedTenant,
    "context never returns foreign tenant": () =>
      contextBody?.tenant_id !== foreignTenant,
  });

  const members = http.get(`${base}/v1/admin/members`, {
    headers: {
      ...headers,
      "X-Request-ID": `${loadProfile}-${__VU}-${__ITER}-members`,
    },
    tags: { route: "members", profile: loadProfile },
  });
  memberLatency.add(members.timings.duration);
  const memberBody = jsonOrNull(members);
  const items = Array.isArray(memberBody?.items) ? memberBody.items : [];
  const memberOk = check(members, {
    "members returns 200": (r) => r.status === 200,
    "members response tenant is expected tenant": () =>
      memberBody?.tenant_id === expectedTenant,
    "own membership is visible": () =>
      items.some((item) => item?.subject === ownSubject || item?.external_subject === ownSubject),
    "foreign membership is not visible": () =>
      !items.some((item) => item?.subject === foreignSubject || item?.external_subject === foreignSubject),
  });

  isolationFailures.add(!(contextOk && memberOk));
}
