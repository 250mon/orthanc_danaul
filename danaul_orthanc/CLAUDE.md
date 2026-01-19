# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository contains Docker Compose configurations for a medical imaging (DICOM) infrastructure using Orthanc PACS server. It consists of three main components that can be deployed independently.

## Architecture

### Three Independent Docker Compose Stacks

1. **PACS Server** (`pacs/docker-compose.yml`)
   - Main DICOM archive using Orthanc with PostgreSQL backend
   - Ports: 4242 (DICOM), 8042 (Web UI)
   - Includes OHIF viewer and DICOMweb plugins

2. **Worklist Server** (`worklists/docker-compose.yml`)
   - DICOM Modality Worklist (MWL) server with MPPS support
   - Ports: 4243 (DICOM), 5243 (MWL/MPPS), 8043 (Web UI)
   - Integrates with external EMR via SQL Server (ODBC/FreeTDS)
   - Uses pynetdicom for MWL/MPPS protocol handling (Orthanc doesn't natively support MPPS)

3. **Modality Simulator** (`orthanc-modality/docker-compose.yml`)
   - Simple Orthanc instance for testing/simulating a modality
   - Port: 888 (Web UI)

### Worklist Server Plugin Architecture

The worklist server (`worklists/orthanc-worklists/`) uses a Python plugin system:

- `plugins/worklist-with-mpps.py`: Main plugin - starts pynetdicom server on Orthanc startup, handles C-FIND (worklist queries), N-CREATE/N-SET (MPPS)
- `plugins/worklist_model.py`: SQLAlchemy models (Patient, WorklistItem, MPPSTracking, ModalityAET), database operations, Korean-to-English name romanization
- `plugins/emr_api.py`: pyodbc connection to external EMR SQL Server, fetches orders and updates status

Data flow: EMR Database -> Background sync (5 min interval + on C-FIND) -> SQLite worklist DB -> pynetdicom responses

## Commands

### Start Services

```bash
# Start PACS server (from pacs/ directory)
docker compose up -d

# Start Worklist server (from worklists/ directory)
docker compose up -d

# Start Modality simulator (from orthanc-modality/ directory)
docker compose up -d

# Build and start with fresh images
docker compose up -d --build
```

### Testing Worklist Server

```bash
# Query all worklist items
findscu -v -W localhost 5243

# Query by accession number
findscu -v -W -k "AccessionNumber=4567" localhost 5243

# Query by modality
findscu -v -W -k "(0040,0100)[0].Modality=MR" localhost 5243

# Query by date
findscu -v -W -k "(0040,0100)[0].ScheduledProcedureStepStartDate=YYYYMMDD" localhost 5243
```

### View Logs

```bash
docker compose logs -f orthanc-worklists
docker compose logs -f orthanc-pacs
```

## Configuration

### Environment Variables (worklists/.env)

Copy `.env.example` to `.env` and configure:
- `EMR_SERVER`, `EMR_PORT`, `EMR_DATABASE`, `EMR_USER`, `EMR_PASSWORD`: SQL Server connection
- `MODALITY_AET_*`: Maps modalities to AE titles (e.g., `MODALITY_AET_US=XC70`)

### Orthanc Configuration

- `orthanc.json` in each component directory
- `DicomModalities`: Define known DICOM peers
- `MPPSAet` / `DicomPortMPPS`: Worklist server AE title and port (worklists only)

## Key Technical Details

- The worklist server runs an independent pynetdicom server alongside Orthanc because Orthanc doesn't support MPPS natively
- Korean patient names are automatically romanized using `korean-romanizer` for US modality compatibility
- Worklist items sync from EMR both on a 5-minute interval AND on every C-FIND request
- SQLite database stored at `/etc/orthanc/WorklistsDatabase/worklist.db` (mounted volume for persistence)
