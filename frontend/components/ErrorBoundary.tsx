"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertCircle } from "lucide-react";

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export default class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] w-full p-8 text-center bg-zinc-950 text-white animate-fade-in rounded-xl border border-zinc-800">
          <div className="h-16 w-16 rounded-2xl bg-red-500/10 text-red-400 border border-red-500/25 flex items-center justify-center mb-6 shadow-lg shadow-red-500/5">
            <AlertCircle size={32} />
          </div>
          <h2 className="text-xl font-bold mb-3 tracking-tight">Something went wrong</h2>
          <p className="text-sm text-zinc-400 max-w-md mx-auto mb-8 leading-relaxed">
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-6 py-2.5 text-sm font-semibold transition cursor-pointer shadow-md focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
