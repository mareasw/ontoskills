import type { Translations } from '../types';

export function TrustBadge({ tier, t }: { tier: string; t: Translations }) {
  const styles: Record<string, string> = {
    official: 'bg-[#52c7e8]/10 text-[#52c7e8]',
    verified: 'bg-green-500/10 text-green-400',
    community: 'bg-amber-500/10 text-amber-400',
  };
  const labels: Record<string, string> = {
    official: t.official,
    verified: t.verified,
    community: t.community,
  };
  const cls = styles[tier] || 'bg-white/5 text-[#8a8a8a]';
  return <span className={`px-2.5 py-1 rounded-full text-xs font-medium uppercase tracking-wide ${cls}`}>{labels[tier] || tier}</span>;
}
