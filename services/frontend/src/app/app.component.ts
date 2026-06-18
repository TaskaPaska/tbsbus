import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

// API-ს /predict/<stop_id> პასუხის ფორმა (იხ. services/api/predict.py: predict_stop).
interface Arrival {
  route: string;
  headsign: string;
  pattern: string;
  operator_min: number;     // baseline: ოპერატორის realtimeArrivalMinutes
  scheduled_min: number | null;
  predicted_min: number;    // ჩვენი მოდელის კორექტირებული პროგნოზი
}
interface PredictResponse { stop_id: string; arrivals: Arrival[]; }

@Component({
  selector: 'app-root',
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  stopId = '806';            // default — დატვირთული გაჩერება (demo).
  arrivals: Arrival[] = [];
  loading = false;
  error = '';

  constructor(private http: HttpClient) {}

  load(): void {
    const id = this.stopId.trim();
    if (!id) { return; }
    this.loading = true;
    this.error = '';
    // dev-ში relative path proxy.conf.json-ით Flask-ზე გადადის (CORS-ის გარეშე).
    this.http.get<PredictResponse>(`/predict/${id}`).subscribe({
      next: (res) => { this.arrivals = res.arrivals; this.loading = false; },
      error: (e) => { this.error = e?.error?.error || e.message || 'შეცდომა'; this.loading = false; this.arrivals = []; }
    });
  }
}
