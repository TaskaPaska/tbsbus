import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StopPickerComponent } from './stop-picker.component';
import { ArrivalsComponent } from './arrivals.component';
import { StopService } from './stop.service';
import { Stop, Arrival } from './models';

// shell — გაჩერებებს ტვირთავს, picker-სა და arrivals-ს აკავშირებს.
@Component({
  selector: 'app-root',
  imports: [CommonModule, StopPickerComponent, ArrivalsComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent implements OnInit {
  stops: Stop[] = [];
  selected: Stop | null = null;
  arrivals: Arrival[] = [];
  loading = false;
  error = '';

  constructor(private api: StopService) {}

  ngOnInit(): void {
    this.api.getStops().subscribe({
      next: (res) => { this.stops = res.stops; },
      error: () => { this.error = 'გაჩერებების სია ვერ ჩაიტვირთა.'; }
    });
  }

  onStopSelected(stop: Stop): void {
    this.selected = stop;
    this.loading = true;
    this.error = '';
    this.arrivals = [];
    this.api.predict(stop.id).subscribe({
      next: (res) => { this.arrivals = res.arrivals; this.loading = false; },
      error: (e) => { this.error = e?.error?.error || 'პროგნოზი ვერ ჩაიტვირთა.'; this.loading = false; }
    });
  }
}
