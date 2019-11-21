FROM ubuntu:18.04
RUN apt-get update && \
  apt-get install -y software-properties-common && \
  add-apt-repository ppa:jonathonf/python-3.6

RUN apt-get install -y build-essential python3.6 python3.6-dev python3-pip


# We copy just the requirements.txt first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt

WORKDIR /app

RUN pip3 install -r requirements.txt

COPY . .

EXPOSE 5000
ENTRYPOINT [ "python3" ]

CMD [ "ghstats.py" ]
