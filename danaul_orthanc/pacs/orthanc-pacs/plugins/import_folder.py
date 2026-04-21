import json
import os
import re
from io import BytesIO

import orthanc
from pydicom import dcmread, dcmwrite
from pydicom.filebase import DicomFileLike


def parse_folder_name(folder_name):
    """
    Parse a folder name like '9895함의영' into (patient_id, patient_name).
    Leading digits become the patient ID; the rest becomes the patient name.
    """
    match = re.match(r'^(\d+)(.+)$', folder_name.strip())
    if match:
        return match.group(1), match.group(2)
    return None, None


def dataset_to_bytes(ds):
    with BytesIO() as buf:
        f = DicomFileLike(buf)
        dcmwrite(f, ds, write_like_original=False)
        f.seek(0)
        return f.read()


def ImportFolder(output, uri, **request):
    if request['method'] != 'POST':
        output.SendMethodNotAllowed('POST')
        return

    try:
        body = json.loads(request['body'])
        folder_path = body.get('folder', '').strip()
    except Exception as e:
        output.SendHttpStatus(400, f'Invalid JSON: {e}')
        return

    if not folder_path:
        output.SendHttpStatus(400, 'Missing "folder" parameter')
        return

    folder_name = os.path.basename(os.path.normpath(folder_path))
    patient_id, patient_name = parse_folder_name(folder_name)

    if not patient_id or not patient_name:
        output.SendHttpStatus(
            400,
            f'Cannot parse patient info from folder name: "{folder_name}". '
            'Expected format: <digits><name>  e.g. "9895함의영"'
        )
        return

    if not os.path.isdir(folder_path):
        output.SendHttpStatus(404, f'Folder not found: {folder_path}')
        return

    orthanc.LogInfo(f'ImportFolder: path="{folder_path}" PatientID={patient_id} PatientName={patient_name}')

    imported, failed, errors = 0, 0, []

    for root, _, files in os.walk(folder_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            try:
                ds = dcmread(file_path, force=True)
                ds.PatientID = patient_id
                ds.PatientName = patient_name
                ds.SpecificCharacterSet = 'ISO_IR 192'
                orthanc.RestApiPost('/instances', dataset_to_bytes(ds))
                imported += 1
                orthanc.LogInfo(f'Imported: {file_path}')
            except Exception as e:
                failed += 1
                errors.append({'file': filename, 'error': str(e)})
                orthanc.LogWarning(f'Failed to import {file_path}: {e}')

    result = {
        'patientId': patient_id,
        'patientName': patient_name,
        'imported': imported,
        'failed': failed,
        'errors': errors,
    }
    orthanc.LogInfo(f'ImportFolder done: {imported} imported, {failed} failed')
    output.AnswerBuffer(json.dumps(result, ensure_ascii=False), 'application/json')


orthanc.RegisterRestCallback('/import-folder', ImportFolder)
