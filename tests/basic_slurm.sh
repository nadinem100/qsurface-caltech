#!/bin/bash

# Submit this script with: sbatch <this-filename>

#SBATCH --time=5:00:00   # walltime
#SBATCH --ntasks=1   # number of processor cores (i.e. tasks)
#SBATCH --nodes=1   # number of nodes
#SBATCH --mem-per-cpu=1G   # memory per CPU core
#SBATCH -J "phi-slope"   # job name
#SBATCH --mail-user=nmeister@caltech.edu   # email address

# Notify at the beginning, end of job and on failure.
#SBATCH --mail-type=BEGIN
#SBATCH --mail-type=END
#SBATCH --mail-type=FAIL


## /SBATCH -p general # partition (queue)
## /SBATCH -o data_cluster/slurm.%N.%j.out # STDOUT
## /SBATCH -e data_cluster/slurm.%N.%j.err # STDERR

# LOAD MODULES, INSERT CODE, AND RUN YOUR PROGRAMS HERE
python nadine_test_unionfind_faulty_cluster.py
echo done