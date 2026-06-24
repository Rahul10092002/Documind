"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FileText, Plus, Trash2, Loader2, AlertCircle, CheckCircle } from "lucide-react";

interface Document {
  id: string;
  filename: string;
  upload_date: string;
  language: string | null;
  status: "pending" | "processing" | "completed" | "failed";
}

interface SidebarProps {
  activeId?: string;
}

export default function Sidebar({ activeId }: SidebarProps) {
  const router = useRouter();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = async () => {
    try {
      const res = await fetch("http://localhost:8000/documents");
      if (!res.ok) throw new Error("Failed to fetch documents");
      const data = await res.json();
      setDocuments(data);
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError("Failed to load history");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  // Poll for document status updates if any document is processing
  useEffect(() => {
    const hasProcessing = documents.some(
      (doc) => doc.status === "processing" || doc.status === "pending"
    );
    if (!hasProcessing) return;

    const interval = setInterval(() => {
      fetchDocuments();
    }, 3000);

    return () => clearInterval(interval);
  }, [documents]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
      const res = await fetch(`http://localhost:8000/documents/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Delete failed");
      
      // Update state
      setDocuments((prev) => prev.filter((doc) => doc.id !== id));
      
      // If deleted active document, redirect home
      if (activeId === id) {
        router.push("/");
      }
    } catch (err) {
      alert("Failed to delete document");
    }
  };

  const handleSelect = (id: string) => {
    router.push(`/documents/${id}`);
  };

  return (
    <div className="w-80 border-r border-zinc-800 bg-zinc-950 flex flex-col h-screen text-zinc-200 shrink-0">
      {/* Brand Header */}
      <div className="p-6 border-b border-zinc-800 flex items-center justify-between">
        <div className="flex items-center gap-3 cursor-pointer select-none group" onClick={() => router.push("/")}>
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-lg shadow-lg shadow-indigo-500/25 group-hover:scale-105 transition-transform duration-200">
            🧠
          </div>
          <div>
            <h1 className="font-bold text-white leading-tight bg-gradient-to-r from-zinc-100 to-zinc-300 bg-clip-text text-transparent group-hover:from-white group-hover:to-zinc-200 transition-all duration-200">DocuMind</h1>
            <p className="text-[10px] text-zinc-550 font-semibold tracking-wider uppercase">Document Intelligence</p>
          </div>
        </div>
      </div>

      {/* Action Button */}
      <div className="p-4">
        <button
          onClick={() => router.push("/")}
          className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-550 hover:to-indigo-650 hover:shadow-indigo-500/25 active:scale-[0.98] text-white rounded-xl py-2.5 px-4 font-semibold transition-all duration-300 text-sm shadow-md cursor-pointer select-none"
        >
          <Plus size={15} className="stroke-[2.5]" />
          Upload Document
        </button>
      </div>

      {/* History List */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        <div className="text-[10px] font-bold text-zinc-500 px-3 mb-3 tracking-wider uppercase select-none">
          Recent Documents
        </div>

        {loading && (
          <div className="flex flex-col items-center justify-center py-12 text-zinc-500 gap-2">
            <Loader2 className="animate-spin text-indigo-500" size={20} />
            <span className="text-xs">Loading history...</span>
          </div>
        )}

        {!loading && error && (
          <div className="text-center py-6 text-zinc-500 text-xs px-4">
            {error}
          </div>
        )}

        {!loading && !error && documents.length === 0 && (
          <div className="text-center py-12 text-zinc-650 text-xs px-4 italic">
            No documents uploaded yet.
          </div>
        )}

        {!loading &&
          documents.map((doc) => {
            const isActive = doc.id === activeId;
            return (
              <div
                key={doc.id}
                onClick={() => handleSelect(doc.id)}
                className={`relative group flex items-center justify-between p-3 rounded-xl cursor-pointer transition-all duration-300 ${
                  isActive
                    ? "bg-zinc-800/80 border border-zinc-700/50 text-white shadow-md shadow-black/20"
                    : "hover:bg-zinc-900/40 text-zinc-400 hover:text-zinc-200 border border-transparent"
                }`}
              >
                {isActive && (
                  <span className="absolute left-0 top-3 bottom-3 w-0.5 bg-indigo-500 rounded-r" />
                )}

                <div className="flex items-center gap-3 overflow-hidden">
                  <FileText
                    className={isActive ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-400"}
                    size={16}
                  />
                  <div className="flex flex-col text-left overflow-hidden">
                    <span className="text-sm font-medium truncate pr-1">
                      {doc.filename}
                    </span>
                    <span className="text-[9px] text-zinc-500 font-medium font-mono uppercase tracking-wide">
                      {doc.language ? doc.language.toUpperCase() : "DETECTING..."}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {/* Status indicator */}
                  {doc.status === "processing" || doc.status === "pending" ? (
                    <Loader2 className="animate-spin text-amber-500" size={13} />
                  ) : doc.status === "failed" ? (
                    <AlertCircle className="text-red-500" size={13} />
                  ) : (
                    <CheckCircle className="text-emerald-500 opacity-70 group-hover:opacity-100" size={13} />
                  )}

                  <button
                    onClick={(e) => handleDelete(e, doc.id)}
                    className="p-1 rounded text-zinc-650 hover:text-red-400 hover:bg-zinc-800 transition duration-150 cursor-pointer opacity-0 group-hover:opacity-100"
                    title="Delete document"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}
