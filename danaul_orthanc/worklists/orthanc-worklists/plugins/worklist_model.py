import os
import datetime
from typing import List, Dict, Optional, Any, Tuple
import logging
import traceback

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.sql import func
import threading
import time

from korean_romanizer.romanizer import Romanizer
import orthanc
import emr_api

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('worklist_model')

# Try to import emr_api, but handle import errors gracefully
try:
    EMR_API_AVAILABLE = True
    orthanc.LogInfo("EMR API module loaded successfully")
except ImportError as e:
    orthanc.LogWarning(f"Error importing emr_api module: {e}")
    orthanc.LogWarning("EMR sync will be disabled")
    EMR_API_AVAILABLE = False
except Exception as e:
    orthanc.LogError(f"Unexpected error importing emr_api: {e}")
    orthanc.LogWarning("EMR sync will be disabled")
    EMR_API_AVAILABLE = False

# Database path - store in the mounted volume for persistence
DB_PATH = "/etc/orthanc/WorklistsDatabase/worklist.db"
DB_URL = f"sqlite:///{DB_PATH}"

Base = declarative_base()

# Define the models
class Patient(Base):
    __tablename__ = 'patients'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, unique=True, nullable=False)
    patient_name = Column(String, nullable=False)
    patient_eng_name = Column(String)  # New column for English name
    birth_date = Column(String)
    sex = Column(String)
    
    # Relationship with worklist items
    worklist_items = relationship("WorklistItem", back_populates="patient", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Patient {self.patient_name}>"


class WorklistItem(Base):
    __tablename__ = 'worklist_items'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String, ForeignKey('patients.patient_id'), nullable=False)
    accession_number = Column(String, unique=True, nullable=False)
    appointment_date = Column(String, nullable=False)
    appointment_time = Column(String, nullable=False)
    modality = Column(String, nullable=False)
    aet = Column(String)
    study_instance_uid = Column(String)
    status = Column(String, default='SCHEDULED')
    emr_order_seq = Column(Integer)
    
    # Relationships
    patient = relationship("Patient", back_populates="worklist_items")
    mpps_trackings = relationship("MPPSTracking", back_populates="worklist_item", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<WorklistItem {self.accession_number}>"


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
    
    def __repr__(self):
        return f"<MPPSTracking {self.sop_instance_uid}>"


# Add this new class after other model classes
class ModalityAET(Base):
    __tablename__ = 'modality_aets'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    modality = Column(String, nullable=False)
    aet = Column(String, nullable=False)
    
    def __repr__(self):
        return f"<ModalityAET {self.modality}:{self.aet}>"


# Create engine and session factory
def ensure_db_path():
    """Ensure the directory for the database exists"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

engine = None
SessionLocal = None

def get_engine():
    """Get the SQLAlchemy engine, creating it if necessary"""
    global engine
    if engine is None:
        ensure_db_path()
        engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    return engine

def get_session_factory():
    """Get the SQLAlchemy session factory, creating it if necessary"""
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return SessionLocal

def get_db() -> Session:
    """Get a database session"""
    db = get_session_factory()()
    try:
        return db
    except Exception:
        db.close()
        raise

def init_db():
    """Initialize the database with required tables"""
    ensure_db_path()
    
    # Create tables
    Base.metadata.create_all(bind=get_engine())
    
    # Load modality-AET mappings
    load_modality_aets()
    
    # Insert sample data
    # insert_sample_data()
    
    # Start background sync
    if EMR_API_AVAILABLE:
        start_background_sync()

def insert_sample_data():
    """Insert sample data for testing"""
    with get_db() as db:
        # Check if we already have data
        if db.query(Patient).count() > 0:
            return
        
        # Insert sample patients
        patients = [
            Patient(
                patient_id='1234', 
                patient_name='TEST^TEST', 
                patient_eng_name=translate_korean_to_english_name('TEST^TEST'),
                birth_date='19900101', 
                sex='F'
            ),
            Patient(
                patient_id='5678', 
                patient_name='SMITH^JOHN', 
                patient_eng_name=translate_korean_to_english_name('SMITH^JOHN'),
                birth_date='19850215', 
                sex='M'
            ),
            Patient(
                patient_id='9012', 
                patient_name='DOE^JANE', 
                patient_eng_name=translate_korean_to_english_name('DOE^JANE'),
                birth_date='19780330', 
                sex='F'
            )
        ]
        
        db.add_all(patients)
        db.commit()
        
        # Insert sample worklist items
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y%m%d')
        day_after = (datetime.datetime.now() + datetime.timedelta(days=2)).strftime('%Y%m%d')
        
        worklist_items = [
            WorklistItem(patient_id='1234', accession_number='4567', appointment_date=tomorrow, appointment_time='100000', modality='MR'),
            WorklistItem(patient_id='5678', accession_number='8901', appointment_date=day_after, appointment_time='110000', modality='CT'),
            WorklistItem(patient_id='9012', accession_number='2345', appointment_date=tomorrow, appointment_time='140000', modality='US')
        ]
        
        db.add_all(worklist_items)
        db.commit()

def get_worklist_items(modality: str = None, date: str = None, accession_number: str = None) -> List[Dict[str, Any]]:
    """
    Get worklist items from the database
    Filters by modality, date and/or accession number if provided
    """
    with get_db() as db:
        query = db.query(
            WorklistItem.accession_number,
            WorklistItem.appointment_date,
            WorklistItem.appointment_time,
            WorklistItem.modality,
            WorklistItem.study_instance_uid,
            WorklistItem.aet,
            Patient.patient_id,
            Patient.patient_name,
            Patient.patient_eng_name,
            Patient.birth_date,
            Patient.sex
        ).join(Patient).filter(WorklistItem.status == 'SCHEDULED')
        
        if accession_number and accession_number != '*':
            query = query.filter(WorklistItem.accession_number == accession_number)
        
        if date:
            query = query.filter(WorklistItem.appointment_date == date)
            
        if modality:
            query = query.filter(WorklistItem.modality == modality)
        
        results = []
        for row in query.all():
            results.append({
                'accession_number': row.accession_number,
                'appointment_date': row.appointment_date,
                'appointment_time': row.appointment_time,
                'modality': row.modality,
                'study_instance_uid': row.study_instance_uid,
                'aet': row.aet,
                'patient_id': row.patient_id,
                'patient_name': row.patient_name,
                'patient_eng_name': row.patient_eng_name,
                'birth_date': row.birth_date,
                'sex': row.sex
            })
        
        return results

def record_mpps_in_progress(sop_instance_uid: str, modality: str, 
                            accession_number: str, study_instance_uid: str) -> bool:
    """
    Record that an MPPS has started for a worklist item
    """
    try:
        with get_db() as db:
            # Update worklist item status
            worklist_item = db.query(WorklistItem).filter(
                WorklistItem.accession_number == accession_number
            ).first()
            
            if not worklist_item:
                return False
            
            worklist_item.status = 'IN PROGRESS'
            
            # Add MPPS tracking entry
            mpps = MPPSTracking(
                sop_instance_uid=sop_instance_uid,
                accession_number=accession_number,
                study_instance_uid=study_instance_uid,
                modality=modality,
                status='IN PROGRESS',
                start_time=datetime.datetime.now()
            )
            
            db.add(mpps)
            db.commit()
            
            # If EMR API is available, update the EMR status
            if EMR_API_AVAILABLE and worklist_item.emr_order_seq:
                try:
                    emr_api.update_order_status(worklist_item.emr_order_seq, 'IP')
                except Exception as e:
                    orthanc.LogError(f"Failed to update EMR status: {e}")
            
            return True
    except Exception as e:
        orthanc.LogError(f"Error recording MPPS in progress: {e}")
        return False

def record_mpps_completed(sop_instance_uid: str) -> Tuple[bool, Optional[str]]:
    """
    Record that an MPPS has completed
    Returns (success, accession_number)
    """
    try:
        with get_db() as db:
            # Get the MPPS tracking entry
            mpps = db.query(MPPSTracking).filter(
                MPPSTracking.sop_instance_uid == sop_instance_uid
            ).first()
            
            if not mpps:
                return False, None
            
            accession_number = mpps.accession_number
            
            # Update MPPS tracking entry
            mpps.status = 'COMPLETED'
            mpps.end_time = datetime.datetime.now()
            
            # Update worklist item status
            worklist_item = db.query(WorklistItem).filter(
                WorklistItem.accession_number == accession_number
            ).first()
            
            if worklist_item:
                worklist_item.status = 'COMPLETED'
                
                # If EMR API is available, update the EMR status
                if EMR_API_AVAILABLE and worklist_item.emr_order_seq:
                    try:
                        emr_api.update_order_status(worklist_item.emr_order_seq, 'CO')
                    except Exception as e:
                        orthanc.LogError(f"Failed to update EMR status: {e}")
            
            db.commit()
            return True, accession_number
    except Exception as e:
        orthanc.LogError(f"Error recording MPPS completion: {e}")
        return False, None

def update_study_instance_uid(accession_number: str, study_instance_uid: str) -> bool:
    """
    Update the study instance UID for a worklist item
    """
    try:
        with get_db() as db:
            worklist_item = db.query(WorklistItem).filter(
                WorklistItem.accession_number == accession_number
            ).first()
            
            if not worklist_item:
                return False
            
            worklist_item.study_instance_uid = study_instance_uid
            db.commit()
            return True
    except Exception as e:
        orthanc.LogError(f"Error updating study UID: {e}")
        return False

def load_modality_aets():
    """Load modality-AET mappings from environment variables"""
    with get_db() as db:
        # Clear existing mappings
        db.query(ModalityAET).delete()
        
        # Load environment variables
        env_vars = os.environ

        # Load new mappings from environment variables
        for key, value in env_vars.items():
            if key.startswith('MODALITY_AET_'):
                orthanc.LogInfo(f"Loading modality-AET mapping for {key}: {value}")
                modality = key.replace('MODALITY_AET_', '')
                aets = value.split(',')
                for aet in aets:
                    mapping = ModalityAET(
                        modality=modality.strip(),
                        aet=aet.strip()
                    )
                    db.add(mapping)
        
        db.commit()
        orthanc.LogInfo("Loaded modality-AET mappings from environment")

def get_aets_for_modality(modality: str) -> List[str]:
    """Get list of AETs for a given modality"""
    with get_db() as db:
        mappings = db.query(ModalityAET).filter_by(modality=modality).all()
        return [m.aet for m in mappings]

# Check if the name contains Korean characters
def has_korean(text):
    return any(ord('가') <= ord(char) <= ord('힣') for char in text)
            
# Korean name to English name translation
def translate_korean_to_english_name(korean_name: str) -> str:
    """
    Translate a Korean name to its English equivalent.
    
    Args:
        korean_name: The Korean name to translate
        
    Returns:
        The English equivalent of the Korean name
    """
    try:
        # Check if the name contains Korean characters
        if not has_korean(korean_name):
            return korean_name

        spaced_korean_name = ''.join([char + ' ' for char in korean_name]).strip()
        return Romanizer(spaced_korean_name).romanize().upper()
        
    except Exception as e:
        orthanc.LogError(f"Error translating Korean name '{korean_name}': {e}")
        return korean_name  # Fall back to original name in case of error


def sync_emr_orders() -> int:
    """
    Sync new orders from EMR database
    Returns number of new orders processed
    """
    if not EMR_API_AVAILABLE:
        orthanc.LogWarning("Cannot sync EMR orders: EMR API not available")
        return 0
        
    try:
        with get_db() as db:
            # Get the latest order sequence we've processed
            latest_order = db.query(WorklistItem).filter(WorklistItem.emr_order_seq != None).order_by(
                WorklistItem.emr_order_seq.desc()
            ).first()
            
            last_seq = latest_order.emr_order_seq if latest_order else None
            orthanc.LogInfo(f"Last processed order sequence: {last_seq}")
            
            # Fetch new orders using direct pyodbc
            try:
                new_orders = emr_api.fetch_new_orders(last_seq)
                orthanc.LogInfo(f"Fetched {len(new_orders)} new orders from EMR")
            except Exception as e:
                orthanc.LogError(f"Error fetching orders from EMR: {e}")
                orthanc.LogError(traceback.format_exc())
                return 0
            
            count = 0
            for order in new_orders:
                # Make sure we have all required fields
                if not order.get('PcsChtNum') or not order.get('PcsPatNam') or not order.get('PcsOdrDtm') or not order.get('PcsOdrSeq'):
                    orthanc.LogWarning(f"Skipping order with incomplete data: {order}")
                    continue
                    
                try:
                    # Convert EMR order to WorklistItem format
                    patient = db.query(Patient).filter_by(
                        patient_id=order['PcsChtNum']
                    ).first()
                    
                    if not patient:
                        # Translate Korean name to English
                        korean_name = order['PcsPatNam']
                        english_name = translate_korean_to_english_name(korean_name)
                        
                        patient = Patient(
                            patient_id=order['PcsChtNum'],
                            patient_name=korean_name,
                            patient_eng_name=english_name,
                            birth_date=order.get('PcsBirDte', ''),
                            sex=order.get('PcsSexTyp', '')
                        )
                        db.add(patient)
                        db.flush()
                    
                    # Format order date/time
                    if isinstance(order['PcsOdrDtm'], datetime.datetime):
                        appointment_date = order['PcsOdrDtm'].strftime('%Y%m%d')
                        appointment_time = order['PcsOdrDtm'].strftime('%H%M%S')
                    else:
                        # Try to parse the string based on expected format
                        try:
                            dt = datetime.datetime.strptime(order['PcsOdrDtm'], '%Y%m%d%H%M')
                            appointment_date = dt.strftime('%Y%m%d')
                            appointment_time = dt.strftime('%H%M%S')
                        except Exception as e:
                            orthanc.LogWarning(f"Could not parse date/time: {order['PcsOdrDtm']} - {e}")
                            appointment_date = datetime.datetime.now().strftime('%Y%m%d')
                            appointment_time = datetime.datetime.now().strftime('%H%M%S')
                    
                    # Create accession number from order sequence
                    accession_number = str(order['PcsOdrSeq']).zfill(8)
                    
                    # Check if worklist item already exists
                    existing_item = db.query(WorklistItem).filter_by(
                        accession_number=accession_number
                    ).first()
                    
                    if existing_item:
                        orthanc.LogInfo(f"Skipping existing order: {accession_number}")
                        continue
                    
                    # Get modality from order
                    modality = order.get('PcsUntCod', 'OT')
                    
                    # Get AETs for this modality
                    aets = get_aets_for_modality(modality)
                    
                    # Use first AET if available, otherwise None
                    assigned_aet = aets[0] if aets else None
                    
                    # Create worklist item
                    worklist_item = WorklistItem(
                        patient_id=order['PcsChtNum'],
                        accession_number=accession_number,
                        appointment_date=appointment_date,
                        appointment_time=appointment_time,
                        modality=modality,
                        aet=assigned_aet,
                        status='SCHEDULED',
                        emr_order_seq=order['PcsOdrSeq']
                    )
                    
                    db.add(worklist_item)
                    count += 1
                    orthanc.LogInfo(f"Added new order: {accession_number}")
                except Exception as e:
                    orthanc.LogError(f"Error processing order {order.get('PcsOdrSeq', 'unknown')}: {e}")
                    orthanc.LogError(traceback.format_exc())
                    continue
                
            db.commit()
            if count > 0:
                orthanc.LogInfo(f"Added {count} new orders from EMR")
            return count
    except Exception as e:
        orthanc.LogError(f"Error in sync_emr_orders: {e}")
        orthanc.LogError(traceback.format_exc())
        return 0

# Background sync thread
def background_sync_thread():
    """Thread function to periodically sync with EMR"""
    if not EMR_API_AVAILABLE:
        orthanc.LogWarning("Background sync thread started but EMR API not available")
        return
        
    orthanc.LogInfo("Starting background EMR sync thread")
    
    # Initial delay before first sync
    time.sleep(10)
    
    sync_interval = 300  # Change to 5 minutes since we're also syncing on C-FIND
    
    while True:
        try:
            orthanc.LogInfo("Running background EMR order sync")
            new_count = sync_emr_orders()
            if new_count > 0:
                orthanc.LogInfo(f"Synced {new_count} new orders from EMR")
        except Exception as e:
            orthanc.LogError(f"Error in EMR sync: {e}")
            orthanc.LogError(traceback.format_exc())
        
        # Sleep until next sync
        try:
            time.sleep(sync_interval)
        except (KeyboardInterrupt, SystemExit):
            orthanc.LogInfo("Sync thread interrupted, exiting")
            break
        except Exception as e:
            orthanc.LogError(f"Error in sleep: {e}")
            time.sleep(10)  # Sleep for a shorter time if there was an error

def start_background_sync():
    """Start the background EMR sync thread"""
    if EMR_API_AVAILABLE:
        thread = threading.Thread(target=background_sync_thread, daemon=True)
        thread.start()
        orthanc.LogInfo("Background EMR sync thread started")
    else:
        orthanc.LogWarning("Not starting background sync: EMR API not available") 