#!/bin/bash
#SBATCH --job-name=verisim_vdb
#SBATCH --account=<SLURM_ACCOUNT>
#SBATCH --qos=gpu
#SBATCH --partition=gpuq
#SBATCH --gres=gpu:A100.80gb:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/build_%j.out
#SBATCH --error=logs/build_%j.err

set -euo pipefail

cd /path/to/working_dir/verisim_vectordb
source venv/bin/activate

# UMLS_API_KEY must be exported by the submitter (sbatch --export=...)
if [ -z "${UMLS_API_KEY:-}" ]; then
    echo "ERROR: UMLS_API_KEY not set in env" >&2
    exit 1
fi

# HF cache redirected per ~/.bashrc but reassert here in case sbatch strips env
export HF_HOME="${HF_HOME:-/path/to/working_dir/hf-cache}"
export TORCH_HOME="${TORCH_HOME:-/path/to/working_dir/torch-cache}"
export TOKENIZERS_PARALLELISM=false

nvidia-smi || true
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"

python -u build_vector_db.py --phase all
