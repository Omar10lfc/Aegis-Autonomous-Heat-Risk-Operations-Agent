import json
from pathlib import Path
from datetime import datetime

traces_dir = Path("traces")
trace_files = list(traces_dir.glob("*.json"))

parsed_traces = []

for f in trace_files:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        trace_id = data.get("trace_id")
        runs = data.get("runs", [])
        if not runs:
            continue
            
        # Top-level pipeline run
        root_run = runs[0]
        dotted = root_run.get("langsmith", {}).get("dotted_order", "")
        # format: 20260831T181228470752Z01a05905...
        ts_str = dotted.split("Z")[0] if "Z" in dotted else None
        dt = None
        if ts_str and len(ts_str) >= 15:
            try:
                dt = datetime.strptime(ts_str[:15], "%Y%m%dT%H%M%S")
            except Exception:
                pass
                
        # Find child runs (planner, executor, analyzer, synthesizer, llm)
        run_names = [r.get("langsmith", {}).get("name") for r in runs]
        
        # Determine duration: min start to max start or run duration
        timestamps = []
        for r in runs:
            d = r.get("langsmith", {}).get("dotted_order", "")
            if "Z" in d:
                t_part = d.split("Z")[0][:15]
                try:
                    timestamps.append(datetime.strptime(t_part, "%Y%m%dT%H%M%S"))
                except Exception:
                    pass
                    
        duration = (max(timestamps) - min(timestamps)).total_seconds() if len(timestamps) > 1 else 0.0
        
        # Check fortyguard_mode & llm_model
        fg_mode = "unknown"
        llm_model = "unknown"
        error = None
        
        for r in runs:
            meta = r.get("metadata", {})
            if "fortyguard_mode" in meta:
                fg_mode = meta["fortyguard_mode"]
            if "llm_model" in meta and meta["llm_model"]:
                llm_model = meta["llm_model"]
            if r.get("error"):
                error = r.get("error").split("\n")[0][:80]
                
            # Check outputs
            out = r.get("outputs", {})
            if isinstance(out, dict):
                if out.get("fortyguard_mode"):
                    fg_mode = out.get("fortyguard_mode")
                if out.get("llm_model"):
                    llm_model = out.get("llm_model")

        parsed_traces.append({
            "filename": f.name,
            "trace_id": trace_id,
            "timestamp": dt or (min(timestamps) if timestamps else None),
            "duration_est": duration,
            "total_runs": len(runs),
            "run_names": list(set(run_names)),
            "fg_mode": fg_mode,
            "llm_model": llm_model,
            "has_error": bool(error),
            "error_snippet": error,
        })
    except Exception as e:
        print(f"Error reading {f.name}: {e}")

# Sort chronologically
parsed_traces = [t for t in parsed_traces if t["timestamp"]]
parsed_traces.sort(key=lambda x: x["timestamp"])

print(f"Parsed {len(parsed_traces)} traces chronologically:\n")
print(f"{'#':<3} | {'Timestamp':<19} | {'Mode':<7} | {'Model':<35} | {'Runs':<4} | {'Error'}")
print("-" * 95)
for i, t in enumerate(parsed_traces):
    err = t['error_snippet'] if t['has_error'] else "None (Success)"
    ts = t['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
    print(f"{i+1:<3} | {ts} | {t['fg_mode']:<7} | {t['llm_model']:<35} | {t['total_runs']:<4} | {err}")

# Summary statistics
print("\n--- Summary Statistics ---")
cached_runs = [t for t in parsed_traces if t["fg_mode"] == "cached"]
live_runs = [t for t in parsed_traces if t["fg_mode"] == "live"]
print(f"Total Traces: {len(parsed_traces)}")
print(f"Cached Mode Runs: {len(cached_runs)}")
print(f"Live FortyGuard API Runs: {len(live_runs)}")
