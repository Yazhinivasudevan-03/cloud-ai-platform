export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatMb(valueMb: number): string {
  if (valueMb >= 1024) return `${(valueMb / 1024).toFixed(1)} GB`;
  return `${valueMb.toFixed(0)} MB`;
}

export function formatKbps(valueKbps: number): string {
  if (valueKbps >= 1024) return `${(valueKbps / 1024).toFixed(1)} Mbps`;
  return `${valueKbps.toFixed(0)} Kbps`;
}

export function formatCurrency(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return "Never";
  const deltaMs = Date.now() - new Date(iso).getTime();
  const seconds = Math.round(deltaMs / 1000);
  if (seconds < 5) return "Just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}
