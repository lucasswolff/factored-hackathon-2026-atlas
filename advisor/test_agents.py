"""Checks the roster filters and country preference with fictional agent IDs."""

import unittest

from advisor.agents import ROSTER_KEY, DynamoAgentDirectory, choose_agent, eligible_agent


def row(agent_id, language, country, *, status="Active", specialty="Créditos", kind="Digital"):
    return {"agent_id": agent_id, "languages": language, "country_of_origin": country,
            "native_accent": country.lower(), "agent_status": status,
            "specialty": specialty, "agent_type": kind,
            "email": "must-not-be-copied@example.test"}


class AgentSelectionTest(unittest.TestCase):
    def test_hosted_roster_uses_permitted_scan_and_pages(self):
        class Table:
            calls = []

            def scan(self, **options):
                self.calls.append(options)
                if len(self.calls) == 1:
                    return {"Items": [{"agent": {"agent_id": "A1"}}],
                            "LastEvaluatedKey": {"pk": ROSTER_KEY, "sk": "A1"}}
                return {"Items": [{"agent": {"agent_id": "A2"}}]}

        table = Table()
        self.assertEqual([r["agent_id"] for r in DynamoAgentDirectory(table).candidates()],
                         ["A1", "A2"])
        self.assertEqual(table.calls[0]["ExpressionAttributeValues"], {":roster": ROSTER_KEY})
        self.assertEqual(table.calls[1]["ExclusiveStartKey"]["sk"], "A1")

    def test_private_contact_fields_are_dropped(self):
        agent = eligible_agent(row("A1", "español, portugués", "Mexico"))
        self.assertEqual(agent["languages"], ["español", "portugués"])
        self.assertNotIn("email", agent)

    def test_language_specialty_channel_and_country_order(self):
        rows = [row("A1", "español, portugués", "Mexico"),
                row("A2", "español, portugués", "Colombia", kind="Hybrid"),
                row("A3", "español, portugués", "Argentina", kind="Phone"),
                row("A4", "español, portugués", "Mexico", specialty="Fraudes"),
                row("A5", "español, portugués", "Mexico", status="Vacation")]
        agents = [agent for item in rows if (agent := eligible_agent(item))]
        chosen = choose_agent(agents, "pt", "México", "conversation-1")
        self.assertEqual(chosen["agent_id"], "A1")
        self.assertTrue(chosen["country_match"])
        other = choose_agent(agents, "pt", "Argentina", "conversation-1")
        self.assertIn(other["agent_id"], {"A1", "A2"})
        self.assertFalse(other["country_match"])
        self.assertEqual(chosen, choose_agent(agents, "pt", "México", "conversation-1"))
        self.assertIsNone(choose_agent(agents, "fr", "México", "conversation-1"))


if __name__ == "__main__":
    unittest.main()
