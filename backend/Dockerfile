FROM python:3.8

WORKDIR /app
COPY /requirements.txt requirements.txt


RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8080
# start the webserver
ENTRYPOINT ["gunicorn", "--bind", "0.0.0.0:8080","ghstats:app"]
