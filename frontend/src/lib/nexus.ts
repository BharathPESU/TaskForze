export type AgentStatus = {
  name: string;
  status: string;
  type: string;
  message: string;
  workflow_id?: string | null;
  last_update?: string | null;
};

export type TaskItem = {
  id: string;
  title: string;
  description?: string;
  priority?: number;
  priority_score?: number | null;
  deadline?: string | null;
  effort_hours?: number | null;
  status?: string;
};

export type WorkflowItem = {
  id: string;
  user_intent?: string;
  created_at?: string;
  status?: string;
  plan?: Array<unknown>;
};

export type AuthStatus = {
  authenticated: boolean;
  has_oauth_client: boolean;
  email?: string;
  services?: Record<string, boolean>;
};

export type HealthStatus = {
  status: string;
  service: string;
  version: string;
  agents: number;
  oauth_configured: boolean;
  integrations: Record<string, string>;
};

export type TraceEvent = {
  type: "trace";
  agent: string;
  status: string;
  message: string;
  workflow_id: string;
  timestamp: string;
  meta: Record<string, unknown>;
};

export type WorkflowAgentOutput = {
  status: string;
  summary?: string;
  error?: string;
};

export type ResultEvent = {
  workflow_id: string;
  summary: string;
  key_actions?: string[];
  warnings?: string[];
  follow_up_suggestions?: string[];
  workflow?: {
    agent_outputs?: Record<string, WorkflowAgentOutput>;
  };
  timestamp?: string;
};

export const API_PREFIX = "/api";

export function apiPath(path: string) {
  return `${API_PREFIX}${path}`;
}

export async function nexusFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiPath(path), {
    ...init,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }

  return (await response.json()) as T;
}
