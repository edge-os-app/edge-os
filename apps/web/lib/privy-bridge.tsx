"use client";

import { PrivyProvider, usePrivy } from "@privy-io/react-auth";
import type { ReactNode } from "react";
import { PRIVY_CONFIG } from "./privy-config";

interface Source {
  ready: boolean;
  authenticated: boolean;
  getAccessToken(): Promise<string | null>;
  login(): void;
  logout(): void;
}

function Bridge({ render }: { render: (source: Source) => ReactNode }) {
  const { ready, authenticated, getAccessToken, login, logout } = usePrivy();
  return <>{render({ ready, authenticated, getAccessToken, login: () => login(), logout: () => void logout() })}</>;
}

export default function PrivyBridge({ appId, render }: { appId: string; render: (source: Source) => ReactNode }) {
  return (
    <PrivyProvider appId={appId} config={PRIVY_CONFIG}>
      <Bridge render={render} />
    </PrivyProvider>
  );
}
