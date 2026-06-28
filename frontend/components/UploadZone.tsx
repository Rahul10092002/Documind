"use client";

import { useState, useRef, useEffect } from "react";
import { UploadCloud, AlertCircle, Loader2 } from "lucide-react";
import { useUploadDocumentMutation } from "@/store/apiSlice";
import { UPLOAD_PROCESSING_STEPS } from "@/lib/constants";

interface UploadZoneProps {
  onUploadSuccess: (id: string) => void;
}



export default function UploadZone({ onUploadSuccess }: UploadZoneProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploadDocument] = useUploadDocumentMutation();

  useEffect(() => {
    if (!processing) {
      setActiveStep(0);
      return;
    }
    const interval = setInterval(() => {
      setActiveStep((prev) => (prev < UPLOAD_PROCESSING_STEPS.length - 1 ? prev + 1 : prev));
    }, 2000);
    return () => clearInterval(interval);
  }, [processing]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      await uploadFile(file);
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      await uploadFile(file);
      // Reset the input so the same file can be selected again if needed
      e.target.value = "";
    }
  };

  const onButtonClick = (e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation();
    }
    if (error) {
      setError(null);
    }
    fileInputRef.current?.click();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      if (error) {
        setError(null);
      } else {
        fileInputRef.current?.click();
      }
    }
  };

  const uploadFile = async (file: File) => {
    if (file.type !== "application/pdf" && !file.name.endsWith(".pdf")) {
      setError("Please upload a PDF document only.");
      return;
    }

    setUploading(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      setUploading(false);
      setProcessing(true);
      const data = await uploadDocument(formData).unwrap();
      onUploadSuccess(data.id);
    } catch (err: any) {
      console.error(err);
      setError(err.data?.detail || err.message || "An error occurred during upload.");
      setUploading(false);
    } finally {
      setUploading(false);
      setProcessing(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[500px] w-full max-w-2xl px-6 py-12 mx-auto animate-fade-in">
      <div className="text-center mb-10 select-none">
        <h2 className="text-3xl font-extrabold text-white tracking-tight sm:text-4xl bg-gradient-to-r from-white via-zinc-100 to-zinc-400 bg-clip-text text-transparent">
          Upload & Analyze Documents
        </h2>
        <p className="mt-4 text-zinc-400 text-sm max-w-md mx-auto leading-relaxed">
          Upload legal documents, agreements, or bank circulars and let AI extract key details, find liabilities, and chat with them.
        </p>
      </div>

      <div
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={onButtonClick}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-label="Upload PDF Document Drag Zone"
        className={`w-full rounded-2xl border-2 border-dashed flex flex-col items-center justify-center gap-4 cursor-pointer transition-all duration-300 relative overflow-hidden focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none ${
          error
            ? "border-red-900 bg-red-950/15 hover:border-red-800"
            : isDragActive
            ? "border-indigo-500 bg-indigo-500/10 scale-[1.02] shadow-lg shadow-indigo-500/5"
            : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-700 hover:bg-zinc-900/20"
        } ${uploading || processing ? "pointer-events-none p-8 py-10 min-h-80" : "p-6 py-12 h-80"}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleChange}
        />

        {/* Ambient background glow */}
        <div className="absolute inset-0 -z-10 bg-gradient-to-tr from-indigo-500/5 via-transparent to-purple-500/5 opacity-50" />

        {error ? (
          <div className="flex flex-col items-center gap-4 text-center px-6 w-full max-w-md animate-scale-up select-none">
            <div className="h-14 w-14 rounded-2xl bg-red-500/10 text-red-400 border border-red-500/25 flex items-center justify-center shadow-lg">
              <AlertCircle size={28} />
            </div>
            <div className="space-y-1">
              <h4 className="text-base font-bold text-white">Upload Failed</h4>
              <p className="text-xs text-zinc-400 leading-relaxed">
                {error}
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setError(null);
                fileInputRef.current?.click();
              }}
              className="mt-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 hover:border-zinc-600 rounded-xl px-4 py-2 text-xs font-semibold transition cursor-pointer select-none active:scale-95 shadow-md focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:outline-none"
            >
              Try Again
            </button>
          </div>
        ) : uploading || processing ? (
          <div className="flex flex-col items-center gap-6 text-center px-6 w-full max-w-md">
            <Loader2 className="animate-spin text-indigo-500" size={44} />
            <div className="space-y-1">
              <h4 className="text-lg font-bold text-white">
                {uploading ? "Uploading PDF..." : "Analyzing Document..."}
              </h4>
              <p className="text-xs text-zinc-500">
                {uploading ? "Sending document to secure analyzer..." : "Please wait while we process the document"}
              </p>
            </div>

            {/* Visual step progress list */}
            {processing && (
              <div aria-live="polite" className="w-full bg-zinc-950/60 border border-zinc-800/80 p-5 rounded-xl text-left space-y-3 mt-2 animate-scale-up">
                {UPLOAD_PROCESSING_STEPS.map((stepText, idx) => {
                  const isDone = activeStep > idx;
                  const isActive = activeStep === idx;
                  return (
                    <div key={idx} className={`flex items-center gap-3 text-xs transition-colors duration-300 ${isDone ? "text-indigo-400" : isActive ? "text-white animate-pulse" : "text-zinc-500"}`}>
                      {isDone ? (
                        <span className="h-4.5 w-4.5 bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 flex items-center justify-center font-bold text-[9px] rounded-full shrink-0">✓</span>
                      ) : isActive ? (
                        <Loader2 className="animate-spin text-indigo-400 shrink-0" size={13} />
                      ) : (
                        <span className="h-4.5 w-4.5 bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-500 text-[9px] rounded-full shrink-0">{idx + 1}</span>
                      )}
                      <span className={isActive ? "font-medium" : "font-normal"}>{stepText}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-5 text-center px-6 group select-none">
            <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-indigo-500/10 to-purple-500/10 text-indigo-400 border border-indigo-500/20 flex items-center justify-center shadow-lg group-hover:scale-105 group-hover:shadow-indigo-500/10 transition-all duration-300">
              <UploadCloud size={30} className="group-hover:-translate-y-0.5 transition-transform duration-300" />
            </div>
            <div className="space-y-2">
              <p className="text-base font-semibold text-zinc-200">
                Drag and drop your PDF here, or{" "}
                <span className="text-indigo-400 hover:text-indigo-300 hover:underline font-medium transition-colors cursor-pointer">browse</span>
              </p>
              <p className="text-xs text-zinc-400 max-w-sm leading-relaxed">
                Supports PDF files up to 10MB. Works with Native & Scanned documents in Hindi, English, and Hinglish.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

