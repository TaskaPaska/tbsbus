import { Component, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Arrival, Stop } from './models';

// არჩეული გაჩერების ჩამოსვლები — AI პროგნოზი hero, ოპერატორის baseline გვერდით; მარშრუტით ფილტრი.
@Component({
  selector: 'app-arrivals',
  standalone: true,
  imports: [CommonModule],
  template: `
    <ng-container *ngIf="stop">
      <div class="head">
        <h2>{{ stop.name }}</h2>
        <span class="hint">ჩვენი AI პროგნოზი vs ოპერატორის (TTC)</span>
      </div>

      <div class="chips" *ngIf="routes.length">
        <button class="chip" [class.on]="!routeFilter" (click)="setFilter(null)">ყველა</button>
        <button class="chip" *ngFor="let r of routes" [class.on]="routeFilter === r"
                (click)="setFilter(r)">{{ r }}</button>
      </div>

      <p class="status" *ngIf="loading">იტვირთება…</p>
      <p class="status error" *ngIf="error">⚠ {{ error }}</p>
      <p class="status" *ngIf="!loading && !error && !view.length">
        ამ გაჩერებაზე realtime პროგნოზი ვერ მოიძებნა.
      </p>

      <ul class="cards">
        <li class="card" *ngFor="let a of view">
          <span class="route">{{ a.route }}</span>
          <div class="body">
            <div class="dest">{{ a.headsign }}</div>
            <div class="stats">
              <div class="stat ai">
                <span class="lbl">AI</span>
                <span class="val">{{ fmt(a.predicted_min) }}</span>
              </div>
              <div class="stat ttc">
                <span class="lbl">TTC</span>
                <span class="val">{{ fmt(a.operator_min) }}</span>
              </div>
            </div>
          </div>
        </li>
      </ul>
    </ng-container>
  `,
  styles: [`
    .head { display: flex; align-items: baseline; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap; }
    h2 { font-size: 1.15rem; margin: 0.5rem 0 0.25rem; }
    .hint { color: #888; font-size: 0.75rem; }
    .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 0.75rem; }
    .chip { border: 1px solid #ccc; background: #fff; border-radius: 999px; padding: 0.25rem 0.7rem;
            font-size: 0.85rem; cursor: pointer; }
    .chip.on { background: #00B38B; color: #fff; border-color: #00B38B; }
    .status { color: #888; }
    .status.error { color: #c0392b; }
    .cards { list-style: none; margin: 0; padding: 0; }
    .card { display: flex; align-items: center; gap: 0.7rem; padding: 0.7rem 0.2rem;
            border-bottom: 1px solid #eee; }
    .route { flex: none; font-weight: 700; background: #1a1a1a; color: #fff; border-radius: 8px;
             padding: 0.35rem 0.55rem; font-size: 0.95rem; min-width: 2.4rem; text-align: center; }
    .body { flex: 1; display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
    .dest { font-weight: 500; }
    .stats { display: flex; gap: 0.5rem; flex: none; }
    .stat { display: flex; flex-direction: column; align-items: center; min-width: 3.4rem;
            border-radius: 9px; padding: 0.3rem 0.4rem; }
    .stat .lbl { font-size: 0.6rem; font-weight: 700; letter-spacing: 0.04em; }
    .stat .val { font-size: 1.15rem; font-weight: 800; line-height: 1.1; white-space: nowrap; }
    .stat.ai { background: #e8f8f3; }
    .stat.ai .lbl { color: #00805f; }
    .stat.ai .val { color: #00805f; }
    .stat.ttc { background: #f1f1f1; }
    .stat.ttc .lbl { color: #777; }
    .stat.ttc .val { color: #444; }
  `]
})
export class ArrivalsComponent implements OnChanges {
  @Input() stop: Stop | null = null;
  @Input() arrivals: Arrival[] = [];
  @Input() loading = false;
  @Input() error = '';

  routes: string[] = [];
  routeFilter: string | null = null;
  view: Arrival[] = [];

  ngOnChanges(): void {
    this.routes = [...new Set(this.arrivals.map(a => a.route))].sort();
    if (this.routeFilter && !this.routes.includes(this.routeFilter)) { this.routeFilter = null; }
    this.applyFilter();
  }

  setFilter(r: string | null): void {
    this.routeFilter = r;
    this.applyFilter();
  }

  private applyFilter(): void {
    this.view = this.routeFilter ? this.arrivals.filter(a => a.route === this.routeFilter) : this.arrivals;
  }

  // user-facing ფორმატი: უარყოფითს 0-ზე ვჭრით (ავტობუსი ვერ მოვა „-1 წუთში"),
  // 1 წუთზე ნაკლები -> „ახლა"; დანარჩენი — მთელ წუთებად.
  fmt(min: number | null): string {
    if (min === null || min === undefined) { return '—'; }
    const m = Math.max(0, min);
    return m < 0.5 ? 'ახლა' : `${Math.round(m)} წთ`;
  }
}
