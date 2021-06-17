FROM python:3
MAINTAINER https://github.com/JacobCallahan

RUN mkdir plinko
COPY / /plinko/
RUN cd /plinko && python3 setup.py install

WORKDIR /plinko

ENTRYPOINT ["plinko"]
CMD ["--help"]
