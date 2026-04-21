FROM orthancteam/orthanc

ENV LANG=C.UTF-8

RUN pip install pydicom --break-system-packages

COPY orthanc.json /etc/orthanc/
