import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Arrival } from './models';
import { I18nService } from './i18n';
import { bigLabel, deltaVsOfficial, isNow, roundMin } from './format';

// ერთი რეისის სტრიქონი. მთავარი რიცხვი ჩვენი მოდელის პროგნოზია; ქვეშ — რამდენად სცდება
// TTC-ის *ოფიციალურ* პროგნოზს (და არა განრიგს). ასე ჩანს, რომ ეს ჩვენი შეფასებაა, და არა
// ოფიციალურის გამეორება — ძველ UI-ში ეს ორი "AI vs TTC" სვეტად იდგა და ერთმანეთს ეჯიბრებოდა.
@Component({
  selector: 'app-arrival-rows',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="rows">
      <div class="row" *ngFor="let a of arrivals; trackBy: track">
        <span class="route-badge num">{{ a.route }}</span>
        <span class="dest">{{ a.headsign || '—' }}</span>
        <span class="times">
          <span class="big num" [class.soon]="isSoon(a)">{{ big(a) }}</span>
          <span class="delta num" [class.same]="tone(a) === 'same'">{{ delta(a) }}</span>
        </span>
      </div>
      <div class="bar" *ngIf="showBars && arrivals.length">
        <span class="fill" [style.width.%]="fill(arrivals[0])"></span>
      </div>
    </div>
  `,
  styles: [`
    .rows { display: flex; flex-direction: column; }
    .row { display: flex; align-items: center; gap: 10px;
           padding: 7px 8px; margin: 0 -8px; border-radius: 6px; }
    .row:hover { background: rgba(233, 233, 237, 0.045); }
    .dest { flex: 1; min-width: 0; font-size: 12px; color: var(--muted);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .times { flex: none; text-align: right; }
    .big { display: block; font-size: 19px; font-weight: 500; line-height: 1.1; }
    .big.soon { color: var(--accent-400); }
    .delta { display: block; font-size: 10px; color: var(--accent-300); }
    .delta.same { color: var(--muted-2); }
    .bar { height: 3px; margin-top: 8px; border-radius: 2px; background: var(--n-900); overflow: hidden; }
    .fill { display: block; height: 3px; background: var(--accent); border-radius: 2px; }
  `],
})
export class ArrivalRowsComponent {
  @Input() arrivals: Arrival[] = [];
  /** სიაში ბარს არ ვაჩვენებთ — ბარათი ისედაც მჭიდროა; დეტალებში კი ვაჩვენებთ. */
  @Input() showBars = false;

  private readonly i18n = inject(I18nService);

  track = (_: number, a: Arrival) => `${a.route}|${a.pattern}|${a.headsign}|${a.operator_min}`;

  big(a: Arrival): string { return bigLabel(a.predicted_min, this.i18n.t()); }
  isSoon(a: Arrival): boolean { return isNow(a.predicted_min) || roundMin(a.predicted_min) <= 2; }
  delta(a: Arrival): string { return deltaVsOfficial(a, this.i18n.t())?.text ?? ''; }
  tone(a: Arrival): string { return deltaVsOfficial(a, this.i18n.t())?.tone ?? 'same'; }

  /** რამდენად ახლოა რეისი — 30 წუთიანი ჰორიზონტით. მხოლოდ ვიზუალური მინიშნებაა. */
  fill(a: Arrival): number {
    return Math.max(4, Math.min(100, 100 - (roundMin(a.predicted_min) / 30) * 100));
  }
}
