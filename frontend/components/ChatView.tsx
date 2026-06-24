"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Loader2, Bot, User, CheckCircle2, AlertTriangle, ShieldCheck, HelpCircle } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
  confidence?: "high" | "medium" | "low";
  sources?: any[];
}

interface ChatViewProps {
  documentId: string;
  filename: string;
  suggestedQuestions?: string[];
}

export default function ChatView({ documentId, filename, suggestedQuestions }: ChatViewProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: `Hello! I have finished indexing "${filename}". Ask me any questions about it in English, Hindi, or Hinglish.`,
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const defaultSuggested = [
    "दस्तावेज़ का मुख्य उद्देश्य क्या है?",
    "मासिक किराया या भुगतान राशि क्या है?",
    "यह समझौता कब तक वैध है?",
    "क्या कोई सुरक्षा जमा (Security Deposit) का उल्लेख है?",
  ];

  const [currentSuggestions, setCurrentSuggestions] = useState<string[]>(() =>
    suggestedQuestions && suggestedQuestions.length > 0 ? suggestedQuestions : defaultSuggested
  );
  const [prevSuggestedQuestions, setPrevSuggestedQuestions] = useState<string[] | undefined>(suggestedQuestions);

  if (suggestedQuestions !== prevSuggestedQuestions) {
    setPrevSuggestedQuestions(suggestedQuestions);
    setCurrentSuggestions(suggestedQuestions && suggestedQuestions.length > 0 ? suggestedQuestions : defaultSuggested);
  }

  const questionsToUse = currentSuggestions && currentSuggestions.length > 0
    ? currentSuggestions
    : defaultSuggested;

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    let active = true;
    const fetchChatHistory = async () => {
      try {
        const res = await fetch(`http://localhost:8000/documents/${documentId}/chat`);
        if (!res.ok) throw new Error("Failed to load chat history");
        const data = await res.json();
        if (active) {
          if (data && data.length > 0) {
            const formatted: Message[] = data.map((msg: any) => ({
              role: msg.role,
              content: msg.content,
            }));
            setMessages(formatted);
          } else {
            setMessages([
              {
                role: "assistant",
                content: `Hello! I have finished indexing "${filename}". Ask me any questions about it in English, Hindi, or Hinglish.`,
              },
            ]);
          }
        }
      } catch (err) {
        console.error("Error fetching chat history:", err);
      }
    };

    fetchChatHistory();
    return () => {
      active = false;
    };
  }, [documentId, filename]);

  const handleSend = async (text: string) => {
    if (!text.trim() || loading) return;

    const userMessage: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setLoading(true);

    try {
      const res = await fetch(`http://localhost:8000/documents/${documentId}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: text }),
      });

      if (!res.ok) throw new Error("Failed to get answer");

      const data = await res.json();
      
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
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I encountered an error while trying to generate an answer. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSuggestClick = (q: string) => {
    handleSend(q);
  };

  return (
    <div className="flex flex-col bg-zinc-900/40 border border-zinc-800/80 rounded-2xl h-[calc(100vh-180px)] overflow-hidden shadow-xl animate-fade-in">
      {/* Messages Window */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin">
        {messages.map((msg, idx) => {
          const isUser = msg.role === "user";
          return (
            <div
              key={idx}
              className={`flex gap-4 max-w-3xl animate-fade-in ${
                isUser ? "ml-auto flex-row-reverse" : "mr-auto"
              }`}
            >
              {/* Avatar */}
              <div
                className={`h-9 w-9 rounded-xl flex items-center justify-center shrink-0 border shadow-sm select-none transition ${
                  isUser
                    ? "bg-zinc-800 border-zinc-700/85 text-indigo-400"
                    : "bg-indigo-950/20 border-indigo-900/30 text-indigo-400"
                }`}
              >
                {isUser ? <User size={15} /> : <Bot size={15} />}
              </div>

              {/* Message Bubble */}
              <div className="space-y-2.5 max-w-[calc(100%-52px)]">
                <div
                  className={`rounded-2xl px-4.5 py-3 text-sm leading-relaxed ${
                    isUser
                      ? "bg-gradient-to-br from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/10 rounded-tr-sm font-medium"
                      : "bg-zinc-900/60 border border-zinc-850 text-zinc-200 shadow-sm rounded-tl-sm"
                  }`}
                >
                  {msg.content}
                </div>

                {/* Sources & Confidence for Assistant Messages */}
                {!isUser && (msg.confidence || (msg.sources && msg.sources.length > 0)) && (
                  <div className="pl-3 border-l border-zinc-800/80 space-y-2.5">
                    {/* Confidence Meter */}
                    {msg.confidence && (
                      <div className="flex items-center gap-1.5 text-[9px] font-bold tracking-wide uppercase select-none">
                        {msg.confidence === "high" ? (
                          <span className="flex items-center gap-1.5 text-emerald-400 bg-emerald-500/5 border border-emerald-500/10 px-2 py-0.5 rounded-full">
                            <ShieldCheck size={11} />
                            High Confidence
                          </span>
                        ) : msg.confidence === "medium" ? (
                          <span className="flex items-center gap-1.5 text-amber-400 bg-amber-500/5 border border-amber-500/10 px-2 py-0.5 rounded-full">
                            <CheckCircle2 size={11} />
                            Medium Confidence
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5 text-zinc-500 bg-zinc-950/40 border border-zinc-850 px-2 py-0.5 rounded-full">
                            <AlertTriangle size={11} />
                            Low Confidence (Limited Context)
                          </span>
                        )}
                      </div>
                    )}

                    {/* Collapsible Source List */}
                    {msg.sources && msg.sources.length > 0 && (
                      <details className="group">
                        <summary className="text-[9px] text-zinc-500 hover:text-zinc-400 cursor-pointer select-none font-bold uppercase tracking-wider outline-none list-none flex items-center gap-1">
                          <span className="transition-transform group-open:rotate-90">▶</span>
                          View Sources ({msg.sources.length} chunks used)
                        </summary>
                        <div className="mt-2.5 space-y-2 pl-1 max-h-48 overflow-y-auto pr-1">
                          {msg.sources.map((src: any, sIdx: number) => (
                            <div
                              key={sIdx}
                              className="text-[10px] text-zinc-350 bg-zinc-950/50 border border-zinc-850/80 p-3 rounded-xl hover:border-zinc-800 transition"
                            >
                              <div className="font-bold text-zinc-500 mb-1.5 flex items-center justify-between font-mono">
                                <span className="transition hover:text-zinc-400">
                                  {src.page !== undefined && src.page !== null
                                    ? `Page ${src.page}`
                                    : `Chunk ${src.chunk_index !== undefined ? src.chunk_index + 1 : sIdx + 1}`}
                                </span>
                                <span className="opacity-60">{src.filename}</span>
                              </div>
                              <p className="font-mono text-zinc-400 leading-normal select-text whitespace-pre-wrap">
                                {src.page_content || "Retrieved context slice"}
                              </p>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex gap-4 max-w-3xl mr-auto">
            <div className="h-9 w-9 rounded-xl bg-indigo-950/20 border border-indigo-900/30 flex items-center justify-center text-zinc-500">
              <Bot size={15} />
            </div>
            <div className="bg-zinc-900/60 border border-zinc-850 rounded-2xl rounded-tl-sm px-4.5 py-3 text-sm text-zinc-400 flex items-center gap-2 shadow-sm animate-pulse">
              <Loader2 className="animate-spin text-indigo-500" size={14} />
              Thinking...
            </div>
          </div>
        )}

        {/* Suggested Questions */}
        {questionsToUse && questionsToUse.length > 0 && !loading && (
          <div className="pl-[52px] space-y-3 select-none animate-fade-in max-w-3xl">
            <div className="flex items-center gap-1.5 text-[10px] text-zinc-500 font-bold tracking-wider uppercase">
              <HelpCircle size={12} className="text-zinc-500" />
              Suggested Questions
            </div>
            <div className="flex flex-wrap gap-2.5">
              {questionsToUse.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSuggestClick(q)}
                  className="text-xs bg-zinc-900/80 border border-zinc-800 hover:border-zinc-700 hover:bg-zinc-850 hover:text-white text-zinc-400 rounded-full px-4 py-2 transition duration-200 cursor-pointer hover:scale-[1.02] active:scale-[0.98]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={scrollRef} />
      </div>

      {/* Input Tray */}
      <div className="p-4 border-t border-zinc-850/60 bg-zinc-950/40 shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(inputValue);
          }}
          className="flex items-center gap-3 bg-zinc-900/60 border border-zinc-800/80 rounded-xl px-4 py-2 focus-within:border-indigo-500/70 focus-within:ring-1 focus-within:ring-indigo-500/10 transition-all shadow-inner"
        >
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            disabled={loading}
            placeholder="Ask a question about this document..."
            className="flex-1 bg-transparent text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none py-1.5 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || loading}
            className="p-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white disabled:bg-zinc-850 disabled:text-zinc-650 transition cursor-pointer hover:scale-105 active:scale-95 shrink-0"
          >
            <Send size={14} className="stroke-[2.5]" />
          </button>
        </form>
      </div>
    </div>
  );
}
