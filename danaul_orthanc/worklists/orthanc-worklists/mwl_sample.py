#!/usr/bin/env python3
# Make it execuatble if you want to use the shebang

import datetime
import os
import re
import time
from datetime import datetime

import pydicom  # https://github.com/pydicom/pydicom, sudo python3 -m pip install pydicom
from pydicom import dcmread, dcmwrite
from pydicom.datadict import dictionary_keyword
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.filebase import DicomFileLike
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

mwljson = {
    "AccessionNumber": "000006656500100",
    "PatientID": "6",
    "PatientBirthDate": "19821218",
    "PatientName": "PJH",
    "PatientSex": "F",
    "RequestedProcedureDescription": "US3",
    "RequestedProcedurePriority": "Routine",
    "RequestingPhysician": "SJY",
    "ScheduledProcedureStepSequence": [
        {
            "Modality": "US",
            "ScheduledStationAETitle": "XC70",
            "ScheduledProcedureStepStartDate": "20250315",
            "ScheduledProcedureStepStartTime": "201000",
            "ScheduledStationName": "US_Room1",
        }
    ],
    "SpecificCharacterSet": "ISO_IR 100",
    "StudyDescription": "MWL TEST STUDY",
    "StudyInstanceUID": "",
}


WORKLIST_DIR = "WorklistsDatabase"

# METHOD TO CONSTRUCT DATASET FROM JSON, SEE SAMPLE, PASS IN the JSON for the Dataset and a Blank Dataset


def utf8len(s):
    return len(s.encode("utf-8"))


def getMWLFromJSON(MWLDict, DataSet):

    for key, value in MWLDict.items():
        if isinstance(value, str) or isinstance(value, int):
            setattr(DataSet, key, value)
        else:  # must be a list or sequence
            # setattr(mwlDataSet, key, Dataset())
            sequence = []
            # Create the Sequence Blank Dataset
            for i in range(len(value)):
                sequenceSet = Dataset()
                sequenceSet = getMWLFromJSON(value[i], sequenceSet)
                sequence.append(sequenceSet)
            setattr(DataSet, key, sequence)
    return DataSet


def MWLFromJSONCreateAndSave(sample):

    response = dict()
    print("Making MWL from JSON")
    dataset = Dataset()
    dataset = getMWLFromJSON(sample, dataset)
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
    dataset.file_meta.ImplementationVersionName = "ORTHANC_PY_MWL"
    dataset.file_meta.MediaStorageSOPClassUID = "0"
    dataset.file_meta.MediaStorageSOPInstanceUID = "0"

    dataset.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    dataset.is_little_endian = (
        dataset.file_meta.TransferSyntaxUID.is_little_endian
    )  # 'Dataset.is_little_endian' and 'Dataset.is_implicit_VR' must be set appropriately before saving
    dataset.is_implicit_VR = dataset.file_meta.TransferSyntaxUID.is_implicit_VR
    # Set creation date/time
    dt = datetime.now()
    dataset.ContentDate = dt.strftime("%Y%m%d")
    timeStr = dt.strftime("%H%M%S.%f")  # long format with micro seconds
    dataset.ContentTime = timeStr
    print(dataset)
    filename = sample["AccessionNumber"] + ".wl"
    dataset.save_as(os.path.join(WORKLIST_DIR, filename), write_like_original=False)


mwl = MWLFromJSONCreateAndSave(mwljson)
