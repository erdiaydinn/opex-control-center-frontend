import { apiGet } from "../../api/client.js";


function camelKey(key) {
  return key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

function camel(value) {
  if (Array.isArray(value)) return value.map(camel);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [camelKey(key), camel(item)]),
    );
  }
  return value;
}

async function request(path) {
  try {
    return camel(await apiGet(path));
  } catch (error) {
    const safe = new Error("");
    safe.name = "WorkforceCommandCenterError";
    safe.cause = error;
    throw safe;
  }
}

export async function loadWorkforceCommandCenterLocations() {
  const result = await request("/workforce/warehouses");
  return result.rows || [];
}

export function loadWorkforceCommandCenter(locationId) {
  return request(`/workforce/command-center/${encodeURIComponent(locationId)}`);
}
