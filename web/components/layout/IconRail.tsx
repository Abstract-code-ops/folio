"use client";

import { Brain, MessageSquare, FileText, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

export type TabId = "coverage" | "chat" | "notes";

const TABS: { id: TabId; icon: typeof Brain; label: string }[] = [
  { id: "coverage", icon: Brain, label: "Coverage" },
  { id: "chat", icon: MessageSquare, label: "Chat" },
  { id: "notes", icon: FileText, label: "Notes" },
];

export function IconRail({
  activeTab,
  onTabChange,
  onSettings,
}: {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  onSettings: () => void;
}) {
  return (
    <nav className="w-rail flex flex-col items-center py-3 gap-2 bg-bg-surface border-r border-border-subtle shrink-0">
      {/* Logo */}
      <div className="mb-4 mt-1">
        <div className="w-7 h-7 rounded-lg bg-accent flex items-center justify-center">
          <span className="text-white font-heading text-body-sm font-bold">F</span>
        </div>
      </div>

      {/* Tab icons */}
      {TABS.map(({ id, icon: Icon, label }) => (
        <button
          key={id}
          onClick={() => onTabChange(id)}
          title={label}
          className={cn(
            "w-9 h-9 rounded-lg flex items-center justify-center transition-colors",
            activeTab === id
              ? "bg-accent/15 text-accent"
              : "text-text-subtle hover:text-text-muted hover:bg-bg-elevated"
          )}
        >
          <Icon className="h-4 w-4" strokeWidth={1.5} />
        </button>
      ))}

      {/* Spacer + settings */}
      <div className="flex-1" />
      <button
        onClick={onSettings}
        title="Settings"
        className="w-9 h-9 rounded-lg flex items-center justify-center text-text-subtle hover:text-text-muted hover:bg-bg-elevated transition-colors"
      >
        <Settings className="h-4 w-4" strokeWidth={1.5} />
      </button>
    </nav>
  );
}
