import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

export interface DocumentData {
  id: string;
  filename: string;
  upload_date: string;
  language: string | null;
  status: "pending" | "processing" | "completed" | "failed";
  detailed_status?: string | null;
  raw_text: string | null;
}

export interface ExtractedEntities {
  parties?: string[];
  dates?: string[];
  amounts?: string[];
  document_type?: string;
  suggested_questions?: string[];
  [key: string]: any;
}

export interface RiskFlag {
  clause: string;
  reason: string;
  level?: "high" | "medium" | "low";
}

export interface SourceInfo {
  page_num?: number;
  snippet?: string;
  [key: string]: any;
}

export interface AnalysisData {
  document_id: string;
  extracted_entities: ExtractedEntities;
  risk_flags: RiskFlag[];
  risk_obligation_summary: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  confidence?: "high" | "medium" | "low";
  sources?: SourceInfo[];
}

export const apiSlice = createApi({
  reducerPath: "api",
  baseQuery: fetchBaseQuery({ baseUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000" }),
  tagTypes: ["Document", "Analysis", "Chat"],
  endpoints: (builder) => ({
    getDocuments: builder.query<DocumentData[], void>({
      query: () => "/documents",
      providesTags: (result) =>
        result
          ? [
              ...result.map(({ id }) => ({ type: "Document" as const, id })),
              { type: "Document" as const, id: "LIST" },
            ]
          : [{ type: "Document" as const, id: "LIST" }],
    }),
    getDocument: builder.query<DocumentData, string>({
      query: (id) => `/documents/${id}`,
      providesTags: (result, error, id) => [{ type: "Document", id }],
    }),
    getDocumentAnalysis: builder.query<AnalysisData, string>({
      query: (id) => `/documents/${id}/analysis`,
      providesTags: (result, error, id) => [{ type: "Analysis", id }],
    }),
    uploadDocument: builder.mutation<{ id: string }, FormData>({
      query: (formData) => ({
        url: "/documents/upload",
        method: "POST",
        body: formData,
      }),
      transformErrorResponse: (response: any) => response.data?.detail || response.error || "Upload failed",
      invalidatesTags: [{ type: "Document", id: "LIST" }],
    }),
    deleteDocument: builder.mutation<void, string>({
      query: (id) => ({
        url: `/documents/${id}`,
        method: "DELETE",
      }),
      transformErrorResponse: (response: any) => response.data?.detail || "Delete failed",
      invalidatesTags: (result, error, id) => [
        { type: "Document", id },
        { type: "Document", id: "LIST" },
      ],
    }),
    reanalyzeDocument: builder.mutation<AnalysisData, string>({
      query: (id) => ({
        url: `/documents/${id}/analysis`,
        method: "PUT",
      }),
      transformErrorResponse: (response: any) => response.data?.detail || "Reanalysis failed",
      invalidatesTags: (result, error, id) => [
        { type: "Analysis", id },
        { type: "Document", id },
        { type: "Document", id: "LIST" },
      ],
    }),
    getDocumentChat: builder.query<ChatMessage[], string>({
      query: (id) => `/documents/${id}/chat`,
      providesTags: (result, error, id) => [{ type: "Chat", id }],
    }),
    askDocumentQuestion: builder.mutation<
      { answer: string; confidence?: "high" | "medium" | "low"; sources?: SourceInfo[]; suggested_questions?: string[] },
      { id: string; question: string }
    >({
      query: ({ id, question }) => ({
        url: `/documents/${id}/chat`,
        method: "POST",
        body: { question },
      }),
      transformErrorResponse: (response: any) => response.data?.detail || "Failed to get answer",
      invalidatesTags: (result, error, { id }) => [{ type: "Chat", id }],
    }),
    exportDocumentPDF: builder.query<Blob, string>({
      query: (id) => ({
        url: `/documents/${id}/export`,
        responseHandler: (response) => response.blob(),
      }),
    }),
  }),
});

export const {
  useGetDocumentsQuery,
  useGetDocumentQuery,
  useGetDocumentAnalysisQuery,
  useUploadDocumentMutation,
  useDeleteDocumentMutation,
  useReanalyzeDocumentMutation,
  useGetDocumentChatQuery,
  useAskDocumentQuestionMutation,
  useLazyExportDocumentPDFQuery,
} = apiSlice;
