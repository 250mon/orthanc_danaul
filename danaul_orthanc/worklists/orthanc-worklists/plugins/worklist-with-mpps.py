# This script is a boilerplate script to implement a worklist server
# with MPPS support.  As of v 1.12.4, Orthanc does not support MPPS
# therefore, this script implements an independant worklist server
# with pydicom.

# This worklist server uses 2 configurations from the Orthanc configuration file:
# "MPPSAet": the AET of this worklist server
# "DicomPortMPPS": the port to be used (must be different from Orthanc DicomPort)

# The script assumes you have a DB with the scheduled exams available.
# This DB being user specific, the interface code with the DB is not included in the script.
# Check the TODO-DB placeholders.

# This script is implemented as an Orthanc python plugin.  Orthanc is
# only responsible for starting/stopping the worklist server and providing the configuration.

# test command:
# findscu -v -W  -k "PatientName=" -k "(0040,0100)[0].Modality=MR" -k "(0040,0100)[0].ScheduledProcedureStepStartDate=20240101" localhost 4243

import datetime
import json
from io import BytesIO
import traceback

import orthanc
import pynetdicom
from pydicom.dataset import Dataset, FileDataset
from pydicom.uid import (
    ExplicitVRBigEndian,
    ExplicitVRLittleEndian,
    ImplicitVRLittleEndian,
    generate_uid,
)
from pynetdicom import AE, evt
from pynetdicom.sop_class import (
    ModalityPerformedProcedureStep,
    ModalityWorklistInformationFind,
    Verification,
)

# Import the database model
import worklist_model

worklist_server = None

managed_instances = {}

# Connect to the database
def init_database():
    """Initialize the database"""
    try:
        worklist_model.init_db()
        orthanc.LogInfo("Database initialized successfully")
    except Exception as e:
        orthanc.LogError(f"Error initializing database: {e}")


def handle_find(event):
    """Handle a C-FIND request event."""
    try:
        ds = event.identifier
        orthanc.LogInfo(f"C-FIND request received with dataset: {ds}")
        dsArray = find_worklist(ds)

        # Import stored SOP Instances
        instances = []
        for instance in dsArray:
            # Check if C-CANCEL has been received
            if event.is_cancelled:
                yield (0xFE00, None)
                return
            # Pending
            yield (0xFF00, instance)
        # Indicate that no more data is available
        yield 0x0000, None  # Success status, no more datasets
    except Exception as e:
        s = str(e)
        orthanc.LogError(f"Error in handle_find: {s}")
        orthanc.LogError(traceback.format_exc())


# Implement the evt.EVT_N_CREATE handler
def handle_create(event):

    # Create a Modality Performed Procedure Step SOP Class Instance
    #   DICOM Standard, Part 3, Annex B.17
    ds = Dataset()
    try:
        # MPPS' N-CREATE request must have an *Affected SOP Instance UID*
        req = event.request
        # identifier = event.identifier
        if req.AffectedSOPInstanceUID is None:
            # Failed - invalid attribute value
            orthanc.LogWarning("N-CREATE failed: Missing SOP Instance UID")
            return 0x0106, None

        # Can't create a duplicate SOP Instance
        if req.AffectedSOPInstanceUID in managed_instances:
            # Failed - duplicate SOP Instance
            orthanc.LogWarning(f"N-CREATE failed: Duplicate SOP Instance UID {req.AffectedSOPInstanceUID}")
            return 0x0111, None

        # The N-CREATE request's *Attribute List* dataset
        attr_list = event.attribute_list

        # Performed Procedure Step Status must be 'IN PROGRESS'
        if "PerformedProcedureStepStatus" not in attr_list:
            # Failed - missing attribute
            orthanc.LogWarning("N-CREATE failed: Missing PerformedProcedureStepStatus")
            return 0x0120, None

        if attr_list.PerformedProcedureStepStatus.upper() != "IN PROGRESS":
            orthanc.LogWarning(f"N-CREATE failed: Invalid status {attr_list.PerformedProcedureStepStatus}")
            return 0x0106, None

        # Skip other tests...

        # Add the SOP Common module elements (Annex C.12.1)
        ds.SOPClassUID = ModalityPerformedProcedureStep
        ds.SOPInstanceUID = req.AffectedSOPInstanceUID

        # Update with the requested attributes
        ds.update(attr_list)

        # Add the dataset to the managed SOP Instances
        managed_instances[ds.SOPInstanceUID] = ds

        modality = attr_list.Modality
        accession_number = attr_list.ScheduledStepAttributesSequence[0].AccessionNumber
        study_instance_uid = attr_list.ScheduledStepAttributesSequence[
            0
        ].StudyInstanceUID

        orthanc.LogInfo(f"N-CREATE request for accession {accession_number}, modality {modality}")

        # Update the DB to record that this study acquisition has been started
        success = worklist_model.record_mpps_in_progress(
            req.AffectedSOPInstanceUID, 
            modality, 
            accession_number, 
            study_instance_uid
        )
        
        if not success:
            orthanc.LogWarning(f"Failed to record MPPS in progress for accession {accession_number}")
        else:
            orthanc.LogInfo(f"Successfully recorded MPPS in progress for accession {accession_number}")

    except Exception as e:
        s = str(e)
        orthanc.LogError(f"Error in handle_create: {s}")
        orthanc.LogError(traceback.format_exc())

    return 0x0000, ds


# Implement the evt.EVT_N_SET handler
def handle_set(event):
    req = event.request
    if req.RequestedSOPInstanceUID not in managed_instances:
        # Failure - SOP Instance not recognised
        orthanc.LogWarning(f"N-SET failed: SOP Instance UID not found: {req.RequestedSOPInstanceUID}")
        return 0x0112, None

    ds = managed_instances[req.RequestedSOPInstanceUID]

    # The N-SET request's *Modification List* dataset
    mod_list = event.attribute_list
    
    orthanc.LogInfo(f"N-SET request received for SOP Instance UID: {req.RequestedSOPInstanceUID}")

    try:
        # Update the DB to record that this study acquisition is complete
        success, accession_number = worklist_model.record_mpps_completed(req.RequestedSOPInstanceUID)
        
        if not success:
            orthanc.LogWarning(f"Failed to record MPPS completion for SOP Instance {req.RequestedSOPInstanceUID}")
        else:
            orthanc.LogInfo(f"Recorded MPPS completion for accession {accession_number}")

        ds.update(mod_list)
    except Exception as e:
        orthanc.LogError(f"Error in handle_set: {e}")
        orthanc.LogError(traceback.format_exc())

    # Return status, dataset
    return 0x0000, ds


def find_worklist(requestedDS):
    """Handle a C-FIND request event."""
    worklist_objects = []
    
    # Log the entire dataset for debugging
    orthanc.LogInfo(f"Worklist request: {requestedDS}")

    # First, sync with EMR to get any new records
    try:
        new_count = worklist_model.sync_emr_orders()
        if new_count > 0:
            orthanc.LogInfo(f"Added {new_count} new orders from EMR during C-FIND")
    except Exception as e:
        orthanc.LogError(f"Error syncing EMR during C-FIND: {e}")
        orthanc.LogError(traceback.format_exc())

    # Check if the request includes the Scheduled Procedure Step Sequence
    sps_modality = None  # Default to no modality filter
    sps_date = None
    
    if hasattr(requestedDS, 'ScheduledProcedureStepSequence') and requestedDS.ScheduledProcedureStepSequence:
        if hasattr(requestedDS.ScheduledProcedureStepSequence[0], 'ScheduledProcedureStepStartDate'):
            sps_date = requestedDS.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate
        
        if hasattr(requestedDS.ScheduledProcedureStepSequence[0], 'Modality'):
            sps_modality = requestedDS.ScheduledProcedureStepSequence[0].Modality
    
    # Check for AccessionNumber in the request
    accession_number = getattr(requestedDS, 'AccessionNumber', '*')
    
    orthanc.LogInfo(f"Searching for worklist items with modality: {sps_modality}, date: {sps_date}, accession: {accession_number}")

    # Query the database for worklist items
    db_items = worklist_model.get_worklist_items(modality=sps_modality, date=sps_date, accession_number=accession_number)
    orthanc.LogInfo(f"Found {len(db_items)} worklist items in database")
    
    for item in db_items:
        ds = Dataset()
        ds.is_little_endian = True
        ds.is_implicit_VR = True
        
        # Add the necessary elements
        if item['modality'] == "US":
            ds.PatientName = item['patient_eng_name']
        else:
            ds.PatientName = item['patient_name']
        ds.PatientID = item['patient_id']
        ds.SpecificCharacterSet = "ISO_IR 192"
        ds.PatientBirthDate = item['birth_date']
        ds.PatientSex = item['sex']

        # Create the scheduled procedure step sequence
        sps = Dataset()
        sps.Modality = item['modality']
        sps.ScheduledStationAETitle = item['aet']
        sps.ScheduledProcedureStepStartDate = item['appointment_date']
        sps.ScheduledProcedureStepStartTime = item['appointment_time']
        sps.ScheduledPerformingPhysicianName = ""
        sps.ScheduledProcedureStepDescription = ""

        # Add the Scheduled Procedure Step Sequence to the dataset
        ds.ScheduledProcedureStepSequence = [sps]

        # Add other necessary elements
        ds.AccessionNumber = item['accession_number']
        
        # Generate or use existing StudyInstanceUID
        if item['study_instance_uid']:
            ds.StudyInstanceUID = item['study_instance_uid']
        else:
            ds.StudyInstanceUID = generate_uid()
            
            # Update the database with the generated UID using SQLAlchemy
            success = worklist_model.update_study_instance_uid(item['accession_number'], ds.StudyInstanceUID)
            if not success:
                orthanc.LogWarning(f"Error updating study UID for accession {item['accession_number']}")
            else:
                orthanc.LogInfo(f"Updated study UID for accession {item['accession_number']}")

        ds.StudyID = item['accession_number']
        worklist_objects.append(ds)
        
    orthanc.LogInfo(f"Returning {len(worklist_objects)} worklist objects")
    return worklist_objects


# Define a handler for the C-ECHO request (Verification)
def handle_echo(event):
    """Handle a C-ECHO request event."""
    orthanc.LogInfo("C-ECHO request received")
    return 0x0000


def OnChange(changeType, level, resourceId):
    global worklist_server

    try:
        # start the worklist server when Orthanc starts
        if changeType == orthanc.ChangeType.ORTHANC_STARTED:
            # Initialize the database
            init_database()

            # Define your custom AE title & port
            mpps_aet = json.loads(orthanc.GetConfiguration()).get("MPPSAet", "ORTHANC")
            mpps_port = json.loads(orthanc.GetConfiguration()).get(
                "DicomPortMPPS", 5243
            )

            # Specify the supported Transfer Syntaxes
            transfer_syntaxes = [
                ExplicitVRLittleEndian,
                ImplicitVRLittleEndian,
                ExplicitVRBigEndian,
            ]

            # Create the Application Entity with the custom AE title
            ae = pynetdicom.AE(ae_title=mpps_aet)
            ae.add_supported_context(ModalityPerformedProcedureStep, transfer_syntaxes)
            ae.add_supported_context(ModalityWorklistInformationFind, transfer_syntaxes)
            ae.add_supported_context(Verification, transfer_syntaxes)

            handlers = [
                (evt.EVT_N_CREATE, handle_create),
                (evt.EVT_N_SET, handle_set),
                (evt.EVT_C_FIND, handle_find),
                (evt.EVT_C_ECHO, handle_echo),
            ]
            worklist_server = ae.start_server(
                ("0.0.0.0", mpps_port), block=False, evt_handlers=handlers
            )

            orthanc.LogInfo(f"Worklist server using pynetdicom has started on port {mpps_port} with AET {mpps_aet}")

        elif changeType == orthanc.ChangeType.ORTHANC_STOPPED:
            orthanc.LogInfo("Stopping pynetdicom Worklist server ")
            if worklist_server:
                worklist_server.shutdown()
            else:
                orthanc.LogWarning("No worklist server to stop")

    except Exception as e:
        s = str(e)
        orthanc.LogError(f"Error in OnChange: {s}")
        orthanc.LogError(traceback.format_exc())


orthanc.RegisterOnChangeCallback(OnChange)
