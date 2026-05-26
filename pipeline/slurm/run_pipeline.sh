#!/bin/bash
#SBATCH --job-name=verisim_pipe
#SBATCH --account=<SLURM_ACCOUNT>
#SBATCH --qos=gpu
#SBATCH --partition=contrib-gpuq
#SBATCH --gres=gpu:A100.80gb:2
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --time=06:00:00
#SBATCH --output=logs/pipeline_%j.out
#SBATCH --error=logs/pipeline_%j.err

set -euo pipefail

cd /path/to/working_dir/verisim_pipeline
source venv/bin/activate

if [ -z "${UMLS_API_KEY:-}" ]; then
    echo "ERROR: UMLS_API_KEY not set" >&2
    exit 1
fi

export HF_HOME="${HF_HOME:-/path/to/working_dir/hf-cache}"
export HF_TOKEN="$(cat ~/.cache/huggingface/token 2>/dev/null || echo "")"
export TOKENIZERS_PARALLELISM=false
export TP_SIZE=2
# vLLM env tuning
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export VLLM_LOGGING_LEVEL=WARNING

nvidia-smi
echo "----"
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'n_gpu=', torch.cuda.device_count())"

python -u pipeline_code/main.py
