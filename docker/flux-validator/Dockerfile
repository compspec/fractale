FROM fluxrm/flux-sched:jammy

LABEL maintainer="Vanessasaurus <@vsoch>"

RUN sudo apt-get update && sudo apt-get install -y less python3-pip && python3 -m pip install IPython
COPY ./ /code
RUN cd /code && sudo python3 -m pip install -e .
ENTRYPOINT ["flux", "start", "python3", "/code/docker/flux-validator/validate.py", "validate"]
