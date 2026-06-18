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
        <span class="hint">AI პროგნოზი vs ოპერატორი</span>
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
          <span class="dest">{{ a.headsign }}</span>
          <span class="pred">
            <span class="min">{{ a.predicted_min }}</span><span class="unit">წთ</span>
            <span class="tag">AI</span>
          </span>
          <span class="base">ოპერ. {{ a.operator_min }}</span>
        </li>
      </ul>
    </ng-container>
  `,
  styles: [`
    .head { display: flex; align-items: baseline; justify-content: space-between; gap: 0.5rem; }
    h2 { font-size: 1.15rem; margin: 0.5rem 0 0.25rem; }
    .hint { color: #888; font-size: 0.75rem; }
    .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 0.75rem; }
    .chip { border: 1px solid #ccc; background: #fff; border-radius: 999px; padding: 0.25rem 0.7rem;
            font-size: 0.85rem; cursor: pointer; }
    .chip.on { background: #00B38B; color: #fff; border-color: #00B38B; }
    .status { color: #888; }
    .status.error { color: #c0392b; }
    .cards { list-style: none; margin: 0; padding: 0; }
    .card { display: grid; grid-template-columns: auto 1fr auto; grid-template-rows: auto auto;
            align-items: center; gap: 0.1rem 0.7rem; padding: 0.7rem 0.2rem; border-bottom: 1px solid #eee; }
    .route { grid-row: 1 / 3; font-weight: 700; background: #1a1a1a; color: #fff; border-radius: 8px;
             padding: 0.3rem 0.55rem; font-size: 0.95rem; min-width: 2.2rem; text-align: center; }
    .dest { font-weight: 500; }
    .base { color: #999; font-size: 0.8rem; }
    .pred { grid-row: 1 / 3; justify-self: end; display: flex; align-items: baseline; gap: 0.15rem; }
    .pred .min { font-size: 1.7rem; font-weight: 800; color: #00805f; line-height: 1; }
    .pred .unit { color: #00805f; font-size: 0.85rem; }
    .pred .tag { margin-left: 0.35rem; background: #e8f8f3; color: #00805f; font-size: 0.65rem;
                 font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 5px; align-self: center; }
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
}
