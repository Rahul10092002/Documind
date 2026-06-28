"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import ExtractionView from "@/components/ExtractionView";
import RiskAnalysisView from "@/components/RiskAnalysisView";
import ChatView from "@/components/ChatView";
import ErrorBoundary from "@/components/ErrorBoundary";
import { Loader2, AlertCircle, FileText, Calendar, CheckCircle, Download, Menu } from "lucide-react";
import { toast } from "sonner";
import { UPLOAD_PROCESSING_STEPS } from "@/lib/constants";
import {
  useGetDocumentQuery,
  useGetDocumentAnalysisQuery,
  useLazyExportDocumentPDFQuery,
} from "@/store/apiSlice";

export default function DocumentPage({ defaultTab = "extraction" }: { defaultTab?: "extraction" | "risk" | "chat" }) {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [activeTab, setActiveTab] = useState<"extraction" | "risk" | "chat">(defaultTab);
  const [pollingInterval, setPollingInterval] = useState(0);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const {
    data: doc,
    error: docError,
    isLoading: docLoading,
    refetch: refetchDoc,
  } = useGetDocumentQuery(id, {
    pollingInterval,
  });

  const {
    data: analysis,
    error: analysisError,
    isLoading: analysisLoading,
  } = useGetDocumentAnalysisQuery(id, {
    skip: !doc || doc.status !== "completed",
  });

  const [triggerExport, { isFetching: exporting }] = useLazyExportDocumentPDFQuery();

  // Poll for document completion if the state is processing and the user is on this page
  useEffect(() => {
    const isCurrentlyOnPage = typeof window !== "undefined" && window.location.pathname.includes(id);
    if (isCurrentlyOnPage && doc && (doc.status === "pending" || doc.status === "processing")) {
      setPollingInterval(2000);
    } else {
      setPollingInterval(0);
    }
    return () => {
      setPollingInterval(0);
    };
  }, [doc, id]);

  const handleExportPDF = async () => {
    if (!doc) return;
    try {
      const blob = await triggerExport(id).unwrap();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      
      // Clean filename for the export
      const safeFilename = doc.filename.replace(/\.pdf$/i, "");
      a.download = `DocMind_Analysis_${safeFilename}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      toast.error("An error occurred while generating and downloading the PDF report.");
    }
  };

  const loading = docLoading || (doc?.status === "completed" && !analysis && analysisLoading);
  const error = docError
    ? "Document not found"
    : analysisError
    ? "Failed to load document analysis"
    : null;

  if (loading) {
    return (
      <div className="flex h-screen w-screen bg-zinc-950 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
        <div className="flex-1 flex flex-col items-center justify-center gap-3 bg-zinc-950">
          <Loader2 className="animate-spin text-indigo-500" size={32} />
          <p className="text-sm text-zinc-400">Loading document...</p>
        </div>
      </div>
    );
  }

  if (error || !doc) {
    return (
      <div className="flex h-screen w-screen bg-zinc-950 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6 bg-zinc-950">
          <AlertCircle className="text-red-500" size={48} />
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-white">Load Error</h3>
            <p className="text-sm text-zinc-400 max-w-sm">
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
    const getActiveStep = (detailedStatus?: string | null) => {
      if (!detailedStatus) return 0;
      if (detailedStatus.startsWith("Reading")) return 0;
      if (detailedStatus.startsWith("Detecting")) return 1;
      if (detailedStatus.startsWith("Indexing")) return 2;
      if (detailedStatus.startsWith("Extracting")) return 3;
      if (detailedStatus.startsWith("Performing")) return 4;
      if (detailedStatus.startsWith("Completed")) return 5;
      return 0;
    };

    const activeStep = getActiveStep(doc.detailed_status);

    return (
      <div className="flex h-screen w-screen bg-zinc-950 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center px-6 bg-zinc-950 overflow-y-auto py-10">
          <Loader2 className="animate-spin text-indigo-500" size={48} />
          
          <div className="space-y-2">
            <h3 className="text-xl font-bold text-white animate-pulse">Analyzing Document</h3>
            <p className="text-sm text-zinc-400 max-w-sm mx-auto leading-relaxed">
              Please wait while we process the document. You can see the real-time progress of each step below.
            </p>
          </div>

          {/* Real-time step progress list */}
          <div className="w-full max-w-md bg-zinc-900/60 border border-zinc-800/80 p-5 rounded-2xl text-left space-y-3.5 shadow-xl">
            {UPLOAD_PROCESSING_STEPS.map((stepText, idx) => {
              const isDone = activeStep > idx;
              const isActive = activeStep === idx;
              return (
                <div key={idx} className={`flex items-center gap-3.5 text-xs transition-colors duration-300 ${isDone ? "text-indigo-400" : isActive ? "text-white animate-pulse" : "text-zinc-500"}`}>
                  {isDone ? (
                    <span className="h-5 w-5 bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 flex items-center justify-center font-bold text-[10px] rounded-full shrink-0">✓</span>
                  ) : isActive ? (
                    <Loader2 className="animate-spin text-indigo-400 shrink-0" size={14} />
                  ) : (
                    <span className="h-5 w-5 bg-zinc-950 border border-zinc-800 flex items-center justify-center text-zinc-500 text-[10px] rounded-full shrink-0">{idx + 1}</span>
                  )}
                  <span className={isActive ? "font-semibold" : "font-normal"}>{stepText}</span>
                </div>
              );
            })}
          </div>

          <div className="max-w-xs bg-zinc-900/40 border border-zinc-800 p-4 rounded-xl text-xs text-zinc-400 text-left space-y-1">
            <span className="font-semibold text-zinc-300 select-none">Did you know?</span>
            <p>DocuMind supports Hindi and Hinglish. It will automatically translate risks and drafts to match the source language!</p>
          </div>
        </div>
      </div>
    );
  }

  // Failed state
  if (doc.status === "failed") {
    return (
      <div className="flex h-screen w-screen bg-zinc-950 overflow-hidden text-zinc-100 font-sans">
        <Sidebar activeId={id} isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
        <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6 bg-zinc-950">
          <AlertCircle className="text-red-500" size={48} />
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-white">Analysis Failed</h3>
            <p className="text-sm text-zinc-400 max-w-xs mx-auto">
              The document processing failed. Ensure the file is not corrupted or password-protected.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => refetchDoc()}
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
      <Sidebar activeId={id} isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />

      {/* Main Workspace */}
      <div className="flex-1 flex flex-col h-full overflow-hidden p-6 md:p-8 bg-zinc-950">
        {/* Workspace Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-900 pb-5 mb-6 shrink-0">
          <div className="space-y-1.5 min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsSidebarOpen(true)}
                className="md:hidden p-1.5 text-zinc-400 hover:text-white bg-zinc-900 rounded-lg hover:bg-zinc-800 transition mr-1 cursor-pointer focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
                title="Open menu"
                aria-label="Open navigation menu"
              >
                <Menu size={16} />
              </button>
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
              {doc.status === "completed" && (
                <button
                  onClick={handleExportPDF}
                  disabled={exporting}
                  className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-600 border border-emerald-500/30 text-white disabled:opacity-50 px-3 py-0.5 rounded-full text-[11px] font-semibold transition cursor-pointer select-none active:scale-95 shadow-sm shrink-0"
                >
                  {exporting ? (
                    <>
                      <Loader2 className="animate-spin text-emerald-200" size={11} />
                      Exporting...
                    </>
                  ) : (
                    <>
                      <Download size={11} className="text-emerald-200" />
                      Export PDF Report
                    </>
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Tab Navigation */}
          <div 
            role="tablist" 
            aria-label="Document views"
            className="flex bg-zinc-900/80 border border-zinc-800 p-1 rounded-xl shrink-0 select-none shadow-inner overflow-x-auto"
            onKeyDown={(e) => {
              const tabs = ["extraction", "risk", "chat"] as const;
              const currentIndex = tabs.indexOf(activeTab);
              if (e.key === "ArrowRight") {
                setActiveTab(tabs[(currentIndex + 1) % tabs.length]);
              } else if (e.key === "ArrowLeft") {
                setActiveTab(tabs[(currentIndex - 1 + tabs.length) % tabs.length]);
              }
            }}
          >
            <button
              role="tab"
              aria-selected={activeTab === "extraction"}
              aria-controls="panel-extraction"
              id="tab-extraction"
              onClick={() => setActiveTab("extraction")}
              className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer select-none whitespace-nowrap ${
                activeTab === "extraction"
                  ? "bg-zinc-800 text-white shadow-sm border border-zinc-700/30"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Key Details
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "risk"}
              aria-controls="panel-risk"
              id="tab-risk"
              onClick={() => setActiveTab("risk")}
              className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer select-none whitespace-nowrap ${
                activeTab === "risk"
                  ? "bg-zinc-800 text-white shadow-sm border border-zinc-700/30"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Risk & Drafts
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "chat"}
              aria-controls="panel-chat"
              id="tab-chat"
              onClick={() => setActiveTab("chat")}
              className={`px-4 py-1.5 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 cursor-pointer select-none whitespace-nowrap ${
                activeTab === "chat"
                  ? "bg-zinc-800 text-white shadow-sm border border-zinc-700/30"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Document Chat
            </button>
          </div>
        </div>

        {/* Tab Panels */}
        <div className="flex-1 overflow-hidden">
          <ErrorBoundary>
            {activeTab === "extraction" && (
              <div role="tabpanel" id="panel-extraction" aria-labelledby="tab-extraction" className="h-full">
                <ExtractionView
                  language={doc.language}
                  extractedEntities={analysis?.extracted_entities || {}}
                  rawText={doc.raw_text}
                />
              </div>
            )}

            {activeTab === "risk" && (
              <div role="tabpanel" id="panel-risk" aria-labelledby="tab-risk" className="h-full">
                <RiskAnalysisView
                  documentId={id}
                  riskFlags={analysis?.risk_flags || []}
                  riskObligationSummary={analysis?.risk_obligation_summary || ""}
                  onReanalyzeSuccess={() => refetchDoc()}
                  rawText={doc.raw_text}
                />
              </div>
            )}

            {activeTab === "chat" && (
              <div role="tabpanel" id="panel-chat" aria-labelledby="tab-chat" className="h-full">
                <ChatView
                  documentId={id}
                  filename={doc.filename}
                  suggestedQuestions={analysis?.extracted_entities?.suggested_questions}
                />
              </div>
            )}
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
