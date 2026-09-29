import { useContext, useEffect } from "react";
import { useLocation } from "react-router-dom";
import {
  ConversationContext,
  ConversationProvider,
  useConversation,
} from "./ConversationProvider";
import { ConversationContent } from "./ConversationContent";
import "./conversation.css";

function PageContent({ search, showCompatibilityHistory = false }: { search?: string; showCompatibilityHistory?: boolean }) {
  const { controller } = useConversation();
  const sessionId = new URLSearchParams(search ?? window.location.search).get("session");
  useEffect(() => {
    if (sessionId) void controller.select(sessionId);
  }, [controller, sessionId]);
  return (
    <main className="conv-page" data-testid="conversation-page">
      <ConversationContent showCompatibilityHistory={showCompatibilityHistory} requestedSessionId={sessionId} />
    </main>
  );
}
export function ConversationPage({ search }: { search?: string } = {}) {
  const controller = useContext(ConversationContext);
  return controller ? (
    <PageContent search={search} />
  ) : (
    <ConversationProvider>
      <PageContent search={search} showCompatibilityHistory />
    </ConversationProvider>
  );
}

export function ConversationRoutePage() {
  const location = useLocation();
  return <ConversationPage search={location.search} />;
}
