import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';

export const appConfig: ApplicationConfig = {
  // provideHttpClient — Flask API-ს /predict-ს ვუძახებთ; dev-ში proxy.conf.json-ით.
  providers: [provideZoneChangeDetection({ eventCoalescing: true }), provideHttpClient()]
};
