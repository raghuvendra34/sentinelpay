const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export const formatCents = (cents: number) => usd.format(cents / 100);

export const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const prettyCategory = (value: string) =>
  value.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const ACCOUNTS = [
  process.env.NEXT_PUBLIC_ACCOUNT_A ?? "11111111-1111-4111-8111-111111111111",
  process.env.NEXT_PUBLIC_ACCOUNT_B ?? "22222222-2222-4222-8222-222222222222",
];

export const MERCHANT_CATEGORIES = ["P2P_TRANSFER", "GROCERIES", "ELECTRONICS", "TRAVEL", "DINING", "UTILITIES"];

export const ERROR_COPY: Record<string, string> = {
  INSUFFICIENT_FUNDS: "The sending account does not have enough balance.",
  RATE_LIMIT_EXCEEDED: "More than 10 requests in 60 seconds for this account. Wait a minute and retry.",
  SAME_ACCOUNT: "Choose two different accounts.",
  MISSING_TOKEN: "No token configured. Set NEXT_PUBLIC_DEMO_JWT.",
  INVALID_TOKEN: "The token was rejected. Mint a new one with infra/mint_token.py.",
  LEDGER_UNAVAILABLE: "The ledger service is not reachable.",
};
