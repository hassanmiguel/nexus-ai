import platform, os
try: import psutil
except Exception: psutil=None

def hardware_profile():
    ram=round(psutil.virtual_memory().total/1024**3,1) if psutil else None
    cpu=psutil.cpu_count(logical=True) if psutil else os.cpu_count()
    gpu='Not detected by built-in diagnostics (Ollama may still use a supported GPU)'
    try:
        import subprocess
        p=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'],capture_output=True,text=True,timeout=2)
        if p.returncode==0 and p.stdout.strip():gpu=p.stdout.strip()
    except Exception:pass
    if ram is None:recommend='Install psutil for RAM telemetry; start with a 3B quantized model.'
    elif ram<8:recommend='Use a 1B–3B quantized model; keep context at 2K–4K; avoid parallel jobs.'
    elif ram<16:recommend='Use a 3B–7B quantized model; context 4K–8K; run one task at a time.'
    elif ram<32:recommend='Use a 7B–14B quantized model if GPU/VRAM supports it; context 8K.'
    else:recommend='A 14B+ quantized model may be feasible; validate available VRAM before selection.'
    return {'platform':platform.platform(),'cpu_threads':cpu,'ram_gb':ram,'gpu':gpu,'recommendation':recommend}
