"use client";

import styles from "./RunActivityTicker.module.css";

export type RunActivityStep = {
  eventType: string;
  text: string;
};

type RunActivityTickerProps = {
  steps: RunActivityStep[];
};

export function RunActivityTicker({ steps }: RunActivityTickerProps) {
  const visibleSteps = steps.slice(-2);
  const hasPreviousStep = visibleSteps.length > 1;
  const animationKey = steps.length;

  if (!visibleSteps.length) return null;

  return (
    <div className={styles.viewport} aria-live="polite" aria-atomic="true">
      <div
        className={hasPreviousStep ? styles.slidingTrack : styles.track}
        key={animationKey}
      >
        {visibleSteps.map((step, index) => {
          const isCurrent = index === visibleSteps.length - 1;
          return (
            <div className={styles.step} key={`${step.eventType}-${steps.length - index}`}>
              <span className={styles.text}>{step.text}</span>
              {isCurrent ? (
                <span className={styles.ellipsis} aria-hidden="true">
                  <span>.</span><span>.</span><span>.</span>
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
