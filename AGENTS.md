# Repository Guidelines

## Project Structure & Module Organization
`orthanc-setup-samples/` contains reusable Orthanc examples, mostly organized as one sample per folder under `docker/`, plus shared `lua-samples/` and `python-samples/`. `danaul_orthanc/` holds project-specific deployments: `pacs/` for the PACS stack, `worklists/` for MWL/MPPS work, `orthanc-modality/` for modality-side setup, and `plugins/` for local plugin experiments. Keep service-specific assets close to their stack, such as `docker-compose.yml`, `Dockerfile`, `orthanc.json`, and plugin scripts in the same subtree.

## Build, Test, and Development Commands
Use Docker Compose from the target sample or stack directory.

- `cd danaul_orthanc/pacs && docker compose up --build`: build and run the PACS stack.
- `cd danaul_orthanc/worklists && docker compose up --build`: start the worklist environment.
- `cd orthanc-setup-samples/docker/<sample> && docker compose up --build`: run a specific reference sample.
- `docker compose down -v`: stop containers and remove attached volumes for a clean rerun.
- `python3 danaul_orthanc/pacs/send_folder.py`: send local studies to a configured PACS endpoint when validating imports.

## Coding Style & Naming Conventions
Python code uses 4-space indentation, `snake_case` for functions/files, and short module-level constants in `UPPER_CASE` such as `ORTHANC_URL`. Prefer small, single-purpose plugin scripts under `plugins/`. Keep JSON config keys aligned with Orthanc naming and avoid reformatting large config blocks unless needed. There is no enforced formatter in the repo, so match surrounding style and keep comments brief and operational.

## Testing Guidelines
There is no centralized unit test suite at the repository root. Validate changes by bringing up the affected Compose stack and checking container logs and Orthanc endpoints. For broader coverage, use the integration setups in `orthanc-setup-samples/docker/orthanc-integration-tests/`, for example: `COMPOSE_FILE=docker-compose.sqlite.yml docker-compose up --build --exit-code-from orthanc-tests --abort-on-container-exit`. Name any new Python tests `test_*.py` and place them beside the feature they verify.

## Commit & Pull Request Guidelines
Recent history uses short, informal commit subjects (`first commit`, `pushed the images into the docker hub`). For new work, prefer concise imperative messages such as `Add PACS import plugin`. PRs should describe the affected stack, list changed config or ports, include exact verification commands, and attach screenshots only when UI templates such as `dicom-importer/templates/` change.

## Security & Configuration Tips
This repo contains sample credentials and environment-specific config. Do not commit real secrets, patient data, or private endpoints. Treat files under import/storage directories and `*.db` artifacts as local runtime data unless the change explicitly updates sample fixtures.
