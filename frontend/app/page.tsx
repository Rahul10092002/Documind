"use client";

import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import UploadZone from "@/components/UploadZone";

export default function Home() {
  const router = useRouter();

  const handleUploadSuccess = (id: string) => {
    router.push(`/documents/${id}`);
  };

  return (
    <div className="flex h-screen w-screen bg-zinc-950 overflow-hidden text-zinc-100 font-sans">
      {/* Sidebar history */}
      <Sidebar />

      {/* Main workspace (upload zone empty state) */}
      <div className="flex-1 flex items-center justify-center p-6 md:p-12 overflow-y-auto">
        <UploadZone onUploadSuccess={handleUploadSuccess} />
      </div>
    </div>
  );
}
