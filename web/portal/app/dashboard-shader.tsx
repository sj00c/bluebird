"use client";

import { useEffect, useRef } from "react";
import {
  createGpuUniformsMap,
  rootPassthrough,
  shaderRendererGPU,
  type GpuShaderDefinition,
} from "shaders/core";
import FlowingGradient from "shaders/core/FlowingGradient";
import styles from "./dashboard-atmosphere.module.css";

const PIXEL_BUDGET = 600_000;
const RESOLUTION_SCALE = 0.5;
// The uniform bridge consumes the core renderer's non-generic definition type.
const gradientDefinition: GpuShaderDefinition = FlowingGradient;

export default function DashboardShader({
  onReady,
  onUnavailable,
}: {
  onReady: () => void;
  onUnavailable: (reason: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // The core renderer has no telemetry collector. Unlike the React <Shader>
    // wrapper, it exposes real resolution and frame-rate controls.
    const renderer = shaderRendererGPU();
    let disposed = false;
    let renderDpr = Math.max(1, window.devicePixelRatio || 1);
    let initialized = false;
    const resize = () => {
      if (!initialized || disposed) return;
      const width = Math.max(1, window.innerWidth);
      const height = Math.max(1, window.innerHeight);
      // The renderer captures its backing ratio when resolution scale is set.
      // Leave one logical pixel of rounding headroom on each axis.
      const ratio = renderDpr * RESOLUTION_SCALE;
      const scale = Math.min(
        1,
        Math.sqrt(PIXEL_BUDGET / (width * height)) / ratio,
      );
      renderer.resize(
        Math.max(1, Math.floor(width * scale) - 1),
        Math.max(1, Math.floor(height * scale) - 1),
      );
    };
    const unavailable = (reason: string) => {
      if (!disposed) onUnavailable(reason);
    };

    renderer.setOnReady(() => {
      if (!disposed) onReady();
    });
    renderer.setOnUnavailable(unavailable);
    renderer.setFrameRateCap(24);

    const initialize = async () => {
      // Start at one CSS pixel: initialization must not briefly allocate a
      // full-viewport retina buffer before we can apply the resolution cap.
      canvas.style.width = "1px";
      canvas.style.height = "1px";
      await renderer.initialize({
        canvas,
        colorSpace: "srgb",
        observeElement: false,
      });
      if (disposed) {
        renderer.cleanup();
        return;
      }
      if (renderer.getFailureReason()) return;
      initialized = true;
      renderDpr = Math.max(1, window.devicePixelRatio || 1);
      renderer.setResolutionScale(RESOLUTION_SCALE);
      resize();
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      renderer.registerNode(
        "dashboard-root",
        rootPassthrough.fragment,
        null,
        null,
        {},
        rootPassthrough,
      );
      renderer.registerNode(
        "dashboard-light",
        FlowingGradient.fragment,
        "dashboard-root",
        { blendMode: "normal", renderOrder: 0, opacity: 1 },
        createGpuUniformsMap(
          gradientDefinition,
          {
            colorA: "#f3f3f3",
            colorB: "#c9c9c9",
            colorC: "#fafafa",
            colorD: "#e7e7e7",
            colorSpace: "linear",
            speed: 0.07,
            distortion: 0.2,
            seed: 4,
          },
          "dashboard-light",
        ),
        FlowingGradient,
      );
    };
    void initialize().catch(() => unavailable("init-failed"));
    window.addEventListener("resize", resize, { passive: true });

    return () => {
      disposed = true;
      window.removeEventListener("resize", resize);
      renderer.setOnReady(null);
      renderer.setOnUnavailable(null);
      renderer.cleanup();
    };
  }, [onReady, onUnavailable]);

  return (
    <canvas ref={canvasRef} width={1} height={1} className={styles.shader} />
  );
}
