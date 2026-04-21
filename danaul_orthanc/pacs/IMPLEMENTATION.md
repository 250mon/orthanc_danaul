# DICOM Import Web UI — Implementation Plan

## Overview

A new `dicom-importer` Flask service added to the existing `pacs/docker-compose.yml`.
It provides a browser UI to scan a folder of `.dcm` files, edit patient ID/name, and
upload the modified files to the Orthanc PACS container.

---

## File Structure to Create

```
pacs/
├── docker-compose.yml              ← MODIFY: add dicom-importer service
└── dicom-importer/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py
    └── templates/
        └── index.html
```

---

## Step 1 — `dicom-importer/requirements.txt`

```
flask
pydicom
requests
```

---

## Step 2 — `dicom-importer/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY templates/ templates/
CMD ["python", "app.py"]
```

---

## Step 3 — `dicom-importer/app.py`

Three routes:

### `GET /`
Renders `index.html` with the path input field pre-filled to `/import`.

### `POST /scan`
- Request JSON: `{ "path": "/mnt/e/PatientFolder" }`
- Walks the given directory recursively for `.dcm` files (uses `pydicom.dcmread(..., force=True)` to safely probe files)
- Groups files by their **immediate parent subdirectory** (each subfolder = one patient batch)
- For each folder, reads the first `.dcm` file to extract current `PatientID` and `PatientName` tags
- Response JSON:
  ```json
  [
    {
      "folder": "/mnt/e/PatientFolder/9723장한",
      "folderName": "9723장한",
      "detectedId": "9723",
      "detectedName": "장한",
      "fileCount": 42
    }
  ]
  ```

### `POST /upload`
- Request JSON:
  ```json
  [
    {
      "folder": "/mnt/e/PatientFolder/9723장한",
      "patientId": "9723",
      "patientName": "장한"
    }
  ]
  ```
- For each entry, walks the folder, reads every `.dcm` file with pydicom, sets:
  - `ds.PatientID = patientId`
  - `ds.PatientName = patientName`
  - `ds.SpecificCharacterSet = 'ISO_IR 192'`
- Serializes the modified dataset to bytes (using `DicomFileLike` + `dcmwrite`, same pattern as `import_folder.py`)
- POSTs bytes to `http://orthanc-pacs:8042/instances` with Basic Auth `demo:demo`
- Response JSON per folder:
  ```json
  { "folder": "9723장한", "imported": 42, "failed": 0, "errors": [] }
  ```

**Key reuse from `orthanc-pacs/plugins/import_folder.py`:**
- `dataset_to_bytes(ds)` — identical helper using `BytesIO` + `DicomFileLike` + `dcmwrite`
- Tag-setting pattern: `ds.PatientID`, `ds.PatientName`, `ds.SpecificCharacterSet`
- Orthanc REST call pattern: POST to `/instances` with binary body

**Environment variables read by `app.py`:**
| Variable | Default | Purpose |
|----------|---------|---------|
| `ORTHANC_URL` | `http://orthanc-pacs:8042` | Orthanc base URL |
| `ORTHANC_USER` | `demo` | Basic auth user |
| `ORTHANC_PASSWORD` | `demo` | Basic auth password |
| `IMPORT_DIR` | `/import` | Default path shown in UI |

---

## Step 4 — `dicom-importer/templates/index.html`

Single-page UI using Bootstrap 5 (CDN). No build step needed.

**Layout:**
1. **Header** — "DICOM Importer"
2. **Scan panel** — text input for folder path (default: `/import`) + "Scan" button
3. **Results table** — rendered after scan, columns:
   | Folder | Files | Current ID | Current Name | New Patient ID | New Patient Name |
   |--------|-------|------------|--------------|----------------|------------------|
   | (readonly) | (readonly) | (readonly) | (readonly) | `<input>` | `<input>` |
4. **Upload button** — collects all rows, POSTs to `/upload`, shows per-row status inline

**JS flow (vanilla JS, no framework):**
```
Scan button click
  → fetch POST /scan { path }
  → render table rows from response

Upload button click
  → collect [{ folder, patientId, patientName }] from table inputs
  → fetch POST /upload [...]
  → update each row with ✓ imported / ✗ failed count
```

---

## Step 5 — Modify `docker-compose.yml`

Add to the `services:` section:

```yaml
  dicom-importer:
    build: ./dicom-importer
    container_name: danaul_dicom_importer
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./import:/import:ro
      - /mnt:/mnt:ro          # WSL2 USB drives appear at /mnt/<letter>/
    depends_on:
      - orthanc-pacs
    environment:
      ORTHANC_URL: "http://orthanc-pacs:8042"
      ORTHANC_USER: "demo"
      ORTHANC_PASSWORD: "demo"
      IMPORT_DIR: "/import"
```

> **Note on `/mnt` mount:** In WSL2, Windows drives and USB drives are accessible
> at `/mnt/c/`, `/mnt/d/`, `/mnt/e/`, etc. Mounting `/mnt` read-only into the
> container makes them available for scanning without copying files first.

---

## Step 6 — Verification

```bash
# 1. Build and start all services
cd pacs/
docker compose up -d --build

# 2. Check the importer is running
docker logs danaul_dicom_importer

# 3. Open the UI
# http://localhost:5000

# 4. Test with local import folder
# - Place .dcm files in pacs/import/9999TestPatient/
# - In UI: path = /import, click Scan
# - Verify folder appears with detected ID/name
# - Edit values, click Upload
# - Check http://localhost:8042 (demo/demo) for the uploaded patient

# 5. Test with USB drive
# - Insert USB, note its path (e.g. /mnt/e/)
# - In UI: path = /mnt/e/PatientFolder, click Scan
# - Proceed as above
```

---

## Notes

- The importer container talks to Orthanc via the **Docker internal network** (`orthanc-pacs:8042`), not `localhost:8042`.
- Files are read **read-only** from disk; modifications happen **in memory** only — original files on disk are never changed.
- Korean patient names work because `SpecificCharacterSet = ISO_IR 192` (UTF-8) is set on every file, and Orthanc's `euckr_to_utf8.py` plugin will further normalize on receipt.
- If a `.dcm` file cannot be parsed by pydicom, it is counted as `failed` and skipped — the rest of the folder continues uploading.
