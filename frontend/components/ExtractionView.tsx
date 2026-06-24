"use client";

import { useState } from "react";
import { User, Calendar, DollarSign, ShieldAlert, FileText, Search, Maximize2, Minimize2, ChevronDown, ChevronUp } from "lucide-react";

interface ExtractionViewProps {
  filename: string;
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
  const [searchTerm, setSearchTerm] = useState("");
  const [collapsedComponents, setCollapsedComponents] = useState<Record<string, boolean>>({
    parties: false,
    dates: false,
    amounts: false,
    obligations: false,
    preview: false,
  });
  const [maximizedComponent, setMaximizedComponent] = useState<string | null>(null);

  const parties = extractedEntities?.parties || [];
  const dates = extractedEntities?.dates || [];
  const amounts = extractedEntities?.amounts || [];
  const obligations = extractedEntities?.obligations || [];

  const rawTextLines = rawText ? rawText.split("\n") : [];

  const handleHighlight = (text: string) => {
    if (!searchTerm || !text) return text;
    const parts = text.split(new RegExp(`(${searchTerm})`, "gi"));
    return (
      <>
        {parts.map((part, i) =>
          part.toLowerCase() === searchTerm.toLowerCase() ? (
            <mark key={i} className="bg-indigo-500/35 text-indigo-200 px-1 py-0.5 rounded border border-indigo-500/20 font-semibold shadow-sm">
              {part}
            </mark>
          ) : (
            part
          )
        )}
      </>
    );
  };

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
            onClick={() => setMaximizedComponent(null)}
            className="p-1.5 rounded-lg bg-zinc-950 hover:bg-zinc-800 hover:text-white text-zinc-400 transition cursor-pointer"
            title="Restore View"
          >
            <Minimize2 size={13} />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setMaximizedComponent(key)}
            className="p-1.5 rounded-lg bg-zinc-950 hover:bg-zinc-800 hover:text-white text-zinc-400 transition cursor-pointer"
            title="Maximize to Full Screen"
          >
            <Maximize2 size={13} />
          </button>
        )}
        
        {/* Inline Expand/Collapse Toggle */}
        {!isMaximized && (
          <button
            type="button"
            onClick={() => toggleCollapse(key)}
            className="p-1.5 rounded-lg bg-zinc-950 hover:bg-zinc-800 hover:text-white text-zinc-400 transition cursor-pointer"
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
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Involved Parties</h4>
          </div>
          {renderCardActions("parties", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {parties.length === 0 ? (
              <p className="text-xs text-zinc-550 italic select-none">No parties detected.</p>
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
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Key Dates</h4>
          </div>
          {renderCardActions("dates", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {dates.length === 0 ? (
              <p className="text-xs text-zinc-555 italic select-none">No dates detected.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                {dates.map((date, idx) => (
                  <div key={idx} className="flex items-center gap-2.5 bg-zinc-950/40 p-3 rounded-xl border border-zinc-900/50 hover:border-zinc-800 transition duration-200">
                    <Calendar size={13} className="text-emerald-555 shrink-0" />
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
            <div className="h-8 w-8 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/25 flex items-center justify-center">
              <DollarSign size={16} />
            </div>
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Monetary Amounts</h4>
          </div>
          {renderCardActions("amounts", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {amounts.length === 0 ? (
              <p className="text-xs text-zinc-550 italic select-none">No amounts detected.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
                {amounts.map((amt, idx) => (
                  <div key={idx} className="flex items-center gap-2.5 bg-zinc-950/40 p-3 rounded-xl border border-zinc-900/50 hover:border-zinc-800 transition duration-200">
                    <span className="h-4.5 w-4.5 rounded bg-amber-500/15 text-amber-455 flex items-center justify-center font-bold text-[10px] border border-amber-500/20 shrink-0">₹</span>
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
            <h4 className="font-bold text-xs uppercase tracking-wider text-zinc-300">Key Obligations & Terms</h4>
          </div>
          {renderCardActions("obligations", isMaximized)}
        </div>
        
        {!isCollapsed && (
          <div className={`flex-1 ${isMaximized ? "overflow-y-auto pr-1" : ""}`}>
            {obligations.length === 0 ? (
              <p className="text-xs text-zinc-550 italic select-none">No key obligations extracted.</p>
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

  const renderPreviewCard = (isMaximized = false) => {
    const isCollapsed = collapsedComponents.preview && !isMaximized;
    return (
      <div className={`bg-zinc-900/40 border border-zinc-800/80 rounded-2xl flex flex-col overflow-hidden shadow-lg ${
        isMaximized ? "h-full animate-scale-up" : isCollapsed ? "min-h-[72px]" : "min-h-[400px]"
      }`}>
        <div className={`p-4 flex items-center justify-between shrink-0 bg-zinc-900/80 select-none ${isCollapsed ? "border-none" : "border-b border-zinc-850"}`}>
          <div className="flex items-center gap-2 text-zinc-200">
            <FileText size={15} className="text-indigo-400" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-350">Document Text Preview</span>
          </div>
          {renderCardActions("preview", isMaximized)}
        </div>

        {!isCollapsed && (
          <>
            {/* Search bar */}
            <div className="p-3 border-b border-zinc-850 shrink-0 bg-zinc-950/20">
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 text-zinc-500" size={13} />
                <input
                  type="text"
                  placeholder="Search document text..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-zinc-950/50 text-xs text-zinc-200 rounded-lg pl-8 pr-3 py-1.5 border border-zinc-800/80 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/10 placeholder-zinc-650 transition"
                />
              </div>
            </div>

            {/* Scrollable text container with editor line numbers */}
            <div className="flex-1 overflow-y-auto bg-zinc-950/60 select-text py-4 scrollbar-thin">
              {rawTextLines.length > 0 ? (
                <div className="font-mono text-[11px] text-zinc-400 leading-relaxed whitespace-pre pr-4">
                  {rawTextLines.map((line, idx) => (
                    <div
                      key={idx}
                      className="flex hover:bg-zinc-900/40 py-0.5 px-3 transition-colors duration-150 group/line"
                    >
                      <span className="w-9 text-zinc-655 group-hover/line:text-zinc-550 select-none text-right pr-3 shrink-0 border-r border-zinc-800/80 mr-3 font-semibold">
                        {idx + 1}
                      </span>
                      <span className="flex-1 whitespace-pre-wrap">{handleHighlight(line || " ")}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-zinc-655 italic text-center py-16">No raw text available.</p>
              )}
            </div>
          </>
        )}
      </div>
    );
  };

  if (maximizedComponent) {
    return (
      <div className="h-[calc(100vh-180px)] w-full flex flex-col gap-4 animate-scale-up">
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
          {maximizedComponent === "preview" && renderPreviewCard(true)}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 h-[calc(100vh-180px)] overflow-hidden animate-fade-in">
      {/* Small metadata bar at top */}
      <div className="flex items-center justify-between border-b border-zinc-900 pb-4 shrink-0 select-none">
        <div>
          <h3 className="text-xl font-bold text-white tracking-tight">Extracted Metadata</h3>
          <p className="text-xs text-zinc-405 mt-1">
            Toggle minimize/maximize icons on individual panels to adapt the dashboard layout.
          </p>
        </div>

        <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-zinc-900 text-indigo-400 border border-zinc-800/80 font-mono shadow-sm">
          LANG: {language ? language.toUpperCase() : "UNKNOWN"}
        </span>
      </div>

      {/* Main Stack Container */}
      <div className="flex-1 overflow-y-auto space-y-6 pr-2 h-full scrollbar-thin pb-8">
        {renderPartiesCard(false)}
        {renderDatesCard(false)}
        {renderAmountsCard(false)}
        {renderObligationsCard(false)}
        {renderPreviewCard(false)}
      </div>
    </div>
  );
}
