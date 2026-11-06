import { BuiltOnSection } from "./BuiltOnSection";
import { ClosingSection } from "./ClosingSection";
import { HeroSection } from "./HeroSection";
import { HowItWorksSection } from "./HowItWorksSection";
import { LandingFooter } from "./LandingFooter";
import { LandingHeader } from "./LandingHeader";
import { LandingMotion } from "./LandingMotion";
import { ProblemSection } from "./ProblemSection";
import { QuestionsSection } from "./QuestionsSection";
import "./landing.css";

/** The marketing page. It sits outside App and AuthRoot, so it never starts sign-in or wallet code. */
export function LandingPage() {
  return (
    <div className="edge-os-landing">
      <a className="lp-skip" href="#main">Skip to content</a>
      <LandingHeader />
      <main id="main">
        <HeroSection />
        <ProblemSection />
        <HowItWorksSection />
        <QuestionsSection />
        <BuiltOnSection />
        <ClosingSection />
      </main>
      <LandingFooter />
      <LandingMotion />
    </div>
  );
}
