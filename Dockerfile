FROM python:3.6-alpine

WORKDIR /app

ADD requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

ADD . /app

ENTRYPOINT ["gunicorn"]
CMD ["-w", "8", "-b", "0.0.0.0:5000", "RunController.server:app"]
