FROM python:3-slim-buster
RUN mkdir /usr/src/app
COPY . /usr/src/app
WORKDIR /usr/src/app
RUN apt update
RUN apt -y install build-essential
RUN pip install -r requirements.txt
ENV PYTHONUNBUFFERED 1
