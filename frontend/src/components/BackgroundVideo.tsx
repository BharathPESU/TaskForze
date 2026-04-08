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
          className="absolute inset-0 h-full w-full object-cover"
          loop
          muted
          onError={() => setVideoFailed(true)}
          playsInline
          preload="metadata"
        >
          <source src={src} type="video/mp4" />
        </video>
      )}

      <div className="absolute inset-0 bg-black/60" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_25%_15%,rgba(123,97,255,0.22),transparent_45%),radial-gradient(circle_at_75%_80%,rgba(8,47,73,0.28),transparent_55%)]" />
    </div>
  );
}
