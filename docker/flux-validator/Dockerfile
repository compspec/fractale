FROM fluxrm/flux-sched:jammy

LABEL maintainer="Vanessasaurus <@vsoch>"

RUN sudo apt-get update && sudo apt-get install -y less python3-pip 
RUN python3 -m pip install git+https://github.com/compspec/fractale.git@add-flux-generator IPython
COPY ./validate.py /validate.py
ENTRYPOINT ["flux", "start", "python3", "/validate.py", "validate"]