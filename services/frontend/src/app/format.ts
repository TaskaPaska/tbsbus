import { Strings } from './i18n';
import { Arrival } from './models';

// წუთების ჩვენება. მოდელი წილად წუთებს აბრუნებს (მაგ. 6.42) — მომხმარებელს მთელი წუთი უნდა.
export function roundMin(v: number | null | undefined): number {
  return v == null ? 0 : Math.max(0, Math.round(v));
}

export function isNow(v: number | null | undefined): boolean {
  return roundMin(v) < 1;
}

/** დიდი ციფრი: „ახლა" ან „6 წთ". */
export function bigLabel(v: number | null | undefined, t: Strings): string {
  return isNow(v) ? t.now : `${roundMin(v)} ${t.min}`;
}

export type DeltaTone = 'later' | 'earlier' | 'same';

export interface DeltaInfo {
  text: string;
  tone: DeltaTone;
}

/** განსხვავება TTC-ის *ოფიციალურ პროგნოზთან* (და არა განრიგთან).
 *
 * სხვაობას უკვე *დამრგვალებულ* რიცხვებზე ვთვლით, რომ ეკრანზე ერთმანეთს არ ეწინააღმდეგებოდეს:
 * 5.6 -> "6 წთ" და 4.4 -> "4" რომ არ აჩვენოს "1 წუთით გვიან" 2-ის ნაცვლად.
 */
export function deltaVsOfficial(a: Arrival, t: Strings): DeltaInfo | null {
  if (a.operator_min == null) { return null; }
  const d = roundMin(a.predicted_min) - roundMin(a.operator_min);
  if (d === 0) { return { text: t.matchesOfficial, tone: 'same' }; }
  return d > 0
    ? { text: `${d} ${t.laterThanOfficial}`, tone: 'later' }
    : { text: `${-d} ${t.earlierThanOfficial}`, tone: 'earlier' };
}
