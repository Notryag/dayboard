"use client";

import {
  Activity,
  Check,
  ChevronDown,
  CircleAlert,
  LoaderCircle,
  Wrench,
} from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/i18n";

import type { RunActivityState, RunActivityStep } from "./runActivity";
import styles from "./RunActivityTimeline.module.css";

type RunActivityTimelineProps = {
  runId: string | null;
  state: RunActivityState;
  steps: RunActivityStep[];
};

type DisclosureOverride = {
  runKey: string;
  state: RunActivityState;
  expanded: boolean;
};

export function RunActivityTimeline({ runId, state, steps }: RunActivityTimelineProps) {
  const { t } = useI18n();
  const [disclosure, setDisclosure] = useState<DisclosureOverride | null>(null);

  if (!steps.length || state === "idle") return null;

  const runKey = runId ?? steps[0]?.id ?? "unknown";
  const expanded = disclosure?.runKey === runKey && disclosure.state === state
    ? disclosure.expanded
    : state === "running" || state === "failed";

  return (
    <section aria-label={t("chat.activityTitle")} aria-live="polite" className={styles.timeline}>
      <button
        aria-expanded={expanded}
        className={styles.header}
        onClick={() => setDisclosure({ runKey, state, expanded: !expanded })}
        type="button"
      >
        <Activity aria-hidden="true" size={15} />
        <span>{t("chat.activityTitle")}</span>
        <small>{activitySummary(state, t)}</small>
        <ChevronDown
          aria-hidden="true"
          className={`${styles.toggle} ${expanded ? styles.toggleExpanded : ""}`}
          size={15}
        />
      </button>
      {expanded ? (
        <ol className={styles.list}>
          {steps.map((step) => {
            const terminal = step.state !== "running";
            const StepIcon = step.kind === "tool" ? Wrench : Activity;
            return (
              <li className={styles.item} key={step.id} title={step.name}>
                <span className={`${styles.stateIcon} ${step.state === "failed" ? styles.failed : ""}`}>
                  {step.state === "failed" ? <CircleAlert aria-hidden="true" size={14} />
                    : terminal ? <Check aria-hidden="true" size={14} />
                      : <LoaderCircle aria-hidden="true" className={styles.spinner} size={14} />}
                </span>
                <StepIcon aria-hidden="true" className={styles.kindIcon} size={13} />
                <span className={styles.text}>{step.text}</span>
                <span className={styles.status}>
                  {step.durationMs !== undefined ? <small>{formatDuration(step.durationMs)}</small> : null}
                  {stepStateLabel(step.state, t)}
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}

function activitySummary(state: RunActivityState, t: ReturnType<typeof useI18n>["t"]): string {
  return {
    idle: "",
    running: t("chat.activityRunning"),
    completed: t("chat.activityCompleted"),
    failed: t("chat.activityFailed"),
    cancelled: t("chat.activityCancelled"),
  }[state];
}

function stepStateLabel(
  state: RunActivityStep["state"],
  t: ReturnType<typeof useI18n>["t"],
): string {
  return {
    running: t("chat.activityStepRunning"),
    completed: t("chat.activityStepCompleted"),
    failed: t("chat.activityStepFailed"),
  }[state];
}

function formatDuration(durationMs: number): string {
  if (durationMs < 1_000) return `${durationMs} ms`;
  return `${(durationMs / 1_000).toFixed(durationMs < 10_000 ? 1 : 0)} s`;
}
