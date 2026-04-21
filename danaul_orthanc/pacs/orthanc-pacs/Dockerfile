FROM orthancteam/orthanc

ENV LANG=C.UTF-8

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY orthanc.json /etc/orthanc/
