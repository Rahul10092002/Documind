"use client";

import { useState } from "react";
import { AlertTriangle, FileText, Clipboard, Check, Download, RefreshCw, Loader2, Maximize2, Minimize2, ChevronDown, ChevronUp } from "lucide-react";

import { useReanalyzeDocumentMutation } from "@/store/apiSlice";

interface RiskFlag {
  clause: string;
  reason: string;
  level?: "high" | "medium" | "low";
}

interface RiskAnalysisViewProps {
  documentId: string;
  riskFlags: RiskFlag[];
  riskObligationSummary: string | null;
  onReanalyzeSuccess: (updatedAnalysis: any) => void;
  rawText?: string | null;
}

export default function RiskAnalysisView({
  documentId,
  riskFlags,
  riskObligationSummary,
  onReanalyzeSuccess,
  rawText,
}: RiskAnalysisViewProps) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const [reanalyzeDocument, { isLoading: reanalyzing }] = useReanalyzeDocumentMutation();

  const [collapsedComponents, setCollapsedComponents] = useState<Record<string, boolean>>({
    risk: false,
    draft: false,
  });
  const [maximizedComponent, setMaximizedComponent] = useState<string | null>(null);

  const handleCopy = () => {
    if (!riskObligationSummary) return;
    navigator.clipboard.writeText(riskObligationSummary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!riskObligationSummary) return;
    const element = document.createElement("a");
    const file = new Blob([riskObligationSummary], { type: "text/plain;charset=utf-8" });
    element.href = URL.createObjectURL(file);
    element.download = `analysis_summary_doc_${documentId}.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const handleReanalyze = async () => {
    setError(null);
    try {
      const data = await reanalyzeDocument(documentId).unwrap();
      onReanalyzeSuccess(data);
    } catch (err: any) {
      console.error(err);
      setError("Failed to re-analyze document.");
    }
  };

  const toggleCollapse = (key: string) => {
    setCollapsedComponents((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderCardActions = (key: string, isMaximized: boolean) => {
    const isCollapsed = collapsedComponents[key];
    return (
      <div className="flex items-center gap-1.5 select-none shrink-0">
        {/* Full-Screen Toggle */}
        {isMaximized ? (
          <button
            type="button"
            aria-label="Restore view"
            onClick={() => setMaximizedComponent(null)}
            className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg bg-zinc-950 hover:bg-zinc-800 hover:text-white text-zinc-400 transition cursor-pointer"
            title="Restore View"
          >
            <Minimize2 size={13} />
          </button>
        ) : (
          <button
            type="button"
            aria-label="Maximize to full screen"
            onClick={() => setMaximizedComponent(key)}
            className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg bg-zinc-950 hover:bg-zinc-800 hover:text-white text-zinc-400 transition cursor-pointer"
            title="Maximize to Full Screen"
          >
            <Maximize2 size={13} />
          </button>
        )}
        
        {/* Collapse/Expand Toggle */}
        {!isMaximized && (
          <button
            type="button"
            aria-label={isCollapsed ? "Expand section" : "Collapse section"}
            onClick={() => toggleCollapse(key)}
            className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg bg-zinc-950 hover:bg-zinc-800 hover:text-white text-zinc-400 transition cursor-pointer"
            title={isCollapsed ? "Expand Section" : "Collapse Section"}
          >
            {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        )}
      </div>
    );
  };

  const renderRiskCard = (isMaximized = false) => {
    const isCollapsed = collapsedComponents.risk && !isMaximized;
    return (
      <div className={`bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-6 shadow-lg hover:border-zinc-700/60 transition-all duration-300 flex flex-col ${
        isMaximized ? "h-full animate-scale-up" : isCollapsed ? "min-h-[72px]" : "min-h-[300px]"
      }`}>
        <div className={`flex items-center justify-between pb-3 shrink-0 select-none ${isCollapsed ? "border-none" : "border-b border-zinc-800 mb-5"}`}>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-red-500/10 text-red-400 border border-red-500/25 flex items-center justify-center">
              <AlertTriangle size={16} />
            </div>
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Risk Flags & Exposure</h4>
          </div>

          <div className="flex items-center gap-3 select-none">
            {!isCollapsed && (
              <button
                type="button"
                onClick={handleReanalyze}
                disabled={reanalyzing}
                className="flex items-center gap-1.5 bg-zinc-950 border border-zinc-800 hover:bg-zinc-800 hover:border-zinc-700 hover:text-white text-zinc-300 disabled:text-zinc-500 rounded-xl px-3 py-1.5 text-[11px] font-semibold transition cursor-pointer select-none active:scale-95 shrink-0 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
              >
                {reanalyzing ? (
                  <>
                    <Loader2 className="animate-spin shrink-0 text-indigo-400" size={12} />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="shrink-0 text-indigo-400" size={12} />
                    Re-analyze
                  </>
                )}
              </button>
            )}
            {renderCardActions("risk", isMaximized)}
          </div>
        </div>

        {error && !isCollapsed && (
          <div className="bg-red-950/30 border border-red-900/50 text-red-200 text-xs rounded-xl p-3 mb-4 animate-fade-in select-none shrink-0">
            {error}
          </div>
        )}

        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {riskFlags.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 bg-zinc-900/20 border border-zinc-800 rounded-2xl text-zinc-400 text-center select-none">
                <AlertTriangle className="text-zinc-600 mb-2" size={24} />
                <p className="text-xs font-semibold text-zinc-300">No risks identified</p>
                <p className="text-[11px] text-zinc-500 mt-1 max-w-xs leading-relaxed">
                  This document didn't trigger any standard legal or compliance warning flags.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {riskFlags.map((risk, idx) => {
                  const level = (risk.level || "medium").toLowerCase();
                  
                  const cardColors =
                    level === "high"
                      ? "border-red-900/40 bg-red-950/10 hover:border-red-800/60 shadow-lg shadow-red-950/5"
                      : level === "medium"
                      ? "border-amber-900/40 bg-amber-950/10 hover:border-amber-800/60 shadow-lg shadow-amber-950/5"
                      : "border-yellow-900/30 bg-yellow-950/5 hover:border-yellow-800/60 shadow-md shadow-yellow-950/5";

                  const badgeColors =
                    level === "high"
                      ? "bg-red-500/10 text-red-400 border-red-500/20"
                      : level === "medium"
                      ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                      : "bg-yellow-500/10 text-yellow-400 border-yellow-500/20";

                  return (
                    <div
                      key={idx}
                      className={`border rounded-2xl p-5 space-y-3.5 transition duration-200 ${cardColors}`}
                    >
                      <div className="flex items-start justify-between select-none">
                        <span className={`px-2 py-0.5 text-[9px] font-bold rounded-md uppercase tracking-wider border font-mono ${badgeColors}`}>
                          {level} Severity Risk
                        </span>
                      </div>

                      <div className="space-y-1.5">
                        <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider select-none">
                          Flagged Clause / Provision
                        </div>
                        <blockquote className="border-l-2 border-zinc-700/80 pl-4 py-2 text-xs text-zinc-300 leading-relaxed bg-zinc-950/40 rounded-r-xl italic font-mono whitespace-pre-wrap select-text">
                          "{risk.clause}"
                        </blockquote>
                      </div>

                      <div className="space-y-1">
                        <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider select-none">
                          Exposure Assessment & Recommendations
                        </div>
                        <p className="text-xs text-zinc-400 font-medium leading-relaxed select-text">
                          {risk.reason}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderSummaryCard = (isMaximized = false) => {
    const isCollapsed = collapsedComponents.draft && !isMaximized;
    return (
      <div className={`bg-zinc-900/40 border border-zinc-800/80 rounded-2xl flex flex-col overflow-hidden shadow-xl ${
        isMaximized ? "h-full animate-scale-up" : isCollapsed ? "min-h-[72px]" : "min-h-[300px]"
      }`}>
        <div className={`p-4 flex items-center justify-between shrink-0 bg-zinc-900/80 select-none ${isCollapsed ? "border-none" : "border-b border-zinc-800"}`}>
          <div className="flex items-center gap-2 text-zinc-200">
            <FileText size={15} className="text-indigo-400" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-350">Risk, Fault & Obligation Summary</span>
          </div>

          <div className="flex items-center gap-2 select-none">
            {!isCollapsed && (
              <>
                <button
                  type="button"
                  aria-label="Copy to Clipboard"
                  onClick={handleCopy}
                  disabled={!riskObligationSummary}
                  className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg bg-zinc-950 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition cursor-pointer disabled:opacity-50 active:scale-95 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
                  title="Copy to Clipboard"
                >
                  {copied ? <Check size={13} className="text-emerald-500 animate-scale-up" /> : <Clipboard size={13} />}
                </button>
                <button
                  type="button"
                  aria-label="Download Summary"
                  onClick={handleDownload}
                  disabled={!riskObligationSummary}
                  className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg bg-zinc-950 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition cursor-pointer disabled:opacity-50 active:scale-95 focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
                  title="Download Summary"
                >
                  <Download size={13} />
                </button>
              </>
            )}
            {renderCardActions("draft", isMaximized)}
          </div>
        </div>

        {!isCollapsed && (
          <div className="flex-1 p-6 overflow-y-auto bg-zinc-950/60 font-sans text-xs text-zinc-300 leading-relaxed select-text whitespace-pre-wrap scrollbar-thin">
            {riskObligationSummary ? (
              <div className="bg-zinc-900/70 p-6 rounded-xl border border-zinc-800/80 shadow-inner font-sans text-zinc-300 max-w-full leading-relaxed select-text hover:border-zinc-750 transition-colors">
                {riskObligationSummary}
              </div>
            ) : (
              <p className="text-zinc-500 italic text-center py-16 select-none">
                No summary generated yet. Run re-analyze on the risk panel to analyze this document.
              </p>
            )}
          </div>
        )}
      </div>
    );
  };

  if (maximizedComponent) {
    return (
      <div className="h-full w-full flex flex-col gap-4 animate-scale-up">
        {/* Breadcrumb / Action bar to restore */}
        <div className="flex items-center justify-between border-b border-zinc-900 pb-3 select-none shrink-0">
          <button
            type="button"
            onClick={() => setMaximizedComponent(null)}
            className="flex items-center gap-1.5 text-xs font-semibold text-zinc-400 hover:text-white transition cursor-pointer"
          >
            ← Back to Multi-Section View
          </button>
          
          <span className="text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/25 px-3 py-1 rounded-full font-bold uppercase tracking-wider">
            Full Screen Focus Mode
          </span>
        </div>



        {/* Maximized component card */}
        <div className="flex-1 overflow-hidden h-full">
          {maximizedComponent === "risk" && renderRiskCard(true)}
          {maximizedComponent === "draft" && renderSummaryCard(true)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 h-full overflow-hidden animate-fade-in">
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-zinc-900 pb-4 shrink-0 select-none">
        <div>
          <h3 className="text-xl font-bold text-white tracking-tight">Risk & Drafts Assessment</h3>
          <p className="text-xs text-zinc-400 mt-1">
            Toggle collapse icons on the risk lists and draft reply sheets to adapt your view layout.
          </p>
        </div>
      </div>



      {/* Main Stack Container */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-2 h-full scrollbar-thin pb-8">
        {renderSummaryCard(false)}
        {renderRiskCard(false)}
      </div>
    </div>
  );
}
