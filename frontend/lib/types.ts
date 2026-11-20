export type TraceStep = {
  ts: string;
  node: "retrieve_context" | "evaluate_policy" | "execute_resolution" | string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
};

export type Dispute = {
  dispute_id: string;
  reason: string;
  decision: "AUTO_CREDIT_APPROVED" | "ESCALATED_TO_OPS" | string;
  confidence: number;
  reasoning_trace: { steps: TraceStep[]; final?: Record<string, unknown> };
  resolved_at: string;
};

export type Tx = {
  tx_id: string;
  sender_id: string;
  sender_name: string;
  receiver_id: string;
  receiver_name: string;
  amount_cents: number;
  merchant_cat: string;
  status: string;
  risk_score: number | null;
  created_at: string;
  dispute: Dispute | null;
};

export type History = {
  account_id: string;
  owner_name: string;
  balance_cents: number;
  transactions: Tx[];
};

export type TransferResult = {
  httpStatus: number;
  replayed: boolean;
  body: { tx_id?: string; detail?: string } & Record<string, unknown>;
};
