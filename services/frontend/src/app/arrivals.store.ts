import { Injectable, inject, signal } from '@angular/core';
import { StopService } from './stop.service';
import { Arrival } from './models';

// /predict/<stop> ყოველ გამოძახებაზე ცოცხლად ურეკავს TTC-ის API-ს, ამიტომ სიაში ჩანს
// გაჩერებების პროგნოზები მხოლოდ შეზღუდულად ვტვირთავთ: მოკლე ქეშით, პარალელურობის ლიმიტით და
// ერთი და იმავე გაჩერების დუბლირებული მოთხოვნების გაერთიანებით.
const TTL_MS = 30_000;
const MAX_PARALLEL = 3;

export interface ArrivalsState {
  arrivals: Arrival[];
  loading: boolean;
  error: string;
  at: number;
}

const EMPTY: ArrivalsState = { arrivals: [], loading: false, error: '', at: 0 };

@Injectable({ providedIn: 'root' })
export class ArrivalsStore {
  private readonly api = inject(StopService);
  private readonly cache = new Map<string, ArrivalsState>();
  private readonly inflight = new Set<string>();
  private queue: string[] = [];
  private running = 0;

  /** გადახატვის ტრიგერი — ქეშის ცვლილებაზე შაბლონები ხელახლა კითხულობენ get()-ს. */
  readonly version = signal(0);

  get(stopId: string): ArrivalsState {
    return this.cache.get(stopId) ?? EMPTY;
  }

  /** ჩატვირთვა საჭიროებისამებრ; force — ქეშის იგნორირება ("განახლება"). */
  request(stopId: string, force = false): void {
    const cur = this.cache.get(stopId);
    if (!force && cur && Date.now() - cur.at < TTL_MS && !cur.error) { return; }
    if (this.inflight.has(stopId)) { return; }
    this.inflight.add(stopId);
    this.queue.push(stopId);
    this.pump();
  }

  private pump(): void {
    while (this.running < MAX_PARALLEL && this.queue.length) {
      const id = this.queue.shift()!;
      this.running++;
      this.set(id, { ...this.get(id), loading: true, error: '' });
      this.api.predict(id).subscribe({
        next: (res) => this.finish(id, { arrivals: res.arrivals ?? [], loading: false, error: '', at: Date.now() }),
        error: (e) => this.finish(id, {
          arrivals: [], loading: false, at: Date.now(),
          error: e?.error?.error || 'error',
        }),
      });
    }
  }

  private finish(id: string, state: ArrivalsState): void {
    this.running--;
    this.inflight.delete(id);
    this.set(id, state);
    this.pump();
  }

  private set(id: string, state: ArrivalsState): void {
    this.cache.set(id, state);
    this.version.update(v => v + 1);
  }
}
