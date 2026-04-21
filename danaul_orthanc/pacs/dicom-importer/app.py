import os
from io import BytesIO

from flask import Flask, jsonify, render_template, request
from pydicom import dcmread, dcmwrite
from pydicom.filebase import DicomFileLike
import requests as http_requests

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4 GB

ORTHANC_URL = os.environ.get('ORTHANC_URL', 'http://orthanc-pacs:8042')
ORTHANC_USER = os.environ.get('ORTHANC_USER', 'demo')
ORTHANC_PASSWORD = os.environ.get('ORTHANC_PASSWORD', 'demo')


def try_fix_mojibake(s):
    """Re-decode EUC-KR bytes that pydicom decoded as Latin-1."""
    try:
        raw = s.encode('latin-1')
        if any(b > 0x7F for b in raw):
            return raw.decode('euc-kr')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s


def decode_patient_name(ds):
    """Return PatientName as a clean UTF-8 string, repairing EUC-KR mojibake."""
    raw = str(getattr(ds, 'PatientName', '') or '')
    return try_fix_mojibake(raw)


def dataset_to_bytes(ds):
    with BytesIO() as buf:
        f = DicomFileLike(buf)
        dcmwrite(f, ds, write_like_original=False)
        f.seek(0)
        return f.read()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/scan-file', methods=['POST'])
def scan_file():
    """Receive one file, return detected PatientID and PatientName."""
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file provided'}), 400
    try:
        ds = dcmread(BytesIO(f.read()), force=True)
        detected_id = try_fix_mojibake(str(getattr(ds, 'PatientID', '') or ''))
        detected_name = decode_patient_name(ds)
    except Exception:
        detected_id = ''
        detected_name = ''
    return jsonify({'detectedId': detected_id, 'detectedName': detected_name})


@app.route('/upload-files', methods=['POST'])
def upload_files():
    """Receive files[] + patientId + patientName, modify tags, upload to Orthanc."""
    files = request.files.getlist('files')
    patient_id = request.form.get('patientId', '')
    patient_name = request.form.get('patientName', '')

    if not files:
        return jsonify({'error': 'No files provided'}), 400

    imported, failed, errors = 0, 0, []

    for f in files:
        try:
            ds = dcmread(BytesIO(f.read()), force=True)
            ds.PatientID = patient_id
            ds.PatientName = patient_name
            ds.SpecificCharacterSet = 'ISO_IR 192'
            dicom_bytes = dataset_to_bytes(ds)
            resp = http_requests.post(
                f'{ORTHANC_URL}/instances',
                data=dicom_bytes,
                auth=(ORTHANC_USER, ORTHANC_PASSWORD),
                headers={'Content-Type': 'application/dicom'},
                timeout=30,
            )
            resp.raise_for_status()
            imported += 1
        except Exception as e:
            failed += 1
            errors.append({'file': f.filename, 'error': str(e)})

    return jsonify({'imported': imported, 'failed': failed, 'errors': errors})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
