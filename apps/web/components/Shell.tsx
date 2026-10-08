"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../lib/auth";
import type { Bundle } from "../lib/types";
import { Conversation, type ConversationContext } from "./Conversation";
import { ResearchHome } from "./ResearchHome";
import { RequestPage } from "./RequestPage";
import { Later } from "./Later";

type Route = { name: "research" } | { name: "request"; id: string } | { name: "later"; area: "Agents" | "Positions" | "Funds" };

function parse(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/");
  if (parts[0] === "research" && parts[1]) return { name: "request", id: parts[1] };
  if (parts[0] === "agents") return { name: "later", area: "Agents" };
  if (parts[0] === "positions") return { name: "later", area: "Positions" };
  if (parts[0] === "funds") return { name: "later", area: "Funds" };
  return { name: "research" };
}

export function Shell() {
  const auth = useAuth();
  const [route, setRoute] = useState<Route>({ name: "research" });
  const [context, setContext] = useState<ConversationContext | null>(null);
  const sheet = useRef<HTMLDialogElement>(null);
  const sheetTrigger = useRef<HTMLElement | null>(null);
  const returnTo = useRef<string | null>(null);

  useEffect(() => {
    const sync = () => setRoute(parse(window.location.hash));
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const go = useCallback((hash: string, from?: string) => {
    returnTo.current = from ?? null;
    window.location.hash = hash;
  }, []);
  const consumeReturn = useCallback(() => { const id = returnTo.current; returnTo.current = null; return id; }, []);
  const setBundleContext = useCallback((ctx: ConversationContext | null) => setContext(ctx), []);

  const openSheet = (event: React.MouseEvent<HTMLButtonElement>) => {
    sheetTrigger.current = event.currentTarget;
    sheet.current?.showModal();
  };
  const closeSheet = () => sheet.current?.close();
  // Keep Tab and Shift+Tab inside the open sheet. The dialog is modal, so wrapping is the expected behavior.
  const trapTab = (event: React.KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== "Tab") return;
    const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select, textarea, summary, [tabindex]:not([tabindex="-1"])'))
      .filter((el) => el.offsetParent !== null || el === document.activeElement);
    if (focusable.length === 0) return;
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  const current = route.name === "later" ? route.area : "Research";

  return (
    <div className="app">
      <aside className="sidebar">
        <p className="brand">Edge OS</p>
        <nav aria-label="Main" className="side-nav">
          <button type="button" aria-current={route.name === "research" || route.name === "request" ? "page" : undefined}
            onClick={() => go("#/research")}>Research</button>
          {(["Agents", "Positions", "Funds"] as const).map((area) => (
            <button key={area} type="button" aria-current={current === area ? "page" : undefined}
              onClick={() => go(`#/${area.toLowerCase()}`)}>{area}</button>
          ))}
        </nav>
        <div className="side-foot">
          <div className="notice">
            <strong>Build scope.</strong> This build runs Research only. Saving a rule grants no trading permission and
            moves no money.
          </div>
          <button className="btn btn-ghost" type="button" onClick={auth.logout}>Sign out</button>
        </div>
      </aside>
      <main id="main" className="main" tabIndex={-1}>
        {route.name === "research" && <ResearchHome go={go} consumeReturn={consumeReturn} />}
        {route.name === "request" && (
          <RequestPage key={route.id} id={route.id} go={go} setContext={setBundleContext}
            openConversation={openSheet} />
        )}
        {route.name === "later" && <Later area={route.area} />}
      </main>
      <div className="convo convo-desktop" aria-label="Conversation">
        <Conversation context={context} idPrefix="side" />
      </div>
      <dialog ref={sheet} className="sheet" aria-label="Conversation" onKeyDown={trapTab} onClose={() => sheetTrigger.current?.focus()}>
        <div className="convo">
          <div className="sheet-head">
            <h2>Conversation</h2>
            <button className="btn btn-secondary" type="button" onClick={closeSheet}>Close</button>
          </div>
          <Conversation context={context} idPrefix="sheet" />
        </div>
      </dialog>
    </div>
  );
}

export type { Bundle };
