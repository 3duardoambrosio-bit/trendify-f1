from ops.systems.feedback_engine import generate_feedback


def main() -> None:
    suggestions = generate_feedback()

    if not suggestions:
        print("[FEEDBACK] Sin sugerencias por ahora. Sistema estable ✅")
        return

    print("=== FEEDBACK-ENGINE: SUGERENCIAS ===")
    for idx, s in enumerate(suggestions, start=1):
        print(f"\n[{idx}] code    : {s.code}")
        print(f"    message : {s.message}")
        if s.details:
            print("    details :")
            for k, v in s.details.items():
                print(f"        {k:24s}: {v}")

    print("\n[SYNAPSE] Demo Feedback-Engine completada ✅")


if __name__ == "__main__":
    main()
