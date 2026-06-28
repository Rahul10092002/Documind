"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Loader2, Bot, User, CheckCircle2, AlertTriangle, ShieldCheck, HelpCircle } from "lucide-react";
import { apiSlice, useGetDocumentChatQuery } from "@/store/apiSlice";
import { useDispatch } from "react-redux";
import { useStreamChat, Message } from "@/hooks/useStreamChat";

interface ChatViewProps {
  documentId: string;
  filename: string;
  suggestedQuestions?: string[];
}

export default function ChatView({ documentId, filename, suggestedQuestions }: ChatViewProps) {
  const [inputValue, setInputValue] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const defaultSuggested = [
    "दस्तावेज़ का मुख्य उद्देश्य क्या है?",
    "मासिक किराया या भुगतान राशि क्या है?",
    "यह समझौता कब तक वैध है?",
    "क्या कोई सुरक्षा जमा (Security Deposit) का उल्लेख है?",
  ];

  const { data: chatHistory } = useGetDocumentChatQuery(documentId);
  const { 
    messages, 
    setMessages, 
    loading, 
    chatStep, 
    currentSuggestions, 
    setCurrentSuggestions, 
    handleSend 
  } = useStreamChat(documentId);

  const questionsToUse = currentSuggestions.length > 0 ? currentSuggestions : defaultSuggested;

  useEffect(() => {
    if (suggestedQuestions && suggestedQuestions.length > 0 && currentSuggestions.length === 0 && (!chatHistory || chatHistory.length === 0)) {
      setCurrentSuggestions(suggestedQuestions);
    }
  }, [suggestedQuestions, currentSuggestions.length, chatHistory]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (chatHistory && chatHistory.length > 0) {
      const formatted: Message[] = chatHistory.map((msg: any) => ({
        role: msg.role,
        content: msg.content,
        confidence: msg.confidence,
        sources: msg.sources,
      }));
      setMessages(formatted);
    } else {
      setMessages([
        {
          role: "assistant",
          content: `Hello! I have finished analyzing "${filename}". Ask me any questions about it in English, Hindi, or Hinglish.`,
        },
      ]);
    }
  }, [chatHistory, filename, setMessages]);

  const handleSuggestClick = (q: string) => {
    handleSend(q);
  };

  return (
    <div className="flex flex-col bg-zinc-900/40 border border-zinc-800/80 rounded-2xl h-full overflow-hidden shadow-xl animate-fade-in">
      {/* Messages Window */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin" role="log" aria-live="polite">
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
                  className={`rounded-2xl px-5 py-3 text-sm leading-relaxed ${
                    isUser
                      ? "bg-gradient-to-br from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/10 rounded-tr-sm font-medium"
                      : "bg-zinc-900/60 border border-zinc-800 text-zinc-200 shadow-sm rounded-tl-sm"
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
                          <span className="flex items-center gap-1.5 text-zinc-500 bg-zinc-950/40 border border-zinc-800 px-2 py-0.5 rounded-full">
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
                          View Sources ({msg.sources.length} sections referenced)
                        </summary>
                        <div className="mt-2.5 space-y-2 pl-1 max-h-48 overflow-y-auto pr-1">
                          {msg.sources.map((src: any, sIdx: number) => (
                            <div
                              key={sIdx}
                              className="text-[10px] text-zinc-350 bg-zinc-950/50 border border-zinc-800/80 p-3 rounded-xl hover:border-zinc-800 transition"
                            >
                              <div className="font-bold text-zinc-500 mb-1.5 flex items-center justify-between font-mono">
                                <span className="transition hover:text-zinc-400">
                                  {src.page !== undefined && src.page !== null
                                    ? `Page ${src.page}`
                                    : `Section ${src.chunk_index !== undefined ? src.chunk_index + 1 : sIdx + 1}`}
                                </span>
                                <span className="opacity-60">{src.filename}</span>
                              </div>
                              <p className="font-mono text-zinc-400 leading-normal select-text whitespace-pre-wrap">
                                {src.page_content || "Reference text"}
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
          <div className="flex gap-4 max-w-3xl mr-auto select-none">
            <div className="h-9 w-9 rounded-xl bg-indigo-950/20 border border-indigo-900/30 flex items-center justify-center text-zinc-500 shrink-0">
              <Bot size={15} />
            </div>
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl rounded-tl-sm p-4 text-xs text-zinc-400 flex flex-col gap-2.5 shadow-sm min-w-[280px]">
              <div className="flex items-center gap-2 font-semibold text-zinc-300 text-sm border-b border-zinc-800 pb-2">
                <Loader2 className="animate-spin text-indigo-500 shrink-0" size={14} />
                Formulating Answer
              </div>
              <div className="space-y-2">
                {[
                  "Refining search query...",
                  "Searching document sections...",
                  "Reading referenced sections...",
                  "Generating final response..."
                ].map((stepText, idx) => {
                  const isDone = chatStep > idx;
                  const isActive = chatStep === idx;
                  return (
                    <div
                      key={idx}
                      className={`flex items-center gap-2.5 transition-colors duration-300 ${
                        isDone ? "text-indigo-400" : isActive ? "text-white animate-pulse" : "text-zinc-500"
                      }`}
                    >
                      {isDone ? (
                        <span className="h-4 w-4 bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 flex items-center justify-center font-bold text-[8px] rounded-full shrink-0">✓</span>
                      ) : isActive ? (
                        <Loader2 className="animate-spin text-indigo-400 shrink-0" size={11} />
                      ) : (
                        <span className="h-4 w-4 bg-zinc-950 border border-zinc-800 flex items-center justify-center text-zinc-500 text-[8px] rounded-full shrink-0">{idx + 1}</span>
                      )}
                      <span>{stepText}</span>
                    </div>
                  );
                })}
              </div>
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
                  className="min-h-[44px] flex items-center text-xs bg-zinc-900/80 border border-zinc-800 hover:border-zinc-700 hover:bg-zinc-850 hover:text-white text-zinc-400 rounded-full px-4 transition duration-200 cursor-pointer hover:scale-[1.02] active:scale-[0.98]"
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
      <div className="pt-4 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] border-t border-zinc-800/60 bg-zinc-950/40 shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(inputValue);
            setInputValue("");
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
            className="p-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white disabled:bg-zinc-900 disabled:text-zinc-500 transition cursor-pointer hover:scale-105 active:scale-95 shrink-0 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
          >
            <Send size={14} className="stroke-[2.5]" />
          </button>
        </form>
      </div>
    </div>
  );
}
