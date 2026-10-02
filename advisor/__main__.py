"""Run an anonymous text conversation: python -m advisor --language es."""

import argparse

from .data_access import DemoDirectory
from .service import CAMPAIGNS, COUNTRIES, Conversation, respond
from .session import (grant_precheck_consent, grant_profile_permission,
                      profile_summary, recommendation_for_session, run_precheck,
                      select_demo_persona, sign_out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("es", "pt"), required=True)
    parser.add_argument("--country", choices=sorted(COUNTRIES))
    parser.add_argument("--campaign", choices=sorted(CAMPAIGNS))
    parser.add_argument("--model", choices=("claude-sonnet-5", "claude-haiku-4-5-20251001"),
                        default="claude-sonnet-5")
    args = parser.parse_args()
    conversation = Conversation.start(args.language, args.country, args.campaign)
    directory = DemoDirectory()
    print(conversation.opening())
    print("Type :help for demo controls; salir/sair to end. Do not enter identifiers or account details.")
    while not conversation.stopped:
        try:
            message = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        try:
            parts = message.strip().split()
            if parts and parts[0] == ":help":
                print(":personas | :persona P01 | :profile-consent yes | :profile | :recommend | :precheck-consent CARD | :precheck CARD | :sign-out")
                continue
            if parts and parts[0] == ":personas":
                for item in directory.public_list():
                    print(f"{item['alias']}: {item['country']} / {item['segment']}")
                continue
            if len(parts) == 2 and parts[0] == ":persona":
                select_demo_persona(conversation, directory, parts[1])
                print(f"Trusted demo persona {parts[1]} selected. Profile permission is still required.")
                continue
            if parts == [":profile-consent", "yes"]:
                grant_profile_permission(conversation)
                print("Profile-use permission recorded for this demo session.")
                continue
            if parts == [":profile"]:
                print(profile_summary(conversation, directory))
                continue
            if parts == [":recommend"]:
                print(recommendation_for_session(conversation, directory)["answer"])
                continue
            if len(parts) == 2 and parts[0] == ":precheck-consent":
                grant_precheck_consent(conversation, directory, parts[1].capitalize())
                print(f"One-use simulated-precheck consent recorded for {parts[1].capitalize()}.")
                continue
            if len(parts) == 2 and parts[0] == ":precheck":
                print(run_precheck(conversation, directory, parts[1].capitalize())["answer"])
                continue
            if parts == [":sign-out"]:
                sign_out(conversation, directory)
                print("Demo session and permissions cleared.")
                continue
            if parts and parts[0].startswith(":"):
                print("Unknown command. Type :help.")
                continue
            result = respond(conversation, message, model=args.model, directory=directory)
        except (ValueError, PermissionError) as exc:
            print(f"Input error: {exc}")
            continue
        print(result["answer"])
        if result["citations"]:
            print(f"Source: {result['fact_version']} / {', '.join(result['citations'])}")


if __name__ == "__main__":
    main()
