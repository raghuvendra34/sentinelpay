import type { History, TransferResult } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const TOKEN = process.env.NEXT_PUBLIC_DEMO_JWT ?? "";

const authHeaders = (): Record<string, string> => ({
  "Content-Type": "application/json",
  Authorization: `Bearer ${TOKEN}`,
});

export async function postTransfer(
  body: { sender_id: string; receiver_id: string; amount_cents: number; merchant_cat: string },
  idempotencyKey: string,
): Promise<TransferResult> {
  const res = await fetch(`${BASE}/api/v1/transfers`, {
    method: "POST",
    headers: { ...authHeaders(), "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });
  return {
    httpStatus: res.status,
    replayed: res.headers.get("Idempotency-Replayed") === "true",
    body: await res.json().catch(() => ({})),
  };
}

export async function fetchHistory(accountId: string): Promise<History> {
  const res = await fetch(`${BASE}/api/v1/accounts/${accountId}/history`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function postDispute(txId: string, reason: string): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/disputes`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ tx_id: txId, reason }),
  });
  if (res.status !== 202) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
}
