"""Continue a frozen pilot and persist each reservation/closed batch to an existing checkpoint."""
import json
import os
from pathlib import Path
import subprocess
import sys

from evals import pilot


def run(config_path):
    config = json.loads(config_path.read_text())
    directory = Path(config["directory"])
    checkpoint = Path(config["checkpoint_path"])
    helper = Path(config["upload_helper"])
    state_path = config_path.with_name("pilot300-control-state.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {"checkpoint_version": config["checkpoint_version"]}

    def save():
        pilot.archive(directory, checkpoint)
        status = pilot.status(directory)
        payload = {"uploads": [{"local_path": str(checkpoint), "purpose": "replace_library_file",
                 "library_file_id": config["checkpoint_library_id"], "expected_current_version": state["checkpoint_version"],
                 "version_reason": f"Pilot checkpoint: {status['success']} successful, {status['errors']} errors, {status['pending']} pending"}]}
        result = subprocess.run([sys.executable, str(helper)], input=json.dumps(payload), text=True, capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError("Checkpoint save failed; no next batch will be sent. " + result.stderr[-500:])
        lines = [x for x in result.stdout.splitlines() if x.startswith('{"results"')]
        if not lines:
            raise RuntimeError("Unknown checkpoint save outcome; inspect before another write or model batch")
        receipt = json.loads(lines[-1])["results"][0]
        if receipt.get("status") != "succeeded" or not receipt.get("local_metadata_applied"):
            raise RuntimeError("Checkpoint not confirmed: " + json.dumps(receipt))
        state["checkpoint_version"] = receipt["current_version_number"]
        state["status"] = {k:v for k,v in status.items() if k != "completed_ids"}
        state["checkpoint_library_id"] = receipt["library_file_id"]
        temp = state_path.with_suffix(".tmp"); temp.write_text(json.dumps(state)); os.replace(temp, state_path)
        print(json.dumps({"checkpoint_saved": state["checkpoint_version"], **state["status"]}), flush=True)

    # Persist the preceding completed batch before reserving any further request.
    save()
    while True:
        reservation = pilot.reserve(directory, config.get("batch_size", 25))
        if reservation is None:
            break
        save()  # durable write-ahead reservation; no API request before confirmation
        try:
            pilot.batch(directory, config["url"], reservation["token"], config.get("concurrency", 2))
        except Exception:
            save()  # retain all observed/unknown outcomes before stopping
            raise
        save()
    print(json.dumps({"pilot_finished": True, **state["status"]}), flush=True)


if __name__ == "__main__":
    run(Path(sys.argv[1]))
