// API client for the Devices / Ambient Intelligence section — the ARBITER that
// resolves the fixed H003 care home from its three observation sources
// (Pattern · Mood · Safety) plus manual human overrides. Every call is
// ephemeral; nothing is persisted, so the demo can be poked at endlessly.
//
// Routes go through the gateway (VITE_API_BASE_URL → :8000) under /devices,
// matching the rest of the app. A direct devices-service port can be forced
// with VITE_DEVICES_API_BASE for local isolation.
const BASE =
  import.meta.env.VITE_DEVICES_API_BASE ||
  `${import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"}/devices`;

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : null;
}

export const deviceApi = {
  health: () => request("/health"),

  // The fixed H003 demo script: source metadata, mood/safety signal catalogues,
  // learned routines, and the guided walkthrough beats.
  scenario: () => request("/scenario"),

  // Resolve the whole house for one moment in time. Deterministic.
  // body = {
  //   time?: "HH:MM",                 // demo clock → drives PATTERN routines
  //   mood?: string | null,           // active mood signal id
  //   safety?: string | null,         // active safety signal id
  //   manual?: { [deviceId]: boolean },// human overrides (room → MANUAL)
  // }
  arbitrate: (body) =>
    request("/arbitrate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export { BASE as DEVICES_API_BASE };
