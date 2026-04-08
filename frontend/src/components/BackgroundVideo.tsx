"use client";

import { useEffect, useState } from "react";

type BackgroundVideoProps = {
  src?: string;
};

const DEFAULT_VIDEO_SRC = "/Futuristic_AI_Workspace_Video_Generation.mp4";

export function BackgroundVideo({ src = DEFAULT_VIDEO_SRC }: BackgroundVideoProps) {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setPrefersReducedMotion(mediaQuery.matches);

    updatePreference();
    mediaQuery.addEventListener("change", updatePreference);

    return () => mediaQuery.removeEventListener("change", updatePreference);
  }, []);

  const showFallback = prefersReducedMotion || videoFailed;

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {showFallback ? (
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('/background_glass.png')" }}
        />
      ) : (
        <video
          autoPlay
          className="absolute inset-0 h-full w-full object-cover saturate-[1.08]"
          loop
          muted
          onError={() => setVideoFailed(true)}
          playsInline
          preload="metadata"
        >
          <source src={src} type="video/mp4" />
        </video>
      )}

      <div className="absolute inset-0 bg-[linear-gradient(160deg,rgba(6,9,19,0.8),rgba(9,12,24,0.66)_38%,rgba(8,10,20,0.78))]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_16%,rgba(125,116,255,0.2),transparent_44%),radial-gradient(circle_at_88%_20%,rgba(86,160,255,0.18),transparent_38%),radial-gradient(circle_at_72%_82%,rgba(255,118,204,0.1),transparent_30%)]" />
      <div className="absolute inset-0 opacity-[0.06] [background-image:radial-gradient(rgba(255,255,255,0.55)_0.5px,transparent_0.5px)] [background-size:2px_2px]" />
    </div>
  );
}
