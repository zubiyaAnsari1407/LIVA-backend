
---

### `backend/README.md` — FULL REPLACEMENT

```md
# LIVA Backend

### AI, Workflow and Data Engine for Land Acquisition Delay Intelligence

This repository contains the backend services for **LIVA — Land Intelligence for Viksit Administration**, developed for:

**SIH 2026 — Problem Statement 26017**

**Predictive Analytics System for Early Detection of Land Acquisition Delays**

---

## Live Services

**API:**  
https://liva-backend-hgyx.onrender.com

**API Documentation:**  
https://liva-backend-hgyx.onrender.com/docs

**Frontend:**  
https://liva-frontend.vercel.app

**Frontend Repository:**  
https://github.com/zubiyaAnsari1407/LIVA-frontend

---

## Backend Responsibilities

The LIVA backend powers:

- Project management
- Land parcel records
- Ownership & Survey workflow
- Document management
- Litigation tracking
- Compensation monitoring
- Rehabilitation & Resettlement
- Action Centre
- Workflow summaries
- GIS project locations
- ML delay-risk intelligence
- Risk explanations
- Delay Digital Twin simulations
- Simulation history
- Reporting data
- Cloud database persistence

---

## Architecture

```text
React / TypeScript Frontend
            ↓
        REST APIs
            ↓
        FastAPI
     ┌──────┼────────┐
     ↓      ↓        ↓
 Workflow   ML      GIS
 Engine    Engine   Services
     └──────┼────────┘
            ↓
      MongoDB Atlas
            ↓
      Persistent Data

Project Images → Cloudinary
