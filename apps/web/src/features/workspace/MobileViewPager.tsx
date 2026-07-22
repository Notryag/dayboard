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
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

export type PrimaryView = "chat" | "schedule";

type MobileViewPagerProps = {
  activeView: PrimaryView;
  children: (isMobile: boolean) => React.ReactNode;
  className: string;
  onSelectView: (view: PrimaryView) => void;
  trackClassName: string;
};

const mobileQuery = "(max-width: 899px)";
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
  const x = useMotionValue(0);
  const dragControls = useDragControls();
  const reduceMotion = useReducedMotion();
  const [isMobile, setIsMobile] = useState(false);
  const [width, setWidth] = useState(0);

  const targetFor = useCallback(
    (view: PrimaryView) => (view === "schedule" ? -width : 0),
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
    const media = window.matchMedia(mobileQuery);
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(entry.contentRect.width);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!isMobile || width === 0) {
      x.set(0);
      return;
    }
    settle(activeView);
  }, [activeView, isMobile, settle, width, x]);

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const supportsDirectDrag = event.pointerType === "touch" || event.pointerType === "mouse";
    if (
      !isMobile
      || reduceMotion
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
      && info.offset.x < 0
      && (crossedDistance || (crossedVelocity && info.velocity.x < 0))
    ) {
      nextView = "schedule";
    } else if (
      activeView === "schedule"
      && info.offset.x > 0
      && (crossedDistance || (crossedVelocity && info.velocity.x > 0))
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
        drag={isMobile && !reduceMotion ? "x" : false}
        dragConstraints={{ left: -width, right: 0 }}
        dragControls={dragControls}
        dragElastic={0.06}
        dragListener={false}
        dragMomentum={false}
        onDragEnd={handleDragEnd}
        onPointerDownCapture={handlePointerDown}
        style={{ x }}
      >
        {children(isMobile)}
      </motion.div>
    </div>
  );
}
