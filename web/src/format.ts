const USDG_DECIMALS = 6n;

export function formatBps(bps: number): string {
  return `${(bps / 100).toFixed(2)}%`;
}

export function formatUsdg(raw: bigint): string {
  const unit = 10n ** USDG_DECIMALS;
  const whole = raw / unit;
  const cents = (raw % unit) / (unit / 100n);
  const grouped = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${grouped}.${cents.toString().padStart(2, "0")}`;
}

function percent(bps: number): string {
  const value = bps / 100;
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/0+$/, "");
}

export function splitLabel(fixedBps: number): string {
  return `${percent(fixedBps)}% fixed / ${percent(10000 - fixedBps)}% floating`;
}

export function shortAddr(address: string): string {
  return `${address.slice(0, 6)}…${address.slice(-4)}`;
}
