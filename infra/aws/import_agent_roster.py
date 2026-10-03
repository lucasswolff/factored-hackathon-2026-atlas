"""Privately import chat-eligible organizer agents into the demo DynamoDB table.

Only IDs and routing fields are stored. No name, email, or phone is copied.
Run with the explicit project AWS profile; this is not part of the public build.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from advisor.agents import ROSTER_KEY, DynamoAgentDirectory, eligible_agent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/service_agents.csv"))
    parser.add_argument("--profile", required=True)
    parser.add_argument("--region", default="us-east-2")
    parser.add_argument("--table", default="factored-advisor-demo")
    args = parser.parse_args()
    import boto3

    with args.source.open(encoding="utf-8-sig", newline="") as file:
        agents = [candidate for row in csv.DictReader(file)
                  if (candidate := eligible_agent(row)) is not None]
    if not agents or not any("portugués" in agent["languages"] for agent in agents):
        raise ValueError("Roster has no Portuguese chat credit specialists")
    table = boto3.Session(profile_name=args.profile, region_name=args.region).resource("dynamodb").Table(args.table)
    previous_ids = {agent["agent_id"] for agent in DynamoAgentDirectory(table).candidates()}
    current_ids = {agent["agent_id"] for agent in agents}
    with table.batch_writer() as batch:
        for agent in agents:
            batch.put_item(Item={"pk": ROSTER_KEY, "sk": agent["agent_id"], "agent": agent})
        for old_id in previous_ids - current_ids:
            batch.delete_item(Key={"pk": ROSTER_KEY, "sk": old_id})
    print(f"Imported {len(agents)} active Digital/Hybrid credit agents; no contact fields copied")


if __name__ == "__main__":
    main()
