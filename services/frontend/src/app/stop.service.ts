import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Stop, PredictResponse } from './models';

// HTTP ლოგიკა ერთ ადგილას — relative path-ები dev-ში proxy.conf.json-ით Flask-ზე გადადის.
@Injectable({ providedIn: 'root' })
export class StopService {
  constructor(private http: HttpClient) {}

  getStops(): Observable<{ stops: Stop[] }> {
    return this.http.get<{ stops: Stop[] }>('/stops');
  }

  predict(stopId: string): Observable<PredictResponse> {
    return this.http.get<PredictResponse>(`/predict/${stopId}`);
  }
}

// ორ კოორდინატს შორის მანძილი მეტრებში (Haversine) — „ჩემთან ახლოს" გაჩერებისთვის.
export function distanceMeters(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLon = toRad(bLon - aLon);
  const lat1 = toRad(aLat);
  const lat2 = toRad(bLat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
