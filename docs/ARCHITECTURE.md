# Architecture

## Vision

Career Copilot is built around independent services.

```
                   Career Copilot

                   User Profile
                         │
                         ▼
               Recommendation Engine
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
Job Providers     Scoring Engine      AI Engine
      │                  │                  │
      └──────────────────┴──────────────────┘
                         │
                         ▼
                      FastAPI
```

---

## Current Services

- Greenhouse Client
- Job Service
- Scoring Service
- AI Service

---

## Future Services

- Resume Service
- Recommendation Service
- Candidate Service
- Provider Service

---

## Principles

- Separation of concerns
- Low coupling
- High cohesion
- Service-oriented architecture
- AI-first product design