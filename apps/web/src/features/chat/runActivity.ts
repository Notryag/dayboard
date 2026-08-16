export type RunActivityState = "idle" | "running" | "completed" | "failed" | "cancelled";
export type RunActivityStepState = "running" | "completed" | "failed";

export type RunActivityStep = {
  id: string;
  eventType: string;
  text: string;
  kind: "run" | "tool" | "subagent";
  state: RunActivityStepState;
  name?: string;
  taskId?: string;
  durationMs?: number;
};

export function upsertRunActivityStep(
  steps: RunActivityStep[],
  incoming: RunActivityStep,
): RunActivityStep[] {
  const index = steps.findIndex((step) => step.id === incoming.id);
  if (index === -1) return [...steps, incoming];
  const next = [...steps];
  next[index] = {
    ...steps[index],
    ...incoming,
    durationMs: incoming.durationMs ?? steps[index]?.durationMs,
  };
  return next;
}

export function settleRunActivitySteps(
  steps: RunActivityStep[],
  state: Exclude<RunActivityState, "idle" | "running">,
): RunActivityStep[] {
  return steps.map((step) => step.state === "running"
    ? { ...step, state: state === "failed" ? "failed" : "completed" }
    : step);
}
