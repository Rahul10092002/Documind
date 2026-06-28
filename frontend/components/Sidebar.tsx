"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { FileText, Plus, Trash2, Loader2, AlertCircle, CheckCircle, Search, X, Filter } from "lucide-react";
import { toast } from "sonner";
import { useGetDocumentsQuery, useDeleteDocumentMutation } from "@/store/apiSlice";

interface SidebarProps {
  activeId?: string;
  isOpen?: boolean;
  onClose?: () => void;
}

export default function Sidebar({ activeId, isOpen = false, onClose }: SidebarProps) {
  const router = useRouter();
  const [pollingInterval, setPollingInterval] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [langFilter, setLangFilter] = useState("all");

  const { data: documents = [], error: getError, isLoading: loading } = useGetDocumentsQuery(undefined, {
    pollingInterval,
  });

  const [deleteDocument] = useDeleteDocumentMutation();

  useEffect(() => {
    const hasProcessing = documents.some(
      (doc) => doc.status === "processing" || doc.status === "pending"
    );
    setPollingInterval(hasProcessing ? 3000 : 0);
  }, [documents]);

  const error = getError ? "Failed to load history" : null;

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    toast.custom((t) => (
      <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl shadow-xl flex flex-col gap-3 min-w-[300px]">
        <h3 className="text-white font-bold text-sm">Delete Document?</h3>
        <p className="text-zinc-400 text-xs">Are you sure you want to delete this document? This action cannot be undone.</p>
        <div className="flex justify-end gap-2 mt-2">
          <button onClick={() => toast.dismiss(t)} className="px-3 py-1.5 rounded-lg text-xs font-semibold text-zinc-300 hover:bg-zinc-800">Cancel</button>
          <button onClick={async () => {
            toast.dismiss(t);
            try {
              await deleteDocument(id).unwrap();
              if (activeId === id) {
                router.push("/");
              }
              toast.success("Document deleted successfully");
            } catch (err) {
              console.error("Delete error:", err);
              toast.error("Failed to delete document.");
            }
          }} className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-600 hover:bg-red-700 text-white">Delete</button>
        </div>
      </div>
    ));
  };

  const handleSelect = (id: string) => {
    router.push(`/documents/${id}`);
    if (onClose) onClose();
  };

  // Client-side filtering logic
  const filteredDocs = useMemo(() => {
    return documents.filter((doc) => {
      const matchesSearch = doc.filename.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesLang =
        langFilter === "all" ||
        (langFilter === "en" && doc.language === "en") ||
        (langFilter === "hi" && doc.language === "hi") ||
        (langFilter === "hi-Latn" && doc.language === "hi-Latn");
      return matchesSearch && matchesLang;
    });
  }, [documents, searchTerm, langFilter]);

  // Date categorization helper
  const categorized = useMemo(() => {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;

    const categories: { today: typeof documents; yesterday: typeof documents; older: typeof documents } = {
      today: [],
      yesterday: [],
      older: [],
    };

    filteredDocs.forEach((doc) => {
      const uploadTime = new Date(doc.upload_date).getTime();
      if (uploadTime >= startOfToday) {
        categories.today.push(doc);
      } else if (uploadTime >= startOfYesterday) {
        categories.yesterday.push(doc);
      } else {
        categories.older.push(doc);
      }
    });

    return categories;
  }, [filteredDocs]);

  return (
    <>
      {/* Mobile backdrop overlay */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 z-40 bg-zinc-950/60 backdrop-blur-sm md:hidden transition-opacity duration-300"
          aria-hidden="true"
        />
      )}

      <div
        role="navigation"
        aria-label="Document Management Sidebar"
        className={`fixed inset-y-0 left-0 z-50 flex flex-col h-screen bg-zinc-950 border-r border-zinc-900 text-zinc-200 shrink-0 transition-all duration-300 ease-in-out md:relative md:translate-x-0 ${
          isOpen ? "w-full sm:w-80 translate-x-0 shadow-2xl shadow-black/80" : "w-full sm:w-80 -translate-x-full md:w-72 lg:w-80"
        }`}
      >
        {/* Brand Header */}
        <div className="p-5 border-b border-zinc-900 flex items-center justify-between">
          <div
            className="flex items-center gap-3 cursor-pointer select-none group"
            onClick={() => {
              router.push("/");
              if (onClose) onClose();
            }}
          >
            <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-md shadow-lg shadow-indigo-500/25 group-hover:scale-105 transition-transform duration-200">
              🧠
            </div>
            <div>
              <h1 className="font-bold text-white text-sm leading-tight bg-gradient-to-r from-zinc-100 to-zinc-300 bg-clip-text text-transparent group-hover:from-white group-hover:to-zinc-200 transition-all duration-200">
                DocuMind
              </h1>
              <p className="text-[9px] text-zinc-500 font-semibold tracking-wider uppercase">Document Intelligence</p>
            </div>
          </div>

          {/* Close button visible only on mobile */}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 md:hidden text-zinc-400 hover:text-white bg-zinc-900 rounded-lg hover:bg-zinc-800 transition cursor-pointer"
              title="Close sidebar"
              aria-label="Close sidebar"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Action Button */}
        <div className="p-4 border-b border-zinc-900/50">
          <button
            onClick={() => {
              router.push("/");
              if (onClose) onClose();
            }}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 active:scale-[0.98] text-white rounded-xl py-2 px-4 font-semibold transition-all duration-200 text-xs shadow-md cursor-pointer select-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
            aria-label="Upload new PDF document"
          >
            <Plus size={14} className="stroke-[2.5]" />
            Upload Document
          </button>
        </div>

        {/* Search & Filter Controls */}
        <div className="p-4 space-y-2 border-b border-zinc-900/50">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 text-zinc-500" size={13} />
            <input
              type="text"
              placeholder="Search documents..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-200 pl-8.5 pr-3 py-1.5 rounded-lg focus:outline-none focus:border-indigo-500/70 transition"
              aria-label="Search documents by name"
            />
          </div>

          <div className="flex items-center gap-2 bg-zinc-900/40 border border-zinc-850 px-2.5 py-1 rounded-lg">
            <Filter size={11} className="text-zinc-500" />
            <select
              value={langFilter}
              onChange={(e) => setLangFilter(e.target.value)}
              className="bg-transparent text-[11px] text-zinc-400 focus:outline-none w-full cursor-pointer font-medium"
              aria-label="Filter documents by language"
            >
              <option value="all">All Languages</option>
              <option value="en">English (EN)</option>
              <option value="hi">Hindi (HI)</option>
              <option value="hi-Latn">Hinglish (HI-L)</option>
            </select>
          </div>
        </div>

        {/* History List */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4">
          {loading && (
            <div className="flex flex-col gap-2 p-1">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-14 w-full bg-zinc-900/40 rounded-lg animate-pulse border border-zinc-800/60" />
              ))}
            </div>
          )}

          {!loading && error && (
            <div className="text-center py-6 text-zinc-500 text-xs px-4 border border-zinc-900 rounded-lg">
              {error}
            </div>
          )}

          {!loading && !error && documents.length === 0 && (
            <div className="text-center py-12 text-zinc-600 text-xs px-4 italic">
              No documents uploaded yet.
            </div>
          )}

          {!loading && !error && documents.length > 0 && filteredDocs.length === 0 && (
            <div className="text-center py-8 text-zinc-600 text-xs px-4">
              No matching files found.
            </div>
          )}

          {!loading && !error && filteredDocs.length > 0 && (
            <div className="space-y-4" role="list" aria-label="Recent documents list">
              {/* Category: Today */}
              {categorized.today.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[9px] font-bold text-zinc-500 px-3 tracking-wider uppercase select-none">
                    Today
                  </div>
                  {categorized.today.map((doc) => renderDocItem(doc))}
                </div>
              )}

              {/* Category: Yesterday */}
              {categorized.yesterday.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[9px] font-bold text-zinc-500 px-3 tracking-wider uppercase select-none">
                    Yesterday
                  </div>
                  {categorized.yesterday.map((doc) => renderDocItem(doc))}
                </div>
              )}

              {/* Category: Older */}
              {categorized.older.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[9px] font-bold text-zinc-500 px-3 tracking-wider uppercase select-none">
                    Older
                  </div>
                  {categorized.older.map((doc) => renderDocItem(doc))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );

  function renderDocItem(doc: any) {
    const isActive = doc.id === activeId;
    return (
      <div
        key={doc.id}
        onClick={() => handleSelect(doc.id)}
        role="listitem"
        className={`relative group flex items-center justify-between p-2.5 rounded-xl cursor-pointer border transition-all duration-200 ${
          isActive
            ? "bg-zinc-900 border-zinc-800 text-white shadow-md"
            : "hover:bg-zinc-900/40 text-zinc-400 hover:text-zinc-200 border-transparent"
        } focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none`}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleSelect(doc.id);
          }
        }}
      >
        {isActive && (
          <span className="absolute left-0 top-2.5 bottom-2.5 w-0.5 bg-indigo-500 rounded-r" />
        )}

        <div className="flex items-center gap-2.5 overflow-hidden">
          <FileText
            className={isActive ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-400"}
            size={14}
          />
          <div className="flex flex-col text-left overflow-hidden">
            <span className="text-xs font-semibold truncate pr-1">
              {doc.filename}
            </span>
            <span className="text-[9px] text-zinc-500 font-bold font-mono uppercase tracking-wide">
              {doc.language ? doc.language.toUpperCase() : "DETECTING..."}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Status Indicators */}
          {doc.status === "processing" || doc.status === "pending" ? (
            <Loader2 className="animate-spin text-amber-500 shrink-0" size={11} />
          ) : doc.status === "failed" ? (
            <AlertCircle className="text-red-500 shrink-0" size={11} />
          ) : (
            <CheckCircle className="text-emerald-500 opacity-60 group-hover:opacity-100 shrink-0" size={11} />
          )}

          <button
            onClick={(e) => handleDelete(e, doc.id)}
            className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-zinc-800/80 transition duration-150 cursor-pointer opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
            title="Delete document"
            aria-label={`Delete ${doc.filename}`}
          >
            <Trash2 size={11} />
          </button>
        </div>
      </div>
    );
  }
}
