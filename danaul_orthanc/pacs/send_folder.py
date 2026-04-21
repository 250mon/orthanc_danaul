import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pydicom import dcmread, dcmwrite


def process_folder(folder_path):
    folder = Path(folder_path)
    if not folder.is_dir():
        print(f'[SKIP] Not a directory: {folder}')
        return

    match = re.match(r'^(\d+)(.+)$', folder.name.strip())
    if not match:
        print(f'[SKIP] Cannot parse patient info from "{folder.name}"')
        return

    patient_id, patient_name = match.group(1), match.group(2)
    print(f'[INFO] {folder.name} -> PatientID={patient_id}, PatientName={patient_name}')

    files = [f for f in folder.rglob('*') if f.is_file()]
    if not files:
        print(f'[SKIP] No files found in {folder}')
        return

    with tempfile.TemporaryDirectory() as tmp:
        converted = 0
        for src in files:
            try:
                ds = dcmread(str(src), force=True)
                ds.PatientID = patient_id
                ds.PatientName = patient_name
                ds.SpecificCharacterSet = 'ISO_IR 192'
                dcmwrite(Path(tmp) / src.name, ds)
                converted += 1
            except Exception as e:
                print(f'[WARN] {src.name}: {e}')

        print(f'[INFO] Sending {converted} files ...')
        subprocess.run(
            [
                'storescu',
                '-aet', 'Danaul_PACS',
                'localhost', '4242',
                '--scan-directories',
                '--recurse',
                '--no-halt',
                tmp,
            ],
            check=True,
        )

    print(f'[DONE] {folder.name}')


if len(sys.argv) < 2:
    sys.exit(f'Usage: {sys.argv[0]} <folder> [folder ...]')

for path in sys.argv[1:]:
    process_folder(path)
