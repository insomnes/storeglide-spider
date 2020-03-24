FROM python:3-slim-buster
RUN mkdir /usr/src/app
COPY . /usr/src/app
WORKDIR /usr/src/app
RUN pip install -r requirements.txt
ENV PYTHONUNBUFFERED 1
