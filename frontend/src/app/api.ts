export type HealthPayload = {
  status: string;
  request_id: string;
  database?: string;
};

export async function fetchHealth(path: "/health/live" | "/health/ready"): Promise<HealthPayload> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  const body = (await response.json()) as HealthPayload & {
    error?: { message?: string; request_id?: string };
  };
  if (!response.ok) {
    throw new Error(body.error?.message ?? `HTTP ${response.status}`);
  }
  return body;
}
