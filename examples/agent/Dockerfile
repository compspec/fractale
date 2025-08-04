# Dockerfile for LAMMPS (Large-scale Atomic/Molecular Massively Parallel Simulator)                                   
# Target: Production HPC environment on Google Cloud                  
# Strategy: Multi-stage build for a lean final image with MPI support.
                                                                      
# Use ARGs at the top to easily update versions of key components globally
ARG LAMMPS_VERSION=stable_2Aug2023                                    
ARG OPENMPI_VERSION=4.1.6                                             
                                                                      
# =====================================================================
# Stage 1: Builder                                                    
# This stage compiles Open MPI and LAMMPS from source. It contains all
# the build-time dependencies, which will be discarded later.         
# =====================================================================
FROM debian:bullseye AS builder                                       
                                                                      
# Inherit ARGs from the global scope                                  
ARG LAMMPS_VERSION                                                    
ARG OPENMPI_VERSION                                                   
                                                                      
# Set environment variables for the Open MPI build location and path  
ENV OMPI_DIR=/opt/openmpi-${OPENMPI_VERSION}                          
ENV PATH=$OMPI_DIR/bin:$PATH                                          
ENV LD_LIBRARY_PATH=$OMPI_DIR/lib                                     
                                                                      
# Prevent interactive prompts during package installation             
ENV DEBIAN_FRONTEND=noninteractive                                    
                                                                      
# Install essential build tools and libraries for both Open MPI and LAMMPS      
# Added ca-certificates to allow git and wget to verify SSL certificates securely.
RUN apt-get update && apt-get install -y --no-install-recommends \    
    build-essential \                                                 
    ca-certificates \                                                 
    cmake \                                                           
    g++ \                                                             
    gfortran \                                                        
    git \                                                             
    libevent-dev \                                                    
    libhwloc-dev \                                                    
    wget \                                                            
    && rm -rf /var/lib/apt/lists/*                                    
                                                                      
# --- Build Open MPI from source ---                                  
# Building from source gives control over the configuration, crucial for        
# containerized HPC environments. We enable PMIx for modern process management. 
WORKDIR /tmp                                                          
RUN wget https://download.open-mpi.org/release/open-mpi/v${OPENMPI_VERSION%.*}/openmpi-${OPENMPI_VERSION}.tar.gz && \ 
    tar -xzf openmpi-${OPENMPI_VERSION}.tar.gz                        
                                                                      
WORKDIR /tmp/openmpi-${OPENMPI_VERSION}                               
RUN ./configure \                                                     
    --prefix=${OMPI_DIR} \                                            
    --with-pmix \                                                     
    --disable-pty-support                                             
RUN make -j$(nproc) all && make install                               
                                                                      
# --- Build LAMMPS from source ---                                    
# Clone a specific stable release tag for reproducibility.            
WORKDIR /opt                                                          
RUN git clone --depth 1 --branch ${LAMMPS_VERSION} https://github.com/lammps/lammps.git lammps                        
                                                                      
# Use CMake to configure the LAMMPS build. Enable common packages.    
WORKDIR /opt/lammps/build                                             
RUN cmake ../cmake \                                                  
    -D CMAKE_INSTALL_PREFIX=/usr/local \                              
    -D BUILD_MPI=yes \                                                
    -D PKG_KSPACE=yes \                                               
    -D PKG_MOLECULE=yes \                                             
    -D PKG_RIGID=yes \                                                
    -D PKG_MANYBODY=yes \                                             
    -D PKG_REPLICA=yes \                                              
    -D CMAKE_BUILD_TYPE=Release \                                     
    -D LAMMPS_EXCEPTIONS=yes                                          
                                                                      
# Compile and install LAMMPS                                          
RUN make -j$(nproc) && make install                                   
                                                                      
# =====================================================================
# Stage 2: Final Image                                                
# This stage creates the lean, final image. It starts from a minimal  
# base and only copies the necessary executables, libraries, and runtime        
# dependencies from the builder stage.                                
# =====================================================================
FROM debian:bullseye-slim                                             
                                                                      
# Inherit ARG for version consistency                                 
ARG OPENMPI_VERSION                                                   
                                                                      
# Set environment variables for Open MPI runtime                      
ENV OMPI_DIR=/opt/openmpi-${OPENMPI_VERSION}                          
ENV PATH=/usr/local/bin:$OMPI_DIR/bin:$PATH                           
                                                                      
# Install only the essential runtime dependencies.                    
# libgfortran5 is required by the Fortran-compiled parts of LAMMPS.   
RUN apt-get update && apt-get install -y --no-install-recommends \    
    libevent-2.1-7 \                                                  
    libgfortran5 \                                                    
    libhwloc15 \                                                      
    && rm -rf /var/lib/apt/lists/*                                    
                                                                      
# Copy the compiled Open MPI installation from the builder stage      
COPY --from=builder ${OMPI_DIR} ${OMPI_DIR}                           
                                                                      
# Copy the entire LAMMPS installation (binary, libs, potentials) from the builder stage                               
COPY --from=builder /usr/local /usr/local                             
                                                                      
# Configure the dynamic linker to find Open MPI and LAMMPS libraries. 
# This is more robust than setting LD_LIBRARY_PATH.                   
RUN echo "${OMPI_DIR}/lib" > /etc/ld.so.conf.d/openmpi.conf && \      
    echo "/usr/local/lib" > /etc/ld.so.conf.d/lammps.conf && \        
    ldconfig                                                          
                                                                      
# Create a dedicated, non-root user for running the application for security    
RUN useradd --create-home --shell /bin/bash lammps                    
USER lammps                                                           
WORKDIR /home/lammps                                                  
                                                                      
# Set the entrypoint to the LAMMPS executable.                        
# Allows running the container with LAMMPS args directly, e.g., `docker run <image> -in in.lj`                        
ENTRYPOINT ["lmp"]                                                    
                                                                      
# Provide a default command to display help if no other args are provided.      
CMD ["-h"] 
# Generated by fractale build agent
