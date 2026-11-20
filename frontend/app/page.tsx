"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LedgerFeed } from "@/components/LedgerFeed";
import { ReasoningInspector } from "@/components/ReasoningInspector";
import { TransferSimulator } from "@/components/TransferSimulator";
import { fetchHistory, postDispute } from "@/lib/api";
import { ACCOUNTS, ERROR_COPY, formatCents } from "@/lib/format";
import type { History, Tx } from "@/lib/types";

export default function ConsolePage() {
  const [histories, setHistories] = useState<Record<string, History>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [raising, setRaising] = useState(false);
  const [queued, setQueued] = useState<Set<string>>(new Set());
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [error, setError] = useState("");
  const known = useRef<Set<string> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const results = await Promise.all(ACCOUNTS.map(fetchHistory));
      setHistories(Object.fromEntries(results.map((h) => [h.account_id, h])));
      setError("");

      // The one motion in the console: a row that was not there before inks in once.
      const ids = results.flatMap((h) => h.transactions.map((t) => t.tx_id));
      if (known.current === null) {
        known.current = new Set(ids);
      } else {
        const seen = known.current;
        const added = ids.filter((id) => !seen.has(id));
        if (added.length) {
          added.forEach((id) => seen.add(id));
          setFresh((prev) => new Set([...prev, ...added]));
          setTimeout(
            () => setFresh((prev) => new Set([...prev].filter((id) => !added.includes(id)))),
            2000,
          );
        }
      }
    } catch (e) {
      const detail = e instanceof Error ? e.message : "";
      setError(ERROR_COPY[detail] ?? "Could not load the ledger. Check that the gateway is running.");
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh]);

  // Merge both accounts' histories, de-duplicated by transaction, newest first.
  const txs = useMemo<Tx[]>(() => {
    const byId = new Map<string, Tx>();
    Object.values(histories).forEach((h) => h.transactions.forEach((t) => byId.set(t.tx_id, t)));
    return [...byId.values()].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 20);
  }, [histories]);

  // FLAGGED transfers are queued for the agent by the gateway; show them as reviewing until resolved.
  const reviewingIds = useMemo(() => {
    const ids = new Set(queued);
    txs.forEach((t) => t.status === "FLAGGED" && !t.dispute && ids.add(t.tx_id));
    return ids;
  }, [queued, txs]);

  const selected = txs.find((t) => t.tx_id === selectedId) ?? null;
  const accountOptions = ACCOUNTS.map((id) => ({
    id,
    name: histories[id]?.owner_name ?? "Loading",
    balance_cents: histories[id]?.balance_cents ?? 0,
  }));

  async function raiseDispute(txId: string, reason: string) {
    await postDispute(txId, reason);
    setQueued((prev) => new Set(prev).add(txId));
    setRaising(false);
    refresh();
  }

  return (
    <main className="mx-auto max-w-[1500px] px-4 py-8 sm:px-8">
      <header className="mb-10">
        <h1 className="font-serif text-4xl tracking-tight">SentinelPay console</h1>
        <p className="mt-1 max-w-prose text-sm text-muted">
          Send money, watch it post to the ledger, and see how the dispute agent decides.
        </p>

        {/* A T-account: the two seeded accounts, balances on either side of the double rule. */}
        <dl className="mt-6 grid max-w-2xl grid-cols-2 border-t-2 border-ink">
          {accountOptions.map((a, i) => (
            <div key={a.id} className={`pt-3 ${i === 1 ? "double-rule-x pl-6" : "pr-6"}`}>
              <dt className="text-sm text-muted">{a.name}</dt>
              <dd className="money text-4xl font-semibold">{formatCents(a.balance_cents)}</dd>
            </div>
          ))}
        </dl>
      </header>

      {error && (
        <p role="alert" className="mb-6 rounded-sm border-l-4 border-debit bg-debit-soft px-4 py-3 text-sm">
          {error}
        </p>
      )}

      <div className="grid gap-x-8 gap-y-10 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)_360px]">
        <TransferSimulator accounts={accountOptions} onSent={refresh} />
        <LedgerFeed
          txs={txs}
          selectedId={selectedId}
          queued={reviewingIds}
          fresh={fresh}
          onSelect={(id) => {
            setSelectedId(id);
            setRaising(false);
          }}
          onRaiseDispute={(id) => {
            setSelectedId(id);
            setRaising(true);
          }}
        />
        <div className="lg:col-span-2 xl:col-span-1">
          <ReasoningInspector
            tx={selected}
            reviewing={selected ? reviewingIds.has(selected.tx_id) && !selected.dispute : false}
            raising={raising}
            onSubmitDispute={raiseDispute}
            onCancelRaise={() => setRaising(false)}
          />
        </div>
      </div>
    </main>
  );
}
