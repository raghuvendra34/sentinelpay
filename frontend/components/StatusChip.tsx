const STYLES: Record<string, { label: string; className: string }> = {
  COMPLETED: { label: "Completed", className: "bg-teal-soft text-teal" },
  FLAGGED: { label: "Flagged", className: "bg-flag-soft text-flag" },
  DISPUTE_CREDITED: { label: "Credited back", className: "bg-credit-soft text-credit" },
  DISPUTE_ESCALATED: { label: "With ops", className: "bg-debit-soft text-debit" },
  REVIEWING: { label: "Agent reviewing", className: "bg-flag-soft text-flag" },
};

export function StatusChip({ status, reviewing }: { status: string; reviewing?: boolean }) {
  const key = reviewing ? "REVIEWING" : status;
  const style = STYLES[key] ?? { label: status, className: "bg-paper text-muted" };
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${style.className}`}>
      {style.label}
    </span>
  );
}
