import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./organic.css";
import "./app.css";

export const metadata: Metadata = {
  title: "Edge OS",
  description: "Research on Monad. Your words, saved.",
  icons: {
    icon: [{ url: "/landing/icon.svg", type: "image/svg+xml" }, { url: "/landing/edge-os-icon.png", type: "image/png" }],
    apple: "/landing/edge-os-icon.png",
  },
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
