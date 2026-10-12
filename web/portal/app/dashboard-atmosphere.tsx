"use client";

import dynamic from "next/dynamic";
import { Component, useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import styles from "./dashboard-atmosphere.module.css";

const DashboardShader = dynamic(() => import("./dashboard-shader"), {
  ssr: false,
});

class ShaderBoundary extends Component<
  { children: ReactNode; onUnavailable: (reason: string) => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onUnavailable("component-error");
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function DashboardAtmosphere() {
  const [eligible, setEligible] = useState(false);
  const [visible, setVisible] = useState(false);
  const [paused, setPaused] = useState(false);
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const onReady = useCallback(() => setReady(true), []);
  const onUnavailable = useCallback((reason: string) => {
    setFailure(reason);
    setReady(false);
  }, []);

  useEffect(() => {
    const media = window.matchMedia(
      "(min-width: 1024px) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)",
    );
    const updateEligibility = () => {
      setEligible(media.matches && "gpu" in navigator);
      setReady(false);
    };
    const updateVisibility = () => {
      setVisible(!document.hidden);
      if (document.hidden) setReady(false);
    };
    updateEligibility();
    updateVisibility();
    media.addEventListener("change", updateEligibility);
    document.addEventListener("visibilitychange", updateVisibility);
    return () => {
      media.removeEventListener("change", updateEligibility);
      document.removeEventListener("visibilitychange", updateVisibility);
    };
  }, []);

  const enabled = eligible && visible && !paused && !failure;

  return (
    <>
      <div
        className={`dashboard-atmosphere ${styles.field}`}
        aria-hidden="true"
        data-renderer={enabled ? (ready ? "webgpu" : "loading") : "static"}
        data-renderer-error={failure ?? undefined}
      >
        {enabled && (
          <ShaderBoundary onUnavailable={onUnavailable}>
            <DashboardShader onReady={onReady} onUnavailable={onUnavailable} />
          </ShaderBoundary>
        )}
      </div>
      {eligible && !failure && (
        <button
          type="button"
          className={styles.motion}
          aria-label="배경 움직임"
          aria-pressed={!paused}
          title={paused ? "배경 움직임 켜기" : "배경 움직임 끄기"}
          onClick={() => {
            setReady(false);
            setPaused((value) => !value);
          }}
        >
          <svg
            viewBox="0 0 20 20"
            width="18"
            height="18"
            fill="currentColor"
            aria-hidden="true"
          >
            {paused ? (
              <path d="M6 3.5 16 10 6 16.5Z" />
            ) : (
              <>
                <rect x="5" y="4" width="3" height="12" />
                <rect x="12" y="4" width="3" height="12" />
              </>
            )}
          </svg>
        </button>
      )}
    </>
  );
}
