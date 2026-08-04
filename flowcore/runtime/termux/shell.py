class TermuxShellProvider:
    """Provider to run secure commands on Termux shell."""

    def run_command(self, cmd: str) -> str:
        return f"Simulated output for cmd: {cmd}"
