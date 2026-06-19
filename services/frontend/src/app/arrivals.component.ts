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
        <div>
          <div class="eyebrow">მომავალი ავტობუსები</div>
          <div class="stopname">{{ stop.name }}</div>
        </div>
        <span class="live" *ngIf="!loading && view.length">
          <span class="dot"><i></i><i></i></span>live
        </span>
      </div>

      <div class="legend">
        <span><i class="sw ai"></i>AI პროგნოზი</span>
        <span><i class="sw ttc"></i>TTC ოფიციალური</span>
      </div>

      <div class="chips" *ngIf="routes.length">
        <button class="chip" [class.on]="!routeFilter" (click)="setFilter(null)">ყველა</button>
        <button class="chip num" *ngFor="let r of routes" [class.on]="routeFilter === r"
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
          <div class="info">
            <div class="dest">{{ a.headsign }}</div>
            <!-- განრიგი ხშირად 0/უარყოფითია (სუსტი baseline) — ვაჩვენებთ მხოლოდ როცა აზრიანია. -->
            <div class="sched" *ngIf="a.scheduled_min != null && !isNow(a.scheduled_min)">
              გრაფიკით {{ mins(a.scheduled_min) }} წთ
            </div>
          </div>
          <div class="preds">
            <div class="pred ai">
              <span class="lbl">AI</span>
              <span class="val" *ngIf="isNow(a.predicted_min)">ახლა</span>
              <span class="val" *ngIf="!isNow(a.predicted_min)"><b>{{ mins(a.predicted_min) }}</b> წთ</span>
            </div>
            <div class="pred ttc">
              <span class="lbl">TTC</span>
              <span class="val" *ngIf="isNow(a.operator_min)">ახლა</span>
              <span class="val" *ngIf="!isNow(a.operator_min)"><b>{{ mins(a.operator_min) }}</b> წთ</span>
            </div>
          </div>
        </li>
      </ul>
    </ng-container>
  `,
  styles: [`
    .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 0.5rem;
            padding: 20px 0 10px; }
    .eyebrow { font: 700 11px var(--mono); letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }
    .stopname { font: 700 19px var(--geo); color: var(--ink); margin-top: 3px; }
    .live { display: inline-flex; align-items: center; gap: 6px; font: 600 11px var(--geo);
            color: var(--green2); padding-bottom: 3px; white-space: nowrap; }
    .live .dot { position: relative; width: 8px; height: 8px; display: inline-block; }
    .live .dot i { position: absolute; inset: 0; border-radius: 50%; background: var(--green-border); display: block; }
    .live .dot i:last-child { animation: movaPulse 1.8s ease infinite; }

    .legend { display: flex; gap: 16px; align-items: center; background: rgba(255,255,255,0.65);
              border: 1px solid var(--card-border); border-radius: 14px; padding: 9px 13px;
              font: 500 12px var(--geo); color: #3a4a47; margin-bottom: 12px; }
    .legend span { display: flex; align-items: center; gap: 6px; }
    .sw { width: 11px; height: 11px; border-radius: 4px; display: block; }
    .sw.ai { background: var(--grad-green); }
    .sw.ttc { background: #fff; border: 1.5px solid #b6c4c0; }

    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
    .chip { border: 1px solid var(--card-border); background: rgba(255,255,255,0.8); color: var(--ink2);
            border-radius: 13px; padding: 8px 14px; font: 600 13px var(--geo); cursor: pointer; }
    .chip.num { font: 700 13px var(--mono); }
    .chip.on { background: var(--grad-green); color: #fff; border-color: transparent;
               box-shadow: 0 1px 0 rgba(255,255,255,0.5) inset, 0 6px 14px -8px rgba(0,150,120,0.55); }
    .status { color: var(--muted2); }
    .status.error { color: #c0392b; }

    .cards { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
    .card { display: flex; align-items: center; gap: 12px; background: var(--card); backdrop-filter: blur(10px);
            border: 1px solid var(--card-border); border-radius: 22px; padding: 14px; box-shadow: var(--shadow-card); }
    .route { flex: none; width: 46px; height: 46px; border-radius: 14px;
             background: linear-gradient(var(--badge1), var(--badge2)); color: #fff;
             display: flex; align-items: center; justify-content: center; font: 700 17px var(--mono);
             box-shadow: 0 1px 0 rgba(255,255,255,0.15) inset; }
    .info { flex: 1; min-width: 0; }
    .dest { font: 700 16px var(--geo); color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .sched { font: 500 12px var(--geo); color: var(--muted2); margin-top: 2px; }
    .preds { display: flex; flex-direction: column; gap: 6px; flex: none; }
    .pred { display: flex; align-items: center; justify-content: space-between; gap: 8px;
            border-radius: 12px; padding: 6px 11px; min-width: 96px; }
    .pred .lbl { font: 700 10px var(--mono); letter-spacing: 0.06em; }
    .pred .val { font: 500 11px var(--geo); }
    .pred .val b { font: 700 18px var(--mono); }
    .pred.ai { background: var(--grad-green); box-shadow: 0 1px 0 rgba(255,255,255,0.5) inset, 0 6px 14px -7px rgba(0,150,120,0.6); }
    .pred.ai .lbl { color: rgba(255,255,255,0.85); }
    .pred.ai .val { color: #fff; }
    .pred.ttc { background: var(--ttc-bg); border: 1px solid var(--ttc-border); }
    .pred.ttc .lbl { color: var(--ttc-lbl); }
    .pred.ttc .val { color: var(--ttc-ink); }

    @keyframes movaPulse { 0% { transform: scale(1); opacity: 0.6; } 100% { transform: scale(2.6); opacity: 0; } }
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

  // user-facing კლამპი: უარყოფითს 0-ზე ვჭრით (ავტობუსი ვერ მოვა „-1 წუთში").
  // 1 წუთზე ნაკლები -> „ახლა"; დანარჩენი — მთელ წუთებად.
  isNow(min: number | null): boolean {
    return min != null && Math.max(0, min) < 0.5;
  }

  mins(min: number | null): number {
    return min == null ? 0 : Math.round(Math.max(0, min));
  }
}
