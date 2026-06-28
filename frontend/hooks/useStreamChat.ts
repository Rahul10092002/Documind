import { useState, useCallback } from "react";
import { useDispatch } from "react-redux";
import { apiSlice } from "@/store/apiSlice";

export interface Message {
  role: "user" | "assistant";
  content: string;
  confidence?: "high" | "medium" | "low";
  sources?: any[];
}

export function useStreamChat(documentId: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [chatStep, setChatStep] = useState(0);
  const [currentSuggestions, setCurrentSuggestions] = useState<string[]>([]);
  const dispatch = useDispatch();

  const handleSend = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    setCurrentSuggestions([]);
    const userMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);
    setChatStep(0);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/documents/${documentId}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: text }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error("Failed to formulate response");
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("Could not initialize stream reader");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;

          if (line.startsWith("step:")) {
            const stepName = line.slice(5);
            if (stepName.includes("Refining")) setChatStep(0);
            else if (stepName.includes("Searching")) setChatStep(1);
            else if (stepName.includes("Reading")) setChatStep(2);
            else if (stepName.includes("Generating")) setChatStep(3);
          } else if (line.startsWith("answer:")) {
            const data = JSON.parse(line.slice(7));
            const assistantMessage: Message = {
              role: "assistant",
              content: data.answer,
              confidence: data.confidence,
              sources: data.sources || [],
            };
            setMessages((prev) => [...prev, assistantMessage]);
            if (data.suggested_questions && data.suggested_questions.length > 0) {
              setCurrentSuggestions(data.suggested_questions);
            }
            dispatch(apiSlice.util.invalidateTags([{ type: "Chat", id: documentId }]));
          } else if (line.startsWith("error:")) {
            throw new Error(line.slice(6));
          }
        }
      }
    } catch (err: any) {
      console.error(err);
      const isTimeout = err.name === "AbortError";
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: isTimeout 
            ? "Sorry, the connection timed out. The server took too long to formulate a response. Please check your network or try again."
            : "Sorry, I encountered an error. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [documentId, loading, dispatch]);

  return { 
    messages, 
    setMessages, 
    loading, 
    chatStep, 
    currentSuggestions, 
    setCurrentSuggestions, 
    handleSend 
  };
}
