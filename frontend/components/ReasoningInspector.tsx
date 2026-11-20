"use client";

import { Check, X } from "lucide-react";
import { useState } from "react";
import { StatusChip } from "./StatusChip";
import { formatCents, formatTime, prettyCategory } from "@/lib/format";
import type { Tx, TraceStep } from "@/lib/types";

const REASONS = [
  "I was charged twice for the same payment",
  "I do not recognise this merchant",
  "I did not authorise this payment",
];

const NODE_LABEL: Record<string, string> = {
  retrieve_context: "Retrieve context",
  evaluate_policy: "Evaluate policy and risk",
  execute_resolution: "Apply guardrails and resolve",
};

type Props = {
  tx: Tx | null;
  reviewing: boolean;
  raising: boolean;
  onSubmitDispute: (txId: string, reason: string) => Promise<void>;
  onCancelRaise: () => void;
};

export function ReasoningInspector({ tx, reviewing, raising, onSubmitDispute, onCancelRaise }: Props) {
  const [reason, setReason] = useState(REASONS[0]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    if (!tx) return;
    setSending(true);
    setError("");
    try {
      await onSubmitDispute(tx.tx_id, reason);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not raise the dispute.");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="rail" aria-labelledby="insp-title" aria-live="polite">
      <h2 id="insp-title" className="rail-title">Agent reasoning inspector</h2>

      {!tx && <p className="mt-3 text-sm text-muted">Select a transfer to see how the agent handled it.</p>}

      {tx && (
        <>
          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-sm">
              <span className="money text-lg font-semibold">{formatCents(tx.amount_cents)}</span> from {tx.sender_name} to{" "}
              {tx.receiver_name}
            </p>
            <StatusChip status={tx.status} reviewing={reviewing} />
          </div>

          {raising && !tx.dispute && !reviewing && (
            <div className="mt-4 rounded-sm border border-rule bg-white p-3">
              <p className="text-sm font-medium">What went wrong?</p>
              <div className="mt-2 space-y-1.5">
                {REASONS.map((r) => (
                  <label key={r} className="flex cursor-pointer items-start gap-2 text-sm">
                    <input type="radio" name="reason" className="mt-1" checked={reason === r} onChange={() => setReason(r)} />
                    {r}
                  </label>
                ))}
              </div>
              {error && <p className="mt-2 text-sm text-debit">{error}</p>}
              <div className="mt-3 flex gap-2">
                <button className="btn-primary" disabled={sending} onClick={submit}>Raise dispute</button>
                <button className="btn-quiet" onClick={onCancelRaise}>Cancel</button>
              </div>
            </div>
          )}

          {reviewing && (
            <p className="mt-4 rounded-sm bg-flag-soft px-3 py-2 text-sm text-flag">
              The agent is reviewing this transfer. The result appears here within a few seconds.
            </p>
          )}

          {!tx.dispute && !reviewing && !raising && (
            <p className="mt-4 text-sm text-muted">
              No dispute on this transfer. Use Raise dispute on a completed row to send it to the agent.
            </p>
          )}

          {tx.dispute && <Resolution tx={tx} />}
        </>
      )}
    </section>
  );
}

function Resolution({ tx }: { tx: Tx }) {
  const d = tx.dispute!;
  const steps = d.reasoning_trace?.steps ?? [];
  const final = steps.find((s) => s.node === "execute_resolution");
  const policy = steps.find((s) => s.node === "evaluate_policy");
  const checks = (final?.output?.checks ?? {}) as Record<string, boolean>;
  const risk = Number(policy?.output?.risk_score ?? tx.risk_score ?? 0);
  const approved = d.decision === "AUTO_CREDIT_APPROVED";

  return (
    <div className="mt-4 space-y-4">
      <div className={`rounded-sm px-3 py-3 ${approved ? "bg-credit-soft" : "bg-debit-soft"}`}>
        <p className={`text-sm font-semibold ${approved ? "text-credit" : "text-debit"}`}>
          {approved ? "Provisional credit issued" : "Escalated to operations"}
        </p>
        <p className="mt-0.5 text-xs text-muted">Decision confidence {Math.round(d.confidence * 100)}%</p>
        <p className="mt-2 text-sm">Customer said: {d.reason}</p>
      </div>

      <div>
        <div className="flex items-baseline justify-between text-sm">
          <span className="font-medium">Risk score</span>
          <span className="money text-lg font-semibold">{risk.toFixed(2)}</span>
        </div>
        <div className="relative mt-2 h-2 rounded bg-paper" role="img" aria-label={`Risk ${risk.toFixed(2)} out of 1.00, auto-credit limit 0.35`}>
          <div className="h-2 rounded bg-teal" style={{ width: `${Math.min(risk, 1) * 100}%` }} />
          <div className="absolute -top-1 h-4 w-0.5 bg-ink" style={{ left: "35%" }} />
        </div>
        <p className="mt-1 text-xs text-muted" style={{ paddingLeft: "35%" }}>
          Auto-credit limit 0.35
        </p>
      </div>

      {policy && (
        <p className="text-sm">
          <span className="font-medium">{prettyCategory(String(policy.output.category))}.</span>{" "}
          {String(policy.output.explanation)}
        </p>
      )}

      <ul className="space-y-1 text-sm">
        <CheckRow ok={checks.amount_within_limit} label="Amount is $100 or less" />
        <CheckRow ok={checks.risk_within_limit} label="Risk score is 0.35 or less" />
        <CheckRow ok={checks.no_prior_disputes} label="No earlier disputes" />
      </ul>

      <div>
        <h3 className="text-sm font-semibold">Reasoning trace</h3>
        <ol className="mt-2 space-y-2">
          {steps.map((s, i) => (
            <TraceItem key={i} step={s} />
          ))}
        </ol>
      </div>
    </div>
  );
}

function CheckRow({ ok, label }: { ok: boolean | undefined; label: string }) {
  return (
    <li className="flex items-center gap-2">
      {ok ? <Check size={16} className="text-credit" aria-label="Passed" /> : <X size={16} className="text-debit" aria-label="Failed" />}
      {label}
    </li>
  );
}

function TraceItem({ step }: { step: TraceStep }) {
  return (
    <li className="rounded-sm border border-rule bg-white">
      <details>
        <summary className="flex cursor-pointer items-center justify-between px-3 py-2 text-sm">
          <span className="font-medium">{NODE_LABEL[step.node] ?? step.node}</span>
          <span className="text-xs text-muted">{formatTime(step.ts)}</span>
        </summary>
        <div className="space-y-2 border-t border-rule px-3 py-2">
          <p className="text-xs font-medium text-muted">Input</p>
          <pre className="max-h-48 overflow-auto rounded bg-paper p-2 font-mono text-xs">{JSON.stringify(step.input, null, 2)}</pre>
          <p className="text-xs font-medium text-muted">Output</p>
          <pre className="max-h-48 overflow-auto rounded bg-paper p-2 font-mono text-xs">{JSON.stringify(step.output, null, 2)}</pre>
        </div>
      </details>
    </li>
  );
}
