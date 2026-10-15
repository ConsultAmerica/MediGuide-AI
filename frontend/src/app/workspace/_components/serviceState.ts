import type { HealthResponse } from "../_state/workspace-shared";

export type ServiceTone = "checking" | "ok" | "limited" | "down";

/** What /api/health actually reported, never a default "healthy". */
export function serviceStateFrom(health: HealthResponse | null): { tone: ServiceTone; label: string } {
  if (!health) return { tone: "checking", label: "Checking services" };
  if (health.total > 0 && health.ready >= health.total) return { tone: "ok", label: "All services available" };
  if (health.ready > 0) return { tone: "limited", label: `${health.ready} of ${health.total} services available` };
  return { tone: "down", label: "Services unavailable" };
}
