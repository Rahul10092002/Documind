"use client";

import { useState } from "react";
import { User, Calendar, DollarSign, ShieldAlert, FileText, Search, Maximize2, Minimize2, ChevronDown, ChevronUp, HelpCircle } from "lucide-react";

interface ExtractionViewProps {
  language: string | null;
  extractedEntities: {
    dates?: string[];
    amounts?: string[];
    parties?: string[];
    obligations?: string[];
  };
  rawText: string | null;
}

export default function ExtractionView({
  language,
  extractedEntities,
  rawText,
}: ExtractionViewProps) {
  const [collapsedComponents, setCollapsedComponents] = useState<Record<string, boolean>>({
    parties: false,
    dates: false,
    amounts: false,
    obligations: false,
  });
  const [maximizedComponent, setMaximizedComponent] = useState<string | null>(null);

  const parties = extractedEntities?.parties || [];
  const dates = extractedEntities?.dates || [];
  const amounts = extractedEntities?.amounts || [];
  const obligations = extractedEntities?.obligations || [];

  const rawTextLines = rawText ? rawText.split("\n") : [];


  const toggleCollapse = (key: string) => {
    setCollapsedComponents((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const renderCardActions = (key: string, isMaximized: boolean) => {
    const isCollapsed = collapsedComponents[key];
    return (
      <div className="flex items-center gap-1.5 select-none">
        {/* Full-Screen Maximize/Minimize Toggle */}
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
        
        {/* Inline Expand/Collapse Toggle */}
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

  // Helper renderers for metadata cards to keep layout code DRY and readable
  const renderPartiesCard = (isMaximized = false) => {
    const isCollapsed = collapsedComponents.parties && !isMaximized;
    return (
      <div className={`bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-6 shadow-lg hover:border-zinc-700/60 transition-all duration-300 flex flex-col ${
        isMaximized ? "h-full animate-scale-up" : isCollapsed ? "min-h-[72px]" : "min-h-[220px]"
      }`}>
        <div className={`flex items-center justify-between pb-3 shrink-0 select-none ${isCollapsed ? "border-none" : "border-b border-zinc-850 mb-5"}`}>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/25 flex items-center justify-center">
              <User size={16} />
            </div>
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Contracting Parties & Signatories</h4>
          </div>
          {renderCardActions("parties", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {parties.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center bg-zinc-900/10 border border-dashed border-zinc-800/80 rounded-xl p-4 select-none">
                <HelpCircle size={16} className="text-zinc-500 mb-1.5" />
                <p className="text-xs font-semibold text-zinc-400">No parties detected</p>
                <p className="text-[10px] text-zinc-600 mt-1 leading-relaxed max-w-sm">
                  We couldn't extract contracting names. If this document is scanned, try checking the document text.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {parties.map((party, idx) => (
                  <div key={idx} className="flex items-center gap-3 bg-zinc-950/40 p-3 rounded-xl border border-zinc-900/50 hover:border-zinc-800 transition duration-200">
                    <div className="h-8 w-8 rounded-lg bg-indigo-500/10 text-indigo-300 flex items-center justify-center font-bold text-xs border border-indigo-500/20 shadow-sm shrink-0">
                      {party.charAt(0).toUpperCase()}
                    </div>
                    <span className="text-sm text-zinc-250 font-semibold truncate">{party}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderDatesCard = (isMaximized = false) => {
    const isCollapsed = collapsedComponents.dates && !isMaximized;
    return (
      <div className={`bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-6 shadow-lg hover:border-zinc-700/60 transition-all duration-300 flex flex-col ${
        isMaximized ? "h-full animate-scale-up" : isCollapsed ? "min-h-[72px]" : "min-h-[220px]"
      }`}>
        <div className={`flex items-center justify-between pb-3 shrink-0 select-none ${isCollapsed ? "border-none" : "border-b border-zinc-850 mb-5"}`}>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/25 flex items-center justify-center">
              <Calendar size={16} />
            </div>
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Important Timelines & Deadlines</h4>
          </div>
          {renderCardActions("dates", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {dates.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center bg-zinc-900/10 border border-dashed border-zinc-800/80 rounded-xl p-4 select-none">
                <HelpCircle size={16} className="text-zinc-500 mb-1.5" />
                <p className="text-xs font-semibold text-zinc-400">No deadlines detected</p>
                <p className="text-[10px] text-zinc-600 mt-1 leading-relaxed max-w-sm">
                  No concrete deadlines, timelines, or expiration dates were identified in this document.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                {dates.map((date, idx) => (
                  <div key={idx} className="flex items-center gap-2.5 bg-zinc-950/40 p-3 rounded-xl border border-zinc-900/50 hover:border-zinc-800 transition duration-200">
                    <Calendar size={13} className="text-emerald-500 shrink-0" />
                    <span className="text-xs text-zinc-300 font-semibold">{date}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderAmountsCard = (isMaximized = false) => {
    const isCollapsed = collapsedComponents.amounts && !isMaximized;
    return (
      <div className={`bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-6 shadow-lg hover:border-zinc-700/60 transition-all duration-300 flex flex-col ${
        isMaximized ? "h-full animate-scale-up" : isCollapsed ? "min-h-[72px]" : "min-h-[220px]"
      }`}>
        <div className={`flex items-center justify-between pb-3 shrink-0 select-none ${isCollapsed ? "border-none" : "border-b border-zinc-850 mb-5"}`}>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-amber-500/15 text-amber-400 border border-amber-500/25 flex items-center justify-center">
              <DollarSign size={16} />
            </div>
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Financial Value & Payment Terms</h4>
          </div>
          {renderCardActions("amounts", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {amounts.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center bg-zinc-900/10 border border-dashed border-zinc-800/80 rounded-xl p-4 select-none">
                <HelpCircle size={16} className="text-zinc-500 mb-1.5" />
                <p className="text-xs font-semibold text-zinc-400">No monetary values detected</p>
                <p className="text-[10px] text-zinc-600 mt-1 leading-relaxed max-w-sm">
                  We didn't detect currency figures or specific payment obligations in the extracted text.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                {amounts.map((amt, idx) => (
                  <div key={idx} className="flex items-center gap-2.5 bg-zinc-950/40 p-3 rounded-xl border border-zinc-900/50 hover:border-zinc-800 transition duration-200">
                    <span className="h-4.5 w-4.5 rounded bg-amber-500/15 text-amber-400 flex items-center justify-center font-bold text-[10px] border border-amber-500/20 shrink-0">₹</span>
                    <span className="text-xs text-zinc-300 font-semibold">{amt}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderObligationsCard = (isMaximized = false) => {
    const isCollapsed = collapsedComponents.obligations && !isMaximized;
    return (
      <div className={`bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-6 shadow-lg hover:border-zinc-700/60 transition-all duration-300 flex flex-col ${
        isMaximized ? "h-full animate-scale-up" : isCollapsed ? "min-h-[72px]" : "min-h-[220px]"
      }`}>
        <div className={`flex items-center justify-between pb-3 shrink-0 select-none ${isCollapsed ? "border-none" : "border-b border-zinc-850 mb-5"}`}>
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/25 flex items-center justify-center">
              <ShieldAlert size={16} />
            </div>
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Core Obligations & Covenants</h4>
          </div>
          {renderCardActions("obligations", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {obligations.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center bg-zinc-900/10 border border-dashed border-zinc-800/80 rounded-xl p-4 select-none">
                <HelpCircle size={16} className="text-zinc-500 mb-1.5" />
                <p className="text-xs font-semibold text-zinc-400">No key covenants detected</p>
                <p className="text-[10px] text-zinc-600 mt-1 leading-relaxed max-w-sm">
                  No strict obligations or legal covenants were parsed. This document may be informative only.
                </p>
              </div>
            ) : (
              <ul className="space-y-3">
                {obligations.map((ob, idx) => (
                  <li key={idx} className="flex items-start gap-3 text-sm text-zinc-300 bg-zinc-950/20 p-3.5 rounded-xl border border-zinc-900/50 hover:border-zinc-800 transition duration-200">
                    <span className="h-5 w-5 bg-purple-500/10 text-purple-400 border border-purple-500/20 flex items-center justify-center font-bold text-[10px] rounded shrink-0 mt-0.5 select-none">
                      {idx + 1}
                    </span>
                    <span className="leading-relaxed text-zinc-300 text-xs font-medium">{ob}</span>
                  </li>
                ))}
              </ul>
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
          {maximizedComponent === "parties" && renderPartiesCard(true)}
          {maximizedComponent === "dates" && renderDatesCard(true)}
          {maximizedComponent === "amounts" && renderAmountsCard(true)}
          {maximizedComponent === "obligations" && renderObligationsCard(true)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 h-full overflow-hidden animate-fade-in">
      {/* Small metadata bar at top */}
      <div className="flex items-center justify-between border-b border-zinc-900 pb-4 shrink-0 select-none">
        <div>
          <h3 className="text-xl font-bold text-white tracking-tight">Key Details</h3>
          <p className="text-xs text-zinc-400 mt-1">
            Toggle minimize/maximize icons on individual panels to adapt the dashboard layout.
          </p>
        </div>

        <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-zinc-900 text-indigo-400 border border-zinc-800/80 font-mono shadow-sm">
          LANG: {language ? language.toUpperCase() : "UNKNOWN"}
        </span>
      </div>

      {/* Main Stack Container */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-2 h-full scrollbar-thin pb-8">
        {renderObligationsCard(false)}
        {renderPartiesCard(false)}
        {renderAmountsCard(false)}
        {renderDatesCard(false)}
      </div>
    </div>
  );
}
