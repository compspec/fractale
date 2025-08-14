# Base image: Ubuntu 22.04 LTS for a stable and recent environment
FROM ubuntu:22.04

# Set non-interactive frontend for package managers to avoid prompts
ENV DEBIAN_FRONTEND=noninteractive

# Configure OpenMPI for containerized environments
# Allow running MPI as root, a requirement for this specific Dockerfile
ENV OMPI_ALLOW_RUN_AS_ROOT=1
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
# Force components to work over TCP, common in container orchestrators
ENV OMPI_MCA_btl=self,tcp
ENV OMPI_MCA_pml=ob1
ENV OMPI_MCA_btl_tcp_if_include=eth0
ENV OMPI_MCA_oob_tcp_if_include=eth0

# Install build dependencies, git, cmake, and MPI libraries
# Added python3 to satisfy the LAMMPS cmake build system dependency
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    wget \
    ca-certificates \
    g++ \
    openmpi-bin \
    libopenmpi-dev \
    libfftw3-dev \
    python3 && \
    rm -rf /var/lib/apt/lists/*

# Clone, build, and install LAMMPS
# Using 'develop' branch as 'master' is no longer a valid branch in the LAMMPS repository
# A selection of common CPU packages are enabled, including REAXFF as requested
RUN git clone --depth 1 -b develop https://github.com/lammps/lammps.git /lammps && \
    cd /lammps && \
    mkdir build && \
    cd build && \
    cmake ../cmake \
        -D CMAKE_INSTALL_PREFIX=/usr/local \
        -D BUILD_MPI=yes \
        -D BUILD_OMP=yes \
        -D PKG_KSPACE=yes \
        -D PKG_MOLECULE=yes \
        -D PKG_RIGID=yes \
        -D PKG_MANYBODY=yes \
        -D PKG_REAXFF=yes \
        -D PKG_MISC=yes \
        -D PKG_EXTRA-COMPUTE=yes \
        -D PKG_EXTRA-DUMP=yes \
        -D PKG_EXTRA-FIX=yes \
        -D PKG_EXTRA-MOLECULE=yes && \
    make -j$(nproc) && \
    make install

# Set the working directory for the container
WORKDIR /data

# Copy the requested example files into the working directory
# These files can be used for initial testing or as templates
RUN cp /lammps/examples/reaxff/HNS/* /data/ && \
    # Clean up the source code to reduce final image size
    rm -rf /lammps

# Set the default entrypoint to the LAMMPS executable
# The executable is on the PATH due to the CMAKE_INSTALL_PREFIX
ENTRYPOINT ["lmp"]

# Default command can be overridden, e.g., docker run <image> -in in.script
CMD ["-h"]