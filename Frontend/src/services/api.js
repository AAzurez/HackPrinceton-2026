const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:5000").replace(/\/$/, "");

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.error || `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return payload;
}

export function getHealth() {
  return request("/health", { method: "GET" });
}

export function getDemoScenario() {
  return request("/api/demo-scenario", { method: "GET" });
}

export function optimizeSchedule(payload) {
  return request("/api/optimize", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export { API_BASE_URL };
