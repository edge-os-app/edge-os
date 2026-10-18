import type { Metadata } from "next";
import { LandingPage } from "../components/landing/LandingPage";

export const metadata: Metadata = { title: "Edge OS · Test your trade idea, then trade it inside your limits" };

export default function Page() {
  return <LandingPage />;
}
