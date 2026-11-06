"use client";

import { useEffect } from "react";

const SLIP_INTRO = { duration: 900, easing: "cubic-bezier(.2,.75,.25,1)", fill: "backwards" as const, delay: 150 };
const STAMP_INTRO = { duration: 380, easing: "cubic-bezier(.3,0,.3,1)", fill: "backwards" as const, delay: 1050 };
const REVEAL = { duration: 650, easing: "ease-out" };
const TILT = "rotate(-1.6deg)";

/**
 * One load moment (the slip drops, the stamp lands) and a scroll reveal for later blocks. The page renders fully
 * without this component. It adds motion only after mount and never when the person prefers reduced motion.
 */
export function LandingMotion() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const root = document.querySelector<HTMLElement>(".edge-os-landing");
    if (!root) return;
    const timers: number[] = [];

    const slip = root.querySelector<HTMLElement>("[data-slip]");
    const stamp = root.querySelector<HTMLElement>("[data-stamp]");
    if (slip && typeof slip.animate === "function") {
      slip.animate([
        { transform: `translateY(-56px) rotate(-7deg)`, opacity: 0, boxShadow: "0 40px 70px rgba(46,43,37,.10)" },
        { transform: `translateY(4px) ${TILT}`, opacity: 1, offset: 0.8 },
        { transform: TILT, opacity: 1 },
      ], SLIP_INTRO);
      if (stamp) {
        stamp.animate([
          { transform: "scale(1.9)", opacity: 0 },
          { transform: "scale(0.94)", opacity: 1, offset: 0.7 },
          { transform: "scale(1)", opacity: 1 },
        ], STAMP_INTRO);
        timers.push(window.setTimeout(() => slip.animate([{ transform: `${TILT} translateY(1.5px)` }, { transform: TILT }], { duration: 160 }), 1320));
      }
    }

    let observer: IntersectionObserver | null = null;
    const hidden: HTMLElement[] = [];
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const target = entry.target as HTMLElement;
          io.unobserve(target);
          target.animate([{ opacity: 0, transform: "translateY(16px)" }, { opacity: 1, transform: "none" }], REVEAL);
          target.style.opacity = "";
        }
      }, { rootMargin: "0px 0px -8% 0px" });
      for (const block of Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]"))) {
        if (block.getBoundingClientRect().top < window.innerHeight) continue;
        block.style.opacity = "0";
        hidden.push(block);
        io.observe(block);
      }
      observer = io;
    }

    return () => {
      observer?.disconnect();
      for (const block of hidden) block.style.opacity = "";
      for (const timer of timers) window.clearTimeout(timer);
    };
  }, []);

  return null;
}
