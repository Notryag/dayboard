"use client";

import {
  animate,
  motion,
  useDragControls,
  useMotionValue,
  useReducedMotion,
  type PanInfo,
} from "motion/react";
import {
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

export type PrimaryView = "chat" | "schedule";

type MobileViewPagerProps = {
  activeView: PrimaryView;
  children: ReactNode;
  className: string;
  onSelectView: (view: PrimaryView) => void;
  trackClassName: string;
};

const edgeInset = 24;
const distanceThresholdRatio = 0.2;
const velocityThreshold = 450;
const ignoredTargets = [
  "button",
  "a",
  "input",
  "textarea",
  "select",
  "[role='dialog']",
  "[data-swipe-navigation-ignore]",
].join(",");

const spring = {
  type: "spring" as const,
  stiffness: 420,
  damping: 42,
  mass: 0.85,
};

export function MobileViewPager({
  activeView,
  children,
  className,
  onSelectView,
  trackClassName,
}: MobileViewPagerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeViewRef = useRef(activeView);
  const x = useMotionValue(0);
  const dragControls = useDragControls();
  const reduceMotion = useReducedMotion();
  const [width, setWidth] = useState(0);

  useEffect(() => {
    activeViewRef.current = activeView;
  }, [activeView]);

  const targetFor = useCallback(
    (view: PrimaryView) => (view === "chat" ? -width : 0),
    [width],
  );

  const settle = useCallback(
    (view: PrimaryView) => {
      const target = targetFor(view);
      if (reduceMotion) {
        x.set(target);
        return;
      }
      animate(x, target, spring);
    },
    [reduceMotion, targetFor, x],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(([entry]) => {
      const nextWidth = entry.contentRect.width;
      x.set(activeViewRef.current === "chat" ? -nextWidth : 0);
      setWidth(nextWidth);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [x]);

  useEffect(() => {
    if (width === 0) {
      x.set(0);
      return;
    }
    settle(activeView);
  }, [activeView, settle, width, x]);

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const supportsDirectDrag = event.pointerType === "touch" || event.pointerType === "mouse";
    if (
      reduceMotion
      || width === 0
      || !supportsDirectDrag
      || event.clientX <= edgeInset
      || event.clientX >= width - edgeInset
      || (event.target as HTMLElement).closest(ignoredTargets)
    ) {
      return;
    }
    dragControls.start(event);
  }

  function handleDragEnd(_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) {
    const crossedDistance = Math.abs(info.offset.x) >= width * distanceThresholdRatio;
    const crossedVelocity = Math.abs(info.velocity.x) >= velocityThreshold;
    let nextView = activeView;

    if (
      activeView === "chat"
      && info.offset.x > 0
      && (crossedDistance || (crossedVelocity && info.velocity.x > 0))
    ) {
      nextView = "schedule";
    } else if (
      activeView === "schedule"
      && info.offset.x < 0
      && (crossedDistance || (crossedVelocity && info.velocity.x < 0))
    ) {
      nextView = "chat";
    }

    if (nextView !== activeView) onSelectView(nextView);
    else settle(activeView);
  }

  return (
    <div
      className={className}
      data-active-view={activeView}
      ref={containerRef}
    >
      <motion.div
        className={trackClassName}
        data-view-track
        drag={!reduceMotion ? "x" : false}
        dragConstraints={{ left: -width, right: 0 }}
        dragControls={dragControls}
        dragElastic={0.06}
        dragListener={false}
        dragMomentum={false}
        onDragEnd={handleDragEnd}
        onPointerDownCapture={handlePointerDown}
        style={width > 0 ? { x } : undefined}
      >
        {children}
      </motion.div>
    </div>
  );
}
