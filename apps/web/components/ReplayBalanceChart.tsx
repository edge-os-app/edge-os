interface ReplaySample {
  at?: unknown;
  account_value_quote?: unknown;
  mark_reasons?: unknown;
}

interface ChartPoint {
  at: string;
  value: string | null;
  numericValue: number | null;
  reasons: string[];
}

interface Props {
  samples: Record<string, unknown>[];
}

function samplePoints(samples: Record<string, unknown>[]): ChartPoint[] {
  return samples.map((sample) => {
    const replaySample = sample as ReplaySample;
    const rawValue = replaySample.account_value_quote;
    const value = typeof rawValue === "string" || typeof rawValue === "number" ? String(rawValue) : null;
    const numericValue = value === null ? null : Number(value);
    const rawReasons = replaySample.mark_reasons;
    return {
      at: typeof replaySample.at === "string" ? replaySample.at : "Saved sample time unavailable",
      value,
      numericValue: numericValue !== null && Number.isFinite(numericValue) ? numericValue : null,
      reasons: Array.isArray(rawReasons) ? rawReasons.filter((reason): reason is string => typeof reason === "string") : [],
    };
  });
}

function displayUtc(value: string): string {
  const normalized = new Date(value);
  if (Number.isNaN(normalized.valueOf())) return value;
  const iso = normalized.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 19)} UTC`;
}

function chartSegments(points: ChartPoint[]): number[][][] {
  const available = points.flatMap((point, index) => point.numericValue === null ? [] : [index]);
  if (!available.length) return [];
  const values = available.map((index) => points[index].numericValue as number);
  const scale = Math.max(...values.map(Math.abs)) || 1;
  const scaled = values.map((value) => value / scale);
  const low = Math.min(...scaled);
  const high = Math.max(...scaled);
  const span = high - low;
  const times = points.map((point) => Date.parse(point.at));
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const hasOrderedTimes = times.every(Number.isFinite) && maxTime > minTime;
  const xFor = (index: number) => points.length < 2 ? 320 : hasOrderedTimes
    ? 40 + ((times[index] - minTime) / (maxTime - minTime)) * 560
    : 40 + (index / (points.length - 1)) * 560;
  const yFor = (value: number) => span === 0 ? 110 : 196 - ((value / scale - low) / span) * 156;

  const segments: number[][][] = [];
  let current: number[][] = [];
  points.forEach((point, index) => {
    if (point.numericValue === null) {
      if (current.length) segments.push(current);
      current = [];
      return;
    }
    current.push([xFor(index), yFor(point.numericValue)]);
  });
  if (current.length) segments.push(current);
  return segments;
}

export function ReplayBalanceChart({ samples }: Props) {
  const points = samplePoints(samples);
  const segments = chartSegments(points);
  const availableCount = points.filter((point) => point.numericValue !== null).length;
  const chartDescription = points.length === 0
    ? "No saved account-balance samples are available."
    : `${availableCount} of ${points.length} saved account-balance samples have available quote values. Unavailable samples break the plotted line; no values are filled or carried.`;

  return (
    <figure className="spot-replay-balance" data-testid="spot-replay-balance-chart">
      <figcaption>Account balance over the saved replay</figcaption>
      <svg viewBox="0 0 640 220" role="img" aria-labelledby="spot-replay-balance-title spot-replay-balance-description">
        <title id="spot-replay-balance-title">Account balance in quote over the replay window</title>
        <desc id="spot-replay-balance-description">{chartDescription}</desc>
        <line x1="40" y1="196" x2="600" y2="196" className="spot-replay-chart-axis" />
        {segments.map((segment, segmentIndex) => segment.length > 1 ? (
          <polyline key={`segment-${segmentIndex}`} points={segment.map(([x, y]) => `${x},${y}`).join(" ")} />
        ) : segment.map(([x, y], pointIndex) => (
          <circle key={`point-${segmentIndex}-${pointIndex}`} cx={x} cy={y} r="4" />
        )))}
      </svg>
      {points.length === 0 ? <p>No saved balance samples are available.</p> : null}
      {availableCount === 0 && points.length > 0 ? <p>No saved account-balance value is available to plot.</p> : null}
      <ol aria-label="Saved account value samples" className="spot-replay-sample-list">
        {points.map((point, index) => (
          <li key={`${point.at}-${index}`}>
            <span>{displayUtc(point.at)}</span>
            <strong>{point.value === null || point.numericValue === null ? "Unavailable" : `${point.value} quote`}</strong>
            {point.value !== null && point.numericValue === null ? <span>Value cannot be plotted safely.</span> : null}
            {point.value === null && point.reasons.length ? <span>{point.reasons.join(", ")}</span> : null}
          </li>
        ))}
      </ol>
    </figure>
  );
}
