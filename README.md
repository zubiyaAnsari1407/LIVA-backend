
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



## AI / ML Layer

LIVA includes a machine-learning research pipeline for infrastructure schedule-delay risk analysis.

The system supports:

risk prediction
probability-based delay intelligence
risk-factor analysis
Explainable AI
recommendations
simulation support

The current trained model acts as a general infrastructure schedule-delay signal and is integrated into the LIVA decision-support workflow.


## Delay Digital Twin

The backend supports simulation APIs used by the LIVA Delay Digital Twin.

Officials can test intervention scenarios and compare possible project outcomes before selecting an action.

Example scenarios may include changes related to:

documentation
compensation
legal issues
administrative intervention
workflow progress

## Database

MongoDB Atlas

Main database:

liva

The deployed application stores live project and workflow records in Atlas.

Demo records are explicitly marked separately from source-backed records.


## Cloud Storage

Project images are uploaded to:

Cloudinary

Supported formats include:

JPG
JPEG
PNG
WEBP

## Main API Areas
/api/projects
/api/parcels
/api/workflow
/api/risk
/api/simulation
/api/gis
/api/geocode
/api/health

Interactive endpoint documentation is available through FastAPI Swagger:

https://liva-backend-hgyx.onrender.com/docs

## Health Checks
GET /api/health
GET /api/health/database

These endpoints verify API and MongoDB connectivity.

## Technology Stack

Backend

Python 3.12
FastAPI
Uvicorn
PyMongo

AI / ML

Scikit-learn
SHAP
Pandas
NumPy

Database

MongoDB Atlas

Media

Cloudinary

Package Management

uv

Deployment

Render

## Local Development

Install dependencies:

uv sync

Start the API:

uv run uvicorn main:app --reload --port 8000

Open:

http://127.0.0.1:8000/docs

## Data Integrity

LIVA distinguishes between:

Source-backed records — linked to documented sources.

Demo records — explicitly marked as illustrative test data.

Adding a source URL does not automatically mean that a record has been independently verified.

## Current Prototype

The backend is deployed and connected to:

Render
   ↓
MongoDB Atlas
   ↓
Cloudinary

The live Vercel frontend communicates with this API and can create persistent records in the cloud database.

## Future Expansion

Production-scale extensions can include:

automatic continuous model retraining
government database connectors
automated email/SMS/push alerts
enterprise authentication
backend-enforced RBAC
comprehensive audit trails
larger land-acquisition-specific training datasets
Team

## Team Paradox

Smart India Hackathon 2026
