"use client";

import { cn } from "@/lib/utils";

export interface PdfViewerProps {
  url: string | null;
  pageNumber: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function PdfViewer({ url, pageNumber, className }: PdfViewerProps) {
  const proxiedUrl = url
    ? `/api/pdf?url=${encodeURIComponent(url)}#page=${pageNumber}`
    : null;

  if (!proxiedUrl) {
    return (
      <div className="flex-1 flex items-center justify-center bg-bg-reader">
        <p className="text-body text-text-muted">No PDF available</p>
      </div>
    );
  }

  return (
    <div className={cn("flex-1 flex flex-col bg-bg-reader overflow-hidden", className)}>
      <iframe
        src={proxiedUrl}
        className="w-full h-full border-0"
        title="PDF viewer"
      />
    </div>
  );
}
