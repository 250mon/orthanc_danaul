import pyodbc
import json
import traceback
from datetime import datetime
from typing import List, Dict, Optional, Any
import os
import orthanc

# Define connection parameters
dsn = os.getenv("EMR_DSN")
server = os.getenv("EMR_SERVER") 
port = os.getenv("EMR_PORT")
database = os.getenv("EMR_DATABASE")
user = os.getenv("EMR_USER")
password = os.getenv("EMR_PASSWORD")

def get_connection():
    """Create and return a pyodbc connection to the EMR database"""
    try:
        # Try using DSN first
        if dsn:
            conn_str = f"DSN={dsn};UID={user};PWD={password}"
            orthanc.LogInfo(f"Connecting using DSN: {dsn}")
        else:
            # Direct connection if no DSN
            conn_str = f"DRIVER={{FreeTDS}};SERVER={server};PORT={port};DATABASE={database};UID={user};PWD={password};TDS_Version=7.2"
            orthanc.LogInfo(f"Connecting directly to {server}:{port}/{database}")
        
        # Create the connection
        conn = pyodbc.connect(conn_str, autocommit=True)
        orthanc.LogInfo("Database connection established successfully")
        return conn
    except Exception as e:
        orthanc.LogError(f"Error connecting to database: {e}")
        orthanc.LogError(traceback.format_exc())
        raise

def fetch_new_orders(last_order_seq: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetch new orders from EMR database
    Args:
        last_order_seq: If provided, only fetch orders newer than this sequence number
    Returns:
        List of order dictionaries
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Build the query - modified to handle PcsDelFlg as a character field
        query = """
            SELECT TOP 5 
                PcsOdrSeq, PcsOdrDtm, PcsOrgDtm, PcsUntCod, 
                PcsPatNam, PcsChtNum, PcsBirDte, PcsSexTyp
            FROM PcsInf
            WHERE PcsDelFlg = 'N'  -- Not deleted ('N' for No)
        """
        
        # Add filter for orders newer than last processed
        params = []
        if last_order_seq is not None:
            query += " AND PcsOdrSeq > ?"
            params.append(last_order_seq)
        
        # Add order by clause
        query += " ORDER BY PcsOdrSeq DESC"
        
        # Execute the query
        orthanc.LogInfo(f"Executing query: {query} with params: {params}")
        cursor.execute(query, params)
        
        # Fetch and process results
        columns = ["PcsOdrSeq", "PcsOdrDtm", "PcsOrgDtm", "PcsUntCod", 
                  "PcsPatNam", "PcsChtNum", "PcsBirDte", "PcsSexTyp"]
        
        results = []
        for row in cursor.fetchall():
            # Create a dictionary for each row
            result = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Convert datetime objects to string if needed
                if isinstance(value, datetime):
                    if col == "PcsOdrDtm" or col == "PcsOrgDtm":
                        result[col] = value
                else:
                    result[col] = value
            results.append(result)
        
        orthanc.LogInfo(f"Fetched {len(results)} orders from EMR")
        
        return results
    except Exception as e:
        orthanc.LogError(f"Error fetching orders: {e}")
        orthanc.LogError(traceback.format_exc())
        # Return empty list on error
        return []
    finally:
        # Ensure connection is closed even if an error occurs
        if conn:
            try:
                conn.close()
            except Exception as e:
                orthanc.LogWarning(f"Error closing connection: {e}")

def update_order_status(order_seq: int, status: str) -> bool:
    """
    Update order status in EMR
    Args:
        order_seq: The order sequence number
        status: New status ('IP' for in progress, 'CO' for completed)
    Returns:
        True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Update status query
        query = "UPDATE PcsInf SET PcsStatus = ? WHERE PcsOdrSeq = ?"
        
        # Log the query
        orthanc.LogInfo(f"Executing update query: {query} with params: [{status}, {order_seq}]")
        
        # Execute update
        cursor.execute(query, (status, order_seq))
        rows_affected = cursor.rowcount
        
        # Commit changes
        conn.commit()
        
        orthanc.LogInfo(f"Updated order {order_seq} status to {status}, rows affected: {rows_affected}")
        return rows_affected > 0
    except Exception as e:
        orthanc.LogError(f"Error updating order status: {e}")
        orthanc.LogError(traceback.format_exc())
        return False
    finally:
        # Ensure connection is closed even if an error occurs
        if conn:
            try:
                conn.close()
            except Exception as e:
                orthanc.LogWarning(f"Error closing connection: {e}")

def get_column_types():
    """
    Diagnostic function to get column types from the PcsInf table
    Returns a dictionary of column names and their types
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Query to get column information
        query = """
            SELECT 
                COLUMN_NAME, 
                DATA_TYPE 
            FROM 
                INFORMATION_SCHEMA.COLUMNS 
            WHERE 
                TABLE_NAME = 'PcsInf'
        """
        
        cursor.execute(query)
        
        results = {}
        for row in cursor.fetchall():
            col_name, data_type = row
            results[col_name] = data_type
        
        orthanc.LogInfo(f"Column types for PcsInf: {json.dumps(results)}")
        return results
    except Exception as e:
        orthanc.LogError(f"Error getting column types: {e}")
        orthanc.LogError(traceback.format_exc())
        return {}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

if __name__ == "__main__":
    # Test the function
    orders = fetch_new_orders()
    print(json.dumps(orders, indent=4, ensure_ascii=False, default=str))