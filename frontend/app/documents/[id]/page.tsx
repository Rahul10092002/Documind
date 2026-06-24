"use client";

import { useEffect, useState, use } from "react";
import { useParams, useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import ExtractionView from "@/components/ExtractionView";
import RiskAnalysisView from "@/components/RiskAnalysisView";
import ChatView from "@/components/ChatView";
import { Loader2, AlertCircle, FileText, Calendar, CheckCircle } from "lucide-react";

interface DocumentData {
  id: string;
  filename: string;
  upload_date: string;
  language: string | null;
  status: "pending" | "processing" | "completed" | "failed";
  raw_text: string | null;
}

interface AnalysisData {
  document_id: string;
  extracted_entities: any;
  risk_flags: any[];
  risk_obligation_summary: string | null;
}

export default function DocumentPage({ defaultTab = "extraction" }: { defaultTab?: "extraction" | "risk" | "chat" }) {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [activeTab, setActiveTab] = useState<"extraction" | "risk" | "chat">(defaultTab);
  const [doc, setDoc] = useState<DocumentData | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      // 1. Fetch document metadata
      const docRes = await fetch(`http://localhost:8000/documents/${id}`);
      if (!docRes.ok) {
        if (docRes.status === 404) throw new Error("Document not found");
        throw new Error("Failed to load document metadata");
      }
      const docData: DocumentData = await docRes.json();
      setDoc(docData);

      // 2. Fetch analysis results if document is completed
      if (docData.status === "completed") {
        const analysisRes = await fetch(`http://localhost:8000/documents/${id}/analysis`);
        if (analysisRes.ok) {
          const analysisData: AnalysisData = await analysisRes.json();
          console.log(analysisData);
          setAnalysis(analysisData);
        }
      }
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "An error occurred while loading data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) {
      fetchData();
    }
  }, [id]);

  // Poll for document completion if the state is processing
  useEffect(() => {
    if (!doc || doc.status === "completed" || doc.status === "failed") return;

    const interval = setInterval(async () => {
      try {
        const docRes = await fetch(`http://localhost:8000/documents/${id}`);
        if (!docRes.ok) return;
        const docData: DocumentData = await docRes.json();
        setDoc(docData);

        if (docData.status === "completed") {
          clearInterval(interval);
          const analysisRes = await fetch(`http://localhost:8000/documents/${id}/analysis`);
          if (analysisRes.ok) {
            const analysisData: AnalysisData = await analysisRes.json();
            setAnalysis(analysisData);
          }
        } else if (docData.status === "failed") {
          clearInterval(interval);
        }
      } catch (err) {
        console.error("Error polling document status:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [doc, id]);

  if (loading) {
    return (
      <div className="flex h-screen w-screen bg-zinc-955 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} />
        <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-zinc-950">
          <Loader2 className="animate-spin text-indigo-500" size={32} />
          <p className="text-sm text-zinc-400">Loading document...</p>
        </div>
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="flex h-screen w-screen bg-zinc-955 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} />
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6 bg-zinc-950">
          <AlertCircle className="text-red-500" size={48} />
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-white">Load Error</h3>
            <p className="text-sm text-zinc-455 max-w-sm">
              {error || "We couldn't retrieve the details for this document."}
            </p>
          </div>
          <button
            onClick={() => router.push("/")}
            className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition cursor-pointer select-none"
          >
            Go Home
          </button>
        </div>
      </div>
    );
  }

  // Processing state
  if (doc.status === "processing" || doc.status === "pending") {
    return (
      <div className="flex h-screen w-screen bg-zinc-955 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} />
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center px-6 bg-zinc-950">
          <Loader2 className="animate-spin text-indigo-500" size={48} />
          <div className="space-y-2">
            <h3 className="text-xl font-bold text-white animate-pulse">Analyzing Document</h3>
            <p className="text-sm text-zinc-400 max-w-xs mx-auto">
              We are parsing the PDF, detecting language, extracting entities, and running our multi-agent risk assessment pipeline.
            </p>
          </div>
          <div className="max-w-xs bg-zinc-900/60 border border-zinc-800 p-4 rounded-xl text-xs text-zinc-500 text-left space-y-1">
            <span className="font-semibold text-zinc-400 select-none">Did you know?</span>
            <p>DocuMind supports Hindi and Hinglish. It will automatically translate risks and drafts to match the source language!</p>
          </div>
        </div>
      </div>
    );
  }

  // Failed state
  if (doc.status === "failed") {
    return (
      <div className="flex h-screen w-screen bg-zinc-955 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} />
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6 bg-zinc-950">
          <AlertCircle className="text-red-500" size={48} />
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-white">Analysis Failed</h3>
            <p className="text-sm text-zinc-450 max-w-xs mx-auto">
              The ingestion engine failed to process the PDF. Ensure the file is not corrupted or password-protected.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchData}
              className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition cursor-pointer select-none"
            >
              Retry
            </button>
            <button
              onClick={() => router.push("/")}
              className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg px-4 py-2 text-sm font-medium transition cursor-pointer select-none"
            >
              Go Home
            </button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="flex h-screen w-screen bg-zinc-950 overflow-hidden text-zinc-100 font-sans animate-fade-in">
      {/* Sidebar */}
      <Sidebar activeId={id} />

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col h-full overflow-hidden p-6 md:p-8 bg-zinc-950">
        {/* Workspace Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-900 pb-5 mb-6 shrink-0">
          <div className="space-y-1.5 min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <FileText className="text-indigo-400 shrink-0" size={20} />
              <h2 className="text-xl font-bold text-white truncate pr-4">{doc.filename}</h2>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs select-none">
              <span className="flex items-center gap-1.5 bg-zinc-900 border border-zinc-800 text-zinc-400 px-2.5 py-0.5 rounded-full text-[11px] font-medium">
                <Calendar size={12} className="text-zinc-500" />
                Uploaded: {new Date(doc.upload_date).toLocaleDateString()}
              </span>
              <span className="flex items-center gap-1.5 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 px-2.5 py-0.5 rounded-full text-[11px] font-semibold font-mono">
                <CheckCircle size={12} className="text-indigo-400" />
                LANG: {doc.language ? doc.language.toUpperCase() : "DETECTED"}
              </span>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="flex bg-zinc-900/80 border border-zinc-850 p-1 rounded-xl shrink-0 select-none shadow-inner">
            <button
              onClick={() => setActiveTab("extraction")}
              className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer select-none ${
                activeTab === "extraction"
                  ? "bg-zinc-800 text-white shadow-sm border border-zinc-700/30"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Extraction
            </button>
            <button
              onClick={() => setActiveTab("risk")}
              className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer select-none ${
                activeTab === "risk"
                  ? "bg-zinc-800 text-white shadow-sm border border-zinc-700/30"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Risk & Drafts
            </button>
            <button
              onClick={() => setActiveTab("chat")}
              className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer select-none ${
                activeTab === "chat"
                  ? "bg-zinc-800 text-white shadow-sm border border-zinc-700/30"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Document Chat (RAG)
            </button>
          </div>
        </div>

        {/* Tab Panels */}
        <div className="flex-1 overflow-hidden">
          {activeTab === "extraction" && (
            <ExtractionView
              filename={doc.filename}
              language={doc.language}
              extractedEntities={analysis?.extracted_entities || {}}
              rawText={doc.raw_text}
            />
          )}

          {activeTab === "risk" && (
            <RiskAnalysisView
              documentId={id}
              riskFlags={analysis?.risk_flags || []}
              riskObligationSummary={analysis?.risk_obligation_summary || ""}
              onReanalyzeSuccess={(updated) => setAnalysis(updated)}
              rawText={doc.raw_text}
            />
          )}

          {activeTab === "chat" && (
            <ChatView
              documentId={id}
              filename={doc.filename}
              suggestedQuestions={analysis?.extracted_entities?.suggested_questions}
            />
          )}
        </div>
      </div>
    </div>
  );
}
