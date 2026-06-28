"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import UploadZone from "@/components/UploadZone";
import { Menu } from "lucide-react";

export default function Home() {
  const router = useRouter();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const handleUploadSuccess = (id: string) => {
    router.push(`/documents/${id}`);
  };

  return (
    <div className="flex h-screen w-screen bg-zinc-950 overflow-hidden text-zinc-100 font-sans">
      {/* Mobile sidebar toggle floating at top left */}
      <button
        onClick={() => setIsSidebarOpen(true)}
        className="md:hidden absolute top-4 left-4 z-30 p-2 text-zinc-400 hover:text-white bg-zinc-900/80 border border-zinc-800 rounded-xl transition cursor-pointer focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
        title="Open menu"
        aria-label="Open navigation menu"
      >
        <Menu size={16} />
      </button>

      {/* Sidebar history */}
      <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />

      {/* Main workspace (upload zone empty state) */}
      <div className="flex-1 flex items-center justify-center p-6 md:p-12 overflow-y-auto">
        <UploadZone onUploadSuccess={handleUploadSuccess} />
      </div>
    </div>
  );
}
