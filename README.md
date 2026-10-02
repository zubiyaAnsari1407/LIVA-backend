# LIVA Backend — Land Acquisition Intelligence & Verification Assistant

This repository contains the backend service for LIVA, a Land Acquisition Delay Detection Platform.

The backend provides APIs for authentication, land registration, document verification, project management, grievance handling, risk intelligence, workflow tracking, reports and simulation-related operations.

The backend is built using FastAPI and Python and uses MongoDB as the primary database.

---

# 1. Backend Overview

The LIVA backend manages the complete workflow between the frontend, database and risk/intelligence services.

The main backend workflow is:

1. Receive landowner request
2. Store registration request
3. Store and manage submitted documents
4. Officer verifies documents
5. Return request for correction if required
6. Officer verifies the registration
7. Administrator reviews the verified request
8. Administrator approves or rejects the request
9. Create LIVA project after approval
10. Give the landowner project access
11. Receive problem / grievance
12. Officer verifies grievance
13. Store verified grievance information
14. Extract available risk factors
15. Send supported information to the risk engine
16. Calculate delay-risk intelligence
17. Generate probable reasons
18. Support simulation / intervention analysis
19. Track actions and project progress
20. Generate workflow reports and monitoring information

---

# 2. Backend Technology Stack

The backend uses:

- Python
- FastAPI
- Uvicorn
- MongoDB
- PyMongo
- Pydantic
- Python virtual environment / uv
- REST APIs
- Machine Learning / Risk Engine
- Explainability logic
- Document management
- GridFS for document files

---

# 3. FastAPI

FastAPI is used to build the REST API layer of LIVA.

The backend provides API endpoints for:

- Registration requests
- Projects
- Grievances
- Risk assessments
- Documents
- Workflow information
- Actions
- Reports
- Simulation-related operations

The API also provides automatic documentation through FastAPI.

API documentation:

`/docs`

---

# 4. Backend Architecture

The backend follows a layered structure.

The main layers are:

## API / Router Layer

Receives HTTP requests from the frontend and returns responses.

## Business Logic Layer

Handles:

- Registration workflow
- Project creation
- Grievance processing
- Verification
- Status transitions
- Risk processing
- Workflow calculations

## Risk / ML Layer

Processes supported verified information and calculates delay-risk intelligence.

## Database Layer

Stores project, registration, grievance, risk and workflow data in MongoDB.

## Document Layer

Handles uploaded documents and document metadata.

---

# 5. Main Backend Modules

Important backend modules include:

- `main.py`
- `liva_registration.py`
- `liva_projects.py`
- `liva_risk_assessments.py`
- `workflow_reports.py`

The ML-related modules are maintained under:

`backend/ml/`

Important ML components include:

- Risk engine
- Explainability logic
- Recommendations
- Land acquisition reference information
- Feature extraction

---

# 6. Land Registration API

The registration workflow is handled through:

`/api/liva/registration-requests`

The backend stores registration requests and manages their status.

The registration workflow supports:

- Request creation
- Document submission
- Officer verification
- Correction requests
- Resubmission
- Officer verification
- Administrative approval
- Rejection
- Project creation after approval

---

# 7. Registration Status

The registration request can move through the following states:

- `SUBMITTED`
- `UNDER_VERIFICATION`
- `RETURNED`
- `OFFICER_VERIFIED`
- `APPROVED`
- `REJECTED`

The backend controls valid status transitions.

This prevents invalid workflow changes.

---

# 8. Registration Correction and Resubmission

If a request is returned or rejected because correction is required, the user can submit the corrected information again.

The backend:

- Preserves the original request ID
- Updates the request information
- Resets document verification where required
- Stores previous review information
- Maintains review history
- Moves the request back into the verification workflow

This allows the complete request history to remain traceable.

---

# 9. Document Management

LIVA requires documents during the land registration workflow.

The main document categories are:

1. Ownership Proof
2. 7/12 Extract / Land Record
3. Identity Proof

The backend stores document metadata and manages uploaded files.

Documents can be individually reviewed by the officer.

The backend records verification status and verification remarks.

---

# 10. Project Creation

After a registration request is approved, the backend creates a LIVA project.

Each project receives a unique project ID.

Example:

`LIVA-PRJ-027`

Project information can include:

- Project ID
- Project name
- Landowner information
- Survey information
- Village
- Taluka / Block
- District
- State
- Land area
- Project status
- Related workflow information

The backend also prevents project ID collisions when creating projects.

---

# 11. Projects API

Project operations are handled through:

`/api/liva/projects`

The backend provides project information to the frontend for:

- Project listing
- Project details
- Project workspace
- Project tracking
- Project monitoring

---

# 12. Grievance Management

After a project is created, the landowner can submit a problem or grievance.

The grievance can contain:

- Project reference
- Problem type
- Subject
- Description
- Supporting documents
- Landowner remarks

Multiple grievances can be associated with the same project.

Each grievance is stored separately and can be independently verified.

---

# 13. Grievance Verification

The officer verifies the submitted grievance.

The backend stores officer verification information such as:

- Findings
- Cause
- Recommended action
- Work status
- Overdue information where available
- Ownership issue confirmation
- Verification remarks

The verified grievance data can then be used by the risk/intelligence workflow.

---

# 14. Risk / Intelligence Engine

The backend contains a risk engine for delay-risk assessment.

The basic process is:

1. Retrieve supported project information
2. Retrieve verified grievance information
3. Extract available factors
4. Process supported factors
5. Calculate risk
6. Determine risk level
7. Generate supporting reasons
8. Return risk intelligence to the frontend

Risk categories include:

- High
- Medium
- Low

The risk is calculated by the system and is not manually assigned by the landowner.

---

# 15. Risk Factors

The backend uses available and supported information.

## Land Factors

Examples include:

- Land area
- Location
- Available land details

## Problem / Grievance Factors

Examples include:

- Problem type
- Verified grievance
- Verified ownership dispute
- Work status
- Confirmed overdue information where available

## Document Factors

Examples include:

- Document availability
- Document verification status
- Ownership proof
- Land record
- Identity proof

## Project Factors

Examples include:

- Available project status
- Project stage
- Available project progress
- Supported dependencies

Only supported information is used.

Unsupported information is not automatically converted into zero or negative values.

---

# 16. Important Risk Engine Rule

The risk engine uses verified information wherever verification is required.

For example:

- An unverified grievance is not treated as a verified problem.
- A survey grievance does not automatically mean survey work is pending.
- A compensation grievance does not automatically mean compensation is unpaid.
- Uploaded supporting documents do not automatically mean that a document is missing or incomplete.
- Unsupported metrics are not automatically represented as zero.

This prevents unsupported assumptions from affecting risk calculations.

---

# 17. Explainability

The backend contains explainability logic to provide reasons supporting the risk result.

The purpose is to provide more information than only a numerical risk score.

Possible supporting reasons can include:

- Verified ownership dispute
- Verified grievance
- Document-related information
- Available project-stage information
- Confirmed overdue work

The explanation is generated only from information available to the backend.

---

# 18. Digital Twin and Simulation

LIVA includes a Digital Twin and simulation concept for intervention analysis.

The backend can support simulation-related data and workflow operations.

The basic concept is:

1. Take the current project state
2. Select an intervention
3. Run a simulation
4. Compare possible outcomes
5. Support follow-up planning

Simulation is intended for what-if analysis.

It does not directly modify official project records.

---

# 19. Workflow Reports

The backend provides workflow reporting functionality.

Reports can contain available information related to:

- Projects
- Parcels
- Ownership
- Surveys
- Litigation
- Documents
- Compensation
- Actions
- Overdue work
- Rehabilitation / R&R

Where data is unavailable, the backend can represent the metric as unavailable instead of incorrectly returning zero.

---

# 20. Compensation Data

Where compensation records are available, the backend can provide:

- Approved amount
- Disbursed amount
- Remaining balance

Monetary values are handled carefully so that rupee/paise calculations remain consistent.

The backend does not infer compensation status only from the type of grievance.

---

# 21. Actions and Monitoring

The backend supports workflow action and monitoring information.

Actions can be associated with project follow-up.

The system can track:

- Action status
- Open actions
- Follow-up information
- Progress
- Monitoring information

This supports the final Action / Monitoring stage of the LIVA workflow.

---

# 22. MongoDB Database

LIVA uses MongoDB as its primary database.

Database name:

`liva`

Important collections include:

- `liva_registration_requests`
- `liva_projects`
- `liva_grievances`
- `liva_risk_assessments`
- `liva_document_metadata`
- `document_files.files`
- `document_files.chunks`
- `projects`
- `parcels`
- `actions`
- `compensation`
- `litigation`
- `rehabilitation`
- `simulation_runs`

The exact data used by each workflow depends on the supported backend schema.

---

# 23. Document Storage

LIVA uses document metadata and file storage for uploaded documents.

The document system supports:

- File upload
- File metadata
- Document category
- Verification status
- Verification remarks
- File retrieval

GridFS collections are used for storing larger document files.

---

# 24. API Structure

Major API areas include:

`/api/liva/registration-requests`

Handles:

- Registration requests
- Verification
- Resubmission
- Approval
- Rejection

`/api/liva/projects`

Handles:

- Project creation
- Project listing
- Project information

`/api/liva/grievances`

Handles:

- Grievance submission
- Grievance verification
- Grievance information

`/api/liva/risk-assessments`

Handles:

- Risk assessment
- Risk information
- Intelligence results

Additional API routes support:

- Documents
- Actions
- Workflow summaries
- Reports
- Simulation

---

# 25. Backend Data Flow

The backend data flow is:

Frontend Request

↓

FastAPI Router

↓

Validation

↓

Business Logic

↓

MongoDB / Document Storage

↓

Risk / Intelligence Processing where required

↓

API Response

↓

Frontend

---

# 26. Environment Variables

The backend uses environment variables for configuration.

Important configuration includes:

`MONGODB_URL`

MongoDB connection URL.

`MONGODB_DB`

MongoDB database name.

`FRONTEND_ORIGIN`

Frontend origin used for API access and CORS configuration.

Cloudinary configuration:

`CLOUDINARY_CLOUD_NAME`

`CLOUDINARY_API_KEY`

`CLOUDINARY_API_SECRET`

AI / model-related configuration where required:

`OPENAI_API_KEY`

`GROQ_API_KEY`

`GROQ_MODEL`

Sensitive environment variables should not be committed to GitHub.

---

# 27. Local Backend Setup

Clone the repository:

`git clone <BACKEND_REPOSITORY_URL>`

Move into the backend directory:

`cd LIVA-backend`

Install dependencies using uv:

`uv sync`

Start the FastAPI development server:

`uv run uvicorn main:app --reload --port 8000`

The local API will be available at:

`http://localhost:8000`

FastAPI documentation:

`http://localhost:8000/docs`

---

# 28. Production Server

The deployed backend uses Uvicorn to run the FastAPI application.

Production start command:

`uv run uvicorn main:app --host 0.0.0.0 --port $PORT`

---

# 29. Backend Deployment

The LIVA backend is deployed using Render.

Deployment flow:

GitHub Repository

↓

Render

↓

FastAPI + Uvicorn

↓

MongoDB Atlas

↓

LIVA Frontend

---

# 30. Live Backend

Current deployed backend:

https://liva-backend-1.onrender.com

API documentation:

https://liva-backend-1.onrender.com/docs

The root endpoint can be used to verify that the deployed LIVA API is running.

---

# 31. Backend and Frontend Connection

The frontend connects to the deployed backend using:

`VITE_API_BASE_URL`

Current backend:

`https://liva-backend-1.onrender.com`

The frontend sends REST API requests to the backend.

The backend processes the request and communicates with MongoDB before returning the response.

---

# 32. End-to-End Backend Workflow

The backend handles the complete workflow:

Landowner Request

↓

Registration API

↓

MongoDB

↓

Document Upload

↓

Officer Verification

↓

Correction / Resubmission if Required

↓

Officer Verified

↓

Administrator Approval

↓

Project Creation

↓

Project Database Record

↓

Landowner Project Access

↓

Grievance Submission

↓

Grievance Verification

↓

Verified Grievance Data

↓

Risk Factor Extraction

↓

Risk / Model Engine

↓

Risk Assessment

↓

Probable Reasons

↓

Simulation / Intervention Analysis

↓

Actions

↓

Monitoring

↓

Reports

---

# 33. Backend Design Principles

The backend follows these principles:

- REST API based architecture
- Role-based workflow
- Status-controlled processes
- Verified data before risk processing
- MongoDB-based persistence
- Separate document storage
- Traceable registration workflow
- Traceable grievance workflow
- Prevention of unsupported risk assumptions
- Separation of official data and simulation results
- Environment-based configuration
- API documentation through FastAPI

---

# 34. Current Backend Scope

The LIVA backend currently supports the major backend workflow for:

- Registration requests
- Document management
- Officer verification
- Registration correction and resubmission
- Administrative approval
- Project creation
- Project management
- Grievance submission
- Grievance verification
- Risk assessment
- Explainability
- Workflow monitoring
- Actions
- Reports
- Simulation-related data

---

# 35. Project Identity

## LIVA

Land Acquisition Intelligence & Verification Assistant

## Platform

Land Acquisition Delay Detection Platform

## Core Workflow

Predict → Explain → Locate → Simulate → Act → Monitor

---

## Live Backend

https://liva-backend-1.onrender.com

## API Documentation

https://liva-backend-1.onrender.com/docs
