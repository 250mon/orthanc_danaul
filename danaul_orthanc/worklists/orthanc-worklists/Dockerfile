FROM orthancteam/orthanc

COPY orthanc.json /etc/orthanc/
COPY plugins /etc/orthanc/plugins

# Install dependencies and ODBC driver
RUN apt-get update && \
    apt-get install -y unixodbc unixodbc-dev tdsodbc freetds-bin freetds-dev freetds-common

# Install Python packages
RUN pip install pynetdicom sqlalchemy pyodbc korean-romanizer --break-system-packages

# Set environment variables
ARG EMR_DSN
ARG EMR_SERVER
ARG EMR_PORT
ARG EMR_DATABASE
ENV EMR_DSN=${EMR_DSN:-EmrDb}
ENV EMR_SERVER=${EMR_SERVER:-localhost}
ENV EMR_PORT=${EMR_PORT:-1433}
ENV EMR_DATABASE=${EMR_DATABASE:-EmrDb}

# Create odbcinst.ini for FreeTDS
RUN echo "[FreeTDS]" > /etc/odbcinst.ini && \
    echo "Description = FreeTDS Driver for SQL Server" >> /etc/odbcinst.ini && \
    echo "Driver = /usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so" >> /etc/odbcinst.ini && \
    echo "Setup = /usr/lib/x86_64-linux-gnu/odbc/libtdsS.so" >> /etc/odbcinst.ini && \
    echo "UsageCount = 1" >> /etc/odbcinst.ini && \
    echo "Trace = No" >> /etc/odbcinst.ini

# Create freetds.conf file
RUN echo "[global]" > /etc/freetds/freetds.conf && \
    echo "    # TDS protocol version" >> /etc/freetds/freetds.conf && \
    echo "    tds version = 7.3" >> /etc/freetds/freetds.conf && \
    echo "    client charset = UTF-8" >> /etc/freetds/freetds.conf && \
    echo "" >> /etc/freetds/freetds.conf && \
    echo "[${EMR_SERVER}]" >> /etc/freetds/freetds.conf && \
    echo "    host = ${EMR_SERVER}" >> /etc/freetds/freetds.conf && \
    echo "    port = ${EMR_PORT}" >> /etc/freetds/freetds.conf && \
    echo "    tds version = 7.3" >> /etc/freetds/freetds.conf

# Create odbc.ini
RUN echo "[${EMR_DSN}]" > /etc/odbc.ini && \
    echo "Driver = FreeTDS" >> /etc/odbc.ini && \
    echo "Servername = ${EMR_SERVER}" >> /etc/odbc.ini && \
    echo "Port = ${EMR_PORT}" >> /etc/odbc.ini && \
    echo "Database = ${EMR_DATABASE}" >> /etc/odbc.ini && \
    echo "TDS_Version = 7.3" >> /etc/odbc.ini

# Test the ODBC configuration
RUN echo "Testing ODBC configuration" && \
    odbcinst -j

ENV MODALITY_AET_CR=VXVUE
ENV MODALITY_AET_US=XC70
ENV MODALITY_AET_RF=SpiderStoreSCP