"use client";

import { Flag } from "lucide-react";
import { StatusChip } from "./StatusChip";
import { formatCents, formatTime, prettyCategory } from "@/lib/format";
import type { Tx } from "@/lib/types";

type Props = {
  txs: Tx[];
  selectedId: string | null;
  queued: Set<string>;
  fresh: Set<string>;
  onSelect: (txId: string) => void;
  onRaiseDispute: (txId: string) => void;
};

/** The journal: each transfer posts one debit (left) and one credit (right) across a double rule. */
export function LedgerFeed({ txs, selectedId, queued, fresh, onSelect, onRaiseDispute }: Props) {
  return (
    <section className="journal" aria-labelledby="feed-title">
      <div className="flex items-baseline justify-between px-5 pb-3 pt-4">
        <h2 id="feed-title" className="rail-title">Live ledger feed</h2>
        <p className="text-xs text-muted">Refreshes every 3 seconds</p>
      </div>

      <div className="hidden border-b-4 border-double border-ink/50 text-sm font-medium md:flex">
        <div className="w-24 px-5 pb-2 text-muted">Time</div>
        <div className="flex-1 px-3 pb-2 text-debit">Debit</div>
        <div className="double-rule-x flex-1 px-3 pb-2 text-credit">Credit</div>
        <div className="w-40 px-3 pb-2 text-muted">Status</div>
      </div>

      {txs.length === 0 ? (
        <p className="px-5 py-12 text-sm text-muted">The journal is empty. Send a transfer from the simulator to post the first entry.</p>
      ) : (
        <ul>
          {txs.map((tx) => {
            const reviewing = queued.has(tx.tx_id) && !tx.dispute;
            const selected = tx.tx_id === selectedId;
            const canDispute = tx.status === "COMPLETED" && !reviewing;
            const flagged = tx.status === "FLAGGED";
            return (
              <li
                key={tx.tx_id}
                className={`flex flex-col border-b border-rule border-l-4 last:border-b-0 md:flex-row md:items-stretch ${
                  selected ? "border-l-teal bg-teal-soft" : flagged ? "border-l-flag" : "border-l-transparent"
                } ${fresh.has(tx.tx_id) ? "animate-post" : ""}`}
              >
                <button
                  type="button"
                  onClick={() => onSelect(tx.tx_id)}
                  className="flex flex-1 flex-col text-left md:flex-row"
                  aria-pressed={selected}
                >
                  <span className="px-4 py-3 text-sm text-muted md:w-24 md:px-4">
                    {formatTime(tx.created_at)}
                    <span className="block text-xs">{prettyCategory(tx.merchant_cat)}</span>
                  </span>
                  <span className="flex-1 px-4 py-1 md:px-3 md:py-3">
                    <span className="block text-sm">{tx.sender_name}</span>
                    <span className="money block text-lg font-semibold text-debit">{formatCents(tx.amount_cents)}</span>
                  </span>
                  <span className="double-rule-x flex-1 px-4 py-1 md:px-3 md:py-3">
                    <span className="block text-sm">{tx.receiver_name}</span>
                    <span className="money block text-lg font-semibold text-credit">{formatCents(tx.amount_cents)}</span>
                  </span>
                </button>
                <div className="flex items-center justify-between gap-2 px-4 pb-3 md:w-40 md:flex-col md:items-start md:justify-center md:px-3 md:py-3">
                  <StatusChip status={tx.status} reviewing={reviewing} />
                  {canDispute && (
                    <button type="button" className="btn-quiet !px-3 !py-1 text-xs" onClick={() => onRaiseDispute(tx.tx_id)}>
                      <Flag size={13} aria-hidden /> Raise dispute
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
