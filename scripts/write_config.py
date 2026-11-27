"""Create public frontend runtime configuration from CloudFormation outputs."""
import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--region", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
stack = json.load(sys.stdin)["Stacks"][0]
outputs = {entry["OutputKey"]: entry["OutputValue"] for entry in stack["Outputs"]}
config = {"apiUrl": outputs["ApiUrl"], "clientId": outputs["UserPoolClientId"],
          "cognitoDomain": outputs["CognitoDomain"], "region": args.region, "local": False}
Path(args.output).write_text("window.STRATUS_CONFIG = " + json.dumps(config) + ";\n")
