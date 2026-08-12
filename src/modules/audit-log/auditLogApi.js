import { apiFetch } from "../../api/client";

export async function fetchAuditEvents({
  limit = 50,
  actor = "",
  decision = "",
  action = "",
} = {}) {
  const params = new URLSearchParams();

  params.set("limit", String(limit));

  if (actor) {
    params.set("actor", actor);
  }

  if (decision) {
    params.set("decision", decision);
  }

  if (action) {
    params.set("action", action);
  }

  return apiFetch(
    `/v1/audit/events?${params.toString()}`,
    {
      method: "GET",
    }
  );
}
