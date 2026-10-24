import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Send, X } from "lucide-react";
import * as api from "@/api/client";
import { ApiError } from "@/api/client";
import type { Citation, Collection } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  timings?: { retrieval_ms: number; llm_ms: number; total_ms: number };
}

export function PlaygroundPage() {
  const [collections, setCollections] = useState<Collection[] | null>(null);
  const [collectionId, setCollectionId] = useState<string>("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);
  const conversationId = useMemo(() => crypto.randomUUID(), [collectionId]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .listCollections()
      .then((data) => {
        setCollections(data);
        if (data.length > 0) setCollectionId(data[0].id);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load collections."));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSubmit() {
    const query = input.trim();
    if (!query || !collectionId || isStreaming) return;

    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: query, citations: [] }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "", citations: [] }]);
    setIsStreaming(true);

    let buffer = "";
    try {
      await api.streamQuery(collectionId, { query, conversation_id: conversationId }, {
        onToken: (text) => {
          buffer += text;
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], content: buffer };
            return next;
          });
        },
        onCitations: (citations) => {
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], citations: citations as Citation[] };
            return next;
          });
        },
        onDone: (payload) => {
          setMessages((prev) => {
            const next = [...prev];
            next[next.length - 1] = {
              ...next[next.length - 1],
              timings: payload.timings as ChatMessage["timings"],
            };
            return next;
          });
          setIsStreaming(false);
        },
        onError: (message) => {
          setError(message);
          setIsStreaming(false);
        },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Streaming failed.");
      setIsStreaming(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Playground</h1>
          <p className="text-sm text-muted-foreground">Ask questions against a collection and watch citations map to source pages.</p>
        </div>
        <select
          className="h-10 rounded-md border border-input bg-background px-3 text-sm"
          value={collectionId}
          onChange={(e) => setCollectionId(e.target.value)}
        >
          {collections === null && <option>Loading...</option>}
          {collections?.length === 0 && <option>No collections yet</option>}
          {collections?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-1 gap-4 overflow-hidden">
        <div className="flex flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4 scrollbar-thin">
            {messages.length === 0 && (
              <p className="py-16 text-center text-sm text-muted-foreground">
                Ask a question below to see a streamed, cited answer.
              </p>
            )}
            {messages.map((m, i) => (
              <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg px-4 py-2 text-sm",
                    m.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
                  )}
                >
                  <p className="whitespace-pre-wrap">
                    {m.content || (m.role === "assistant" && isStreaming && i === messages.length - 1 ? "..." : "")}
                  </p>
                  {m.citations.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {m.citations.map((c) => (
                        <button
                          key={c.marker}
                          onClick={() => setActiveCitation(c)}
                          className="rounded-full bg-background/80 px-2 py-0.5 text-xs font-medium text-foreground ring-1 ring-border hover:ring-primary"
                        >
                          [{c.marker}] {c.filename}
                          {c.page_number ? ` p.${c.page_number}` : ""}
                        </button>
                      ))}
                    </div>
                  )}
                  {m.timings && (
                    <p className="mt-1 text-[10px] text-muted-foreground/70">
                      retrieval {m.timings.retrieval_ms}ms · llm {m.timings.llm_ms}ms · total {m.timings.total_ms}ms
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-2 border-t border-border p-3">
            <Textarea
              placeholder="Ask a question about this collection..."
              className="min-h-[44px] flex-1 resize-none"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              disabled={isStreaming || !collectionId}
            />
            <Button onClick={handleSubmit} disabled={isStreaming || !input.trim() || !collectionId}>
              {isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        {activeCitation && (
          <Card className="w-80 shrink-0 overflow-y-auto">
            <CardContent className="p-4">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold">Source [{activeCitation.marker}]</h3>
                <button onClick={() => setActiveCitation(null)} aria-label="Close">
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              </div>
              <p className="mb-1 text-xs font-medium">{activeCitation.filename}</p>
              {activeCitation.page_number && <p className="mb-3 text-xs text-muted-foreground">Page {activeCitation.page_number}</p>}
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">{activeCitation.snippet}</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
