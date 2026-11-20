"use client";

import { Copy, Send } from "lucide-react";
import { useState } from "react";
import { postTransfer } from "@/lib/api";
import { ERROR_COPY, MERCHANT_CATEGORIES, formatCents } from "@/lib/format";
import type { TransferResult } from "@/lib/types";

type AccountOption = { id: string; name: string; balance_cents: number };
type LogEntry = { id: number; label: string; tone: "ok" | "replay" | "error"; text: string };

export function TransferSimulator({ accounts, onSent }: { accounts: AccountOption[]; onSent: () => void }) {
  const [from, setFrom] = useState(0);
  const [amount, setAmount] = useState("25.00");
  const [category, setCategory] = useState(MERCHANT_CATEGORIES[0]);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<LogEntry[]>([]);

  const sender = accounts[from];
  const receiver = accounts[from === 0 ? 1 : 0];
  const cents = Math.round(parseFloat(amount) * 100);
  const validAmount = Number.isFinite(cents) && cents > 0;
  const willFlag = validAmount && cents >= 50_000;

  const describe = (r: TransferResult): Omit<LogEntry, "id" | "label"> => {
    if (r.httpStatus === 201) return { tone: "ok", text: `201 created, tx ${r.body.tx_id?.slice(0, 8)}` };
    if (r.httpStatus === 200 && r.replayed)
      return { tone: "replay", text: `200 replayed, same tx ${r.body.tx_id?.slice(0, 8)}, no second charge` };
    const detail = String(r.body.detail ?? "");
    return { tone: "error", text: `${r.httpStatus} ${ERROR_COPY[detail] ?? detail}` };
  };

  const push = (entries: Omit<LogEntry, "id">[]) =>
    setLog((prev) => [...entries.map((e, i) => ({ ...e, id: Date.now() + i })), ...prev].slice(0, 6));

  const body = () => ({
    sender_id: sender.id,
    receiver_id: receiver.id,
    amount_cents: cents,
    merchant_cat: category,
  });

  async function send(duplicate: boolean) {
    if (!validAmount || busy) return;
    setBusy(true);
    const key = crypto.randomUUID();
    try {
      const first = await postTransfer(body(), key);
      const entries = [{ label: duplicate ? "First call" : "Transfer", ...describe(first) }];
      if (duplicate) {
        const second = await postTransfer(body(), key); // identical Idempotency-Key
        entries.push({ label: "Retry, same key", ...describe(second) });
      }
      push(entries.reverse());
    } catch {
      push([{ label: "Network", tone: "error", text: "The gateway did not respond. Check that it is running." }]);
    } finally {
      setBusy(false);
      onSent();
    }
  }

  return (
    <section className="rail" aria-labelledby="sim-title">
      <h2 id="sim-title" className="rail-title">Transfer simulator</h2>
      <p className="mt-1 text-sm text-muted">Move money between the two seeded accounts.</p>

      <div className="mt-4 space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">From</span>
          <select className="field" value={from} onChange={(e) => setFrom(Number(e.target.value))}>
            {accounts.map((a, i) => (
              <option key={a.id} value={i}>
                {a.name} ({formatCents(a.balance_cents)})
              </option>
            ))}
          </select>
        </label>
        <p className="text-sm text-muted">
          To <span className="font-medium text-ink">{receiver?.name}</span>
        </p>

        <label className="block text-sm">
          <span className="mb-1 block font-medium">Amount in dollars</span>
          <input className="field" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        {willFlag && (
          <p className="rounded-sm bg-flag-soft px-3 py-2 text-sm text-flag">
            $500 or more is flagged and sent to the dispute agent automatically.
          </p>
        )}

        <label className="block text-sm">
          <span className="mb-1 block font-medium">Merchant category</span>
          <select className="field" value={category} onChange={(e) => setCategory(e.target.value)}>
            {MERCHANT_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c.replace(/_/g, " ").toLowerCase()}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-5 flex flex-col gap-2">
        <button className="btn-primary" disabled={!validAmount || busy || !sender} onClick={() => send(false)}>
          <Send size={16} aria-hidden /> Send transfer
        </button>
        <button className="btn-quiet" disabled={!validAmount || busy || !sender} onClick={() => send(true)}>
          <Copy size={16} aria-hidden /> Test duplicate retry
        </button>
      </div>

      <ul className="mt-5 space-y-2" aria-live="polite">
        {log.length === 0 && (
          <li className="text-sm text-muted">Send a transfer, or fire the same Idempotency-Key twice to see only one charge.</li>
        )}
        {log.map((e) => (
          <li
            key={e.id}
            className={`rounded-sm border-l-4 px-3 py-2 text-sm ${
              e.tone === "ok"
                ? "border-credit bg-credit-soft"
                : e.tone === "replay"
                  ? "border-teal bg-teal-soft"
                  : "border-debit bg-debit-soft"
            }`}
          >
            <span className="font-medium">{e.label}: </span>
            {e.text}
          </li>
        ))}
      </ul>
    </section>
  );
}
