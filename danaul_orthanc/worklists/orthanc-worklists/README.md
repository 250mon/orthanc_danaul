# DICOM Worklist Server with MPPS Support

This is a DICOM Modality Worklist Server with MPPS (Modality Performed Procedure Step) support for Orthanc. It uses pynetdicom to implement a worklist server that can respond to C-FIND requests for scheduled exams and support MPPS N-CREATE and N-SET operations.

## Features

- DICOM Modality Worklist server (MWL)
- MPPS support for tracking study status
- SQLAlchemy ORM for database operations
- SQLite database for storing worklist data
- Sample data provided for testing
- Support for filtering by modality, date, and accession number

## Configuration

The worklist server is configured in the orthanc.json file with the following parameters:

```json
{
  "MPPSAet": "WORKLISTS",    // The AE title of the worklist server
  "DicomPortMPPS": 5243      // The port number for the worklist server
}
```

## Database

The worklist data is stored in an SQLite database located at `/etc/orthanc/WorklistsDatabase/worklist.db`. It uses SQLAlchemy for object-relational mapping and contains three models:

1. `Patient` - Patient information
2. `WorklistItem` - Scheduled procedures
3. `MPPSTracking` - Status tracking for MPPS

Sample data is automatically loaded when the server starts.

### Database Schema

The database schema is defined using SQLAlchemy models:

```python
class Patient(Base):
    __tablename__ = 'patients'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, unique=True, nullable=False)
    patient_name = Column(String, nullable=False)
    birth_date = Column(String)
    sex = Column(String)
    
    # Relationship with worklist items
    worklist_items = relationship("WorklistItem", back_populates="patient")

class WorklistItem(Base):
    __tablename__ = 'worklist_items'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey('patients.patient_id'), nullable=False)
    accession_number = Column(String, unique=True, nullable=False)
    appointment_date = Column(String, nullable=False)
    appointment_time = Column(String, nullable=False)
    modality = Column(String, nullable=False)
    study_instance_uid = Column(String)
    status = Column(String, default='SCHEDULED')
    
    # Relationships
    patient = relationship("Patient", back_populates="worklist_items")
    mpps_trackings = relationship("MPPSTracking", back_populates="worklist_item")

class MPPSTracking(Base):
    __tablename__ = 'mpps_tracking'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sop_instance_uid = Column(String, unique=True, nullable=False)
    accession_number = Column(String, ForeignKey('worklist_items.accession_number'), nullable=False)
    study_instance_uid = Column(String, nullable=False)
    modality = Column(String, nullable=False)
    status = Column(String, nullable=False)
    start_time = Column(DateTime, default=func.now())
    end_time = Column(DateTime)
    
    # Relationship
    worklist_item = relationship("WorklistItem", back_populates="mpps_trackings")
```

## Testing the Server

### Querying the Worklist

You can test the worklist server with the findscu command:

```bash
# Query all worklist items
findscu -v -W localhost 5243

# Query by accession number
findscu -v -W -k "AccessionNumber=4567" localhost 5243

# Query by modality
findscu -v -W -k "(0040,0100)[0].Modality=MR" localhost 5243

# Query by date
findscu -v -W -k "(0040,0100)[0].ScheduledProcedureStepStartDate=YYYYMMDD" localhost 5243

# Combined query
findscu -v -W -k "PatientName=" -k "(0040,0100)[0].Modality=MR" -k "(0040,0100)[0].ScheduledProcedureStepStartDate=YYYYMMDD" localhost 5243
```

### Testing MPPS

You can use the DCMTK tool `dump2dcm` to create MPPS N-CREATE and N-SET requests:

1. Create an N-CREATE request file:

```
# Create a file named mpps-in-progress.txt with:
(0008,0050) LO [4567]              # Accession Number
(0008,0060) CS [MR]                # Modality
(0040,0270) SQ                     # Scheduled Step Attributes Sequence
  (fffe,e000) -                    # Item
    (0008,0050) LO [4567]          # Accession Number
    (0020,000d) UI [<StudyUID>]    # Study Instance UID
  (fffe,e00d) -                    # Item Delimiter
(fffe,e0dd) -                      # Sequence Delimiter
(0040,0252) CS [IN PROGRESS]       # Performed Procedure Step Status
```

2. Convert to DICOM format:
```bash
dump2dcm mpps-in-progress.txt mpps-in-progress.dcm
```

3. Send the N-CREATE request:
```bash
echo "mpps-n-create <SOP-Instance-UID>" | dcmpsmk localhost 5243
```

4. Create an N-SET request file for completion:
```
# Create a file named mpps-completed.txt with:
(0040,0252) CS [COMPLETED]         # Performed Procedure Step Status
```

5. Convert to DICOM format:
```bash
dump2dcm mpps-completed.txt mpps-completed.dcm
```

6. Send the N-SET request:
```bash
echo "mpps-n-set <SOP-Instance-UID>" | dcmpsmk localhost 5243
```

## Troubleshooting

- Check the Orthanc logs for any errors related to the worklist server
- Verify that the specified port is available
- Ensure the database permissions are correct
- Make sure the AE titles match between server and client
- If the server doesn't respond, try restarting Orthanc

## Development

The main components of the worklist server are:

- `worklist-with-mpps.py`: The main worklist server implementation
- `model.py`: SQLAlchemy database models and operations
- `orthanc.json`: Configuration for Orthanc and the worklist server

The code is designed to be easily extended with additional functionality. 