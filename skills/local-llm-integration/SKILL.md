---
name: local-llm-integration
description: "Run an open-weight model locally with Ollama, llama.cpp llama-server, or vLLM behind an OpenAI-compatible endpoint: estimate weight and KV-cache memory first, pick quantization and engine, bind to loopback, health-check, and measure streaming time to first token. Use when adding, sizing, or debugging a local or self-hosted model, or when one runs out of memory or is slow. Not for judging output quality (use the llm-eval-harness skill)."
---

# Local LLM Integration

Serve an open-weight model on local or self-hosted hardware and connect the
application to it through an OpenAI-compatible endpoint. The stance is
**estimate before you load**: do the memory math, start the smallest
configuration that meets the application's needs, and measure it.

## When to use

- Adding a local or self-hosted model for privacy, offline use, cost, or latency.
- Choosing model size, quantization, context length, or engine for given hardware.
- Debugging out-of-memory errors, slow first tokens, silent CPU fallback, or
  truncated context on a local server.

## When not to use

- Calling a hosted provider, or designing prompts, tools, and output handling:
  use the `build-llm-feature` skill.
- Deciding whether a local model is good enough: use the `llm-eval-harness`
  skill with local and hosted candidates side by side.
- Load and capacity testing: use the `load-testing-suite` skill.
- Packaging the server as an image: use the `containerize-service` skill.
- An independent feasibility check: delegate to the `local-model-specialist` subagent.

## Inputs to gather

Discover these before asking; ask only about what would change the plan.

- **Hardware**, with read-only commands: `nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv`
  (NVIDIA), `rocm-smi --showmeminfo vram` (AMD), `sysctl -n hw.memsize` (macOS
  total RAM in bytes, which is not usable GPU memory), `free -m` (Linux RAM),
  and free disk space for the weights.
- **Model:** exact repository or file, parameter count, license terms, and
  architecture values from `config.json` or GGUF metadata: layer count
  (`num_hidden_layers`), key-value heads (`num_key_value_heads`), and head
  dimension (`head_dim`, or `hidden_size / num_attention_heads`).
- **Application needs:** context length, concurrent requests, streaming,
  structured output, and the application's latency target. There is no
  universal time-to-first-token target.
- **Existing setup:** installed engines, ports in use, the client's base URL and
  model configuration, and how the project starts services (scripts, compose,
  `Makefile`).

## Workflow

1. **Estimate memory before downloading or loading anything.**
   - Weights ≈ parameters × bytes per parameter. Prefer the actual size of the
     weight files. Approximate bytes per parameter: 2 for FP16 or BF16, about
     1.06 for Q8_0, about 0.7 for Q5_K_M, about 0.6 for Q4_K_M, and roughly
     0.55 to 0.6 for 4-bit AWQ or GPTQ once unquantized layers are included.
   - KV cache ≈ 2 × layers × kv_heads × head_dim × context_length ×
     concurrent_sequences × bytes per element (2 for an FP16 or BF16 cache,
     about 1 for an 8-bit cache where the engine supports it). Use key-value
     heads, not attention heads: with grouped-query attention the cache is often
     4 to 8 times smaller. Sliding-window and latent-attention architectures
     need less; trust the engine's reported KV size for those.
   - Add headroom for activations, the CUDA context or Metal buffers, and the
     runtime (for example 1 to 2 GB plus about 10 percent), then confirm against
     the engine's startup log.
   - Compare with **usable** memory. On a discrete GPU that is free VRAM after
     other processes and the display. On macOS the GPU can use only part of
     unified memory; llama.cpp prints the limit as `recommendedMaxWorkingSetSize`
     in its Metal startup log. Never equate total RAM with usable VRAM.
   - If it does not fit: shorten the context, reduce concurrent sequences, pick
     a smaller quantization or model, quantize the KV cache, or offload some
     layers to the CPU (much slower). State the tradeoff you chose.

   Worked example: a Llama 3 8B architecture (32 layers, 8 KV heads, head_dim
   128) at Q4_K_M. Weights ≈ 8.0 billion × 0.6 ≈ 4.8 GB. KV per token = 2 × 32 ×
   8 × 128 × 2 bytes = 128 KiB, so one 8,192-token sequence needs about 1 GiB and
   four concurrent ones about 4 GiB. Using the 32 attention heads instead of the
   8 KV heads would overestimate the cache four times.
2. **Choose the engine.** Prefer what the project already uses.
   - **Ollama:** simplest on a developer machine; manages downloads and
     quantized builds; serves an OpenAI-compatible API at
     `http://127.0.0.1:11434/v1`.
   - **llama.cpp `llama-server`:** GGUF files on CPU, Metal, CUDA, or Vulkan,
     with direct control of GPU layers, context, and parallel slots.
   - **vLLM:** GPU servers with many concurrent requests (continuous batching);
     safetensors models including AWQ and GPTQ. GGUF support is experimental.
3. **Ask before heavy actions.** Downloading weights (often many gigabytes),
   accepting a model license, and starting a long-running GPU process each need
   the user's go-ahead. State the model, size on disk, license, port, and
   expected memory use.
4. **Start the server on loopback,** recording its PID and log in a temp
   directory. Flags change between releases: check `--help` for the installed
   version before relying on any of them.

   ```bash
   # Illustrative. Run one engine. mktemp -d works on Linux, macOS, and Git Bash.
   run_dir="$(mktemp -d)"
   PORT=8080

   # llama.cpp: -c context, -ngl GPU layers (a large value offloads all of them)
   llama-server -m "$MODEL_GGUF" -c 8192 -ngl 99 --host 127.0.0.1 --port "$PORT" \
     > "$run_dir/server.log" 2>&1 &
   echo $! > "$run_dir/server.pid"

   # vLLM
   vllm serve "$MODEL_ID" --host 127.0.0.1 --port "$PORT" --max-model-len 8192 \
     --gpu-memory-utilization 0.85 --max-num-seqs 4 > "$run_dir/server.log" 2>&1 &
   echo $! > "$run_dir/server.pid"

   # Ollama listens on 127.0.0.1:11434; skip `ollama serve` if the app already runs.
   ollama serve > "$run_dir/server.log" 2>&1 &
   echo $! > "$run_dir/server.pid"
   ollama pull "$OLLAMA_MODEL"   # after the health check passes and the user approves
   ```

   On native Windows PowerShell, use `$env:TEMP` for the run directory and
   record the PID from `Start-Process -PassThru`.

   Engine notes:
   - **Ollama** may default to a shorter context than the model supports (the
     default varies by version), and longer prompts are truncated. Set it
     explicitly (the `num_ctx` option, `PARAMETER num_ctx` in a Modelfile, or
     `OLLAMA_CONTEXT_LENGTH` in recent versions) and confirm what applied.
     `ollama ps` shows how much of the model sits on GPU versus CPU. Ollama
     loads a model on its first request, so warm it up before timing.
   - **llama-server:** `-np` sets parallel slots, and in many versions the `-c`
     context is divided among them, so `-c 8192 -np 4` leaves about 2,048 tokens
     per request. The startup log reports offloaded layers and KV cache size.
   - **vLLM:** `--gpu-memory-utilization` is the fraction of total GPU memory the
     instance preallocates for weights, activations, and KV cache; startup fails
     if the cache cannot hold one `--max-model-len` sequence. Quantization is
     usually read from the model config; quantization, structured-output, and
     KV-cache-dtype options vary by version (check `vllm serve --help`). GGUF
     loads from a local file path, typically with `--tokenizer` set to the base
     model's repository.
5. **Health-check with a bounded poll** that also stops if the process dies.
   llama-server and vLLM answer `GET /health` (llama-server returns 503 while
   loading); for Ollama use `GET /api/version`.

   ```bash
   # Illustrative: wait up to about 5 minutes.
   health_url="http://127.0.0.1:${PORT}/health"   # Ollama: http://127.0.0.1:11434/api/version
   pid="$(cat "$run_dir/server.pid")"
   ready=0
   for _ in $(seq 1 60); do
     if curl -fsS --max-time 2 "$health_url" > /dev/null; then
       ready=1; break
     fi
     kill -0 "$pid" 2>/dev/null || break   # the server exited; read the log
     sleep 5
   done
   [ "$ready" -eq 1 ] || tail -n 50 "$run_dir/server.log"
   ```
6. **Connect the application** through its existing client configuration: base
   URL `http://127.0.0.1:PORT/v1`, the model name reported by `GET /v1/models`,
   and a placeholder API key if the client insists on one. Keep the base URL and
   model id in config, not code. Use the model card's recommended sampling
   settings and make sure the server applies the model's chat template.
   Engine-specific parameters (repetition-penalty names differ by engine) are
   not portable through the OpenAI-compatible API. Request a JSON output mode
   only when the application needs structured output, check which
   `response_format` types the engine supports, and still validate the result
   in code. Allow for cold starts in client timeouts.
7. **Measure time to first token with a streaming request** (`"stream": true`).
   A non-streaming request returns only when generation ends, so its timing is
   total time. Use a prompt of realistic length (prefill time grows with it),
   warm up first, and report the median and worst of several runs against the
   application's target.

   ```python
   # Illustrative: python ttft.py http://127.0.0.1:8080/v1 MODEL prompt.txt
   import json
   import statistics
   import sys
   import time
   import urllib.request


   def measure(base_url: str, model: str, prompt: str, timeout: float = 300.0) -> dict:
       body = json.dumps({
           "model": model,
           "messages": [{"role": "user", "content": prompt}],
           "max_tokens": 128,
           "stream": True,
       }).encode("utf-8")
       request = urllib.request.Request(
           base_url.rstrip("/") + "/chat/completions", data=body,
           headers={"Content-Type": "application/json"}, method="POST")
       start = time.perf_counter()
       first = None
       with urllib.request.urlopen(request, timeout=timeout) as response:
           for raw in response:  # one server-sent event line at a time
               line = raw.decode("utf-8").strip()
               if not line.startswith("data:"):
                   continue
               data = line[len("data:"):].strip()
               if data == "[DONE]":
                   break
               choices = json.loads(data).get("choices") or [{}]
               if first is None and choices[0].get("delta", {}).get("content"):
                   first = time.perf_counter()
       end = time.perf_counter()
       return {"ttft_s": None if first is None else first - start, "total_s": end - start}


   if __name__ == "__main__":
       base_url, model, prompt_file = sys.argv[1], sys.argv[2], sys.argv[3]
       with open(prompt_file, encoding="utf-8") as fh:
           prompt = fh.read()
       measure(base_url, model, prompt)  # warm-up; not reported
       runs = [measure(base_url, model, prompt) for _ in range(5)]
       ttfts = [r["ttft_s"] for r in runs if r["ttft_s"] is not None]
       if ttfts:
           print(f"TTFT median {statistics.median(ttfts):.3f}s, worst {max(ttfts):.3f}s")
       print(f"total median {statistics.median(r['total_s'] for r in runs):.3f}s, runs={len(runs)}")
   ```

   Reasoning models may stream reasoning text before content; decide whether
   the application's target counts it.
8. **Stop only what you started,** by the PID you recorded: SIGTERM first, then
   SIGKILL only if it has not exited.

   ```bash
   pid="$(cat "$run_dir/server.pid")"
   ps -p "$pid" -o command=        # confirm it is still the server you started
   kill -TERM "$pid"
   for _ in $(seq 1 30); do
     kill -0 "$pid" 2>/dev/null || break
     sleep 1
   done
   if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid"; fi
   ```

## Guardrails

- Revert or delete only files you created in this session, and say so. Never
  discard someone else's uncommitted work.
- Ask before destructive, irreversible, outward-facing, or production actions,
  including large downloads, license acceptance, long-running GPU processes,
  and changes to drivers or system memory limits.
- Never weaken a test, check, or threshold to make work pass.
- Bind to 127.0.0.1. Before exposing a server beyond loopback, put an
  authenticating proxy with TLS in front of it. Ollama has no built-in
  authentication; an `--api-key` on vLLM or llama-server is one layer, not a
  reason to bind to `0.0.0.0`.
- Prefer safetensors or GGUF weights from the publisher or a trusted mirror.
  Pickle-based `.bin` or `.pt` files and `--trust-remote-code` can execute code;
  never enable the latter without approval.
- Stop processes only by the PID you recorded; never kill by name pattern, and
  never stop an Ollama app or server someone else started.
- Never claim a latency target was met without a streaming measurement.

## Verification

Use the project's own commands for application checks; run each separately.

- `GET /v1/models` lists the expected model.
- The startup log (or `ollama ps`) shows the intended GPU offload and context
  length, with no unexpected CPU fallback.
- Observed peak memory (`nvidia-smi`, Activity Monitor, `ollama ps`) is within
  the estimate plus headroom.
- The streaming measurement reports median and worst time to first token
  against the application's target.
- The application's tests or a smoke request through its own client pass, and
  structured output, if used, validates against its schema.

## Report

- **Hardware and usable memory:** and how usable memory was determined.
- **Model:** source, quantization, license, size on disk.
- **Memory:** estimated weights, KV cache, and headroom versus observed.
- **Engine:** version (`--version`), exact command, and endpoint.
- **Configuration changes:** base URL, model id, timeouts, files touched.
- **Measurements:** time to first token median and worst, total time, prompt
  length, number of runs.
- **Process state:** running (PID, log path) or stopped.
- **Not verified:** checks that could not run and why.

## Optional delegation

The `local-model-specialist` subagent can review the memory estimate,
quantization choice, and engine selection before anything is downloaded;
re-check its numbers before acting. Judge output quality with the
`llm-eval-harness` skill.
