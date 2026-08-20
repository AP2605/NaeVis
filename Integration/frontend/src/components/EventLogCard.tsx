"use client";

import React from "react";
import { Terminal } from "lucide-react";
import { LogEntry } from "../hooks/useTelemetryWebSocket";

interface EventLogCardProps {
  logs: LogEntry[];
  syncStatus?: Record<string, any>;
}

export const EventLogCard: React.FC<EventLogCardProps> = ({ logs, syncStatus }) => {
  // Strip any internal module codes [P1], [P2], [P3] from logs in case backend sends them
  const sanitizeMessage = (msg: string) => {
    return msg
      .replace(/\[P1\]\s*/gi, "Scene: ")
      .replace(/\[P2\]\s*/gi, "Ref: ")
      .replace(/\[P3\]\s*/gi, "Nav: ")
      .replace(/\[P4\]\s*/gi, "Core: ");
  };

  const getLogBadge = (type: LogEntry["type"]) => {
    switch (type) {
      case "warning":
        return <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-ops-warningBg text-ops-warning border border-ops-warning/30 font-semibold">WARN</span>;
      case "error":
        return <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-ops-criticalBg text-ops-critical border border-ops-critical/30 font-semibold">ERR</span>;
      case "event":
        return <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-ops-accentBg text-ops-accent border border-ops-accent/30 font-semibold">EVT</span>;
      default:
        return <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-ops-card text-ops-textDim border border-ops-border font-semibold">INFO</span>;
    }
  };

  return (
    <div className="bg-ops-panel border border-ops-border rounded-lg p-3.5 sm:p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-ops-border pb-2.5">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-ops-accent" />
          <h2 className="font-semibold text-ops-text text-xs tracking-wider uppercase">
            System Event Logs & Diagnostics
          </h2>
        </div>
        {syncStatus && (
          <div className="flex items-center gap-2.5 text-[11px] font-mono text-ops-textDim">
            <span className="bg-ops-subpanel px-1.5 py-0.5 rounded border border-ops-border">
              Analysis: <span className="text-ops-text font-medium">{syncStatus.p1_rate_hz ?? 0} Hz</span>
            </span>
            <span className="bg-ops-subpanel px-1.5 py-0.5 rounded border border-ops-border">
              Ref: <span className="text-ops-text font-medium">{syncStatus.p2_rate_hz ?? 0} Hz</span>
            </span>
            <span className="bg-ops-subpanel px-1.5 py-0.5 rounded border border-ops-border">
              Nav: <span className="text-ops-text font-medium">{syncStatus.p3_rate_hz ?? 0} Hz</span>
            </span>
          </div>
        )}
      </div>

      {/* Terminal log window */}
      <div className="bg-ops-subpanel rounded-md p-2.5 h-44 overflow-y-auto font-mono text-[11px] space-y-1.5 border border-ops-border">
        {logs.length > 0 ? (
          logs.map((log) => {
            let textColor = "text-ops-textMuted";
            if (log.type === "warning") textColor = "text-ops-warning";
            if (log.type === "error") textColor = "text-ops-critical";
            if (log.type === "event") textColor = "text-ops-text";

            return (
              <div key={log.id} className="flex items-start gap-2 leading-relaxed">
                <span className="text-ops-textDim select-none shrink-0 font-sans text-[10px]">
                  {log.time}
                </span>
                <span className="shrink-0">{getLogBadge(log.type)}</span>
                <span className={`${textColor} break-all`}>{sanitizeMessage(log.message)}</span>
              </div>
            );
          })
        ) : (
          <div className="text-ops-textDim italic py-2 text-center">
            No system events recorded yet
          </div>
        )}
      </div>
    </div>
  );
};

