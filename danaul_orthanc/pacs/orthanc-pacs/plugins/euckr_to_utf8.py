from io import BytesIO

from pydicom import dcmread, dcmwrite
from pydicom.charset import decode_bytes
from pydicom.filebase import DicomFileLike

import orthanc

TEXT_VRS = {"PN", "LO", "LT", "SH", "ST", "UC", "UT"}


def write_dataset_to_bytes(dataset):
    with BytesIO() as buffer:
        f = DicomFileLike(buffer)
        dcmwrite(f, dataset, write_like_original=False)
        f.seek(0)
        return f.read()


def try_fix_mojibake(s):
    """Repair EUC-KR text that pydicom decoded as Latin-1.

    When a DICOM file has no SpecificCharacterSet (or claims ASCII/ISO_IR 6),
    pydicom decodes EUC-KR bytes as Latin-1, producing garbled strings like
    'ÇÔÀÇ¿µ'. This recovers the original bytes and re-decodes as EUC-KR.
    Pure ASCII strings are returned unchanged.
    """
    try:
        raw = s.encode("latin-1")
        if any(b > 0x7F for b in raw):
            return raw.decode("euc-kr")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s


def force_dataset_to_utf8(ds):
    """
    Best-effort normalization:
    1. Assume missing/legacy Korean data should be interpreted as EUC-KR.
    2. Convert string values to Python unicode.
    3. Rewrite SpecificCharacterSet as UTF-8 (ISO_IR 192).
    """

    # If the source omitted charset, assume Korean legacy encoding.
    if "SpecificCharacterSet" not in ds:
        ds.SpecificCharacterSet = "ISO_IR 149"

    for elem in ds.iterall():
        if elem.VR in TEXT_VRS and elem.value not in (None, ""):
            try:
                if isinstance(elem.value, bytes):
                    elem.value = decode_bytes(elem.value, ["ISO_IR 149"])
                elif isinstance(elem.value, list):
                    converted = []
                    for item in elem.value:
                        if isinstance(item, bytes):
                            converted.append(decode_bytes(item, ["ISO_IR 149"]))
                        else:
                            converted.append(try_fix_mojibake(str(item)))
                    elem.value = converted
                else:
                    # elem.value may be a str or PersonName already decoded by
                    # pydicom as Latin-1; repair mojibake before storing.
                    elem.value = try_fix_mojibake(str(elem.value))
            except Exception as e:
                orthanc.LogWarning(f"Failed to normalize tag {elem.tag}: {e}")

    # Rewrite output charset as UTF-8
    ds.SpecificCharacterSet = "ISO_IR 192"
    return ds


def ReceivedInstanceCallback(receivedDicom, origin):
    try:
        ds = dcmread(BytesIO(receivedDicom), force=True)
        ds = force_dataset_to_utf8(ds)
        return orthanc.ReceivedInstanceAction.MODIFY, write_dataset_to_bytes(ds)
    except Exception as e:
        orthanc.LogError(f"EUC-KR->UTF-8 conversion failed: {e}")
        return orthanc.ReceivedInstanceAction.KEEP_AS_IS, None


orthanc.RegisterReceivedInstanceCallback(ReceivedInstanceCallback)

import import_folder
